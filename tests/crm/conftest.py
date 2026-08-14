"""Test setup for the CRM.

These tests were previously under `tests/sdr/`, because that is where the
in-memory database fixture happened to live. They never tested the SDR module -
they cover the lead pipeline, the won automation, the public endpoints and the
delete cascade - so when that module was deleted they moved here rather than
going with it.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
