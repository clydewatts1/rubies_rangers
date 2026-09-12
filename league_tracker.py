"""
Backward-compatibility shim for trackers.league.
Canonical implementation now lives in `trackers.league`.
"""

from trackers.league import *

if __name__ == "__main__":
    import runpy
    runpy.run_module("trackers.league", run_name="__main__")
