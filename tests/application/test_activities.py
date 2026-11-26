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
from app.agents import nodes as N  # noqa: E402
from app.agents.adapters import claude_code, codex  # noqa: E402
from app.application import activities  # noqa: E402
from app.application import settings as S  # noqa: E402
from app.observability import telemetry as T  # noqa: E402
from app.foundation import flows  # noqa: E402
from app.foundation import localenv  # noqa: E402
from app.foundation import policy as P  # noqa: E402
from app.workspace import worktrees  # noqa: E402
from fakes import FakeRepos, FakeWorktrees, Recorder, every_skill, installed  # noqa: E402
import stand_in  # noqa: E402

SHIPPED = ("claude-code", "codex", "pi")


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

    def test_preparation_checks_the_pi_launcher_selected_by_the_profile(self):
        configured = policy("pi")
        for role in configured["roles"].values():
            role.update(launcher="pi-sot", provider="deepseek", model="deepseek-flash")
        self.host({"pi-sot"}).prepare({"repository": self.SELECTED, "policy": configured})
        self.assertEqual(self.looked, ["pi-sot"])

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

    def prepare(self, holds_skill=activities.holds_skill, skills="plan-it"):
        repo = self.repo

        class Here(FakeRepos):
            def resolve(inner, selected, worktree_root):
                return dict(FakeRepos.resolve(inner, selected, worktree_root), repo_path=repo)
        host = activities.Activities(runner=None, git=None, repositories=Here(), telemetry=None,
                                     which=installed, holds_skill=holds_skill)
        return host.prepare({"repository": self.SELECTED,
                             "policy": policy(stand_in.KIND, stage_skills={"plan": skills})})

    def test_a_skill_where_its_kind_finds_it_lets_the_run_go_on(self):
        os.makedirs(self.folder)
        with open(os.path.join(self.folder, "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write("---\nname: plan-it\n---\n")
        self.assertEqual(self.prepare()["repo_path"], self.repo)

    def test_shipped_flows_prepare_with_no_installed_skills(self):
        settings = S.load(path=P.SETTINGS_FILE)
        missing_skill = mock.Mock(return_value=False)
        host = activities.Activities(runner=None, git=None, repositories=FakeRepos(), telemetry=None,
                                     which=installed, holds_skill=missing_skill)
        with mock.patch.object(activities.trust, "ensure"):
            for flow in flows.available():
                with self.subTest(flow=flow["name"]):
                    policy = S.run_policy(settings, flow["steps"])
                    prepared = host.prepare({"repository": self.SELECTED, "policy": policy})
                    self.assertEqual(prepared["repo_path"], "/fake/repo")
        missing_skill.assert_not_called()

    def test_a_skill_no_folder_holds_refuses_the_run_naming_it_and_where_it_looked(self):
        os.makedirs(self.folder)
        # A folder of that name is not a skill without its SKILL.md.
        with self.assertRaises(ApplicationError) as raised:
            self.prepare()
        self.assertEqual(raised.exception.message,
                         "the plan stage's skill plan-it is in none of %s on the wsl host" % self.folder)

    def test_control_a_preparation_that_looks_nowhere_starts_the_run(self):
        self.assertEqual(self.prepare(holds_skill=lambda folder: True)["repo_path"], self.repo)

    def test_a_missing_supporting_skill_refuses_the_stack_before_worktree_creation(self):
        with self.assertRaisesRegex(ApplicationError, "plan stage's skill evidence-check"):
            self.prepare(holds_skill=lambda folder: folder == self.folder, skills=["plan-it", "evidence-check"])

    def test_a_skill_missing_from_the_worktree_stops_the_turn_before_launch(self):
        run = dict(state("test-missing-worktree-skill"), repo_path=self.repo, target="wsl")
        self.addCleanup(shutil.rmtree, activities.run_dir(run["run_id"]), True)
        runner = mock.Mock(return_value=(1, "the agent should not start"))
        kind = stand_in.KIND
        holds = lambda folder: (folder == self.folder or
                                folder == os.path.join(run["worktree_path"], ".stand-in", "skills", "plan-it") or
                                folder == os.path.join(self.repo, ".stand-in", "skills", "evidence-check"))
        args = {"stage": "plan", "state": run, "policy": policy(kind, stage_skills={"plan": ["plan-it", "evidence-check"]})}
        host = activities.Activities(runner=runner, git=FakeWorktrees(), repositories=FakeRepos(), telemetry=None,
                                     which=installed, holds_skill=holds)
        self.prepare(holds_skill=holds, skills=["plan-it", "evidence-check"])
        with mock.patch.object(activities.trust, "ensure"), self.assertRaisesRegex(ApplicationError, "evidence-check"):
            host.run_role(args)
        runner.assert_not_called()


class Environment(unittest.TestCase):
    """No agent, of whatever kind, inherits a marker that any kind's sessions leave."""

    MARKERS = {"CLAUDECODE": "1", "CLAUDE_PID": "1", "CLAUDE_CODE_SESSION_ID": "x", "CLAUDE_CODE_CHILD_SESSION": "1",
               "STAND_IN_SESSION": "s", "STAND_IN_TURN_ID": "t"}

    def setUp(self):
        stand_in.plant(self)
        self.run_id = "test-activities-%s" % os.urandom(4).hex()
        self.addCleanup(shutil.rmtree, activities.run_dir(self.run_id), True)
        self.addCleanup(terminal.close_run, self.run_id)

    def test_a_failed_turn_still_exports_recorded_usage_without_a_final_session(self):
        adapter = adapters.load("pi")
        host = activities.Activities(runner=lambda *args, **kwargs: (1, "provider failed"),
                                     git=FakeWorktrees(), telemetry=None)
        context = {"traceparent": "parent"}
        with mock.patch.object(T, "trace_context", return_value=context), \
                mock.patch.object(adapter, "upload", return_value=None) as upload:
            with self.assertRaises(ApplicationError):
                host.run_role({"stage": "plan", "state": state(self.run_id), "policy": policy("pi")})
        upload.assert_called_once_with(None, context)

    def test_deepseek_is_scoped_to_its_profile_and_missing_auth_starts_no_agent(self):
        configured = policy("claude-code")
        configured["roles"]["engineer"].update(provider="deepseek", model="deepseek-flash", effort="max")
        given = []

        def runner(worktree, argv, rdir, name, prompt, timeout, env, *, kind):
            with open(argv[argv.index("--settings") + 1], encoding="utf-8") as fh:
                private_settings = json.load(fh)
            given.append((argv, env, timeout, private_settings))
            return 0, "planned"

        host = activities.Activities(runner=runner, git=FakeWorktrees(), telemetry=None)
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-deepseek", "ANTHROPIC_API_KEY": "test-anthropic",
                                         "CLAUDE_CODE_OAUTH_TOKEN": "test-subscription", "CLAUDE_CODE_USE_VERTEX": "1"}):
            host.run_role({"stage": "plan", "state": state(self.run_id), "policy": configured})
            argv, env, timeout, private_settings = given[0]
            self.assertEqual(argv[argv.index("--model") + 1], "deepseek-flash[1m]")
            self.assertEqual(env["ANTHROPIC_BASE_URL"], "https://api.deepseek.com/anthropic")
            self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], "test-deepseek")
            for competing in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_USE_VERTEX"):
                self.assertEqual(env[competing], "")
                self.assertEqual(private_settings["env"][competing], "", "overrides competing settings-file env")
            self.assertEqual(private_settings["env"]["ANTHROPIC_AUTH_TOKEN"], "test-deepseek")
            self.assertFalse(os.path.exists(argv[argv.index("--settings") + 1]), "private settings removed after the turn")
            for name in ("OPUS", "SONNET", "HAIKU", "FABLE"):
                self.assertEqual(env["ANTHROPIC_DEFAULT_%s_MODEL" % name], "deepseek-flash")
            self.assertEqual(os.environ["ANTHROPIC_API_KEY"], "test-anthropic", "the worker's environment is untouched")
        given.clear()
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}), \
                mock.patch.object(localenv, "read", return_value={}), self.assertRaises(ApplicationError) as raised:
            host.run_role({"stage": "plan", "state": state(self.run_id), "policy": configured})
        self.assertIn("DEEPSEEK_API_KEY", str(raised.exception))
        self.assertEqual(given, [], "missing DeepSeek credentials never fall back to a subscription")

    def test_deepseek_reads_the_deployment_file_without_exporting_other_values(self):
        role = {"provider": "deepseek", "model": "deepseek-flash"}
        with mock.patch.object(localenv, "read", return_value={"DEEPSEEK_API_KEY": "test-file", "UNRELATED": "private"}):
            configured = claude_code.environment(role, {})
        self.assertEqual(configured["ANTHROPIC_AUTH_TOKEN"], "test-file")
        self.assertNotIn("UNRELATED", configured)
        with mock.patch.object(localenv, "read", side_effect=OSError("private contents")):
            unchanged = {"ANTHROPIC_AUTH_TOKEN": "test-existing"}
            self.assertEqual(claude_code.environment({}, unchanged), {}, "other profiles read no DeepSeek key")
            self.assertEqual(claude_code.environment(role, {"DEEPSEEK_API_KEY": "test-env"})["ANTHROPIC_AUTH_TOKEN"],
                             "test-env", "an explicit environment needs no file")
            with self.assertRaisesRegex(Exception, "cannot read DeepSeek credentials") as raised:
                claude_code.environment(role, {})
        self.assertNotIn("private contents", str(raised.exception))

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
        # A temporary folder of this class's own: the sweep these tests make takes every ended process's
        # folder it finds, and the machine's own holds the ones other classes' workers left for their checks.
        own = tempfile.mkdtemp(prefix="orchestra-keys-")
        self.addCleanup(shutil.rmtree, own, True)
        self.addCleanup(setattr, tempfile, "tempdir", tempfile.tempdir)
        tempfile.tempdir = own

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


