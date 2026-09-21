"""The rules this repository keeps about its own source, made enforceable.

Four of them: the package boundaries its imports already respect, that the checkout root
the whole tree derives from still lands on a checkout, that no `app/` module escapes a
package, and the one incident this suite has actually caused — a unit run that wrote a
fake repository into the operator's real CLI configuration. Every check carries a
control, because a checker that looks at nothing passes every suite.

The boundaries:

Nothing here invents a structure. `ALLOWED` records the direction the packages already
depend in, so the test fails when a new import crosses a boundary rather than when
someone dislikes a design. The folder is the structural source of truth: a new module
inside a package needs no entry here, and a new *package* does — which is the one
decision worth forcing someone to write down.

Imports inside a package are that package's own business. Nothing may import
`interfaces`, which is what keeps argparse and console output out of the worker and
the workbench.

The determinism boundary is Temporal's to enforce at runtime; this owns the rest.
"""
import ast
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

PACKAGE = "app"
SOURCE = os.path.join(REPO, PACKAGE)
# What each package may import. A package may always import itself; absent from every
# value means nothing may import it. Derived from the imports that exist, not from a
# diagram: no indirection exists here only to satisfy this table.
ALLOWED = {
    # The contract every package reads: the checkout, the policy, the stages. Reads nothing of ours.
    "foundation": frozenset(),
    # The run: its stages, its routes, its stops. Deterministic under Temporal.
    "orchestration": frozenset({"foundation"}),
    # The repositories a run operates on, and its worktree through their own git.
    "workspace": frozenset({"foundation"}),
    # A role's agent: its terminal, its containment, its prompt and its answer.
    "agents": frozenset({"foundation"}),
    # The optional trace. Nothing reads back from it (D20).
    "observability": frozenset({"foundation"}),
    # Where the concerns are composed: the activities a run executes, and its client.
    "application": frozenset({"foundation", "orchestration", "workspace", "agents",
                              "observability"}),
    # What a human or a process manager starts. Nothing imports these.
    "interfaces": frozenset({"foundation", "orchestration", "workspace", "agents",
                             "observability", "application"}),
}


def _package_of(path, source):
    """The top-level package a file under `source` belongs to, or None for `source` itself."""
    relative = os.path.relpath(path, source)
    head = relative.split(os.sep)[0]
    return head if head != os.path.basename(relative) else None


def _own_package(path, source):
    """The importing module's own package, as Python sees it: ('app', 'agents', ...)."""
    relative = os.path.relpath(os.path.dirname(path), source)
    inside = [] if relative == os.curdir else relative.split(os.sep)
    return [PACKAGE] + inside


def _imported_packages(tree, own_package):
    """Every `app.<package>` this module imports, with the line it is imported on.

    A relative import is resolved the way Python resolves it, against the importing
    module's own package — one that climbs out of its package and into a sibling is
    exactly the import worth catching, and reads like an innocent local one.
    """
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # `from . import x` stays in this package; each extra dot climbs one out.
                base = own_package[:len(own_package) - (node.level - 1)]
                module = ".".join(base + (node.module.split(".") if node.module else []))
            else:
                module = node.module
            # What is imported is the module *and* each name taken from it, which may itself be a
            # package: `from .. import high` and `from app import high` both import `app.high`.
            names = [module] + ["%s.%s" % (module, alias.name) for alias in node.names
                                if alias.name != "*"]
        else:
            continue
        for name in names:
            parts = name.split(".")
            if parts[0] == PACKAGE and len(parts) > 1:
                found.append((parts[1], node.lineno))
    return found


def source_files(source):
    for root, dirs, files in os.walk(source):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for name in sorted(files):
            if name.endswith(".py"):
                yield os.path.join(root, name)


def crossing_imports(source, allowed):
    """Every import that crosses a boundary the table does not allow, as (from, to, file, line)."""
    found = []
    for path in source_files(source):
        mine = _package_of(path, source)
        if mine is None:
            continue
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename=path)
        for package, line in _imported_packages(tree, _own_package(path, source)):
            if package == mine or package in allowed.get(mine, frozenset()):
                continue
            found.append((mine, package, os.path.relpath(path, source).replace(os.sep, "/"), line))
    return sorted(set(found))


