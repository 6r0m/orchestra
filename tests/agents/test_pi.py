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
from app.agents import nodes


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

    def test_multiline_skill_arguments_keep_the_native_literal_space_separator(self):
        prompt = nodes.render([{"part": "skill", "text": adapters.skill(self.pi, "method") + "\n"},
                               {"part": "instructions", "text": "Complete the stage\nwith its full tail"}])
        # Pi extracts its skill name up to the first literal space, rather than any whitespace.
        command, separator, arguments = prompt.partition(" ")
        self.assertEqual(command, "/skill:method")
        self.assertEqual(separator, " ")
        self.assertIn("Complete the stage\nwith its full tail", arguments)

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

    def native_generation(self, cost=None, **fields):
        event = self.event("PiGeneration", model="requested-model", provider="a-provider", api="an-api",
                           usage={"input": 5, "output": 3, "cacheRead": 7, "cacheWrite": 0, "cost": cost},
                           **fields)
        context = {"traceparent": "parent", "metadata": {
            "run_id": "test", "stage": "plan", "episode": 1, "round": 1}}
        with mock.patch.object(terminal, "turn_attempts", return_value=[{"events": "unused"}]), \
                mock.patch.object(terminal, "_events", return_value=[event]):
            return self.pi.upload("/session.jsonl", context)["generations"][0]

    def test_native_request_identity_and_catalog_cost_provenance_are_preserved(self):
        generation = self.native_generation({"total": 1.25, "totalFromProvider": False},
                                            request_timestamp_ms=1700000000123,
                                            response_id="response-1", response_model="actual-model")
        meta = generation["metadata"]
        self.assertEqual(meta.get("request_timestamp_ms"), 1700000000123)
        self.assertEqual(meta.get("response_id"), "response-1")
        self.assertEqual(meta.get("response_model"), "actual-model")
        self.assertEqual(generation["model"], "requested-model")
        self.assertEqual(meta.get("native_cost_total"), 1.25)
        self.assertIs(meta.get("native_cost_total_from_provider"), False)
        self.assertEqual(meta.get("native_cost_source"), "catalog_estimate")
        self.assertEqual(meta["cost_source"], "model_price_inference")
        self.assertEqual(meta.get("billing_coverage"), "unknown")
        self.assertNotIn("cost_details", generation)

    def test_only_valid_explicit_provider_totals_are_supplied_as_costs(self):
        for flag in (True, False, None, "true"):
            for amount in (0, 1.25, -1, True, "1.25", float("nan"), float("inf"), 10 ** 1000):
                with self.subTest(flag=flag, amount=amount):
                    generation = self.native_generation({"total": amount, "totalFromProvider": flag})
                    if flag is True and type(amount) in (float, int) and amount in (0, 1.25):
                        self.assertEqual(generation.get("cost_details"), {"total": amount})
                        self.assertEqual(generation["metadata"]["cost_source"], "provider_reported")
                    else:
                        self.assertNotIn("cost_details", generation)
                        self.assertNotEqual(generation["metadata"]["cost_source"], "provider_reported")

    def test_missing_or_invalid_native_time_is_not_replaced_by_capture_time(self):
        for timestamp in (None, False, -1, "1700000000123", float("nan"), float("inf"), 10 ** 1000):
            with self.subTest(timestamp=timestamp):
                meta = self.native_generation(request_timestamp_ms=timestamp, _at=1700000999)["metadata"]
                self.assertNotIn("request_timestamp_ms", meta)
                self.assertEqual(meta.get("request_time_source"), "unknown")

    def test_a_provider_total_does_not_claim_complete_token_or_billing_coverage(self):
        event = self.event("PiGeneration", usage={"cost": {"total": 0.25, "totalFromProvider": True}})
        context = {"traceparent": "parent", "metadata": {
            "run_id": "test", "stage": "plan", "episode": 1, "round": 1}}
        with mock.patch.object(terminal, "turn_attempts", return_value=[{"events": "unused"}]), \
                mock.patch.object(terminal, "_events", return_value=[event]):
            described = self.pi.upload("/session.jsonl", context)
        generation = described["generations"][0]
        self.assertEqual(generation["cost_details"], {"total": 0.25})
        self.assertIsNone(generation["usage_details"])
        self.assertFalse(generation["metadata"]["usage_complete"])
        self.assertEqual(generation["metadata"]["billing_coverage"], "unknown")
        self.assertTrue(described["notes"])


