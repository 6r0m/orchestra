"""The settings as `application.settings` loads and applies them: each kind checks its own values, a
role's access is its contract whatever profile it runs, a run's policy made from them stays under
Temporal's payload warning on the real wire, and the Settings view's Apply writes only what it changes,
against the revision it read, one at a time.

The suite's own kind (`stand_in.py`) takes a value no shipped kind would, so a rule that belongs to a
kind can be told from one that was left generic.
"""
import ast
import base64
import contextlib
import glob
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

# The suite's own folder, reached from this concern's folder inside it, and the
# checkout above both: the shared harness and the fixtures live at the suite root.
HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PKG = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path[:0] = [PKG, HERE]

from app.application import settings as S  # noqa: E402
from app.foundation import policy as P  # noqa: E402
import stand_in  # noqa: E402


def shipped():
    """The shared settings, as a fresh copy to change."""
    return json.loads(json.dumps(S.load()))


class EachKindChecksItsOwnValues(unittest.TestCase):
    def setUp(self):
        stand_in.plant(self)

    def with_profile(self, **profile):
        settings = shipped()
        settings["agents"]["mine"] = profile
        return settings

    def test_a_kind_refuses_a_value_it_does_not_take(self):
        with self.assertRaises(P.InvalidPolicy) as raised:
            S.check(P.validate(self.with_profile(kind=stand_in.KIND, effort="high")))
        self.assertEqual(raised.exception.pointer, "/agents/mine/effort")

    def test_claude_code_and_codex_refuse_a_model_that_is_not_a_plain_token(self):
        for kind in ("claude-code", "codex"):
            for bad in ("a b", "x;rm", "high'", ""):
                with self.subTest(kind=kind, bad=bad), self.assertRaises(P.InvalidPolicy) as raised:
                    S.check(P.validate(self.with_profile(kind=kind, model=bad)))
                self.assertEqual(raised.exception.pointer, "/agents/mine/model")
            S.check(P.validate(self.with_profile(kind=kind, model="gpt-5.6-sol", effort="medium")))

    def test_the_plain_token_rule_is_the_kinds_never_the_settings(self):
        """The control: a model the stand-in takes, which a generic plain-token rule would refuse."""
        settings = self.with_profile(kind=stand_in.KIND, model="its model (preview)")
        S.check(P.validate(settings))
        self.assertIsNone(P.PLAIN_TOKEN.fullmatch("its model (preview)"))

    def test_a_kind_no_module_answers_for_is_refused(self):
        with self.assertRaises(P.InvalidPolicy) as raised:
            S.check(P.validate(self.with_profile(kind="deepseek")))
        self.assertEqual(raised.exception.pointer, "/agents/mine/kind")
        self.assertIn("deepseek", str(raised.exception))


class AccessIsTheRolesContract(unittest.TestCase):
    """The architect only reads and the engineer writes, whatever profile each runs; a kind that cannot run a
    role's access is refused for it."""

    def setUp(self):
        stand_in.plant(self, {"writer": stand_in.variant(ACCESS='ACCESS = ("write",)'),
                              "reader": stand_in.variant(ACCESS='ACCESS = ("read",)')})

    def bound(self, role, kind):
        settings = shipped()
        settings["agents"]["mine"] = {"kind": kind}
        settings["roles"][role]["agent"] = "mine"
        return P.validate(settings)

    def test_a_kind_with_no_read_only_mode_is_refused_for_the_architect(self):
        with self.assertRaises(P.InvalidPolicy) as raised:
            S.check(self.bound("architect", "writer"))
        self.assertEqual(raised.exception.pointer, "/roles/architect/agent")
        self.assertIn("read-only", str(raised.exception))
        S.check(self.bound("engineer", "writer"))

    def test_a_kind_that_cannot_write_is_refused_for_the_engineer(self):
        with self.assertRaises(P.InvalidPolicy) as raised:
            S.check(self.bound("engineer", "reader"))
        self.assertEqual(raised.exception.pointer, "/roles/engineer/agent")
        S.check(self.bound("architect", "reader"))

    def test_a_runs_policy_says_each_roles_access_whatever_profile_it_runs(self):
        settings = shipped()
        for profile in settings["agents"]:
            for role in P.ROLES:
                settings["roles"][role]["agent"] = profile
            S.check(settings)
            roles = S.run_policy(settings)["roles"]
            self.assertEqual({role: roles[role]["workspace_access"] for role in P.ROLES}, P.ROLE_ACCESS)

    def test_access_is_no_setting(self):
        settings = shipped()
        settings["roles"]["architect"]["workspace_access"] = "write"
        with self.assertRaises(P.InvalidPolicy) as raised:
            P.validate(settings)
        self.assertEqual(raised.exception.pointer, "/roles/architect/workspace_access")
        # The control: with the key let through, the run's policy still takes the contract's.
        with mock.patch.object(P, "ROLE_KEYS", P.ROLE_KEYS | {"workspace_access"}):
            let_through = P.validate(settings)
        self.assertEqual(S.run_policy(let_through)["roles"]["architect"]["workspace_access"], "read")


