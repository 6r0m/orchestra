"""Which repository a run targets, where its agents run, and where its worktree goes.

The one owner of a run's repository, base branch, execution target and worktree
root. A value comes from the repository's entry in `repos.json` when one is
configured and is detected otherwise; a value that is neither refuses the run before
any work.

The client selects the repository and its target, which is all it needs to route the
run. The rest is resolved on the target host, with that host's own git and paths.
"""
import json
import ntpath
import os
import re
import shutil
import subprocess

# This repository, and where a run keeps its state on this host. One definition each: a second
# one is equal only while every module sits at the root, and drifts silently the moment one moves.
# workers.sh and workers.ps1 build the same runtime path for the shell side of the lifecycle.
REPO = os.path.dirname(os.path.abspath(__file__))
RUNTIME_ROOT = os.path.join(REPO, "tmp", "orchestration")
# ORCH_REPOS names another descriptor file, as the acceptance run's throwaway repository needs.
DESCRIPTORS = os.environ.get("ORCH_REPOS") or os.path.join(REPO, "repos.json")
TARGETS = ("wsl", "windows")
ENTRY_KEYS = {"path", "target", "base_branch", "worktree_root", "todo_dir", "todo_done_dir", "todo_name",
              "lfs_pointers"}
# True keeps Git LFS files in a run's worktree as pointers instead of copying every asset
# out of the repository's LFS store, for a repository whose assets a run does not need.
FLAGS = {"lfs_pointers"}
# Where a run's plan is written, where it moves once merged, and its name: this
# repository's own convention unless the entry states the repository's.
TODO_DEFAULTS = {"todo_dir": "todo", "todo_done_dir": "todo/done", "todo_name": "%Y-%m-%d_%H%M-{slug}"}
# Keys whose null is a setting of its own: a null `todo_done_dir` means the repository deletes
# a finished task rather than moving it to a done folder.
NULLABLE = {"todo_done_dir"}
# The base branch when none is configured: the first of these the repository has,
# then the remote's default branch.
BASE_CANDIDATES = ("develop", "dev")
_DRIVE = re.compile(r"^/mnt/([a-zA-Z])(/.*)?$")
UNC_REASON = ("a Windows process given a Linux path as its working directory silently runs "
              "in C:\\Windows instead")


class Refused(ValueError):
    """The run cannot start as configured; nothing has been changed."""


def load(path=DESCRIPTORS):
    """The descriptor entries, validated strictly: an unknown key is a typo that would do nothing.

    No file at all means no descriptors, not an error: the file names the operator's own
    repositories, so a fresh checkout has none and a run then works on this repository itself.
    """
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, dict):
        raise Refused("%s must hold an object of repositories" % path)
    for name, entry in raw.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not entry["path"]:
            raise Refused("repository %r in %s needs a path" % (name, path))
        unknown = set(entry) - ENTRY_KEYS
        if unknown:
            raise Refused("repository %r: unknown keys %s" % (name, ", ".join(sorted(unknown))))
        if "target" in entry and entry["target"] not in TARGETS:
            raise Refused("repository %r: target must be one of %s" % (name, ", ".join(TARGETS)))
        for key in ENTRY_KEYS - {"path", "target"} - FLAGS:
            if key in NULLABLE and key in entry and entry[key] is None:
                continue
            if key in entry and not (isinstance(entry[key], str) and entry[key]):
                raise Refused("repository %r: %s must be a non-empty string" % (name, key))
        for key in FLAGS:
            if key in entry and not isinstance(entry[key], bool):
                raise Refused("repository %r: %s must be true or false" % (name, key))
    return raw


def windows_path(path):
    """The Windows form of a WSL path on a Windows drive; None for a Linux-only path."""
    found = _DRIVE.match(path)
    if not found:
        return None
    return "%s:%s" % (found.group(1).upper(), (found.group(2) or "/").replace("/", "\\"))


