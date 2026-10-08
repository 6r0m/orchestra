"""A run's worktree, through the target host's own git: create, guard, reconcile, reopen, merge, discard, list.

Only this module stages, commits, merges or reaches a remote, and only for the run it is given.
Every side effect reads what git already holds before acting, so an attempt whose
worker died after git wrote but before it reported is adopted when it runs again,
never applied twice.
"""
import datetime
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import uuid

from app.foundation import envpath


class GitError(RuntimeError):
    error_type = "git_error"


class MergeRefused(RuntimeError):
    """A guard or git refused the merge. Nothing was merged into the base branch."""


def git(path, *args, check=True, env=None):
    done = subprocess.run(["git", "-C", path] + list(args), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=1800)
    if check and done.returncode != 0:
        raise GitError("git %s in %s: rc=%d %s" % (" ".join(args[:2]), path, done.returncode,
                                                   (done.stderr or done.stdout).strip()[:500]))
    return done


def _same(a, b):
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


def worktrees(repo):
    """Every worktree git lists for `repo`, the main checkout first: path, head and branch."""
    entries = []
    for line in git(repo, "worktree", "list", "--porcelain").stdout.splitlines():
        if line.startswith("worktree "):
            entries.append({"path": os.path.normpath(line[len("worktree "):]), "head": None,
                            "branch": None})
        elif entries and line.startswith("HEAD "):
            entries[-1]["head"] = line[len("HEAD "):]
        elif entries and line.startswith("branch "):
            entries[-1]["branch"] = re.sub(r"^refs/heads/", "", line[len("branch "):])
    return entries


def branch_exists(repo, branch):
    return git(repo, "show-ref", "--verify", "--quiet", "refs/heads/" + branch,
               check=False).returncode == 0


def _ref(base, remote=None):
    """Where a repository's base lives: its own branch, or — when the base is a remote's — that remote's
    branch as this repository last fetched it."""
    return "refs/remotes/%s/%s" % (remote, base) if remote else "refs/heads/" + base


def _unattended():
    """Git's environment for a step no person watches: a remote that would ask for a credential fails
    instead of waiting for an answer nobody gives."""
    return dict(os.environ, GIT_TERMINAL_PROMPT="0")


def remote_id(repo, remote):
    """A fingerprint of where `remote` leads now: the one URL git would fetch from and the one it would push
    to, as the repository's configuration resolves them, rewrites included. The URLs themselves are never
    kept — one may carry a credential.

    A remote with more than one of either is refused: one push writes to every push URL in turn, and one
    may take a merge that another refuses — which is no landing on the repository's one source of truth.
    """
    urls = []
    for what, flags in (("fetch", ("--all",)), ("push", ("--push", "--all"))):
        found = [line for line in git(repo, "remote", "get-url", *flags, remote).stdout.splitlines() if line]
        if len(found) != 1:
            raise GitError("%s has %d %s URLs in this repository's configuration: a run begins from one place "
                           "and lands on one" % (remote, len(found), what))
        urls += found
    return hashlib.sha256("\0".join(urls).encode("utf-8")).hexdigest()


def _led(repo, remote, pinned):
    """Refuse a remote that no longer leads where it did when its run began (`pinned`, its `remote_id` then).
    A role's turn can rewrite the repository's configuration without touching anything the controller
    guards, and what is fetched from or pushed to another place is nothing the operator agreed to."""
    # Read whether or not a fingerprint was taken: a remote that leads to two places is refused by the read.
    led = remote_id(repo, remote)
    if pinned and led != pinned:
        raise GitError("%s no longer leads where it did when this run began: its URL, or a rewrite of it, changed "
                       "in the repository's configuration. Nothing is fetched from it or pushed to it" % remote)


def prepush_id(repo):
    """A fingerprint of what git would run before a push from `repo`: every hook its configuration states,
    as git resolves it, and the bytes of its pre-push hook's file, wherever git looks for one. Like where a
    remote leads (`remote_id`), a role's turn can change either without touching anything the controller
    guards — and a push made past a gate that is gone, or says something else, is one nobody agreed to.

    The file's mode is no part of it: one that is there and not executable is refused as that (`_passed_by`),
    and made executable it is the same hook.
    """
    stated = git(repo, "config", "--null", "--get-regexp", r"^hook\.", check=False)
    if stated.returncode not in (0, 1):
        # 1 is git's word for "none stated"; anything else is no answer.
        raise GitError("git config in %s: rc=%d %s" % (repo, stated.returncode, stated.stderr.strip()[:500]))
    path = os.path.join(repo, git(repo, "rev-parse", "--git-path", "hooks/pre-push").stdout.strip())
    held = b""
    if os.path.isfile(path):
        with open(path, "rb") as fh:
            held = fh.read()
    return hashlib.sha256(stated.stdout.encode("utf-8") + b"\0\0" + held).hexdigest()


def base_tip(repo, base, remote=None, pinned=None):
    """The commit the base is at now. A remote's is fetched first — that branch alone, into its own
    remote-tracking ref, and only from where the remote led when the run began (`pinned`): where a remote
    stands is the remote's to say, and a fetch that failed is no answer."""
    if remote:
        _led(repo, remote, pinned)
        git(repo, "fetch", "--quiet", "--no-tags", remote,
            "+refs/heads/%s:%s" % (base, _ref(base, remote)), env=_unattended())
    return git(repo, "rev-parse", "--verify", _ref(base, remote) + "^{commit}").stdout.strip()


