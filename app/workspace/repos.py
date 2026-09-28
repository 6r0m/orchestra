"""Which repository a run targets, where its agents run, and where its worktree goes.

The one owner of a run's repository, base branch, execution target and worktree
root. A value comes from the repository's entry in the descriptor file when one is
configured and is detected otherwise; a value that is neither refuses the run before
any work.

The descriptors come from one file: the one `ORCHESTRA_REPOS` names, alone — a stack of
its own, the demo's or the acceptance run's — else this checkout's `.orchestra/repos.json`.
A `repos.json` left at the checkout's root, where it once lived, is refused rather than
read, and so is one beside the new file: the move is the operator's, made once, by hand.

The client selects the repository and its target, which is all it needs to route the
run. The rest is resolved on the target host, with that host's own git and paths.

This owns the repositories a run operates on. Where Orchestra itself is installed and
where its runs write is `app.foundation.paths`, which is a different fact: a descriptor
file happens to sit in this checkout, and the default target happens to be it.
"""
import json
import ntpath
import os
import re
import shutil
import subprocess

from app.foundation import paths

# Names a descriptor file of a stack's own, taken alone.
VARIABLE = "ORCHESTRA_REPOS"
DESCRIPTORS = os.path.join(paths.REPO, ".orchestra", "repos.json")
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
_WINDOWS_DRIVE = re.compile(r"^([a-zA-Z]):(?:[\\/](.*))?$")
UNC_REASON = ("a Windows process given a Linux path as its working directory silently runs "
              "in C:\\Windows instead")


class Refused(ValueError):
    """The run cannot start as configured; nothing has been changed."""


def descriptor_file(root=paths.REPO, environ=os.environ):
    """The one file the descriptors come from, or None when there is none.

    Decided each time descriptors are loaded, never at import: a layout it refuses fails what needs the
    descriptors — a start, the picker — with its reason, and no process's start.
    """
    named = environ.get(VARIABLE)
    if named:
        # Named on purpose: a file that is not there is a mistake, not a stack with no repositories.
        if not os.path.isfile(named):
            raise Refused("%s names %s, which does not exist" % (VARIABLE, named))
        return named
    current = os.path.join(root, ".orchestra", "repos.json")
    legacy = os.path.join(root, "repos.json")
    if os.path.exists(legacy):
        if os.path.exists(current):
            raise Refused("both %s and %s hold repositories; keep only %s" % (legacy, current, current))
        raise Refused("%s is where repositories were listed before; move it to %s" % (legacy, current))
    return current if os.path.exists(current) else None


def load(path=None):
    """The descriptor entries, validated strictly: an unknown key is a typo that would do nothing.

    No file at all means no descriptors, not an error: the file names the operator's own
    repositories, so a fresh checkout has none and a run then works on this repository itself.
    """
    path = path or descriptor_file()
    if path is None or not os.path.exists(path):
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


def wsl_path(path):
    """The WSL form of a path on a Windows drive, `windows_path` reversed; None for any other path."""
    found = _WINDOWS_DRIVE.match(path)
    if not found:
        return None
    rest = (found.group(2) or "").replace("\\", "/").strip("/")
    return "/mnt/%s" % found.group(1).lower() + ("/" + rest if rest else "")


def selector(name, path, target, descriptors=None):
    """What `select` takes to choose again the repository a run chose as `name` and resolved to `path` on
    `target`: that name while its entry in the descriptors is still that repository, else the path as WSL sees it.

    The name alone is not enough: a repository given by its path is named for its folder, a name the descriptors
    may give another repository, or none.
    """
    if not path:
        return name
    if target == "windows":
        path = wsl_path(path) or path
    try:
        descriptors = load() if descriptors is None else descriptors
    except (OSError, ValueError):
        # Descriptors that cannot be read cannot say the name is still this repository's; the path can.
        descriptors = {}
    entry = descriptors.get(name)
    return name if entry and os.path.abspath(entry["path"]) == path else path


def select(repo=None, descriptors=None):
    """The run's repository as the client sees it: its id, its WSL path, its target and any overrides.

    `repo` is a descriptor name or a path; none means the orchestration's own repository.
    A repository on a Windows drive runs on Windows unless its entry says otherwise.
    """
    descriptors = load() if descriptors is None else descriptors
    if repo in descriptors:
        name, entry = repo, descriptors[repo]
    else:
        path = os.path.abspath(repo or paths.REPO)
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
                  "set base_branch in .orchestra/repos.json" % path)


def detect_worktree_root(path, target_root):
    """`<target root>/<the repository's category folder, matched case-insensitively>/<its name>`."""
    root = os.path.expanduser(target_root)
    if not os.path.isdir(root):
        raise Refused("the worktree root %s does not exist" % root)
    category = os.path.basename(os.path.dirname(path))
    matches = [entry for entry in os.listdir(root)
               if entry.lower() == category.lower() and os.path.isdir(os.path.join(root, entry))]
    if len(matches) != 1:
        raise Refused("%s: %d folders under %s match the category %r; set worktree_root in .orchestra/repos.json"
                      % (path, len(matches), root, category))
    return os.path.join(root, matches[0], os.path.basename(path))


def resolve(selected, target_root, which=shutil.which):
    """Resolve the rest on the target host: its path there, the base branch and the worktree root.

    Refuses before any work when git, the repository or a value is missing. Whether the run's agents can
    run on this host is not a repository's fact, and the run's preparation asks it first.
    """
    target = selected["target"]
    path = selected["path"]
    if target == "windows" and not ntpath.splitdrive(path)[0]:
        path = windows_path(path)
        if path is None:
            raise Refused("%s cannot run on Windows: %s" % (selected["path"], UNC_REASON))
    if not which("git"):
        raise Refused("git is not installed on the %s host" % target)
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
