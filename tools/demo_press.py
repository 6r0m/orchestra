"""Press one of the Workbench's own buttons in a headless browser, as the operator would.

    python tools/demo_press.py <workbench url> <run id | stack | start | page> <button label | task | refused:repo:task | answered:status | markdown | markdown-safety | change:words | change-rows | change-idle | terminal-fit:role | terminal-rows:role | handoff | approval-notes | hints | terminal:role | turn:stage | turn-then:stage:label | file:path | round:stage:path | history | hold:role:label | type-after:role:label:line | layout:WIDTHxHEIGHT | absent:label,...> <what the page should say> [note]

The Windows side of `make demo` (WSL cannot reach Windows' loopback, and Windows reaches the
Workbench's): headless Edge, driven over the DevTools protocol, opens the page, opens the run by its
link, presses the run's button with that label — an answer to its stop, Stop run, Force terminate, or the
start of the worker it is blocked by — or, given `stack` for the run, the one in the stack's popover,
opened from its chips; the page's own confirmation answered yes, and each question it asked printed;
given a note, it types it into the stop's own note first, as an answer's words are, the page hearing it typed —
so a button that then names the note, *Approve with note*, is pressed by that name. Given `start`, it
opens New run and types the task into the page's own form, with the first repository it offers, and
presses Start run; given `refused:<repo>:<task>` for it, it starts the run on that listed repository and
reads the window the page opens once the run is refused: its exit code says whether the window says the
words expected, stays open through the page's reads and a move to another view, and closes on its Close;
given `answered:<status>`, the page's start is answered in the page itself with that HTTP status, or with no
answer at all for `none`, and no write of the page's reaches any server: its exit code says whether the window
then names the words expected and the form's alert says the same kind of thing — refused, or not confirmed.
Given `markdown`, it presses nothing: it opens the run and reads its decision's evidence as the page draws
it, and exits 0 when a table there holds the words expected and no table is left as rows of pipes. Given
`markdown-safety` for the run `page`, it presses nothing either: it has the page's own renderer draw a fixed
Markdown text, hostile parts among it, and exits 0 when every part is drawn as it should be and nothing
outside the renderer's own elements is made, no link leads off the web and nothing is loaded.
Given `change:<words>`, it presses nothing but a file: it opens the run and waits for its change, live, to
list the file expected, then opens that file: it exits 0 when the change comes before the terminals with
nothing pressed to read it, lists that file, and its diff shows the words — and then presses *Copy all changes*,
the clipboard stood in for, until what it copied names that file with those words. Given `change-rows`, the page's
socket for the run's change and its reads of a file's diff are stood in for before the page loads, and three
summaries are sent: it exits 0 when a file opened stays open and is not read again while another file comes,
and is read once more, and only it, when it changes. Given `change-idle`, the same stand-in watches the run's
page: it exits 0 when the page, its run waiting with no role at work, opens no socket for the change. Given
`terminal-fit:<role>`, in a window as narrow as an operator's, what the page sends that role's agent is recorded and
dropped from before it loads, and its terminal read: it exits 0 when its text and scrollbar fit its box, a drag of
the scrollbar's thumb scrolls it back and selects nothing, Maximize fills the window drawn larger and Restore puts it
back, and Ctrl+C on a selection copies it and sends nothing — with nothing selected, a live agent's still. Given
`terminal-rows:<role>`, in a window taller than wide, as a portrait display's, through the worker's own socket: it
exits 0 when Maximize has the agent's terminal take as many rows as fill the window, and Restore puts back its
usual rows. Given `handoff`, the run's status is stood in for from before the page loads — a blocker taking guidance to either role,
with what an agent last answered the operator — and the page's answers caught, none reaching the Workbench: it
exits 0 when the card names the agent that answered and offers the other first, is drawn anew when the other
answers the same words, and each of its four presses — the answer sent to either role, a note guiding either —
sends exactly its action with exactly its words. Given `approval-notes`, the same stands in an approval, first one
whose stop says it takes a note, then one that does not, as a worker from before notes publishes it: it exits 0
when Approve says the note goes with it and sends it at the first, and at the second keeps Approve, sends nothing
while a note is written — saying why at the note — and sends Approve alone once the note is cleared. Given
`hints`, it presses nothing but the stack's chips: it visits New run, Settings and — for a run other than `page`
— that run's page, and exits 0 when every button shown outside a dialog says on hover what it does.
Given `terminal:<role>`, it presses nothing: it opens that role's terminal, if it is
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
shown on screen. Given `accounting`, it reads a priced run, verifies zero/tiny/unknown/partial and
API-equivalent presentation, disclosure focus across cost refresh, tab USD, and responsive layouts
through 320 pixels and 200% CSS zoom; its cropped screenshot goes only to ignored `tmp/`.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
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
             " const change = box && box.closest('details.change'); if (change) change.open = true;"
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

# The page's window saying a run was refused, while it is open: what it says, its parts in order.
REFUSAL = ("(d => d && d.open ? [...d.querySelectorAll('h2, p, pre')].filter((n) => !n.hidden)"
           ".map((n) => n.textContent.trim()).filter(Boolean).join(' | ') : '')(document.getElementById('refusal'))")

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


def refused(page, repo, task, said):
    """A run started as the operator starts one, on the listed repository `repo`, which its host refuses: the
    window the page then opens — whether it says `said`, stays open through the page's reads and a move to
    another view, and closes on its own Close. Prints what it saw; 0 when all of it holds."""
    page.value("location.hash = '#new'; true")
    wait(lambda: page.value("[...document.getElementById('start-repo').options].some((o) => o.value === %s)"
                            % json.dumps(repo)), 30, "the page offering the repository %s" % repo)
    page.value("document.getElementById('start-repo').value = %s; document.getElementById('start-task').value = %s;"
               " true" % (json.dumps(repo), json.dumps(task)))
    pressed = button("#start", "Start run")
    wait(lambda: page.value(pressed + " !== undefined"), 60, "the 'Start run' button")
    region = page.value(REGION % pressed)
    page.value(pressed + ".click(); true")
    started = wait(lambda: page.value(SAID % json.dumps(region)), 60, "the page's word on the start")
    print("pressed 'Start run' on %s in the Workbench: the page said %r" % (repo, started))
    window = wait(lambda: page.value(REFUSAL), 120, "the page's window saying why the run was refused")
    print("a window opened: %r" % window)
    time.sleep(6)                                   # two of the page's reads of the runs and of the run it opened
    stayed = page.value(REFUSAL) == window
    page.value("location.hash = '#worktrees'; true")
    time.sleep(1)
    moved = page.value(REFUSAL) == window
    page.value("document.getElementById('refusal-close').click(); true")
    shut = not page.value(REFUSAL)
    print("it %s open through the page's reads, %s open once the page moved to Worktrees, and %s on its Close"
          % ("stayed" if stayed else "did NOT stay", "stayed" if moved else "did NOT stay",
             "closed" if shut else "did NOT close"))
    return 0 if started.startswith("started ") and said in window and stayed and moved and shut else 1


# Every write of the page's answered in the page, so none reaches the Workbench: its start with `status` — an
# HTTP status, or none at all for `none` — and any other write refused outright. Its reads still go through.
ANSWER_STARTS = ("(answer => { const real = window.fetch; window.__starts = 0;"
                 " window.fetch = (path, options) => {"
                 " if (!(options && options.method === 'POST')) return real(path, options);"
                 " if (path !== '/api/runs') return Promise.reject(new TypeError('this check sends no other write'));"
                 " window.__starts += 1;"
                 " if (answer === 'none') return Promise.reject(new TypeError('Failed to fetch'));"
                 " return Promise.resolve(new Response(JSON.stringify({ error: 'answered ' + answer + ' by the check' }),"
                 " { status: Number(answer), headers: { 'Content-Type': 'application/json' } })); };"
                 " return true; })(%s)")


def answered(page, status, said):
    """A start the page sends, answered in the page with `status` — or with no answer, for `none` — so nothing is
    started anywhere: whether the window then says `said`, the form's alert says the same kind of thing — a 4xx
    is refused, anything else not confirmed — the page sent the start once, and the window closes on its Close.
    Prints what it saw; 0 when all of it holds."""
    page.value("location.hash = '#new'; true")
    wait(lambda: page.value("document.getElementById('start-repo').options.length > 0"), 30,
         "the repositories the page offers")
    page.value(ANSWER_STARTS % json.dumps(status))
    page.value("document.getElementById('start-task').value = %s; true" % json.dumps("A start answered " + status))
    pressed = button("#start", "Start run")
    wait(lambda: page.value(pressed + " !== undefined"), 60, "the 'Start run' button")
    region = page.value(REGION % pressed)
    page.value(pressed + ".click(); true")
    window = wait(lambda: page.value(REFUSAL), 30, "the page's window on the start answered %s" % status)
    alert = wait(lambda: page.value(SAID % json.dumps(region)), 10, "the form's word on it")
    sent = page.value("window.__starts")
    page.value("document.getElementById('refusal-close').click(); true")
    shut = not page.value(REFUSAL)
    kind = "refused: " if status.isdigit() and 400 <= int(status) < 500 else "not confirmed: "
    print("the start answered %s in the page, sent %s time(s): the window said %r; the form said %r; the window %s "
          "on its Close" % (status, sent, window, alert, "closed" if shut else "did NOT close"))
    return 0 if said in window and alert.startswith(kind) and sent == 1 and shut else 1


# The decision's evidence as the page draws it: its tables' cells, and whether a Markdown table's rule row is left
# in its text as pipes.
EVIDENCE = ("(() => { const box = document.getElementById('stop-evidence');"
            " if (!box || !box.offsetParent || !box.textContent.trim()) return null;"
            " return { cells: [...box.querySelectorAll('table th, table td')].map((c) => c.textContent.trim()),"
            " strong: box.querySelectorAll('strong').length, pipes: /\\|\\s*:?-{3,}/.test(box.innerText),"
            " text: box.innerText.replace(/\\s+/g, ' ').slice(0, 300) }; })()")


def markdown(page, run_id, said):
    """The run's decision, its evidence drawn as Markdown: 0 when a table there holds `said` and no table is left
    as rows of pipes. Prints what it saw."""
    page.value(OPEN % json.dumps(run_id))
    wait(lambda: page.value(OPENED), 60, "the run")
    shown = wait(lambda: page.value(EVIDENCE), 60, "the run's decision and its evidence")
    print("the decision's evidence in the Workbench: %d table cells %s, %d bold, %s; it reads %r"
          % (len(shown["cells"]), shown["cells"][:8], shown["strong"],
             "a table left as rows of pipes" if shown["pipes"] else "no table left as pipes", shown["text"]))
    return 0 if any(said in cell for cell in shown["cells"]) and not shown["pipes"] else 1


# Markdown an agent could write, hostile parts among it: raw HTML, a script, an event attribute, a `javascript:`
# link, an image, a path on the agent's host, and what an answer is made of.
SAMPLE = "\n".join([
    "## Heading", "", "| Capability | Verdict |", "|:--|--:|", "| **audio** | `keep` |", "", "- one", "- two", "",
    "> quoted", "", "```js", "let a = 1;", "```", "",
    "See https://example.com/a and [docs](https://example.com/b).", "",
    "[local](C:/path/to/repo/Source/File.h:35) [bad](javascript:alert(1)) ![pic](https://example.com/p.png)", "",
    "<img src=x onerror=alert(1)> <script>alert(1)</script> <b onclick=alert(1)>raw</b>"])
# The page's renderer imported in the page and given SAMPLE: what it made of each part.
SAFETY = ("import('/markdown.js').then((m) => { const box = m.markdown(%s); const all = [...box.querySelectorAll('*')];"
          " return { tags: [...new Set(all.map((n) => n.tagName.toLowerCase()))].sort(),"
          " cells: box.querySelectorAll('table th, table td').length,"
          " aligned: [...box.querySelectorAll('th, td')].map((c) => c.style.textAlign),"
          " links: [...box.querySelectorAll('a')].map((a) => [a.getAttribute('href'), a.target, a.rel]),"
          " local: [...box.querySelectorAll('[title]')].map((n) => [n.textContent, n.title]),"
          " events: all.filter((n) => [...n.attributes].some((x) => /^on/i.test(x.name))).length,"
          " text: box.textContent, line: (l => ({ tags: [...l.querySelectorAll('*')].map((n) => n.tagName.toLowerCase()),"
          " text: l.textContent }))(m.markdownLine(%s, 'first-line')) }; })")
# A summary's one line, drawn inline: its emphasis drawn, its link and raw HTML its words.
LINE = "**gist** with [a link](https://example.com/c) and <b onclick=alert(1)>raw</b>"
# Every element the renderer may make, and no other.
ALLOWED = {"div", "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "blockquote", "table", "thead",
           "tbody", "tr", "th", "td", "strong", "em", "s", "code", "pre", "hr", "br", "a", "span"}


def markdown_safety(page):
    """The page's renderer given SAMPLE: 0 when the table, list, quote, code and links are drawn, the path stays
    words with its target on hover, and nothing outside ALLOWED is made — no image, script or event attribute,
    no link off the web — the raw HTML kept as its words. Prints what it saw."""
    found = page.call("Runtime.evaluate", expression=SAFETY % (json.dumps(SAMPLE), json.dumps(LINE)),
                      awaitPromise=True, returnByValue=True)
    if "exceptionDetails" in found:
        print("the page's renderer could not be used: %s" % found["exceptionDetails"].get("exception", {})
              .get("description", found["exceptionDetails"].get("text")))
        return 1
    seen = found["result"]["value"]
    wrong = []
    if set(seen["tags"]) - ALLOWED:
        wrong.append("it made %s" % sorted(set(seen["tags"]) - ALLOWED))
    for tag in ("table", "ul", "blockquote", "pre", "code", "strong", "h2"):
        if tag not in seen["tags"]:
            wrong.append("no %s" % tag)
    if seen["cells"] != 4 or seen["aligned"] != ["left", "right", "left", "right"]:
        wrong.append("the table is %d cells aligned %s" % (seen["cells"], seen["aligned"]))
    web = [["https://example.com/a", "_blank", "noopener noreferrer"],
           ["https://example.com/b", "_blank", "noopener noreferrer"]]
    if seen["links"] != web:
        wrong.append("its links are %s" % seen["links"])
    if ["local", "C:/path/to/repo/Source/File.h:35"] not in seen["local"]:
        wrong.append("the path is not its words with its target on hover: %s" % seen["local"])
    if seen["events"]:
        wrong.append("%d element(s) carry an event attribute" % seen["events"])
    for words in ("[bad](javascript:alert(1))", "<img src=x onerror=alert(1)>", "<script>alert(1)</script>", "pic"):
        if words not in seen["text"]:
            wrong.append("%r is not kept as its words" % words)
    line = seen["line"]
    if line["tags"] != ["strong"] or line["text"] != "gist with a link and <b onclick=alert(1)>raw</b>":
        wrong.append("a summary's line is %s reading %r" % (line["tags"], line["text"]))
    print("the page's renderer drew the sample as %s; links %s; on hover %s; a summary's line as %s, reading %r"
          % (", ".join(seen["tags"]), seen["links"], seen["local"], line["tags"], line["text"]))
    for text in wrong:
        print("wrong: %s" % text)
    return 1 if wrong else 0


# The run's change as the page shows it: whether it comes before the terminals, whether its read was asked for —
# the button shown — its line, and the paths it lists.
CHANGE = ("(() => { const box = document.getElementById('change'); if (!box || box.hidden) return null;"
          " return { first: Boolean(box.compareDocumentPosition(document.getElementById('agents'))"
          " & Node.DOCUMENT_POSITION_FOLLOWING), button: !document.getElementById('diff-load').hidden,"
          " said: document.getElementById('change-said').innerText,"
          " paths: [...box.querySelectorAll('details.file')].map((f) => f.dataset.path) }; })()")


def change(page, run_id, path, words):
    """The run's change, live: 0 when it comes first on the run's page, lists `path` with nothing pressed to
    read it, and that file's diff, opened, shows `words`. Prints what it saw."""
    page.value(OPEN % json.dumps(run_id))
    wait(lambda: page.value(OPENED), 60, "the run")
    shown = wait(lambda: (lambda seen: seen if seen and path in seen["paths"] else None)(page.value(CHANGE)), 90,
                 "the run's change to list %s" % path)
    wait(lambda: page.value(OPEN_FILE % (json.dumps("#change"), json.dumps(path))), 30, "the file %s" % path)
    lines = wait(lambda: [line for line in page.value(FILE_LINES % (json.dumps("#change"), json.dumps(path)))
                          if words in line], 60, "the diff of %s to show %r" % (path, words))
    # The whole change copied by its own button, read by the press itself, while the run works.
    page.value(button("#change", "Copy all changes") + ".click(); true")
    copied = wait(lambda: next((text for text in page.value("window.__copied") or [] if path in text and words in text),
                               None), 60, "Copy all changes to copy the patch of %s" % path)
    print("the run's change in the Workbench, %s: %r, listing %s, nothing pressed to read it%s; %s opened: %r; Copy all "
          "changes copied a patch of %d characters naming it"
          % ("first on its page" if shown["first"] else "NOT before its terminals", " ".join(shown["said"].split()),
             shown["paths"], " — yet its button is shown" if shown["button"] else "", path, lines[0], len(copied)))
    return 0 if shown["first"] and not shown["button"] else 1


