"""Test package. Discovery starts at the checkout, which is what puts `app` on
sys.path; the tests import it by package path. Each concern under `app/` has a
folder of its own here, and the shared harness — the fakes, the controls, the
fixtures and the recorded histories — stays at this root."""