class Closeout(unittest.TestCase):
    """The engineer's closeout turn against a real repository: the tree it left is the one its run holds for
    the merge, and a turn that changed what the architect verified, or left the todo unclosed, fails."""

    PLAN = "todo/2026-09-15_1200-task.md"
    DONE = "todo/done/2026-09-15_1200-task.md"

    def setUp(self):
        import subprocess
        import folders
        self.repo = tempfile.mkdtemp(prefix="orchestra-closeout-")
        self.addCleanup(folders.remove, self.repo)
        for args in (["init", "-q", "-b", "develop"], ["config", "user.email", "t@t"], ["config", "user.name", "t"],
                     ["config", "core.autocrlf", "false"]):
            subprocess.run(["git", "-C", self.repo] + args, check=True)
        self.write("app.txt", "one\n")
        self.write("roles/engineer.md", "You are the engineer.\n")
        subprocess.run(["git", "-C", self.repo, "add", "-A"], check=True)
        subprocess.run(["git", "-C", self.repo, "commit", "-q", "-m", "base"], check=True)
        # The change the architect verified, uncommitted as a run's is.
        self.write("app.txt", "one\nbuilt\n")
        self.write("docs/guide.md", "the guide\n")
        self.write(self.PLAN, "**Status:** REVIEW REQUIRED\nplan\n")
        self.run_id = "test-closeout-%s" % os.urandom(4).hex()
        self.addCleanup(shutil.rmtree, activities.run_dir(self.run_id), True)
        self.addCleanup(terminal.close_run, self.run_id)
        self.verified = worktrees.work_tree(self.repo)
        # As the run's repository resolves: its todo folders, and the documents a closeout may bring up to date.
        self.state = {"run_id": self.run_id, "task": "t", "phase": "closeout", "round": 0, "episode": 3,
                      "worktree_path": self.repo, "todo_path": os.path.join(self.repo, *self.PLAN.split("/")),
                      "plan": os.path.join(*self.PLAN.split("/")), "todo_dir": "todo", "todo_done_dir": "todo/done",
                      "closeout_docs": ["**/README.md", "docs/"], "agent_sessions": {"engineer": "s-1"},
                      "verified_tree": self.verified}

    def write(self, name, text):
        path = os.path.join(self.repo, *name.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)

    def closes_out(self):
        """What a closeout does: the todo cut and moved to the done folder, a document brought up to date."""
        os.remove(self.state["todo_path"])
        self.write(self.DONE, "**Status:** PASS 2026-09-15\nthe record\n")
        self.write("docs/guide.md", "the guide\nwhat stays true\n")

    def turn(self, edit, **state):
        def runner(worktree, argv, rdir, name, prompt, timeout, env, *, kind):
            edit()
            return 0, "closed out\n"
        host = activities.Activities(runner=runner, git=worktrees, telemetry=None)
        return host.run_role({"stage": "closeout", "state": dict(self.state, **state),
                              "policy": policy("claude-code")})

    def refused(self, edit, **state):
        with self.assertRaises(ApplicationError) as failed:
            self.turn(edit, **state)
        return str(failed.exception)

    def test_the_tree_a_closeout_left_is_the_one_the_run_holds_for_its_merge(self):
        result = self.turn(self.closes_out)
        self.assertEqual(result["final_tree"], worktrees.work_tree(self.repo))
        self.assertNotEqual(result["final_tree"], self.verified)
        self.assertNotIn("verdict", result, "a closeout is work: it judges nothing and routes nothing")

    def test_a_closeout_that_changed_what_its_repository_does_not_call_a_document_fails_naming_the_files(self):
        def also_code():
            self.closes_out()
            self.write("app.txt", "one\nbuilt\nand a fix nobody verified\n")
            self.write("tests/test_app.py", "assert True\n")
            # Markdown, and behaviour: no document of this repository's.
            self.write("roles/engineer.md", "You are the engineer, and you may merge.\n")
            self.write("docs/README.md", "a document twice over\n")
        said = self.refused(also_code)
        self.assertIn("closeout_violation: the closeout changed what the architect verified", said)
        for named in ("app.txt", "tests/test_app.py", "roles/engineer.md"):
            self.assertIn(named, said)
        for allowed in ("docs/guide.md", "docs/README.md", "todo/done"):
            self.assertNotIn(allowed, said)

    def test_a_repository_that_names_no_document_leaves_a_closeout_the_todo_alone(self):
        said = self.refused(self.closes_out, closeout_docs=[])
        self.assertIn("docs/guide.md", said)
        self.assertNotIn("todo/", said)
        # The document put back as the refusal asks, the closeout runs again and finds its todo closed already.
        self.write("docs/guide.md", "the guide\n")
        self.assertIn("final_tree", self.turn(lambda: None, closeout_docs=[]), "the todo alone is its to close")

    def test_a_closeout_that_left_the_todo_unclosed_fails_and_holds_no_tree(self):
        said = self.refused(lambda: self.write("docs/guide.md", "the guide\nwhat stays true\n"))
        self.assertIn("closeout_violation: the closeout left the todo unclosed: it is still at " + self.PLAN, said)
        # Gone from where it was, and not where this repository keeps a finished todo.
        os.remove(self.state["todo_path"])
        said = self.refused(lambda: self.write("todo/finished/2026-09-15_1200-task.md", "elsewhere\n"))
        self.assertIn("the closeout left the todo unclosed: it is not at " + self.DONE, said)

    def test_a_repository_that_deletes_a_finished_todo_has_it_deleted(self):
        said = self.refused(lambda: None, todo_done_dir=None)
        self.assertIn("it is still at " + self.PLAN, said)
        result = self.turn(lambda: os.remove(self.state["todo_path"]), todo_done_dir=None)
        self.assertEqual(result["final_tree"], worktrees.work_tree(self.repo))

    def test_a_closeout_with_no_verified_tree_to_stand_on_fails_before_its_agent_starts(self):
        ran = []
        said = self.refused(lambda: ran.append(True), verified_tree=None)
        self.assertIn("closeout_violation", said)
        self.assertEqual(ran, [], "unknown is not unchanged: nothing is closed out against a tree nobody verified")

    def test_a_verified_todo_rename_is_adopted_explicitly_without_moving_files_or_starting_an_agent(self):
        renamed = "todo/concise.md"
        os.rename(self.state["todo_path"], os.path.join(self.repo, *renamed.split("/")))
        self.state["verified_tree"] = worktrees.work_tree(self.repo)
        self.write("todo/done/concise.md", "the finished record\n")
        os.remove(os.path.join(self.repo, *renamed.split("/")))
        before = worktrees.work_tree(self.repo), worktrees.guard(self.repo, self.run_id)
        host = activities.Activities(runner=lambda *args, **kwargs: self.fail("no agent may start"), git=worktrees,
                                     telemetry=None)
        result = host.adopt_todo_name({"state": self.state, "name": "concise.md"})
        self.assertEqual(result, {"plan": renamed, "todo_path": os.path.join(self.repo, "todo", "concise.md")})
        self.state["verified_tree"] = worktrees.work_tree(self.repo)
        self.assertEqual(host.adopt_todo_name({"state": self.state, "name": "concise.md"}), result,
                         "a verified finished record retains the same todo identity")
        self.assertEqual(self.state["plan"].replace("\\", "/"), self.PLAN, "only Temporal may update the saved path")
        self.assertEqual((worktrees.work_tree(self.repo), worktrees.guard(self.repo, self.run_id)), before)

    def test_a_todo_name_mismatch_is_refused_before_paying_for_closeout(self):
        os.rename(self.state["todo_path"], os.path.join(self.repo, "todo", "concise.md"))
        self.state["verified_tree"] = worktrees.work_tree(self.repo)
        ran = []
        with mock.patch.object(T, "run_upload") as upload:
            said = self.refused(lambda: ran.append(True))
        upload.assert_not_called()
        self.assertEqual(ran, [], "a missing recorded path is known before the agent starts")
        self.assertIn("--adopt-todo-name", said)

    def test_a_renamed_todo_in_a_deletion_policy_is_refused_before_its_agent_starts(self):
        os.rename(self.state["todo_path"], os.path.join(self.repo, "todo", "concise.md"))
        self.state["verified_tree"] = worktrees.work_tree(self.repo)
        before = worktrees.work_tree(self.repo), worktrees.guard(self.repo, self.run_id)
        ran = []
        with mock.patch.object(T, "run_upload") as upload:
            said = self.refused(lambda: ran.append(True), todo_done_dir=None)
        self.assertEqual(ran, [])
        upload.assert_not_called()
        self.assertIn("--adopt-todo-name", said)
        self.assertEqual((worktrees.work_tree(self.repo), worktrees.guard(self.repo, self.run_id)), before)

    def test_a_deleted_todo_can_continue_when_it_existed_in_the_verified_tree(self):
        os.remove(self.state["todo_path"])
        ran = []
        result = self.turn(lambda: ran.append(True), todo_done_dir=None)
        self.assertEqual(ran, [True])
        self.assertEqual(result["final_tree"], worktrees.work_tree(self.repo))
        self.assertEqual(self.state["verified_tree"], self.verified)

    def test_preflight_preserves_retained_todos_already_finished_in_the_verified_tree(self):
        self.closes_out()
        self.state["verified_tree"] = worktrees.work_tree(self.repo)
        self.assertIn("final_tree", self.turn(lambda: None))

    def test_adopting_a_todo_name_refuses_unsafe_missing_and_unverified_renames_without_mutation(self):
        self.write("todo/concise.md", "another todo\n")
        self.state["verified_tree"] = worktrees.work_tree(self.repo)
        host = activities.Activities(git=worktrees, telemetry=None)
        before = worktrees.work_tree(self.repo), worktrees.guard(self.repo, self.run_id)
        for name in ("../elsewhere.md", "..\\elsewhere.md", "bad:name.md", "missing.md", "concise.md"):
            with self.subTest(name=name), self.assertRaises(ApplicationError):
                host.adopt_todo_name({"state": self.state, "name": name})
            self.assertEqual((worktrees.work_tree(self.repo), worktrees.guard(self.repo, self.run_id)), before)