# Before the page loads: what it puts on the clipboard recorded in place of the clipboard, written whole or as an
# item whose text comes later.
CLIPBOARD_STAND_IN = """(() => {
  const copied = window.__copied = [];
  if (!navigator.clipboard) return;
  navigator.clipboard.writeText = (text) => { copied.push(text); return Promise.resolve(); };
  navigator.clipboard.write = async (items) => {
    for (const item of items) copied.push(await (await item.getType("text/plain")).text());
  };
})();"""


# Before the page loads: its socket for a run's change stood in for — the summaries a test sends it in place of the
# worker's — and its reads of a file's diff answered here, each counted by the file it names; nothing else changed.
FEED_STAND_IN = """(() => {
  const Real = window.WebSocket, realFetch = window.fetch;
  const feed = window.__feed = { socket: null, opened: 0, reads: {} };
  window.WebSocket = function (url, protocols) {
    if (!String(url).endsWith("/change")) return new Real(url, protocols);
    feed.opened += 1;
    feed.socket = { readyState: 1, close() { this.readyState = 3; }, send() {} };
    return feed.socket;
  };
  Object.assign(window.WebSocket, { CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3 });
  feed.say = (message) => feed.socket.onmessage({ data: JSON.stringify(message) });
  window.fetch = (path, options) => {
    const url = new URL(String(path), location.href);
    const file = url.pathname.endsWith("/diff") && url.searchParams.get("file");
    if (!file) return realFetch(path, options);
    feed.reads[file] = (feed.reads[file] || 0) + 1;
    return Promise.resolve(new Response(JSON.stringify({ base: "b", tree: "t", file: { path: file, status: "A" },
      patch: "@@ -0,0 +1 @@\\n+read " + feed.reads[file] + "\\n", whole: true }),
      { status: 200, headers: { "Content-Type": "application/json" } }));
  };
})();"""
# Each row of the run's change, and which are open; and how many times each file's diff was read.
ROWS = ("({ paths: [...document.querySelectorAll('#change details.file')].map((f) => f.dataset.path),"
        " open: [...document.querySelectorAll('#change details.file[open]')].map((f) => f.dataset.path),"
        " reads: window.__feed.reads })")


