"""What the activities ask of a run's kinds of agent: that each one's program, and each skill the run's
stages invoke, is on this host before any work, that no agent inherits a session any kind leaves behind,
and that a traced turn's keys live only in the turn's private folder.

Each is proven with the suite's own kind (`stand_in.py`), whose name is not its program's, beside the
shipped ones.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

# The suite's own folder, reached from this concern's folder inside it, and the
# checkout above both: the shared harness and the fixtures live at the suite root.
HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path[:0] = [PKG, HERE]

from temporalio.exceptions import ApplicationError  # noqa: E402

from app.agents import adapters, terminal  # noqa: E402
from app.agents.adapters import claude_code, codex  # noqa: E402
from app.application import activities  # noqa: E402
from app.observability import telemetry as T  # noqa: E402
from fakes import FakeRepos, FakeWorktrees, Recorder, every_skill, installed  # noqa: E402
import stand_in  # noqa: E402

SHIPPED = ("claude-code", "codex")


def policy(kind, **extra):
    """A run's policy with both roles on `kind`, as a run carries it."""
    roles = {"engineer": {"kind": kind, "workspace_access": "write", "persona": "Build it."},
             "architect": {"kind": kind, "workspace_access": "read", "persona": "Judge it."}}
    return dict({"roles": roles, "targets": {"wsl": {"worktree_root": "/fake/worktrees"}},
                 "timeout_seconds": 60, "max_rounds": {"plan": 2, "build": 2}, "stage_skills": {}}, **extra)


def state(run_id):
    return {"run_id": run_id, "task": "t", "phase": "plan", "round": 0, "episode": 1,
            "worktree_path": "/fake/worktree", "todo_path": "/fake/worktree/todo/x.md", "agent_sessions": {}}


class Preparing(unittest.TestCase):
    """`prepare` looks for each bound kind's program by the program's own name, before the repository is
    resolved; one that is missing refuses the run before any work."""

    SELECTED = {"id": "example", "target": "wsl", "path": "/x"}

    def setUp(self):
        stand_in.plant(self)
        self.repos = FakeRepos()
        self.looked = []

    def host(self, programs):
        def which(program):
            self.looked.append(program)
            return "/fake/bin/%s" % program if program in programs else None
        return activities.Activities(runner=None, git=None, repositories=self.repos, telemetry=None, which=which,
                                     holds_skill=every_skill)

    def test_its_program_found_the_run_goes_on_to_its_repository(self):
        resolved = self.host({stand_in.PROGRAM}).prepare({"repository": self.SELECTED,
                                                          "policy": policy(stand_in.KIND)})
        self.assertEqual(self.looked, [stand_in.PROGRAM], "each kind once, by its program")
        self.assertEqual(self.repos.calls, [(self.SELECTED, "/fake/worktrees")])
        self.assertEqual(resolved["repo_path"], "/fake/repo")

    def test_its_program_missing_the_run_is_refused_naming_the_program_before_any_work(self):
        with self.assertRaises(ApplicationError) as raised:
            self.host(set()).prepare({"repository": self.SELECTED, "policy": policy(stand_in.KIND)})
        self.assertEqual(raised.exception.message, "stand-in-agent is not installed on the wsl host")
        self.assertEqual(self.repos.calls, [], "no repository resolved: no git read, no worktree, no agent")

    def test_control_the_kinds_own_name_is_not_its_program(self):
        """A lookup by the kind's name — what the preflight asked when kinds were their programs — would
        refuse the host that has the program."""
        host = self.host({stand_in.PROGRAM})
        self.assertIsNone(host.which(stand_in.KIND))
        self.assertIsNotNone(host.which(stand_in.PROGRAM))

    def test_every_kinds_launch_runs_its_program(self):
        for kind in SHIPPED + (stand_in.KIND,):
            adapter = adapters.load(kind)
            for access in adapters.ACCESSES:
                with self.subTest(kind=kind, access=access):
                    argv, _ = adapter.command({"workspace_access": access, "model": None, "effort": None}, None)
                    self.assertEqual(adapter.host(argv)[0], adapter.EXECUTABLE)


