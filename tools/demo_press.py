"""Press one of the Workbench's own buttons in a headless browser, as the operator would.

    python tools/demo_press.py <workbench url> <run id | stack | start> <button label | task | terminal:role> <what the page should say> [note]

The Windows side of `make demo` (WSL cannot reach Windows' loopback, and Windows reaches the
Workbench's): headless Edge, driven over the DevTools protocol, opens the page, selects the run,
presses the run's button with that label — an answer to its stop, Stop run, Force terminate, or the
start of the worker it is blocked by — or, given `stack` for the run, the stack panel's; the page's own
confirmation accepted, and each question it asked printed; given a note, it types it into the stop's own
note first, as an answer's words are. Given `start`, it types the task into the
page's own form, with the first repository it offers, and presses Start. Given `terminal:<role>`, it
presses nothing: it reads that role's terminal as the page shows it, live from its host. It waits for
the page to report what came of it, and its exit code says whether the page's words begin as expected
— for a terminal, whether it shows them. Nothing is shown on screen.
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
    """The run's or the stack panel's button with that label, once it is shown and enabled."""
    return ("[...document.querySelectorAll('#run button, #stack button')].find((b) => b.textContent === %s"
            " && !b.disabled && b.offsetParent !== null)" % json.dumps(label))


# A role's terminal as the page shows it: every line of its screen and scrollback.
SCREEN = ("(role => { const entry = terminals[role]; if (!entry) return ''; const buffer = entry.term.buffer.active;"
          " const lines = []; for (let i = 0; i < buffer.length; i++) { const line = buffer.getLine(i);"
          " if (line) lines.push(line.translateToString(true)); } return lines.join('\\n'); })(%s)")

# What the page said of the press, in the result line of the button's own card: `answered: ...` for
# an answer, `stopping` or `terminated` for a run's lifecycle, `done: ...` or `failed: ...` for the
# stack, `started <run id>` for the start form, `not accepted: ...` or `refused: ...` for a refusal.
SAID = "(t => t && t !== 'sending…' && t !== 'starting…' ? t : '')(document.getElementById(%s).textContent)"


def main(url, run_id, label, said, note=None):
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
            # The page asks before an answer that lands or removes work; the operator says yes, and what
            # it asked is kept.
            page.value("window.asked = []; window.confirm = (text) => { window.asked.push(String(text));"
                       " return true; }; true")
            if label.startswith("terminal:"):
                role = label.split(":", 1)[1]
                page.value("select(%s); true" % json.dumps(run_id))
                screen = wait(lambda: (lambda text: text if said in text else "")(
                    page.value(SCREEN % json.dumps(role))), 90, "the %s terminal to show %r" % (role, said))
                shown = [line for line in screen.splitlines() if said in line][-1].strip()
                print("read the %s terminal in the Workbench: it shows %r" % (role, shown))
                return 0
            if run_id == "start":
                wait(lambda: page.value("document.getElementById('start-repo').options.length > 0"), 30,
                     "the repositories the page offers")
                page.value("document.getElementById('start-task').value = %s; "
                           "document.querySelector('#start button[type=submit]').click(); true" % json.dumps(label))
                line = "start-result"
            else:
                if run_id != "stack":
                    page.value("select(%s); true" % json.dumps(run_id))
                wait(lambda: page.value(button(label) + " !== undefined"), 60, "the %r button" % label)
                line = page.value("(b => b.closest('.card').querySelector('[id$=\"-result\"]').id)(%s)"
                                  % button(label))
                if note:
                    page.value("document.getElementById('stop-note').value = %s; true" % json.dumps(note))
                page.value(button(label) + ".click(); true")
            # A stack action waits until what it started is up: a worker polling, Temporal answering.
            shown = wait(lambda: page.value(SAID % json.dumps(line)), 300, "the page's word on it")
            asked = page.value("window.asked")
    finally:
        edge.terminate()
        try:
            edge.wait(10)
        except subprocess.TimeoutExpired:
            edge.kill()
        shutil.rmtree(profile, ignore_errors=True)
    print("pressed %r in the Workbench: the page said %r" % (label, shown))
    for text in asked:
        print("it asked: %s" % text)
    return 0 if shown.startswith(said) else 1


if __name__ == "__main__":
    if len(sys.argv) not in (5, 6):
        sys.exit(__doc__.strip().splitlines()[2].strip())
    sys.exit(main(*sys.argv[1:]))
