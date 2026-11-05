"""Press one of the Workbench's own buttons in a headless browser, as the operator would.

    python tools/demo_press.py <workbench url> <run id | stack | start | page> <button label | task | refused:repo:task | answered:status | markdown | markdown-safety | change:words | change-rows | change-idle | hints | terminal:role | turn:stage | turn-then:stage:label | file:path | round:stage:path | history | hold:role:label | type-after:role:label:line | layout:WIDTHxHEIGHT | absent:label,...> <what the page should say> [note]

The Windows side of `make demo` (WSL cannot reach Windows' loopback, and Windows reaches the
Workbench's): headless Edge, driven over the DevTools protocol, opens the page, opens the run by its
link, presses the run's button with that label — an answer to its stop, Stop run, Force terminate, or the
start of the worker it is blocked by — or, given `stack` for the run, the one in the stack's popover,
opened from its chips; the page's own confirmation answered yes, and each question it asked printed;
given a note, it types it into the stop's own note first, as an answer's words are. Given `start`, it
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
nothing pressed to read it, lists that file, and its diff shows the words. Given `change-rows`, the page's
socket for the run's change and its reads of a file's diff are stood in for before the page loads, and three
summaries are sent: it exits 0 when a file opened stays open and is not read again while another file comes,
and is read once more, and only it, when it changes. Given `change-idle`, the same stand-in watches the run's
page: it exits 0 when the page, its run waiting with no role at work, opens no socket for the change. Given
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
shown on screen.
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
    print("the run's change in the Workbench, %s: %r, listing %s, nothing pressed to read it%s; %s opened: %r"
          % ("first on its page" if shown["first"] else "NOT before its terminals", " ".join(shown["said"].split()),
             shown["paths"], " — yet its button is shown" if shown["button"] else "", path, lines[0]))
    return 0 if shown["first"] and not shown["button"] else 1


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


def change_idle(page, run_id):
    """The run's page while it waits with no role at work: 0 when it opens no socket for the change and offers its
    button to read it. Prints what it saw."""
    page.value(OPEN % json.dumps(run_id))
    wait(lambda: page.value(OPENED), 60, "the run")
    time.sleep(6)                                   # two of the page's reads of the run
    opened = page.value("window.__feed.opened")
    button = page.value("(b => Boolean(b && !b.hidden && b.offsetParent))(document.getElementById('diff-load'))")
    print("the waiting run's page opened %d socket(s) for its change, %s its button to read it"
          % (opened, "and offers" if button else "and does NOT offer"))
    return 0 if opened == 0 and button else 1


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
            if label in ("change-rows", "change-idle"):
                page.call("Page.addScriptToEvaluateOnNewDocument", source=FEED_STAND_IN)
            page.call("Page.navigate", url=url)
            if label == "hints":
                # Its views read no run, so neither does it wait for the list of runs.
                wait(lambda: page.value("document.readyState === 'complete'"), 30, "the Workbench page")
                return hints(page, run_id)
            wait(lambda: page.value("document.readyState === 'complete' && "
                                    "document.querySelector('#runs-finished li') !== null"), 30, "the Workbench page")
            if size:
                return laid_out(page, run_id, size, said)
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
            if label == "change-idle":
                return change_idle(page, run_id)
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
    # What the page said reaches a Windows console whose code page lacks many of its characters — a minus sign,
    # a dash: written escaped, never crashing the press it reports.
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.exit(main(*sys.argv[1:]))
