"""
Backward-compatibility shim for trackers.setpiece.
Canonical implementation now lives in `trackers.setpiece`.
"""

from trackers.setpiece import *

if __name__ == "__main__":
    import runpy
    runpy.run_module("trackers.setpiece", run_name="__main__")
