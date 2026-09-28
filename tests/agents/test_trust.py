"""What a run records so its agents are not stopped by a trust dialog, and what it never touches.

The dialogs themselves are the vendors'; that a record silences one is measured against the real
CLIs in the acceptance, not here. These tests own the writing: the right key, the operator's own
file kept, nothing written twice, and a failure that costs a dialog rather than a run.
"""
import json
import os
import sys
import tempfile
import unittest

# The suite's own folder, reached from this concern's folder inside it, and the
# checkout above both: the shared harness and the fixtures live at the suite root.
HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path[:0] = [PKG, HERE]

from app.agents import trust  # noqa: E402
from app.agents.adapters import claude_code, codex  # noqa: E402

REPO = os.path.abspath(PKG)          # a repository that really is on this host


class Home(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="orchestra-trust-")
        self.addCleanup(__import__("shutil").rmtree, self.home, True)

    def claude(self):
        with open(os.path.join(self.home, claude_code.CONFIG_FILE), encoding="utf-8") as fh:
            return json.load(fh)

    def codex(self, text=None):
        path = os.path.join(self.home, codex.CONFIG_FILE)
        if text is not None:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            return None
        with open(path, encoding="utf-8") as fh:
            return fh.read()


class Recording(Home):
    def test_both_clis_are_told_once_and_the_operators_own_settings_are_kept(self):
        with open(os.path.join(self.home, claude_code.CONFIG_FILE), "w", encoding="utf-8") as fh:
            json.dump({"numStartups": 7, "projects": {"/other": {"hasTrustDialogAccepted": True,
                                                                 "history": ["keep me"]}}}, fh)
        self.codex("model = \"gpt-5.6-sol\"\n\n[projects.'/other']\ntrust_level = \"trusted\"\n")

        self.assertEqual(trust.ensure(REPO, ["claude-code", "codex"], self.home), ["claude-code", "codex"])
        config = self.claude()
        self.assertTrue(config["projects"][claude_code.trust_key(REPO)]["hasTrustDialogAccepted"])
        self.assertEqual(config["numStartups"], 7, "the rest of the file is the operator's")
        self.assertEqual(config["projects"]["/other"]["history"], ["keep me"])
        text = self.codex()
        self.assertIn("model = \"gpt-5.6-sol\"", text, "the config is appended to, never rewritten")
        self.assertIn("[projects.%s]" % codex.trust_key(REPO), text)
        self.assertIn("trust_level = \"trusted\"", text.split("[projects.%s]" % codex.trust_key(REPO))[1])

        self.assertEqual(trust.ensure(REPO, ["claude-code", "codex"], self.home), [],
                         "a repository already recorded is left alone")
        self.assertEqual(self.claude(), config)
        self.assertEqual(self.codex(), text)

    def test_the_key_is_the_spelling_that_hosts_cli_reads(self):
        trust.ensure(REPO, ["claude-code"], self.home)
        key, = [k for k in self.claude()["projects"]]
        if claude_code.WINDOWS:
            self.assertNotIn("\\", key, "measured: Windows Claude reads the forward-slash spelling")
            self.assertEqual(key, REPO.replace("\\", "/"))
        else:
            self.assertEqual(key, REPO)
        self.assertEqual(codex.trust_key(REPO), "'%s'" % REPO,
                         "a TOML literal string, so a Windows path keeps its backslashes")

    def test_a_repository_the_operator_already_trusts_is_not_recorded_again(self):
        # Windows folds case, so the same repository spelled differently is the same repository.
        spelled = REPO.upper() if codex.WINDOWS else REPO
        self.codex("[projects.'%s']\ntrust_level = \"trusted\"\n" % spelled)
        self.assertEqual(trust.ensure(REPO, ["codex"], self.home), [])
        self.assertEqual(self.codex().count("[projects."), 1)

    def test_a_repository_the_operator_marked_untrusted_is_left_exactly_as_it_is(self):
        # Codex keeps `untrusted` as a real decision; a second table with the same key is invalid TOML.
        self.codex("[projects.'%s']\ntrust_level = \"untrusted\"\n\n[features]\nhooks = true\n" % REPO)
        self.assertEqual(trust.ensure(REPO, ["codex"], self.home), [])
        text = self.codex()
        self.assertEqual(text.count("[projects."), 1, "never a second table for a key already there")
        self.assertIn('trust_level = "untrusted"', text, "the operator's own decision stands")
        import tomllib
        self.assertEqual(tomllib.loads(text)["projects"][REPO]["trust_level"], "untrusted",
                         "and the config still parses")

    def test_a_project_the_config_holds_is_found_however_its_table_is_written(self):
        # Valid TOML the operator may have written by hand: a comment on the header, a quoted key.
        self.codex("[projects.'%s'] # the operator's own note\ntrust_level = \"untrusted\"\n" % REPO)
        self.assertEqual(trust.ensure(REPO, ["codex"], self.home), [])
        self.assertEqual(self.codex().count("[projects."), 1, "never a second table for a key already there")
        import tomllib
        self.assertEqual(tomllib.loads(self.codex())["projects"][REPO]["trust_level"], "untrusted")

    def test_nothing_is_written_for_a_file_we_do_not_understand_and_no_failure_reaches_the_run(self):
        with open(os.path.join(self.home, claude_code.CONFIG_FILE), "w", encoding="utf-8") as fh:
            fh.write("not json at all")
        self.codex("[projects.'/other']\ntrust_level = \"trusted\"\nthis is not toml =\n")
        self.assertEqual(trust.ensure(REPO, ["claude-code", "codex"], self.home), [])
        with open(os.path.join(self.home, claude_code.CONFIG_FILE), encoding="utf-8") as fh:
            self.assertIn("not json at all", fh.read(), "a file we do not understand is left as it is")
        self.assertNotIn("example", self.codex(), "an unreadable config is not appended to")

    def test_a_repository_that_is_not_on_this_host_is_never_recorded(self):
        # A test's fake path, or a descriptor for another machine: the operator's config stays clean.
        self.assertEqual(trust.ensure(os.path.join(self.home, "not-here"), ["claude-code", "codex"], self.home), [])
        self.assertFalse(os.path.exists(os.path.join(self.home, claude_code.CONFIG_FILE)))
        self.assertFalse(os.path.exists(os.path.join(self.home, codex.CONFIG_FILE)))

    def test_an_unknown_kind_and_an_unusable_home_change_nothing(self):
        self.assertEqual(trust.ensure(REPO, ["deepseek"], self.home), [])
        self.assertFalse(os.listdir(self.home))
        blocked = os.path.join(self.home, "file-not-a-directory")
        with open(blocked, "w", encoding="utf-8") as fh:
            fh.write("x")
        self.assertEqual(trust.ensure(REPO, ["claude-code", "codex"], blocked), [],
                         "a record that cannot be written costs a dialog, never the run")



