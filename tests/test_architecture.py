"""The rules this repository keeps about its own source, made enforceable.

Two of them: the layering its imports already have, and the one incident this suite
has actually caused — a unit run that wrote a fake repository into the operator's real
CLI configuration. Both checks carry a control, because a checker that looks at nothing
passes every suite.

The layering:

Nothing here invents a structure: `LAYERS` records the order the modules already
depend in, so the test fails when a new import inverts it rather than when someone
dislikes a design. A module may import a lower layer and never its own or a higher
one — an entry point is therefore never imported by anything, which is what keeps
argparse and console output out of the worker and the workbench.

The determinism boundary is Temporal's to enforce at runtime; this owns the rest.
"""
import ast
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

# Low to high. A module imports only from a strictly lower tuple.
LAYERS = (
    # Facts and pure decisions: no import of ours at all.
    ("envpath", "launch", "nodes", "policy", "ptyhost", "repos", "routing", "trust", "turn_hook"),
    # Mechanisms over those facts: git, terminals, the workflow itself, the trace.
    ("telemetry", "terminal", "workflow", "worktrees"),
    # What the outside drives the run through.
    ("activities", "client"),
    # Entry points. Nothing imports these.
    ("cli", "workbench", "worker"),
)


def _layer_of(module, layers):
    for index, names in enumerate(layers):
        if module in names:
            return index
    return None


def upward_imports(root, layers):
    """Every import that reaches its own layer or higher, as (module, imported, line)."""
    known = {name for names in layers for name in names}
    found = []
    for names in layers:
        for module in names:
            path = os.path.join(root, module + ".py")
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as handle:
                tree = ast.parse(handle.read(), filename=path)
            mine = _layer_of(module, layers)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                    imported = [node.module.split(".")[0]]
                else:
                    continue
                for name in imported:
                    if name in known and name != module and _layer_of(name, layers) >= mine:
                        found.append((module, name, node.lineno))
    return sorted(found)


class Layering(unittest.TestCase):
    def test_every_module_is_placed(self):
        placed = {name for names in LAYERS for name in names}
        on_disk = {f[:-3] for f in os.listdir(REPO) if f.endswith(".py")}
        self.assertEqual(on_disk - placed, set(), "a module no layer claims")
        self.assertEqual(placed - on_disk, set(), "a layer names a module that is gone")

    def test_no_import_reaches_its_own_layer_or_higher(self):
        found = upward_imports(REPO, LAYERS)
        self.assertEqual(found, [], "\n".join(
            "%s imports %s at line %d" % row for row in found))


def unguarded_trust_writes(paths):
    """Every `trust.ensure`/`forget` in a unit test that does not name a home, as (file, line).

    A trust record is written into the CLI's own store, so a unit test that leaves the home
    to its default edits the operator's real configuration. `acceptance_restart.py` is not a
    unit test and deliberately uses the real store: it proves a record is made and taken back.
    """
    found = []
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename=path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in ("ensure", "forget"):
                continue
            target = node.func.value
            if not isinstance(target, ast.Name) or target.id != "trust":
                continue
            named = any(kw.arg == "home" for kw in node.keywords)
            if len(node.args) < 3 and not named:
                found.append((os.path.basename(path), node.lineno))
    return sorted(found)


class TrustStaysOffTheOperatorsHome(unittest.TestCase):
    def test_no_unit_test_writes_a_trust_record_to_the_real_home(self):
        unit = [os.path.join(HERE, f) for f in sorted(os.listdir(HERE))
                if f.startswith("test_") and f.endswith(".py")]
        self.assertTrue(unit, "no unit tests were found to check")
        found = unguarded_trust_writes(unit)
        self.assertEqual(found, [], "\n".join("%s:%d names no home" % row for row in found))


class TheCheckersCanFail(unittest.TestCase):
    """Without these, a checker that never looks at anything would pass the suite."""

    def test_it_sees_a_trust_write_with_no_home(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "test_bad.py")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("trust.ensure(repo, ['claude'])\n")
            self.assertEqual(unguarded_trust_writes([path]), [("test_bad.py", 1)])

    def test_it_accepts_a_trust_write_that_names_a_home(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "test_ok.py")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("trust.ensure(repo, ['claude'], home)\n"
                         "trust.forget(repo, ['codex'], home=home)\n")
            self.assertEqual(unguarded_trust_writes([path]), [])

    def test_it_sees_an_upward_import(self):
        layers = (("low",), ("high",))
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "low.py"), "w", encoding="utf-8") as fh:
                fh.write("import high\n")          # the violation: low reaches up
            with open(os.path.join(root, "high.py"), "w", encoding="utf-8") as fh:
                fh.write("x = 1\n")
            self.assertEqual(upward_imports(root, layers), [("low", "high", 1)])

    def test_it_sees_an_import_inside_a_function(self):
        layers = (("low",), ("high",))
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "low.py"), "w", encoding="utf-8") as fh:
                fh.write("def f():\n    from high import thing\n    return thing\n")
            with open(os.path.join(root, "high.py"), "w", encoding="utf-8") as fh:
                fh.write("thing = 1\n")
            self.assertEqual(upward_imports(root, layers), [("low", "high", 2)])

    def test_it_accepts_a_downward_import(self):
        layers = (("low",), ("high",))
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "low.py"), "w", encoding="utf-8") as fh:
                fh.write("x = 1\n")
            with open(os.path.join(root, "high.py"), "w", encoding="utf-8") as fh:
                fh.write("import low\n")
            self.assertEqual(upward_imports(root, layers), [])


class TheVendorIsTheRunsDecision(unittest.TestCase):
    """A turn is driven as the agent the run chose, and an unknown one is refused."""

    def test_a_turn_refuses_an_agent_this_host_cannot_wire(self):
        import launch
        import terminal
        with tempfile.TemporaryDirectory() as rdir:
            with self.assertRaises(launch.ExecutorError) as raised:
                terminal.run_turn(rdir, ["claude"], rdir, "build-e1-1", "hi", 60, {},
                                  brain="deepseek")
            self.assertIn("deepseek", str(raised.exception))
            # Refused before the turn left anything behind.
            self.assertEqual(os.listdir(rdir), [])

    def test_the_policy_names_the_agents_a_turn_accepts(self):
        import policy
        self.assertEqual(sorted(policy.KNOWN_BRAINS), ["claude", "codex"])


if __name__ == "__main__":
    unittest.main()
