"""A test's temporary folder, taken back whole.

Git writes its object files read-only, and Windows deletes no read-only file, so `shutil.rmtree` with
its errors ignored left every repository a test made in the Windows temporary folder. A file that still
cannot be removed fails the test's cleanup instead: something the test started still holds it.
"""
import os
import shutil
import stat


def remove(path):
    def writable(function, name, _):
        os.chmod(name, stat.S_IWRITE)
        function(name)
    if os.path.lexists(path):
        shutil.rmtree(path, onexc=writable)