class ARunsPolicy(unittest.TestCase):
    """What `client.start` hands a run: whole, and only what the run's flow takes."""

    def test_each_role_carries_its_profiles_values_and_its_personas_text(self):
        settings = shipped()
        policy = S.run_policy(settings)
        for role in P.ROLES:
            profile = settings["agents"][settings["roles"][role]["agent"]]
            carried = policy["roles"][role]
            self.assertEqual({key: carried[key] for key in profile}, profile)
            self.assertEqual(carried["agent"], settings["roles"][role]["agent"])
            with open(os.path.join(PKG, settings["roles"][role]["persona_file"]), encoding="utf-8") as fh:
                self.assertEqual(carried["persona"], fh.read())
        self.assertNotIn("agents", policy)
        self.assertFalse([key for key in policy if key.startswith("_")], "where the settings were read stays behind")

    def test_only_the_skills_of_the_stages_its_flow_takes(self):
        settings = dict(shipped(), stage_skills={"research": "architect", "build": "implement-approved-change"})
        self.assertEqual(S.run_policy(settings, ["architect:research", "you:approve"])["stage_skills"],
                         {"research": "architect"})
        self.assertEqual(S.run_policy(settings)["stage_skills"], {"build": "implement-approved-change"},
                         "a run started with no flow takes the stages those runs took")

    def test_a_new_run_carries_review_rounds_instead_of_the_legacy_budget(self):
        settings = shipped()
        settings.pop("max_rounds", None)
        settings["review_rounds"] = {phase: {"normal": 10, "extended": 10} for phase in P.stages.PHASES}
        policy = S.run_policy(settings)
        self.assertEqual(policy["review_rounds"], settings["review_rounds"])
        self.assertEqual(policy["review_prompts"], settings["review_prompts"])
        self.assertNotIn("max_rounds", policy)

    def test_a_skill_bound_to_a_kind_that_takes_none_is_refused(self):
        stand_in.plant(self, {"skill_less": stand_in.variant(SKILL="SKILL = None")})
        settings = shipped()
        settings["agents"]["mine"] = {"kind": "skill-less"}
        settings["roles"]["engineer"]["agent"] = "mine"
        settings["stage_skills"] = {"plan": "investigate-change"}
        with self.assertRaises(P.InvalidPolicy) as raised:
            S.check(P.validate(settings))
        self.assertEqual(raised.exception.pointer, "/stage_skills/plan")


