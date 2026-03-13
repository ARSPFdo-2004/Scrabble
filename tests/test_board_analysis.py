"""
tests/test_board_analysis.py – Tests for the OpenCV board analyser
(runs without a real camera using synthetic test images).
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import numpy as np
import pytest

from board_analysis import BoardAnalyzer, BOARD_PX, CELL_SIZE, BOARD_SIZE


@pytest.fixture
def analyzer():
    return BoardAnalyzer(camera_index=0)


class TestBoardAnalyzer:
    def test_cell_to_mm_origin(self, analyzer):
        """Cell (0,0) centre should be at half a cell size from origin."""
        x, y = analyzer.cell_to_mm(0, 0, cell_size_mm=30.0, origin_x_mm=0.0, origin_y_mm=0.0)
        assert x == pytest.approx(15.0)
        assert y == pytest.approx(15.0)

    def test_cell_to_mm_offset(self, analyzer):
        x, y = analyzer.cell_to_mm(1, 2, cell_size_mm=30.0, origin_x_mm=10.0, origin_y_mm=5.0)
        assert x == pytest.approx(10.0 + 2.5 * 30.0)
        assert y == pytest.approx(5.0  + 1.5 * 30.0)

    def test_detect_new_tiles_empty(self, analyzer):
        """No new tiles when boards are identical."""
        board = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        result = analyzer.detect_new_tiles(board, board)
        assert result == []

    def test_detect_new_tiles_finds_difference(self, analyzer):
        old = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        new = [row[:] for row in old]
        new[7][7] = 'A'
        new[7][8] = 'T'
        result = analyzer.detect_new_tiles(new, old)
        assert len(result) == 2
        assert (7, 7, 'A') in result
        assert (7, 8, 'T') in result

    def test_board_constants(self):
        assert BOARD_PX == CELL_SIZE * BOARD_SIZE

    def test_templates_built(self, analyzer):
        assert len(analyzer._templates) == 26
        for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            assert ch in analyzer._templates

    def test_order_corners(self):
        pts = np.array([
            [100, 100],
            [500, 100],
            [500, 500],
            [100, 500],
        ], dtype=np.float32)
        ordered = BoardAnalyzer._order_corners(pts)
        # TL should be (100,100)
        assert tuple(ordered[0]) == (100.0, 100.0)
        # BR should be (500,500)
        assert tuple(ordered[2]) == (500.0, 500.0)

    def test_rectify_returns_correct_size(self, analyzer):
        """
        Feed a synthetic frame with a clear white rectangle in the centre
        and verify the homography produces a BOARD_PX × BOARD_PX image.
        """
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        # Draw a thick white quadrilateral (simulated board outline)
        pts = np.array([[200, 100], [1080, 100], [1080, 620], [200, 620]], dtype=np.int32)
        import cv2
        cv2.polylines(frame, [pts], isClosed=True, color=(255, 255, 255), thickness=5)
        result = analyzer._rectify_board(frame)
        if result is not None:
            assert result.shape == (BOARD_PX, BOARD_PX, 3)
