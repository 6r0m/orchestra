"""Pi's native interactive CLI, exact session files, settlement events and recorded model usage."""
import glob
import json
import os
import re
import sys
import uuid

NAME = "Pi"
EXECUTABLE = "pi"
ACCESS = ("read", "write")
BOUNDARY = {
    "read": "Pi's tool allowlist enables only read, grep, find and ls, with MCP disabled. Extensions still run "
            "as the host user; there is no operating-system filesystem boundary.",
    "write": "Pi runs with its installed permission extensions as the host user. Its tools and commands have no "
             "operating-system filesystem isolation; use the host's managed launcher for its permission rules.",
}
OPTIONS = ("model", "effort", "provider", "launcher")
# Pi separates a skill's name from its arguments at a literal space, including multiline arguments.
SKILL = "/skill:{name} "
SESSION_MARKERS = ("ORCHESTRA_PI_PROMPT_FILE", "ORCHESTRA_PI_INPUT_TOKEN")
SESSION_MARKER_PREFIXES = ()
LOST_SESSION = ("pi session not found before work",)
OLD_BRAIN = None
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]*")
BRIDGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pi_events.mjs")


def validate(profile):
    problems = []
    for key, value in profile.items():
        if key == "kind":
            continue
        if key not in OPTIONS:
            problems.append((key, "Pi takes model, effort, provider and an optional launcher"))
        elif key == "effort":
            if value not in ("off", "minimal", "low", "medium", "high", "xhigh", "max"):
                problems.append((key, "must be a Pi thinking level"))
        elif not (isinstance(value, str) and TOKEN.fullmatch(value)):
            problems.append((key, "must be a plain token"))
    if profile.get("provider") and not profile.get("model"):
        problems.append(("model", "Pi requires a model when a provider is selected"))
    return problems


def program(role):
    return role.get("launcher") or EXECUTABLE


def command(role, resume_id, traced=None):
    argv = [program(role), "--tui-mode", "regular"]
    for key, flag in (("provider", "--provider"), ("model", "--model"), ("effort", "--thinking")):
        if role.get(key):
            argv += [flag, role[key]]
    if role["workspace_access"] == "read":
        argv += ["--no-mcp", "--tools", "read,grep,find,ls"]
    else:
        argv += ["--exclude-tools", "powershell"]
    if resume_id:
        return argv + ["--session", resume_id, "--orchestra-resume-session", resume_id], None
    minted = str(uuid.uuid4())
    return argv + ["--session-id", minted], minted


def host(argv):
    return list(argv)


def session_in(argv):
    for flag in ("--session", "--session-id"):
        if flag in argv:
            return argv[argv.index(flag) + 1]
    return None


def wire(argv, events, sink):
    return list(argv) + ["--extension", BRIDGE]


def prompt_input(_prompt, path):
    """A shell-safe input token; the native bridge delivers the already recorded prompt."""
    token = "orchestra-input-" + uuid.uuid4().hex
    return token, {"ORCHESTRA_PI_PROMPT_FILE": path, "ORCHESTRA_PI_INPUT_TOKEN": token}


def held(text):
    screen = " ".join(text.split())
    if ("Trust project folder?" in screen and "settings and resources" in screen
            and "execute project extensions." in screen and "Do not trust" in screen):
        return ("Pi asks whether to trust project settings, packages and project extensions in the role's terminal. "
                "Continue the run and review the prompt there; Orchestra does not answer or save a trust decision")
    return None


def _ours(event, session):
    return session is None or session in (event.get("session_id"), event.get("session_file"))


def completion(events, prompt, session):
    begun = False
    for event in events:
        if not _ours(event, session):
            continue
        if event.get("_hook") == "PiInput" and (event.get("prompt") or "").strip() == prompt.strip():
            begun = True
        elif begun and event.get("_hook") == "PiSettled":
            return event.get("ok") is True, event, event.get("session_file")
    return None


def output(message, session):
    payload = message if isinstance(message, dict) else {"answer": message, "session_file": session}
    return json.dumps(payload) + "\n"


def _payload(out):
    try:
        value = json.loads(out)
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def session(out, minted):
    return _payload(out).get("session_file")


def final_message(out):
    return _payload(out).get("answer") or ""


def message_of(event):
    return event.get("answer") if isinstance(event, dict) else None


def reply(events, prompt, session):
    done = completion(events, prompt, session)
    if done is None:
        return None
    ended = False
    asked = False
    answer = None
    for event in events:
        if event is done[1]:
            ended = True
            continue
        if not ended or not _ours(event, session):
            continue
        if event.get("_hook") == "PiInput":
            asked = (event.get("prompt") or "").strip() != prompt.strip()
        elif asked and event.get("_hook") == "PiSettled" and event.get("ok") and event.get("answer"):
            answer = event["answer"], event.get("_at")
    return answer


