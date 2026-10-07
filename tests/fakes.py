"""Test doubles for the world a run touches: no agent CLI, no git, no network.

FakeAgent replays scripted (rc, stdout) per role-run and records every argv — the
tests' window into session identity, read-only flags and the --last ban.
"""
import json
import uuid


def codex_first_out(payload_text, thread_id=None):
    tid = thread_id or str(uuid.uuid4())
    lines = [json.dumps({"type": "thread.started", "thread_id": tid}),
             json.dumps({"type": "item.completed",
                         "item": {"id": "item_0", "type": "agent_message",
                                  "text": payload_text}}),
             json.dumps({"type": "turn.completed", "usage": {}})]
    return "\n".join(lines) + "\n", tid


def codex_review_first(verdict, feedback="fb", thread_id=None):
    return codex_first_out(json.dumps({"verdict": verdict, "feedback": feedback}),
                           thread_id)


def codex_review_resumed(verdict, feedback="fb"):
    return "thinking...\n" + json.dumps({"verdict": verdict, "feedback": feedback}) + "\n"


def first_message_for(settings, role, message):
    kind = settings["agents"][settings["roles"][role]["agent"]]["kind"]
    if kind == "codex":
        return codex_first_out(message)
    if kind == "claude-code":
        return message, None
    raise AssertionError("no fake first message for agent kind %r" % kind)


def review_first_for(settings, role, verdict, feedback="fb"):
    message = json.dumps({"verdict": verdict, "feedback": feedback})
    return first_message_for(settings, role, message)


def review_resumed_for(settings, role, verdict, feedback="fb"):
    kind = settings["agents"][settings["roles"][role]["agent"]]["kind"]
    if kind == "codex":
        return codex_review_resumed(verdict, feedback)
    if kind == "claude-code":
        return json.dumps({"verdict": verdict, "feedback": feedback}) + "\n"
    raise AssertionError("no fake resumed review for agent kind %r" % kind)


class FakeAgent:
    """The Temporal path's execution seam: scripted (rc, stdout) per role-run, each call recorded.

    `command` is the argv joined, the tests' window into session identity and flags.
    """

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def __call__(self, worktree, argv, run_dir, name, prompt, timeout_seconds, env, *, kind):
        self.calls.append({"worktree": worktree, "argv": list(argv), "command": " ".join(argv),
                           "name": name, "prompt": prompt, "env": env, "kind": kind})
        if not self.script:
            raise AssertionError("unexpected extra invocation: %s" % name)
        expect, rc, out = self.script.pop(0)
        if not name.startswith(expect):
            raise AssertionError("expected %s got %s" % (expect, name))
        return rc, out


class FakeWorktrees:
    """Stands in for `worktrees`: no git, every call recorded, results chosen by the test."""

    def __init__(self, merge_results=None):
        self.calls = []
        self.merge_results = list(merge_results or [{"result": "merged", "commit": "c0ffee"}])
        # What a read of the change is refused with, as its host's git would refuse it; None reads it.
        self.diff_refusal = None
        # What each merge was handed to finish itself: the run's plan, or None when its closeout already had.
        self.finished = []
        # What a closeout changed since the architect's verification, as `changed` names it.
        self.closeout_changes = []

    def create(self, repo, base, root, run_id, target, lfs_pointers=False):
        self.calls.append(("create", run_id, target))
        return "/fake/worktree/%s" % run_id

    def guard(self, path, run_id):
        return "unchanged"

    def work_tree(self, path):
        return "verified-tree"

    def changed(self, path, base, tree):
        return list(self.closeout_changes)

    def reopen(self, worktree, closeout_tree, verified_tree):
        self.calls.append(("reopen", closeout_tree, verified_tree))
        return []

    def merge(self, repo, worktree, run_id, base, verified_tree, plan, done_dir, message, merge_message):
        self.calls.append(("merge", run_id, verified_tree, message, merge_message))
        self.finished.append(plan)
        return self.merge_results.pop(0)

    def discard(self, repo, worktree, run_id):
        self.calls.append(("discard", run_id))

    def view(self, repo, base):
        return [{"path": "/fake/worktrees/one", "branch": "one", "state": "unmerged"},
                {"path": "/fake/worktrees/two", "branch": "two", "state": "merged"}]

    def review_diff(self, path, offset=0, base=None, tree=None, file=None, files_from=None):
        self.calls.append(("review_diff", path, offset, base, tree, file, files_from))
        if self.diff_refusal:
            from app.workspace import worktrees
            raise worktrees.ChangeRefused(self.diff_refusal)
        patch = "diff --git a/x b/x\n"
        base, tree = base or "b" * 40, tree or "c" * 40
        if file is not None:
            return {"base": base, "tree": tree, "patch": patch, "whole": True,
                    "file": {"path": file, "old": None, "status": "M", "added": 1, "removed": 0, "binary": False}}
        return {"base": base, "tree": tree, "summary": " 1 file changed", "summary_total": 15,
                "files": [{"path": "x", "old": None, "status": "M", "added": 1, "removed": 0, "binary": False}],
                "files_total": 1, "patch": patch[offset:], "offset": offset, "next": len(patch), "total": len(patch)}


class FakeRepos:
    """Stands in for `repos.resolve`: a fixed resolution, or a refusal; each call recorded."""

    def __init__(self, refusal=None):
        self.refusal = refusal
        self.calls = []

    def resolve(self, selected, worktree_root):
        self.calls.append((selected, worktree_root))
        if self.refusal:
            from app.workspace import repos
            raise repos.Refused(self.refusal)
        return {"repo_path": "/fake/repo", "base_branch": "develop", "worktree_root": "/fake/worktrees",
                "todo_dir": "todo", "todo_done_dir": "todo/done", "todo_name": "%Y-%m-%d_%H%M-{slug}"}


def installed(program):
    """Stands in for `shutil.which` on a host that has every agent's program."""
    return "/fake/bin/%s" % program


def every_skill(folder):
    """Stands in for `activities.holds_skill` on a host that holds every skill a run invokes."""
    return True


class Recorder:
    """The part of a Langfuse client the trace uses, recording instead of sending.

    Metadata accumulates across updates, as the SDK's one attribute per key does.
    """

    def __init__(self):
        self.events = []
        self.scores = []

    def create_trace_id(self, seed=None):
        return "0" * 32

    def get_trace_url(self, *, trace_id=None):
        return "http://langfuse.test/traces/%s" % (trace_id or "")

    def create_score(self, **kwargs):
        self.scores.append(kwargs)

    def flush(self):
        pass

    def start_as_current_observation(self, **kwargs):
        record = dict(kwargs)
        self.events.append(record)

        class Span:
            def update(self, **fields):
                metadata = fields.pop("metadata", None)
                if metadata:
                    record["metadata"] = dict(record.get("metadata") or {}, **metadata)
                record.update(fields)

        class Context:
            def __enter__(self):
                return Span()

            def __exit__(self, *exc):
                return False

        return Context()