class FlexibleCloseout(unittest.TestCase):
    """Real Git protects unfinished todo contents and exact artifact ownership."""
    PLAN, DONE = Closeout.PLAN, Closeout.DONE
    setUp, write = Closeout.setUp, Closeout.write

    def turn(self, disposition='active', edit=None, product=None, **state):
        self.state.update(closeout_version=1, todo_parked_dir='todo/parked', todo_backlog_dir='todo/backlog')
        original = open(self.state['todo_path'], encoding='utf-8').read() if os.path.exists(self.state['todo_path']) else None
        destination = {'active': self.PLAN, 'completed': self.DONE,
                       'parked': 'todo/parked/' + os.path.basename(self.PLAN),
                       'backlog': 'todo/backlog/' + os.path.basename(self.PLAN)}[disposition]
        proposal = {'disposition': disposition, 'remaining': '' if disposition == 'completed' else 'Measure sustained reliability.',
                    'reason': '' if disposition == 'completed' else 'Await the separately approved trial.'}
        output = json.dumps({'todo': proposal if product is None else product})
        self.prompts = []
        def runner(worktree, argv, rdir, name, prompt, timeout, env, *, kind):
            self.prompts.append(prompt)
            if edit:
                edit()
            elif original is not None:
                preamble = '\n\n'.join(proposal[key] for key in ('remaining', 'reason')
                                       if proposal[key] and proposal[key] not in original)
                self.write(destination, (preamble + '\n\n' if preamble else '') + original)
                if destination != self.PLAN:
                    os.remove(self.state['todo_path'])
            return 0, output
        self.host = activities.Activities(runner=runner, git=worktrees, telemetry=None)
        return self.host.run_role({'stage': 'closeout', 'state': dict(self.state, **state), 'policy': policy('claude-code')})

    def test_unfinished_dispositions_preserve_steps_and_the_index(self):
        for disposition in ('active', 'parked', 'backlog'):
            with self.subTest(disposition=disposition):
                self.write(self.PLAN, 'Original acceptance\n- [ ] Complete the live trial\n')
                self.state['verified_tree'] = worktrees.work_tree(self.repo)
                protected = worktrees.guard(self.repo, self.run_id)
                result = self.turn(disposition)
                outcome = result['todo_closeout']
                self.assertEqual(outcome['disposition'], disposition)
                self.assertIn('Measure sustained reliability', outcome['remaining'])
                self.assertIn('- [ ] Complete the live trial', open(os.path.join(self.repo, outcome['path']), encoding='utf-8').read())
                self.assertEqual(worktrees.guard(self.repo, self.run_id), protected)
                if outcome['path'] != self.PLAN:
                    os.rename(os.path.join(self.repo, outcome['path']), self.state['todo_path'])

    def test_reviewed_companion_materials_follow_the_todo_without_modification(self):
        source = self.PLAN[:-3]
        target = 'todo/parked/' + os.path.basename(source)
        self.write(source + '/README.md', 'Sanitized incident evidence and next experiment.\n')
        self.write(source + '/fixtures/sample.txt', 'SYNTHETIC_ORDER_7_ALLOCATION_FAILURE\n')
        self.write(source + '/reproduce.py', 'print("local fixture only")\n')
        self.state['verified_tree'] = worktrees.work_tree(self.repo)
        before = worktrees.guard(self.repo, self.run_id)
        def relocate():
            original = open(self.state['todo_path'], encoding='utf-8').read()
            self.write('todo/parked/' + os.path.basename(self.PLAN), 'Measure sustained reliability.\n\nAwait the separately approved trial.\n\n' + original)
            os.remove(self.state['todo_path'])
            shutil.move(os.path.join(self.repo, source), os.path.join(self.repo, target))
        result = self.turn('parked', edit=relocate)
        self.assertEqual(worktrees.guard(self.repo, self.run_id), before)
        self.assertIn('SYNTHETIC_ORDER_7', open(os.path.join(self.repo, target, 'fixtures/sample.txt'), encoding='utf-8').read())
        self.host.reopen({'state': dict(self.state, final_tree=result['final_tree'])})
        self.assertTrue(os.path.isfile(os.path.join(self.repo, source, 'reproduce.py')))
        self.assertFalse(os.path.isfile(os.path.join(self.repo, target, 'reproduce.py')))

    def test_companion_collision_is_detected_before_the_agent_starts(self):
        self.write(self.PLAN[:-3] + '/README.md', 'Reviewed materials\n')
        self.state['verified_tree'] = worktrees.work_tree(self.repo)
        self.write(self.DONE[:-3] + '/README.md', 'Another existing folder\n')
        with self.assertRaisesRegex(ApplicationError, 'collision'):
            self.turn('completed')
        self.assertEqual(self.prompts, [])

    def test_reviewed_materials_cannot_be_rewritten_even_when_documents_allow_them(self):
        source = self.PLAN[:-3]
        self.write(source + '/README.md', 'Reviewed evidence\n')
        self.state['verified_tree'] = worktrees.work_tree(self.repo)
        with self.assertRaises(ApplicationError):
            self.turn(edit=lambda: self.write(source + '/README.md', 'Rewritten after review\n'), closeout_docs=['**/*.md'])

    def test_an_ignored_material_destination_cannot_produce_a_final_tree(self):
        source = self.PLAN[:-3]
        target = 'todo/parked/' + os.path.basename(source)
        self.write(source + '/README.md', 'Required reviewed evidence\n')
        self.write('.gitignore', target + '/\n')
        self.state['verified_tree'] = worktrees.work_tree(self.repo)
        def relocate():
            original = open(self.state['todo_path'], encoding='utf-8').read()
            self.write('todo/parked/' + os.path.basename(self.PLAN), 'Measure sustained reliability.\n\nAwait the separately approved trial.\n\n' + original)
            os.remove(self.state['todo_path'])
            shutil.move(os.path.join(self.repo, source), os.path.join(self.repo, target))
        before = worktrees.guard(self.repo, self.run_id)
        with self.assertRaisesRegex(ApplicationError, 'ignored|materials'):
            self.turn('parked', edit=relocate)
        self.assertEqual(worktrees.guard(self.repo, self.run_id), before)

    def test_materials_are_retained_for_active_work_and_completed_deletion_policy(self):
        source = self.PLAN[:-3]
        self.write(source + '/README.md', 'Reviewed incident record\n')
        self.state['verified_tree'] = worktrees.work_tree(self.repo)
        self.assertIn('final_tree', self.turn('active'))
        result = self.turn('completed', edit=lambda: os.remove(self.state['todo_path']), todo_done_dir=None)
        self.assertIsNone(result['todo_closeout']['path'])
        self.assertTrue(os.path.isfile(os.path.join(self.repo, source, 'README.md')))

    def test_other_todos_are_protected_even_when_documents_allow_all_markdown(self):
        self.write('todo/other.md', 'Other task\n')
        self.state['verified_tree'] = worktrees.work_tree(self.repo)
        with self.assertRaisesRegex(ApplicationError, 'todo/other.md'):
            self.turn('completed', edit=lambda: (
                self.write(self.DONE, 'Done\n'), os.remove(self.state['todo_path']), self.write('todo/other.md', 'Changed\n')),
                closeout_docs=['**/*.md'])

    def test_unfinished_work_cannot_be_deleted_or_shortened(self):
        for bad in ('delete', 'shorten'):
            self.write(self.PLAN, 'Original acceptance\n- [ ] Run the live trial\n')
            with self.subTest(bad=bad), self.assertRaisesRegex(ApplicationError, 'todo|unfinished'):
                self.turn(edit=lambda: os.remove(self.state['todo_path']) if bad == 'delete' else self.write(self.PLAN, 'All fine\n'))

    def test_new_remaining_work_cannot_exist_only_in_the_final_product(self):
        self.write(self.PLAN, '**Status:** verified increment\n- [x] Existing acceptance completed\n')
        self.state['verified_tree'] = worktrees.work_tree(self.repo)
        with self.assertRaisesRegex(ApplicationError, 'remaining'):
            self.turn(edit=lambda: None, product={'disposition': 'active',
                'remaining': 'Run a newly identified acceptance trial.', 'reason': ''})

    def test_existing_remaining_criteria_need_no_duplicate_preamble(self):
        original = 'Original acceptance\n- [ ] Measure sustained reliability.\n'
        self.write(self.PLAN, original)
        self.state['verified_tree'] = worktrees.work_tree(self.repo)
        self.turn(edit=lambda: None)
        self.assertEqual(open(self.state['todo_path'], encoding='utf-8').read(), original)

    def test_multiline_remaining_work_matches_windows_newlines_without_rewriting_the_todo(self):
        original = 'Original acceptance\r\n- [ ] Measure sustained reliability.\r\n- [ ] Resume after approval.\r\n'
        self.write(self.PLAN, original)
        self.state['verified_tree'] = worktrees.work_tree(self.repo)
        self.turn(edit=lambda: None, product={'disposition': 'active',
            'remaining': '- [ ] Measure sustained reliability.\n- [ ] Resume after approval.', 'reason': ''})
        with open(self.state['todo_path'], 'rb') as artifact:
            self.assertEqual(artifact.read(), original.encode('utf-8'))

    def test_parked_outcome_keeps_the_resume_reason_in_the_actual_todo(self):
        original = open(self.state['todo_path'], encoding='utf-8').read()
        destination = 'todo/parked/' + os.path.basename(self.PLAN)
        with self.assertRaisesRegex(ApplicationError, 'reason'):
            self.turn('parked', edit=lambda: (self.write(destination, 'Measure sustained reliability.\n\n' + original),
                                             os.remove(self.state['todo_path'])))

    def test_invalid_and_duplicate_products_do_not_produce_a_final_tree(self):
        for product in ({}, {'disposition': 'active', 'remaining': '', 'reason': ''},
                        {'disposition': 'completed', 'remaining': 'Still required', 'reason': ''},
                        {'disposition': '../other', 'remaining': 'Pending', 'reason': 'Blocked'}):
            with self.subTest(product=product), self.assertRaises(ApplicationError):
                self.turn(product=product)
        with self.assertRaisesRegex(ApplicationError, 'duplicate|exactly one|collision'):
            self.turn(edit=lambda: self.write(self.DONE, 'Duplicate task\n'))

    def test_verified_finished_location_is_given_to_the_agent_and_restored_on_revision(self):
        original = open(self.state['todo_path'], encoding='utf-8').read()
        self.write(self.DONE, original)
        os.remove(self.state['todo_path'])
        self.state['verified_tree'] = worktrees.work_tree(self.repo)
        result = self.turn('backlog', edit=lambda: (
            self.write('todo/backlog/' + os.path.basename(self.PLAN), 'Measure sustained reliability.\n\nAwait the separately approved trial.\n\n' + original), os.remove(os.path.join(self.repo, self.DONE))))
        self.assertIn(os.path.join(self.repo, *self.DONE.split('/')), self.prompts[0])
        self.host.reopen({'state': dict(self.state, final_tree=result['final_tree'], todo_closeout=result['todo_closeout'])})
        self.assertTrue(os.path.isfile(os.path.join(self.repo, self.DONE)))
        self.assertFalse(os.path.exists(os.path.join(self.repo, result['todo_closeout']['path'])))

    def test_partial_closeout_continues_at_its_declared_location_without_losing_steps(self):
        original = open(self.state['todo_path'], encoding='utf-8').read()
        destination = 'todo/parked/' + os.path.basename(self.PLAN)
        self.write(destination, 'Measure sustained reliability.\n\nAwait the separately approved trial.\n\n' + original)
        os.remove(self.state['todo_path'])
        result = self.turn('parked', edit=lambda: None)
        self.assertEqual(result['todo_closeout']['path'], destination)

    def test_deletion_policy_only_deletes_completed_work(self):
        result = self.turn('completed', edit=lambda: os.remove(self.state['todo_path']), todo_done_dir=None)
        self.assertIsNone(result['todo_closeout']['path'])
        self.write(self.PLAN, 'Original acceptance\n')
        with self.assertRaises(ApplicationError):
            self.turn('active', edit=lambda: os.remove(self.state['todo_path']), todo_done_dir=None)

    def test_invalid_or_colliding_directories_refuse_before_starting_an_agent(self):
        for folder in ('../escape', '/absolute', 'todo/*', 'todo/done'):
            with self.subTest(folder=folder), self.assertRaises(ApplicationError):
                self.turn(todo_parked_dir=folder)
            self.assertEqual(self.prompts, [])
        with self.assertRaisesRegex(ApplicationError, 'no enabled'):
            self.turn('backlog', todo_backlog_dir=None)

    def test_existing_destination_collision_refuses_before_the_agent_can_overwrite_it(self):
        self.write(self.DONE, 'Another file created after verification\n')
        with self.assertRaisesRegex(ApplicationError, 'collision|exactly one'):
            self.turn('completed')
        self.assertEqual(self.prompts, [])

    def test_explicit_name_recovery_recognizes_parked_artifacts_without_moving_them(self):
        self.state.update(closeout_version=1, todo_parked_dir='todo/parked', todo_backlog_dir='todo/backlog')
        self.write('todo/parked/renamed.md', 'Verified renamed task\n')
        os.remove(self.state['todo_path'])
        self.state['verified_tree'] = worktrees.work_tree(self.repo)
        before = worktrees.work_tree(self.repo), worktrees.guard(self.repo, self.run_id)
        host = activities.Activities(git=worktrees, telemetry=None)
        adopted = host.adopt_todo_name({'state': self.state, 'name': 'renamed.md'})
        self.assertEqual(adopted['plan'], 'todo/renamed.md')
        self.assertEqual(adopted['todo_path'], os.path.join(self.repo, 'todo', 'parked', 'renamed.md'))
        self.assertEqual((worktrees.work_tree(self.repo), worktrees.guard(self.repo, self.run_id)), before)

    def test_reopen_for_each_disposition_restores_the_verified_todo_and_preserves_later_edits(self):
        for disposition in ('active', 'parked', 'backlog', 'completed'):
            with self.subTest(disposition=disposition):
                self.write(self.PLAN, 'All original acceptance\n')
                self.state['verified_tree'] = worktrees.work_tree(self.repo)
                result = self.turn(disposition)
                self.write('docs/later.md', 'Operator edit after closeout\n')
                self.host.reopen({'state': dict(self.state, final_tree=result['final_tree'], todo_closeout=result['todo_closeout'])})
                self.assertEqual(open(self.state['todo_path'], encoding='utf-8').read(), 'All original acceptance\n')
                self.assertEqual(open(os.path.join(self.repo, 'docs/later.md'), encoding='utf-8').read(), 'Operator edit after closeout\n')