def _settings(path):
    try:
        with open(path, encoding="utf-8") as fh:
            value = json.load(fh)
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def skill_roots(repo, agent_dir=None):
    agent_dir = agent_dir or os.environ.get("PI_CODING_AGENT_DIR") or os.path.expanduser("~/.pi/agent")
    roots = [os.path.join(agent_dir, "skills"), os.path.join(repo, ".pi", "skills"),
             os.path.join(repo, ".agents", "skills")]
    for folder in (agent_dir, os.path.join(repo, ".pi")):
        settings = _settings(os.path.join(folder, "settings.json"))
        for entry in settings.get("packages") or []:
            source = entry if isinstance(entry, str) else entry.get("source", "") if isinstance(entry, dict) else ""
            package = os.path.abspath(os.path.join(folder, os.path.expanduser(source)))
            if not source or not os.path.isdir(package):
                continue
            patterns = (_settings(os.path.join(package, "package.json")).get("pi") or {}).get("skills") or []
            included, excluded = set(), set()
            for pattern in patterns:
                if not isinstance(pattern, str):
                    continue
                remove = pattern.startswith("!")
                for found in glob.glob(os.path.join(package, pattern.lstrip("!")), recursive=True):
                    (excluded if remove else included).add(os.path.dirname(found) if os.path.isfile(found) else found)
            roots.extend(os.path.dirname(found) for found in included - excluded)
    return list(dict.fromkeys(roots))


def skill_folders(name, repo, agent_dir=None):
    return [os.path.join(root, name) for root in skill_roots(repo, agent_dir)]


def _nonnegative_number(value):
    return type(value) in (int, float) and 0 <= value <= sys.float_info.max


def upload(session, context):
    if not context or not context.get("traceparent"):
        return None
    from app.agents import terminal
    meta = context["metadata"]
    name = terminal.turn_name(meta["stage"], meta["episode"], meta["round"])
    generations = []
    for files in terminal.turn_attempts(terminal.run_dir(meta["run_id"]), name):
        for event in terminal._events(files["events"]):
            if event.get("_hook") != "PiGeneration" or not _ours(event, session):
                continue
            usage = event.get("usage")
            usage = usage if isinstance(usage, dict) else {}
            keys = {"input": "input", "output": "output", "cacheRead": "input_cached_tokens",
                    "cacheWrite": "input_cache_creation_tokens"}
            complete = all(isinstance(usage.get(key), int) and not isinstance(usage[key], bool) and usage[key] >= 0
                           for key in keys)
            cost = usage.get("cost")
            cost = cost if isinstance(cost, dict) else {}
            amount = cost.get("total")
            valid_cost = _nonnegative_number(amount)
            provider_reported = cost.get("totalFromProvider") is True
            timestamp = event.get("request_timestamp_ms")
            valid_time = _nonnegative_number(timestamp) and timestamp <= 2 ** 53 - 1
            metadata = {"provider": event.get("provider"), "api": event.get("api"),
                        "usage_complete": complete, "billing_coverage": "unknown",
                        "request_time_source": "native" if valid_time else "unknown",
                        "cost_source": "provider_reported" if provider_reported and valid_cost else "model_price_inference",
                        "native_cost_total_from_provider": provider_reported,
                        "native_cost_source": ("unknown" if not valid_cost else
                                               "provider_reported" if provider_reported else "catalog_estimate"),
                        "stop_reason": event.get("stop_reason")}
            if valid_time:
                metadata["request_timestamp_ms"] = timestamp
            if valid_cost:
                metadata["native_cost_total"] = amount
            for field in ("response_id", "response_model"):
                if isinstance(event.get(field), str) and event[field]:
                    metadata[field] = event[field]
            generation = {"model": event.get("model"), "output": event.get("answer"),
                          "usage_details": {target: usage[key] for key, target in keys.items()} if complete else None,
                          "metadata": metadata}
            # Ingest only an explicitly provider-reported total. Pi's catalog estimate remains
            # evidence in metadata and never overrides Langfuse's configured model prices.
            if provider_reported and valid_cost:
                generation["cost_details"] = {"total": amount}
            generations.append(generation)
    notes = []
    if not generations or any(not generation["metadata"]["usage_complete"] for generation in generations):
        notes.append({"key": "pi usage", "say": "native generation usage is incomplete",
                      "degraded": "native generation usage is incomplete; cost is unknown"})
    return {"generations": generations, "traceparent": context["traceparent"], "notes": notes}