def package_imports(source):
    """Every (importer, imported) pair of distinct packages some module under `source` makes."""
    found = set()
    for path in source_files(source):
        mine = _package_of(path, source)
        if mine is None:
            continue
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename=path)
        found.update((mine, package) for package, _ in _imported_packages(tree, _own_package(path, source))
                     if package != mine)
    return found


# A Mermaid edge `a -->|"label"| b`, or `a --> b`. `<-->` and `-.->` are a participant's traffic
# and a trace's, never an import, so neither matches.
EDGE = re.compile(r"^\s*(\w+)\s+-->(?:\|[^|]*\|)?\s*(\w+)\s*$")


def drawn_imports(view, packages):
    """Every arrow the view draws between two of `packages`, as (from, to)."""
    with open(view, encoding="utf-8") as handle:
        edges = (EDGE.match(line) for line in handle)
        return {m.groups() for m in edges if m and m.group(1) in packages and m.group(2) in packages}


def unplaced_modules(source, allowed):
    """Every module under `source` that no package in the table claims, as relative paths."""
    found = []
    for path in source_files(source):
        package = _package_of(path, source)
        if package is None:
            # Only the package marker may sit at the root of the source tree.
            if os.path.basename(path) != "__init__.py":
                found.append(os.path.relpath(path, source).replace(os.sep, "/"))
        elif package not in allowed:
            found.append(os.path.relpath(path, source).replace(os.sep, "/"))
    return sorted(found)


# The address every architecture-owning scope here uses, so a reader routes to it without
# looking, as the hops that reach it. One hop per level: a scope's README routes to its docs,
# which route to its architecture, which routes to its structure and to its views.
ROUTE = (("README.md", "docs/README.md"),
         ("docs/README.md", "docs/architecture/README.md"),
         ("docs/architecture/README.md", "docs/architecture/structure.md"),
         ("docs/architecture/README.md", "docs/architecture/diagrams/README.md"),
         ("docs/architecture/diagrams/README.md", "docs/architecture/diagrams/main.md"))
LINK = re.compile(r"\]\(([^)\s#]+)")


def links(path):
    """Every local file `path` links to, as a normalised absolute path."""
    with open(path, encoding="utf-8") as handle:
        targets = LINK.findall(handle.read())
    base = os.path.dirname(path)
    return {os.path.normpath(os.path.join(base, *t.split("/"))) for t in targets if "://" not in t}


def broken_routes(scope):
    """Every hop of the architecture address that `scope` does not walk, as `from -> to`.

    Each hop must exist as a file *and* as a link from the router one level up: a file that
    exists and that nothing routes to is unreachable by traversal, and so is every file below it.
    """
    found = []
    for source, target in ROUTE:
        router = os.path.join(scope, *source.split("/"))
        routed = os.path.join(scope, *target.split("/"))
        if not os.path.isfile(routed):
            found.append("%s is missing" % target)
        elif not os.path.isfile(router) or routed not in links(router):
            found.append("%s -> %s" % (source, target))
    return found


def unrouted(router, children):
    """Every child directory whose README `router` does not link, which is where a branch goes dark."""
    linked = links(router)
    base = os.path.dirname(router)
    return sorted(c for c in children if os.path.join(base, c, "README.md") not in linked)


def is_checkout(path):
    """Whether `path` is the root of an Orchestra checkout rather than some directory above it."""
    return os.path.isfile(os.path.join(path, "pyproject.toml"))


def under(root, path):
    """Whether `path` lies inside `root` — by path components, never by string prefix.

    A string prefix would call `<root>2/x` a child of `<root>`, which is how a second
    checkout beside this one would pass a check that means to see only this one.
    """
    relative = os.path.relpath(os.path.abspath(path), os.path.abspath(root))
    return relative != os.curdir and relative.split(os.sep)[0] != os.pardir


