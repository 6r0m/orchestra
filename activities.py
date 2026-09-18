"""Everything a run does to the world, on its target host: resolve, worktree, roles, merge, trace.

Each activity runs on the task queue of the run's target host, so the host's own git,
agent executables, provider stores and paths are the ones used. The
workflow sends a compact state and receives only explicit results; it never sees a
transcript.

Temporal would retry an activity without limit by default. A role-run and every git
side effect run once instead: a failure stops the run for the
operator, and the operator's Continue is the only way anything runs again.
"""
import os
import sys

from temporalio import activity
from temporalio.exceptions import ApplicationError

import nodes as N
import policy as P
import repos
import routing
import telemetry as T
import terminal
import trust
import worktrees as W


# An agent's git can neither push nor reach any remote. The rewrite covers every
# remote without its own push URL and cannot be undone with `git -c`; refusing every
# transport also covers a remote with a push URL. `GIT_ALLOW_PROTOCOL` names the only
# transports allowed and takes precedence over the `protocol.allow` configuration, so
# a deliberate `git -c protocol.allow=always` no longer lifts the refusal; the value
# is a protocol name that does not exist, which allows none. Local work — `status`,
# `diff`, `log`, `add`, `commit` — is unaffected, all measured.
AGENT_GIT = {"GIT_CONFIG_COUNT": "2",
             "GIT_CONFIG_KEY_0": "url.orchestration-push-blocked:.pushInsteadOf",
             "GIT_CONFIG_VALUE_0": "",
             "GIT_CONFIG_KEY_1": "protocol.allow",
             "GIT_CONFIG_VALUE_1": "never",
             "GIT_ALLOW_PROTOCOL": "orchestration-none"}
# Set for this worker only: inherited, they would point an agent's tools at the
# environment the worker itself imports from.
WORKER_ONLY = ("UV_PROJECT_ENVIRONMENT", "VIRTUAL_ENV")
# A worker started from inside a Claude Code session inherits that session's markers, and a
# Claude agent carrying them runs as its child: measured, it saves no transcript, so its
# session cannot be resumed by id.
PARENT_SESSION = ("CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT", "CLAUDE_AGENT_SDK_VERSION")
PARENT_SESSION_PREFIX = "CLAUDE_CODE_"
WINDOWS = sys.platform.startswith("win")
# Codex's elevated Windows sandbox starts its helper through an administrator prompt,
# which a worker running outside the interactive desktop can never show: every command
# the agent runs then fails with error 1223. The unelevated sandbox needs no prompt, and
# the read-only and workspace-write policies still hold inside it.
WINDOWS_CODEX = ["-c", 'windows.sandbox="unelevated"']


class GitViolation(RuntimeError):
    """A role changed what only the controller may: HEAD, the run's branch or what is staged."""
    error_type = "git_violation"


def run_dir(run_id):
    return os.path.join(repos.RUNTIME_ROOT, run_id)


def host_argv(argv, brain, windows=WINDOWS, skills=None):
    """The agent's argv as this host must launch it."""
    if windows and brain == "codex":
        return list(argv) + WINDOWS_CODEX
    if brain == "claude":
        # The skills a stage invokes read their references from this host's skills directory,
        # outside the worktree; as a working directory it needs no approval to read.
        skills = skills or os.path.join(os.path.expanduser("~"), ".claude", "skills")
        if os.path.isdir(skills):
            return list(argv) + ["--add-dir", os.path.realpath(skills)]
    return list(argv)


def agent_env(extra):
    env = {key: value for key, value in os.environ.items()
           if key not in WORKER_ONLY and key not in PARENT_SESSION and not key.startswith(PARENT_SESSION_PREFIX)}
    env.update(AGENT_GIT)
    env.update(extra or {})
    return env


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _failure(exc):
    """The failure the workflow stops on: its class and message, and never retried."""
    return ApplicationError("%s: %s" % (N.error_type(exc), exc), type=type(exc).__name__,
                            non_retryable=True)


