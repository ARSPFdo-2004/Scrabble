"""
conftest.py – Pytest configuration shared by all test modules.
"""
import sys
import os

# Ensure simulate mode for all tests
os.environ.setdefault("SIMULATE", "true")

# Ensure the backend package is importable from tests
BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import pytest


@pytest.fixture()
def game_engine():
    """Return a fresh GameEngine instance."""
    from game_engine import GameEngine
    return GameEngine()


@pytest.fixture()
def ai_player_hard():
    """Return an AIPlayer with 'hard' difficulty."""
    from ai_player import AIPlayer
    return AIPlayer(difficulty="hard")


@pytest.fixture()
def empty_board():
    """Return a 15×15 board with all cells set to None."""
    from constants import BOARD_SIZE
    return [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]


@pytest.fixture()
def plotter_sim():
    """Return a PlotterController in simulation mode."""
    from plotter_control import PlotterController
    p = PlotterController(port="/dev/null", simulate=True)
    p.connect()
    return p


@pytest.fixture()
def arduino_sim():
    """Return an ArduinoController in simulation mode."""
    from serial_communication import ArduinoController
    a = ArduinoController(port="/dev/null", simulate=True)
    a.connect()
    return a


@pytest.fixture()
def tile_cart_sim():
    """Return a TileCartController in simulation mode."""
    from serial_communication import TileCartController
    t = TileCartController(port="/dev/null", simulate=True)
    t.connect()
    return t
