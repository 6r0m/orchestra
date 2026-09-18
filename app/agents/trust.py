"""Tell this host's agent CLIs that a run's repository is one the operator works in.

Both vendor CLIs stop at a trust dialog the first time they start in a repository they have no
record of, and a stopped turn waits until someone answers it in the page — for an unattended run,
until its timeout. The dialog asks exactly what the operator answered by starting a run on that
repository: a `repos.json` entry, or a path they typed into the workbench. So a run records that
answer for the brains it will use, on the host it will use, before any agent starts.

The record is per repository, not per run: both CLIs resolve a run's worktree to the repository it
belongs to, so one record covers every later run of that repository on that host (measured on both
CLIs and both hosts; see the todo's review record).

Writing is best effort and never fails a run. A record that could not be written leaves the dialog
exactly as it was, and the operator answers it once in the page.

  Claude  `~/.claude.json`         projects["<repo>"].hasTrustDialogAccepted = true
  Codex   `~/.codex/config.toml`   [projects.'<repo>'] trust_level = "trusted"

Neither file is ours, so nothing else in either is touched: Claude's is read, changed in memory and
replaced atomically, and Codex's is only ever appended to — never with a key it already holds, since
two tables of one key are not valid TOML and would break the CLI that reads them. An explicit
`trust_level = "untrusted"` is the operator's own decision and is left alone.

Both CLIs rewrite their own file when they exit, from the copy they read at startup, so a record
written while one of them is running is taken back when it exits — measured, not feared. A run
therefore records again before every turn rather than once at its start: a lost record costs a
stopped turn, and recording again costs one small read.

`forget` undoes exactly what `ensure` wrote, for probes and acceptance that create a repository and
then remove it. It leaves anything it does not recognise as its own.
"""
import json
import os
import re
import tempfile

CLAUDE_FILE = ".claude.json"
CODEX_FILE = os.path.join(".codex", "config.toml")
WINDOWS = os.name == "nt"
TRUSTED = 'trust_level = "trusted"'
# Where a table begins: a header at the start of a line. Only removal uses this; what the
# config already holds is read by the TOML parser itself.
_HEADER = re.compile(r"^\[[^\n\]]*\]", re.M)
_UNPARSED = object()


def claude_path(home=None):
    """Claude Code's config file on this host, under `CLAUDE_CONFIG_DIR` when that names its home.

    Measured, not assumed: started with an empty directory named by that variable, the CLI created
    `.claude.json` inside it, beside its own `sessions/` and `cache/`.
    """
    if home:
        return os.path.join(home, CLAUDE_FILE)
    return os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~"), CLAUDE_FILE)


def codex_path(home=None):
    """Codex's config file on this host. `CODEX_HOME` names the root that holds it."""
    if home:
        return os.path.join(home, CODEX_FILE)
    named = os.environ.get("CODEX_HOME")
    if named:
        return os.path.join(named, "config.toml")
    return os.path.join(os.path.expanduser("~"), CODEX_FILE)


def ensure(repo_path, brains, home=None):
    """Record `repo_path` as trusted for each brain's CLI on this host; returns those recorded now.

    The returned list is the receipt `forget` takes back: it names what this call actually wrote.
    """
    return _each(repo_path, brains, home, {"claude": _claude_ensure, "codex": _codex_ensure},
                 present=True)


def forget(repo_path, brains, home=None):
    """Remove the records `ensure` wrote for exactly this repository; returns those removed.

    Exact: the repository's own key, never one that merely starts with it, and for Codex only a
    table that is still exactly the line we wrote — an `untrusted` decision, or any other shape, is
    left as it is. Claude's entry loses the trust flag and nothing else: what the CLI itself wrote
    there is not ours to remove, so the entry goes only when the flag was all it held.
    """
    return _each(repo_path, brains, home, {"claude": _claude_forget, "codex": _codex_forget})


def _each(repo_path, brains, home, writers, present=False):
    repo = os.path.normpath(repo_path)
    # Nothing is recorded for a repository that is not on this host: a path from a test's fake, or a
    # descriptor pointing elsewhere, would otherwise leave a row in the operator's own config.
    # Forgetting asks for no such proof — a probe removes its records after removing its repository.
    if present and not os.path.isdir(repo):
        return []
    done = []
    for brain in sorted(set(brains or ())):
        writer = writers.get(brain)
        if writer is None:
            continue
        try:
            if writer(repo, home):
                done.append(brain)
        except Exception:                           # noqa: BLE001 - a dialog is the cost of failing here
            continue
    return done


