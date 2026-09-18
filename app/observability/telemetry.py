"""Optional Langfuse projection of the workflow. Observability only (D20).

This module may be switched off, misconfigured or unreachable, and a run must not
notice.

Two values cross back into the workflow: the work item's trace id and the id of its
root observation, which the workflow keeps as `trace_id` and `trace_root`, so every
later step, on either host and after any stop, attaches to the same root. They are
opaque correlation ids. Nothing routes, judges, budgets or gates on them, and a
run without them behaves identically; only its trace loses the shared root.
Nothing is ever read back from Langfuse itself.

The work item is the durable entity. One trace per `run_id` — stable across
`--continue`, the human gate and a process restart — holds every stage of that
piece of work, grouped in a session named by the work item's label, so the
operator opens one thing and sees the whole loop instead of correlating windows.

Its rows are an interface as much as a view: saved views, the dashboard and the
scores select them by name, so a name says what kind of step a row is and never
which run, round or verdict — those are metadata. The contract, with the level
policy and what each score means, is `docs/architecture/trace-contract.md`.

Under each stage span the agent's own harness attaches its turns and tool calls,
through the vendor's own tracing plugin. This module takes the keys from
`.env`, and no user-level Claude or Codex configuration holds a
working one: a Claude role-run receives them through a private settings file
that exists only while it runs, the Codex uploader through its process
environment, and the command line we build carries only non-secret correlation
ids.
"""
import os
import re
import sys

from app.foundation import envpath
from app.foundation import paths
from app.foundation import policy as P
# The change a human reviews is the worktree's; the trace only records it.

REPO_ROOT = paths.REPO
# This checkout's private file — every credential this component reads, and nothing else; it is
# gitignored, and `.env.example` names its keys. Only the key pair is exported from it; the mask
# also keeps its secret values, in this process only, so that none of them can leave in a row.
SECRETS_FILE = os.path.join(REPO_ROOT, ".env")
DEFAULT_HOST = "http://localhost:3000"
# Where a run's rows are filed unless LANGFUSE_TRACING_ENVIRONMENT says otherwise.
DEFAULT_ENVIRONMENT = "dev"

# The trace's contract. Saved views, the dashboard and the scores select rows by
# these names, so they change only on purpose and never carry a run's own values.
SCHEMA_VERSION = "observability-schema-v1"
RUN_NAME = "orchestration-run"
PHASE_NAMES = {"plan": "plan-phase", "build": "build-phase"}
PHASE_ROLES = {"plan": "the engineer plans, the architect assesses",
               "build": "the engineer builds, the architect verifies"}
GATE_NAME = "human-gate"
ANSWER_NAME = "human-answer"
DIFF_NAME = "final-diff"
SCORE_NAMES = ("architect_verdict", "plan_first_pass", "build_first_pass", "final_verify_pass")
# Read from the file only when the environment lacks them: an explicit
# environment variable wins, as in the rest of this repository's tooling, and a
# run needs no shell setup.
_CREDENTIALS = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")

_warned = set()


def _read_secrets_file():
    """`NAME=value` entries of the secrets file, {} when it is absent. Never raises, never logs a value."""
    try:
        with open(SECRETS_FILE, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except FileNotFoundError:
        return {}                       # absent is normal: telemetry is optional
    except (OSError, UnicodeError) as exc:
        # The kind of failure only, nothing read from the file.
        _warn_once("secrets", "cannot read %s: %s"
                   % (os.path.relpath(SECRETS_FILE, REPO_ROOT), type(exc).__name__))
        return {}
    entries = {}
    for line in lines:
        name, sep, value = line.partition("=")
        name = name.strip()
        if sep and name and not name.startswith("#"):
            entries[name] = value.strip().strip("'\"")
    return entries


def _load_credentials():
    """Fill missing Langfuse env vars from `.env`. Never raises, never logs a value."""
    os.environ.setdefault("LANGFUSE_HOST", DEFAULT_HOST)
    missing = [name for name in _CREDENTIALS if not os.environ.get(name)]
    if not missing:
        return
    entries = _read_secrets_file()
    for name in missing:
        if entries.get(name):
            os.environ[name] = entries[name]


def _warn_once(what, exc):
    """One line to stderr per failure kind; a broken projection is not a storm."""
    if what not in _warned:
        _warned.add(what)
        sys.stderr.write("langfuse telemetry degraded (%s): %r\n" % (what, exc))


def configured():
    """True when a Langfuse is reachable in principle. Never raises."""
    _load_credentials()
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY")
                and os.environ.get("LANGFUSE_SECRET_KEY"))


def tags(values):
    """The few tags every row carries: stable values only, since a tag naming a run splits every view by run.

    The repository and the target are the run's, never this process's own.
    """
    return ["workflow:feature", "repo:%s" % values.get("repo"), "target:%s" % values.get("target"),
            "source:manual"]


