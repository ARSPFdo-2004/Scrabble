"""
board_analysis.py – OpenCV-based Scrabble board analysis.

Captures frames from a camera, detects the board grid, and reads
tile letters using adaptive thresholding + contour analysis.
"""

import logging
import time
from typing import List, Optional, Tuple

import cv2
import numpy as np

from constants import BOARD_SIZE

logger = logging.getLogger(__name__)

# Physical pixel size of each cell in the rectified board image
CELL_SIZE = 40
BOARD_PX  = CELL_SIZE * BOARD_SIZE  # 600 × 600 rectified image


class BoardAnalyzer:
    """
    Captures frames from a camera and analyses the Scrabble board.

    Parameters
    ----------
    camera_index : int
        OpenCV camera index (default 0).
    calibration_file : str | None
        Path to an optional NumPy .npz file containing the pre-computed
        homography matrix (key ``H``).  When *None* the homography is
        estimated automatically from the first frame.
    """

    def __init__(self, camera_index: int = 0, calibration_file: Optional[str] = None):
        self.camera_index = camera_index
        self._cap: Optional[cv2.VideoCapture] = None
        self._homography: Optional[np.ndarray] = None
        self._prev_board: List[List[Optional[str]]] = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]

        if calibration_file:
            try:
                data = np.load(calibration_file)
                self._homography = data["H"]
                logger.info("Loaded homography from %s", calibration_file)
            except Exception as exc:
                logger.warning("Could not load calibration file: %s", exc)

        # Pre-build reference letter templates (simple font rendering)
        self._templates = self._build_letter_templates()

    # ------------------------------------------------------------------
    # Camera lifecycle
    # ------------------------------------------------------------------

    def open_camera(self) -> bool:
        """Open the video capture device.  Returns True on success."""
        self._cap = cv2.VideoCapture(self.camera_index)
        if not self._cap.isOpened():
            logger.error("Cannot open camera %d", self.camera_index)
            return False
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        logger.info("Camera %d opened", self.camera_index)
        return True

    def close_camera(self) -> None:
        """Release the video capture device."""
        if self._cap and self._cap.isOpened():
            self._cap.release()
            self._cap = None

    def capture_frame(self) -> Optional[np.ndarray]:
        """Capture and return a single BGR frame from the camera."""
        if self._cap is None or not self._cap.isOpened():
            if not self.open_camera():
                return None
        ret, frame = self._cap.read()
        if not ret:
            logger.warning("Failed to read frame from camera")
            return None
        return frame

    # ------------------------------------------------------------------
    # Board detection
    # ------------------------------------------------------------------

    def _detect_board_corners(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Detect the four corners of the Scrabble board in *frame*.

        Uses Canny edge detection + contour approximation to find the
        largest quadrilateral in the image.

        Returns a (4, 2) float32 array in top-left, top-right,
        bottom-right, bottom-left order, or None if not found.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (7, 7), 0)
        edges = cv2.Canny(blurred, 50, 150)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        edges = cv2.dilate(edges, kernel, iterations=1)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        for cnt in contours[:5]:
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
            if len(approx) == 4:
                return self._order_corners(approx.reshape(4, 2).astype(np.float32))
        return None

    @staticmethod
    def _order_corners(pts: np.ndarray) -> np.ndarray:
        """Order corners: TL, TR, BR, BL."""
        rect = np.zeros((4, 2), dtype=np.float32)
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]   # TL
        rect[2] = pts[np.argmax(s)]   # BR
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]  # TR
        rect[3] = pts[np.argmax(diff)]  # BL
        return rect

    def _rectify_board(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Warp the board region to a canonical square image of size
        BOARD_PX × BOARD_PX.
        """
        if self._homography is None:
            corners = self._detect_board_corners(frame)
            if corners is None:
                logger.warning("Board corners not detected")
                return None
            dst = np.array([
                [0, 0],
                [BOARD_PX - 1, 0],
                [BOARD_PX - 1, BOARD_PX - 1],
                [0, BOARD_PX - 1],
            ], dtype=np.float32)
            self._homography, _ = cv2.findHomography(corners, dst)

        rectified = cv2.warpPerspective(frame, self._homography, (BOARD_PX, BOARD_PX))
        return rectified

    # ------------------------------------------------------------------
    # Tile / letter recognition
    # ------------------------------------------------------------------

    def _build_letter_templates(self) -> dict:
        """
        Build small grayscale template images for each letter A-Z using
        OpenCV's built-in font.  These are used for template-matching
        letter recognition.
        """
        templates = {}
        size = CELL_SIZE - 4  # slightly smaller than a cell
        for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            img = np.zeros((size, size), dtype=np.uint8)
            cv2.putText(
                img, ch,
                (4, size - 6),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9, 255, 2,
            )
            templates[ch] = img
        return templates

    def _recognize_letter(self, cell_img: np.ndarray) -> Optional[str]:
        """
        Recognise the letter on a single cell image.

        Returns the recognised letter, or None if the cell appears empty.
        """
        gray = cv2.cvtColor(cell_img, cv2.COLOR_BGR2GRAY) if len(cell_img.shape) == 3 else cell_img
        resized = cv2.resize(gray, (CELL_SIZE - 4, CELL_SIZE - 4))

        # Check if cell is likely occupied (bright tile on darker board)
        mean_val = np.mean(resized)
        if mean_val < 30 or mean_val > 230:  # likely empty board square
            return None

        # Adaptive threshold to isolate the letter
        thresh = cv2.adaptiveThreshold(
            resized, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            11, 4,
        )

        # Template match against all letters
        best_letter: Optional[str] = None
        best_score: float = 0.3  # minimum correlation threshold

        for ch, tmpl in self._templates.items():
            result = cv2.matchTemplate(thresh, tmpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)
            if max_val > best_score:
                best_score = max_val
                best_letter = ch

        return best_letter

    def analyse_board(self, frame: Optional[np.ndarray] = None) -> Optional[List[List[Optional[str]]]]:
        """
        Analyse a board frame and return a 15×15 grid of letters (or None
        for empty squares).

        If *frame* is None a new frame is captured from the camera.
        Returns None when the board cannot be detected.
        """
        if frame is None:
            frame = self.capture_frame()
            if frame is None:
                return None

        rectified = self._rectify_board(frame)
        if rectified is None:
            return None

        board: List[List[Optional[str]]] = []
        for row in range(BOARD_SIZE):
            board_row: List[Optional[str]] = []
            for col in range(BOARD_SIZE):
                y1 = row * CELL_SIZE
                y2 = y1 + CELL_SIZE
                x1 = col * CELL_SIZE
                x2 = x1 + CELL_SIZE
                cell = rectified[y1:y2, x1:x2]
                letter = self._recognize_letter(cell)
                board_row.append(letter)
            board.append(board_row)

        self._prev_board = board
        return board

    def detect_new_tiles(
        self,
        new_board: List[List[Optional[str]]],
        old_board: Optional[List[List[Optional[str]]]] = None,
    ) -> List[Tuple[int, int, str]]:
        """
        Compare *new_board* against *old_board* (defaults to the last
        analysed board) and return the newly placed tiles as a list of
        (row, col, letter) tuples.
        """
        if old_board is None:
            old_board = self._prev_board
        new_tiles = []
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                old_cell = old_board[r][c]
                new_cell = new_board[r][c]
                if old_cell is None and new_cell is not None:
                    new_tiles.append((r, c, new_cell))
        return new_tiles

    # ------------------------------------------------------------------
    # Plotter coordinate helpers
    # ------------------------------------------------------------------

    def cell_to_mm(
        self,
        row: int,
        col: int,
        cell_size_mm: float = 30.0,
        origin_x_mm: float = 0.0,
        origin_y_mm: float = 0.0,
    ) -> Tuple[float, float]:
        """
        Convert a board (row, col) to plotter coordinates in millimetres.

        Parameters
        ----------
        row, col       : Board cell indices (0-based)
        cell_size_mm   : Physical size of one board cell
        origin_x_mm    : X offset of the board's top-left corner
        origin_y_mm    : Y offset of the board's top-left corner
        """
        x_mm = origin_x_mm + (col + 0.5) * cell_size_mm
        y_mm = origin_y_mm + (row + 0.5) * cell_size_mm
        return x_mm, y_mm

    def get_latest_frame_jpeg(self) -> Optional[bytes]:
        """Capture a frame and return it as JPEG bytes for the live feed."""
        frame = self.capture_frame()
        if frame is None:
            return None
        ret, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ret:
            return None
        return bytes(buf)
