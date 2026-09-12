"""
Backward-compatibility shim for trackers.xp.
Canonical implementation now lives in `trackers.xp`.
"""

from trackers.xp import *

if __name__ == "__main__":
    import runpy
    runpy.run_module("trackers.xp", run_name="__main__")