def select(repo=None, descriptors=None):
    """The run's repository as the client sees it: its id, its WSL path, its target and any overrides.

    `repo` is a descriptor name or a path; none means the orchestration's own repository.
    A repository on a Windows drive runs on Windows unless its entry says otherwise.
    """
    descriptors = load() if descriptors is None else descriptors
    if repo in descriptors:
        name, entry = repo, descriptors[repo]
    else:
        path = os.path.abspath(repo or REPO)
        matches = [(n, e) for n, e in descriptors.items() if os.path.abspath(e["path"]) == path]
        name, entry = matches[0] if matches else (os.path.basename(path), {"path": path})
    path = os.path.abspath(entry["path"])
    if not os.path.isdir(path):
        raise Refused("repository %r: %s does not exist" % (name, path))
    target = entry.get("target") or ("windows" if windows_path(path) else "wsl")
    if target == "windows" and windows_path(path) is None:
        raise Refused("repository %r at %s cannot run on Windows: %s" % (name, path, UNC_REASON))
    selected = {"id": name, "path": path, "target": target}
    selected.update({key: entry[key] for key in ENTRY_KEYS - {"path", "target"} if key in entry})
    return selected


def _git(path, *args):
    return subprocess.run(["git", "-C", path] + list(args), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)


def detect_base(path):
    for branch in BASE_CANDIDATES:
        if _git(path, "show-ref", "--verify", "--quiet", "refs/heads/" + branch).returncode == 0:
            return branch
    remote = _git(path, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    branch = remote.stdout.strip().split("/", 1)[-1] if remote.returncode == 0 else ""
    if branch and _git(path, "show-ref", "--verify", "--quiet", "refs/heads/" + branch).returncode == 0:
        return branch
    raise Refused("%s has no develop or dev branch and no local branch for the remote's default; "
                  "set base_branch in repos.json" % path)


def detect_worktree_root(path, target_root):
    """`<target root>/<the repository's category folder, matched case-insensitively>/<its name>`."""
    root = os.path.expanduser(target_root)
    if not os.path.isdir(root):
        raise Refused("the worktree root %s does not exist" % root)
    category = os.path.basename(os.path.dirname(path))
    matches = [entry for entry in os.listdir(root)
               if entry.lower() == category.lower() and os.path.isdir(os.path.join(root, entry))]
    if len(matches) != 1:
        raise Refused("%s: %d folders under %s match the category %r; set worktree_root in repos.json"
                      % (path, len(matches), root, category))
    return os.path.join(root, matches[0], os.path.basename(path))


def resolve(selected, brains, target_root, which=shutil.which):
    """Resolve the rest on the target host: its path there, the base branch and the worktree root.

    Refuses before any work when a tool, the repository or a value is missing.
    """
    target = selected["target"]
    path = selected["path"]
    if target == "windows" and not ntpath.splitdrive(path)[0]:
        path = windows_path(path)
        if path is None:
            raise Refused("%s cannot run on Windows: %s" % (selected["path"], UNC_REASON))
    for tool in ("git",) + tuple(sorted(set(brains))):
        if not which(tool):
            raise Refused("%s is not installed on the %s host" % (tool, target))
    if _git(path, "rev-parse", "--show-toplevel").returncode != 0:
        raise Refused("%s is not a git repository" % path)
    base = selected.get("base_branch")
    if base:
        if _git(path, "show-ref", "--verify", "--quiet", "refs/heads/" + base).returncode != 0:
            raise Refused("%s has no local branch %r, the configured base branch" % (path, base))
    else:
        base = detect_base(path)
    root = selected.get("worktree_root") or detect_worktree_root(path, target_root)
    if target == "windows" and not ntpath.splitdrive(root)[0]:
        raise Refused("the worktree root %s is not on a Windows drive: %s" % (root, UNC_REASON))
    resolved = {"repo_path": path, "base_branch": base, "worktree_root": root}
    resolved.update({key: selected.get(key, value) for key, value in TODO_DEFAULTS.items()})
    resolved["lfs_pointers"] = selected.get("lfs_pointers", False)
    return resolved