class PackageBoundaries(unittest.TestCase):
    def test_no_import_crosses_a_boundary_the_table_does_not_allow(self):
        found = crossing_imports(SOURCE, ALLOWED)
        self.assertEqual(found, [], "\n".join(
            "%s imports %s (%s:%d)" % row for row in found))

    def test_every_module_lives_in_a_package_the_table_claims(self):
        self.assertEqual(unplaced_modules(SOURCE, ALLOWED), [])

    def test_every_package_on_disk_is_in_the_table(self):
        on_disk = {name for name in os.listdir(SOURCE)
                   if os.path.isdir(os.path.join(SOURCE, name)) and name != "__pycache__"}
        self.assertEqual(on_disk - set(ALLOWED), set(), "a package no rule claims")
        self.assertEqual(set(ALLOWED) - on_disk, set(), "a rule names a package that is gone")

    def test_every_allowed_import_is_one_the_source_makes(self):
        """The table records the imports that exist, so a permission nothing uses is stale."""
        allowed = {(p, q) for p, may in ALLOWED.items() for q in may}
        self.assertEqual(allowed - package_imports(SOURCE), set())

    def test_the_main_view_draws_exactly_the_allowed_imports(self):
        view = os.path.join(REPO, "docs", "architecture", "diagrams", "main.md")
        allowed = {(p, q) for p, may in ALLOWED.items() for q in may}
        drawn = drawn_imports(view, ALLOWED)
        self.assertEqual((allowed - drawn, drawn - allowed), (set(), set()),
                         "(allowed but not drawn, drawn but not allowed)")

    def test_nothing_imports_an_entry_point(self):
        importers = [package for package, may in ALLOWED.items() if "interfaces" in may]
        self.assertEqual(importers, [], "an entry point is imported by %s" % importers)


class EveryConcernIsReachable(unittest.TestCase):
    """A concern nothing routes to is unreachable by traversal, whatever else points at it."""

    def test_the_project_and_every_package_walk_the_architecture_address(self):
        scopes = {"the project": REPO}
        scopes.update(("app/" + p, os.path.join(SOURCE, p)) for p in ALLOWED)
        broken = {name: broken_routes(path) for name, path in scopes.items()}
        self.assertEqual({name: hops for name, hops in broken.items() if hops}, {})

    def test_every_package_is_linked_from_its_parents_router(self):
        self.assertEqual(unrouted(os.path.join(REPO, "README.md"), [PACKAGE]), [])
        self.assertEqual(unrouted(os.path.join(SOURCE, "README.md"), ALLOWED), [])


class TheCheckoutRootIsStillTheCheckout(unittest.TestCase):
    """`paths` derives the root by climbing out of its own file; a move must fail loudly."""

    def test_the_derived_root_is_a_checkout(self):
        from app.foundation import paths
        self.assertTrue(is_checkout(paths.REPO), "%s is not a checkout" % paths.REPO)
        self.assertEqual(os.path.normcase(os.path.realpath(paths.REPO)),
                         os.path.normcase(os.path.realpath(REPO)))

    def test_every_other_root_is_derived_from_that_one(self):
        """No module builds a second root: every path below is `paths.REPO` plus a name.

        `repos.DESCRIPTORS` is checked as its default. `ORCH_REPOS` may point it anywhere,
        which is the acceptance run's throwaway repository and not a second definition.
        """
        from app.foundation import paths, policy
        from app.workspace import repos
        default_descriptors = os.path.join(paths.REPO, "repos.json")
        for value in (paths.RUNTIME_ROOT, paths.SECRETS, policy.POLICY_FILE, default_descriptors):
            self.assertTrue(under(paths.REPO, value), "%s does not lie under %s" % (value, paths.REPO))
        self.assertIn(repos.DESCRIPTORS, (default_descriptors, os.environ.get("ORCH_REPOS")))


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


def unit_tests(root):
    """Every `test_*.py` in the suite, at any depth: the concerns are mirrored in folders."""
    found = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        found.extend(os.path.join(base, f) for f in files
                     if f.startswith("test_") and f.endswith(".py"))
    return sorted(found)


class TrustStaysOffTheOperatorsHome(unittest.TestCase):
    def test_no_unit_test_writes_a_trust_record_to_the_real_home(self):
        unit = unit_tests(HERE)
        self.assertTrue(unit, "no unit tests were found to check")
        found = unguarded_trust_writes(unit)
        self.assertEqual(found, [], "\n".join("%s:%d names no home" % row for row in found))

    def test_the_search_reaches_a_mirrored_concern(self):
        """The suite is nested now: a guard that only read the top folder would check nothing."""
        self.assertTrue(any(os.path.dirname(p) != HERE for p in unit_tests(HERE)),
                        "no test lives in a concern folder, so this search proves nothing")