def started_from(path):
    """The commit a worktree's branch is at: for a run's worktree just made, the base's tip it began from."""
    return git(path, "rev-parse", "HEAD").stdout.strip()


# A run id names the Windows worktree folder, which with a repository's deepest file must stay
# under Windows' path limit; `create` checks that per repository. 16 characters of words and 8
# random ones keep the id at 25: readable, and a collision is a refused start that draws again.
RUN_ID_WORDS = 16
# The longest file and directory paths Windows opens without long-path support.
WINDOWS_MAX_FILE = 259
WINDOWS_MAX_DIRECTORY = 247


def run_id(task):
    """A run's id, which also names its branch and worktree: the task's first words, then
    eight random characters that keep two runs of a similar task apart.

    Lowercase letters, digits and hyphens only, at most 25 characters, so it is a valid
    branch name, folder name and workflow id on either host.
    """
    words = re.findall(r"[a-z0-9]+", (task or "").encode("ascii", "ignore").decode().lower())
    name = ""
    for word in words:
        candidate = word if not name else name + "-" + word
        if len(candidate) > RUN_ID_WORDS:
            break
        name = candidate
    if not name:
        name = words[0][:RUN_ID_WORDS] if words else "run"
    return "%s-%s" % (name, uuid.uuid4().hex[:8])


def slug(text, words=6):
    found = re.findall(r"[a-z0-9]+", (text or "").encode("ascii", "ignore").decode().lower())
    return "_".join(found[:words])[:60].strip("_") or "run"


def plan_path(todo_dir, todo_name, created, task):
    """The run's plan, named by the repository's own todo convention from the run's start time."""
    stamp = datetime.datetime.fromisoformat(created)
    return os.path.join(todo_dir, stamp.strftime(todo_name).replace("{slug}", slug(task)) + ".md")


def create(repo, base, root, run_id, target, lfs_pointers=False, remote=None, pinned=None):
    """The run's worktree at `<root>/<run-id>` on branch `<run-id>`, from `base` — as `remote` holds it now,
    when the repository's base is a remote's, and as this repository's own branch otherwise.

    With `lfs_pointers`, Git LFS files stay pointers rather than copies of their content.
    A branch of that name without its worktree is adopted only while it still points at
    the base: one holding other commits belongs to something else. A Windows worktree whose
    deepest file or directory would pass Windows' path limit is refused before it exists.
    """
    path = os.path.join(root, run_id)
    for entry in worktrees(repo):
        if _same(entry["path"], path):
            if entry["branch"] != run_id:
                raise GitError("%s is a worktree of branch %r, not %r" % (path, entry["branch"], run_id))
            return path
    if os.path.exists(path):
        raise GitError("%s exists but is not a worktree of %s" % (path, repo))
    # A remote's base by its commit: the run's branch follows no upstream, and is never pushed.
    start = base_tip(repo, base, remote, pinned) if remote else base
    if target == "windows":
        _check_windows_paths(repo, start, path)
    os.makedirs(root, exist_ok=True)
    args = ["worktree", "add"]
    if branch_exists(repo, run_id):
        tip = git(repo, "rev-parse", "refs/heads/" + run_id).stdout.strip()
        if tip != git(repo, "rev-parse", start).stdout.strip():
            raise GitError("branch %s exists without its worktree and does not point at %s: it is "
                           "not this run's, and nothing is created" % (run_id, base))
        args += [path, run_id]
    else:
        args += (["--no-track"] if remote else []) + ["-b", run_id, path, start]
    git(repo, *args, env=dict(os.environ, GIT_LFS_SKIP_SMUDGE="1") if lfs_pointers else None)
    return path


def _check_windows_paths(repo, base, path):
    names = [name for name in git(repo, "ls-tree", "-r", "-z", "--name-only", base).stdout.split("\0") if name]
    if not names:
        return
    deepest = max(names, key=len)
    longest_file = len(path) + 1 + len(deepest)
    folders = [os.path.dirname(name) for name in names if "/" in name]
    longest_folder = len(path) + 1 + max(map(len, folders)) if folders else len(path)
    if longest_file > WINDOWS_MAX_FILE or longest_folder > WINDOWS_MAX_DIRECTORY:
        raise GitError("the worktree %s would hold a path of %d characters (a file) or %d (a folder), past "
                       "Windows' limits of %d and %d; its deepest file is %s. Nothing was created: shorten "
                       "the repository's worktree root or the task's first words"
                       % (path, longest_file, longest_folder, WINDOWS_MAX_FILE, WINDOWS_MAX_DIRECTORY, deepest))


def guard(path, run_id):
    """A digest of what only the controller may change: HEAD, the run's branch and what is staged.

    The staged content, not the index file: `git status` rewrites that file when it
    refreshes stat data, and an agent may run it.
    """
    parts = [git(path, "rev-parse", "HEAD").stdout,
             git(path, "rev-parse", "--verify", "--quiet", "refs/heads/" + run_id, check=False).stdout,
             git(path, "rev-parse", "--verify", "--quiet", "MERGE_HEAD", check=False).stdout,
             git(path, "ls-files", "--stage").stdout]
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def work_tree(path):
    """The tree `git add -A` would commit, computed on a private copy of the index."""
    index = git(path, "rev-parse", "--path-format=absolute", "--git-path", "index").stdout.strip()
    with tempfile.TemporaryDirectory(prefix="orchestra-index-") as private:
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(private, "index"))
        if os.path.exists(index):
            # With the time it was written: git takes an entry no older than its index for one whose stat
            # cannot be trusted, and compares its content. A copy stamped now would trust the stat of a file
            # rewritten to the same size in the second the index was written, and leave that edit out of
            # the tree (measured).
            shutil.copy2(index, env["GIT_INDEX_FILE"])
        git(path, "add", "-A", env=env)
        return git(path, "write-tree", env=env).stdout.strip()


