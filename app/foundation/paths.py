"""Where this checkout is, and where its runs write on this host.

One definition of each. A second is equal only while every module sits where it sits
today, and drifts silently the moment one moves, so the checkout root is derived here
once and nowhere else; `tests/test_architecture.py` proves the derivation still lands
on a real checkout.

`workers.sh` and `workers.ps1` build the same runtime path for the shell side of the
lifecycle.
"""
import os

# app/foundation/paths.py -> app/foundation -> app -> the checkout.
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# A run's logs, its terminal records, and the pid files the lifecycle scripts read.
RUNTIME_ROOT = os.path.join(REPO, "tmp", "orchestration")
# What this deployment supplies and never commits: the workbench token, the Langfuse keys.
SECRETS = os.path.join(REPO, "secrets")