def summary(*files):
    """A summary as the worker sends one: each file `(path, added, stamp)`."""
    return {"base": "b", "files_total": len(files), "read": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "files": [{"path": path, "old": None, "status": "A", "added": added, "removed": 0, "binary": False,
                       "stamp": stamp} for path, added, stamp in files]}


def change_rows(page, run_id):
    """The run's change, live, as summaries come: 0 when a file opened stays open and is not read again while
    another file comes, and is read once more — it alone — when it changes. Prints what it saw."""
    page.value(OPEN % json.dumps(run_id))
    wait(lambda: page.value(OPENED), 60, "the run")
    wait(lambda: page.value("Boolean(window.__feed.socket && window.__feed.socket.onmessage)"), 60,
         "the page watching the run's change")

    def say(message, path):
        page.value("window.__feed.say(%s); true" % json.dumps(message))
        return wait(lambda: (lambda rows: rows if path in rows["paths"] else None)(page.value(ROWS)), 30,
                    "the change to list %s" % path)
    say(summary(("a.txt", 1, "1:1")), "a.txt")
    wait(lambda: page.value(OPEN_FILE % (json.dumps("#change"), json.dumps("a.txt"))), 30, "a.txt opened")
    wait(lambda: page.value(FILE_LINES % (json.dumps("#change"), json.dumps("a.txt"))), 30, "a.txt's diff")
    say(summary(("a.txt", 1, "1:1"), ("b.txt", 2, "1:2")), "b.txt")
    time.sleep(2)                                   # time for any read the new summary would start
    came = page.value(ROWS)
    say(summary(("a.txt", 2, "2:3"), ("b.txt", 2, "1:2")), "a.txt")
    wait(lambda: page.value(ROWS)["reads"].get("a.txt") == 2, 30, "a.txt read again once it changed")
    time.sleep(2)
    changed = page.value(ROWS)
    print("the run's change, live: with b.txt come, %s open and a.txt read %d time(s); with a.txt changed, %s open, "
          "reads %s" % (came["open"], came["reads"].get("a.txt", 0), changed["open"], changed["reads"]))
    return 0 if (came["open"] == ["a.txt"] and came["reads"] == {"a.txt": 1}
                 and changed["open"] == ["a.txt"] and changed["reads"] == {"a.txt": 2}) else 1


CHANGE_DISCLOSURE_STAND_IN = FEED_STAND_IN + """(() => {
  const real = window.fetch;
  window.fetch = async (path, options) => {
    const url = new URL(String(path), location.href);
    if (url.pathname.endsWith('/diff') && !url.search) {
      window.__feed.snapshots=(window.__feed.snapshots || 0)+1;
      const files=Array.from({length:181},(_,i)=>({path:'file-'+String(i).padStart(3,'0')+'.txt',status:'A',added:1,removed:0}));
      return new Response(JSON.stringify({base:'b'.repeat(40),tree:'t',against:'tip',files:files,files_total:files.length,
        patch:'@@ -0,0 +1 @@\\n+fixture\\n',total:25,next:25}),{status:200,headers:{'Content-Type':'application/json'}});
    }
    if (/^\\/api\\/runs\\/[^/]+$/.test(url.pathname)) {
      const response = await real(path, options), status = await response.json();
      status.stop = null;
      Object.assign(status.view, {state:'running', role:'engineer', stop:null, worktree:'/path/to/repo'});
      return new Response(JSON.stringify(status), {status:200,headers:{'Content-Type':'application/json'}});
    }
    return real(path, options);
  };
})();"""


