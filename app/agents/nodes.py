"""Role stages: compose the prompt, launch the role's agent, ingest the explicit result.

Contract highlights:
- One persistent CLI session per (run_id, role_id), resumed always by exact id, never --last. Whether an id
  is minted before a session's first turn or learned from it is the role's kind's (`app.agents.adapters`).
- Each role turn is the agent's interactive CLI in the role's live terminal (`terminal`, beside this
  module), the prompt its argument, built by its kind. A read-only role runs under its kind's read-only
  mode; a review ends its final message with the {verdict, feedback} JSON, which is validated here, for
  every kind alike, and research answers with its final message.
- The workflow never treats hidden session history as its state: only the explicit output parsed here
  enters state. Malformed reviewer output is a content error, never a verdict: unparseable output says
  nothing about the work.
- Fresh-rehydrate happens only on a definitive session-not-found *before* work begins; every other
  failure surfaces as an error.
"""
import json
import re
import subprocess

from app.agents import adapters
from app.foundation import stages

# What may follow the verdict object and still leave it the reviewer's last word.
_ENDS_THERE = re.compile(r"\s*(?:```)?\s*")
CONVERGENCE_REFLECTION = {
    "engineer": """The normal review budget has elapsed. Reflect on your own work and the architect's review before continuing.

Check whether you misunderstood a requirement, repeated a failed approach, or left a regression. Re-check every open
architect finding against the current code and tests. Fix supported findings. If you disagree, answer the finding with
specific repository evidence and propose a correction to the review only when that evidence supports it. Do not dismiss
feedback because a different design is your preference. Use a different implementation or investigation strategy when
the evidence shows the current one is not converging. Ask the operator only when a concrete decision blocks safe progress.""",
    "architect": """The normal review budget has elapsed. Reflect on your own review and the engineer's work before continuing.

Check each finding for current evidence, duplicate or stale claims, and assumptions that changed. Re-evaluate the
engineer's fixes and refutations against the code and tests. Accept supported corrections and withdraw findings that
are unsupported, already resolved, or outside the agreed goal. For anything that remains, state the evidence and the
smallest safe correction. Do not require a preferred design without a concrete reason. Return BLOCKER only when a
specific human decision is required; otherwise continue with concrete findings.""",
}
FINAL_REVIEW_SUMMARY = {
    "engineer": """This is the last budgeted iteration for this phase. Finish changes supported by the review and leave the architect
a concise, factual handoff in the run's todo: what you changed, what evidence you checked, which architect findings you
addressed or refuted, and what remains unresolved. Do not assume another engineer turn will follow.""",
    "architect": """This is the last budgeted iteration for this phase. If your verdict is PATCH or UNVERIFIED, make feedback an
evidence summary with separate sections named Engineer contribution and Architect assessment. State what remains
unresolved; what the engineer tried or changed; which architect findings the engineer addressed or disputed and the
evidence on each side; your remaining findings; the likely cause (task ambiguity, implementation or reasoning,
reviewer disagreement or overreach, or an external blocker); and the exact operator decision or input needed. Keep the
verdict JSON contract. For PASS or BLOCKER, follow the usual verdict and stop rules.""",
}


class TransportError(RuntimeError):
    """The agent could not be reached/completed; never a verdict: an agent we could not reach has not judged
    anything, so the run stops instead of routing."""
    # All the trace can say for certain is that the agent CLI exited non-zero: no measured signature tells a
    # rate limit or a network fault from any other exit.
    error_type = "agent_exit"


class ContentError(RuntimeError):
    """The agent answered but the answer is unusable; never a verdict."""
    error_type = "malformed_output"


def build_argv(role, resume_id, traced=None):
    """The role's agent CLI for one turn, as its kind builds it, and the session id it minted, if any.

    An argv list, launched without a shell: no value here is ever parsed as shell syntax, whatever it
    contains. The runner adds the turn's completion wiring and the prompt as the last argument. `traced` is
    what the kind's own tracing gave this turn, which only it reads.
    """
    return adapters.for_role(role).command(adapters.view(role), resume_id, traced)


def extract_session(role, resume_id, minted, rc, out):
    """This role-run's agent_session_id, honouring the fallback rule."""
    if resume_id:
        return resume_id
    found = adapters.for_role(role).session(out, minted)
    if not found:
        raise TransportError("the agent's turn named no session (rc=%d)" % rc)
    return found


