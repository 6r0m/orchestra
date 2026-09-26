"""Press one of the Workbench's own buttons in a headless browser, as the operator would.

    python tools/demo_press.py <workbench url> <run id | stack | start> <button label | task | terminal:role | absent:label,...> <what the page should say> [note]

The Windows side of `make demo` (WSL cannot reach Windows' loopback, and Windows reaches the
Workbench's): headless Edge, driven over the DevTools protocol, opens the page, opens the run by its
link, presses the run's button with that label — an answer to its stop, Stop run, Force terminate, or the
start of the worker it is blocked by — or, given `stack` for the run, the one in the stack's popover,
opened from its chips; the page's own confirmation answered yes, and each question it asked printed;
given a note, it types it into the stop's own note first, as an answer's words are. Given `start`, it
opens New run and types the task into the page's own form, with the first repository it offers, and
presses Start run. Given `terminal:<role>`, it presses nothing: it opens that role's terminal, if it is
closed, and reads its screen as the page shows it, live from its host. It waits for the page to report
what came of the press — the status line, or the alert, beside the control — and its exit code says
whether the page's words begin as expected; for a terminal, whether it shows them. Given `absent:` and
labels, it presses nothing either: its exit code says whether the run's view, once shown, offers none of
those buttons. Nothing is shown on screen.
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


# A run opened as its link in the list opens it: by the URL's fragment.
OPEN = "(id => { location.hash = '#run=' + encodeURIComponent(id); return true; })(%s)"
OPENED = "document.getElementById('run-task').textContent.length > 0"


def button(scope, label):
    """The button with that label in `scope`, once it is shown and enabled."""
    return ("[...document.querySelectorAll('%s button')].find((b) => b.textContent.trim() === %s"
            " && !b.disabled && b.offsetParent !== null)" % (scope, json.dumps(label)))


# Whether the run's view shows a button with that label, enabled or not.
SHOWN = ("(label => [...document.querySelectorAll('#run button')].some((b) => b.textContent.trim() === label"
         " && b.offsetParent !== null))(%s)")

# A role's terminal opened, as a click on its summary opens it, and its screen as the page shows it.
OPEN_TERMINAL = ("(role => { const box = document.getElementById('terminal-' + role);"
                 " if (!box.open) box.querySelector('summary').click(); return true; })(%s)")
SCREEN = ("(role => { const rows = document.querySelector('#term-' + role + ' .xterm-rows');"
          " return rows ? rows.innerText : ''; })(%s)")

# The status line beside a control: in the nearest part of the page around it that has one. What the
# page says of a press is there — `answered: ...`, `stopping`, `terminated`, `done: ...`, `started <run
# id>`, `removed` — or, for a refusal, in the alert beside it: `not accepted: ...`, `refused: ...`.
REGION = ("(b => { let node = b.parentElement; while (node && !node.querySelector('[role=status]'))"
          " node = node.parentElement; if (!node.id) node.id = 'pressed-' + Date.now(); return node.id; })(%s)")
SAID = ("(id => [...document.getElementById(id).querySelectorAll('[role=status], [role=alert]')]"
        ".map((n) => n.textContent.trim()).find((t) => t && t !== 'sending…' && t !== 'starting…') || '')(%s)")

# The page's own confirmation, when it asks one: its question, and its yes.
ASKED = ("(d => d.open ? [document.getElementById('confirm-title').textContent,"
         " document.getElementById('confirm-body').textContent].filter(Boolean).join(' ') : '')"
         "(document.getElementById('confirm'))")
YES = "document.getElementById('confirm-yes').click(); true"


def main(url, run_id, label, said, note=None):
    profile = tempfile.mkdtemp(prefix="orch-demo-edge-")
    edge = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--no-first-run", "--remote-debugging-port=0",
                             "--user-data-dir=" + profile, "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    asked = []
    try:
        # Edge writes the port it chose into its profile once it listens.
        port = wait(lambda: open(os.path.join(profile, "DevToolsActivePort")).readline().strip(), 30,
                    "Edge's debugging port")
        target = wait(lambda: next(page["webSocketDebuggerUrl"] for page in json.load(urllib.request.urlopen(
            "http://127.0.0.1:%s/json/list" % port)) if page.get("type") == "page"), 30, "a page to drive")
        with connect(target, max_size=None) as socket:
            page = Page(socket)
            page.call("Page.navigate", url=url)
            wait(lambda: page.value("document.readyState === 'complete' && "
                                    "document.querySelector('#runs-finished li') !== null"), 30, "the Workbench page")
            if label.startswith("terminal:"):
                role = label.split(":", 1)[1]
                page.value(OPEN % json.dumps(run_id))
                wait(lambda: page.value(OPENED), 60, "the run")
                page.value(OPEN_TERMINAL % json.dumps(role))
                screen = wait(lambda: (lambda text: text if said in text else "")(
                    page.value(SCREEN % json.dumps(role))), 90, "the %s terminal to show %r" % (role, said))
                shown = [line for line in screen.splitlines() if said in line][-1].strip()
                print("read the %s terminal in the Workbench: it shows %r" % (role, shown))
                return 0
            if label.startswith("absent:"):
                labels = label.split(":", 1)[1].split(",")
                page.value(OPEN % json.dumps(run_id))
                wait(lambda: page.value(OPENED), 60, "the run")
                # Two of the page's reads of the run, so what it offers is what it read of the run as it is now.
                time.sleep(6)
                offered = [text for text in labels if page.value(SHOWN % json.dumps(text))]
                print("the Workbench offers run %s %s" % (run_id, ", ".join(offered) or "none of: " + ", ".join(labels)))
                return 1 if offered else 0
            if run_id == "start":
                page.value("location.hash = '#new'; true")
                wait(lambda: page.value("document.getElementById('start-repo').options.length > 0"), 30,
                     "the repositories the page offers")
                page.value("document.getElementById('start-task').value = %s; true" % json.dumps(label))
                pressed = button("#start", "Start run")
            else:
                if run_id == "stack":
                    # The stack's controls are in the popover its chips open.
                    page.value("(p => { if (!p.matches(':popover-open')) document.getElementById('stack-button')"
                               ".click(); return true; })(document.getElementById('stack-panel'))")
                    pressed = button("#stack-panel", label)
                    # The stack's result shows under the top bar, not in the popover a confirmation closes.
                else:
                    page.value(OPEN % json.dumps(run_id))
                    wait(lambda: page.value(OPENED), 60, "the run")
                    pressed = button("#run", label)
            wait(lambda: page.value(pressed + " !== undefined"), 60, "the %r button" % label)
            # Typed once its stop is drawn: drawing a new stop clears the note.
            if note:
                page.value("document.getElementById('stop-note').value = %s; true" % json.dumps(note))
            region = "banners" if run_id == "stack" else page.value(REGION % pressed)
            page.value(pressed + ".click(); true")
            # The page asks before a press that stops, lands or removes work; the operator says yes, and what
            # it asked is kept.
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                question = page.value(ASKED)
                if question:
                    asked.append(question)
                    page.value(YES)
                    break
                time.sleep(0.2)
            # A stack action waits until what it started is up: a worker polling, Temporal answering.
            shown = wait(lambda: page.value(SAID % json.dumps(region)), 300, "the page's word on it")
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