def changed(path, base, tree, folders=(), patterns=()):
    """What differs from the tree `base` to `tree`, each as `(status, path)`: `A` a file added, `D` one
    removed, `M` or `T` one changed — a move its removal and its addition, each path as git names it.

    Left out: every path under one of `folders`, each taken literally, and every path one of `patterns`
    matches as git globs it — `docs/` that folder, `**/README.md` that file wherever it is. The matching
    is git's own, so what is left is what git itself says lies outside them.
    """
    but = [":(exclude,literal)" + folder.replace("\\", "/").strip("/") for folder in folders if folder]
    but += [":(exclude,glob)" + pattern for pattern in patterns]
    tokens = git(path, "diff", "--no-renames", "--name-status", "-z", base, tree,
                 *(["--"] + but if but else [])).stdout.split("\0")
    return list(zip(tokens[0::2], tokens[1::2]))


def holds(path, tree, names):
    """Which of `names` — each a file's path as git names it, never a pattern — the tree holds."""
    found = git(path, "ls-tree", "-r", "-z", "--name-only", tree, "--", *names,
                env=dict(os.environ, GIT_LITERAL_PATHSPECS="1")).stdout.split("\0")
    return [name for name in names if name in found]


def reopen(worktree, final_tree, verified_tree):
    """Take a worktree offered for its merge back to what the architect verified: each path changed from
    `verified_tree` to `final_tree` is again as it was verified, so the run's todo is where its roles are
    asked to read it. Returns the paths left alone because they changed again after `final_tree` — a later
    hand's work, or a base merged in — which the next review judges.

    Files are written and removed, as they were made; nothing is staged, and a merge under way stays under
    way. Every file is read from git before any is touched, so a tree git cannot read changes nothing — and
    run again it finds its own work done.
    """
    now = work_tree(worktree)
    since = {name for _, name in changed(worktree, final_tree, now)}
    apart = {name for _, name in changed(worktree, verified_tree, now)}
    kept, restored, removed = [], [], []
    for status, name in changed(worktree, verified_tree, final_tree):
        target = os.path.join(worktree, *name.split("/"))
        if name in since:
            if name in apart:
                kept.append(name)
        elif status == "A":
            removed.append(target)
        else:
            # Bytes, as the verified plan is put back after a refused commit.
            original = subprocess.run(["git", "-C", worktree, "cat-file", "blob", "%s:%s" % (verified_tree, name)],
                                      capture_output=True, timeout=60)
            if original.returncode != 0:
                raise GitError("git cat-file in %s: rc=%d %s" % (
                    worktree, original.returncode, original.stderr.decode("utf-8", "replace").strip()[:500]))
            restored.append((target, original.stdout))
    for target, content in restored:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as fh:
            fh.write(content)
    for target in removed:
        os.remove(target)
    return sorted(kept)


def reconcile(repo, worktree, base, tip, remote=None, pinned=None):
    """Bring the base into the run's worktree when it has moved past `tip`, the commit the run stands on.

    `{"moved": False}` while the base is still at that commit. Otherwise the worktree's files as they are
    are kept in a commit of the run's own branch, which never lands (`merge`), and the base is merged into
    the worktree, uncommitted, for the run's roles: `{"moved": True, "base_tip": <the base's tip>, "files":
    <those in conflict>, "tree": <what the worktree then holds>}`. A merge of that tip already under way is an
    earlier attempt's, and is adopted; one of an older tip is committed with the files, then the newer
    brought in. The base itself is never written. A base that no longer holds `tip` at all — rewound to an
    ancestor, or rewritten — is brought into nothing and refused: what that means is the operator's to say.
    """
    now = base_tip(repo, base, remote, pinned)
    held = git(worktree, "rev-parse", "--verify", "--quiet", "MERGE_HEAD", check=False).stdout.strip()
    if now == tip and held in ("", now):
        return {"moved": False}
    if git(repo, "merge-base", "--is-ancestor", tip, now, check=False).returncode != 0:
        # Git would call a rewound tip merged already, and the run would land again what the base dropped.
        raise GitError("%s no longer holds %s, the commit this run stands on: it was rewound or rewritten. "
                       "Nothing is brought into the worktree, which still holds what the base dropped. "
                       "Continue once %s holds that commit again, or stop the run — its worktree keeps the "
                       "work — and begin from the base as it is" % (base, tip[:10], base))
    if held != now:
        if held or not _clean(worktree):
            git(worktree, "add", "-A")
            # No hook judges a commit that never lands: the one that does is made by `merge`, hooks and all.
            git(worktree, "commit", "-q", "--no-verify", "-m", "As it stood when %s moved" % base)
        done = git(worktree, "merge", "--no-ff", "--no-commit", now, check=False)
        if done.returncode != 0 and not _merging(worktree):
            raise GitError("could not bring %s into %s: %s"
                           % (base, worktree, (done.stderr or done.stdout).strip()[:500]))
    return {"moved": True, "base_tip": now, "files": sorted(_unmerged(worktree)), "tree": work_tree(worktree)}


