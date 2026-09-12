"""
Backward-compatibility shim for trackers.trend.
Canonical implementation now lives in `trackers.trend`.
"""

from trackers.trend import *

if __name__ == "__main__":
    import runpy
    runpy.run_module("trackers.trend", run_name="__main__")
