"""Files the kinds write that are not theirs — a CLI's own configuration — read and replaced safely.

Private to the adapters, and no kind: `available()` skips a module whose name starts with `_`.
"""
import os
import sys
import tempfile

WINDOWS = sys.platform.startswith("win")


def read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return ""


def replace(path, text):
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


def same(path):
    """One spelling of a path for comparison: separators folded, and case too where the host folds it."""
    folded = path.replace("\\", "/").rstrip("/")
    return folded.casefold() if WINDOWS else folded


def private_file(private, name, content):
    """Write `content` as `name` in the turn's private folder, only this user able to read it, and return its
    path. One that cannot be written whole is removed before the failure is raised: it may already hold a
    secret."""
    path = private.path(name)
    try:
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as fh:
            fh.write(content)
    except BaseException:
        try:
            os.remove(path)
        except OSError:
            pass
        raise
    return path
