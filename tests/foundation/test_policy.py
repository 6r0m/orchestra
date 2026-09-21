"""A role's persona file has one resolver, and it answers the same on either host.

The policy crosses hosts as data: the client validates it, and the target host runs the role.
While each built the path itself, an external policy was validated against its own directory
and then read from the checkout — two files, one name. With one resolver, what crosses is the
policy's origin, so it must be a name the target host can read: relative to the checkout when
the file is inside it, and refused when it is a path only the other host can spell.
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

POLICY = """{
  "roles": {
    "engineer": {"brain": "claude", "workspace_access": "write", "prompt": "roles/engineer.md"},
    "architect": {"brain": "codex", "workspace_access": "read", "prompt": "roles/architect.md"}
  },
  "max_rounds": {"plan": 2, "build": 2},
  "auto_proceed": false,
  "timeout_seconds": 60,
  "heartbeat_seconds": 30,
  "workbench_port": 8390,
  "targets": {"wsl": {"host": "local", "worktree_root": "/tmp", "terminal_port": 8401},
              "windows": {"host": "local", "worktree_root": "C:\\\\tmp", "terminal_port": 8402}},
  "target_repo": {"commit_allowed": false, "push_allowed": false, "merge_allowed": false}
}
"""


def external_policy(root):
    """A policy file under `root`, whose role prompts are relative to itself."""
    os.makedirs(os.path.join(root, "roles"), exist_ok=True)
    for role in ("engineer", "architect"):
        with open(os.path.join(root, "roles", "%s.md" % role), "w", encoding="utf-8") as fh:
            fh.write("# the %s of this other policy\n" % role)
    path = os.path.join(root, "policy.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(POLICY)
    return path


# How the other host spells an absolute path: what a policy loaded there would carry across.
OTHER_HOSTS_PATH = ("/mnt/e/elsewhere/policy.json" if sys.platform.startswith("win")
                    else "E:\\elsewhere\\policy.json")


class OneResolver(unittest.TestCase):
    def test_an_external_policy_resolves_to_its_own_roles_at_validation_and_at_run_time(self):
        with tempfile.TemporaryDirectory() as root:
            path = external_policy(root)
            loaded = P.load(path)
            mine = os.path.normpath(os.path.join(root, "roles", "engineer.md"))
            # Validation proved the persona is there and stored no path: the policy crosses hosts.
            self.assertNotIn("prompt_path", loaded["roles"]["engineer"])
            self.assertEqual(P.prompt_path(loaded, "engineer", path), mine)
            self.assertEqual(P.prompt_path(loaded, "engineer"), mine,
                             "on the host that loaded it, its absolute origin is readable as it stands")
            # The defect this test exists for: the checkout's own file is a different one.
            self.assertNotEqual(mine, os.path.join(paths.REPO, "roles", "engineer.md"))

    def test_the_default_policy_resolves_against_this_checkout(self):
        loaded = P.load(P.POLICY_FILE)
        self.assertEqual(
            P.prompt_path(loaded, "architect", None),
            os.path.normpath(os.path.join(paths.REPO,
                                          loaded["roles"]["architect"]["prompt"])))

    def test_the_base_it_is_given_is_the_base_it_uses(self):
        """The control: a resolver that ignored its base would pass the two tests above."""
        with tempfile.TemporaryDirectory() as root:
            loaded = P.load(external_policy(root))
            elsewhere = external_policy(os.path.join(root, "moved"))
            self.assertEqual(
                P.prompt_path(loaded, "engineer", elsewhere),
                os.path.normpath(os.path.join(root, "moved", "roles", "engineer.md")))

    def test_an_absolute_prompt_is_left_alone(self):
        with tempfile.TemporaryDirectory() as root:
            path = external_policy(root)
            loaded = P.load(path)
            absolute = os.path.abspath(os.path.join(root, "roles", "architect.md"))
            loaded["roles"]["architect"]["prompt"] = absolute
            self.assertEqual(P.prompt_path(loaded, "architect"), absolute)

    def test_a_persona_that_is_not_there_is_refused_where_the_role_would_run(self):
        loaded = P.load(P.POLICY_FILE)
        loaded["roles"]["engineer"] = dict(loaded["roles"]["engineer"], prompt="roles/nobody.md")
        with self.assertRaises(P.InvalidPolicy) as raised:
            P.prompt_path(loaded, "engineer")
        self.assertIn("nobody.md", str(raised.exception))


class TheOriginCrossesHosts(unittest.TestCase):
    """What the client's policy carries must be readable on the host that runs the role."""

    def test_a_policy_inside_the_checkout_carries_a_name_relative_to_it(self):
        loaded = P.load(P.POLICY_FILE)
        self.assertEqual(loaded["_policy_path"], "policy.json")
        # Neither host's spelling of the checkout crosses: that was the defect.
        self.assertIsNone(P.ABSOLUTE_ANYWHERE.match(loaded["_policy_path"]))

    def test_a_relative_origin_is_read_against_this_hosts_checkout(self):
        """What the target host does with a policy the other host loaded from its checkout."""
        os.makedirs(paths.RUNTIME_ROOT, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=paths.RUNTIME_ROOT) as root:
            external_policy(root)
            loaded = P.load(os.path.join(root, "policy.json"))
            relative = os.path.relpath(root, paths.REPO).replace(os.sep, "/")
            self.assertEqual(loaded["_policy_path"], relative + "/policy.json")
            self.assertEqual(P.prompt_path(loaded, "engineer"),
                             os.path.normpath(os.path.join(root, "roles", "engineer.md")))
            # The control: the checkout's own persona is another file, so a resolver that fell
            # back to it would fail here.
            self.assertNotEqual(P.prompt_path(loaded, "engineer"),
                                P.prompt_path(P.load(P.POLICY_FILE), "engineer"))

    def test_an_origin_only_the_other_host_can_read_is_refused(self):
        loaded = P.load(P.POLICY_FILE)
        loaded["_policy_path"] = OTHER_HOSTS_PATH
        with self.assertRaises(P.InvalidPolicy) as raised:
            P.prompt_path(loaded, "engineer")
        self.assertIn("ORCH_POLICY", str(raised.exception))

    def test_this_hosts_copy_of_the_policy_decides_where_its_personas_are(self):
        """A target given ORCH_POLICY reads the personas beside its own copy of the run's policy."""
        with tempfile.TemporaryDirectory() as root:
            loaded = P.load(external_policy(os.path.join(root, "client")))
            loaded["_policy_path"] = OTHER_HOSTS_PATH
            mine = external_policy(os.path.join(root, "target"))
            self.assertEqual(P.prompt_path(loaded, "engineer", mine),
                             os.path.normpath(os.path.join(root, "target", "roles", "engineer.md")))

    def test_a_copy_that_says_something_else_is_refused(self):
        """ORCH_POLICY is where a host keeps the run's policy, not a second one that overrides it."""
        with tempfile.TemporaryDirectory() as root:
            loaded = P.load(external_policy(os.path.join(root, "client")))
            mine = external_policy(os.path.join(root, "target"))
            with open(mine, encoding="utf-8") as fh:
                other = fh.read().replace('"roles/engineer.md"', '"personas/engineer.md"')
            os.makedirs(os.path.join(root, "target", "personas"))
            with open(os.path.join(root, "target", "personas", "engineer.md"), "w", encoding="utf-8") as fh:
                fh.write("# another persona\n")
            with open(mine, "w", encoding="utf-8") as fh:
                fh.write(other)
            with self.assertRaises(P.InvalidPolicy) as raised:
                P.prompt_path(loaded, "engineer", mine)
            self.assertIn("roles", str(raised.exception))

    def test_nothing_resolved_on_one_host_crosses_to_the_other(self):
        loaded = P.load(P.POLICY_FILE)
        for role in loaded["roles"].values():
            self.assertNotIn("prompt_path", role)
        crossing = json.dumps(loaded)
        for spelling in (paths.REPO, paths.REPO.replace(os.sep, "/"), json.dumps(paths.REPO)[1:-1]):
            self.assertNotIn(spelling, crossing, "this host's checkout is in what crosses")

    def test_this_hosts_policy_is_the_one_orch_policy_names(self):
        """What the page, the CLI and the worker each load when none is named."""
        with tempfile.TemporaryDirectory() as root:
            mine = external_policy(root)
            with mock.patch.dict(os.environ, {"ORCH_POLICY": mine}):
                self.assertEqual(P.load()["_policy_path"], os.path.abspath(mine))
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("ORCH_POLICY", None)
                self.assertEqual(P.load()["_policy_path"], "policy.json")