class Activities:
    """The activities of one host, with the seams tests replace: execution, git, repositories, trace."""

    def __init__(self, runner=terminal.run_turn, git=W, repositories=repos, telemetry=T.resolve):
        self.runner = runner
        self.git = git
        self.repositories = repositories
        self._telemetry = telemetry
        self._client = None
        self._resolved = False

    def all(self):
        return [self.prepare, self.create_worktree, self.open_run, self.open_phase, self.run_role,
                self.record_stop, self.record_answer, self.finish_trace, self.merge, self.discard,
                self.worktree_view, self.review_diff, self.work_tree]

    def client(self):
        if not self._resolved:
            self._client = self._telemetry() if callable(self._telemetry) else self._telemetry
            self._resolved = True
        return self._client

    @activity.defn
    def prepare(self, args):
        """Resolve the repository on this host, refusing before any work."""
        selected, policy = args["repository"], args["policy"]
        brains = [role["brain"] for role in policy["roles"].values()]
        try:
            resolved = self.repositories.resolve(
                selected, brains, policy["targets"][selected["target"]]["worktree_root"])
        except repos.Refused as exc:
            raise ApplicationError(str(exc), type="Refused", non_retryable=True)
        # The CLIs' trust dialog asks what repos.json already answers, and would stop this run's
        # first turn until someone answered it in the page. Best effort; never fails the run.
        trust.ensure(resolved["repo_path"], brains)
        return resolved

    @activity.defn
    def create_worktree(self, args):
        state = args["state"]
        try:
            path = self.git.create(state["repo_path"], state["base_branch"], state["worktree_root"],
                                   state["run_id"], state["target"], state.get("lfs_pointers", False))
        except Exception as exc:
            raise _failure(exc) from exc
        plan = W.plan_path(state["todo_dir"], state["todo_name"], state["created"], state["task"])
        return {"worktree_path": path, "worktree": path, "plan": plan, "todo_path": os.path.join(path, plan)}

    @activity.defn
    def open_run(self, args):
        state, client = args["state"], self.client()
        trace_id, root = T.open_work_item(client, state)
        ids = dict(state, trace_id=trace_id, trace_root=root)
        phase = T.open_phase(client, ids, "plan")
        T.flush(client)
        return {"trace_id": trace_id, "trace_root": root, "trace_phases": {"plan": phase}}

    @activity.defn
    def open_phase(self, args):
        client = self.client()
        node = T.open_phase(client, args["state"], args["phase"])
        T.flush(client)
        return {"id": node}

    @activity.defn
    def run_role(self, args):
        """One stage: its role's agent launched once, its explicit result returned."""
        state, stage, policy = args["state"], args["stage"], args["policy"]
        role_name = P.STAGE_ROLE[stage]
        role = dict(policy["roles"][role_name])
        # The persona file as this host sees it.
        role["prompt_path"] = os.path.join(repos.REPO, role["prompt"])
        is_reviewer = role["workspace_access"] == "read"
        resume_id = (state.get("agent_sessions") or {}).get(role_name)
        rdir = run_dir(state["run_id"])
        attempt, episode = state.get("round", 0) + 1, state.get("episode", 1)
        # Episode-scoped so a guidance reset cannot overwrite an earlier episode's logs.
        name = "%s-e%d-%d" % (stage, episode, attempt)
        worktree = state["worktree_path"]
        client = self.client()

        def compose(session_first):
            return N.compose_prompt(stage, role, is_reviewer, state, session_first=session_first,
                                    stage_first=attempt == 1, logs=os.path.join(rdir, "logs"),
                                    skills=policy.get("stage_skills"))

        span = T.begin(client, state, stage, role_name, role,
                       log=os.path.relpath(os.path.join(rdir, "logs", name), repos.REPO))
        settings = None
        try:
            # Holds the trace store's secret, so it exists only while this stage runs.
            settings = T.harness_settings(role, span)
            env = agent_env(T.harness_env(role, span, state, stage, role_name))
            # Again before every turn, not once per run: a CLI that was running when the record was
            # written rewrites that file from its own copy when it exits, and takes the record with
            # it (measured). Re-recording costs one small read; losing it costs a stopped turn.
            if state.get("repo_path"):
                trust.ensure(state["repo_path"], [role["brain"]])
            before = self.git.guard(worktree, state["run_id"])
            # The terminals stay live while the architect reviews, so what it judged is the tree as its
            # turn began, and a change during that turn fails the step rather than passing unjudged:
            # a verdict must describe the plan or the change it actually read.
            judged = self.git.work_tree(worktree) if is_reviewer else None
            argv, minted = N.build_argv(role_name, role, resume_id, rdir, settings)
            argv = host_argv(argv, role["brain"])
            rc, out = self.runner(worktree, argv, rdir, name, compose(resume_id is None),
                                  policy["timeout_seconds"], env, brain=role["brain"])
            effective_resume = resume_id
            if rc != 0 and N.classify_failure(role, resume_id, rc, out,
                                              _read(os.path.join(rdir, "logs", name + ".err"))) == "session_lost":
                # Definitive not-found before any work began: a fresh session gets the
                # whole task again, since the lost one took the task and persona with it.
                T.warn(span, "session_lost",
                       "the %s session to resume was not found; a fresh one was started and "
                       "given the whole task again" % role_name)
                effective_resume = None
                argv, minted = N.build_argv(role_name, role, None, rdir, settings)
                argv = host_argv(argv, role["brain"])
                rc, out = self.runner(worktree, argv, rdir, name + "-rehydrated", compose(True),
                                      policy["timeout_seconds"], env, brain=role["brain"])
            if rc != 0:
                raise N.TransportError("%s failed rc=%d — inspect %s/logs/%s.*" % (stage, rc, rdir, name))
            if self.git.guard(worktree, state["run_id"]) != before:
                raise GitViolation("the %s changed the worktree's HEAD, branch or staged content, "
                                   "which only the controller may" % role_name)
            session = N.extract_session(role, effective_resume, minted, rc, out)
            result = {"agent_sessions": {role_name: session}}
            gate_reason = None
            if is_reviewer:
                verdict, feedback = N.parse_review(role, rc, out)
                result.update(verdict=verdict, feedback=feedback)
                # The routing is the workflow's; the trace only records what it will be.
                gate_reason = routing.gate_reason_for(
                    verdict, state["phase"], attempt, policy["max_rounds"][state["phase"]],
                    state.get("auto_proceed", False))
                if verdict == "PASS" and judged is not None:
                    if self.git.work_tree(worktree) != judged:
                        raise GitViolation("the worktree changed while the architect judged it, so what it "
                                           "passed is not what is there; continue to %s it again" % stage)
                    # What the run may go on with: exactly what was judged here — the plan the
                    # operator is about to approve, or the change a merge may commit.
                    result["assessed_tree" if stage == "assess" else "verified_tree"] = judged
        except Exception as exc:
            # A failed step leaves no agent behind, whichever check failed it.
            terminal.end_agent(state["run_id"], role_name)
            T.end(span, error_type=N.error_type(exc), error=exc)
            T.flush(client)
            raise _failure(exc) from exc
        finally:
            T.discard_settings(settings)
        T.upload_codex_session(client, role, session, state, stage, role_name, span)
        T.end(span, verdict=result.get("verdict"), gate_reason=gate_reason,
              # The verdict routes, but the reasoning behind it is what a person reads first.
              feedback=result.get("feedback"),
              # The engineer's own account of what it did, where the architect's feedback sits.
              response=None if is_reviewer else out,
              reasoning=T.codex_reasoning(role, session) if is_reviewer else None,
              session=session)
        T.flush(client)
        return result

    @activity.defn
    def record_stop(self, args):
        client = self.client()
        T.gate_event(client, args["state"], args["stop"])
        T.flush(client)

    @activity.defn
    def record_answer(self, args):
        client = self.client()
        T.gate_answer(client, args["state"], args["answer"])
        T.flush(client)

    @activity.defn
    def finish_trace(self, args):
        state, client = args["state"], self.client()
        if state.get("status") == "ABORTED":
            # An aborted run keeps its worktree but no longer needs its live terminals.
            terminal.close_run(state["run_id"])
        T.final_diff(client, state, W.review_diff)
        T.outcome_score(client, state)
        T.flush(client)
        return {"trace_url": T.trace_url(client, state.get("trace_id"))}

    @activity.defn
    def merge(self, args):
        state = args["state"]
        stem = os.path.splitext(os.path.basename(state["plan"]))[0]
        words = " ".join(state["task"].encode("ascii", "ignore").decode().split()[:8])
        # No agent may change the worktree between the check of the verified tree and the commit,
        # nor hold it open while it is removed; a conflict's next turn opens the terminals again.
        terminal.close_run(state["run_id"])
        try:
            return self.git.merge(state["repo_path"], state["worktree_path"], state["run_id"],
                                  state["base_branch"], state.get("verified_tree"), state["plan"],
                                  state["todo_done_dir"], ("%s: %s" % (stem, words))[:100],
                                  "Merge %s" % stem)
        except W.MergeRefused as exc:
            return {"result": "refused", "reason": str(exc)}
        except Exception as exc:
            raise _failure(exc) from exc

    @activity.defn
    def discard(self, args):
        state = args["state"]
        terminal.close_run(state["run_id"])
        try:
            self.git.discard(state["repo_path"], state["worktree_path"], state["run_id"])
        except Exception as exc:
            raise _failure(exc) from exc
        return {"result": "discarded"}

    @activity.defn
    def review_diff(self, args):
        """The run's change as the operator reviews it, read by this host's own git. Reads only.

        Bounded: `offset` asks for the next part of a change too large for one payload.
        """
        try:
            return self.git.review_diff(args["worktree_path"], args.get("offset", 0))
        except Exception as exc:
            raise _failure(exc) from exc

    @activity.defn
    def work_tree(self, args):
        """The tree this worktree would commit now, for the controller's own checks. Reads only."""
        try:
            return {"tree": self.git.work_tree(args["worktree_path"])}
        except Exception as exc:
            raise _failure(exc) from exc

    @activity.defn
    def worktree_view(self, args):
        """Every worktree the target's git reports, and whether it is merged. Reads only."""
        try:
            resolved = self.repositories.resolve(args["repository"], [], args["worktree_root"])
            return {"base_branch": resolved["base_branch"],
                    "rows": self.git.view(resolved["repo_path"], resolved["base_branch"])}
        except repos.Refused as exc:
            raise ApplicationError(str(exc), type="Refused", non_retryable=True)