# ---- Claude -------------------------------------------------------------------------------

def claude_key(repo):
    """The spelling Claude Code looks a repository up by on this host.

    Measured on Windows: an entry spelled with backslashes is not the one it reads, and the same
    path spelled with forward slashes is.
    """
    return repo.replace("\\", "/") if WINDOWS else repo


def _claude_config(home):
    path = claude_path(home)
    try:
        with open(path, encoding="utf-8") as fh:
            config = json.load(fh)
    except FileNotFoundError:
        return path, {}
    except ValueError:
        return path, None                           # not the shape we know; leave it alone
    return path, config if isinstance(config, dict) else None


def _claude_ensure(repo, home):
    path, config = _claude_config(home)
    if config is None:
        return False
    projects = config.setdefault("projects", {})
    entry = projects.get(claude_key(repo))
    if isinstance(entry, dict) and entry.get("hasTrustDialogAccepted"):
        return False
    projects[claude_key(repo)] = dict(entry or {}, hasTrustDialogAccepted=True)
    _replace(path, json.dumps(config, indent=2))
    return True


def _claude_forget(repo, home):
    path, config = _claude_config(home)
    if config is None:
        return False
    projects = config.get("projects") or {}
    entry = projects.get(claude_key(repo))
    if not isinstance(entry, dict) or not entry.pop("hasTrustDialogAccepted", False):
        return False
    # What the CLI itself put in the entry is not ours to remove; an entry holding nothing else goes.
    if not any(value for value in entry.values()):
        projects.pop(claude_key(repo))
    _replace(path, json.dumps(config, indent=2))
    return True


# ---- Codex --------------------------------------------------------------------------------

def codex_key(repo):
    """The repository as a TOML key: a literal string, so a Windows path keeps its backslashes."""
    return "'%s'" % repo if "'" not in repo else json.dumps(repo)


def _tables(text):
    """`text` split where a table begins: what precedes the first one, then each table whole.

    A table runs to the next header, so a table that follows the one we remove is never part of it.
    """
    headers = list(_HEADER.finditer(text))
    if not headers:
        return [text]
    blocks = [text[:headers[0].start()]] if headers[0].start() else []
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        blocks.append(text[header.start():end])
    return blocks


def _codex_state(text, repo):
    """What the config already says about `repo`: its `trust_level`, None when absent, or unreadable.

    Read by the TOML parser, never by matching text: the operator may write a table in any valid
    shape — a comment after the header, either kind of quoting — and a table we failed to see is a
    table we would append a second time, which is not valid TOML and would break the CLI.
    """
    try:
        import tomllib
        projects = tomllib.loads(text).get("projects") or {}
    except Exception:                               # noqa: BLE001 - unreadable: touch nothing
        return _UNPARSED
    wanted = _same(repo)
    for key, value in projects.items():
        if _same(key) == wanted:
            return (value or {}).get("trust_level") or ""
    return None


def _codex_ensure(repo, home):
    path = codex_path(home)
    text = _read(path)
    if _codex_state(text, repo) is not None:
        # Already there — trusted, untrusted, or a shape we do not own. Never a second table.
        return False
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    # Appended, never rewritten: the file is the operator's, with their own comments and order.
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write("\n[projects.%s]\n%s\n" % (codex_key(repo), TRUSTED))
    return True


def _codex_forget(repo, home):
    path = codex_path(home)
    text = _read(path)
    if _codex_state(text, repo) != "trusted":
        return False
    header = "[projects.%s]" % codex_key(repo)
    kept, removed = [], False
    for block in _tables(text):
        lines = block.splitlines()
        ours = lines and lines[0].strip() == header and [line.strip() for line in lines[1:] if line.strip()] == [TRUSTED]
        if ours:
            removed = True
            continue
        kept.append(block)
    if not removed:
        return False                                # trusted, but not in the shape we wrote it
    _replace(path, "".join(kept))
    return True


# ---- shared -------------------------------------------------------------------------------

def _same(path):
    """One spelling of a path for comparison: separators folded, and case too where the host folds it."""
    folded = path.replace("\\", "/").rstrip("/")
    return folded.casefold() if WINDOWS else folded


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return ""


def _replace(path, text):
    """Write `text` as `path` in one step, so a reader never sees a half-written file."""
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=folder, prefix=".trust-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.remove(temporary)
        except OSError:
            pass
        raise
