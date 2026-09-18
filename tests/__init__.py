"""Test package. Discovery starts at the subsystem root, which is what puts
the modules under test on sys.path - the tests import them by name, never by
a path relative to this directory."""
