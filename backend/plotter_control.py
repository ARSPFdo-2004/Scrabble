"""
plotter_control.py – X/Y/Z plotter control for tile manipulation.

Sends G-code style commands over a serial port to move the plotter head,
activate/deactivate the tile gripper, and position tiles on the board.
"""

import logging
import time
from typing import Optional, Tuple

import serial

logger = logging.getLogger(__name__)

# Default serial settings
DEFAULT_BAUD    = 115200
DEFAULT_TIMEOUT = 2  # seconds

# Z positions (mm)
Z_TRAVEL  = 20.0   # safe travel height
Z_PICK    = 0.5    # gripper down to pick tile
Z_PLACE   = 0.5    # gripper down to place tile

# Feed rates (mm/min)
FEED_XY = 3000
FEED_Z  = 1000


class PlotterController:
    """
    Controls the XYZ plotter over a serial connection.

    Parameters
    ----------
    port : str
        Serial port name, e.g. ``'/dev/ttyUSB0'`` or ``'COM3'``.
    baud_rate : int
        Baud rate (default 115200).
    simulate : bool
        When True, all serial commands are logged rather than sent.
        Useful for testing without hardware.
    """

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baud_rate: int = DEFAULT_BAUD,
        simulate: bool = False,
    ):
        self.port = port
        self.baud_rate = baud_rate
        self.simulate = simulate
        self._serial: Optional[serial.Serial] = None
        self._gripper_active = False
        self._current_pos: Tuple[float, float, float] = (0.0, 0.0, Z_TRAVEL)

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Open the serial connection.  Returns True on success."""
        if self.simulate:
            logger.info("[SIMULATE] Plotter connected on %s", self.port)
            return True
        try:
            self._serial = serial.Serial(
                self.port,
                self.baud_rate,
                timeout=DEFAULT_TIMEOUT,
            )
            time.sleep(2)  # wait for firmware to boot
            self._send_raw("G90")        # absolute positioning
            self._send_raw("G21")        # millimetre units
            logger.info("Plotter connected on %s at %d baud", self.port, self.baud_rate)
            return True
        except serial.SerialException as exc:
            logger.error("Cannot open serial port %s: %s", self.port, exc)
            return False

    def disconnect(self) -> None:
        """Close the serial connection."""
        if self._serial and self._serial.is_open:
            self._serial.close()
        logger.info("Plotter disconnected")

    def is_connected(self) -> bool:
        if self.simulate:
            return True
        return self._serial is not None and self._serial.is_open

    # ------------------------------------------------------------------
    # Low-level serial helpers
    # ------------------------------------------------------------------

    def _send_raw(self, command: str) -> str:
        """Send a raw G-code command and return the response line."""
        command = command.strip() + "\n"
        if self.simulate:
            logger.debug("[SIMULATE] >> %s", command.strip())
            return "ok"
        if self._serial and self._serial.is_open:
            self._serial.write(command.encode())
            response = self._serial.readline().decode(errors="replace").strip()
            logger.debug(">> %s | << %s", command.strip(), response)
            return response
        logger.warning("Serial port not open – command dropped: %s", command.strip())
        return ""

    def _wait_for_idle(self) -> None:
        """Send M400 (wait for moves to finish) and block until done."""
        self._send_raw("M400")

    # ------------------------------------------------------------------
    # Motion
    # ------------------------------------------------------------------

    def home(self) -> None:
        """Home all axes."""
        logger.info("Homing plotter")
        self._send_raw("G28")
        self._wait_for_idle()
        self._current_pos = (0.0, 0.0, Z_TRAVEL)

    def move_to(self, x: float, y: float, z: Optional[float] = None, feed: Optional[int] = None) -> None:
        """Move the plotter head to (x, y) at the given Z height."""
        if z is None:
            z = Z_TRAVEL
        f = feed or FEED_XY
        cmd = f"G1 X{x:.2f} Y{y:.2f} Z{z:.2f} F{f}"
        self._send_raw(cmd)
        self._wait_for_idle()
        self._current_pos = (x, y, z)

    def move_z(self, z: float) -> None:
        """Move only the Z axis."""
        cmd = f"G1 Z{z:.2f} F{FEED_Z}"
        self._send_raw(cmd)
        self._wait_for_idle()
        x, y, _ = self._current_pos
        self._current_pos = (x, y, z)

    # ------------------------------------------------------------------
    # Gripper (M-code relay)
    # ------------------------------------------------------------------

    def gripper_on(self) -> None:
        """Activate the vacuum/magnetic gripper."""
        self._send_raw("M3 S255")  # spindle / relay on
        self._gripper_active = True
        logger.debug("Gripper ON")

    def gripper_off(self) -> None:
        """Deactivate the gripper."""
        self._send_raw("M5")  # spindle / relay off
        self._gripper_active = False
        logger.debug("Gripper OFF")

    # ------------------------------------------------------------------
    # High-level tile operations
    # ------------------------------------------------------------------

    def pick_tile(self, x: float, y: float) -> None:
        """
        Move to (x, y), lower the head, activate the gripper, and raise.
        """
        logger.info("Picking tile at (%.1f, %.1f)", x, y)
        self.move_to(x, y, Z_TRAVEL)   # travel height
        self.move_z(Z_PICK)             # lower
        self.gripper_on()
        time.sleep(0.3)                 # brief dwell
        self.move_z(Z_TRAVEL)           # raise

    def place_tile(self, x: float, y: float) -> None:
        """
        Move to (x, y), lower the head, release the gripper, and raise.
        """
        logger.info("Placing tile at (%.1f, %.1f)", x, y)
        self.move_to(x, y, Z_TRAVEL)
        self.move_z(Z_PLACE)
        self.gripper_off()
        time.sleep(0.3)
        self.move_z(Z_TRAVEL)

    def transfer_tile(
        self,
        src_x: float,
        src_y: float,
        dst_x: float,
        dst_y: float,
    ) -> None:
        """Pick a tile from (src) and place it at (dst)."""
        self.pick_tile(src_x, src_y)
        self.place_tile(dst_x, dst_y)

    def execute_move(
        self,
        tiles: list,
        tile_rack_positions: dict,
        cell_to_mm_fn,
    ) -> None:
        """
        Execute a full AI move.

        Parameters
        ----------
        tiles : list of (row, col, letter)
            Tiles to place on the board.
        tile_rack_positions : dict
            Mapping of letter → (x_mm, y_mm) in the tile storage area.
        cell_to_mm_fn : callable
            Function (row, col) → (x_mm, y_mm) for board coordinates.
        """
        for row, col, letter in tiles:
            if letter not in tile_rack_positions:
                logger.warning("No rack position for letter '%s' – skipping", letter)
                continue
            src_x, src_y = tile_rack_positions[letter]
            dst_x, dst_y = cell_to_mm_fn(row, col)
            logger.info("Moving '%s' from rack (%.1f,%.1f) to board (%d,%d)", letter, src_x, src_y, row, col)
            self.transfer_tile(src_x, src_y, dst_x, dst_y)

        # Return to safe home position after move
        self.move_to(0.0, 0.0, Z_TRAVEL)