def _merging(path):
    return git(path, "rev-parse", "--verify", "--quiet", "MERGE_HEAD", check=False).returncode == 0


def _unmerged(path):
    return git(path, "diff", "--name-only", "--diff-filter=U").stdout.split()


def _clean(path):
    return not git(path, "status", "--porcelain", "--untracked-files=all").stdout.strip()


def _adopted_merge(repo, base, run_id, merge_message, remote=None):
    """A merge of *this* run already on the base branch, or None.

    Identified by the run's own tip as the merged side of a merge commit — its second
    parent — never by the message: two runs can carry the same subject, and a wrong
    match would clean up a run whose work the base does not hold. The first parent is
    the base's own history, which a run that has committed nothing yet still points at,
    so only the second identifies the work. Once the run's branch is gone there is no
    tip to match and nothing left whose removal could lose work, so the message
    identifies the commit to report.
    """
    tip = git(repo, "rev-parse", "--verify", "--quiet", "refs/heads/" + run_id,
              check=False).stdout.strip()
    log = git(repo, "log", "--first-parent", "-n", "500", "--format=%H %P%x09%s", _ref(base, remote))
    for line in log.stdout.splitlines():
        shas, _, subject = line.partition("\t")
        parts = shas.split()
        commit, parents = parts[0], parts[1:]
        if len(parents) < 2:
            continue                                  # only a merge commit can hold a run's work
        if tip:
            if parents[1] == tip:
                return commit
        elif subject == merge_message:
            return commit
    return None


