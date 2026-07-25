"""Test scaffolding for the self-improve pure-core test suite (anicha's trimmed copy).

Puts `skills/earn/self-improve/` on sys.path so tests can `from lib import gate_math` — this
repo only ships the pure `gate_math.py` module (no `evaluator.py`/`promote.py`/etc., which are
effectful and not self-contained), so this conftest is a minimal version of the original
project's own conftest.py that only does the path wiring `test_gate_math_property_fuzz.py` needs.
"""
from __future__ import annotations

import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SELF_IMPROVE_DIR = os.path.dirname(TESTS_DIR)
if SELF_IMPROVE_DIR not in sys.path:
    sys.path.insert(0, SELF_IMPROVE_DIR)
