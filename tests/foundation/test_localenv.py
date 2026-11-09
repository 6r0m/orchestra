"""The private deployment file has one parser; callers choose their own failure policy."""
import os
import tempfile
import unittest

from app.foundation import localenv


class PrivateValues(unittest.TestCase):
    def test_values_are_read_without_exporting_them(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, ".env")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("# private deployment values\n ONE = 'first'\nTWO=\"second=part\"\nEMPTY=\n")
            before = dict(os.environ)
            self.assertEqual(localenv.read(path), {"ONE": "first", "TWO": "second=part", "EMPTY": ""})
            self.assertEqual(dict(os.environ), before)

    def test_absent_is_empty_but_unreadable_is_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, ".env")
            self.assertEqual(localenv.read(path), {})
            with open(path, "wb") as fh:
                fh.write(b"KEY=\xff")
            with self.assertRaises(UnicodeError):
                localenv.read(path)
            with self.assertRaises(OSError):
                localenv.read(folder)
