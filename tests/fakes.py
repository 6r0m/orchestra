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


class FakeAgent:
    """The Temporal path's execution seam: scripted (rc, stdout) per role-run, each call recorded.

    `command` is the argv joined, the tests' window into session identity and flags.
    """

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def __call__(self, worktree, argv, run_dir, name, prompt, timeout_seconds, env, *, brain):
        self.calls.append({"worktree": worktree, "argv": list(argv), "command": " ".join(argv),
                           "name": name, "prompt": prompt, "env": env, "brain": brain})
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

    def create(self, repo, base, root, run_id, target, lfs_pointers=False):
        self.calls.append(("create", run_id, target))
        return "/fake/worktree/%s" % run_id

    def guard(self, path, run_id):
        return "unchanged"

    def work_tree(self, path):
        return "verified-tree"

    def merge(self, repo, worktree, run_id, base, verified_tree, plan, done_dir, message, merge_message):
        self.calls.append(("merge", run_id, verified_tree, message, merge_message))
        return self.merge_results.pop(0)

    def discard(self, repo, worktree, run_id):
        self.calls.append(("discard", run_id))

    def view(self, repo, base):
        return [{"path": "/fake/worktrees/one", "branch": "one", "state": "unmerged"},
                {"path": "/fake/worktrees/two", "branch": "two", "state": "merged"}]

    def review_diff(self, path, offset=0):
        self.calls.append(("review_diff", path, offset))
        patch = "diff --git a/x b/x\n"
        return {"base": "abc1234", "summary": " 1 file changed", "summary_total": 15,
                "patch": patch[offset:], "offset": offset, "next": len(patch), "total": len(patch),
                "snapshot": "0" * 32}


class FakeRepos:
    """Stands in for `repos.resolve`: a fixed resolution, or a refusal."""

    def __init__(self, refusal=None):
        self.refusal = refusal

    def resolve(self, selected, brains, worktree_root):
        if self.refusal:
            from app.workspace import repos
            raise repos.Refused(self.refusal)
        return {"repo_path": "/fake/repo", "base_branch": "develop", "worktree_root": "/fake/worktrees",
                "todo_dir": "todo", "todo_done_dir": "todo/done", "todo_name": "%Y-%m-%d_%H%M-{slug}"}


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
