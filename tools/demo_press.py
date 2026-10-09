"""Press one of the Workbench's own buttons in a headless browser, as the operator would.

    python tools/demo_press.py <workbench url> <run id | stack | start> <button label | task | terminal:role | turn:stage | turn-then:stage:label | file:path | round:stage:path | history | hold:role:label | type-after:role:label:line | layout:WIDTHxHEIGHT | absent:label,...> <what the page should say> [note]

The Windows side of `make demo` (WSL cannot reach Windows' loopback, and Windows reaches the
Workbench's): headless Edge, driven over the DevTools protocol, opens the page, opens the run by its
link, presses the run's button with that label — an answer to its stop, Stop run, Force terminate, or the
start of the worker it is blocked by — or, given `stack` for the run, the one in the stack's popover,
opened from its chips; the page's own confirmation answered yes, and each question it asked printed;
given a note, it types it into the stop's own note first, as an answer's words are. Given `start`, it
opens New run and types the task into the page's own form, with the first repository it offers, and
presses Start run. Given `terminal:<role>`, it presses nothing: it opens that role's terminal, if it is
closed, and reads its screen as the page shows it, live from its host. Given `turn:<stage>`, it presses
nothing either: it opens the run's latest turn of that stage in its history and reads what the page shows it
produced, from that turn's record. Given `file:<path>`, it opens that file of the run's change and reads the
lines its diff shows; given `round:<stage>:<path>`, the same file in the change since the review before the run's
latest turn of that stage; given `history`, it reads the run's history: each exits 0 once what it reads holds the
words expected. Given `turn-then:<stage>:<label>`, it opens that turn first, presses the button, and reads the
turn again in the same page once what it produced is said anew: its exit code also says whether it is said
there, not pointed to the decision above. It waits for the page to report
what came of the press — the status line, or the alert, beside the control — and its exit code says
whether the page's words begin as expected; for a terminal, whether it shows them. Given
`hold:<role>:<label>`, it first opens that role's terminal — its record, while the run's worker holds no
terminal for the role — selects its first line and leaves it open past the page's old fifteen-second
retry, then presses the button with that label and waits for the role's next turn to reach the terminal:
its exit code also says whether the terminal was never drawn again — one connection until the turn, the
selection kept, the record not written twice. Given `type-after:<role>:<label>:<line>`, it presses the button
and then types the line, with Enter, into whatever the press left the keyboard in, clicking nothing: its
exit code also says whether the keyboard was in that role's terminal and no other terminal was opened, and
the note is what that terminal's screen must then show. Given `layout:<width>x<height>`, it presses nothing:
it opens the run in a window of that size and reads how the page is laid out — the run's pinned controls
seen whole at the top of the page and with the page scrolled to its history, nothing that takes the keyboard
left under them, each list of runs scrolling inside itself only past five runs — and, for each `list:run`
the expected words name, that the run is in that list; `none` names none. Given `absent:` and labels, it presses nothing
either: its exit code says whether the run's view, once shown, offers none of those buttons. Nothing is
shown on screen.
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

# A role's terminal opened, as a click on its summary opens it, and brought into sight, as the operator reads
# it — xterm draws only a terminal on screen — and its screen as the page shows it.
OPEN_TERMINAL = ("(role => { const box = document.getElementById('terminal-' + role);"
                 " if (!box.open) box.querySelector('summary').click(); box.scrollIntoView(); return true; })(%s)")
SCREEN = ("(role => { const rows = document.querySelector('#term-' + role + ' .xterm-rows');"
          " return rows ? rows.innerText : ''; })(%s)")

# A stage's latest turn in the run's history, opened as a click on its summary opens it, and what the page then
# shows it produced, from its record.
LATEST_TURN = ("const turns = document.querySelectorAll("
               "'#timeline details.turn[data-history-detail^=\"turn:' + stage + ':\"]');"
               " const turn = turns[turns.length - 1];")
OPEN_TURN = ("(stage => { " + LATEST_TURN + " if (!turn) return false;"
             " if (!turn.open) turn.querySelector('summary').click(); turn.scrollIntoView(); return true; })(%s)")
TURN_SAID = ("(stage => { " + LATEST_TURN + " const field = turn && turn.querySelector('.produced');"
             " if (!field) return ''; field.querySelectorAll('details.turn-output').forEach((d) => { d.open = true; });"
             " return field.innerText.replace(/\\s+/g, ' '); })(%s)")
# A changed file opened as a click on its row opens it — in the run's change, or in a turn's change since the review
# before it, that change opened first — and the lines its diff then shows.
OPEN_FILE = ("((scope, path) => { const box = typeof scope === 'string' ? document.querySelector(scope) : scope;"
             " const file = box && [...box.querySelectorAll('details.file')].find((f) => f.dataset.path === path);"
             " if (!file) return false; if (!file.open) file.querySelector('summary').click(); file.scrollIntoView();"
             " return true; })(%s, %s)")
FILE_LINES = ("((scope, path) => { const box = document.querySelector(scope);"
              " const file = box && [...box.querySelectorAll('details.file')].find((f) => f.dataset.path === path);"
              " return file ? [...file.querySelectorAll('.diff .ln')].map((l) => l.innerText.replace(/\\s+/g, ' ')"
              ".trim()) : []; })(%s, %s)")
OPEN_ROUND = ("(stage => { " + LATEST_TURN + " if (!turn) return false;"
              " if (!turn.open) turn.querySelector('summary').click();"
              " const change = turn.querySelector('details.round-change'); if (!change) return false;"
              " if (!change.open) change.querySelector('summary').click(); change.scrollIntoView();"
              " if (!turn.id) turn.id = 'pressed-turn'; return '#' + turn.id; })(%s)")
HISTORY_SAID = "document.getElementById('timeline').innerText.replace(/\\s+/g, ' ')"

# A role's terminal watched: the connections the page opens for it, and the xterm it makes — whose buffer,
# selection and scroll are read from it, not from what it drew. Then opened, as a click on its summary opens it:
# its xterm is the first the page makes from here, and the other role's, made once that role works, is not it.
HOLD = ("(role => { const held = window.__held = { role: role, sockets: 0, term: null, first: null };"
        " const Socket = window.WebSocket;"
        " window.WebSocket = function (url, protocols) {"
        " if (String(url).endsWith('/' + role)) held.sockets += 1; return new Socket(url, protocols); };"
        " window.WebSocket.OPEN = Socket.OPEN;"
        " const Made = window.Terminal;"
        " window.Terminal = function (options) { const term = new Made(options); held.term = held.term || term;"
        " return term; };"
        " const box = document.getElementById('terminal-' + role);"
        " box.querySelector('summary').click(); box.scrollIntoView(); return true; })(%s)")
# Its record in: the page says it is recorded, and a line of it is in the buffer.
HELD_READY = ("(h => { if (!h.term || !document.getElementById('state-' + h.role).textContent.startsWith('recorded'))"
              " return false; const buffer = h.term.buffer.active;"
              " for (let i = 0; i < buffer.length; i++) if (buffer.getLine(i).translateToString(true).trim()) return true;"
              " return false; })(window.__held)")
# The operator reads back: the view at the top, the record's first line selected.
HELD_SELECT = ("(h => { const buffer = h.term.buffer.active; let row = 0;"
               " while (row < buffer.length - 1 && !buffer.getLine(row).translateToString(true).trim()) row += 1;"
               " h.first = buffer.getLine(row).translateToString(true);"
               " h.term.scrollToTop(); h.term.select(0, row, h.first.length); return h.term.getSelection(); })(window.__held)")
HELD_READ = ("(h => { const buffer = h.term.buffer.active; let first = 0;"
             " for (let i = 0; i < buffer.length; i++) if (buffer.getLine(i).translateToString(true) === h.first) first += 1;"
             " return { sockets: h.sockets, row: buffer.baseY + buffer.cursorY, top: buffer.viewportY,"
             " selection: h.term.getSelection(), first: first,"
             " state: document.getElementById('state-' + h.role).textContent }; })(window.__held)")
# Longer than the page's old retry of a recorded terminal, which drew it again from its record every 15 s.
HOLD_SECONDS = 18

# The status line beside a control: in the nearest part of the page around it that has one. What the
# page says of a press is there — `answered: ...`, `stopping`, `terminated`, `done: ...`, `started <run
# id>`, `removed` — or, for a refusal, in the alert beside it: `not accepted: ...`, `refused: ...`.
REGION = ("(b => { let node = b.parentElement; while (node && !node.querySelector('[role=status]'))"
          " node = node.parentElement; if (!node.id) node.id = 'pressed-' + Date.now(); return node.id; })(%s)")
SAID = ("(id => [...document.getElementById(id).querySelectorAll('[role=status], [role=alert]')]"
        ".map((n) => n.textContent.trim()).find((t) => t && t !== 'sending…' && t !== 'starting…') || '')(%s)")

# After a press that leaves the keyboard in a role's terminal: whether it is there, and whether the other
# role's terminal was left closed.
KEYBOARD_IN = "(role => document.getElementById('term-' + role).contains(document.activeElement))(%s)"
OTHERS_CLOSED = ("(role => [...document.querySelectorAll('details.terminal')]"
                 ".every((box) => box.dataset.role === role || !box.open))(%s)")

# The run's page as it is laid out now: each control of its pinned strip — whether it is whole inside the
# window and nothing lies over it — and how far the page is scrolled.
CONTROLS = ("(() => [...document.querySelectorAll('#run-strip button, #run-strip a.button')]"
            ".filter((b) => b.offsetParent !== null).map((b) => { const r = b.getBoundingClientRect();"
            " const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);"
            " return { label: b.textContent.trim(), scrolled: Math.round(scrollY),"
            " seen: r.width > 0 && r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth"
            " && (hit === b || b.contains(hit)) }; }))()")
# The page scrolled to its end, then the keyboard given to a control it had scrolled past: how far below the
# pinned strip that control then is — never under it.
FOCUS_BELOW = ("(() => { scrollTo(0, document.documentElement.scrollHeight);"
               " const first = document.querySelector('#run .run-head button, #run .run-head a[href], #agents summary');"
               " if (!first) return null; first.focus();"
               " return Math.round(first.getBoundingClientRect().top"
               " - document.getElementById('run-strip').getBoundingClientRect().bottom); })()")
# Each list of runs: how many it holds, whether it scrolls inside itself, and which runs it holds.
LISTS = ("(() => Object.fromEntries(['runs-waiting', 'runs-running', 'runs-finished', 'runs-rejected'].map((id) => {"
         " const list = document.getElementById(id); const rows = [...list.querySelectorAll('a.row')];"
         " return [id, { rows: rows.length, scrolls: list.scrollHeight - list.clientHeight > 1,"
         " runs: rows.map((row) => row.dataset.run) }]; })))()")
# The rail that holds them, where it is pinned beside the run: how far it scrolls as a whole, and how many rows'
# height the tallest list past five still shows. Null where the window is too narrow for a rail beside the run.
RAIL = ("(() => { const rail = document.querySelector('.rail');"
        " if (getComputedStyle(rail).position !== 'sticky') return null;"
        " const tall = [...rail.querySelectorAll('.runs')].filter((list) => list.querySelectorAll('a.row').length > 5)"
        ".map((list) => list.clientHeight / list.querySelector('a.row').offsetHeight);"
        " return { scrolls: rail.scrollHeight - rail.clientHeight, shown: Math.max(0, ...tall),"
        " least: Math.min(...tall) }; })()")

# The page's own confirmation, when it asks one: its question, and its yes.
ASKED = ("(d => d.open ? [document.getElementById('confirm-title').textContent,"
         " document.getElementById('confirm-body').textContent].filter(Boolean).join(' ') : '')"
         "(document.getElementById('confirm'))")
YES = "document.getElementById('confirm-yes').click(); true"


def laid_out(page, run_id, size, said):
    """The run's page at the window size it was opened at: its pinned controls seen whole at the top of the
    run's page and with the page scrolled to its history; nothing that takes the keyboard left under them;
    each list of runs scrolling inside itself once it holds more than five, and never before; and each run
    `said` names, as `list:run`, in that list — `none` names none. Prints what it saw; 0 when all of it holds."""
    page.value(OPEN % json.dumps(run_id))
    wait(lambda: page.value(OPENED), 60, "the run")
    time.sleep(6)                                   # two of the page's reads of the run and of the list
    wrong = []
    # The top of the run's own page: below the runs' lists, where the window is too narrow for them beside it.
    page.value("document.getElementById('run-strip').scrollIntoView(); true")
    time.sleep(0.5)
    top = page.value(CONTROLS)
    page.value("document.getElementById('history').scrollIntoView(); true")
    time.sleep(0.5)
    scrolled = page.value(CONTROLS)
    for where, controls in (("at the top", top), ("scrolled to the history", scrolled)):
        wrong += ["%s is not seen whole %s" % (control["label"], where) for control in controls if not control["seen"]]
    below = page.value(FOCUS_BELOW)
    if below is not None and below < 0:
        wrong.append("what took the keyboard is %d px under the pinned controls" % -below)
    lists = page.value(LISTS)
    for name, found in lists.items():
        if found["rows"] > 5 and not found["scrolls"]:
            wrong.append("%s holds %d runs and does not scroll" % (name, found["rows"]))
        if found["rows"] <= 5 and found["scrolls"]:
            wrong.append("%s holds %d runs and scrolls" % (name, found["rows"]))
    if not any(found["rows"] > 5 for found in lists.values()):
        wrong.append("no list holds more than five runs, so no scrolling was proven")
    rail = page.value(RAIL)
    if rail and any(found["rows"] > 5 for found in lists.values()):
        if rail["least"] < 0.99:
            wrong.append("a list of more than five runs shows less than one of them")
        if rail["scrolls"] > 1 and rail["shown"] > 1.05:      # a heading's few pixels are not a row to give up
            wrong.append("the runs' lists scroll as a whole by %d px while one past five still shows %.1f rows"
                         % (rail["scrolls"], rail["shown"]))
    for placed in filter(None, said.split(",")) if said != "none" else ():
        name, run = placed.split(":", 1)
        if run not in lists.get(name, {}).get("runs", ()):
            wrong.append("run %s is not listed under %s" % (run, name))
    print("laid the page out at %s: its controls %s, seen whole at the top and with the page scrolled %d px; what "
          "took the keyboard is %s px below them; the lists hold %s runs and %s scroll; %s"
          % (size, ", ".join(control["label"] for control in top) or "none, the run being closed",
             max([control["scrolled"] for control in scrolled] or [0]), below,
             ", ".join("%s %d" % (name[len("runs-"):], found["rows"]) for name, found in lists.items()),
             ", ".join(name[len("runs-"):] for name, found in lists.items() if found["scrolls"]) or "none",
             "beside the run they scroll as a whole by %d px, a list past five showing %.1f rows"
             % (rail["scrolls"], rail["shown"]) if rail else "they lie above the run, not beside it"))
    for text in wrong:
        print("wrong: %s" % text)
    return 1 if wrong else 0


def main(url, run_id, label, said, note=None):
    profile = tempfile.mkdtemp(prefix="orchestra-demo-edge-")
    # A layout is read at the window size it names; every press at the browser's own.
    size = label.split(":", 1)[1] if label.startswith("layout:") else None
    edge = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--no-first-run", "--remote-debugging-port=0",
                             "--user-data-dir=" + profile]
                            + (["--window-size=" + size.replace("x", ",")] if size else []) + ["about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    asked = []
    held = then = typed = None
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
            if size:
                return laid_out(page, run_id, size, said)
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
            if label.startswith("turn:"):
                stage = label.split(":", 1)[1]
                page.value(OPEN % json.dumps(run_id))
                wait(lambda: page.value(OPENED), 60, "the run")
                wait(lambda: page.value(OPEN_TURN % json.dumps(stage)), 60, "the %s turn in the history" % stage)
                message = wait(lambda: (lambda text: text if said in text else "")(
                    page.value(TURN_SAID % json.dumps(stage))), 60, "the %s turn's record to show %r" % (stage, said))
                print("opened the %s turn's record in the Workbench: %r" % (stage, " ".join(message.split())))
                return 0
            if label.startswith(("file:", "round:", "history")):
                page.value(OPEN % json.dumps(run_id))
                wait(lambda: page.value(OPENED), 60, "the run")
                if label == "history":
                    shown = wait(lambda: (lambda text: text if said in text else "")(page.value(HISTORY_SAID)), 60,
                                 "the history to say %r" % said)
                    print("read the run's history in the Workbench: it says %r" % said)
                    return 0
                if label.startswith("file:"):
                    scope, path = "#change", label.split(":", 1)[1]
                else:
                    stage, path = label.split(":", 2)[1:]
                    scope = wait(lambda: page.value(OPEN_ROUND % json.dumps(stage)), 60,
                                 "the %s turn's change since the review before it" % stage)
                wait(lambda: page.value(OPEN_FILE % (json.dumps(scope), json.dumps(path))), 60, "the file %s" % path)
                lines = wait(lambda: [line for line in page.value(FILE_LINES % (json.dumps(scope), json.dumps(path)))
                                      if said in line], 60, "the diff of %s to show %r" % (path, said))
                print("opened %s in the Workbench's viewer: it shows %r" % (path, lines[0]))
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
            if label.startswith("turn-then:"):
                # A turn opened before the press, and what it produced read again once the run has moved on, in
                # the same page: what was shown above is said in the turn once the decision no longer shows it.
                stage, label = label.split(":", 2)[1:]
                page.value(OPEN % json.dumps(run_id))
                wait(lambda: page.value(OPENED), 60, "the run")
                wait(lambda: page.value(OPEN_TURN % json.dumps(stage)), 60, "the %s turn in the history" % stage)
                then = {"stage": stage,
                        "before": wait(lambda: page.value(TURN_SAID % json.dumps(stage)), 60, "its record")}
            if label.startswith("type-after:"):
                # A press that leaves the keyboard in a role's terminal, and a line typed there without a click.
                role, label, line = label.split(":", 3)[1:]
                typed = {"role": role, "line": line}
            if label.startswith("hold:"):
                role, label = label.split(":", 2)[1:]
                page.value(OPEN % json.dumps(run_id))
                wait(lambda: page.value(OPENED), 60, "the run")
                page.value(HOLD % json.dumps(role))
                wait(lambda: page.value(HELD_READY), 60, "the %s terminal's record" % role)
                held = {"role": role, "selected": page.value(HELD_SELECT)}
                time.sleep(HOLD_SECONDS)
                held["before"] = page.value(HELD_READ)
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
            if note and not typed:
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
            if typed:
                # Where the press left the keyboard, read before a key is sent; then the line, as keys: text
                # into whatever has the keyboard, and Enter. The terminal's screen says whether its agent got it.
                role = json.dumps(typed["role"])
                typed["keyboard"] = page.value(KEYBOARD_IN % role)
                typed["alone"] = page.value(OTHERS_CLOSED % role)
                page.call("Input.insertText", text=typed["line"])
                for kind in ("rawKeyDown", "keyUp"):
                    page.call("Input.dispatchKeyEvent", type=kind, key="Enter", code="Enter",
                              windowsVirtualKeyCode=13, nativeVirtualKeyCode=13)
                screen = wait(lambda: (lambda text: text if note in text else "")(page.value(SCREEN % role)), 90,
                              "the %s terminal to show %r" % (typed["role"], note))
                typed["screen"] = [text for text in screen.splitlines() if note in text][-1].strip()
            if then:
                then["after"] = wait(lambda: (lambda text: text if text != then["before"] else "")(
                    page.value(TURN_SAID % json.dumps(then["stage"]))), 300,
                    "the %s turn to say again what it produced" % then["stage"])
            if held:
                # The role's next turn, on its worker: the page connects to it again and adds what it drew,
                # below what was there.
                before = held["before"]
                held["after"] = wait(lambda: (lambda now: now if now["sockets"] > before["sockets"]
                                              and now["row"] > before["row"] else None)(page.value(HELD_READ)),
                                     180, "the %s's next turn in its terminal" % held["role"])
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
    if typed:
        print("the keyboard was %s the %s terminal, %s; %r typed there, and its screen shows %r"
              % ("in" if typed["keyboard"] else "NOT in", typed["role"],
                 "the only one opened" if typed["alone"] else "NOT the only one opened", typed["line"], typed["screen"]))
        return 0 if shown.startswith(said) and typed["keyboard"] and typed["alone"] else 1
    if then:
        print("its %s turn, opened before: %r, then %r" % (then["stage"], then["before"], then["after"]))
        return 0 if shown.startswith(said) and "Shown above" not in then["after"] else 1
    if held:
        before, after = held["before"], held["after"]
        print("its %s terminal, its record's first line %r selected: after %d s %d connection, the view at line "
              "%d, %r still selected; after its next turn %d connections, its cursor from row %d to %d, the "
              "record's first line there %d time, %r still selected"
              % (held["role"], held["selected"], HOLD_SECONDS, before["sockets"], before["top"],
                 before["selection"], after["sockets"], before["row"], after["row"], after["first"],
                 after["selection"]))
        undrawn = (before["sockets"] == 1 and before["top"] == 0 and held["selected"]
                   and before["selection"] == after["selection"] == held["selected"] and after["first"] == 1)
        return 0 if shown.startswith(said) and undrawn else 1
    return 0 if shown.startswith(said) else 1


if __name__ == "__main__":
    if len(sys.argv) not in (5, 6):
        sys.exit(__doc__.strip().splitlines()[2].strip())
    sys.exit(main(*sys.argv[1:]))