def change_disclosure(page, run_id):
    """A large change stays compact until opened, through live updates and keyboard interaction."""
    page.value(OPEN % json.dumps(run_id))
    wait(lambda: page.value(OPENED), 30, "the run")
    wait(lambda: page.value("Boolean(window.__feed.socket && window.__feed.socket.onmessage)"), 30, "the change feed")
    files = [("file-%03d.txt" % i, 1, "1:1") for i in range(181)]
    page.value("window.__feed.say(%s); true" % json.dumps(summary(*files)))
    if not page.value("document.getElementById('change').tagName==='DETAILS' && !document.getElementById('change').open"):
        raise SystemExit("the large Change block is not collapsed by default")
    if not page.value("document.getElementById('change-count').textContent==='181 files changed' && "
                      "!document.getElementById('diff-files').checkVisibility() && "
                      "document.getElementById('change').getBoundingClientRect().height === "
                      "document.querySelector('#change > summary').getBoundingClientRect().height"):
        raise SystemExit("the collapsed change must show its count and hide its files: %r" % page.value(
            "({count:document.getElementById('change-count').textContent, "
            "outer:document.getElementById('change').getBoundingClientRect().height, "
            "summary:document.querySelector('#change > summary').getBoundingClientRect().height, "
            "files:document.getElementById('diff-files').getBoundingClientRect().height, "
            "visible:document.getElementById('diff-files').checkVisibility()})"))
    page.value("window.__changeSummary=document.querySelector('#change > summary'); window.__changeSummary.focus(); true")
    if not page.value("document.activeElement===window.__changeSummary"):
        raise SystemExit("change summary cannot take keyboard focus: %r" % page.value(
            "({active:document.activeElement.tagName,id:document.activeElement.id,hidden:document.getElementById('change').hidden})"))
    def key(name, code, number):
        page.call("Input.dispatchKeyEvent", type="keyDown", key=name, code=code, windowsVirtualKeyCode=number,
                  nativeVirtualKeyCode=number, text="\r" if name == "Enter" else name)
        page.call("Input.dispatchKeyEvent", type="keyUp", key=name, code=code, windowsVirtualKeyCode=number,
                  nativeVirtualKeyCode=number)
    key("Enter", "Enter", 13)
    wait(lambda: page.value("document.getElementById('change').open"), 5, "Enter to open the change")
    files.append(("file-181.txt", 1, "1:1"))
    page.value("window.__feed.say(%s); true" % json.dumps(summary(*files)))
    if not page.value("document.getElementById('change').open && document.activeElement===window.__changeSummary && "
                      "document.getElementById('change-count').textContent==='182 files changed'"):
        raise SystemExit("a live update lost the disclosure state or focus")
    key(" ", "Space", 32)
    wait(lambda: page.value("!document.getElementById('change').open"), 5, "Space to collapse the change")
    page.value("window.__feed.say(%s); true" % json.dumps(summary(*files)))
    time.sleep(3)
    if not page.value("!document.getElementById('change').open && document.activeElement===window.__changeSummary"):
        raise SystemExit("a status refresh reopened the change or lost focus")
    page.call("Runtime.evaluate", expression="import('/change.js').then(c=>{ c.watchChange(null); c.readOnceFor({id:'disclosure-first'}); })", awaitPromise=True)
    wait(lambda: page.value("document.getElementById('change-count').textContent==='181 files changed'"), 5, "a snapshot read")
    if page.value("document.getElementById('change').open"):
        raise SystemExit("a snapshot read reopened the collapsed change")
    key("Enter", "Enter", 13)
    page.value(button("#change", "Refresh") + ".click(); true")
    wait(lambda: page.value("window.__feed.snapshots===2"), 5, "Refresh to read the next snapshot")
    if not page.value("document.getElementById('change').open"):
        raise SystemExit("Refresh collapsed the open change")
    result = page.call("Runtime.evaluate", expression="""(async () => {
      const change=await import('/change.js'); change.showChangeFor(null);
      return !document.getElementById('change').open && document.getElementById('change-count').textContent==='Files and patch';
    })()""", awaitPromise=True, returnByValue=True)["result"].get("value")
    if not result: raise SystemExit("switching runs retained the prior change state")
    print("PASS: 181-file change collapsed by default; count visible; Enter/Space work; live/snapshot updates preserve state/focus; Refresh stays open; navigation resets it")
    return 0


def change_idle(page, run_id):
    """The run's page while it waits with no role at work: 0 when it opens no socket for the change and offers its
    button to read it. Prints what it saw."""
    page.value(OPEN % json.dumps(run_id))
    wait(lambda: page.value(OPENED), 60, "the run")
    time.sleep(6)                                   # two of the page's reads of the run
    page.value("const change=document.getElementById('change'); if(change.tagName==='DETAILS') change.open=true; true")
    opened = page.value("window.__feed.opened")
    button = page.value("(b => Boolean(b && !b.hidden && b.offsetParent))(document.getElementById('diff-load'))")
    print("the waiting run's page opened %d socket(s) for its change, %s its button to read it"
          % (opened, "and offers" if button else "and does NOT offer"))
    return 0 if opened == 0 and button else 1


# Before the page loads: what it sends a role's terminal — the agent's keys — recorded and dropped, so a check made
# on a live run reaches no agent; and what it copies recorded in place of the clipboard.
TERMINAL_STAND_IN = """(() => {
  const sent = window.__sent = [], copied = window.__copied = [];
  const send = WebSocket.prototype.send;
  WebSocket.prototype.send = function (data) {
    if (/\\/(engineer|architect)$/.test(new URL(this.url).pathname)) { sent.push(String(data)); return; }
    return send.call(this, data);
  };
  if (navigator.clipboard) navigator.clipboard.writeText = (text) => { copied.push(text); return Promise.resolve(); };
})();"""
# A role's terminal as laid out: its box, the text drawn and the viewport that scrolls it — and its scrollbar's
# width — where it is scrolled to, what is selected, its font, and whether its agent is live.
TERMINAL_LAYOUT = """(role => {
  const details = document.getElementById('terminal-' + role), box = document.getElementById('term-' + role);
  const view = box.querySelector('.xterm-viewport'), screen = box.querySelector('.xterm-screen');
  if (!view || !screen) return null;
  const d = details.getBoundingClientRect(), v = view.getBoundingClientRect(), s = screen.getBoundingClientRect();
  return { window: [innerWidth, innerHeight], details: [d.left, d.top, d.width, d.height].map(Math.round),
    clientWidth: box.clientWidth, scrollWidth: box.scrollWidth, clientHeight: box.clientHeight,
    scrollHeight: box.scrollHeight, screen: [s.left, s.right, s.top, s.bottom].map(Math.round),
    viewport: [v.left, v.right, v.top, v.bottom].map(Math.round), bar: view.offsetWidth - view.clientWidth,
    scrollTop: view.scrollTop, scrollMax: view.scrollHeight - view.clientHeight,
    selected: box.querySelectorAll('.xterm-selection div').length,
    font: parseFloat(getComputedStyle(box.querySelector('.xterm-rows')).fontSize),
    live: /live/.test(document.getElementById('state-' + role).textContent),
    mouse: box.querySelector('.xterm').classList.contains('enable-mouse-events'),
    room: box.clientWidth - parseFloat(getComputedStyle(box).paddingLeft) - parseFloat(getComputedStyle(box).paddingRight) - (view.offsetWidth - view.clientWidth) };
})(%s)"""


