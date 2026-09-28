"""Test package. Discovery starts at the checkout, which is what puts `app` on
sys.path; the tests import it by package path. Each concern under `app/` has a
folder of its own here, and the shared harness — the fakes, the controls, the
fixtures and the recorded histories — stays at this root.

The suite never reads the operator's own settings or descriptors: whichever way it is
run, its processes name the shared settings alone, so no local patch is applied, and a
descriptor file of the suite's own, which lists none."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["ORCHESTRA_SETTINGS"] = os.path.join(os.path.dirname(HERE), ".orchestra", "settings.json")
os.environ["ORCHESTRA_REPOS"] = os.path.join(HERE, "fixtures", "descriptors.json")
