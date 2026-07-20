"""Test setup for the SDR domain layer.

These tests import only from `sdr/domain/` and `sdr/config/`, neither of which
touches Mongo. That matters: `database.py` reads os.environ["MONGO_URL"] at
import time, so anything importing it would need a live connection string just
to run a unit test. Keeping the domain layer I/O-free is what makes it
testable at all.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
