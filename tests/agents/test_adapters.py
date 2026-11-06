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

    OURS = {"C:\\<session-flags>\\config.toml:user_prompt_submit:0:0": "sha256:aa",
            "C:\\<session-flags>\\config.toml:stop:0:0": "sha256:bb"}

    class Started:
        """Codex started for its dialog: draws `screen`; told to trust, records `written` in its config."""

        def __init__(self, screen, config, written):
            self.screen, self.config, self.written, self.sent, self.ended = screen, config, written, [], False

        def text(self):
            return self.screen

        def write(self, data):
            self.sent.append(data)
            os.makedirs(os.path.dirname(self.config), exist_ok=True)
            with open(self.config, "a", encoding="utf-8") as fh:
                for key, value in self.written.items():
                    fh.write("\n[hooks.state.'%s']\ntrusted_hash = \"%s\"\n" % (key, value))

        def end(self):
            self.ended = True

    def trusting(self, screen):
        from app.agents.adapters import codex
        home = self.home = tempfile.mkdtemp(prefix="orchestra-codex-home-")
        self.addCleanup(lambda: __import__("shutil").rmtree(home, True))
        self.record = os.path.join(home, "hook-trust.json")
        started = []

        def start(args):
            started.append(self.Started(screen, codex.config_path(home), self.OURS))
            return started[-1]

        def trust():
            return codex.hooks_trust(lambda label, source, events="e": ["/py", "/hook.py", events, label, source],
                                     start, self.record, home=home)
        return codex, started, trust

    def test_its_hooks_are_trusted_once_by_its_own_dialog_and_then_need_none(self):
        codex, started, trust = self.trusting("Hooks need review 2 hooks are new or changed. 1. Review hooks "
                                              "2. Trust all and continue Ask Codex to do anything")
        self.assertTrue(trust())
        self.assertEqual((started[0].sent, started[0].ended), ([codex.TRUST_ALL], True))
        self.assertFalse(trust(), "remembered with what Codex wrote: no dialog again")
        self.assertEqual(len(started), 1)

    def test_what_it_remembers_of_a_config_that_is_gone_is_dropped(self):
        # A demo's own Codex home goes with the demo: its entry is not kept, demo after demo.
        codex, started, trust = self.trusting("Hooks need review 2 hooks are new or changed. Ask Codex to do anything")
        gone = os.path.join(self.home, "vanished", "config.toml") + "\n[]"
        with open(self.record, "w", encoding="utf-8") as fh:
            json.dump({gone: {"key": "sha256:old"}}, fh)
        self.assertTrue(trust())
        with open(self.record, encoding="utf-8") as fh:
            kept = json.load(fh)
        self.assertNotIn(gone, kept)
        self.assertEqual(len(kept), 1, "what it trusted now")

    def test_other_hooks_waiting_for_review_are_never_trusted_for_the_operator(self):
        codex, started, trust = self.trusting("Hooks need review 3 hooks are new or changed.")
        with self.assertRaises(codex.HooksRefused) as refused:
            trust()
        self.assertIn("/hooks", str(refused.exception))
        self.assertEqual((started[0].sent, started[0].ended), ([], True), "nothing answered; ended")

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
