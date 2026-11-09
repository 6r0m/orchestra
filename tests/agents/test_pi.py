"""Pi's interactive turn contract, exercised without a model or a provider credential."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from unittest import mock

from app.agents import adapters
from app.agents import terminal
from app.agents import launch


class PiContract(unittest.TestCase):
    def setUp(self):
        self.pi = adapters.load("pi")

    def event(self, hook, **fields):
        return dict(_hook=hook, session_id="session-1", session_file="/session.jsonl", **fields)

    def test_launcher_provider_and_exact_session_are_one_command_contract(self):
        role = dict(provider="deepseek", model="deepseek-flash", effort="max", launcher="pi-sot", workspace_access="write")
        argv, minted = self.pi.command(role, None)
        self.assertEqual(argv[0], "pi-sot")
        self.assertEqual(argv[argv.index("--provider") + 1], "deepseek")
        self.assertEqual(argv[argv.index("--thinking") + 1], "max")
        self.assertEqual(self.pi.session_in(argv), minted)
        resumed, fresh = self.pi.command(role, "/session.jsonl")
        self.assertIsNone(fresh)
        self.assertEqual(resumed[resumed.index("--session") + 1], "/session.jsonl")
        self.assertEqual(resumed[resumed.index("--orchestra-resume-session") + 1], "/session.jsonl")
        self.assertNotIn("--continue", resumed)
        role["workspace_access"] = "read"
        readonly, _ = self.pi.command(role, None)
        self.assertIn("--no-mcp", readonly)
        self.assertEqual(readonly[readonly.index("--tools") + 1], "read,grep,find,ls")

    def test_project_trust_is_never_overridden_by_either_role(self):
        for access in ("read", "write"):
            for session in (None, "/session.jsonl"):
                argv, _ = self.pi.command({"workspace_access": access}, session)
                self.assertFalse({"--approve", "-a", "--no-approve", "-na"} & set(argv))

    def test_an_unknown_projects_trust_dialog_is_reported_without_answering_it(self):
        dialog = "Trust project folder?\n/path/to/repo\n\nThis allows pi to load .pi settings and resources, " \
                 "install missing project packages, and execute project extensions.\nTrust\nDo not trust"
        self.assertIn("role's terminal", self.pi.held(dialog))
        self.assertIn("project extensions", self.pi.held(dialog))
        self.assertIsNone(self.pi.held("A tool quoted: Trust project folder?"))
        self.assertIsNone(self.pi.held("Pi is working"))

    def test_only_the_controller_prompt_and_final_settlement_end_a_turn(self):
        events = [self.event("PiInput", prompt="another task"), self.event("PiSettled", ok=True, answer="foreign")]
        self.assertIsNone(self.pi.completion(events, "our task", "session-1"))
        events += [self.event("PiInput", prompt="our task"), self.event("PiAgentEnd", answer="not settled")]
        self.assertIsNone(self.pi.completion(events, "our task", "session-1"))
        events += [self.event("PiInterrupted")]
        self.assertIsNone(self.pi.completion(events, "our task", "session-1"), "Esc completes nothing")
        events += [self.event("PiInput", prompt="go on"), self.event("PiSettled", ok=True, answer="finished", _at=5)]
        ok, message, session = self.pi.completion(events, "our task", "session-1")
        out = self.pi.output(message, session)
        self.assertTrue(ok)
        self.assertEqual(self.pi.final_message(out), "finished")
        self.assertEqual(self.pi.session(out, None), "/session.jsonl")
        self.assertIsNone(self.pi.completion(events, "our task", "/other.jsonl"))
        self.assertIsNone(self.pi.reply(events, "our task", "/session.jsonl"))
        events += [self.event("PiInput", prompt="a manual question"), self.event("PiSettled", ok=True, answer="manual", _at=9)]
        self.assertEqual(self.pi.reply(events, "our task", "/session.jsonl"), ("manual", 9))

    def test_failed_settlement_is_an_error_and_provider_options_are_validated(self):
        events = [self.event("PiInput", prompt="our task"), self.event("PiSettled", ok=False, answer="API failed")]
        self.assertFalse(self.pi.completion(events, "our task", "/session.jsonl")[0])
        self.assertFalse(self.pi.validate(dict(kind="pi", provider="deepseek", model="deepseek-flash", effort="max")))
        for wrong in ({"effort": "infinite"}, {"launcher": "bad; command"}, {"api_key": "not a setting"}):
            self.assertTrue(self.pi.validate(dict(kind="pi", **wrong)))

    def test_skills_in_registered_local_packages_are_discovered(self):
        with tempfile.TemporaryDirectory() as folder:
            agent, package = os.path.join(folder, "agent"), os.path.join(folder, "package")
            os.makedirs(agent)
            skill = os.path.join(package, "skills", "method")
            os.makedirs(skill)
            with open(os.path.join(skill, "SKILL.md"), "w") as fh:
                fh.write("a method")
            with open(os.path.join(package, "package.json"), "w") as fh:
                json.dump({"pi": {"skills": ["skills/*/SKILL.md"]}}, fh)
            with open(os.path.join(agent, "settings.json"), "w") as fh:
                json.dump({"packages": [package]}, fh)
            self.assertIn(skill, self.pi.skill_folders("method", folder, agent_dir=agent))

    def test_upload_keeps_exclusive_usage_and_reports_missing_evidence(self):
        context = {"traceparent": "parent", "metadata": {"run_id": "test", "stage": "plan", "episode": 1, "round": 1}}
        generation = self.event("PiGeneration", model="a-model", answer="answer", provider="a-provider",
                                usage={"input": 5, "output": 3, "cacheRead": 7, "cacheWrite": 0, "cost": {"total": 123}})
        with mock.patch.object(terminal, "turn_attempts", return_value=[{"events": "unused"}]), \
                mock.patch.object(terminal, "_events", return_value=[generation]):
            described = self.pi.upload("/session.jsonl", context)
            self.assertEqual(described["generations"][0]["usage_details"],
                             {"input": 5, "output": 3, "input_cached_tokens": 7, "input_cache_creation_tokens": 0})
            self.assertNotIn("cost_details", described["generations"][0])
            generation["usage"].pop("cacheRead")
            unknown = self.pi.upload(None, context)
            self.assertIsNone(unknown["generations"][0]["usage_details"])
            self.assertTrue(unknown.get("notes"), "missing buckets must degrade telemetry")
        with mock.patch.object(terminal, "turn_attempts", return_value=[]):
            self.assertTrue(self.pi.upload("/session.jsonl", context).get("notes"), "no generation is not free usage")


@unittest.skipUnless(shutil.which("node"), "Pi's extension bridge requires Node")
class PiBridge(unittest.TestCase):
    def run_bridge(self, script, folder, expected=None, version="1.1.0"):
        pi = adapters.load("pi")
        setup = """
