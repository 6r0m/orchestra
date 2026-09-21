"""A role's persona file has one resolver, and it answers the same on either host.

The policy crosses hosts as data: the client validates it, and the target host runs the role.
While each built the path itself, an external policy was validated against its own directory
and then read from the checkout — two files, one name. These prove there is one resolver and
that the run-time call and validation agree.
"""
import ast
import os
import sys
import tempfile
import unittest

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
    """A policy outside the checkout, whose role prompts are relative to itself."""
    os.makedirs(os.path.join(root, "roles"))
    for role in ("engineer", "architect"):
        with open(os.path.join(root, "roles", "%s.md" % role), "w", encoding="utf-8") as fh:
            fh.write("# the %s of this other policy\n" % role)
    path = os.path.join(root, "policy.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(POLICY)
    return path


class OneResolver(unittest.TestCase):
    def test_an_external_policy_resolves_to_its_own_roles_at_validation_and_at_run_time(self):
        with tempfile.TemporaryDirectory() as root:
            path = external_policy(root)
            loaded = P.load(path)
            mine = os.path.normpath(os.path.join(root, "roles", "engineer.md"))
            # What validation stored, and what the host running the role asks for.
            self.assertEqual(loaded["roles"]["engineer"]["prompt_path"], mine)
            self.assertEqual(P.prompt_path(loaded, "engineer", path), mine)
            self.assertTrue(os.path.isfile(mine))
            # The defect this test exists for: the checkout's own file is a different one.
            self.assertNotEqual(mine, os.path.join(paths.REPO, "roles", "engineer.md"))

    def test_the_default_policy_resolves_against_this_checkout(self):
        loaded = P.load()
        self.assertEqual(
            P.prompt_path(loaded, "architect", None),
            os.path.normpath(os.path.join(paths.REPO,
                                          loaded["roles"]["architect"]["prompt"])))

    def test_the_base_it_is_given_is_the_base_it_uses(self):
        """The control: a resolver that ignored its base would pass the two tests above."""
        with tempfile.TemporaryDirectory() as root:
            path = external_policy(root)
            loaded = P.load(path)
            elsewhere = os.path.join(root, "moved", "policy.json")
            self.assertEqual(
                P.prompt_path(loaded, "engineer", elsewhere),
                os.path.normpath(os.path.join(root, "moved", "roles", "engineer.md")))

    def test_an_absolute_prompt_is_left_alone(self):
        with tempfile.TemporaryDirectory() as root:
            path = external_policy(root)
            loaded = P.load(path)
            absolute = os.path.abspath(os.path.join(root, "roles", "architect.md"))
            loaded["roles"]["architect"]["prompt"] = absolute
            self.assertEqual(P.prompt_path(loaded, "architect", path), absolute)


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