class Applying(unittest.TestCase):
    """The Settings view's Apply, over a checkout of the test's own: sparse, against the revision it read,
    one at a time, validated whole, and nothing written when refused."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="orchestra-apply-")
        self.addCleanup(__import__("shutil").rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, ".orchestra"))
        shared = {key: value for key, value in shipped().items() if not key.startswith("_")}
        shared["agents"]["spare"] = {"kind": "codex"}
        self.shared = os.path.join(self.root, ".orchestra", "settings.json")
        self.local = os.path.join(self.root, ".orchestra", "settings.local.json")
        with open(self.shared, "w", encoding="utf-8") as fh:
            json.dump(shared, fh, indent=2)
        self.environ = {}

    def read(self):
        return S.read(self.root, self.environ)

    def test_read_exposes_the_combined_review_prompt_limit(self):
        self.assertEqual(self.read()["max_review_prompt_bytes"], P.MAX_REVIEW_PROMPT_BYTES)

    def apply(self, *changes, revision=None):
        return S.apply(list(changes), revision or self.read()["revision"], self.root, self.environ)

    def files(self):
        found = []
        for path in (self.shared, self.local):
            try:
                with open(path, "rb") as fh:
                    found.append(fh.read())
            except FileNotFoundError:
                found.append(None)
        return found

    def patch(self):
        with open(self.local, encoding="utf-8") as fh:
            return json.load(fh)

    def write_patch(self, patch):
        with open(self.local, "w", encoding="utf-8") as fh:
            fh.write(patch if isinstance(patch, str) else json.dumps(patch))

    def test_an_apply_writes_the_settings_it_changes_and_nothing_else(self):
        shown = self.apply({"pointer": "/roles/architect/agent", "value": "codex-architect"})
        self.assertEqual(self.patch(), {"roles": {"architect": {"agent": "codex-architect"}}},
                         "no unchanged shared value copied in")
        self.assertEqual(shown["settings"]["roles"]["architect"]["agent"], "codex-architect")
        self.assertEqual(shown["overrides"], self.patch())

    def test_control_a_writer_that_rebuilds_the_patch_from_the_effective_settings(self):
        """What the sparse writer is there to prevent: every shared value copied into the patch, where it
        would hide a later shared change."""
        rebuilt = P.merge(P.read_settings(self.shared), {"roles": {"architect": {"agent": "codex-architect"}}})
        self.assertIn("timeout_seconds", rebuilt)

    def test_a_hand_written_override_survives_an_apply(self):
        self.write_patch({"timeout_seconds": 90, "targets": {"wsl": {"terminal_port": 8501}}})
        self.apply({"pointer": "/roles/architect/agent", "value": "codex-architect"})
        self.assertEqual(self.patch(), {"timeout_seconds": 90, "targets": {"wsl": {"terminal_port": 8501}},
                                        "roles": {"architect": {"agent": "codex-architect"}}})

    def test_resetting_visible_settings_keeps_hidden_legacy_and_unrelated_local_members(self):
        self.write_patch({
            "timeout_seconds": 90,
            "agents": {"claude-engineer": {"effort": "high"}},
            "roles": {"engineer": {"agent": "codex-engineer"}},
            "stage_skills": {"plan": "architect"},
            "review_rounds": {"plan": {"normal": 3}},
            "review_prompts": {"after_normal": {"engineer": "Re-check the task evidence."}},
            "max_rounds": {"plan": 4, "build": 5},
            "default_flow": "engineer-code",
        })
        changes = [{"pointer": "/%s" % key, "revert": True}
                   for key in ("agents", "roles", "stage_skills", "review_rounds", "review_prompts",
                               "default_flow")]
        shown = S.apply(changes, self.read()["revision"], self.root, self.environ)
        owned = ("agents", "roles", "stage_skills", "review_rounds", "review_prompts", "default_flow")
        self.assertEqual({key: shown["settings"][key] for key in owned},
                         {key: shown["shared"][key] for key in owned})
        self.assertEqual(shown["settings"]["max_rounds"], {"plan": 4, "build": 5})
        self.assertEqual(self.patch(), {"timeout_seconds": 90, "max_rounds": {"plan": 4, "build": 5}},
                         "Reset only reverts visible page-owned settings")

    def test_an_applied_override_survives_a_fresh_read(self):
        self.apply({"pointer": "/review_rounds/plan/normal", "value": 7})
        reloaded = self.read()
        self.assertEqual(reloaded["settings"]["review_rounds"]["plan"]["normal"], 7)
        self.assertEqual(reloaded["overrides"], {"review_rounds": {"plan": {"normal": 7}}})

    def test_a_role_prompt_addition_applies_sparsely_and_reverts(self):
        self.apply({"pointer": "/review_prompts/after_normal/engineer", "value": "Check my assumptions."})
        reloaded = self.read()
        self.assertEqual(reloaded["settings"]["review_prompts"]["after_normal"]["engineer"],
                         "Check my assumptions.")
        self.assertEqual(self.patch(), {"review_prompts": {"after_normal": {"engineer": "Check my assumptions."}}})
        self.apply({"pointer": "/review_prompts/after_normal/engineer", "revert": True})
        self.assertFalse(os.path.exists(self.local), "a prompt patch left empty is no file")

    def test_revert_removes_that_setting_alone_and_the_last_one_the_file(self):
        self.apply({"pointer": "/roles/architect/agent", "value": "codex-architect"},
                   {"pointer": "/review_rounds/plan/normal", "value": 3})
        self.apply({"pointer": "/roles/architect/agent", "revert": True})
        self.assertEqual(self.patch(), {"review_rounds": {"plan": {"normal": 3}}})
        self.apply({"pointer": "/review_rounds/plan/normal", "revert": True})
        self.assertFalse(os.path.exists(self.local), "a patch left empty is no file")

    def test_removing_a_shipped_profile_writes_null(self):
        shown = self.apply({"pointer": "/agents/spare", "remove": True})
        self.assertEqual(self.patch(), {"agents": {"spare": None}})
        self.assertNotIn("spare", shown["settings"]["agents"])

    def test_a_persona_written_in_the_view_takes_the_files_place_until_reverted(self):
        shown = self.apply({"pointer": "/roles/engineer/persona", "value": "Build it small."})
        self.assertEqual(shown["personas"]["engineer"], "Build it small.")
        shown = self.apply({"pointer": "/roles/engineer/persona", "revert": True})
        with open(os.path.join(PKG, "roles", "engineer.md"), encoding="utf-8") as fh:
            self.assertEqual(shown["personas"]["engineer"], fh.read())

    def test_a_refused_apply_names_its_setting_and_changes_nothing(self):
        before = self.files()
        with self.assertRaises(P.InvalidPolicy) as raised:
            self.apply({"pointer": "/agents/codex-engineer/model", "value": "a b"})
        self.assertEqual(raised.exception.pointer, "/agents/codex-engineer/model")
        self.assertEqual(self.files(), before)

    def test_an_apply_against_a_revision_either_file_has_left_changes_nothing(self):
        for path in (self.local, self.shared):
            with self.subTest(edited=os.path.basename(path)):
                revision = self.read()["revision"]
                with open(path, "a" if path == self.shared else "w", encoding="utf-8") as fh:
                    fh.write("\n" if path == self.shared else '{"timeout_seconds": 70}')
                before = self.files()
                with self.assertRaises(S.Stale):
                    self.apply({"pointer": "/review_rounds/plan/normal", "value": 3}, revision=revision)
                self.assertEqual(self.files(), before)

    def racing(self, lock):
        """Two Applies on one revision, each held after its revision's check until the other has checked
        too, or for two seconds; returns how each ended."""
        revision, met = self.read()["revision"], threading.Barrier(2, timeout=2)
        write = P.write_patch
        ordering = threading.Lock()
        first_writer = [None]
        first_apply_returned = threading.Event()

        def held(local, patch):
            try:
                met.wait()
            except threading.BrokenBarrierError:
                pass
            current = threading.current_thread()
            with ordering:
                if first_writer[0] is None:
                    first_writer[0] = current
                    first = True
                else:
                    first = current is first_writer[0]
            if not first:
                # Let the first apply finish its readback before replacing on Windows, where an open
                # reader can make os.replace fail with a sharing violation unrelated to the apply lock.
                first_apply_returned.wait(5)
            write(local, patch)
        ended = []

        def one(value):
            try:
                self.apply({"pointer": "/review_rounds/plan/normal", "value": value}, revision=revision)
                ended.append("landed")
            except S.Stale:
                ended.append("stale")
            finally:
                if threading.current_thread() is first_writer[0]:
                    first_apply_returned.set()
        with mock.patch.object(P, "write_patch", held), mock.patch.object(S, "_APPLYING", lock):
            threads = [threading.Thread(target=one, args=(value,)) for value in (3, 4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(30)
        return sorted(ended)

    def test_two_applies_on_one_revision_one_lands_and_the_other_is_stale(self):
        self.assertEqual(self.racing(threading.Lock()), ["landed", "stale"])

    def test_control_without_the_lock_both_land(self):
        self.assertEqual(self.racing(contextlib.nullcontext()), ["landed", "landed"])

    def test_while_the_local_patch_does_not_load_the_view_says_why_and_takes_no_apply(self):
        self.write_patch("{")
        shown = self.read()
        self.assertFalse(shown["writable"])
        self.assertIn("settings.local.json", shown["refused"]["reason"])
        before = self.files()
        with self.assertRaises(P.InvalidPolicy):
            self.apply({"pointer": "/review_rounds/plan/normal", "value": 3})
        self.assertEqual(self.files(), before)

    def test_settings_a_stack_was_named_take_no_apply_and_the_checkouts_patch_is_left_alone(self):
        self.write_patch({"timeout_seconds": 90})
        with tempfile.TemporaryDirectory() as elsewhere:
            named = os.path.join(elsewhere, "settings.json")
            with open(self.shared, encoding="utf-8") as fh, open(named, "w", encoding="utf-8") as out:
                out.write(fh.read())
            self.environ = {P.VARIABLE: named}
            self.assertFalse(self.read()["writable"])
            before = self.files()
            with self.assertRaises(S.ReadOnly):
                self.apply({"pointer": "/review_rounds/plan/normal", "value": 3})
            self.assertEqual(self.files(), before, "the operator's own patch, byte for byte")
            # The control: an Apply that ignored where its settings came from writes the operator's patch.
            sources = P.sources
            with mock.patch.object(P, "sources", lambda path=None, root=None, environ=None: sources(path, root, {})):
                self.apply({"pointer": "/review_rounds/plan/normal", "value": 3})
            self.assertNotEqual(self.files(), before)

    def test_the_kinds_and_how_each_invokes_a_skill_come_from_the_adapters(self):
        from app.agents import adapters
        shown = self.read()
        self.assertEqual(shown["kinds"], adapters.available())
        kinds = {kind["kind"]: kind for kind in shown["kinds"]}
        self.assertEqual((kinds["claude-code"]["skill"], kinds["codex"]["skill"]), ("/{name}", "${name}"))

    def test_skill_discovery_uses_adapter_roots_and_returns_names_only(self):
        folders = (os.path.join(self.root, ".claude", "skills", "repo-method"),
                   os.path.join(self.root, ".agents", "skills", "repo-tool"))
        for folder in folders:
            os.makedirs(folder)
            with open(os.path.join(folder, "SKILL.md"), "w", encoding="utf-8") as fh:
                fh.write("---\nname: %s\n---\n" % os.path.basename(folder))
        os.makedirs(os.path.join(self.root, ".claude", "skills", "empty-method"))
        shown = self.read()
        self.assertIn("repo-method", shown["skills"]["claude-code"])
        self.assertIn("repo-tool", shown["skills"]["codex"])
        self.assertNotIn("empty-method", shown["skills"]["claude-code"])
        encoded = json.dumps(shown["skills"])
        self.assertNotIn(self.root, encoded)
        self.assertTrue(all(isinstance(name, str) and os.path.basename(name) == name
                            for names in shown["skills"].values() for name in names))


def calls_to_policy_load(root, owner):
    """Every call of `policy.load` in a module under `root` other than `owner`, as (file, line)."""
    found = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in sorted(files):
            path = os.path.join(base, name)
            if not name.endswith(".py") or os.path.normcase(path) == os.path.normcase(owner):
                continue
            with open(path, encoding="utf-8") as handle:
                tree = ast.parse(handle.read(), filename=path)
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "load"
                        and isinstance(node.func.value, ast.Name) and node.func.value.id in ("P", "policy", "policy_mod")):
                    found.append((os.path.relpath(path, root).replace(os.sep, "/"), node.lineno))
    return found


class OneLoader(unittest.TestCase):
    """Everything loads settings through `application.settings`, so no loader skips a kind's own checks."""

    OWNER = os.path.join(PKG, "app", "application", "settings.py")

    def test_no_other_production_module_loads_the_settings_file_itself(self):
        self.assertEqual(calls_to_policy_load(os.path.join(PKG, "app"), self.OWNER), [])

    def test_it_sees_a_module_that_does(self):
        """The control: a load planted in another module."""
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "worker.py"), "w", encoding="utf-8") as fh:
                fh.write("from app.foundation import policy as P\nsettings = P.load()\n")
            self.assertEqual(calls_to_policy_load(root, self.OWNER), [("worker.py", 2)])


