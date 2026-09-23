"""The suite, as `python -m unittest` runs it, watched for an exit that does not come.

    python -m tests <what python -m unittest takes>

Once the tests have finished the interpreter has EXIT_SECONDS to exit; past that, every thread's stack
is written to stderr. The process is left as it is — a hang still shows, and now says where it is.
"""
import faulthandler
import sys
import unittest

EXIT_SECONDS = 60

program = unittest.main(module=None, exit=False)
faulthandler.dump_traceback_later(EXIT_SECONDS)
sys.exit(not program.result.wasSuccessful())
