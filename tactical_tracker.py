"""
Backward-compatibility shim for trackers.tactical.
Canonical implementation now lives in `trackers.tactical`.
"""

from trackers.tactical import *

if __name__ == "__main__":
    import runpy
    runpy.run_module("trackers.tactical", run_name="__main__")