class Forgetting(Home):
    """What a probe or an acceptance takes back: its own records, and nothing that merely looks like them."""

    def test_only_this_repositorys_own_records_go_and_the_rest_of_the_file_is_untouched(self):
        near = os.path.join(REPO, "tools")        # a real directory whose key starts with ours
        self.codex("model = \"gpt-5.6-sol\"\n")
        self.assertEqual(trust.ensure(REPO, ["claude-code", "codex"], self.home), ["claude-code", "codex"])
        # Tables of someone else's directly after ours: a block ends at the next header, whatever it is.
        with open(os.path.join(self.home, codex.CONFIG_FILE), "a", encoding="utf-8", newline="\n") as fh:
            fh.write("\n[features]\nhooks = true\n\n[hooks.state]\nkeep = \"me\"\n")
        self.assertEqual(trust.ensure(near, ["claude-code", "codex"], self.home), ["claude-code", "codex"])

        self.assertEqual(trust.forget(REPO, ["claude-code", "codex"], self.home), ["claude-code", "codex"])

        text = self.codex()
        self.assertNotIn("[projects.%s]" % codex.trust_key(REPO), text, "our own record is gone")
        self.assertIn("[projects.%s]" % codex.trust_key(near), text, "a repository of a similar name stays")
        self.assertIn("[features]\nhooks = true", text, "and every table after ours survives")
        self.assertIn("[hooks.state]\nkeep = \"me\"", text)
        self.assertIn("model = \"gpt-5.6-sol\"", text)
        import tomllib
        self.assertEqual(sorted(tomllib.loads(text)), ["features", "hooks", "model", "projects"])
        projects = self.claude()["projects"]
        self.assertNotIn(claude_code.trust_key(REPO), projects)
        self.assertIn(claude_code.trust_key(near), projects, "and so does its Claude entry")

    def test_what_is_no_longer_ours_is_left_alone(self):
        self.codex("[projects.%s]\ntrust_level = \"untrusted\"\n" % codex.trust_key(REPO))
        with open(os.path.join(self.home, claude_code.CONFIG_FILE), "w", encoding="utf-8") as fh:
            json.dump({"projects": {claude_code.trust_key(REPO): {"hasTrustDialogAccepted": True,
                                                             "history": ["the CLI's own"]}}}, fh)
        self.assertEqual(trust.forget(REPO, ["codex"], self.home), [],
                         "an untrusted decision is the operator's, not a record of ours")
        self.assertIn('trust_level = "untrusted"', self.codex())
        self.assertEqual(trust.forget(REPO, ["claude-code"], self.home), ["claude-code"])
        entry = self.claude()["projects"][claude_code.trust_key(REPO)]
        self.assertEqual(entry, {"history": ["the CLI's own"]},
                         "the trust goes; what the CLI wrote in that entry stays")

    def test_a_record_that_was_never_written_is_not_reported_as_removed(self):
        self.assertEqual(trust.forget(REPO, ["claude-code", "codex"], self.home), [])