def fitted(seen, tall=False):
    """Whether the terminal's text, its scrollbar beside it, lies within its box across — and, maximized, its rows
    within the window's height; in its place the box grows with its rows."""
    across = seen["screen"][1] <= seen["viewport"][1] - seen["bar"] + 1 and seen["scrollWidth"] <= seen["clientWidth"] + 1
    return across and (not tall or seen["screen"][3] <= seen["details"][1] + seen["details"][3] + 1)


# A role's terminal's rows as drawn, and how much of its window its screen fills down.
TERMINAL_ROWS = """(role => {
  const rows = document.querySelector('#term-' + role + ' .xterm-rows');
  const screen = document.querySelector('#term-' + role + ' .xterm-screen');
  if (!rows || !screen) return null;
  const s = screen.getBoundingClientRect();
  return { rows: rows.children.length, top: Math.round(s.top), bottom: Math.round(s.bottom), window: innerHeight };
})(%s)"""

# A Workbench process from before row bounds, serving today's JavaScript from the shared checkout.
LEGACY_TERMINAL_CONFIG = """(() => {
  const get = document.getElementById.bind(document);
  document.getElementById = (id) => {
    const node = get(id);
    if (id === "config" && node) {
      const config = JSON.parse(node.textContent);
      delete config.terminal_size.min_rows;
      delete config.terminal_size.max_rows;
      node.textContent = JSON.stringify(config);
    }
    return node;
  };
})();"""

SETTINGS_POLICY_STAND_IN = """(() => {
  const real = window.fetch;
  window.__policyChanges = null;
  let shown;
  window.fetch = async (path, options = {}) => {
    if (String(path) !== "/api/settings") return real(path, options);
    if (options.method === "POST") {
      window.__policyChanges = JSON.parse(options.body).changes;
      return new Response(JSON.stringify(shown), { status: 200 });
    }
    shown = await (await real(path, options)).json();
    shown.writable = true;
    shown.settings.timeout_seconds = 3600;
    delete shown.settings.agents['deepseek-engineer'].provider;
    return new Response(JSON.stringify(shown), { status: 200 });
  };
})();"""


def settings_policy(page):
    """The Settings controls stage a duration and provider; their Apply is captured without writing settings."""
    page.value("location.hash = '#settings'; true")
    wait(lambda: page.value("Boolean(document.getElementById('settings-turn-hours'))"), 30, "Settings controls")
    page.value("""(() => {
      document.getElementById('settings-profile-disclosure').open = true;
      for (const [id, value] of [['settings-turn-hours', '48'], ['settings-provider-deepseek-engineer', 'deepseek']]) {
        const field = document.getElementById(id);
        field.value = value;
        field.dispatchEvent(new Event('change'));
      }
      document.getElementById('settings-apply').click();
      return true;
    })()""")
    sent = wait(lambda: page.value("window.__policyChanges"), 30, "Settings Apply")
    expected = {"/timeout_seconds": 172800, "/agents/deepseek-engineer/provider": "deepseek"}
    correct = len(sent) == len(expected) and {change["pointer"]: change.get("value") for change in sent} == expected
    print("Settings Apply captured, no settings written: %s" % sent)
    return 0 if correct else 1


def terminal_rows(page, run_id, role):
    """`role`'s terminal on the run's page, in a window taller than wide, as a portrait display's: 0 when Maximize has
    the agent's terminal take as many rows as fill the window — its worker's mark of the new size drawn — and Restore
    puts back its usual rows. Prints what it saw."""
    seen = lambda: page.value(TERMINAL_ROWS % json.dumps(role))   # noqa: E731
    page.value(OPEN % json.dumps(run_id))
    wait(lambda: page.value(OPENED), 60, "the run")
    page.value(OPEN_TERMINAL % json.dumps(role))
    rest = wait(lambda: (lambda now: now if now and now["rows"] else None)(seen()), 60, "the %s terminal" % role)
    time.sleep(2)
    page.value(button("#terminal-%s summary" % role, "Maximize") + ".click(); true")
    big = wait(lambda: (lambda now: now if now and now["rows"] > rest["rows"] else None)(seen()), 30,
               "the %s terminal to take more rows" % role)
    time.sleep(1)
    big = seen()
    failures = []
    if big["bottom"] < big["window"] - 60:
        failures.append("maximized, its %d rows end %d px above the window's foot" % (big["rows"],
                                                                                     big["window"] - big["bottom"]))
    page.value(button("#terminal-%s summary" % role, "Restore") + ".click(); true")
    back = wait(lambda: (lambda now: now if now and now["rows"] == rest["rows"] else None)(seen()), 30,
                "the %s terminal to take its usual rows again" % role)
    print("the %s terminal in a %d px tall window: %d rows in its place; maximized, %d rows, its screen down to %d px "
          "of %d; restored, %d rows%s" % (role, rest["window"], rest["rows"], big["rows"], big["bottom"],
                                          big["window"], back["rows"],
                                          "" if not failures else "\nFAILED: " + "\nFAILED: ".join(failures)))
    return 0 if not failures else 1