@unittest.skipUnless(shutil.which("node"), "Pi's extension bridge requires Node")
class PiBridge(unittest.TestCase):
    def run_bridge(self, script, folder, expected=None, version="1.5.0", environ=None):
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
                              env={**os.environ, "ORCHESTRA_TURN_EVENTS": os.path.join(folder, "events"),
                                   "EXPECTED_SESSION": expected or "", "SESSION_FILE": expected or "/s.jsonl",
                                   "PI_TEST_VERSION": version, **(environ or {})},
                              capture_output=True, text=True, timeout=15)

    def test_multiline_prompt_survives_a_launcher_that_passes_only_its_first_line(self):
        pi = adapters.load("pi")
        parts = [{"part": "skill", "text": '/skill:method \n'},
                 {"part": "task", "text": 'Read the whole task, including "quotes", %VARIABLE% and &.\nUnicode: \u2713'},
                 {"part": "persona", "text": "Saved engineer"},
                 {"part": "instructions", "text": "Implement the approved todo"}]
        prompt = nodes.render(parts)
        with tempfile.TemporaryDirectory(prefix="pi prompt ") as folder:
            terminal.record_parts(folder, "build-e1-1", parts)
            term = mock.Mock()
            observed = {}

            def started(argv, cwd, env):
                supplied = argv[-1].splitlines()[0]
                script = """
const typed = %s;
const result = events.input({text:typed,source:'interactive'},ctx);
const actual = result?.action === 'transform' ? result.text : typed;
events.message_end({message:{role:'assistant',content:[{type:'text',text:actual}],stopReason:'stop'}},ctx);
events.agent_settled({aborted:false},ctx);
""" % json.dumps(supplied)
                child = self.run_bridge(script, folder, environ=env)
                self.assertEqual(child.returncode, 0, child.stderr)
                observed.update(argv=argv, env=env)
                return type("Agent", (), {"output": bytearray(), "heard": time.monotonic(),
                    "pump": mock.Mock(), "returncode": lambda self: None})()

            term.start.side_effect = started
            which = shutil.which
            with mock.patch.object(terminal, "open_terminal", return_value=term), \
                    mock.patch.object(terminal.shutil, "which", side_effect=lambda name: "pi" if name == "pi" else which(name)), \
                    mock.patch.object(terminal, "TICK_SECONDS", 0.01):
                rc, out = terminal.run_turn(folder, ["pi", "--session-id", "s"], folder, "build-e1-1",
                                           prompt, 0.15, {}, on_tick=lambda: None, kind="pi")
            self.assertEqual((rc, pi.final_message(out)), (0, prompt))
            self.assertNotIn(prompt, observed["argv"])
            self.assertNotIn("\n", observed["argv"][-1])
            path = terminal.turn_files(folder, "build-e1-1")["prompt"]
            self.assertNotIn(path, observed["argv"])
            with open(path, encoding="utf-8", newline="") as stream:
                self.assertEqual(stream.read(), prompt)

    def test_native_system_section_projects_only_the_current_recorded_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            files = terminal.turn_files(folder, "build-e1-2")
            parts = [{"part": "skill", "text": "/skill:method \n"},
                     {"part": "task", "text": "Current task"},
                     {"part": "persona", "text": "Saved engineer. Never commit."},
                     {"part": "instructions", "text": "# Current stage: build\nImplement the approved todo."},
                     {"part": "findings", "text": "Dynamic feedback"}]
            terminal.record_parts(folder, "build-e1-2", parts)
            with open(files["prompt"], "w", encoding="utf-8", newline="") as stream:
                stream.write(nodes.render(parts))
            result = self.run_bridge("""
const options = {sections:{existing:'Keep native and other extension instructions'}};
events.before_agent_start({systemPromptOptions:options},ctx);
const anchor = options.sections.orchestra_turn;
if (typeof anchor !== 'string' || !anchor.includes('Saved engineer. Never commit.')
  || !anchor.includes('# Current stage: build') || !anchor.includes('/skill:method')
  || !anchor.includes('Current task') || anchor.includes('Dynamic feedback')) process.exit(8);
events.before_agent_start({systemPromptOptions:options},ctx);
if (options.sections.orchestra_turn !== anchor || options.sections.existing !== 'Keep native and other extension instructions'
  || options.forceSystemPrompt !== undefined) process.exit(9);
""", folder, version="1.5.0", environ={"ORCHESTRA_PI_PROMPT_FILE": files["prompt"],
                "ORCHESTRA_PI_INPUT_TOKEN": "token", "ORCHESTRA_PI_PARTS_FILE": files["parts"]})
            self.assertEqual(result.returncode, 0, result.stderr)

            missing_api = self.run_bridge("events.before_agent_start({systemPromptOptions:{}},ctx); console.log('work began');",
                folder, environ={"ORCHESTRA_PI_PROMPT_FILE": files["prompt"], "ORCHESTRA_PI_INPUT_TOKEN": "token",
                                 "ORCHESTRA_PI_PARTS_FILE": files["parts"]})
            self.assertNotEqual(missing_api.returncode, 0)
            self.assertNotIn("work began", missing_api.stdout)

    def test_a_missing_or_mismatched_recorded_contract_refuses_before_input(self):
        for case in ("missing", "malformed", "wrong-prompt", "no-persona", "no-instructions"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                files = terminal.turn_files(folder, "build-e1-1")
                parts = [{"part": "persona", "text": "Saved role"},
                         {"part": "task", "text": "Task"}, {"part": "instructions", "text": "Stage contract"}]
                if case.startswith("no-"):
                    parts = [part for part in parts if part["part"] != case[3:]]
                terminal.record_parts(folder, "build-e1-1", parts)
                with open(files["prompt"], "w", encoding="utf-8", newline="") as stream:
                    stream.write("different" if case == "wrong-prompt" else nodes.render(parts))
                if case == "malformed":
                    with open(files["parts"], "w", encoding="utf-8") as stream:
                        stream.write("not JSON")
                env = {"ORCHESTRA_PI_PROMPT_FILE": files["prompt"], "ORCHESTRA_PI_INPUT_TOKEN": "token"}
                if case != "missing":
                    env["ORCHESTRA_PI_PARTS_FILE"] = files["parts"]
                result = self.run_bridge("console.log('work began');", folder, version="1.5.0", environ=env)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("work began", result.stdout)
                self.assertFalse(os.path.exists(files["events"]))

    def test_prompt_transport_refuses_missing_files_incomplete_parameters_and_wrong_input_before_work(self):
        for case in ("missing-file", "missing-token", "missing-path", "wrong-input", "empty-file"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                path = os.path.join(folder, "prompt.txt")
                parts = [{"part": "task", "text": "controller task\nwith its full tail"},
                         {"part": "persona", "text": "Saved role"}, {"part": "instructions", "text": "Current stage"}]
                terminal.record_parts(folder, "build-e1-1", parts)
                original = "" if case == "empty-file" else nodes.render(parts)
                if case != "missing-file":
                    with open(path, "w", encoding="utf-8", newline="") as stream:
                        stream.write(original)
                env = {"ORCHESTRA_PI_PROMPT_FILE": path, "ORCHESTRA_PI_INPUT_TOKEN": "expected-input",
                       "ORCHESTRA_PI_PARTS_FILE": terminal.turn_files(folder, "build-e1-1")["parts"]}
                if case == "missing-token":
                    env.pop("ORCHESTRA_PI_INPUT_TOKEN")
                if case == "missing-path":
                    env.pop("ORCHESTRA_PI_PROMPT_FILE")
                result = self.run_bridge("events.input({text:'wrong-input',source:'interactive'},ctx);", folder, environ=env)
                self.assertNotEqual(result.returncode, 0)
                if case == "wrong-input":
                    self.assertIn("did not receive the controller input token", result.stderr)
                self.assertFalse(os.path.exists(os.path.join(folder, "events")), "refusal cannot record a begun turn")
                if os.path.exists(path):
                    with open(path, encoding="utf-8", newline="") as stream:
                        self.assertEqual(stream.read(), original)

    def test_transport_applies_once_and_operator_followups_remain_ordinary_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "prompt.txt")
            parts = [{"part": "task", "text": "controller task\ncomplete"},
                     {"part": "persona", "text": "Saved role"}, {"part": "instructions", "text": "Current stage"}]
            terminal.record_parts(folder, "build-e1-1", parts)
            with open(path, "w", encoding="utf-8", newline="") as stream:
                stream.write(nodes.render(parts))
            result = self.run_bridge("""
const restored = events.input({text:'expected-input',source:'interactive'},ctx);
if (restored?.action !== 'transform' || !restored.text.includes('controller task\\ncomplete')) process.exit(8);
if (events.input({text:'operator followup',source:'interactive'},ctx) !== undefined) process.exit(9);
""", folder, environ={"ORCHESTRA_PI_PROMPT_FILE": path, "ORCHESTRA_PI_INPUT_TOKEN": "expected-input",
                         "ORCHESTRA_PI_PARTS_FILE": terminal.turn_files(folder, "build-e1-1")["parts"]})
            self.assertEqual(result.returncode, 0, result.stderr)
            events = terminal._events(os.path.join(folder, "events"))
            self.assertEqual([event["prompt"] for event in events], [nodes.render(parts), "operator followup"])

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

    def test_a_runtime_without_the_native_contract_api_is_refused_before_work(self):
        with tempfile.TemporaryDirectory() as folder:
            for version in ("1.0.4", "1.1.0", "1.4.9", "0.99.1", "unknown", "1.5.0-dev"):
                result = self.run_bridge("process.stdout.write('work started');", folder, version=version)
                self.assertEqual(result.returncode, 1, version)
                self.assertIn("Pi 1.5.0 or newer", result.stderr)
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
  timestamp: 1700000000123, responseId: 'response-1', responseModel: 'actual-model',
  usage: {input: 12, output: 3, cacheRead: 7, cacheWrite: 0,
    cost: {total: 123, totalFromProvider: true}}}}, ctx);
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
            self.assertEqual(events[1].get("request_timestamp_ms"), 1700000000123)
            self.assertEqual(events[1].get("response_id"), "response-1")
            self.assertEqual(events[1].get("response_model"), "actual-model")
            self.assertIs(events[1]["usage"]["cost"]["totalFromProvider"], True)
            context = {"traceparent": "parent", "metadata": {
                "run_id": "test", "stage": "plan", "episode": 1, "round": 1}}
            with mock.patch.object(terminal, "turn_attempts", return_value=[{"events": path}]):
                generation = adapters.load("pi").upload("/s.jsonl", context)["generations"][0]
            self.assertEqual(generation["metadata"]["request_timestamp_ms"], 1700000000123)
            self.assertEqual(generation["metadata"]["response_id"], "response-1")
            self.assertEqual(generation["cost_details"], {"total": 123})
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