class Stores(unittest.TestCase):
    """Where each CLI keeps its record when its home is named by the environment."""

    def test_codex_home_and_claude_config_dir_are_honoured(self):
        moved = tempfile.mkdtemp(prefix="orchestra-trust-home-")
        self.addCleanup(__import__("shutil").rmtree, moved, True)
        saved = {name: os.environ.get(name) for name in ("CODEX_HOME", "CLAUDE_CONFIG_DIR")}
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
                                 for k, v in saved.items()])
        os.environ["CODEX_HOME"] = moved
        self.assertEqual(codex.config_path(), os.path.join(moved, "config.toml"),
                         "CODEX_HOME names the root that holds the config")
        os.environ["CLAUDE_CONFIG_DIR"] = moved
        # Measured against the installed CLI: given an empty directory, it makes `.claude.json` there.
        self.assertEqual(claude_code.config_path(), os.path.join(moved, claude_code.CONFIG_FILE),
                         "the record belongs in the configuration home, whether or not the file is there yet")


class Wiring(unittest.TestCase):
    """The run records it, on the host that will run the agents, before any of them starts."""

    def test_preparing_a_run_records_its_repository_for_the_kinds_it_will_use(self):
        from app.application import activities
        from app.application import settings as S
        from fakes import FakeRepos, FakeWorktrees, every_skill, installed
        recorded = []
        saved = trust.ensure
        trust.ensure = lambda repo, kinds, home=None: recorded.append((repo, sorted(set(kinds))))
        self.addCleanup(setattr, trust, "ensure", saved)
        host = activities.Activities(runner=None, git=None, repositories=FakeRepos(), telemetry=None,
                                     which=installed, holds_skill=every_skill)
        resolved = host.prepare({"repository": {"id": "example", "target": "wsl", "path": "/x"},
                                 "policy": S.run_policy(S.load())})
        self.assertEqual(recorded, [(resolved["repo_path"], ["claude-code", "codex"])])

        # And again before each turn, because a record written while a CLI runs can be taken back.
        recorded.clear()
        policy = S.run_policy(S.load())
        state = {"run_id": "r1", "task": "t", "phase": "plan", "round": 0, "episode": 1,
                 "repo_path": resolved["repo_path"], "worktree_path": "/fake/worktree",
                 "todo_path": "/fake/worktree/todo/x.md", "agent_sessions": {}}
        host = activities.Activities(runner=lambda *args, **kwargs: (1, ""), git=FakeWorktrees(), telemetry=None)
        with self.assertRaises(Exception):
            host.run_role({"stage": "plan", "state": state, "policy": policy})
        self.assertEqual(recorded, [(resolved["repo_path"], ["claude-code"])],
                         "for the kind whose turn it is, before that turn starts")

if __name__ == "__main__":
    unittest.main()