def _finish_plan(worktree, plan, done_dir):
    """Move the run's plan to the repository's done folder, with a finished status line.

    A repository with no done folder deletes a finished task, so its plan is removed.
    """
    source = os.path.join(worktree, plan)
    if not os.path.isfile(source):
        return
    if not done_dir:
        os.remove(source)
        return
    target = os.path.join(worktree, done_dir, os.path.basename(plan))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(source, encoding="utf-8") as fh:
        text = fh.read()
    text = re.sub(r"^\*\*Status:\*\*.*$", "**Status:** PASS (implementation) %s"
                  % datetime.date.today().isoformat(), text, count=1, flags=re.M)
    with open(target, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.remove(source)


def _unfinish_plan(worktree, verified_tree, plan, done_dir):
    """Undo an attempt that finished the plan and staged the change but did not commit.

    A commit refused — by a hook, a missing identity, the worker's death — leaves the plan
    moved and everything staged, which no longer matches the verified tree. The plan as it
    was verified is in that tree, so it is put back and the index returns to HEAD's; the
    change itself stays in the files.
    """
    source = os.path.join(worktree, plan)
    if os.path.exists(source):
        return
    # Bytes, so the plan returns exactly as verified, line endings included.
    original = subprocess.run(["git", "-C", worktree, "cat-file", "blob",
                               "%s:%s" % (verified_tree, plan.replace(os.sep, "/"))], capture_output=True, timeout=60)
    if original.returncode != 0:
        return
    if done_dir:
        finished = os.path.join(worktree, done_dir, os.path.basename(plan))
        if os.path.isfile(finished):
            os.remove(finished)
    os.makedirs(os.path.dirname(source), exist_ok=True)
    with open(source, "wb") as fh:
        fh.write(original.stdout)
    git(worktree, "reset", "-q")


def merge(repo, worktree, run_id, base, verified_tree, plan, done_dir, message, merge_message, tip=None,
          remote=None, pinned=None, gate=None):
    """Land the run's change on the base: the local branch, or `remote`'s where the base is a remote's.

    `verified_tree` is the tree the run holds for its merge, and the worktree must still be it. A run
    that stands on a recorded base `tip` hands its final tree and no `plan`: that tree lands as it is while
    the base is still at that tip, and merged by git onto a base that moved on since (`_land`). A run
    started before a flow made its build final hands the tree the architect verified and its `plan`, which
    is finished here — moved to `done_dir`, or deleted where the repository has none — and is merged into
    the local base as git merges it.

    Returns `{"result": "merged", "commit": ...}` once the base holds the merge and the worktree, branch
    and environment are gone, with `"onto"`, the commit it was merged onto, where the base had moved on
    from `tip`; `{"result": "moved"}`, nothing merged, when git cannot merge the change onto the base as it
    is — a conflict, or a base that no longer holds `tip`; or, for a run that recorded none,
    `{"result": "conflict", "files": [...]}` with the base brought into the run's worktree for its agents
    to resolve.
    Raises MergeRefused, merging nothing, when a guard or git refuses.
    """
    landing = bool(tip) and not plan
    remote = remote if landing else None
    now = base_tip(repo, base, remote, pinned) if landing else None
    merged = _adopted_merge(repo, base, run_id, merge_message, remote)
    if merged:
        cleanup(repo, worktree, run_id, base, remote)
        return _merged(repo, merged, tip if landing else None)
    if not branch_exists(repo, run_id) or not os.path.isdir(worktree):
        raise MergeRefused("the run's branch or worktree is gone and %s holds no merge of it" % base)
    if landing:
        return _land(repo, worktree, run_id, base, verified_tree, message, merge_message, tip, now, remote,
                     pinned, gate)
    merging = _merging(worktree)
    if not merging and verified_tree and not _clean(worktree):
        # Only while the work is uncommitted: a written work commit is merged, never undone. An attempt
        # whose commit was refused left the change staged, and a finished plan moved.
        if plan:
            _unfinish_plan(worktree, verified_tree, plan, done_dir)
        else:
            git(worktree, "reset", "-q")
    if merging or not _clean(worktree):
        # Only the tree the run holds for its merge is committed.
        if work_tree(worktree) != verified_tree:
            raise MergeRefused("the worktree no longer matches the change the architect verified" if plan else
                               "the worktree is no longer the change that was offered for this merge")
        if merging:
            git(worktree, "add", "-A")
            git(worktree, "commit", "--no-edit", "-m", "Merge %s into %s" % (base, run_id))
        else:
            if plan:
                _finish_plan(worktree, plan, done_dir)
            git(worktree, "add", "-A")
            git(worktree, "commit", "-m", message)
    if git(repo, "rev-list", "--count", "refs/heads/%s..refs/heads/%s" % (base, run_id)).stdout.strip() == "0":
        raise MergeRefused("the run branch holds no change that %s lacks" % base)

    run_tip = git(repo, "rev-parse", "refs/heads/" + run_id).stdout.strip()
    checkout = next((entry["path"] for entry in worktrees(repo) if entry["branch"] == base), None)
    if checkout:
        # The base is checked out, so it is merged there and its files stay in step.
        if git(checkout, "diff", "--cached", "--quiet", check=False).returncode != 0:
            raise MergeRefused("%s has staged changes on %s, which are the operator's" % (checkout, base))
        done = git(checkout, "merge", "--no-ff", "-m", merge_message, run_tip, check=False)
        if done.returncode != 0:
            if _merging(checkout):
                files = _unmerged(checkout)
                git(checkout, "merge", "--abort")
                return _hand_back(worktree, base, files)
            raise MergeRefused("git refused the merge into %s: %s"
                               % (base, (done.stderr or done.stdout).strip()[:500]))
        commit = git(checkout, "rev-parse", "HEAD").stdout.strip()
    else:
        base_head = git(repo, "rev-parse", "refs/heads/" + base).stdout.strip()
        done = git(repo, "merge-tree", "--write-tree", "--name-only", "--no-messages",
                   base_head, run_tip, check=False)
        lines = done.stdout.splitlines()
        if done.returncode == 1:
            return _hand_back(worktree, base, lines[1:])
        if done.returncode != 0 or not lines:
            raise GitError("git merge-tree rc=%d %s" % (done.returncode, done.stderr.strip()[:500]))
        commit = git(repo, "commit-tree", lines[0], "-p", base_head, "-p", run_tip,
                     "-m", merge_message).stdout.strip()
        git(repo, "update-ref", "-m", merge_message, "refs/heads/" + base, commit, base_head)
    cleanup(repo, worktree, run_id, base)
    return {"result": "merged", "commit": commit}


def _tree(path, commit):
    return git(path, "rev-parse", "--verify", commit + "^{tree}").stdout.strip()


def _passed_by(repo, hook):
    """The file of the repository's `hook` where git would pass it by: it is there, and not executable.

    Git says so in a hint and goes on, and on a drive mounted without file modes no file is executable —
    so a check the repository's pushes must pass would be skipped with nobody told. A hook stated in git's
    configuration (`hook.<name>.command`) is no file, and runs wherever the repository is."""
    path = os.path.join(repo, git(repo, "rev-parse", "--git-path", "hooks/" + hook).stdout.strip())
    return path if os.path.isfile(path) and not os.access(path, os.X_OK) else None


def _merged_onto(repo, tip, now, final_tree):
    """The tree the run's change makes on the base as it is: `final_tree` itself while the base is still at
    `tip`, the commit the change was judged on; what git merges the two into where the base moved on from
    it. None where git finds a conflict — and where the base no longer holds `tip`, rewound or rewritten,
    which git would call merged already."""
    if now == tip:
        return final_tree
    if git(repo, "merge-base", "--is-ancestor", tip, now, check=False).returncode != 0:
        return None
    # Git merges commits: the change as one no ref holds, so a look that finds a conflict has written
    # nothing of the run's.
    change = git(repo, "commit-tree", final_tree, "-p", tip, "-m", "the change, as it would land").stdout.strip()
    done = git(repo, "merge-tree", "--write-tree", "--name-only", "--no-messages", now, change, check=False)
    lines = done.stdout.splitlines()
    if done.returncode == 1:
        return None
    if done.returncode != 0 or not lines:
        raise GitError("git merge-tree rc=%d %s" % (done.returncode, done.stderr.strip()[:500]))
    return lines[0]


def _merged(repo, commit, tip=None):
    """What a landing answers: its merge commit — and, where the base had moved on from `tip`, the commit the
    change was judged on, the commit it was merged onto."""
    result = {"result": "merged", "commit": commit}
    if tip:
        onto = git(repo, "rev-parse", "--verify", commit + "^1").stdout.strip()
        if onto != tip:
            result["onto"] = onto
    return result


def _land(repo, worktree, run_id, base, final_tree, message, merge_message, tip, now, remote, pinned=None,
          gate=None):
    """Land the change — `final_tree` on `tip`, the commit the run was judged on — on the base as it is.

    The change is one commit on that tip, made in the worktree so the repository's own commit hooks judge
    it; then the merge commit named for the run, its first parent the base's own tip, so the base's history
    stays its first-parent line and nothing the worktree's branch held before — the files kept as the base
    came in (`reconcile`) — is reachable from it. While the base is still at `tip` that commit's tree is the
    final tree exactly. Where the base moved on since, it is what git merges the two into (`_merged_onto`):
    the same change on the base as it is, and no role's turn for a merge git makes by itself. Where git finds
    a conflict, or the base no longer holds `tip`, nothing is committed and the base takes nothing: `moved`,
    for the run's roles to meet it in the worktree (`reconcile`) — the controller resolves nothing.

    The base takes the merge commit only while it is exactly at the commit that merge was made onto, and so
    only as a fast-forward: a remote by a push leased on that commit; a branch checked out nowhere by a
    compare-and-swap of its ref; a checked-out branch by `--ff-only`, which keeps its files in step and
    refuses to write over the operator's own edits, asked only once the branch is seen to be at that commit
    still — the one of the three that is a look and then a step, not a compare-and-swap. One that moved
    under that is refused in words, and the next Merge takes it from where it is then.

    The push runs the repository's own pre-push hook, which is handed that merge commit and may refuse it;
    a hook whose file git would pass by unrun (`_passed_by`) refuses the landing before anything is committed,
    and what git runs before a push must still be what it was when the run began (`gate`, its `prepush_id`
    then), read again as the last thing before the push.
    """
    tree = _merged_onto(repo, tip, now, final_tree)
    if tree is None:
        return {"result": "moved"}
    if tree == _tree(repo, now):
        raise MergeRefused("the run holds no change that %s lacks" % base)
    skipped = _passed_by(repo, "pre-push") if remote else None
    if skipped:
        raise MergeRefused("the repository's pre-push hook is not executable here, and git would push past it "
                           "unrun: %s. Make it executable; or, where the drive keeps no file modes, state it in "
                           "git's configuration (hook.<name>.command, git 2.54 and later); or remove it" % skipped)
    head = git(repo, "rev-parse", "refs/heads/" + run_id).stdout.strip()
    parents = git(repo, "rev-list", "--parents", "-n", "1", head).stdout.split()[1:]
    if not (parents == [tip] and _tree(repo, head) == final_tree and _clean(worktree)):
        # Not yet committed — or an attempt's commit was refused, its change left staged on the tip.
        if work_tree(worktree) != final_tree:
            raise MergeRefused("the worktree is no longer the change that was offered for this merge")
        git(worktree, "add", "-A")
        if _merging(worktree):
            git(worktree, "merge", "--quit")
        git(worktree, "reset", "-q", "--soft", tip)
        git(worktree, "commit", "-q", "-m", message)
        head = git(worktree, "rev-parse", "HEAD").stdout.strip()
        if _tree(repo, head) != final_tree:
            raise MergeRefused("a commit hook changed what was committed: it is no longer the change "
                               "that was offered for this merge")
    commit = git(repo, "commit-tree", tree, "-p", now, "-p", head, "-m", merge_message).stdout.strip()
    if remote:
        _led(repo, remote, pinned)
        # A compare-and-swap, not a rewrite: the remote takes the commit only while its branch is exactly
        # `now` — a plain push would also land on a branch rewound to an ancestor of it — and the commit is
        # `now`'s own descendant, so the update is a fast-forward or it is nothing.
        git(repo, "merge-base", "--is-ancestor", now, commit)
        if gate and prepush_id(repo) != gate:
            raise MergeRefused("what git runs before a push from this repository is no longer what it was when "
                               "this run began: a hook stated in its configuration, or its pre-push hook's file, "
                               "changed. Nothing is pushed. Put it back as it was, or stop the run — its worktree "
                               "keeps the work — and begin from the repository as it is")
        done = git(repo, "push", "--porcelain", "--force-with-lease=refs/heads/%s:%s" % (base, now), remote,
                   "%s:refs/heads/%s" % (commit, base), check=False, env=_unattended())
        # Refused by the remote, or before it by the repository's own pre-push hook: git's words say which.
        refused = "the push to %s's %s was refused" % (remote, base)
    else:
        checkout = next((entry["path"] for entry in worktrees(repo) if entry["branch"] == base), None)
        if checkout and git(checkout, "diff", "--cached", "--quiet", check=False).returncode != 0:
            raise MergeRefused("%s has staged changes on %s, which are the operator's" % (checkout, base))
        if not checkout:
            done = git(repo, "update-ref", "-m", merge_message, "refs/heads/" + base, commit, now, check=False)
        elif base_tip(repo, base) == now:
            done = git(checkout, "merge", "--ff-only", commit, check=False)
        else:
            # `merge --ff-only` asks only that the commit descend from where the branch is, so a branch
            # taken back since the look would take what it had dropped: it is asked only while the branch
            # is still at `now`. A look and then a merge, not one step — git has no compare-and-swap for a
            # branch together with its checkout — with nothing between the two.
            done = None
        refused = "git refused the merge into %s" % base
    if done is None or done.returncode != 0:
        latest = base_tip(repo, base, remote, pinned)
        if done is not None and latest == now:
            raise MergeRefused("%s: %s" % (refused, (done.stderr or done.stdout).strip()[:500]))
        if _merged_onto(repo, tip, latest, final_tree) is None:
            return {"result": "moved"}
        # The merge made for where the base was is never put over where it is: the next Merge makes its own.
        raise MergeRefused("%s moved while this change was being landed on it, and took nothing. Merge again: "
                           "git merges the two without a conflict, and the change lands on the base as it is" % base)
    cleanup(repo, worktree, run_id, base, remote)
    return _merged(repo, commit, tip)


def _hand_back(worktree, base, files):
    """Bring the moved base into the run's worktree, conflicts and all, for the run's agents."""
    if not _merging(worktree):
        git(worktree, "merge", "--no-ff", "--no-commit", base, check=False)
    if not _merging(worktree):
        raise GitError("could not bring %s into %s to resolve the conflict" % (base, worktree))
    return {"result": "conflict", "files": sorted(set(files) | set(_unmerged(worktree)))}


def cleanup(repo, worktree, run_id, base, remote=None):
    """After a merge: the worktree, the run branch and the worktree's environment go.

    The base — `remote`'s, where it is a remote's — is proven to hold the run's work before anything is
    removed, so a run whose work it lacks keeps both its branch and its worktree.
    """
    if branch_exists(repo, run_id):
        if git(repo, "merge-base", "--is-ancestor", "refs/heads/" + run_id, _ref(base, remote),
               check=False).returncode != 0:
            raise GitError("refusing to clean up %s: it is not merged into %s" % (run_id, base))
    if any(_same(entry["path"], worktree) for entry in worktrees(repo)):
        git(repo, "worktree", "remove", worktree)
    if branch_exists(repo, run_id):
        git(repo, "branch", "-D", run_id)
    envpath.remove_environment(worktree)


def discard(repo, worktree, run_id):
    """The operator's confirmed discard: the worktree, its branch and its environment go, unmerged."""
    if any(_same(entry["path"], worktree) for entry in worktrees(repo)):
        git(repo, "worktree", "remove", "--force", worktree)
    if branch_exists(repo, run_id):
        git(repo, "branch", "-D", run_id)
    envpath.remove_environment(worktree)


# What one read of a change returns, in bytes of UTF-8. Temporal refuses any payload past its own
# error limit — measured: a 3.6 MB patch fails the read with PayloadsTooLarge [TMPRL1103] — so a
# large change is read in chunks instead of failing the review it is needed for.
PATCH_CHUNK = 512 * 1024
SUMMARY_LIMIT = 128 * 1024
# One file's diff is read whole up to this many bytes, and past it its changes alone; the list names at most
# this many files. Both stay inside one payload beside the rest of a read.
FILE_LIMIT = 512 * 1024
FILES_LIMIT = 2000
# Every diff of a change is read with these, whatever the repository or its user configured: no external
# diff or text conversion runs, rename detection is on and the text is uncoloured. Git still bounds its
# exhaustive rename search by `diff.renameLimit`, so a rename past that bound reads as a delete and an add.
DIFF = ["--no-ext-diff", "--no-textconv", "--find-renames", "--no-color"]
# Context enough for any file: its diff holds it whole.
WHOLE = "-U2147483647"
OBJECT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


class ChangeRefused(RuntimeError):
    """A read of a change naming what it cannot read: no object, one git no longer holds, a file not in it."""


def _chunk(text, offset, limit):
    """At most `limit` bytes of `text` from `offset`: the part, where it ends, and the whole size.

    Counted in bytes, as the payload limit is, and never cut inside a character: a character the
    slice would split belongs to the next part whole, so the parts join back into the text exactly.
    An offset that is not where a part ended is refused rather than answered with mangled text.
    """
    data = text.encode("utf-8")
    if offset and offset < len(data) and data[offset] & 0xC0 == 0x80:
        raise RuntimeError("offset %d is inside a character; ask from where the last part ended" % offset)
    part = data[offset:offset + limit]
    for _ in range(4):                              # a character is at most four bytes
        try:
            return part.decode("utf-8"), offset + len(part), len(data)
        except UnicodeDecodeError:
            part = part[:-1]
    return part.decode("utf-8", "replace"), offset + len(part), len(data)


def _files(numstat, status):
    """Each file of a diff from its `--numstat -z` and `--name-status -z`: exact paths, never quoted or cut."""
    counts, tokens, at = {}, numstat.split("\0"), 0
    while at < len(tokens) and tokens[at]:
        added, removed, name = tokens[at].split("\t", 2)
        if name:
            at += 1
        else:
            name, at = tokens[at + 2], at + 3          # a rename: its old path, then its new
        counts[name] = (added, removed)
    files, tokens, at = [], status.split("\0"), 0
    while at < len(tokens) and tokens[at]:
        letter = tokens[at][0]
        if letter in "RC":
            old, name, at = tokens[at + 1], tokens[at + 2], at + 3
        else:
            old, name, at = None, tokens[at + 1], at + 2
        added, removed = counts.get(name, ("-", "-"))
        binary = added == "-"
        files.append({"path": name, "old": old, "status": letter, "added": None if binary else int(added),
                      "removed": None if binary else int(removed), "binary": binary})
    return files


def review_diff(path, offset=0, base=None, tree=None, file=None, files_from=None):
    """A run's change as a human reviews it: one snapshot, named by its base and its tree, and read from them.

    Without `tree`, the change now: the worktree's HEAD and the tree `git add -A` would commit, made on a
    private copy of the index (`work_tree`), so reading a change for review changes nothing anyone staged, and
    a new file arrives with its contents. The change now is read against the commit the caller names — the
    base's tip a run stands on (`against` "tip"); else, while the base is merged into the worktree and not yet
    committed, against that base ("merged"), since HEAD then holds the run's files already and only the
    base's own commits would show; else against HEAD ("commit"). With `tree`,
    the change from `base` — the worktree's HEAD when not
    given — to that tree: a snapshot read before, or the trees two reviews judged. Either is read with `DIFF`,
    so every read of one snapshot is the same bytes whatever the live worktree does meanwhile.

    Returns the base, the tree, each changed file with its exact path (`FILES_LIMIT` of them, `files_total` in
    all) and the diff's stat, and `PATCH_CHUNK` bytes of the patch from `offset` with its whole size, so the
    reader can ask for the rest. With `files_from`, the snapshot's files from that one on instead, again
    `FILES_LIMIT` of them. With `file`, one of the snapshot's files: its diff whole when each side is at most
    `FILE_LIMIT` bytes, its changes alone otherwise, and which.

    Raises ChangeRefused for a name that is no object, an object git no longer holds — it prunes unreferenced
    ones after a while — or a file not in the change; on any git failure, RuntimeError: a worktree that could
    not be read is not a worktree without changes.
    """
    if not path:
        raise RuntimeError("no worktree path in the run's state")

    def git(args, env=None):
        done = subprocess.run(["git", "-C", path] + args, capture_output=True,
                              env=env, timeout=60)
        if done.returncode != 0:
            raise RuntimeError("git %s: rc=%d %s" % (
                args[0], done.returncode,
                done.stderr.decode("utf-8", "replace").strip()[:300]))
        return done.stdout.decode("utf-8", "replace")

    def held(name):
        if not isinstance(name, str) or not OBJECT.match(name):
            raise ChangeRefused("%r is not an object name" % (name,))
        if subprocess.run(["git", "-C", path, "cat-file", "-e", name], capture_output=True, timeout=60).returncode:
            raise ChangeRefused("git no longer holds %s: it prunes what nothing refers to after a while" % name)
        return name

    if tree is None and base is not None:
        base, tree, against = held(base), work_tree(path), "tip"
    elif tree is None:
        against = "merged" if _merging(path) else "commit"
        base, tree = git(["rev-parse", "MERGE_HEAD" if against == "merged" else "HEAD"]).strip(), work_tree(path)
    else:
        against = None
        base = held(base) if base is not None else git(["rev-parse", "HEAD"]).strip()
        tree = held(tree)
    pair = [base, tree]

    def listed():
        return _files(git(["diff"] + DIFF + ["--numstat", "-z"] + pair),
                      git(["diff"] + DIFF + ["--name-status", "-z"] + pair))

    if file is not None:
        entry = next((each for each in listed() if each["path"] == file), None)
        if entry is None:
            raise ChangeRefused("%r is not a file of this change" % (file,))
        # Its paths are names, never patterns: `[ab].txt` is that file, not a.txt.
        literal = dict(os.environ, GIT_LITERAL_PATHSPECS="1")
        named = ["--"] + [name for name in (entry["old"], entry["path"]) if name]
        # Whole only when each side is small, decided before any diff runs: a large file with one changed line is
        # never diffed whole only to be thrown away. A side whose size git does not give is not read whole.
        sides = ([] if entry["status"] == "A" else ["%s:%s" % (base, entry["old"] or entry["path"])]) + (
            [] if entry["status"] == "D" else ["%s:%s" % (tree, entry["path"])])
        sizes = [subprocess.run(["git", "-C", path, "cat-file", "-s", side], capture_output=True, timeout=60)
                 for side in sides]
        whole = all(done.returncode == 0 and done.stdout.strip().isdigit() and int(done.stdout) <= FILE_LIMIT
                    for done in sizes)
        text = git(["diff"] + DIFF + [WHOLE] + pair + named, literal) if whole else None
        if text is None or len(text.encode("utf-8")) > FILE_LIMIT:
            text, whole = git(["diff"] + DIFF + ["-U3"] + pair + named, literal), False
            if len(text.encode("utf-8")) > FILE_LIMIT:
                raise ChangeRefused("%s's changes are too large to show here; copy the patch for them" % file)
        return {"base": base, "tree": tree, "file": entry, "patch": text, "whole": whole}
    if files_from is not None:
        files = listed()
        return {"base": base, "tree": tree, "files": files[files_from:files_from + FILES_LIMIT],
                "files_total": len(files), "files_from": files_from}
    read = {"base": base, "tree": tree, "against": against}
    if not offset:
        files = listed()
        summary, _, summary_total = _chunk(git(["diff"] + DIFF + ["--stat"] + pair), 0, SUMMARY_LIMIT)
        read.update(files=files[:FILES_LIMIT], files_total=len(files), summary=summary, summary_total=summary_total)
    patch, following, total = _chunk(git(["diff"] + DIFF + pair), offset, PATCH_CHUNK)
    read.update(patch=patch, offset=offset, next=following, total=total)
    return read


def view(repo, base, remote=None):
    """Every worktree git reports, and whether its work is merged into the base — `remote`'s branch as this
    repository last fetched it, where the base is a remote's, and the local branch otherwise.

    A run's work stays uncommitted until its merge, so a branch with nothing the base lacks
    is merged only when its worktree holds nothing uncommitted either.
    """
    rows = []
    for entry in worktrees(repo):
        branch = entry["branch"]
        if branch is None:
            state = "detached"
        elif branch == base:
            state = "base"
        elif git(repo, "rev-list", "--count", "%s..refs/heads/%s" % (_ref(base, remote), branch)).stdout.strip() != "0":
            state = "unmerged"
        elif os.path.isdir(entry["path"]) and not _clean(entry["path"]):
            state = "uncommitted"
        else:
            state = "merged"
        rows.append({"path": entry["path"], "branch": branch, "state": state})
    return rows
