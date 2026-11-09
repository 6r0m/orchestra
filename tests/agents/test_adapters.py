"""The kinds of agent: found among the adapters' modules rather than listed, and each checked against the
one contract when it is loaded.

A kind planted for a test (`stand_in.py`) is found beside the shipped ones, and refused only for what it
lacks; its terminal turns are `test_terminal.py`'s.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

# The suite's own folder, reached from this concern's folder inside it, and the
# checkout above both: the shared harness and the fixtures live at the suite root.
HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path[:0] = [PKG, HERE]

from app.agents import adapters  # noqa: E402
import stand_in  # noqa: E402

SHIPPED = ("claude-code", "codex")

# What `available()` answers in a process of its own, with the folder of planted kinds on its search path.
LIST = """
import json, sys
sys.path.insert(0, sys.argv[1])
from app.agents import adapters
adapters.__path__.append(sys.argv[2])
print(json.dumps(adapters.available()))
"""


class Loading(unittest.TestCase):
    """A kind is loaded by its name alone, and refused, saying why, when it is not one."""

    def test_an_unknown_kind_is_refused_by_its_name(self):
        with self.assertRaisesRegex(adapters.Refused, "no kind 'deepseek'"):
            adapters.load("deepseek")

    def test_a_name_outside_the_grammar_is_refused_before_anything_is_imported(self):
        for name in ("Claude-Code", "claude_code", "-codex", "codex-", "claude--code", "../codex", "", None):
            with self.subTest(name=name), self.assertRaisesRegex(adapters.Refused, "not a kind's name"):
                adapters.load(name)

    def test_a_module_lacking_part_of_the_contract_is_refused_saying_what(self):
        stand_in.plant(self, {"partial": stand_in.variant(ACCESS=None, completion=None),
                              "odd": stand_in.variant(ACCESS='ACCESS = ("admin",)'),
                              "flat": stand_in.variant(wire="wire = None"),
                              "unsaid": stand_in.variant(BOUNDARY=None),
                              "halfsaid": stand_in.variant(BOUNDARY='BOUNDARY = {"read": "Held.", "write": ""}')})
        for kind, lacks in (("partial", ("ACCESS", "completion")), ("odd", ("ACCESS", "admin")),
                            ("flat", ("wire",)), ("unsaid", ("BOUNDARY",)), ("halfsaid", ("BOUNDARY", "write"))):
            with self.subTest(kind=kind), self.assertRaises(adapters.Refused) as raised:
                adapters.load(kind)
            for part in lacks:
                self.assertIn(part, str(raised.exception))

    def test_every_shipped_kind_keeps_the_contract(self):
        for kind in SHIPPED:
            with self.subTest(kind=kind):
                module = adapters.load(kind)
                self.assertEqual(adapters.kind_name(module), kind)
                self.assertTrue(set(module.ACCESS) <= set(adapters.ACCESSES))
                self.assertTrue(all(module.BOUNDARY[access].strip() for access in module.ACCESS),
                                "what holds it to each access it can run with")


class Finding(unittest.TestCase):
    """Nothing lists the kinds: a module on the adapters' search path is one, and one that fails the
    contract is answered refused beside the rest rather than hiding them."""

    def test_a_planted_kind_is_found_beside_the_shipped_ones(self):
        stand_in.plant(self, {stand_in.MODULE: stand_in.SOURCE, "_helper": "x = 1\n",
                              "broken": stand_in.variant(wire=None), "BadName": stand_in.SOURCE})
        found = {entry["kind"]: entry for entry in adapters.available()}
        self.assertIsNone(found[stand_in.KIND]["refused"])
        self.assertEqual({key: found[stand_in.KIND][key] for key in ("name", "access", "options", "skill",
                                                                     "boundary")},
                         {"name": "Stand-in", "access": ["read", "write"], "options": ["model"],
                          "skill": "@{name}",
                          "boundary": {"read": "Held by the stand-in's word.", "write": "Held by nothing."}})
        self.assertEqual([kind for kind in SHIPPED if found[kind]["refused"]], [])
        self.assertIn("wire", found["broken"]["refused"])
        self.assertIn("not named for a kind", found["BadName"]["refused"])
        self.assertFalse({"_helper", "-helper", "_files", "-files", "__init__"} & set(found),
                         "a module of the package's own is not a kind")
        # The control: a list of the kinds written down would not know the planted one.
        self.assertNotIn(stand_in.KIND, SHIPPED)

    def test_listing_the_kinds_asks_nothing_of_the_host(self):
        """A kind's module only defines it on import: with no program on the PATH and an empty home, every
        kind is still found. Control: a planted module that looks for its program when imported is refused
        there."""
        folder = stand_in.plant(self, {
            stand_in.MODULE: stand_in.SOURCE,
            "probing": "import shutil\nassert shutil.which('stand-in-agent'), 'no program'\n"
                       + stand_in.SOURCE})
        home = tempfile.mkdtemp(prefix="orchestra-empty-home-")
        self.addCleanup(__import__("shutil").rmtree, home, True)
        bare = {"PATH": "", "HOME": home, "USERPROFILE": home}
        if "SYSTEMROOT" in os.environ:
            bare["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
        done = subprocess.run([sys.executable, "-c", LIST, PKG, folder], env=bare, capture_output=True,
                              text=True, encoding="utf-8", timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        found = {entry["kind"]: entry["refused"] for entry in json.loads(done.stdout)}
        self.assertEqual({kind: found[kind] for kind in SHIPPED + (stand_in.KIND,)},
                         dict.fromkeys(SHIPPED + (stand_in.KIND,)))
        self.assertIn("no program", found["probing"])


class CodexHooks(unittest.TestCase):
    """Codex's turn ends on its own hooks, their event on stdin — never `notify`, whose event carries every input
    of the thread on the hook's command line and outgrew Windows' (os error 206: the turn never ended) — with one
    definition on every turn, since Codex runs a hook only once it has trusted that exact definition."""

    @staticmethod
    def wired(events):
        from app.agents.adapters import codex
        # As the terminal's sink: a turn's events file, unless the kind names it otherwise.
        return codex.wire(["codex"], events, lambda label, source, events=events:
                          ["/py/python", "/repo/app/agents/turn_hook.py", events, label, source])

    @staticmethod
    def hooks(argv):
        import tomllib
        found = {}
        for index, value in enumerate(argv):
            if value == "-c" and argv[index + 1].startswith("hooks."):
                key, _, toml = argv[index + 1].partition("=")
                found[key[len("hooks."):]] = tomllib.loads("v = " + toml)["v"][0]["hooks"][0]
        return found

    def test_a_start_held_for_the_operator_is_read_off_its_screen_and_said(self):
        from app.agents.adapters import codex
        # As Codex 0.166 drew it, measured: its words run together where it draws them so.
        review = ("Hooks need review1 hook is new or changed.Hooks can run outside the sandbox after you trust "
                  "them.\u203a 1. Review hooks 2.Trustallandcontinue3.Continuewithouttrusting(hookswon'trun)")
        self.assertIn("1 hook(s)", codex.held(review))
        self.assertIn("role's terminal", codex.held(review))
        self.assertIn("role's terminal", codex.held("Trust this folder? 1. Yes 2. No"))
        self.assertIsNone(codex.held("\u203a Ask Codex to do anything ? for shortcuts"))

    def test_one_definition_on_every_turn_its_file_in_the_environment_and_no_notify(self):
        first, second = self.wired("one/turn.events"), self.wired("two/turn.events")
        self.assertEqual(first, second, "the same definition whatever the turn's file")
        self.assertNotIn("notify", " ".join(first))
        hooks = self.hooks(first)
        self.assertEqual(sorted(hooks), ["Stop", "UserPromptSubmit"])
        for label, hook in hooks.items():
            self.assertEqual(hook["type"], "command")
            self.assertEqual(hook["command"].split(), ["/py/python", "/repo/app/agents/turn_hook.py", "-", label,
                                                       "stdin"])


class DeepSeekSettings(unittest.TestCase):
    def test_provider_settings_share_the_private_trace_file_and_survive_hook_wiring(self):
        from app.agents.adapters import claude_code
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "settings.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"enabledPlugins": {"tracer": True}}, fh)
            env, chosen = claude_code.configure({"provider": "deepseek", "model": "deepseek-flash"},
                                                {"DEEPSEEK_API_KEY": "test-provider", "KEEP": "kept"}, path, None)
            self.assertEqual(chosen, path, "one private file, no duplicated trace credentials")
            self.assertEqual(env["KEEP"], "kept")
            wired = claude_code.wire(["claude", "--settings", chosen], "turn.events",
                                     lambda label, source: ["python", "hook.py", "events", label, source])
            with open(path, encoding="utf-8") as fh:
                settings = json.load(fh)
            self.assertEqual(settings["enabledPlugins"], {"tracer": True})
            self.assertEqual(settings["env"]["ANTHROPIC_AUTH_TOKEN"], "test-provider")
            self.assertIn("Stop", settings["hooks"])
            self.assertTrue(settings["autoCompactEnabled"])
            self.assertNotIn("test-provider", " ".join(wired), "credentials never enter the command line")


class ClaudeCompacts(unittest.TestCase):
    """A role's Claude session spans every turn of the role, and one that fills its context with auto-compact off
    stops at *Context limit reached* firing no hook, so the turn waits out its limit (measured, the operator's
    build): its turns ask for auto-compact in their own settings, which outrank the operator's."""

    @staticmethod
    def sink(label, source):
        return ["python", "hook", label, source]

    def test_its_own_settings_ask_for_auto_compact(self):
        from app.agents.adapters import claude_code
        wired = claude_code.wire(["claude", "--session-id", "s"], "turn.events", self.sink)
        settings = json.loads(wired[wired.index("--settings") + 1])
        self.assertIs(settings.get("autoCompactEnabled"), True)
        self.assertIn("Stop", settings["hooks"])

    def test_a_traced_turns_settings_file_asks_for_it_and_keeps_what_it_held(self):
        from app.agents.adapters import claude_code
        folder = tempfile.mkdtemp(prefix="orchestra-claude-settings-")
        self.addCleanup(lambda: __import__("shutil").rmtree(folder, True))
        path = os.path.join(folder, "claude-settings.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"enabledPlugins": {claude_code.PLUGIN: True}}, fh)
        claude_code.wire(["claude", "--settings", path], "turn.events", self.sink)
        with open(path, encoding="utf-8") as fh:
            settings = json.load(fh)
        self.assertIs(settings.get("autoCompactEnabled"), True)
        self.assertEqual(settings["enabledPlugins"], {claude_code.PLUGIN: True})
        self.assertIn("Stop", settings["hooks"])

    def test_a_turn_stopped_at_its_context_limit_is_read_off_its_screen(self):
        from app.agents.adapters import claude_code
        working = "Running… (esc to interrupt) "
        # As the operator's build drew it (measured), its words spaced and run together, and as Claude's docs
        # spell the error that ends its auto-compact when the context refills at once.
        stopped = ('Background command "Run each red case" completed (exit code 0)Context limit reached · /compact '
                   "or /clear to continue · auto-compact is off · /config to turn it on✻ Cogitated for 0s")
        together = "Contextlimitreached·/compactor/cleartocontinue·auto-compactisoff·/configtoturniton"
        thrashing = "Autocompact is thrashing: the context refilled to the limit several times in a row"
        # As the build's last events stood: its own prompt, then a background check's notification, submitted.
        begun = [{"_hook": "UserPromptSubmit"}, {"_hook": "PostToolUse"}, {"_hook": "UserPromptSubmit"}]
        for screen in (working + stopped, "esctointerrupt " + together, working + thrashing):
            self.assertIn("context limit", claude_code.halted(screen, begun), screen)
        # Working again after it — compacting and going on, or writing those words itself: nothing to read.
        self.assertIsNone(claude_code.halted(stopped + " " + working, begun))
        self.assertIsNone(claude_code.halted(working + "editing the plan", begun))
        # Its answer ended — a background task of it still running — quoting the line: idle as it should be.
        self.assertIsNone(claude_code.halted(working + stopped, begun + [{"_hook": "Stop"}]))


class Reply(unittest.TestCase):
    """What a role last answered the operator in its terminal after its turn — words they settled with it at a
    stop, for the page to send on — read from the turn's events by the kind whose events they are."""
    PROMPT = "$architect\n\n# Task\nassess the plan"

    def test_codex_answers_the_last_prompt_typed_in_its_own_thread_never_a_side_thread_or_its_turn(self):
        def asked(turn, prompt, thread="t1"):
            return {"_hook": "UserPromptSubmit", "session_id": thread, "turn_id": turn, "prompt": prompt}

        def stopped(turn, said, thread="t1", at=None):
            return {"_hook": "Stop", "session_id": thread, "turn_id": turn, "last_assistant_message": said, "_at": at}
        turn = [asked("u1", self.PROMPT), stopped("u1", '{"verdict":"BLOCKER","feedback":"answer Q1"}')]
        side = [asked("x1", "Write a brief catch-up", thread="t2"), stopped("x1", '{"summary":"..."}', thread="t2")]
        self.assertIsNone(adapters.reply(turn + side, self.PROMPT, "t1"), "its turn's own answer is the stop's already")
        talk = [asked("u2", "which plugins for q1?"), stopped("u2", "The private one."),
                asked("u3", "guide the engineer"), stopped("u3", "Engineer: revise the todo.", at=1700.5)]
        self.assertEqual(adapters.reply(turn + talk + side, self.PROMPT, "t1"), ("Engineer: revise the todo.", 1700.5))
        self.assertIsNone(adapters.reply(turn + talk, self.PROMPT, "t9"), "another thread's")

    def test_codex_reads_a_record_its_notify_wrote(self):
        # Turns recorded before its hooks were wired, its notify's events: still read, for the stop they wait at.
        def done(thread, inputs, said, at=None):
            return {"_hook": "notify", "type": "agent-turn-complete", "thread-id": thread, "input-messages": inputs,
                    "last-assistant-message": said, "_at": at}
        turn = done("t1", [self.PROMPT], '{"verdict":"BLOCKER","feedback":"answer Q1"}')
        # Its own catch-up summaries come from threads of their own.
        summary = done("t2", ["Write a brief catch-up for a user returning to this task."], '{"summary":"..."}')
        asked = done("t1", [self.PROMPT, "which plugins for q1?"], "The private one.")
        handoff = done("t1", [self.PROMPT, "which plugins for q1?", "guide the engineer"], "Engineer: revise the todo.",
                       at=1700.5)
        self.assertIsNone(adapters.reply([turn], self.PROMPT, "t1"), "its turn's own answer is the stop's already")
        self.assertIsNone(adapters.reply([turn, summary], self.PROMPT, "t1"))
        # Its answer and when its hook recorded it, for two roles' answers to be told apart by when each came.
        self.assertEqual(adapters.reply([turn, asked, summary, handoff, summary], self.PROMPT, "t1"),
                         ("Engineer: revise the todo.", 1700.5))
        self.assertIsNone(adapters.reply([turn, asked, handoff], self.PROMPT, "t9"), "another session's")

    def test_claude_answers_the_last_prompt_typed_after_its_turns_never_its_turns_own(self):
        def asked(prompt_id, prompt, session="s1"):
            return {"_hook": "UserPromptSubmit", "session_id": session, "prompt_id": prompt_id, "prompt": prompt}

        def stopped(prompt_id, said, session="s1", at=None):
            return {"_hook": "Stop", "session_id": session, "prompt_id": prompt_id, "last_assistant_message": said,
                    "background_tasks": [], "_at": at}
        turn = [asked("p1", self.PROMPT), stopped("p1", "BLOCKER: answer Q1")]
        self.assertIsNone(adapters.reply(turn, self.PROMPT, "s1"))
        chat = turn + [asked("p2", "which plugins?"), stopped("p2", "The private one."),
                       asked("p3", "guide the engineer"), stopped("p3", "Engineer: revise the todo.", at=1800.0)]
        self.assertEqual(adapters.reply(chat, self.PROMPT, "s1"), ("Engineer: revise the todo.", 1800.0))
        self.assertIsNone(adapters.reply(chat, self.PROMPT, "s2"), "another session's")


if __name__ == "__main__":
    unittest.main()