def terminal_fit(page, run_id, role):
    """`role`'s terminal on the run's page, in a window as narrow as an operator's: 0 when its text and scrollbar
    fit its box; a drag of the thumb up its track scrolls it back, selecting nothing; Maximize fills the window,
    drawn larger and still fitting, and Restore puts it back; Ctrl+C on a selection copies it and sends the agent
    nothing — and, its agent live, Ctrl+C with nothing selected is the agent's still. Prints what it saw."""
    layout = lambda: page.value(TERMINAL_LAYOUT % json.dumps(role))   # noqa: E731
    page.value(OPEN % json.dumps(run_id))
    wait(lambda: page.value(OPENED), 60, "the run")
    page.value(OPEN_TERMINAL % json.dumps(role))
    wait(lambda: (layout() or {}).get("scrollMax", 0) > 0, 90, "the %s terminal to hold more than a screen" % role)
    time.sleep(2)
    page.value("document.getElementById('term-%s').scrollIntoView({ block: 'start' }); true" % role)
    time.sleep(1)
    rest = layout()
    failures = [] if fitted(rest) else ["its text and scrollbar do not fit its box: %s" % rest]
    # The thumb, at the foot of its track with the terminal at its end, dragged halfway up, as a hand drags it.
    page.value("(v => { v.scrollTop = v.scrollHeight; })(document.querySelector('#term-%s .xterm-viewport'))" % role)
    time.sleep(1)
    rest = layout()
    x, top, bottom = rest["viewport"][1] - max(rest["bar"], 2) / 2, rest["viewport"][2], rest["viewport"][3]
    grab, to = bottom - rest["bar"] - 4, (top + bottom) // 2
    page.call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=grab)
    page.call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=grab, button="left", buttons=1, clickCount=1)
    for step in range(1, 11):
        page.call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=grab + (to - grab) * step / 10,
                  button="left", buttons=1)
        time.sleep(0.05)
    page.call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=to, button="left", clickCount=1)
    time.sleep(1)
    dragged = layout()
    if not dragged["scrollTop"] < rest["scrollMax"] * 0.8 or dragged["selected"]:
        failures.append("a drag of its thumb scrolled it from %d of %d to %d, %d piece(s) of text selected"
                        % (rest["scrollTop"], rest["scrollMax"], dragged["scrollTop"], dragged["selected"]))
    # Maximize, then Restore.
    page.value(button("#terminal-%s summary" % role, "Maximize") + ".click(); true")
    time.sleep(2)
    big = layout()
    if not (fitted(big, tall=True) and big["details"][2] >= big["window"][0] - 40 and big["details"][3] >= big["window"][1] - 40
            and big["font"] > rest["font"]):
        failures.append("maximized, it is %s at font %s (in its place, %s): %s"
                        % (big["details"][2:], big["font"], rest["font"], big))
    page.value(button("#terminal-%s summary" % role, "Restore") + ".click(); true")
    time.sleep(2)
    back = layout()
    if not (fitted(back) and abs(back["details"][2] - rest["details"][2]) <= 2
            and abs(back["font"] - rest["font"]) <= 0.2):
        failures.append("restored, it is %s at font %s, not %s at %s: %s"
                        % (back["details"][2:], back["font"], rest["details"][2:], rest["font"], back))
    # Text selected down its screen — with Shift where the agent takes the mouse, which then selects all the same;
    # elsewhere Shift would extend a selection rather than start one — then Ctrl+C.
    page.value("document.getElementById('term-%s').scrollIntoView({ block: 'start' }); true" % role)
    time.sleep(1)
    back = layout()
    left, top, right, bottom = back["screen"][0] + 4, back["screen"][2] + 20, back["screen"][1] - 20, back["screen"][3] - 20
    for kind, x, y in (("mousePressed", left, top), ("mouseMoved", (left + right) / 2, (top + bottom) / 2),
                       ("mouseReleased", right, bottom)):
        page.call("Input.dispatchMouseEvent", type=kind, x=x, y=y, button="left", buttons=1 if kind != "mouseReleased"
                  else 0, clickCount=1, modifiers=8 if back["mouse"] else 0)
    time.sleep(0.5)
    # Ctrl+C as the page receives it, at the terminal's own input: headless Edge's browser process breaks on a
    # real one now and then, in its own clipboard component — measured from its crash dump, a check that fails
    # before the page is told of the key — so the key goes to the page alone; the selection above is the mouse's.
    # xterm reads a control key's character from its legacy `keyCode`, which a key built here leaves at 0 unless set.
    ctrl_c = ("(t => { t.focus(); t.dispatchEvent(new KeyboardEvent('keydown', { key: 'c', code: 'KeyC', "
              "keyCode: 67, which: 67, ctrlKey: true, bubbles: true, cancelable: true })); return true; })"
              "(document.querySelector('#term-%s .xterm-helper-textarea'))" % role)
    page.value(ctrl_c)
    time.sleep(0.5)
    copied, sent = page.value("window.__copied"), page.value("window.__sent")
    if not (copied and copied[-1].strip()) or "\x03" in sent:
        failures.append("Ctrl+C on a selection copied %r and sent the agent %r" % (copied, sent))
    if back["live"]:
        page.value(ctrl_c)
        time.sleep(0.5)
        if "\x03" not in page.value("window.__sent"):
            failures.append("Ctrl+C with nothing selected did not reach its live agent")
    print("the %s terminal in a %dx%d window: its box %d px, its text %d px and scrollbar %d px within it at font %s; "
          "its thumb dragged from %d to %d of %d; maximized %s at font %s, restored at %s; Ctrl+C on a selection "
          "copied %r, sent the agent %r%s"
          % (role, rest["window"][0], rest["window"][1], rest["clientWidth"], rest["screen"][1] - rest["screen"][0],
             rest["bar"], rest["font"], rest["scrollTop"], dragged["scrollTop"], rest["scrollMax"], big["details"][2:],
             big["font"], back["font"], (copied or [""])[-1][:40], sent,
             "" if not failures else "\nFAILED: " + "\nFAILED: ".join(failures)))
    return 0 if not failures else 1


# Before the page loads: the run's status stood in for — a blocker taking guidance to either role, and what an agent
# last answered the operator — and the page's answers to it caught: each recorded as sent, none reaching the
# Workbench, and the next stop shown after it, so the card is drawn anew.
HANDOFF_STAND_IN = """(() => {
  const real = window.fetch;
  const hand = window.__handoff = { stop: 1, answers: [], reply: { role: "architect", text: "Yes, proceed." } };
  const reply = (body) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  window.fetch = async (path, options) => {
    const at = new URL(String(path), location.href).pathname;
    if (/^\\/api\\/runs\\/[^/]+\\/answer$/.test(at)) {
      const body = JSON.parse(options.body);
      hand.answers.push(body);
      hand.stop += 1;
      return reply({ stop: body.stop, action: body.action });
    }
    const response = await real(path, options);
    if (!/^\\/api\\/runs\\/[^/]+$/.test(at)) return response;
    const status = await response.json();
    const id = "stand-in:" + hand.stop;
    status.unreadable = null;
    status.stop = { id: id, reason: "blocker", phase: "plan", feedback: "The plan bans the engine's own names.",
      hint: "guide with your decision to continue", actions: ["guide", "guide:architect"], since: new Date().toISOString() };
    status.view = Object.assign(status.view, { state: "waiting", stop: { id: id, reason: "blocker", to: "engineer" },
      reply: hand.reply });
    return reply(status);
  };
})();"""
HANDOFF_CARD = """(() => {
  const buttons = (id) => [...document.querySelectorAll('#' + id + ' button')].map((b) => ({ label: b.textContent,
    primary: b.classList.contains('primary'), enabled: !b.disabled }));
  return { stop: window.__handoff.stop, label: document.getElementById('stop-reply-label').textContent,
    reply: buttons('stop-reply-actions'), guide: buttons('stop-actions'), answers: window.__handoff.answers }; })()"""


def handoff(page, run_id):
    """A blocker's guidance and an agent's answer handed on, its run's status and answers stood in for: 0 when the
    card names the agent that answered and offers the other first — drawn anew when the other answers the same
    words — and each of its four presses sends exactly its action with exactly its words. Prints what it saw."""
    card = lambda: page.value(HANDOFF_CARD)   # noqa: E731
    page.value(OPEN % json.dumps(run_id))
    wait(lambda: page.value(OPENED), 60, "the run")
    wait(lambda: card()["reply"], 30, "the agent's answer offered on the stop")
    failures = []
    first = card()
    if not (first["label"].startswith("The architect's") and [b["label"] for b in first["reply"]] ==
            ["Send to the engineer", "Send to the architect"] and first["reply"][0]["primary"]):
        failures.append("the architect's answer offered as %s" % first)
    # The same words, now the engineer's: the card is drawn anew for who said them.
    page.value("window.__handoff.reply = { role: 'engineer', text: 'Yes, proceed.' }; true")
    switched = wait(lambda: (lambda seen: seen if seen["label"].startswith("The engineer's") else None)(card()), 30,
                    "the card to name the engineer, who said the same words")
    if [b["label"] for b in switched["reply"]][:1] != ["Send to the architect"] or not switched["reply"][0]["primary"]:
        failures.append("the engineer's answer offered as %s" % switched)
    presses = [("stop-reply-actions", "Send to the architect", None, {"action": "guide:architect", "text": "Yes, proceed."}),
               ("stop-reply-actions", "Send to the engineer", None, {"action": "guide", "text": "Yes, proceed."}),
               ("stop-actions", "Guide the engineer", "Revise the plan.", {"action": "guide", "text": "Revise the plan."}),
               ("stop-actions", "Guide the architect", "Judge it again.", {"action": "guide:architect",
                                                                            "text": "Judge it again."})]
    for number, (where, label, note, wanted) in enumerate(presses, 1):
        wait(lambda: card()["stop"] == number and any(b["label"] == label and b["enabled"]
                                                       for b in card()["reply" if where == "stop-reply-actions"
                                                                       else "guide"]), 30, "%s, enabled" % label)
        if note is not None:
            page.value("(n => { n.value = %s; n.dispatchEvent(new Event('input')); })(document.getElementById('stop-note'))"
                       % json.dumps(note))
        page.value(button("#" + where, label) + ".click(); true")
        sent = wait(lambda: (lambda answers: answers[number - 1] if len(answers) >= number else None)(
            page.value("window.__handoff.answers")), 30, "what %s sent" % label)
        if sent != dict(wanted, stop="stand-in:%d" % number):
            failures.append("%s sent %s" % (label, sent))
    print("a blocker's card, its run's status stood in for: the architect's answer offered %s; the same words, the "
          "engineer's, offered %s; sent %s%s"
          % ([b["label"] for b in first["reply"]], [b["label"] for b in switched["reply"]],
             page.value("window.__handoff.answers"), "" if not failures else "\nFAILED: " + "\nFAILED: ".join(failures)))
    return 0 if not failures else 1


