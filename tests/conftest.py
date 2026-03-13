"""
conftest.py – Pytest configuration shared by all test modules.
"""
import sys
import os

# Ensure the backend package is importable from tests
BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
