"""Press one of the Workbench's own buttons in a headless browser, as the operator would.

    python tools/demo_press.py <workbench url> <run id> <button label> <what the page should say>

The Windows side of `make demo` (WSL cannot reach Windows' loopback, and Windows reaches the
Workbench's): headless Edge, driven over the DevTools protocol, opens the page, selects the run,
presses the run's button with that label — an answer to its stop, or Stop run or Force terminate,
the page's own confirmation accepted — and waits for the page to report what came of it. Its exit
code says whether the page said what was expected. Nothing is shown on screen.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

from websockets.sync.client import connect

EDGE = os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                    "Microsoft", "Edge", "Application", "msedge.exe")


def wait(probe, seconds, what):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            found = probe()
        except OSError:
            found = None
        if found:
            return found
        time.sleep(0.3)
    raise SystemExit("gave up waiting for %s" % what)


class Page:
    """One page, driven over the DevTools protocol: commands out, their replies in, events skipped."""

    def __init__(self, socket):
        self.socket, self.next = socket, 0

    def call(self, method, **params):
        self.next += 1
        self.socket.send(json.dumps({"id": self.next, "method": method, "params": params}))
        while True:
            reply = json.loads(self.socket.recv())
            if reply.get("id") == self.next:
                if "error" in reply:
                    raise SystemExit("%s failed: %s" % (method, reply["error"]))
                return reply.get("result", {})

    def value(self, expression):
        return self.call("Runtime.evaluate", expression=expression, returnByValue=True)["result"].get("value")


def button(label):
    """The run's button with that label, once it is shown and enabled."""
    return ("[...document.querySelectorAll('#run button')].find((b) => b.textContent === %s && !b.disabled"
            " && b.offsetParent !== null)" % json.dumps(label))


# What the page said of the press, in the result line of the button's own card: `answered: ...` for
# an answer, `stopping` or `terminated` for a run's lifecycle, `not accepted: ...` for a refusal.
SAID = "(t => t && t !== 'sending…' ? t : '')(document.getElementById(%s).textContent)"


def main(url, run_id, label, said):
    profile = tempfile.mkdtemp(prefix="orch-demo-edge-")
    edge = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--no-first-run", "--remote-debugging-port=0",
                             "--user-data-dir=" + profile, "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        # Edge writes the port it chose into its profile once it listens.
        port = wait(lambda: open(os.path.join(profile, "DevToolsActivePort")).readline().strip(), 30,
                    "Edge's debugging port")
        target = wait(lambda: next(page["webSocketDebuggerUrl"] for page in json.load(urllib.request.urlopen(
            "http://127.0.0.1:%s/json/list" % port)) if page.get("type") == "page"), 30, "a page to drive")
        with connect(target, max_size=None) as socket:
            page = Page(socket)
            page.call("Page.navigate", url=url)
            wait(lambda: page.value("document.readyState === 'complete' && typeof select === 'function'"), 30,
                 "the Workbench page")
            # The page asks before an answer that lands or removes work; the operator says yes.
            page.value("window.confirm = () => true; select(%s); true" % json.dumps(run_id))
            wait(lambda: page.value(button(label) + " !== undefined"), 60, "the %r button" % label)
            line = page.value("(b => b.closest('.card').querySelector('[id$=\"-result\"]').id)(%s)" % button(label))
            page.value(button(label) + ".click(); true")
            shown = wait(lambda: page.value(SAID % json.dumps(line)), 60, "the page's word on it")
    finally:
        edge.terminate()
        try:
            edge.wait(10)
        except subprocess.TimeoutExpired:
            edge.kill()
        shutil.rmtree(profile, ignore_errors=True)
    print("pressed %r in the Workbench: the page said %r" % (label, shown))
    return 0 if shown == said else 1


if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit(__doc__.strip().splitlines()[2].strip())
    sys.exit(main(*sys.argv[1:]))
