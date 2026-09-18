"""Role stages: compose the prompt, launch the brain, ingest the explicit result.

Contract highlights:
- One persistent CLI session per (run_id, role_id): Claude ids are minted by
  us (--session-id), Codex ids are the thread of its first turn; resume is
  always by exact id, never --last.
- Each role turn is the vendor's interactive CLI in the role's live terminal
  (`terminal`, beside this module), the prompt its argument. Reviewers are read-only via native
  flags (--permission-mode plan / --sandbox read-only) and end their final
  message with the {verdict, feedback} JSON, which is validated here.
- The workflow never treats hidden session history as its state: only the
  explicit output parsed here enters state. Malformed reviewer output is a
  content error, never a verdict: unparseable output says nothing about the work.
- Fresh-rehydrate happens only on a definitive session-not-found *before*
  work begins; every other failure surfaces as an error.
"""
import json
import re
import subprocess
import uuid

VERDICTS = ("PASS", "PATCH", "BLOCKER", "UNVERIFIED")
_VERDICT_ASK = ("End your final message with exactly one JSON object and nothing after it: "
                '{"verdict": "...", "feedback": "..."}, where verdict is one '
                "of PASS, PATCH, BLOCKER, UNVERIFIED; feedback lists each "
                "required finding with evidence and the smallest safe fix, or ")
_PASS_CONFIRMATION = "is a short confirmation on PASS."
# A plan's PASS stops the run for approval, and the operator approves from this
# text alone, so it is written for that decision rather than as a confirmation.
_PASS_PLAN_SUMMARY = ("on PASS is the summary a human reads before approving "
                      "implementation: at most six short lines stating the chosen "
                      "direction, the decision and why, the blast radius (what "
                      "changes and what could break), and what is reused versus "
                      "newly built.")
# What may follow the verdict object and still leave it the reviewer's last word.
_ENDS_THERE = re.compile(r"\s*(?:```)?\s*")
# Definitive "that session does not exist, nothing ran" signatures, as each
# interactive CLI shows them in its terminal before exiting without any work —
# the only condition that permits auto-rehydration. Measured on the installed binaries.
_NOT_FOUND = ("no saved session found with id",              # codex resume
              "no conversation found with session id")       # claude --resume


class TransportError(RuntimeError):
    """The brain could not be reached/completed; never a verdict: a brain we could not
    reach has not judged anything, so the run stops instead of routing."""
    # All the trace can say for certain is that the agent CLI exited non-zero: no
    # measured signature tells a rate limit or a network fault from any other exit.
    error_type = "agent_exit"


class ContentError(RuntimeError):
    """The brain answered but the answer is unusable; never a verdict."""
    error_type = "malformed_output"


def build_argv(role_name, role, resume_id, run_dir, settings=None):
    """Compose the CLI invocation. Returns (argv, minted_session_or_None).

    An argv list, launched without a shell: no value here is ever parsed as shell
    syntax, whatever it contains. The interactive CLI of each vendor; the runner adds
    the turn's completion hook and the prompt as the last argument. `settings` is a
    Claude settings file that switches the tracing plugin on for this role-run only.
    """
    reviewer = role["workspace_access"] == "read"
    model = role.get("model")
    effort = role.get("reasoning_effort")
    if role["brain"] == "claude":
        parts = ["claude"]
        if settings:
            parts += ["--settings", settings]
        minted = None
        if resume_id:
            parts += ["--resume", resume_id]
        else:
            minted = str(uuid.uuid4())
            parts += ["--session-id", minted]
        if model:
            parts += ["--model", model]
        if effort:
            parts += ["--effort", effort]
        if reviewer:
            parts += ["--permission-mode", "plan"]
        else:
            # A role turn never waits on a permission prompt: what is not allowed is denied and
            # the agent works on, as a run with no one to ask always did. Edits in the worktree
            # are allowed; an Edit rule also governs writes.
            parts += ["--permission-mode", "dontAsk", "--allowedTools", "Edit(./**)"]
        return parts, minted
    if role["brain"] == "codex":
        sandbox = "read-only" if reviewer else "workspace-write"
        parts = ["codex", "resume", resume_id] if resume_id else ["codex"]
        # Both forms take the flag. An interactive Codex would otherwise ask before
        # commands; a role turn runs them under its sandbox or not at all, as `exec` did.
        sandbox_args = ["--sandbox", sandbox, "--ask-for-approval", "never"]
        # Live web search on: the roles are told to prefer current out-of-the-box
        # practice over folklore, and the architect may challenge the task itself
        # (D15). Set explicitly rather than relying on the provider default, and
        # through the validated config key — an unknown key or value is rejected
        # at startup, so a vendor rename fails loudly instead of silently
        # downgrading the architect to stale knowledge.
        # Reasoning summaries are OFF by default on this account — measured:
        # 23,253 stored reasoning records carried encrypted content and not one
        # readable summary, because the vendor ran with `reasoning summaries:
        # none`. They are what makes a verdict legible, so ask for them
        # explicitly; the same strict config validation applies, so a rename
        # fails loudly instead of quietly returning us to opaque reviews.
        parts += ["-c", 'model_reasoning_summary="detailed"']
        parts += ["-c", 'web_search="live"'] + sandbox_args
        if model:
            parts += ["--model", model]
        if effort:
            # No flag for this; the documented config key is validated
            # strictly, so a vendor rename fails loudly.
            parts += ["-c", 'model_reasoning_effort="%s"' % effort]
        return parts, None
    raise ContentError("unknown brain %r" % role["brain"])