def _tree(root, files):
    for relative, body in files.items():
        path = os.path.join(root, *relative.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
    return root


class TheCheckersCanFail(unittest.TestCase):
    """Without these, a checker that never looks at anything would pass the suite."""

    LAYERS = {"low": frozenset(), "high": frozenset({"low"})}

    def test_it_sees_an_import_that_crosses_upward(self):
        with tempfile.TemporaryDirectory() as root:
            _tree(root, {"low/x.py": "from app.high import y\n", "high/y.py": "z = 1\n"})
            self.assertEqual(crossing_imports(root, self.LAYERS),
                             [("low", "high", "low/x.py", 1)])

    def test_it_sees_an_import_inside_a_function(self):
        with tempfile.TemporaryDirectory() as root:
            _tree(root, {"low/x.py": "def f():\n    import app.high.y\n    return app\n",
                         "high/y.py": "z = 1\n"})
            self.assertEqual(crossing_imports(root, self.LAYERS),
                             [("low", "high", "low/x.py", 2)])

    def test_it_sees_a_relative_import_that_climbs_into_another_package(self):
        """`from ..high import y` reads like a local import and is a boundary crossing."""
        with tempfile.TemporaryDirectory() as root:
            _tree(root, {"low/x.py": "from ..high import y\n", "high/y.py": "z = 1\n"})
            self.assertEqual(crossing_imports(root, self.LAYERS),
                             [("low", "high", "low/x.py", 1)])

    def test_it_sees_a_bare_relative_climb(self):
        """`from .. import high` names no module, and imports the package `app.high` all the same."""
        with tempfile.TemporaryDirectory() as root:
            _tree(root, {"low/x.py": "from .. import high\n", "high/y.py": "z = 1\n"})
            self.assertEqual(crossing_imports(root, self.LAYERS),
                             [("low", "high", "low/x.py", 1)])

    def test_it_sees_a_package_taken_from_the_root_by_name(self):
        with tempfile.TemporaryDirectory() as root:
            _tree(root, {"low/x.py": "from app import high\n", "high/y.py": "z = 1\n"})
            self.assertEqual(crossing_imports(root, self.LAYERS),
                             [("low", "high", "low/x.py", 1)])

    def test_it_accepts_a_relative_import_inside_one_package(self):
        with tempfile.TemporaryDirectory() as root:
            _tree(root, {"low/x.py": "from . import y\nfrom .y import thing\n",
                         "low/y.py": "thing = 1\n"})
            self.assertEqual(crossing_imports(root, self.LAYERS), [])

    def test_it_resolves_a_relative_import_from_a_subpackage(self):
        with tempfile.TemporaryDirectory() as root:
            _tree(root, {"low/sub/x.py": "from ...high import y\n", "high/y.py": "z = 1\n"})
            self.assertEqual(crossing_imports(root, self.LAYERS),
                             [("low", "high", "low/sub/x.py", 1)])

    def test_it_accepts_an_allowed_import_and_a_sibling(self):
        with tempfile.TemporaryDirectory() as root:
            _tree(root, {"high/y.py": "from app.low import x\nfrom app.high import w\n",
                         "high/w.py": "v = 1\n", "low/x.py": "z = 1\n"})
            self.assertEqual(crossing_imports(root, self.LAYERS), [])

    def test_it_sees_a_module_no_package_claims(self):
        with tempfile.TemporaryDirectory() as root:
            _tree(root, {"stray.py": "x = 1\n", "nowhere/m.py": "x = 1\n", "low/x.py": "x = 1\n"})
            self.assertEqual(unplaced_modules(root, self.LAYERS), ["nowhere/m.py", "stray.py"])

    def test_it_accepts_a_tree_whose_modules_are_all_placed(self):
        with tempfile.TemporaryDirectory() as root:
            _tree(root, {"__init__.py": "", "low/x.py": "x = 1\n", "high/y.py": "x = 1\n"})
            self.assertEqual(unplaced_modules(root, self.LAYERS), [])

    def test_it_sees_a_path_that_only_looks_like_a_child(self):
        root = os.path.join("E:", os.sep, "repos", "orchestra")
        self.assertTrue(under(root, os.path.join(root, "tmp", "orchestration")))
        self.assertFalse(under(root, root))
        self.assertFalse(under(root, os.path.join("E:", os.sep, "repos", "orchestra2", "x")))
        self.assertFalse(under(root, os.path.join("E:", os.sep, "repos")))

    def test_it_reads_the_imports_a_tree_makes(self):
        with tempfile.TemporaryDirectory() as root:
            _tree(root, {"high/y.py": "from app.low import x\nfrom . import w\n",
                         "high/w.py": "", "low/x.py": ""})
            self.assertEqual(package_imports(root), {("high", "low")})

    def test_it_reads_only_the_arrows_between_parts(self):
        with tempfile.TemporaryDirectory() as root:
            _tree(root, {"main.md": "```mermaid\nflowchart TD\n"
                                    '    high -->|"a label"| low\n'
                                    "    high --> low2\n"
                                    '    high <-->|"traffic"| low\n'
                                    '    low -.->|"rows"| high\n'
                                    '    high -->|"argv"| clis[("claude")]\n```\n'})
            self.assertEqual(drawn_imports(os.path.join(root, "main.md"), {"high", "low", "low2"}),
                             {("high", "low"), ("high", "low2")})

    WALKED = {"README.md": "[docs](docs/README.md)\n",
              "docs/README.md": "[a](architecture/README.md#top)\n",
              "docs/architecture/README.md": "[s](structure.md) [d](diagrams/README.md)\n",
              "docs/architecture/structure.md": "",
              "docs/architecture/diagrams/README.md": "[m](main.md)\n",
              "docs/architecture/diagrams/main.md": ""}

    def test_it_accepts_a_scope_that_walks_every_hop(self):
        with tempfile.TemporaryDirectory() as root:
            _tree(root, self.WALKED)
            self.assertEqual(broken_routes(root), [])

    def test_it_sees_a_hop_whose_link_is_gone_though_every_file_is_there(self):
        """The case an existence check passes: the router skips a level, so the route is broken."""
        with tempfile.TemporaryDirectory() as root:
            _tree(root, dict(self.WALKED, **{"README.md": "[a](docs/architecture/README.md)\n",
                                             "docs/architecture/README.md": "[s](structure.md)\n"}))
            self.assertEqual(broken_routes(root), [
                "README.md -> docs/README.md",
                "docs/architecture/README.md -> docs/architecture/diagrams/README.md"])

    def test_it_sees_a_concern_missing_its_architecture(self):
        with tempfile.TemporaryDirectory() as root:
            _tree(root, {"README.md": "[docs](docs/README.md)\n", "docs/README.md": ""})
            missing = broken_routes(root)
            self.assertIn("docs/architecture/structure.md is missing", missing)
            self.assertIn("docs/architecture/diagrams/main.md is missing", missing)
            self.assertNotIn("README.md -> docs/README.md", missing)

    def test_it_sees_a_concern_its_parent_does_not_route_to(self):
        with tempfile.TemporaryDirectory() as root:
            _tree(root, {"README.md": "| x | [low/README.md](low/README.md) |\n"})
            self.assertEqual(unrouted(os.path.join(root, "README.md"), ["low", "high"]), ["high"])

    def test_it_sees_a_directory_that_is_not_a_checkout(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertFalse(is_checkout(root))
            with open(os.path.join(root, "pyproject.toml"), "w", encoding="utf-8") as fh:
                fh.write("[project]\n")
            self.assertTrue(is_checkout(root))

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

    def test_it_finds_a_nested_unit_test(self):
        with tempfile.TemporaryDirectory() as root:
            _tree(root, {"concern/test_x.py": "", "test_y.py": "", "helper.py": ""})
            self.assertEqual([os.path.relpath(p, root).replace(os.sep, "/")
                              for p in unit_tests(root)], ["concern/test_x.py", "test_y.py"])


class TheVendorIsTheRunsDecision(unittest.TestCase):
    """A turn is driven as the agent the run chose, and an unknown one is refused."""

    def test_a_turn_refuses_an_agent_this_host_cannot_wire(self):
        from app.agents import launch
        from app.agents import terminal
        with tempfile.TemporaryDirectory() as rdir:
            with self.assertRaises(launch.ExecutorError) as raised:
                terminal.run_turn(rdir, ["claude"], rdir, "build-e1-1", "hi", 60, {},
                                  brain="deepseek")
            self.assertIn("deepseek", str(raised.exception))
            # Refused before the turn left anything behind.
            self.assertEqual(os.listdir(rdir), [])

    def test_the_policy_names_the_agents_a_turn_accepts(self):
        from app.foundation import policy
        self.assertEqual(sorted(policy.KNOWN_BRAINS), ["claude", "codex"])


if __name__ == "__main__":
    unittest.main()
