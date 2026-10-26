"""Load a script from scripts/ by its file name, for the unit and the contract suites.

The scripts are deliberately not a package and not pytest files: each is run by hand.
Loading one costs no network; what it then calls is up to the test.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def load_script(filename: str) -> ModuleType:
    """The module of scripts/<filename>, loaded without importing `scripts` as a package."""
    spec = importlib.util.spec_from_file_location(f"_{Path(filename).stem}", SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