WARNING = 256 * 1024
# Each class of character the converter treats its own way: kept as ASCII, escaped as `\"` or `\n`,
# escaped as `\uXXXX` whatever its UTF-8 length, or as a surrogate pair, and control characters.
CONTENT = {"ascii letters": "a", "quotes": '"', "newlines": "\n", "2-byte": "и", "3-byte": "中",
           "4-byte": "\U0001F600", "control": "\x01"}


def largest_recorded_run_role():
    """The `run_role` input of the recorded histories that is largest on the wire."""
    inputs = []
    for path in sorted(glob.glob(os.path.join(HERE, "histories", "*.json"))):
        with open(path, encoding="utf-8") as fh:
            events = json.load(fh).get("events", [])
        for event in events:
            attrs = next((value for key, value in event.items()
                          if key.lower().startswith("activitytaskscheduled") and isinstance(value, dict)), None)
            if attrs and (attrs.get("activityType") or {}).get("name") == "run_role":
                inputs += [json.loads(base64.b64decode(payload["data"]))
                           for payload in (attrs.get("input") or {}).get("payloads", [])]
    return max(inputs, key=wire_bytes)


def wire_bytes(value):
    """What Temporal measures of an activity's input: its `Payloads`, by the converter this project runs on."""
    from temporalio.api.common.v1 import Payloads
    from temporalio.converter import DataConverter
    return Payloads(payloads=DataConverter.default.payload_converter.to_payloads([value])).ByteSize()


class ThePersonaBoundHoldsOnTheWire(unittest.TestCase):
    """Both personas at the bound, in the largest turn input the recorded runs hold, stay under Temporal's
    payload warning for every class of character."""

    @classmethod
    def setUpClass(cls):
        cls.recorded = largest_recorded_run_role()

    def turn_input(self, text):
        settings = shipped()
        for role in P.ROLES:
            settings["roles"][role]["persona"] = text
        return dict(self.recorded, policy=S.run_policy(P.validate(settings)))

    def of_bytes(self, unit, limit):
        return unit * (limit // len(unit.encode("utf-8")))

    def test_every_class_of_character_at_the_bound_stays_under_the_warning(self):
        for label, unit in CONTENT.items():
            with self.subTest(content=label):
                self.assertLess(wire_bytes(self.turn_input(self.of_bytes(unit, P.MAX_PERSONA_BYTES))), WARNING)

    def test_control_a_bound_of_64_kib_crosses_it_for_two_byte_text(self):
        with mock.patch.object(P, "MAX_PERSONA_BYTES", 64 * 1024):
            self.assertGreater(wire_bytes(self.turn_input(self.of_bytes("и", 64 * 1024))), WARNING)


if __name__ == "__main__":
    unittest.main()