import fs from 'node:fs';
import vm from 'node:vm';
const module = new vm.SourceTextModule(fs.readFileSync(new URL(process.argv[1]), 'utf8'));
await module.link(async name => {
  const values = name === '@earendil-works/pi-coding-agent' ? {VERSION: process.env.PI_TEST_VERSION} : await import(name);
  return new vm.SyntheticModule(Object.keys(values), function() {
    for (const [key, value] of Object.entries(values)) this.setExport(key, value);
  });
});
await module.evaluate();
const bridge = module.namespace.default;
const events = {};
const api = {on: (name, fn) => events[name] = fn, registerFlag: () => {}, getFlag: () => process.env.EXPECTED_SESSION};
bridge(api);
const ctx = {sessionManager: {getSessionId: () => 's', getSessionFile: () => process.env.SESSION_FILE || '/s.jsonl',
  getEntries: () => process.env.EMPTY_HISTORY ? [] : [{type:'message', message:{role:'assistant'}}]}};
"""
        return subprocess.run([shutil.which("node"), "--experimental-vm-modules", "--input-type=module", "-e", setup + script,
                               __import__("pathlib").Path(pi.BRIDGE).as_uri()],
                              env=dict(os.environ, ORCHESTRA_TURN_EVENTS=os.path.join(folder, "events"),
                                       EXPECTED_SESSION=expected or "", SESSION_FILE=expected or "/s.jsonl", PI_TEST_VERSION=version),
                              capture_output=True, text=True, timeout=15)

    def test_aborted_settlement_after_a_tool_call_skips_before_settle_and_cannot_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.run_bridge("""
