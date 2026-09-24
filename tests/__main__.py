"""`python -m tests`: the suite, as `tests/runner.py` runs it — one process, or each class in its own."""
import sys

from tests import runner

sys.exit(runner.main(sys.argv[1:]))