# An approval stood in for, and the answers to it caught: the first stop says it takes a note, the next — as a worker
# from before notes publishes it — does not.
APPROVAL_STAND_IN = """(() => {
  const real = window.fetch;
  const hand = window.__approval = { stop: 1, answers: [] };
  const reply = (body) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  window.fetch = async (path, options) => {
    const at = new URL(String(path), location.href).pathname;
    if (/^\\/api\\/runs\\/[^/]+\\/answer$/.test(at)) {
      const body = JSON.parse(options.body);
      hand.answers.push(body);
      hand.stop += 1;
      return reply({ stop: body.stop, action: body.action });
    }
    const response = await real(path, options);
    if (!/^\\/api\\/runs\\/[^/]+$/.test(at)) return response;
    const status = await response.json();
    const id = "stand-in:" + hand.stop;
    status.unreadable = null;
    status.stop = Object.assign({ id: id, reason: "approval", phase: "plan", feedback: "PASS: the plan holds.",
      hint: "approve to start implementation, or revise with feedback for a new plan", actions: ["approve", "revise"],
      since: new Date().toISOString() }, hand.stop === 1 ? { noted: true } : {});
    status.view = Object.assign(status.view, { state: "waiting", stop: { id: id, reason: "approval", to: "engineer" },
      reply: null });
    return reply(status);
  };
})();"""
APPROVAL_CARD = """(() => {
  const approve = [...document.querySelectorAll('#stop-actions button')].find((b) => b.textContent.startsWith('Approve'));
  return { stop: window.__approval.stop, shown: document.getElementById('stop-title').textContent.length > 0,
    label: document.getElementById('stop-note-label').textContent, approve: approve ? approve.textContent : null,
    alert: document.getElementById('stop-note-alert').textContent, answers: window.__approval.answers }; })()"""
NOTE_TYPED = ("(n => { n.value = %s; n.dispatchEvent(new Event('input')); return true; })"
              "(document.getElementById('stop-note'))")


def approval_notes(page, run_id):
    """A note at an approval, its run's status and answers stood in for: 0 when a stop that says it takes a note has
    Approve say so and send it, and one that does not — as a worker from before notes publishes it — keeps Approve,
    sends nothing while a note is written, saying why, and sends Approve alone once it is cleared. Prints what it
    saw."""
    card = lambda: page.value(APPROVAL_CARD)   # noqa: E731
    page.value(OPEN % json.dumps(run_id))
    wait(lambda: page.value(OPENED), 60, "the run")
    wait(lambda: card()["approve"], 30, "the approval's Approve")
    failures = []
    note = "Keep greeting.txt to one line."
    page.value(NOTE_TYPED % json.dumps(note))
    noted = wait(lambda: (lambda seen: seen if seen["approve"] == "Approve with note" else None)(card()), 10,
                 "Approve to say the note goes with it")
    page.value(button("#stop-actions", "Approve with note") + ".click(); true")
    first = wait(lambda: (lambda answers: answers[0] if answers else None)(card()["answers"]), 30,
                 "what Approve with note sent")
    if first != {"stop": "stand-in:1", "action": "approve", "text": note}:
        failures.append("Approve with note sent %s" % first)
    legacy = wait(lambda: (lambda seen: seen if seen["approve"] and "Revise" in seen["label"]
                           and "Approve" not in seen["label"] else None)(card()), 30,
                  "the next stop, which says nothing of a note, drawn")
    page.value(NOTE_TYPED % json.dumps(note))
    time.sleep(0.5)
    if card()["approve"] != "Approve":
        failures.append("at a stop that takes no note, Approve read %r" % card()["approve"])
    page.value(button("#stop-actions", "Approve") + ".click(); true")
    said = wait(lambda: card()["alert"], 10, "the page to say why the note is not sent")
    time.sleep(1)
    if len(card()["answers"]) != 1:
        failures.append("a note at a stop that takes none was sent: %s" % card()["answers"][1:])
    page.value(NOTE_TYPED % json.dumps(""))
    page.value(button("#stop-actions", "Approve") + ".click(); true")
    second = wait(lambda: (lambda answers: answers[1] if len(answers) > 1 else None)(card()["answers"]), 30,
                  "what Approve sent once the note was cleared")
    if second != {"stop": "stand-in:2", "action": "approve"}:
        failures.append("Approve, the note cleared, sent %s" % second)
    print("an approval's note, its run's status stood in for: where the stop takes one, the label %r and %r sent %s; "
          "where it does not, the label %r, the note refused — %r — and Approve alone sent %s%s"
          % (noted["label"], noted["approve"], first, legacy["label"], said, second,
             "" if not failures else "\nFAILED: " + "\nFAILED: ".join(failures)))
    return 0 if not failures else 1


# Every button shown outside a dialog — a dialog's own say what it asks — that says nothing on hover; and how many
# there are in all.
UNHINTED = ("(() => { const shown = [...document.querySelectorAll('button, a.button')].filter((b) => b.offsetParent"
            " !== null && !b.closest('dialog')); return { shown: shown.length, bare: shown.filter((b) =>"
            " !b.title.trim()).map((b) => b.textContent.trim().replace(/\\s+/g, ' ')) }; })()")


def hints(page, run_id):
    """New run, Settings, the stack's panel and — unless `run_id` is `page` — that run's page: 0 when every button
    shown outside a dialog says on hover what it does. Prints what it saw."""
    views = ["#new", "#settings"] + ([] if run_id == "page" else ["#run=" + urllib.parse.quote(run_id)])
    shown, bare = 0, []
    for view in views:
        page.value("location.hash = %s; true" % json.dumps(view))
        time.sleep(4)                               # the view's reads
        if view == "#new":
            page.value("document.getElementById('stack-button').click(); true")
            time.sleep(1)
        seen = page.value(UNHINTED)
        shown += seen["shown"]
        bare += ["%s %r" % (view, label) for label in seen["bare"]]
        if view == "#new":
            page.value("document.getElementById('stack-button').click(); true")
    print("%d buttons shown across %s: %s" % (shown, ", ".join(views), "each says what it does on hover" if not bare
                                              else "these say nothing: " + "; ".join(bare)))
    return 0 if shown and not bare else 1


