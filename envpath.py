"""Where a checkout's orchestration environment lives on this host, and its removal.

The Linux and Windows hosts share one checkout on a Windows drive, so uv's default
`.venv` inside it would be written by both, and a Linux environment on that drive
pays its filesystem's cost for every file. Each host therefore keeps each checkout's
environment on its own disk, under one root, in a directory named by the checkout
and a short hash of its real path: a run's worktree of this repository gets its own
environment, and its tests never re-sync the one the live workers import from.

The main checkout's environment persists. A run worktree's belongs to that worktree
and is removed with it, on the host that ran it. The path to remove is derived again
from the worktree's path, never read from saved state, and removal refuses anything
that is not exactly that environment.

Standard library only: wrappers run it before any environment exists.

    python envpath.py <checkout>     print the environment path for that checkout
"""
import hashlib
import os
import shutil
import stat
import sys

ROOT_NAME = "orchestra"


class UnsafeRemoval(RuntimeError):
    """The derived path is not an environment this module may delete."""


def environment_root():
    if sys.platform.startswith("win"):
        return os.path.join(os.environ["LOCALAPPDATA"], ROOT_NAME)
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, ROOT_NAME)


def environment_for(checkout):
    real = os.path.normcase(os.path.realpath(checkout))
    digest = hashlib.sha256(real.encode("utf-8")).hexdigest()[:12]
    return os.path.join(environment_root(), "%s-%s" % (os.path.basename(real), digest))


def _is_link(path):
    """A symlink, a junction, or any other reparse point."""
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
                if hasattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT") else 0)


def remove_environment(checkout):
    """Remove `checkout`'s environment on this host. True when removed, False when absent.

    Raises UnsafeRemoval, deleting nothing, unless the path lies directly under the
    real environment root, is not itself a link, and holds `pyvenv.cfg`.
    """
    path = environment_for(checkout)
    if not os.path.lexists(path):
        return False
    root = environment_root()
    if not os.path.isdir(root):
        raise UnsafeRemoval("%s exists but the environment root %s does not" % (path, root))
    if _is_link(root) or os.path.realpath(root) != os.path.abspath(root):
        raise UnsafeRemoval("environment root %s resolves elsewhere" % root)
    if _is_link(path):
        raise UnsafeRemoval("%s is a link" % path)
    real = os.path.realpath(path)
    if os.path.dirname(real) != os.path.realpath(root):
        raise UnsafeRemoval("%s resolves outside %s" % (path, root))
    if not os.path.isfile(os.path.join(real, "pyvenv.cfg")):
        raise UnsafeRemoval("%s holds no pyvenv.cfg" % path)
    # rmtree removes links found inside without following them.
    shutil.rmtree(real)
    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: envpath.py <checkout>")
    print(environment_for(sys.argv[1]))
