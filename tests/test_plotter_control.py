"""
tests/test_plotter_control.py – Tests for the plotter controller in
simulation mode (no hardware required).
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from plotter_control import PlotterController, Z_TRAVEL, Z_PICK, Z_PLACE


@pytest.fixture
def plotter():
    p = PlotterController(port="/dev/ttyUSB0", simulate=True)
    p.connect()
    return p


class TestPlotterController:
    def test_connect_simulate(self, plotter):
        assert plotter.is_connected()

    def test_initial_position(self, plotter):
        assert plotter._current_pos == (0.0, 0.0, Z_TRAVEL)

    def test_move_to_updates_position(self, plotter):
        plotter.move_to(100.0, 200.0, 10.0)
        assert plotter._current_pos == (100.0, 200.0, 10.0)

    def test_move_z_updates_z(self, plotter):
        plotter.move_z(5.0)
        x, y, z = plotter._current_pos
        assert z == 5.0

    def test_gripper_state_on_off(self, plotter):
        plotter.gripper_on()
        assert plotter._gripper_active
        plotter.gripper_off()
        assert not plotter._gripper_active

    def test_pick_tile_activates_gripper(self, plotter):
        plotter.pick_tile(50.0, 75.0)
        assert plotter._gripper_active

    def test_place_tile_deactivates_gripper(self, plotter):
        plotter.gripper_on()
        plotter.place_tile(50.0, 75.0)
        assert not plotter._gripper_active

    def test_transfer_tile_cycle(self, plotter):
        plotter.transfer_tile(10.0, 10.0, 200.0, 150.0)
        # After transfer, gripper should be off
        assert not plotter._gripper_active

    def test_execute_move(self, plotter):
        from board_analysis import BoardAnalyzer
        ana = BoardAnalyzer()
        def cell_mm(r, c):
            return ana.cell_to_mm(r, c)
        rack_positions = {
            'H': (10.0, 10.0),
            'I': (40.0, 10.0),
            'T': (70.0, 10.0),
        }
        tiles = [(7, 7, 'H'), (7, 8, 'I'), (7, 9, 'T')]
        # Should run without error in simulate mode
        plotter.execute_move(tiles, rack_positions, cell_mm)
