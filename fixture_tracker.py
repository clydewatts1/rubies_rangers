"""
Backward-compatibility shim for trackers.fixture.
Canonical implementation now lives in `trackers.fixture`.
"""

from trackers.fixture import *

if __name__ == "__main__":
    import runpy
    runpy.run_module("trackers.fixture", run_name="__main__")
