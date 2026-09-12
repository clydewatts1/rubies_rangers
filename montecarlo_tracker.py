"""
Backward-compatibility shim for trackers.montecarlo.
Canonical implementation now lives in `trackers.montecarlo`.
"""

from trackers.montecarlo import *

if __name__ == "__main__":
    import runpy
    runpy.run_module("trackers.montecarlo", run_name="__main__")