def extract_session(role, resume_id, minted, rc, out):
    """Return this role-run's agent_session_id, honouring the fallback rule."""
    if resume_id:
        return resume_id
    if role["brain"] == "claude":
        return minted
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "thread.started" and event.get("thread_id"):
            return event["thread_id"]
    raise TransportError("codex emitted no thread.started event (rc=%d)" % rc)


def classify_failure(role, resume_id, rc, out, err_text):
    """Definitive session-not-found before work → rehydrate; else error."""
    if resume_id and rc != 0:
        haystack = ((err_text or "") + out).lower()
        if any(sig in haystack for sig in _NOT_FOUND):
            return "session_lost"
    return "error"


def error_type(exc):
    """A failed stage's stable, low-cardinality class, which the trace filters and counts on.

    A failure's owner declares the class on its exception; a standard timeout is a
    timeout whoever raised it; anything else is an internal defect. Never taken
    from the message, which carries paths and ids that a class must not.
    """
    declared = getattr(type(exc), "error_type", None)
    if declared:
        return declared
    if isinstance(exc, (TimeoutError, subprocess.TimeoutExpired)):
        return "timeout"
    return "internal"


def parse_review(role, rc, out):
    """Parse the reviewer's {verdict, feedback}: the last such JSON object it gave; strict on purpose."""
    if rc != 0:
        raise TransportError("reviewer exited rc=%d" % rc)
    payload = None
    candidates = []
    lines = out.splitlines()
    ends = max((number for number, line in enumerate(lines) if line.strip()), default=-1)
    for number, line in enumerate(lines):
        line = line.strip()
        if line.startswith("{"):
            try:
                # A bare verdict object is the answer only as the reviewer's last word, as asked.
                candidates.append((json.loads(line), number == ends))
            except ValueError:
                pass
    for obj, last in reversed(candidates):
        # A Codex turn's output wraps the final message as an agent_message item.
        for probe in (obj if last else None, obj.get("result"), _codex_item(obj)):
            probe = _verdict_object(probe)
            if probe is not None:
                payload = probe
                break
        if payload:
            break
    if payload is None:
        # A Claude turn's output is the final message itself.
        payload = _verdict_object(out)
    if payload is None:
        raise ContentError("reviewer returned no parseable {verdict, feedback}")
    if payload["verdict"] not in VERDICTS or not isinstance(payload["feedback"], str):
        raise ContentError("reviewer payload invalid: %r" % (payload,))
    return payload["verdict"], payload["feedback"]


def _verdict_object(value):
    """The JSON object holding verdict and feedback that ends `value` — a dict, or text ending with one.

    The reviewer is asked to end its message with exactly that object and nothing after it, and the
    verdict routes the run, so only blank space or a closing code fence may follow it: a verdict the
    reviewer then wrote past is not the answer it gave. Reasoning before it is expected.
    """
    if isinstance(value, dict):
        return value if set(value) >= {"verdict", "feedback"} else None
    if not isinstance(value, str):
        return None
    decoder = json.JSONDecoder()
    found = None
    index = value.find("{")
    while index != -1:
        try:
            obj, end = decoder.raw_decode(value, index)
        except ValueError:
            index = value.find("{", index + 1)
            continue
        if isinstance(obj, dict) and set(obj) >= {"verdict", "feedback"}:
            found = obj if _ENDS_THERE.fullmatch(value[end:]) else None
        index = value.find("{", end)
    return found


