"""The settings' files and shape, and a role's persona file, which has one resolver.

Settings name a persona file from the checkout's root, and the host starting a run reads it into the
run's policy, so the host running the role never resolves a path. A run started before agent profiles
carries a path and where its policy was loaded, and the host running its role resolves that path the
way such runs always did — refusing an origin only the other host can spell.
"""
import ast
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

# The suite's own folder, reached from this concern's folder inside it, and the
# checkout above both: the shared harness and the fixtures live at the suite root.
HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path[:0] = [PKG, HERE]

from app.foundation import paths  # noqa: E402
from app.foundation import policy as P  # noqa: E402

SETTINGS = """{
  "agents": {"builder": {"kind": "claude-code"}, "judge": {"kind": "codex", "model": "m", "effort": "high"}},
  "roles": {
    "engineer": {"agent": "builder", "persona_file": "roles/engineer.md"},
    "architect": {"agent": "judge", "persona_file": "roles/architect.md"}
  },
  "max_rounds": {"plan": 2, "build": 2},
  "auto_proceed": false,
  "timeout_seconds": 60,
  "heartbeat_seconds": 30,
  "workflow_queue": "orchestration:other",
  "workbench_port": 8390,
  "targets": {"wsl": {"host": "local", "worktree_root": "/tmp", "terminal_port": 8401},
              "windows": {"host": "local", "worktree_root": "C:\\\\tmp", "terminal_port": 8402}},
  "target_repo": {"commit_allowed": false, "push_allowed": false, "merge_allowed": false}
}
"""
# A run's policy as a run started before agent profiles carries it: a brain, a path to a persona file,
# the access it stored, and where the policy it was made from was loaded.
OLD_RUN = {"roles": {"engineer": {"brain": "claude", "workspace_access": "write", "prompt": "roles/engineer.md"},
                     "architect": {"brain": "codex", "workspace_access": "read", "prompt": "roles/architect.md"}},
           "_policy_path": "policy.json"}