events.input({text:'our task'}, ctx);
events.message_end({message:{role:'assistant', content:[{type:'text',text:'I will do this'}], stopReason:'toolUse'}}, ctx);
events.agent_settled({aborted:true}, ctx);
""", folder)
            self.assertEqual(result.returncode, 0, result.stderr)
            with open(os.path.join(folder, "events")) as fh:
                events = [json.loads(line) for line in fh]
            self.assertEqual(events[-1]["_hook"], "PiInterrupted")
            self.assertIsNone(adapters.load("pi").completion(events, "our task", "s"))

    def test_a_runtime_without_reliable_abort_reporting_is_refused_before_work(self):
        with tempfile.TemporaryDirectory() as folder:
            for version in ("1.0.4", "0.99.1", "unknown", "1.1.0-dev"):
                result = self.run_bridge("process.stdout.write('work started');", folder, version=version)
                self.assertEqual(result.returncode, 1, version)
                self.assertIn("Pi 1.1.0 or newer", result.stderr)
                self.assertNotIn("work started", result.stdout)
                self.assertFalse(os.path.exists(os.path.join(folder, "events")))

    def test_missing_abort_status_or_an_incomplete_assistant_never_means_success(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.run_bridge("""
for (const [stopReason, status] of [['stop', {}], ['toolUse', {aborted:false}], ['length', {aborted:false}]]) {
  events.input({text:'our task'}, ctx);
  events.message_end({message:{role:'assistant', content:[], stopReason}}, ctx);
  events.agent_settled(status, ctx);
}
""", folder)
            self.assertEqual(result.returncode, 0, result.stderr)
            with open(os.path.join(folder, "events")) as fh:
                settled = [json.loads(line) for line in fh if json.loads(line)["_hook"] == "PiSettled"]
            self.assertEqual(len(settled), 3)
            self.assertTrue(all(row["ok"] is False for row in settled))

    def test_resume_requires_the_existing_exact_session_before_work(self):
        with tempfile.TemporaryDirectory() as folder:
            session = os.path.join(folder, "session.jsonl")
            start = "events.session_start({}, ctx); process.stdout.write('allowed');"
            absent = self.run_bridge(start, folder, session)
            self.assertEqual(absent.returncode, 1)
            self.assertIn("Pi session not found before work", absent.stderr)
            self.assertNotIn("allowed", absent.stdout)
            self.assertFalse(os.path.exists(session), "refusal creates no conversation")
            for value, allowed in (("not JSON\n", False), ('{"type":"session","id":"other"}\n', False),
                                   ('{"type":"session","id":"s"}\n', True)):
                with open(session, "w", encoding="utf-8") as fh:
                    fh.write(value)
                result = self.run_bridge(start, folder, session)
                self.assertEqual(result.returncode, 0 if allowed else 1, result.stderr)
                self.assertEqual("allowed" in result.stdout, allowed)
                with open(session, encoding="utf-8") as fh:
                    self.assertEqual(fh.read(), value, "validation leaves session bytes unchanged")
                if not allowed:
                    self.assertNotIn("not found", result.stderr, "unreadable identity is not proof of session loss")
            result = self.run_bridge("ctx.sessionManager.getEntries = () => []; " + start, folder, session)
            self.assertEqual(result.returncode, 1, "a header-only replacement cannot resume a completed conversation")
            self.assertNotIn("allowed", result.stdout)

    def test_abort_and_error_settlement_are_never_success(self):
        with tempfile.TemporaryDirectory() as folder:
            script = """