def compose_prompt(stage, stage_cfg, is_architect, state, session_first,
                   stage_first, logs="the run's logs", skills=None):
    """Everything a stage needs, explicitly from state — no hidden memory.

    HOW a role acts lives in its persona file (read every invocation, so an
    edit applies from the next session). Mechanics — task at session birth,
    the stage ask, feedback/re-check deltas, operator guidance — stay here:
    workflow, not personality. A role's session persists across its stages
    (engineer: plan→build; architect: assess→verify), so the stage ask
    re-anchors the session when the stage changes.

    Invariant: a prompt built with `session_first=True` must be independently
    executable from zero — state and the worktree are the only context a
    rehydrated role gets.
    """
    todo = state["todo_path"]
    lines = []
    # A host may bind its own skill to a stage (`stage_skills` in the policy): its methodology,
    # which this component does not own. An invocation only takes effect as the prompt's very
    # first characters (measured: a trailing `/name` is inert), so it leads the composed prompt
    # and everything after it — task, persona, stage ask — is its argument. Only when the skill
    # is not already loaded in this session: a session persists across its stages, but a role's
    # two stages can be bound to different skills.
    skill = (skills or {}).get(stage)
    if skill and (session_first or stage_first):
        lines += [skill, ""]
    if session_first:
        lines += ["# Task", state["task"], "",
                  _template(stage_cfg, todo)]        # the ROLE's persona file
    # A session being born has no memory to lean on, so it always gets the
    # full current-stage bootstrap — whatever the attempt number. Without
    # this a session lost mid-loop would be rehydrated with a delta that
    # references findings and instructions it never received.
    if stage_first or session_first:
        lines += [STAGE_ASK[stage].replace("{{TODO_PATH}}", todo).replace("{{LOGS}}", logs)]
        if state.get("feedback"):
            lines += ["",
                      "# Your prior findings on this artifact — re-check each"
                      if is_architect else "# Architect findings to address",
                      state["feedback"]]
    else:
        if is_architect:
            lines += ["The artifact was revised in response to your findings — "
                      "re-check whether each was addressed or explicitly refuted; "
                      "re-verify refutations against the code before insisting.",
                      "(Your stage instructions are unchanged: judge the artifact "
                      "at %s and end with the verdict JSON.)" % todo]
        else:
            lines += ["# Architect findings to address", state.get("feedback", ""),
                      "Handle them per your feedback-handling instructions: fix "
                      "what is valid; refute what is not, with evidence "
                      "(todo: %s)." % todo]
    if state.get("guidance"):
        lines += ["", "# Operator guidance", state["guidance"]]
    return "\n".join(lines) + "\n"


# What each stage demands is workflow contract (the todo path, the diff),
# not personality — so it lives here, next to the workflow that depends on it.
# The architect judges at the level of architecture — the todo, the diff, the engineer's
# own reports and the web — and leaves running tests to the engineer, whose reports carry them.
_ARCHITECT_EVIDENCE = ("Judge from the todo, the repository, `git diff`, the engineer's "
                       "reports (its final messages, in {{LOGS}}/plan-*.out and build-*.out) "
                       "and the web. Do not run tests or builds.\n")
STAGE_ASK = {
    "plan": ("Investigate the task in the "
             "current repository and write the reviewable todo to exactly: "
             "{{TODO_PATH}}\nDo not implement. Do not commit."),
    "assess": ("Independently assess the todo at {{TODO_PATH}} against the "
               "actual repository.\n" + _ARCHITECT_EVIDENCE + _VERDICT_ASK + _PASS_PLAN_SUMMARY),
    "build": ("Implement the "
              "approved todo at {{TODO_PATH}} in this worktree.\n"
              "Never run git commit or git push."),
    "verify": ("Independently verify the implementation in this worktree "
               "(inspect `git diff` and `git status`) against the todo at "
               "{{TODO_PATH}}.\n" + _ARCHITECT_EVIDENCE + _VERDICT_ASK + _PASS_CONFIRMATION),
}


def _template(role_cfg, todo_path):
    with open(role_cfg["prompt_path"], encoding="utf-8") as fh:
        return fh.read().replace("{{TODO_PATH}}", todo_path).rstrip("\n")


def _codex_item(obj):
    item = obj.get("item") if isinstance(obj, dict) else None
    if isinstance(item, dict) and item.get("type") == "agent_message":
        return item.get("text")
    return None
