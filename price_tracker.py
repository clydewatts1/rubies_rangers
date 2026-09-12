"""
Backward-compatibility shim for trackers.price.
Canonical implementation now lives in `trackers.price`.
"""

from trackers.price import *

if __name__ == "__main__":
    import runpy
    runpy.run_module("trackers.price", run_name="__main__")