def _release():
    """The orchestrator code this process runs: its commit, `-dirty` when that code differs from it.

    None when git cannot say, so an unknown release is never recorded as a known one.
    """
    import subprocess
    try:
        head = subprocess.run(["git", "-C", REPO_ROOT, "rev-parse", "--short=12", "HEAD"],
                              capture_output=True, text=True, timeout=10)
        status = subprocess.run(["git", "-C", REPO_ROOT, "status", "--porcelain"],
                                capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        _warn_once("release", exc)
        return None
    if head.returncode or status.returncode:
        _warn_once("release", "git rc=%d/%d %s" % (head.returncode, status.returncode,
                                                  (head.stderr or status.stderr).strip()[:200]))
        return None
    return head.stdout.strip() + ("-dirty" if status.stdout.strip() else "")


REDACTED = "[REDACTED]"
# High-confidence shapes only: a pattern that also matched ordinary code would
# redact the very commands and diffs a person opens the trace to read.
_SECRET_SHAPES = re.compile("|".join((
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
    r"\bsk-[A-Za-z0-9_-]{20,}",
    r"\bgh[pousr]_[A-Za-z0-9]{30,}",
    r"\bgithub_pat_[A-Za-z0-9_]{20,}",
    r"\bglpat-[A-Za-z0-9_-]{20,}",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"\bxox[abprs]-[A-Za-z0-9-]{10,}",
    r"\bAIza[0-9A-Za-z_-]{35}",
    r"\b(?i:bearer)\s+[A-Za-z0-9._~+/-]{20,}=*",
)))
# Which entries of the secrets file hold a secret — never the public key, which
# the SDK itself writes into every row — and the shortest value treated as one: a
# shorter value would redact ordinary words wherever they appear.
_SECRET_NAME = re.compile(r"SECRET|PASSWORD|TOKEN|SALT|KEY|AUTH")
_NOT_SECRET_NAME = re.compile(r"PUBLIC|_(URL|HOST|PORT|ENDPOINT|REGION|ENABLED|USER|EMAIL|ID)$")
_SECRET_MIN_CHARS = 8
_SECRETS = ()


def _remember_secrets():
    """Keep the values the mask must never let out: our secret key and the secret entries of the secrets file."""
    global _SECRETS
    values = {value for name, value in _read_secrets_file().items()
              if _SECRET_NAME.search(name) and not _NOT_SECRET_NAME.search(name)}
    values.add(os.environ.get("LANGFUSE_SECRET_KEY") or "")
    # Longest first, so a secret that contains another goes whole.
    _SECRETS = tuple(sorted((value for value in values if len(value) >= _SECRET_MIN_CHARS),
                            key=len, reverse=True))


def _redact(value):
    """`value` with every secret shape and remembered secret replaced; its structure and non-text kept."""
    if isinstance(value, str):
        text = _SECRET_SHAPES.sub(REDACTED, value)
        for secret in _SECRETS:
            text = text.replace(secret, REDACTED)
        return text
    if isinstance(value, dict):
        return {key: _redact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def mask(*, data, **kwargs):
    """The client's mask: what this component exports leaves the process redacted.

    It covers the input, output and metadata of our own rows. The vendor plugins
    export from their own processes, which it does not reach.
    """
    return _redact(data)


def resolve():
    """Return a client, or None when telemetry is off or unusable.

    Deliberately does not call `auth_check`: reachability is not a precondition
    for running the workflow, and paying a round trip to discover otherwise
    would make an outage cost the run time it must never cost.

    The run's environment and release are set in this process's environment,
    where our client, the Codex uploader and each Claude role-run's command all
    take them from; a value already set there wins.
    """
    if not configured():
        return None
    if not os.environ.get("LANGFUSE_TRACING_ENVIRONMENT"):
        os.environ["LANGFUSE_TRACING_ENVIRONMENT"] = DEFAULT_ENVIRONMENT
    if not os.environ.get("LANGFUSE_RELEASE"):
        release = _release()
        if release:
            os.environ["LANGFUSE_RELEASE"] = release
    _remember_secrets()
    try:
        from langfuse import Langfuse
        return Langfuse(mask=mask)
    except Exception as exc:                       # noqa: BLE001 - by contract
        _warn_once("client", exc)
        return None


class _Span:
    """A stage span, or a no-op standing in for one. Callers never branch.

    It keeps what closing the stage needs: the client that scores a verdict, the
    phase and round that say whether the verdict was its phase's first, and the
    warnings raised while it ran.
    """

    def __init__(self, cm=None, span=None, traceparent=None, client=None, phase=None, round=None):
        self._cm = cm
        self._span = span
        self.traceparent = traceparent
        self.client = client
        self.phase = phase
        self.round = round
        self.warnings = []


def _work_item_context(client, values):
    """Where an observation belongs: this run's trace, under its root if one exists.

    A run whose root never opened has no trace id of its own; its rows still
    share one, derived from the run id.
    """
    context = {"trace_id": values.get("trace_id")
               or client.create_trace_id(seed=values["run_id"])}
    if values.get("trace_root"):
        context["parent_span_id"] = values["trace_root"]
    return context


def _phase_context(client, values):
    """Where a stage belongs: under its phase's node, else under the work item."""
    context = _work_item_context(client, values)
    phase = (values.get("trace_phases") or {}).get(values.get("phase"))
    if phase:
        context["parent_span_id"] = phase
    return context


def _not_a_root(current):
    """Mark a span as the child it is, though its parent was exported by another process.

    Both flags are needed. The SDK marks what it creates from a trace context as a
    root (`AS_ROOT`), and its span processor marks a span whose parent this process
    never exported as an application root (`IS_APP_ROOT`). Langfuse treats either
    as a root, and the trace page names the trace after one of its roots.
    """
    from langfuse import LangfuseOtelSpanAttributes as attrs
    current.set_attribute(attrs.AS_ROOT, False)
    current.set_attribute(attrs.IS_APP_ROOT, False)


def phase_round(state):
    """The round a person counts: architect judgements in this phase so far, plus one.

    Guidance restarts the round budget, not this count, so the rows after a
    blocker carry on from where the phase was instead of repeating `round 1`.
    """
    return state.get("phase_rounds", 0) + 1


def stage_name(stage, role_name):
    """A role step's name: who acts, in which stage — `architect-assess`.

    Never the round or the verdict, which are metadata, so one name gathers every
    round of one kind of step; the stage keeps plan's steps apart from build's.
    """
    return "%s-%s" % (role_name, stage)


ROW_NAMES = ((RUN_NAME,) + tuple(PHASE_NAMES.values())
             + tuple(stage_name(stage, role) for stage, role in P.STAGE_ROLE.items())
             + (GATE_NAME, ANSWER_NAME, DIFF_NAME))


def _mark_work_item(current, values):
    """Give a row its work item's trace-level fields: the session, the trace name and the tags.

    They are OTEL attributes in the v4 SDK — measured: passed to `update()` they
    are accepted and silently dropped. Every row carries the same ones, so no row
    renames or retags the work item as itself. The session key is the readable
    label an operator scans a list for; an older run without one keeps its id.
    """
    from langfuse import LangfuseOtelSpanAttributes as attrs
    current.set_attribute(attrs.TRACE_SESSION_ID, values.get("label") or values["run_id"])
    current.set_attribute(attrs.TRACE_NAME, RUN_NAME)
    current.set_attribute(attrs.TRACE_TAGS, tags(values))


def open_phase(client, values, phase):
    """Open the node one phase's rounds hang from, under the work item in `values`; return its id.

    Plan and build are what the operator moves between, so each gets one node
    under the work item, opened when that phase starts. Like the work item's own
    root it is opened and closed at once and joined later by the id the workflow keeps.
    """
    if client is None:
        return None
    try:
        from opentelemetry import trace as otel
    except Exception as exc:                       # noqa: BLE001 - by contract
        _warn_once("import", exc)
        return None
    try:
        cm = client.start_as_current_observation(
            name=PHASE_NAMES.get(phase, phase), as_type="chain", version=SCHEMA_VERSION,
            trace_context=_work_item_context(client, values))
        span = cm.__enter__()
        try:
            current = otel.get_current_span()
            if values.get("trace_root"):
                # Left marked as a root by the SDK, a phase node renames the trace.
                _not_a_root(current)
            _mark_work_item(current, values)
            span.update(input={"phase": phase, "roles": PHASE_ROLES.get(phase)},
                        metadata={"phase": phase})
            return "%016x" % current.get_span_context().span_id
        finally:
            # Closed on every way out: left open, it would stay the current
            # context and the rows that follow would attach beneath it.
            cm.__exit__(None, None, None)
    except Exception as exc:                       # noqa: BLE001 - by contract
        _warn_once("phase node", exc)
        return None


def open_work_item(client, values):
    """Create the one root observation a work item hangs from; return its trace id and its id.

    `values` holds the run's id, label and task, and its worktree and base branch.
    Called once, at setup. It is opened with no trace context, which would give
    it a parent, so it is a genuine root and its trace id is the SDK's own. Both
    ids are kept by the workflow and every later step attaches to them,
    so the observations table shows one entry row per request instead of one per
    stage. It is opened and closed immediately: hierarchy in Langfuse is decided
    by ids, not by holding a Python object open across a stop, a restart and two
    hosts, which no run could do anyway. `(None, None)`
    when it cannot open.
    """
    if client is None:
        return None, None
    try:
        from opentelemetry import trace as otel
    except Exception as exc:                       # noqa: BLE001 - by contract
        _warn_once("import", exc)
        return None, None
    try:
        cm = client.start_as_current_observation(name=RUN_NAME, as_type="chain",
                                                 version=SCHEMA_VERSION)
        span = cm.__enter__()
        try:
            current = otel.get_current_span()
            _mark_work_item(current, values)
            # What a table of work items and an evaluator show first: the request,
            # and where it is carried out.
            asked = {"request": values.get("task"), "repo": values.get("repo"),
                     "base_branch": values.get("base_branch"), "target": values.get("target")}
            span.update(input={k: v for k, v in asked.items() if v is not None},
                        metadata={k: v for k, v in (("run_id", values["run_id"]),
                                                    ("worktree", values.get("worktree"))) if v})
            ctx = current.get_span_context()
            return "%032x" % ctx.trace_id, "%016x" % ctx.span_id
        finally:
            cm.__exit__(None, None, None)
    except Exception as exc:                       # noqa: BLE001 - by contract
        _warn_once("work item root", exc)
        return None, None


def begin(client, state, stage, role_name, role, log=None):
    """Open the span for one role invocation. Always returns a usable object.

    `log` is where this stage's own prompt and output files are kept.
    """
    if client is None:
        return _Span()
    try:
        from opentelemetry import trace as otel
    except Exception as exc:                       # noqa: BLE001 - by contract
        _warn_once("import", exc)
        return _Span()

    attempt = phase_round(state)
    try:
        # One work item is one trace, and one root inside it. The workflow keeps
        # both ids, so a step on either host, after any stop, joins them
        # instead of starting its own. Stages are `agent` observations:
        # it is what they are, and the agent graph reads the type.
        cm = client.start_as_current_observation(
            name=stage_name(stage, role_name), as_type="agent", version=SCHEMA_VERSION,
            trace_context=_phase_context(client, state))
        span = cm.__enter__()
    except Exception as exc:                       # noqa: BLE001 - by contract
        _warn_once("span start", exc)
        return _Span()

    traceparent = None
    try:
        current = otel.get_current_span()
        # The SDK marks anything created from a trace_context as a root, even
        # when a parent span id was supplied (`_create_span_with_parent_context`
        # keys that off the remote parent existing, not off whether it has a
        # parent of its own). Left set, every stage and provider turn shows up
        # as an application entry point and the observations table stops being
        # one row per request. A stage that has a parent is not a root.
        if state.get("trace_root"):
            _not_a_root(current)
        _mark_work_item(current, state)
        # The round, phase and stage are what views and the dashboard filter a
        # step on, so they are metadata and never part of its name. The logs are
        # pointed at directly: the counters that name those files would sit
        # beside the round and read as a second, contradicting count.
        described = {"role": role_name, "stage": stage, "phase": state.get("phase"),
                     "round": attempt, "logs": log, "brain": role.get("brain"),
                     "model": role.get("model"), "reasoning_effort": role.get("reasoning_effort"),
                     "run_id": state["run_id"], "worktree": state.get("worktree")}
        span.update(metadata={k: v for k, v in described.items() if v is not None})
        # Without input/output a span is filtered out of Langfuse's default
        # view, which renders the whole session empty even though every
        # observation is present. What the stage was asked, and what it
        # answered, is also what an operator wants to read first.
        asked = {"task": state.get("task"), "stage": stage, "role": role_name,
                 "round": attempt,
                 "prior_feedback": (state.get("feedback") or "")[:1500] or None,
                 "guidance": (state.get("guidance") or "")[:1000] or None}
        span.update(input={k: v for k, v in asked.items() if v is not None})
        ctx = current.get_span_context()
        traceparent = "00-%032x-%016x-01" % (ctx.trace_id, ctx.span_id)
    except Exception as exc:                       # noqa: BLE001 - by contract
        _warn_once("span attributes", exc)
    return _Span(cm, span, traceparent, client=client, phase=state.get("phase"), round=attempt)


RESPONSE_MAX_CHARS = 4000


def end(span, error_type=None, error=None, **fields):
    """Close a stage span, recording its outcome. Never raises.

    Called on both exits of a stage, including the failure path, so a span can
    never be left open claiming a role is still working. A failed stage is ERROR,
    classed by `error_type`, with what failed as its status. A verdict is also
    scored, on the step that gave it.
    """
    if span is None or span._cm is None:
        return
    try:
        for key in ("reasoning", "response"):
            if fields.get(key):
                # A role's own summary of what it did, trimmed: this is the part a
                # human reads, not the transcript it was distilled from, which stays
                # nested under the stage and in logs/.
                fields[key] = str(fields[key]).strip()[:RESPONSE_MAX_CHARS]
        # The texts a person reads belong to the output alone; metadata keeps the
        # short values a table filters on, or every text shows up twice.
        metadata = {key: fields[key] for key in ("verdict", "gate_reason") if fields.get(key)}
        if fields.get("session"):
            metadata["provider_session_id"] = fields["session"]
        output = {key: value for key, value in fields.items()
                  if key != "session" and value not in (None, "")}
        # A status message is not shown where a person reads a step, so what made
        # it a warning or an error is written into its output as well.
        if span.warnings:
            output["warning"] = "; ".join(span.warnings)
        if error_type:
            message = _status_message(error or error_type)
            metadata["error_type"] = error_type
            output["error"] = message
            span._span.update(level="ERROR", status_message=message)
        if metadata:
            span._span.update(metadata=metadata)
        if output:
            span._span.update(output=output)
    except Exception as exc:                       # noqa: BLE001 - by contract
        _warn_once("span update", exc)
    if fields.get("verdict"):
        _score_verdict(span, fields["verdict"])
    try:
        span._cm.__exit__(None, None, None)
    except Exception as exc:                       # noqa: BLE001 - by contract
        _warn_once("span end", exc)


def warn(span, error_type, message):
    """Mark a stage that goes on degraded: WARNING, classed by `error_type`. Never raises."""
    if span is None or span._span is None:
        return
    message = _status_message(message)
    span.warnings.append(message)
    try:
        span._span.update(level="WARNING", status_message=message,
                          metadata={"error_type": error_type})
    except Exception as exc:                       # noqa: BLE001 - by contract
        _warn_once("span update", exc)


STATUS_MAX_CHARS = 500


def _status_message(value):
    """What failed, short and redacted: the SDK's mask does not cover a status message."""
    return _redact(str(value)).strip()[:STATUS_MAX_CHARS]


def _ids(traceparent):
    """The trace id and observation id inside a W3C traceparent, or None."""
    parts = (traceparent or "").split("-")
    if len(parts) != 4 or len(parts[1]) != 32 or len(parts[2]) != 16:
        return None
    return parts[1], parts[2]


def _score(client, **score):
    """Send one score. Never raises: a lost score costs a number on a dashboard, never the run."""
    try:
        client.create_score(**score)
    except Exception as exc:                       # noqa: BLE001 - by contract
        _warn_once("score", exc)


def _score_verdict(span, verdict):
    """Score a judgement on the step that made it, and on the work item when it was its phase's first.

    Whether a phase passed at its first judgement belongs to the work item, so
    that score has one id per work item: a stage run again after a crash replaces
    it rather than adding a second.
    """
    ids = _ids(span.traceparent)
    if span.client is None or ids is None:
        return
    trace_id, observation_id = ids
    _score(span.client, name="architect_verdict", value=verdict, data_type="CATEGORICAL",
           trace_id=trace_id, observation_id=observation_id)
    if span.round == 1 and span.phase in PHASE_NAMES:
        name = "%s_first_pass" % span.phase
        _score(span.client, name=name, value=1.0 if verdict == "PASS" else 0.0,
               data_type="BOOLEAN", trace_id=trace_id, score_id="%s-%s" % (trace_id, name))


def harness_env(role, span, state, stage, role_name):
    """Non-secret correlation ids for the agent's own tracing plugin.

    Claude accepts a W3C traceparent, so its turns nest directly under this
    stage span. Codex documents no equivalent, and its variables here are
    **inert today**: codex does not pass this environment to its hook
    subprocess, so the tracing plugin never sees them (measured). They are kept
    because they are the vendor's documented interface and cost nothing if that
    changes; the architect's transcript actually arrives through
    `upload_codex_session`, which the plugin's own sidecar keeps from
    double-uploading should the hook ever start working.
    """
    if span is None or span.traceparent is None:
        return None
    episode, attempt = state.get("episode", 1), state.get("round", 0) + 1
    if role.get("brain") == "claude":
        env = {"CC_LANGFUSE_TRACEPARENT": span.traceparent}
        # The plugin builds its own client inside the role-run, so the run's
        # environment and release reach its rows only through that process.
        for name in ("LANGFUSE_TRACING_ENVIRONMENT", "LANGFUSE_RELEASE"):
            if os.environ.get(name):
                env[name] = os.environ[name]
        return env
    if role.get("brain") == "codex":
        # Deliberately nothing. Enabling the vendor hook from here uploads every
        # turn a second time - measured on run f4756084470c: one copy nested
        # under this stage span from `upload_codex_session`, and one copy in its
        # own trace under the codex thread id from the hook. Ingested
        # observations are immutable, so a duplicate cannot be repaired
        # afterwards; the only fix is to run one uploader. The explicit one wins
        # because it is the only one that can carry this stage's parent context.
        return None
    return None


# Only role-runs the orchestrator launches may trace. The Claude plugin is
# installed for the user but disabled there, and no user-level configuration
# holds a working key: not the settings, and not the plugin's credential store,
# whose secret outranks any a run supplies (measured). A traced role-run gets
# both keys through its own settings file, passed with `--settings`, and that
# file exists only while the role-run does.
CLAUDE_PLUGIN = "langfuse-observability@langfuse-observability"
SETTINGS_FILE = "claude-telemetry-settings.json"
SETTINGS_DIR_PREFIX = "orch-claude-settings-"


def harness_settings(role, span):
    """Path of a private settings file that lets one Claude role-run trace, or None.

    None unless this stage is actually traced and both keys are configured, so a
    run with telemetry off never switches the plugin on. The file holds the
    secret, so it is written into a new directory only this user can enter, on
    the machine's temporary filesystem rather than the repository's drive, whose
    mount ignores file modes. The caller removes both with `discard_settings`
    when the role-run ends.
    """
    if role.get("brain") != "claude" or span is None or span.traceparent is None:
        return None
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    if not public_key or not secret_key:
        return None
    import json
    import tempfile
    settings = {
        "enabledPlugins": {CLAUDE_PLUGIN: True},
        "pluginConfigs": {CLAUDE_PLUGIN: {"options": {
            "LANGFUSE_PUBLIC_KEY": public_key,
            "LANGFUSE_SECRET_KEY": secret_key,
            "LANGFUSE_BASE_URL": os.environ.get("LANGFUSE_HOST", DEFAULT_HOST)}}},
    }
    path = None
    try:
        path = os.path.join(tempfile.mkdtemp(prefix=SETTINGS_DIR_PREFIX), SETTINGS_FILE)
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
                       "w", encoding="utf-8") as fh:
            json.dump(settings, fh)
    except OSError as exc:
        _warn_once("claude settings", exc)
        # A file cut short may already hold the secret, and no caller can delete
        # a file this function never handed out.
        discard_settings(path)
        return None
    return path


def discard_settings(path):
    """Remove a role-run's settings file and its private directory. Never raises."""
    if not path:
        return
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError as exc:
        _warn_once("claude settings cleanup", exc)
    directory = os.path.dirname(path)
    # Only a directory `harness_settings` made: never one a caller owns.
    if os.path.basename(directory).startswith(SETTINGS_DIR_PREFIX):
        try:
            os.rmdir(directory)
        except FileNotFoundError:
            pass
        except OSError as exc:
            _warn_once("claude settings cleanup", exc)


# The vendor's own uploader, built with the changes this trace needs, kept under the
# orchestration's own directory on each host: Codex restores its plugin cache whenever it
# starts, which replaces any build placed there.
CODEX_PLUGIN = os.path.join(envpath.environment_root(), "codex-observability-plugin", "dist", "index.mjs")
CODEX_ROLLOUTS = "~/.codex/sessions/*/*/*/rollout-*-%s.jsonl"
UPLOAD_TIMEOUT_SECONDS = 60


# What the trace needs from the installed Codex plugin build: a name each change
# adds to the bundle, and what goes wrong without it. The first is the documented
# input. The second is the option the turn-lifecycle change introduces, so a
# release that renames it warns once instead of quietly bringing empty turns back.
CODEX_PLUGIN_NEEDS = (
    ("LANGFUSE_CODEX_TRACEPARENT", "architect turns will not nest under their stage"),
    ("finalizeTurnId", "empty duplicate turns will appear under later stages"),
)


def _missing_codex_capabilities(bundle):
    """What the installed plugin build lacks, as the consequence of each gap."""
    try:
        with open(bundle, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return [effect for _, effect in CODEX_PLUGIN_NEEDS]
    return [effect for marker, effect in CODEX_PLUGIN_NEEDS if marker not in text]


def codex_reasoning(role, session_id):
    """The reasoning summaries of a codex role's most recent run, as readable text.

    Langfuse's formatted view of a model call shows its commands and its answer
    but not its reasoning field, so the architect's thinking was only reachable
    by switching an individual call to raw JSON. The engineer's account already
    sits on its stage; this puts the architect's beside its verdict.

    One codex session spans every stage the architect judges, and each run of it
    opens with a `task_started` record, so the summaries after the last one are
    exactly the run that just finished.
    """
    if role.get("brain") != "codex" or not session_id:
        return None
    import glob
    import json
    paths = glob.glob(os.path.expanduser(CODEX_ROLLOUTS % session_id))
    if not paths:
        return None
    current = []
    try:
        with open(paths[-1], encoding="utf-8") as fh:
            for line in fh:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                payload = record.get("payload") or record
                if payload.get("type") == "task_started":
                    current = []
                elif payload.get("type") == "reasoning":
                    for item in payload.get("summary") or []:
                        text = (item.get("text") if isinstance(item, dict) else str(item)) or ""
                        if text.strip():
                            current.append(text.strip())
    except OSError as exc:
        _warn_once("codex reasoning", exc)
        return None
    return "\n\n".join(current) or None


def _last_codex_turn(path):
    """The id of a rollout's most recent turn, as Codex's Stop hook reports it."""
    import json
    last = None
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                payload = (record.get("payload") if isinstance(record, dict) else None) or {}
                if payload.get("type") == "task_started" and payload.get("turn_id"):
                    last = payload["turn_id"]
    except OSError as exc:
        _warn_once("codex turn id", exc)
    return last


def upload_codex_session(client, role, session_id, state, stage, role_name, span=None):
    """Hand a finished codex role-run's transcript to the vendor's own uploader.

    Codex's Stop hook cannot do this for us, measured on 0.153.4 with the hook
    trusted and running: the plugin needs `TRACE_TO_LANGFUSE` in its own
    environment, and codex does not pass ours to hook subprocesses. Its config
    file is no way round that either — the plugin resolves the project file
    from its own working directory, which is not the worktree. The same
    environment carries our seed and tags, so the hook path could not produce a
    *correlated* trace even if it fired. Calling the documented entry point
    ourselves is the only route, and it keeps tracing scoped to orchestration
    runs instead of every codex session on the machine.

    Best-effort like everything else here: a failure costs the architect's
    transcript in the UI and nothing else, and marks the stage `span` WARNING, so
    the trace itself says it is incomplete.
    """
    if client is None or role.get("brain") != "codex" or not session_id:
        return
    import glob
    import json
    import subprocess

    traceparent = span.traceparent if span is not None else None
    uploader = sorted(glob.glob(os.path.expanduser(CODEX_PLUGIN)))
    missing = _missing_codex_capabilities(uploader[-1]) if uploader else []
    if missing:
        # A plugin upgrade can replace a build that has these with one that lacks
        # them. The upload still works, so the run is unaffected, but the trace
        # quietly degrades in exactly the ways this component removed. Say so.
        _warn_once("codex plugin build",
                   "plugin build at %s: %s (see tools/README.md, "
                   "'The Codex plugin must support a parent trace')"
                   % (uploader[-1], "; ".join(missing)))
        warn(span, "telemetry_degraded", "codex plugin build: %s" % "; ".join(missing))
    rollout = glob.glob(os.path.expanduser(CODEX_ROLLOUTS % session_id))
    if not uploader or not rollout:
        _warn_once("codex upload", "no uploader (%d) or rollout (%d) for %s"
                   % (len(uploader), len(rollout), session_id))
        warn(span, "telemetry_degraded", "the architect's turns were not uploaded: no uploader "
             "(%d) or rollout (%d)" % (len(uploader), len(rollout)))
        return

    episode, attempt = state.get("episode", 1), state.get("round", 0) + 1
    env = dict(os.environ)
    env.update({
        "TRACE_TO_LANGFUSE": "true",
        # The plugin's own default host is Langfuse Cloud: name ours rather than
        # rely on a user-level config file to.
        "LANGFUSE_CODEX_BASE_URL": os.environ.get("LANGFUSE_HOST", DEFAULT_HOST),
        # Attach this role-run's turns to the stage span that caused them. A
        # plugin build without parent-context support ignores it and degrades
        # to a correlated separate session.
        **({"LANGFUSE_CODEX_TRACEPARENT": traceparent} if traceparent else {}),
        "PLUGIN_ROOT": os.path.dirname(os.path.dirname(uploader[-1])),
        "LANGFUSE_CODEX_TRACE_SEED":
            "%s-%s-e%d-r%d" % (state["run_id"], stage, episode, attempt),
        # Tags and metadata reach the plugin's rows only when it is not attached
        # to a stage. The tags are the few every row carries; the run's own
        # values belong in the metadata below.
        "LANGFUSE_CODEX_TAGS": ",".join(tags(state)),
        # We cannot rename the vendor's session, so carry the work item inside
        # it instead: this is what makes an architect session identifiable
        # without going back to the orchestration side to look it up.
        "LANGFUSE_CODEX_METADATA": json.dumps({
            "work_item": state.get("label") or state["run_id"],
            "run_id": state["run_id"], "stage": stage, "role": role_name,
            "episode": episode, "round": attempt,
            "worktree": state.get("worktree")}),
    })
    payload = json.dumps({"session_id": session_id,
                          "transcript_path": rollout[-1],
                          "hook_event_name": "Stop",
                          # Codex's own Stop hook names the turn that just ended, and
                          # the plugin finalizes only that one. Without it, the empty
                          # record a resumed session writes before its next turn
                          # is exported as a turn of its own, under every later stage.
                          "turn_id": _last_codex_turn(rollout[-1])})
    try:
        done = subprocess.run(["node", uploader[-1]], input=payload, env=env,
                              text=True, capture_output=True,
                              timeout=UPLOAD_TIMEOUT_SECONDS)
    except Exception as exc:                       # noqa: BLE001 - by contract
        _warn_once("codex upload", exc)
        warn(span, "telemetry_degraded", "the architect's turns were not uploaded: %s" % exc)
        return
    if done.returncode != 0:
        # Fail open, but never fail silent: losing the architect's transcript
        # must cost a warning, or the UI is quietly incomplete and nothing says so.
        _warn_once("codex upload", "rc=%d %s" % (done.returncode,
                                                 (done.stderr or "").strip()[:200]))
        warn(span, "telemetry_degraded", "the architect's turns were not uploaded: "
             "the uploader exited rc=%d" % done.returncode)


DIFF_MAX_CHARS = 200000


def _record(client, name, trace_context, values, **fields):
    """Record a row that happens at an instant: a stop, an answer, the final diff.

    Written as a span that opens and closes at once, not through `create_event`:
    the SDK marks anything it creates from a trace context as a root, Langfuse
    lets every root rename the trace, and an event gives no moment to say
    otherwise. The work item's own root is the only root.
    """
    from opentelemetry import trace as otel
    cm = client.start_as_current_observation(name=name, as_type="span", version=SCHEMA_VERSION,
                                             trace_context=trace_context)
    span = cm.__enter__()
    try:
        current = otel.get_current_span()
        if trace_context.get("parent_span_id"):
            _not_a_root(current)
        _mark_work_item(current, values)
        span.update(**fields)
    finally:
        cm.__exit__(None, None, None)


def gate_event(client, values, gate):
    """Record that a run stopped for a human, and why.

    The gate is the one part of the flow with no role-run behind it, so nothing
    else in the trace shows it: without this the work item jumps from a verdict
    straight to the next stage, and weeks later there is no sign a person was
    ever asked. Written by an activity the workflow runs once as it stops, never
    from workflow code, which Temporal replays.
    """
    if client is None or not values or not gate:
        return
    try:
        # Approval closes the plan and opens the build, so it sits between the
        # two, and what it shows is the plan's summary, written for the person
        # deciding whether to build.
        # Any other stop interrupts a phase and belongs inside it.
        approval = gate.get("reason") == "approval"
        _record(client,
            name=GATE_NAME,
            trace_context=(_work_item_context if approval else _phase_context)(client, values),
            values=values,
            # The output is what the person reads; where the plan document lives
            # is context for the question, beside the reason and the hint.
            input={"reason": gate.get("reason"), "phase": gate.get("phase"),
                   "hint": gate.get("hint"), "todo": gate.get("todo")},
            output={("summary" if approval else "feedback"): gate.get("feedback") or None},
            metadata={k: v for k, v in (("gate_reason", gate.get("reason")),
                                        ("phase", gate.get("phase"))) if v})
    except Exception as exc:                       # noqa: BLE001 - by contract
        _warn_once("gate event", exc)


def gate_answer(client, values, answer):
    """Record what a person answered at a stop, as the row right after that stop.

    The stop is recorded while nobody has answered yet, and a recorded row cannot
    be amended afterwards; so the answer is a row of its own, written when it
    arrives and before the run moves on. It sits where
    its stop sits: an approval's answer between the phases, any other inside
    its phase.
    """
    if client is None or not values or answer is None:
        return
    reason = values.get("gate_reason") or "?"
    try:
        _record(client,
            name=ANSWER_NAME,
            trace_context=(_work_item_context if reason == "approval" else _phase_context)(client, values),
            values=values,
            input={"reason": reason, "phase": values.get("phase")},
            output={"answer": str(answer)[:RESPONSE_MAX_CHARS]},
            metadata={k: v for k, v in (("gate_reason", reason), ("phase", values.get("phase"))) if v})
    except Exception as exc:                       # noqa: BLE001 - by contract
        _warn_once("gate answer", exc)


def final_diff(client, values, read_diff):
    """Close a finished work item's trace with the change the operator reviews.

    `read_diff` is the caller's own reader of a worktree, because what the change *is*
    belongs to git and the trace only records it: this module never reads the repository.

    Only on `READY_FOR_HUMAN`: every other stop — the plan approval, a blocker,
    an exhausted budget, a failed stage — would put
    several "final" diffs in one work item, none of them final.

    The base is the worktree's own HEAD, not the branch it forked from: that
    branch moves while a run is in flight, and diffing against its tip
    attributes other people's commits to this run. Agents never commit (D11),
    so HEAD is exactly where this run started.

    The patch is its own output field because Langfuse gives every field a copy
    button that copies the raw value, so one click yields the patch as text. A
    patch that held a secret is redacted and says so, because its copy is then
    not the exact change.
    """
    if client is None or not values:
        return
    if values.get("status") != "READY_FOR_HUMAN":
        return
    path = values.get("worktree_path")
    try:
        read = read_diff(path)
        base, summary, patch = read["base"], read["summary"], read["patch"]
    except Exception as exc:                       # noqa: BLE001 - by contract
        _warn_once("final diff", exc)
        # Still recorded, and as an error: an absent final diff reads as a run
        # that never finished, and an empty one as a run that changed nothing.
        try:
            _record(client,
                name=DIFF_NAME, trace_context=_work_item_context(client, values), values=values,
                level="ERROR", status_message=_status_message(exc),
                input={"worktree": path, "status": values.get("status")},
                output={"error": "could not read the worktree: %s" % exc},
                metadata={"error_type": "git_error"})
        except Exception as inner:                 # noqa: BLE001 - by contract
            _warn_once("final diff event", inner)
        return
    shown = _redact(patch[:DIFF_MAX_CHARS])
    try:
        _record(client,
            name=DIFF_NAME,
            trace_context=_work_item_context(client, values), values=values,
            input={"base": "%s (worktree HEAD at run start)" % base,
                   "worktree": path, "status": values.get("status"),
                   "command": "gdiff -s: git add -A, then git diff "
                              "--no-ext-diff --no-textconv --cached "
                              "(on a private copy of the index)"},
            output={"summary": summary.strip() or "(no changes)",
                    "patch": shown or None,
                    # Cut here, or already cut by the bounded read the change came through.
                    "truncated": len(patch) > DIFF_MAX_CHARS or read["next"] < read["total"],
                    "redacted": shown != patch[:DIFF_MAX_CHARS]})
    except Exception as exc:                       # noqa: BLE001 - by contract
        _warn_once("final diff", exc)


def outcome_score(client, values):
    """Score whether a work item ended with a verified build: 1 at `READY_FOR_HUMAN`, 0 when aborted.

    A run that only stopped at a gate has not ended, so it is not scored. The
    score has one id per work item, so recording it again replaces it.
    """
    if client is None or not values:
        return
    status = values.get("status")
    if status not in ("READY_FOR_HUMAN", "ABORTED"):
        return
    try:
        trace_id = _work_item_context(client, values)["trace_id"]
    except Exception as exc:                       # noqa: BLE001 - by contract
        _warn_once("score", exc)
        return
    _score(client, name="final_verify_pass", value=1.0 if status == "READY_FOR_HUMAN" else 0.0,
           data_type="BOOLEAN", trace_id=trace_id, score_id="%s-final_verify_pass" % trace_id)


def flush(client):
    """Best-effort delivery at the end of a run. Never raises."""
    if client is None:
        return
    try:
        client.flush()
    except Exception as exc:                       # noqa: BLE001 - by contract
        _warn_once("flush", exc)


def trace_url(client, trace_id):
    """A direct link to this run's trace in the Langfuse UI, or None. Never raises.

    The SDK builds it from the real project id, so the link stays correct
    whatever the project is named. None when telemetry is off or the run opened
    no trace, so a caller prints the line only when there is a page to open.
    """
    if client is None or not trace_id:
        return None
    try:
        return client.get_trace_url(trace_id=trace_id)
    except Exception as exc:                       # noqa: BLE001 - by contract
        _warn_once("trace url", exc)
        return None
