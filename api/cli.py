# =============================================================================
# cli.py
# Bootstrap CLI entry point for the mlb console_script.
# Ensures the project root is on sys.path so top-level modules
# (run.py, run_historical_ingest.py) are importable.
# Rubén Eduardo Casares Rosales
# =============================================================================

import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from run import main