def settings_file(root, text=SETTINGS, personas=True):
    """A settings file under `root`, with persona files of its own beside it that it does not name."""
    if personas:
        os.makedirs(os.path.join(root, "roles"), exist_ok=True)
        for role in P.ROLES:
            with open(os.path.join(root, "roles", "%s.md" % role), "w", encoding="utf-8") as fh:
                fh.write("# the %s beside these settings\n" % role)
    path = os.path.join(root, "settings.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


# How the other host spells an absolute path: what a policy loaded there would carry across.
OTHER_HOSTS_PATH = ("/mnt/e/elsewhere/policy.json" if sys.platform.startswith("win")
                    else "E:\\elsewhere\\policy.json")


class OneResolver(unittest.TestCase):
    def test_a_persona_file_resolves_from_the_checkout_root_wherever_the_settings_are(self):
        with tempfile.TemporaryDirectory() as root:
            loaded = P.load(settings_file(root))
            self.assertEqual(P.prompt_path(loaded, "engineer"),
                             os.path.normpath(os.path.join(paths.REPO, "roles", "engineer.md")))
            # The control: the settings' own folder holds a file of that name too, which is not the one.
            self.assertTrue(os.path.isfile(os.path.join(root, "roles", "engineer.md")))

    def test_an_old_runs_persona_resolves_beside_the_policy_it_was_made_from(self):
        """A run started before agent profiles resolves its path as those runs did: against its origin."""
        with tempfile.TemporaryDirectory() as root:
            settings_file(root)
            old = dict(OLD_RUN, _policy_path=os.path.join(root, "policy.json"))
            self.assertEqual(P.prompt_path(old, "engineer"), os.path.join(root, "roles", "engineer.md"))
            self.assertEqual(P.prompt_path(OLD_RUN, "engineer"),
                             os.path.normpath(os.path.join(paths.REPO, "roles", "engineer.md")),
                             "the deployment's own: its origin read against this host's checkout")

    def test_the_shipped_workflow_queue_is_the_one_its_runs_were_started_on(self):
        """Runs started before the queue became the settings' are on `orchestration`: renamed, no worker
        would poll them again."""
        self.assertEqual(P.workflow_queue(P.load(P.SETTINGS_FILE)), "orchestration")

    def test_an_absolute_persona_file_is_left_alone(self):
        with tempfile.TemporaryDirectory() as root:
            loaded = P.load(settings_file(root))
            absolute = os.path.abspath(os.path.join(root, "roles", "architect.md"))
            loaded["roles"]["architect"]["persona_file"] = absolute
            self.assertEqual(P.prompt_path(loaded, "architect"), absolute)

    def test_a_persona_that_is_not_there_is_refused_naming_its_setting(self):
        loaded = P.load(P.SETTINGS_FILE)
        loaded["roles"]["engineer"] = dict(loaded["roles"]["engineer"], persona_file="roles/nobody.md")
        with self.assertRaises(P.InvalidPolicy) as raised:
            P.prompt_path(loaded, "engineer")
        self.assertIn("nobody.md", str(raised.exception))
        self.assertEqual(raised.exception.pointer, "/roles/engineer/persona_file")


class TheOriginCrossesHosts(unittest.TestCase):
    """Where settings came from, and what an old run's policy carries, must be readable on the host that
    runs the role."""

    def test_settings_inside_the_checkout_carry_a_name_relative_to_it(self):
        loaded = P.load(P.SETTINGS_FILE)
        self.assertEqual(loaded["_policy_path"], ".orchestra/settings.json")
        # Neither host's spelling of the checkout crosses: that was the defect.
        self.assertIsNone(P.ABSOLUTE_ANYWHERE.match(loaded["_policy_path"]))

    def test_an_old_runs_relative_origin_is_read_against_this_hosts_checkout(self):
        os.makedirs(paths.RUNTIME_ROOT, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=paths.RUNTIME_ROOT) as root:
            settings_file(root)
            relative = os.path.relpath(root, paths.REPO).replace(os.sep, "/")
            old = dict(OLD_RUN, _policy_path=relative + "/policy.json")
            self.assertEqual(P.prompt_path(old, "engineer"),
                             os.path.normpath(os.path.join(root, "roles", "engineer.md")))
            # The control: the checkout's own persona is another file, so a resolver that fell back to it
            # would fail here.
            self.assertNotEqual(P.prompt_path(old, "engineer"), P.prompt_path(OLD_RUN, "engineer"))

    def test_an_old_runs_origin_only_the_other_host_can_read_is_refused(self):
        with self.assertRaises(P.InvalidPolicy) as raised:
            P.prompt_path(dict(OLD_RUN, _policy_path=OTHER_HOSTS_PATH), "engineer")
        self.assertIn("other host", str(raised.exception))

    def test_this_hosts_settings_are_the_ones_orchestra_settings_names(self):
        """What the page, the command line and the workers each load when none is named."""
        with tempfile.TemporaryDirectory() as root:
            mine = settings_file(root)
            with mock.patch.dict(os.environ, {P.VARIABLE: mine}):
                self.assertEqual(P.load()["_policy_path"], os.path.abspath(mine))
        # Named by nothing: the checkout's shared settings, with its local patch — never read here, since it is
        # the operator's own.
        self.assertEqual(P.sources(environ={}), (P.SETTINGS_FILE, P.LOCAL_FILE))


class Shape(unittest.TestCase):
    """What a settings file holds, refused by the JSON Pointer of what is wrong."""

    def raw(self):
        return json.loads(SETTINGS)

    def test_the_shipped_settings_bind_role_profiles_and_stage_methodologies(self):
        loaded = P.load(P.SETTINGS_FILE)
        self.assertEqual({role: settings["agent"] for role, settings in loaded["roles"].items()},
                         {"engineer": "claude-engineer", "architect": "claude-architect"})
        self.assertEqual(set(loaded["agents"]),
                         {"claude-engineer", "claude-architect", "codex-engineer", "codex-architect"})
        self.assertEqual(loaded["stage_skills"], {
            "research": "architect", "plan": "investigate-change", "assess": "architect",
            "build": "implement-approved-change", "verify": "architect"})

    def test_review_rounds_have_normal_and_extended_budgets_and_old_settings_still_load(self):
        raw = self.raw()
        raw.pop("max_rounds")
        raw["review_rounds"] = {phase: {"normal": 10, "extended": 10} for phase in P.stages.PHASES}
        P.validate(raw)
        for phase, threshold, value in (("plan", "normal", 0), ("build", "extended", -1),
                                        ("plan", "extended", True)):
            broken = json.loads(json.dumps(raw))
            broken["review_rounds"][phase][threshold] = value
            with self.subTest(phase=phase, threshold=threshold, value=value), self.assertRaises(P.InvalidPolicy) as raised:
                P.validate(broken)
            self.assertEqual(raised.exception.pointer, "/review_rounds/%s/%s" % (phase, threshold))
        legacy = self.raw()
        legacy.pop("review_prompts", None)
        P.validate(legacy)

    def test_review_prompt_additions_are_role_specific_and_bounded_together(self):
        raw = self.raw()
        raw["review_prompts"] = {
            event: {role: "" for role in P.ROLES} for event in ("after_normal", "at_limit")
        }
        raw["review_prompts"]["after_normal"]["engineer"] = "Check the work and findings."
        P.validate(raw)

        missing_role = json.loads(json.dumps(raw))
        del missing_role["review_prompts"]["at_limit"]["architect"]
        with self.assertRaises(P.InvalidPolicy) as raised:
            P.validate(missing_role)
        self.assertEqual(raised.exception.pointer, "/review_prompts/at_limit")

        within_limit = json.loads(json.dumps(raw))
        within_limit["review_prompts"]["after_normal"]["engineer"] = "é" * (P.MAX_REVIEW_PROMPT_BYTES // 2)
        P.validate(within_limit)

        too_long = json.loads(json.dumps(within_limit))
        too_long["review_prompts"]["at_limit"]["architect"] = "x"
        with self.assertRaises(P.InvalidPolicy) as raised:
            P.validate(too_long)
        self.assertEqual(raised.exception.pointer, "/review_prompts/at_limit/architect")

        not_text = json.loads(json.dumps(raw))
        not_text["review_prompts"]["at_limit"]["engineer"] = False
        with self.assertRaises(P.InvalidPolicy) as raised:
            P.validate(not_text)
        self.assertEqual(raised.exception.pointer, "/review_prompts/at_limit/engineer")

    def test_settings_of_the_old_shape_are_refused_naming_the_new_keys(self):
        old = self.raw()
        old.pop("agents")
        old["roles"] = {name: {"brain": "claude", "workspace_access": access, "prompt": "roles/%s.md" % name}
                        for name, access in P.ROLE_ACCESS.items()}
        with self.assertRaises(P.InvalidPolicy) as raised:
            P.validate(old)
        for key in ("agents", "kind", "agent", "persona_file"):
            self.assertIn("`%s`" % key, str(raised.exception))

    def test_a_skill_is_a_name_by_the_agent_skills_rule(self):
        for good in ("investigate-change", "a", "x" * P.SKILL_NAME_MAX, "v2-review"):
            raw = dict(self.raw(), stage_skills={"plan": good})
            P.validate(raw)
        for bad in ("/investigate-change", "$architect", "Investigate", "-x", "x-", "a--b", "", "x" * 65, 7):
            raw = dict(self.raw(), stage_skills={"plan": bad})
            with self.assertRaises(P.InvalidPolicy, msg=repr(bad)) as raised:
                P.validate(raw)
            self.assertEqual(raised.exception.pointer, "/stage_skills/plan")

    def test_a_role_names_a_profile_and_takes_nothing_else(self):
        raw = self.raw()
        raw["roles"]["architect"]["agent"] = "nobody"
        with self.assertRaises(P.InvalidPolicy) as raised:
            P.validate(raw)
        self.assertEqual(raised.exception.pointer, "/roles/architect/agent")
        raw = self.raw()
        raw["roles"]["architect"]["workspace_access"] = "write"
        with self.assertRaises(P.InvalidPolicy) as raised:
            P.validate(raw)
        self.assertEqual(raised.exception.pointer, "/roles/architect/workspace_access")

    def test_a_profile_is_named_and_names_its_kind(self):
        for name, profile, where in (("Bad Name", {"kind": "codex"}, "/agents/Bad Name"),
                                     ("ok", {"model": "m"}, "/agents/ok/kind"),
                                     ("ok", {"kind": "Codex"}, "/agents/ok/kind"),
                                     ("a/b", {"kind": "codex"}, "/agents/a~1b")):
            raw = self.raw()
            raw["agents"][name] = profile
            with self.assertRaises(P.InvalidPolicy, msg=name) as raised:
                P.validate(raw)
            self.assertEqual(raised.exception.pointer, where)

    def test_the_persona_text_takes_the_files_place(self):
        raw = self.raw()
        raw["roles"]["engineer"] = {"agent": "builder", "persona": "Build it small."}
        self.assertEqual(P.persona(P.validate(raw), "engineer"), "Build it small.")
        raw = self.raw()
        raw["roles"]["engineer"]["persona"] = "Mine."
        self.assertEqual(P.persona(P.validate(raw), "engineer"), "Mine.", "the text wins over the file")
        raw = self.raw()
        del raw["roles"]["engineer"]["persona_file"]
        with self.assertRaises(P.InvalidPolicy) as raised:
            P.validate(raw)
        self.assertEqual(raised.exception.pointer, "/roles/engineer")

    def test_a_persona_is_bounded_by_its_bytes_of_utf8(self):
        raw = self.raw()
        raw["roles"]["engineer"]["persona"] = "x" * P.MAX_PERSONA_BYTES
        P.validate(raw)
        # Two bytes each: fewer characters than the bound, and one byte past it.
        raw["roles"]["engineer"]["persona"] = "\u00e9" * (P.MAX_PERSONA_BYTES // 2) + "x"
        with self.assertRaises(P.InvalidPolicy) as raised:
            P.validate(raw)
        self.assertEqual(raised.exception.pointer, "/roles/engineer/persona")
        self.assertIn("engineer", str(raised.exception))

    def test_a_pointer_escapes_what_rfc_6901_escapes(self):
        self.assertEqual(P.pointer("agents", "a/b~c", "model"), "/agents/a~1b~0c/model")


class Layers(unittest.TestCase):
    """The checkout's shared settings with the operator's local patch over them, or one file, named, alone."""

    def checkout(self, patch=None, shared=SETTINGS):
        root = tempfile.mkdtemp(prefix="orchestra-layers-")
        self.addCleanup(__import__("shutil").rmtree, root, True)
        os.makedirs(os.path.join(root, ".orchestra"))
        with open(os.path.join(root, ".orchestra", "settings.json"), "w", encoding="utf-8") as fh:
            fh.write(shared)
        if patch is not None:
            with open(os.path.join(root, ".orchestra", "settings.local.json"), "w", encoding="utf-8") as fh:
                fh.write(patch if isinstance(patch, str) else json.dumps(patch))
        return root

    def test_a_patch_merges_objects_replaces_everything_else_and_removes_by_null(self):
        self.assertEqual(P.merge({"a": [1, 2], "b": {"c": 1, "d": 2}, "e": 1}, {"a": [3], "b": {"d": None, "f": 4}}),
                         {"a": [3], "b": {"c": 1, "f": 4}, "e": 1})
        shared = json.loads(SETTINGS)
        shared["agents"]["spare"] = {"kind": "codex"}
        root = self.checkout({"agents": {"judge": {"model": "other"}, "spare": None}, "max_rounds": {"plan": 3}},
                             shared=json.dumps(shared))
        loaded = P.load(root=root, environ={})
        self.assertEqual(loaded["agents"], {"builder": {"kind": "claude-code"},
                                            "judge": {"kind": "codex", "model": "other", "effort": "high"}},
                         "a shipped profile removed, another's model changed and the rest kept")
        self.assertEqual(loaded["max_rounds"], {"plan": 3, "build": 2})

    def test_the_result_is_validated_whole_and_a_patch_that_breaks_it_is_named(self):
        root = self.checkout({"roles": {"architect": {"agent": "nobody"}}})
        with self.assertRaises(P.InvalidPolicy) as raised:
            P.load(root=root, environ={})
        self.assertIn("settings.local.json", str(raised.exception))
        self.assertEqual(raised.exception.pointer, "/roles/architect/agent")
        with self.assertRaisesRegex(P.InvalidPolicy, "settings.local.json is not JSON"):
            P.load(root=self.checkout("{"), environ={})

    def test_the_named_file_is_taken_alone(self):
        root = self.checkout({"max_rounds": {"plan": 5}})
        with tempfile.TemporaryDirectory() as elsewhere:
            named = settings_file(elsewhere)
            loaded = P.load(root=root, environ={P.VARIABLE: named})
            self.assertEqual((loaded["max_rounds"]["plan"], loaded["_policy_path"]), (2, os.path.abspath(named)),
                             "no patch applied to it")

    def test_the_origin_is_the_file_below_the_patch(self):
        """So a patch never makes the deployment another stack."""
        root = self.checkout({"max_rounds": {"plan": 3}})
        self.assertEqual(P.load(root=root, environ={})["_policy_path"], ".orchestra/settings.json")

    def test_the_suite_reads_no_local_patch(self):
        self.assertIsNone(P.sources()[1], "the harness names the shared settings alone")
        # The control: without the harness's variable, the checkout's own patch is what would be read.
        self.assertEqual(P.sources(environ={})[1], P.LOCAL_FILE)

    def test_a_revision_changes_with_either_file_and_tells_absent_from_empty(self):
        root = self.checkout()
        below, local = P.sources(root=root, environ={})
        first = P.revision(below, local)
        self.assertEqual(P.revision(below, local), first)
        with open(local, "w", encoding="utf-8") as fh:
            fh.write("")
        empty = P.revision(below, local)
        self.assertNotEqual(empty, first)
        with open(local, "w", encoding="utf-8") as fh:
            fh.write("{}")
        self.assertNotIn(P.revision(below, local), (first, empty))
        with open(below, "a", encoding="utf-8") as fh:
            fh.write("\n")
        self.assertNotIn(P.revision(below, local), (first, empty))


class SparseEdit(unittest.TestCase):
    """An edit of the patch touches only the settings it is given."""

    BELOW = {"agents": {"a": {"kind": "x", "model": "m"}, "b": {"kind": "y"}}, "timeout_seconds": 60}

    def test_a_value_is_set_where_it_differs_and_nothing_else_is_copied_in(self):
        self.assertEqual(P.edited(self.BELOW, {"timeout_seconds": 90}, [{"pointer": "/agents/a/model", "value": "n"}]),
                         {"timeout_seconds": 90, "agents": {"a": {"model": "n"}}})

    def test_a_value_equal_to_the_one_below_leaves_the_patch(self):
        self.assertEqual(P.edited(self.BELOW, {"agents": {"a": {"model": "n"}}},
                                  [{"pointer": "/agents/a/model", "value": "m"}]), {})

    def test_a_whole_object_is_written_as_its_difference(self):
        self.assertEqual(P.edited(self.BELOW, {}, [{"pointer": "/agents/a", "value": {"kind": "x"}}]),
                         {"agents": {"a": {"model": None}}})
        self.assertEqual(P.edited(self.BELOW, {}, [{"pointer": "/agents/c", "value": {"kind": "z"}}]),
                         {"agents": {"c": {"kind": "z"}}})

    def test_removing_a_shipped_member_writes_null_and_one_of_the_patchs_own_goes(self):
        self.assertEqual(P.edited(self.BELOW, {}, [{"pointer": "/agents/b", "remove": True}]),
                         {"agents": {"b": None}})
        self.assertEqual(P.edited(self.BELOW, {"agents": {"c": {"kind": "z"}}},
                                  [{"pointer": "/agents/c", "remove": True}]), {})

    def test_revert_removes_that_member_alone_and_prunes_what_it_empties(self):
        patch = {"agents": {"a": {"model": "n"}}, "timeout_seconds": 90}
        self.assertEqual(P.edited(self.BELOW, patch, [{"pointer": "/agents/a/model", "revert": True}]),
                         {"timeout_seconds": 90})
        self.assertEqual(patch, {"agents": {"a": {"model": "n"}}, "timeout_seconds": 90}, "the patch given is untouched")

    def test_a_change_that_says_nothing_is_refused(self):
        with self.assertRaises(P.InvalidPolicy):
            P.edited(self.BELOW, {}, [{"pointer": "/timeout_seconds"}])
        with self.assertRaises(P.InvalidPolicy):
            P.edited(self.BELOW, {}, [{"pointer": "timeout_seconds", "value": 1}])


class TheTargetOpensItsOwnPersona(unittest.TestCase):
    """At the boundary that matters: the activity a target host runs, given the policy a client sent.

    The policy arrives as a Temporal payload — JSON, decoded on the host running this suite — and the
    agent is the runner seam, so no vendor CLI runs. A run carries its persona's text, which reaches the
    agent whatever this host holds; an old run's persona file this host cannot map starts no agent at all.
    """

    def setUp(self):
        from fakes import FakeWorktrees
        from app.application import activities
        self.activities, self.git = activities, FakeWorktrees()
        self.run_id = "persona-%s" % os.urandom(4).hex()
        self.addCleanup(lambda: __import__("shutil").rmtree(activities.run_dir(self.run_id), True))
        self.prompts = []

    def run_plan(self, policy):
        def agent(worktree, argv, rdir, name, prompt, timeout, env, kind=None):
            self.prompts.append(prompt)
            return 0, "planned\n"
        state = {"run_id": self.run_id, "task": "t", "phase": "plan", "round": 0, "episode": 1,
                 "worktree_path": "/fake/worktree", "todo_path": "/fake/worktree/todo/x.md",
                 "agent_sessions": {}}
        host = self.activities.Activities(runner=agent, git=self.git, telemetry=None)
        # What Temporal carries between the hosts: JSON, decoded here.
        return host.run_role({"stage": "plan", "state": state, "policy": json.loads(json.dumps(policy))})

    def test_a_runs_persona_text_reaches_the_agent(self):
        from app.application import settings
        sent = settings.run_policy(settings.load())
        sent["roles"]["engineer"]["persona"] = "A persona only this run carries."
        self.run_plan(sent)
        self.assertEqual(len(self.prompts), 1)
        self.assertIn("A persona only this run carries.", self.prompts[0])

    def test_an_old_runs_persona_file_reaches_the_agent(self):
        with open(os.path.join(paths.REPO, "roles", "engineer.md"), encoding="utf-8") as fh:
            persona = fh.readline().strip()
        self.run_plan(dict(OLD_RUN, timeout_seconds=60, max_rounds={"plan": 2, "build": 2}))
        self.assertEqual(len(self.prompts), 1)
        self.assertIn(persona, self.prompts[0])

    def test_an_old_runs_origin_only_the_client_can_read_starts_no_agent(self):
        sent = dict(OLD_RUN, timeout_seconds=60, max_rounds={"plan": 2, "build": 2}, _policy_path=OTHER_HOSTS_PATH)
        with self.assertRaises(Exception) as raised:
            self.run_plan(sent)
        self.assertIn("other host", str(raised.exception))
        self.assertEqual(self.prompts, [], "no agent started")


def prompt_path_writers(root):
    """Every module under `root` that assigns `prompt_path` without calling the resolver."""
    found = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(base, name)
            with open(path, encoding="utf-8") as handle:
                tree = ast.parse(handle.read(), filename=path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign):
                    continue
                for target in node.targets:
                    if not (isinstance(target, ast.Subscript)
                            and isinstance(target.slice, ast.Constant)
                            and target.slice.value == "prompt_path"):
                        continue
                    call = node.value
                    named = None
                    if isinstance(call, ast.Call):
                        named = (call.func.attr if isinstance(call.func, ast.Attribute)
                                 else getattr(call.func, "id", None))
                    # The resolver's own module calls it unqualified; still the one resolver.
                    resolved = named == "prompt_path"
                    if not resolved:
                        found.append((os.path.relpath(path, root).replace(os.sep, "/"),
                                      node.lineno))
    return sorted(found)


class NobodyElseBuildsThePath(unittest.TestCase):
    """The split this test exists for was two modules each joining a base to `prompt`."""

    def test_every_assignment_of_prompt_path_comes_from_the_resolver(self):
        self.assertEqual(prompt_path_writers(os.path.join(PKG, "app")), [])

    def test_it_sees_a_module_that_builds_the_path_itself(self):
        """The control: without it, a checker that matched nothing would pass."""
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "m.py"), "w", encoding="utf-8") as fh:
                fh.write('role["prompt_path"] = os.path.join(paths.REPO, role["prompt"])\n')
            self.assertEqual(prompt_path_writers(root), [("m.py", 1)])

    def test_it_accepts_an_assignment_from_the_resolver(self):
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "m.py"), "w", encoding="utf-8") as fh:
                fh.write('role["prompt_path"] = P.prompt_path(policy, name)\n')
            self.assertEqual(prompt_path_writers(root), [])


if __name__ == "__main__":
    unittest.main()