def accounting(page, run_id):
    """Read a priced run, exercise the amount formatter and keep disclosure focus through a refresh."""
    page.value(OPEN % json.dumps(run_id))
    wait(lambda: page.value("document.querySelector('#accounting-summary').textContent.includes('$')"),
         30, "a recorded cost")
    result = page.call("Runtime.evaluate", expression="""(async () => {
      const {money} = await import('/accounting.js');
      const zero = money({usd:0,provenance:'provider_reported'});
      return {zero:zero === new Intl.NumberFormat(undefined,{style:'currency',currency:'USD',
        minimumFractionDigits:2,maximumFractionDigits:6}).format(0),
        tiny:money({usd:1e-9}).includes('<'), unknown:money({usd:null}) === 'Cost unavailable',
        partial:money({usd:.01,provenance:'estimated',partial:true}).includes('partial'),
        equivalent:money({usd:.01,provenance:'estimated',api_equivalent:true}).includes('API-equivalent')};
    })()""", awaitPromise=True, returnByValue=True)["result"].get("value")
    if not result or not all(result.values()):
        raise SystemExit("accounting amount contract failed: %r" % result)
    page.value("document.getElementById('accounting-details').open=true; "
               "window.__accountingSummary=document.querySelector('#accounting-details > summary'); "
               "window.__accountingSummary.focus(); window.__accountingReads=0; "
               "window.__accountingFetch=window.fetch; window.fetch=(...args)=>{ "
               "if(String(args[0]).endsWith('/accounting')) window.__accountingReads++; "
               "return window.__accountingFetch(...args); }; true")
    wait(lambda: page.value("window.__accountingReads > 0"), 20, "the next independent cost read")
    if not page.value("document.getElementById('accounting-details').open && "
                      "document.activeElement===window.__accountingSummary && document.title.includes('$')"):
        raise SystemExit("cost refresh lost disclosure focus or the tab amount")
    page.value("window.__accountingAmount=document.querySelector('#accounting-summary > div:last-child strong').textContent; "
               "window.fetch=(...args)=>String(args[0]).endsWith('/accounting') "
               "? Promise.reject(new TypeError('accounting acceptance outage')) : window.__accountingFetch(...args); true")
    wait(lambda: page.value("document.title.includes('stale')"), 20, "a visibly stale cost after read failure")
    if not page.value("document.querySelector('#accounting-summary > div:last-child strong').textContent === "
                      "window.__accountingAmount && [...document.querySelectorAll('#run-controls button')]"
                      ".some(b=>!b.disabled && b.textContent.includes('Stop'))"):
        raise SystemExit("cost outage lost the prior amount or disabled run controls")
    page.value("window.fetch=window.__accountingFetch; true")
    wait(lambda: page.value("!document.title.includes('stale')"), 20, "cost read recovery")
    layouts = []
    for width, zoom in ((1400, 1), (640, 1), (320, 1), (1400, 2)):
        page.call("Emulation.setDeviceMetricsOverride", width=width, height=1000, deviceScaleFactor=1, mobile=False)
        page.value("document.body.style.zoom=%s" % zoom)
        found = page.value("({page:document.documentElement.scrollWidth, width:innerWidth, "
                           "rows:document.querySelectorAll('#accounting-attempts tr').length})")
        if found["page"] > found["width"] + 1 or not found["rows"]:
            raise SystemExit("accounting overflow or missing iterations: %r" % found)
        layouts.append([width, zoom])
    page.value("document.body.style.zoom=1; document.getElementById('run-accounting').scrollIntoView(); true")
    rectangle = page.value("(() => { const r=document.getElementById('run-accounting').getBoundingClientRect(); "
                           "return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,scale:1}; })()")
    import base64
    captured = page.call("Page.captureScreenshot", format="png", clip=rectangle, captureBeyondViewport=True)
    with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "tmp", "accounting-desktop.png"), "wb") as fh:
        fh.write(base64.b64decode(captured["data"]))
    print(json.dumps({"accounting": "PASS", "formatter": result, "outage_recovery": True, "layouts": layouts,
                      "summary": page.value("document.getElementById('accounting-summary').innerText"),
                      "roles": page.value("document.getElementById('accounting-roles').innerText")}))
    return 0


def main(url, run_id, label, said, note=None):
    profile = tempfile.mkdtemp(prefix="orchestra-demo-edge-")
    # A layout is read at the window size it names; every press at the browser's own.
    size = label.split(":", 1)[1] if label.startswith("layout:") else None
    # A terminal is fitted in a window as narrow as an operator's, where 160 columns at the page's font do not fit.
    size = "1032x1100" if label.startswith("terminal-fit:") else size
    # A terminal's rows follow a window taller than wide, as a portrait display's.
    size = "1000x1700" if label.startswith(("terminal-rows:", "terminal-rows-legacy:")) else size
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
            if label == "settings-policy":
                page.call("Page.enable")
                page.call("Page.addScriptToEvaluateOnNewDocument", source=SETTINGS_POLICY_STAND_IN)
            if label.startswith("terminal-rows-legacy:"):
                page.call("Page.enable")
                page.call("Page.addScriptToEvaluateOnNewDocument", source=LEGACY_TERMINAL_CONFIG)
            if label in ("change-rows", "change-idle"):
                # A script for documents to come is applied only once the Page domain is enabled (measured).
                page.call("Page.enable")
                page.call("Page.addScriptToEvaluateOnNewDocument", source=FEED_STAND_IN)
            if label == "change-disclosure":
                page.call("Page.enable")
                page.call("Page.addScriptToEvaluateOnNewDocument", source=CHANGE_DISCLOSURE_STAND_IN)
            if label.startswith("terminal-fit:"):
                page.call("Page.enable")
                page.call("Page.addScriptToEvaluateOnNewDocument", source=TERMINAL_STAND_IN)
            if label == "handoff":
                page.call("Page.enable")
                page.call("Page.addScriptToEvaluateOnNewDocument", source=HANDOFF_STAND_IN)
            if label == "approval-notes":
                page.call("Page.enable")
                page.call("Page.addScriptToEvaluateOnNewDocument", source=APPROVAL_STAND_IN)
            if label.startswith("change:"):
                page.call("Page.enable")
                page.call("Page.addScriptToEvaluateOnNewDocument", source=CLIPBOARD_STAND_IN)
            page.call("Page.navigate", url=url)
            if label == "settings-policy":
                wait(lambda: page.value("document.readyState === 'complete'"), 30, "the Workbench page")
                return settings_policy(page)
            if label == "hints":
                # Its views read no run, so neither does it wait for the list of runs.
                wait(lambda: page.value("document.readyState === 'complete'"), 30, "the Workbench page")
                return hints(page, run_id)
            wait(lambda: page.value("document.readyState === 'complete' && "
                                    "document.querySelector('#runs-finished li') !== null"), 30, "the Workbench page")
            if label.startswith("layout:"):
                return laid_out(page, run_id, size, said)
            if label == "accounting":
                return accounting(page, run_id)
            if run_id == "start" and label.startswith("refused:"):
                repo, task = label.split(":", 2)[1:]
                return refused(page, repo, task, said)
            if run_id == "start" and label.startswith("answered:"):
                return answered(page, label.split(":", 1)[1], said)
            if label == "markdown-safety":
                return markdown_safety(page)
            if label == "markdown":
                return markdown(page, run_id, said)
            if label.startswith("change:"):
                return change(page, run_id, said, label.split(":", 1)[1])
            if label == "change-rows":
                return change_rows(page, run_id)
            if label == "change-disclosure":
                return change_disclosure(page, run_id)
            if label == "change-idle":
                return change_idle(page, run_id)
            if label.startswith("terminal-fit:"):
                return terminal_fit(page, run_id, label.split(":", 1)[1])
            if label.startswith(("terminal-rows:", "terminal-rows-legacy:")):
                return terminal_rows(page, run_id, label.split(":", 1)[1])
            if label == "handoff":
                return handoff(page, run_id)
            if label == "approval-notes":
                return approval_notes(page, run_id)
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
            # Typed once its stop is drawn — drawing a new stop clears the note — and as typing is, heard by the page,
            # whose buttons may say then that the note goes with them.
            if note and not typed:
                wait(lambda: page.value("document.getElementById('stop-actions').children.length > 0"), 60,
                     "the run's stop")
                page.value("(n => { n.value = %s; n.dispatchEvent(new Event('input')); return true; })"
                           "(document.getElementById('stop-note'))" % json.dumps(note))
            wait(lambda: page.value(pressed + " !== undefined"), 60, "the %r button" % label)
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
    # What the page said reaches a Windows console whose code page lacks many of its characters — a minus sign,
    # a dash: written escaped, never crashing the press it reports.
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.exit(main(*sys.argv[1:]))
