"""A run's worktree, through the target host's own git: create, guard, merge, discard, list.

Only this module stages, commits or merges, and only for the run it is given.
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


def create(repo, base, root, run_id, target, lfs_pointers=False):
    """The run's worktree at `<root>/<run-id>` on branch `<run-id>`, from `base`.

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
    if target == "windows":
        _check_windows_paths(repo, base, path)
    os.makedirs(root, exist_ok=True)
    args = ["worktree", "add"]
    if branch_exists(repo, run_id):
        tip = git(repo, "rev-parse", "refs/heads/" + run_id).stdout.strip()
        if tip != git(repo, "rev-parse", base).stdout.strip():
            raise GitError("branch %s exists without its worktree and does not point at %s: it is "
                           "not this run's, and nothing is created" % (run_id, base))
        args += [path, run_id]
    else:
        args += ["-b", run_id, path, base]
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
    with tempfile.TemporaryDirectory(prefix="orch-index-") as private:
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(private, "index"))
        if os.path.exists(index):
            shutil.copyfile(index, env["GIT_INDEX_FILE"])
        git(path, "add", "-A", env=env)
        return git(path, "write-tree", env=env).stdout.strip()


def _merging(path):
    return git(path, "rev-parse", "--verify", "--quiet", "MERGE_HEAD", check=False).returncode == 0


def _unmerged(path):
    return git(path, "diff", "--name-only", "--diff-filter=U").stdout.split()


def _clean(path):
    return not git(path, "status", "--porcelain", "--untracked-files=all").stdout.strip()


def _adopted_merge(repo, base, run_id, merge_message):
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
    log = git(repo, "log", "--first-parent", "-n", "500", "--format=%H %P%x09%s", "refs/heads/" + base)
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


def merge(repo, worktree, run_id, base, verified_tree, plan, done_dir, message, merge_message):
    """Commit the verified change on the run branch and merge it into the local base branch.

    Returns `{"result": "merged", "commit": ...}` once the base holds the merge and the
    worktree, branch and environment are gone, or `{"result": "conflict", "files": [...]}`
    with the base brought into the run's worktree for its agents to resolve.
    Raises MergeRefused, merging nothing, when a guard or git refuses.
    """
    merged = _adopted_merge(repo, base, run_id, merge_message)
    if merged:
        cleanup(repo, worktree, run_id, base)
        return {"result": "merged", "commit": merged}
    if not branch_exists(repo, run_id) or not os.path.isdir(worktree):
        raise MergeRefused("the run's branch or worktree is gone and %s holds no merge of it" % base)
    merging = _merging(worktree)
    if not merging and verified_tree and not _clean(worktree):
        # Only while the work is uncommitted: a written work commit is merged, never undone.
        _unfinish_plan(worktree, verified_tree, plan, done_dir)
    if merging or not _clean(worktree):
        # Only the change the architect verified is committed.
        if work_tree(worktree) != verified_tree:
            raise MergeRefused("the worktree no longer matches the change the architect verified")
        if merging:
            git(worktree, "add", "-A")
            git(worktree, "commit", "--no-edit", "-m", "Merge %s into %s" % (base, run_id))
        else:
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
        base_tip = git(repo, "rev-parse", "refs/heads/" + base).stdout.strip()
        done = git(repo, "merge-tree", "--write-tree", "--name-only", "--no-messages",
                   base_tip, run_tip, check=False)
        lines = done.stdout.splitlines()
        if done.returncode == 1:
            return _hand_back(worktree, base, lines[1:])
        if done.returncode != 0 or not lines:
            raise GitError("git merge-tree rc=%d %s" % (done.returncode, done.stderr.strip()[:500]))
        commit = git(repo, "commit-tree", lines[0], "-p", base_tip, "-p", run_tip,
                     "-m", merge_message).stdout.strip()
        git(repo, "update-ref", "-m", merge_message, "refs/heads/" + base, commit, base_tip)
    cleanup(repo, worktree, run_id, base)
    return {"result": "merged", "commit": commit}


def _hand_back(worktree, base, files):
    """Bring the moved base into the run's worktree, conflicts and all, for the run's agents."""
    if not _merging(worktree):
        git(worktree, "merge", "--no-ff", "--no-commit", base, check=False)
    if not _merging(worktree):
        raise GitError("could not bring %s into %s to resolve the conflict" % (base, worktree))
    return {"result": "conflict", "files": sorted(set(files) | set(_unmerged(worktree)))}


def cleanup(repo, worktree, run_id, base):
    """After a merge: the worktree, the run branch and the worktree's environment go.

    The base is proven to hold the run's work before anything is removed, so a run
    whose work it lacks keeps both its branch and its worktree.
    """
    if branch_exists(repo, run_id):
        if git(repo, "merge-base", "--is-ancestor", "refs/heads/" + run_id, "refs/heads/" + base,
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


def review_diff(path, offset=0):
    """The change a human reviews, exactly as `gdiff -s` copies it.

    `gdiff -s` stages everything the work tree holds (`git add -A`, gitignored
    paths excluded) and copies `git diff --no-ext-diff --no-textconv --cached`,
    so a new file arrives with its contents rather than as a name. The same
    commands run here against a private copy of the index, because reading a
    change for review must not change what anyone has staged. Returns the
    worktree's HEAD, the diff's stat, and `PATCH_CHUNK` bytes of the patch from
    `offset` with the patch's whole size, so the reader can ask for the rest.

    Raises on any git failure: a worktree that could not be read is not a
    worktree without changes.
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

    base = git(["rev-parse", "--short", "HEAD"]).strip()
    index = git(["rev-parse", "--path-format=absolute", "--git-path", "index"]).strip()
    with tempfile.TemporaryDirectory(prefix="review-index-") as private:
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(private, "index"))
        # Starting from the real index, not from HEAD, keeps anything already
        # staged exactly as `git add -A` on top of it would see it.
        if os.path.exists(index):
            shutil.copyfile(index, env["GIT_INDEX_FILE"])
        git(["add", "-A"], env)
        diff = ["diff", "--no-ext-diff", "--no-textconv", "--cached"]
        summary, _, summary_total = _chunk(git(diff + ["--stat"], env), 0, SUMMARY_LIMIT)
        whole = git(diff, env)
        patch, following, total = _chunk(whole, offset, PATCH_CHUNK)
        return {"base": base, "summary": summary, "summary_total": summary_total,
                "patch": patch, "offset": offset, "next": following, "total": total,
                # Which change this part belongs to: the parts of one review must be one change, and a
                # worktree whose terminals stay live can be edited between two reads of the same size.
                "snapshot": hashlib.sha256(whole.encode("utf-8")).hexdigest()[:32]}


def view(repo, base):
    """Every worktree git reports, and whether its work is merged into the local base branch.

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
        elif git(repo, "rev-list", "--count", "refs/heads/%s..refs/heads/%s" % (base, branch)).stdout.strip() != "0":
            state = "unmerged"
        elif os.path.isdir(entry["path"]) and not _clean(entry["path"]):
            state = "uncommitted"
        else:
            state = "merged"
        rows.append({"path": entry["path"], "branch": branch, "state": state})
    return rows