class LongPrompt(unittest.TestCase):
    """A turn given guidance longer than a command line takes — an audit pasted whole — still starts: the
    guidance is attached as a file in the run's own folder, which the agent may read, and the prompt names it."""

    def setUp(self):
        self.run_id = "test-activities-%s" % os.urandom(4).hex()
        self.addCleanup(shutil.rmtree, activities.run_dir(self.run_id), True)
        self.addCleanup(terminal.close_run, self.run_id)

    def test_each_kinds_turn_starts_with_the_long_guidance_attached(self):
        guidance = "".join("line %d of an audit pasted whole, \"PATCH\" and all\n" % n for n in range(1500))
        notes = [{"stop": "r:1", "phase": "plan", "action": "guide", "role": "engineer", "text": guidance}]
        for kind in SHIPPED:
            given = []
            adapter = adapters.load(kind)

            def runner(worktree, argv, rdir, name, prompt, timeout, env, *, kind):
                given.append((argv, prompt))
                return 0, adapter.output("planned", "s1")
            with self.subTest(kind=kind):
                host = activities.Activities(runner=runner, git=FakeWorktrees(), telemetry=None)
                host.run_role({"stage": "plan", "state": dict(state(self.run_id), operator_notes=notes),
                               "policy": policy(kind)})
                argv, prompt = given[0]
                folder = os.path.join(activities.run_dir(self.run_id), "attachments")
                path = os.path.join(folder, "plan-e1-1-guidance.md")
                self.assertLessEqual(N.cost(prompt), N.PROMPT_BUDGET)
                self.assertIn(path, prompt)
                with open(path, encoding="utf-8", newline="") as fh:
                    self.assertEqual(json.loads(fh.read().split("\n\n", 1)[1]), notes,
                                     "every original byte and provenance field survive the JSON attachment")
                if kind == "claude-code":
                    rule = adapter.read_rule(os.path.realpath(folder))
                    self.assertEqual(argv[argv.index(rule) - 1], "--allowedTools",
                                     "a folder Claude reads without approval")
                    self.assertNotIn(os.path.realpath(folder), argv,
                                     "never a working directory, which would keep the agent's cd into it")


def stand_in_output():
    return json.dumps({"thread": "s1", "answer": "planned"}) + "\n"


if __name__ == "__main__":
    unittest.main()