class TheTargetOpensItsOwnPersona(unittest.TestCase):
    """At the boundary that matters: the activity a target host runs, given the policy a client sent.

    The policy arrives as a Temporal payload — JSON, decoded on the host running this suite — and
    the agent is the runner seam, so no vendor CLI runs. What reaches the agent is the persona
    this host holds; a policy this host cannot map starts no agent at all. On the Windows host
    suite this is the WSL client's policy meeting the Windows target's activity.
    """

    def setUp(self):
        from fakes import FakeWorktrees
        from app.application import activities
        self.activities, self.git = activities, FakeWorktrees()
        self.run_id = "persona-%s" % os.urandom(4).hex()
        self.addCleanup(lambda: __import__("shutil").rmtree(activities.run_dir(self.run_id), True))
        self.prompts = []
        environ = mock.patch.dict(os.environ)
        environ.start()
        self.addCleanup(environ.stop)
        os.environ.pop("ORCH_POLICY", None)

    def run_plan(self, policy):
        def agent(worktree, argv, rdir, name, prompt, timeout, env, brain=None):
            self.prompts.append(prompt)
            return 0, "planned\n"
        state = {"run_id": self.run_id, "task": "t", "phase": "plan", "round": 0, "episode": 1,
                 "worktree_path": "/fake/worktree", "todo_path": "/fake/worktree/todo/x.md",
                 "agent_sessions": {}}
        host = self.activities.Activities(runner=agent, git=self.git, telemetry=None)
        # What Temporal carries between the hosts: JSON, decoded here.
        return host.run_role({"stage": "plan", "state": state, "policy": json.loads(json.dumps(policy))})

    def test_a_clients_policy_reaches_the_agent_with_this_hosts_persona(self):
        sent = P.load(P.POLICY_FILE)
        with open(os.path.join(paths.REPO, "roles", "engineer.md"), encoding="utf-8") as fh:
            persona = fh.readline().strip()
        self.run_plan(sent)
        self.assertEqual(len(self.prompts), 1)
        self.assertIn(persona, self.prompts[0])

    def test_an_origin_only_the_client_can_read_starts_no_agent(self):
        """The control: what the staged resolver sent — the client's absolute path — is refused."""
        sent = dict(P.load(P.POLICY_FILE), _policy_path=OTHER_HOSTS_PATH)
        with self.assertRaises(Exception) as raised:
            self.run_plan(sent)
        self.assertIn("ORCH_POLICY", str(raised.exception))
        self.assertEqual(self.prompts, [], "no agent started")

    def test_a_host_copy_that_differs_starts_no_agent(self):
        with tempfile.TemporaryDirectory() as root:
            mine = external_policy(root)
            os.environ["ORCH_POLICY"] = mine
            with self.assertRaises(Exception) as raised:
                self.run_plan(P.load(P.POLICY_FILE))
        self.assertIn("differs from the run's", str(raised.exception))
        self.assertEqual(self.prompts, [], "no agent started")

    def test_a_host_copy_that_differs_starts_no_agent_for_an_absolute_prompt_either(self):
        """The copy is checked whatever the prompt: an absolute one resolves nothing, and is no exception."""
        with tempfile.TemporaryDirectory() as root:
            sent = P.load(P.POLICY_FILE)
            sent["roles"]["engineer"] = dict(sent["roles"]["engineer"],
                                             prompt=os.path.join(paths.REPO, "roles", "engineer.md"))
            os.environ["ORCH_POLICY"] = external_policy(root)
            with self.assertRaises(Exception) as raised:
                self.run_plan(sent)
        self.assertIn("differs from the run's", str(raised.exception))
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
                fh.write('role["prompt_path"] = P.prompt_path(policy, name, named)\n')
            self.assertEqual(prompt_path_writers(root), [])


if __name__ == "__main__":
    unittest.main()
