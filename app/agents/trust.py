"""Tell this host's agent CLIs that a run's repository is one the operator works in.

An interactive CLI stops at a trust dialog the first time it starts in a repository it has no record of,
and a stopped turn waits until someone answers it in the page — for an unattended run, until its timeout.
The dialog asks exactly what the operator answered by starting a run on that repository: an entry in the
descriptors, or a path they typed into the workbench. So a run records that answer for the kinds it will
use, on the host it will use, before any agent starts. Where each kind keeps its record, and how it is
written, is that kind's own (`app.agents.adapters`).

The record is per repository, not per run: a CLI resolves a run's worktree to the repository it belongs
to, so one record covers every later run of that repository on that host — measured on both of today's
CLIs and both hosts, and checked on the installed CLIs by `tools/trust_probe.py` after either vendor is
upgraded.

Writing is best effort and never fails a run. A record that could not be written leaves the dialog
exactly as it was, and the operator answers it once in the page.

A CLI may rewrite its own file when it exits, from the copy it read at startup, so a record written while
it runs is taken back when it exits — measured, not feared. A run therefore records again before every
turn rather than once at its start: a lost record costs a stopped turn, and recording again costs one
small read.

`forget` undoes exactly what `ensure` wrote, for probes and acceptance that create a repository and then
remove it. It leaves anything it does not recognise as its own.
"""
import os

from app.agents import adapters


def ensure(repo_path, kinds, home=None):
    """Record `repo_path` as trusted for each kind's CLI on this host; returns the kinds recorded now.

    The returned list is the receipt `forget` takes back: it names what this call actually wrote.
    """
    return _each(repo_path, kinds, home, "trust_ensure", present=True)


def forget(repo_path, kinds, home=None):
    """Remove the records `ensure` wrote for exactly this repository; returns the kinds removed."""
    return _each(repo_path, kinds, home, "trust_forget")


def _each(repo_path, kinds, home, answer, present=False):
    repo = os.path.normpath(repo_path)
    # Nothing is recorded for a repository that is not on this host: a path from a test's fake, or a
    # descriptor pointing elsewhere, would otherwise leave a row in the operator's own config.
    # Forgetting asks for no such proof — a probe removes its records after removing its repository.
    if present and not os.path.isdir(repo):
        return []
    done = []
    for kind in sorted(set(kinds or ())):
        try:
            writer = getattr(adapters.load(kind), answer, None)
            if writer is not None and writer(repo, home):
                done.append(kind)
        except Exception:                           # noqa: BLE001 - a dialog is the cost of failing here
            continue
    return done