def classify_failure(role, resume_id, rc, out, err_text):
    """Definitive session-not-found before work → rehydrate; else error. How a lost session shows is the
    role's kind's, as its CLI says it in its terminal before exiting without any work (measured)."""
    if resume_id and rc != 0:
        haystack = ((err_text or "") + out).lower()
        if any(sig in haystack for sig in adapters.for_role(role).LOST_SESSION):
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
    # Where the agent's own message sits in its output is its kind's; the verdict it ends with is read here,
    # one grammar for every kind.
    message_of = adapters.for_role(role).message_of
    for obj, last in reversed(candidates):
        for probe in (obj if last else None, message_of(obj)):
            probe = _verdict_object(probe)
            if probe is not None:
                payload = probe
                break
        if payload:
            break
    if payload is None:
        # An output that is the final message itself.
        payload = _verdict_object(out)
    if payload is None:
        raise ContentError("reviewer returned no parseable {verdict, feedback}")
    if payload["verdict"] not in stages.VERDICTS or not isinstance(payload["feedback"], str):
        raise ContentError("reviewer payload invalid: %r" % (payload,))
    return payload["verdict"], payload["feedback"]


def final_message(role, out):
    """A work stage's answer when its product is that answer: its final message, as the role's kind finds
    it in the turn's output. An empty one is no answer."""
    adapter = adapters.for_role(role)
    text = (adapter.final_message(out) or "").strip()
    if not text:
        raise ContentError("the %s gave no answer" % adapter.NAME)
    return text


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


def compose_prompt(stage, stage_cfg, is_review, state, session_first,
                   stage_first, logs="the run's logs", skills=None, review_rounds=None, review_prompts=None):
    """Everything a stage needs, explicitly from state — no hidden memory.

    HOW a role acts lives in its persona, which the run carries from its start, so
    no later edit reaches it (a run started before agent profiles still reads its
    persona file when a session is born). Mechanics — task at session birth,
    the stage ask, feedback/re-check deltas, operator guidance — stay here:
    workflow, not personality. A role's session persists across its stages
    (engineer: plan→build; architect: research→assess→verify), so the stage ask
    re-anchors the session when the stage changes. `is_review` is the stage's,
    from the stages' contract: a review re-checks its findings, work addresses them.

    Invariant: a prompt built with `session_first=True` must be independently
    executable from zero — state and the worktree are the only context a
    rehydrated role gets.
    """
    todo = state["todo_path"]
    lines = []
    # The operator may bind a skill to a stage (`stage_skills`): its methodology, which this component
    # does not own. An invocation only takes effect as the prompt's very first characters (measured: a
    # trailing one is inert), so it leads the composed prompt and everything after it — task, persona,
    # stage ask — is its argument; how it is spelled is the role's kind's. Only when the skill is not
    # already loaded in this session: a session persists across its stages, but a role's stages can each
    # be bound to a different skill. A run of the old shape named it `/name`.
    named = (skills or {}).get(stage)
    skill = adapters.skill(adapters.for_role(stage_cfg), named[1:] if named and named.startswith("/") else named)
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
        lines += [stages.STAGE_ASK[stage].replace("{{TODO_PATH}}", todo).replace("{{LOGS}}", logs)]
        # A flow that began with research hands its brief to the plan that turns it into a todo, and a
        # research session born again gets the brief it gave, which the operator's feedback is about.
        if stage == "plan" and state.get("brief"):
            lines += ["", "# The architect's research brief — check its abstract todo against the code",
                      state["brief"]]
        elif stage == "research" and session_first and state.get("brief"):
            lines += ["", "# Your previous brief", state["brief"]]
        if state.get("feedback"):
            lines += ["",
                      "# Your prior findings on this artifact — re-check each"
                      if is_review else "# Architect findings to address",
                      state["feedback"]]
    else:
        if is_review:
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
    convergence = state.get("convergence") or {}
    role_name = stages.STAGE_ROLE[stage]
    seen = state.get("convergence_seen") or []
    if (convergence.get("phase") == state.get("phase") and
            (session_first or role_name not in seen)):
        extra = ((review_prompts or {}).get("after_normal") or {}).get(role_name, "").strip()
        lines += ["", "# Convergence reflection",
                  "The normal review budget of %d iterations has elapsed.\n\n%s" %
                  (convergence["round"], CONVERGENCE_REFLECTION[role_name])]
        if extra:
            lines += ["", "# Operator's additional reflection guidance", extra]
    thresholds = (review_rounds or {}).get(state.get("phase"))
    if thresholds:
        review_number = state.get("round", 0) + 1
        if review_number >= thresholds["normal"] + thresholds["extended"]:
            extra = ((review_prompts or {}).get("at_limit") or {}).get(role_name, "").strip()
            lines += ["", "# Final budget handoff", FINAL_REVIEW_SUMMARY[role_name]]
            if extra:
                lines += ["", "# Operator's additional final-turn guidance", extra]
    return "\n".join(lines) + "\n"


def _template(role_cfg, todo_path):
    """The role's persona: the text its run's policy carries from the run's start, or — for a run of the
    old shape — the file this host resolved for it."""
    if "persona" in role_cfg:
        text = role_cfg["persona"]
    else:
        with open(role_cfg["prompt_path"], encoding="utf-8") as fh:
            text = fh.read()
    return text.replace("{{TODO_PATH}}", todo_path).rstrip("\n")