class Skills(unittest.TestCase):
    """Neither CLI fails a turn whose skill no folder holds, so `prepare` looks for every skill the run's
    stages invoke where its kind finds skills, and refuses the run before any work when one is not there."""

    SELECTED = {"id": "example", "target": "wsl", "path": "/x"}

    def setUp(self):
        stand_in.plant(self)
        self.repo = tempfile.mkdtemp(prefix="orchestra-skills-repo-")
        self.addCleanup(shutil.rmtree, self.repo, True)
        # Where the stand-in finds a skill of that name: inside the repository the run resolved.
        self.folder = os.path.join(self.repo, ".stand-in", "skills", "plan-it")

    def prepare(self, holds_skill=activities.holds_skill):
        repo = self.repo

        class Here(FakeRepos):
            def resolve(inner, selected, worktree_root):
                return dict(FakeRepos.resolve(inner, selected, worktree_root), repo_path=repo)
        host = activities.Activities(runner=None, git=None, repositories=Here(), telemetry=None,
                                     which=installed, holds_skill=holds_skill)
        return host.prepare({"repository": self.SELECTED,
                             "policy": policy(stand_in.KIND, stage_skills={"plan": "plan-it"})})

    def test_a_skill_where_its_kind_finds_it_lets_the_run_go_on(self):
        os.makedirs(self.folder)
        with open(os.path.join(self.folder, "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write("---\nname: plan-it\n---\n")
        self.assertEqual(self.prepare()["repo_path"], self.repo)

    def test_a_skill_no_folder_holds_refuses_the_run_naming_it_and_where_it_looked(self):
        os.makedirs(self.folder)
        # A folder of that name is not a skill without its SKILL.md.
        with self.assertRaises(ApplicationError) as raised:
            self.prepare()
        self.assertEqual(raised.exception.message,
                         "the plan stage's skill plan-it is in none of %s on the wsl host" % self.folder)

    def test_control_a_preparation_that_looks_nowhere_starts_the_run(self):
        self.assertEqual(self.prepare(holds_skill=lambda folder: True)["repo_path"], self.repo)


class Environment(unittest.TestCase):
    """No agent, of whatever kind, inherits a marker that any kind's sessions leave."""

    MARKERS = {"CLAUDECODE": "1", "CLAUDE_PID": "1", "CLAUDE_CODE_SESSION_ID": "x", "CLAUDE_CODE_CHILD_SESSION": "1",
               "STAND_IN_SESSION": "s", "STAND_IN_TURN_ID": "t"}

    def setUp(self):
        stand_in.plant(self)
        self.run_id = "test-activities-%s" % os.urandom(4).hex()
        self.addCleanup(shutil.rmtree, activities.run_dir(self.run_id), True)
        self.addCleanup(terminal.close_run, self.run_id)

    def test_no_agent_of_any_kind_inherits_any_kinds_session_markers(self):
        for kind in SHIPPED + (stand_in.KIND,):
            adapter = adapters.load(kind)
            given = []

            def runner(worktree, argv, rdir, name, prompt, timeout, env, *, kind):
                given.append(env)
                return 0, adapter.output("planned", "s1")
            with self.subTest(kind=kind), mock.patch.dict(os.environ, self.MARKERS):
                host = activities.Activities(runner=runner, git=FakeWorktrees(), telemetry=None)
                host.run_role({"stage": "plan", "state": state(self.run_id), "policy": policy(kind)})
                self.assertEqual(set(given[0]) & set(self.MARKERS), set())
                self.assertIn("PATH", given[0])

    def test_control_stripping_only_the_agents_own_kinds_markers_leaves_claudes_in_a_codex_agents(self):
        kept = {key for key in self.MARKERS
                if key not in codex.SESSION_MARKERS and not key.startswith(tuple(codex.SESSION_MARKER_PREFIXES))}
        self.assertIn("CLAUDECODE", kept)
        self.assertIn("CLAUDECODE", claude_code.SESSION_MARKERS)


# The stand-in, traced as a kind with keys is: its settings, the trace store's secret among them, written into
# the private folder it is handed, and named to its program.
KEYED = stand_in.variant(command="""def command(role, resume_id, traced=None):
    return [EXECUTABLE, "--keys", traced or ""] + (["--thread", resume_id] if resume_id else []), None
""") + """

def trace_settings(context, private):
    if not context:
        return None
    path = private.path("keys.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"secret": context["secret_key"]}, fh)
    return path
"""
# The control: the same, in a folder of the kind's own making.
OWN_FOLDER = KEYED.replace('path = private.path("keys.json")',
                           'import tempfile\n    path = os.path.join(tempfile.mkdtemp(prefix="stand-in-keys-"), '
                           '"keys.json")')


class TracedKeys(unittest.TestCase):
    """A traced turn's keys live in `telemetry`'s private folder only, only while the turn runs; a folder
    whose process is gone is swept."""

    def setUp(self):
        stand_in.plant(self, {"keyed_stand_in": KEYED, "own_folder_stand_in": OWN_FOLDER})
        self.run_id = "test-activities-%s" % os.urandom(4).hex()
        self.addCleanup(shutil.rmtree, activities.run_dir(self.run_id), True)
        self.addCleanup(terminal.close_run, self.run_id)
        patched = mock.patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "pk-test", "LANGFUSE_SECRET_KEY": "sk-test"})
        patched.start()
        self.addCleanup(patched.stop)

    def turn(self, kind, during, rc=0):
        """Run one traced plan step of `kind`, calling `during(keys)` while its agent works."""
        seen = []

        def runner(worktree, argv, rdir, name, prompt, timeout, env, *, kind):
            keys = argv[argv.index("--keys") + 1]
            seen.append(keys)
            during(keys)
            return rc, stand_in_output()
        host = activities.Activities(runner=runner, git=FakeWorktrees(), telemetry=Recorder())
        try:
            host.run_role({"stage": "plan", "state": state(self.run_id), "policy": policy(kind)})
        except ApplicationError:
            if rc == 0:
                raise
        return seen[0]

    def test_the_keys_are_in_the_private_folder_during_the_turn_and_gone_after_it_passed_or_failed(self):
        for rc in (0, 1):
            with self.subTest(rc=rc):
                during = []

                def look(keys):
                    folder = os.path.dirname(keys)
                    with open(keys, encoding="utf-8") as fh:
                        during.append((os.path.dirname(folder), os.path.basename(folder), json.load(fh)))
                keys = self.turn("keyed-stand-in", look, rc=rc)
                (parent, name, content), = during
                self.assertEqual(os.path.normcase(parent), os.path.normcase(tempfile.gettempdir()))
                self.assertTrue(name.startswith("%s%d-" % (T.TRACE_DIR_PREFIX, os.getpid())), name)
                self.assertEqual(content, {"secret": "sk-test"})
                self.assertFalse(os.path.exists(os.path.dirname(keys)), "the folder outlived its turn")

    def test_a_folder_whose_process_is_gone_is_swept(self):
        swept = []
        # The worker taken as gone mid-turn, as a later worker's sweep would find it.
        keys = self.turn("keyed-stand-in", lambda keys: swept.append(
            (T.discard_stale_settings(gone=(os.getpid(),)), os.path.exists(keys))))
        (removed, left), exists = swept[0]
        self.assertIn(os.path.dirname(keys), removed)
        self.assertEqual((left, exists), ([], False))

    def test_control_a_folder_of_the_kinds_own_is_never_swept(self):
        swept = []
        keys = self.turn("own-folder-stand-in", lambda keys: swept.append(
            (T.discard_stale_settings(gone=(os.getpid(),)), os.path.exists(keys))))
        self.addCleanup(shutil.rmtree, os.path.dirname(keys), True)
        (removed, _), exists = swept[0]
        self.assertNotIn(os.path.dirname(keys), removed)
        self.assertTrue(exists, "the key outlives the process that wrote it")


def stand_in_output():
    return json.dumps({"thread": "s1", "answer": "planned"}) + "\n"


if __name__ == "__main__":
    unittest.main()