events.input({text: 'task'}, ctx);
events.message_end({message: {role:'assistant', content:[], stopReason:'aborted'}}, ctx);
events.agent_settled({aborted:true}, ctx);
events.input({text: 'continue'}, ctx);
events.message_end({message: {role:'assistant', content:[], stopReason:'error', errorMessage:'provider failed'}}, ctx);
events.agent_settled({aborted:false}, ctx);
"""
            result = self.run_bridge(script, folder)
            self.assertEqual(result.returncode, 0, result.stderr)
            with open(os.path.join(folder, "events")) as fh:
                events = [json.loads(line) for line in fh]
            self.assertEqual(events[2]["_hook"], "PiInterrupted")
            self.assertFalse(events[-1]["ok"])
            self.assertEqual(events[-1]["answer"], "provider failed")

    def test_bridge_reports_native_usage_and_only_finishes_when_settled(self):
        script = r"""
events.input({text: 'our task', source: 'interactive'}, ctx);
events.message_end({message: {role: 'assistant', content: [{type: 'text', text: 'answer'}],
  provider: 'deepseek', model: 'deepseek-flash', api: 'openai-completions', stopReason: 'stop',
  usage: {input: 12, output: 3, cacheRead: 7, cacheWrite: 0, cost: {total: 123}}}}, ctx);
if (events.agent_end) events.agent_end({messages: []}, ctx);
events.agent_settled({aborted:false}, ctx);
"""
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "events")
            result = self.run_bridge(script, folder)
            self.assertEqual(result.returncode, 0, result.stderr)
            with open(path) as fh:
                events = [json.loads(line) for line in fh]
            self.assertEqual([event["_hook"] for event in events], ["PiInput", "PiGeneration", "PiSettled"])
            self.assertEqual(events[1]["usage"]["cacheRead"], 7)
            self.assertEqual(events[-1]["answer"], "answer")
            self.assertTrue(events[-1]["ok"])


class PiHeldStart(unittest.TestCase):
    def test_an_unanswered_project_trust_prompt_fails_early_without_executing_or_saving_trust(self):
        run_id = "test-pi-trust-" + uuid.uuid4().hex[:8]
        self.addCleanup(shutil.rmtree, terminal.run_dir(run_id), True)
        self.addCleanup(terminal.close_run, run_id)
        with tempfile.TemporaryDirectory() as folder:
            extensions = os.path.join(folder, ".pi", "extensions")
            os.makedirs(extensions)
            marker, trust = os.path.join(folder, "executed"), os.path.join(folder, "trust.json")
            with open(os.path.join(extensions, "unapproved.ts"), "w") as fh:
                fh.write("export default function () {}\n")
            script = os.path.join(folder, "standin.py")
            with open(script, "w", encoding="utf-8") as fh:
                fh.write("import pathlib, sys\n"
                         "if '--approve' in sys.argv or '-a' in sys.argv:\n"
                         " pathlib.Path('executed').write_text('project extension ran')\n"
                         " raise SystemExit(0)\n"
                         "print('Trust project folder?\\n/path/to/repo\\nThis allows pi to load .pi settings and resources, "
                         "install missing project packages, and execute project extensions.\\nTrust\\nDo not trust', flush=True)\n"
                         "sys.stdin.read()\n")
            executable = os.path.join(folder, "test-pi" + (".cmd" if os.name == "nt" else ""))
            with open(executable, "w", encoding="utf-8", newline="") as fh:
                fh.write('@"%s" "%s" %%*\r\n' % (sys.executable, script) if os.name == "nt"
                         else '#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, script))
            os.chmod(executable, 0o755)
            argv, _ = adapters.load("pi").command({"launcher": "test-pi", "workspace_access": "read"}, None)
            argv[0] = executable
            started = time.monotonic()
            try:
                with mock.patch.object(terminal, "BEGIN_SECONDS", 1), mock.patch.object(terminal, "TICK_SECONDS", .05):
                    with self.assertRaisesRegex(launch.ExecutorError, "role's terminal"):
                        terminal.run_turn(folder, argv, terminal.run_dir(run_id), "assess-e1-1", "Inspect it", 172800,
                                          dict(os.environ), on_tick=lambda: None, kind="pi")
                self.assertLess(time.monotonic() - started, 20)
                self.assertFalse(terminal.get(run_id, "architect").live())
                self.assertFalse(os.path.exists(marker))
                self.assertFalse(os.path.exists(trust))
            finally:
                terminal.close_run(run_id)
