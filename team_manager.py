"""
Backward-compatibility shim for analytics.team_manager.
Canonical implementation now lives in `analytics.team_manager`.
"""

from analytics.team_manager import *

if __name__ == "__main__":
    import runpy
    runpy.run_module("analytics.team_manager", run_name="__main__")
