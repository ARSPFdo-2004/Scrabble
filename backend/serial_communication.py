"""
serial_communication.py – Serial bridge to Arduino (score display / challenge)
and ESP32 (tile cart).

Both devices communicate via UART at 9600 baud using simple newline-delimited
JSON messages.
"""

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

import serial

logger = logging.getLogger(__name__)

DEFAULT_BAUD    = 9600
DEFAULT_TIMEOUT = 1


class SerialDevice:
    """
    Generic serial device wrapper.

    Receives newline-delimited JSON messages and dispatches them to a
    registered callback.  Sends JSON messages to the device.
    """

    def __init__(
        self,
        port: str,
        baud_rate: int = DEFAULT_BAUD,
        name: str = "device",
        simulate: bool = False,
    ):
        self.port = port
        self.baud_rate = baud_rate
        self.name = name
        self.simulate = simulate
        self._serial: Optional[serial.Serial] = None
        self._rx_thread: Optional[threading.Thread] = None
        self._running = False
        self._on_message: Optional[Callable[[Dict[str, Any]], None]] = None

    def on_message(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Register a callback for incoming messages."""
        self._on_message = callback

    def connect(self) -> bool:
        if self.simulate:
            logger.info("[SIMULATE] %s connected on %s", self.name, self.port)
            return True
        try:
            self._serial = serial.Serial(self.port, self.baud_rate, timeout=DEFAULT_TIMEOUT)
            time.sleep(1)
            self._running = True
            self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
            self._rx_thread.start()
            logger.info("%s connected on %s at %d baud", self.name, self.port, self.baud_rate)
            return True
        except serial.SerialException as exc:
            logger.error("Cannot open %s on %s: %s", self.name, self.port, exc)
            return False

    def disconnect(self) -> None:
        self._running = False
        if self._serial and self._serial.is_open:
            self._serial.close()
        logger.info("%s disconnected", self.name)

    def send(self, data: Dict[str, Any]) -> None:
        """Serialise *data* as JSON and write to the serial port."""
        message = json.dumps(data) + "\n"
        if self.simulate:
            logger.debug("[SIMULATE] %s >> %s", self.name, message.strip())
            return
        if self._serial and self._serial.is_open:
            try:
                self._serial.write(message.encode())
            except serial.SerialException as exc:
                logger.error("Write error on %s: %s", self.name, exc)
        else:
            logger.warning("%s not connected – message dropped: %s", self.name, message.strip())

    def _rx_loop(self) -> None:
        """Background thread that reads incoming lines from the serial port."""
        while self._running and self._serial and self._serial.is_open:
            try:
                raw = self._serial.readline()
                if raw:
                    text = raw.decode(errors="replace").strip()
                    if text:
                        try:
                            data = json.loads(text)
                            if self._on_message:
                                self._on_message(data)
                        except json.JSONDecodeError:
                            logger.debug("%s raw: %s", self.name, text)
            except serial.SerialException as exc:
                logger.error("Read error on %s: %s", self.name, exc)
                break


class ArduinoController(SerialDevice):
    """
    Communicates with the Arduino that drives the score display and the
    word-challenge navigation buttons.

    Outgoing message types
    ----------------------
    ``{"type": "scores", "human": <int>, "ai": <int>}``
        Update the score display.
    ``{"type": "words", "words": [<str>, ...]}``
        Send the list of AI-placed words that can be challenged.
    ``{"type": "challenge_result", "valid": <bool>, "word": <str>, "points": <int>}``
        Inform the display of a challenge outcome.
    ``{"type": "turn", "player": "human"|"ai"}``
        Indicate whose turn it is.

    Incoming message types (from Arduino)
    --------------------------------------
    ``{"type": "challenge", "word": <str>}``
        Human has selected a word to challenge via the navigation buttons.
    ``{"type": "navigate", "direction": "up"|"down"|"select"}``
        Raw navigation event (optional, handled on the server).
    """

    def __init__(self, port: str = "/dev/ttyACM0", simulate: bool = False):
        super().__init__(port, baud_rate=DEFAULT_BAUD, name="Arduino", simulate=simulate)

    def update_scores(self, human: int, ai: int) -> None:
        self.send({"type": "scores", "human": human, "ai": ai})

    def send_challengeable_words(self, words: list) -> None:
        self.send({"type": "words", "words": words})

    def send_challenge_result(self, valid: bool, word: str, points: int) -> None:
        self.send({"type": "challenge_result", "valid": valid, "word": word, "points": points})

    def send_turn(self, player: str) -> None:
        self.send({"type": "turn", "player": player})


class TileCartController(SerialDevice):
    """
    Communicates with the ESP32-controlled tile cart.

    Outgoing message types
    ----------------------
    ``{"type": "move", "player": "human"|"ai"}``
        Drive the cart towards the specified player's side.
    ``{"type": "stop"}``
        Stop the cart.
    ``{"type": "home"}``
        Return the cart to its home position.

    Incoming message types (from ESP32)
    ------------------------------------
    ``{"type": "arrived", "player": <str>}``
        Cart has reached the player's position.
    ``{"type": "status", "state": <str>}``
        General status update.
    """

    def __init__(self, port: str = "/dev/ttyUSB1", simulate: bool = False):
        super().__init__(port, baud_rate=DEFAULT_BAUD, name="TileCart", simulate=simulate)

    def move_to_player(self, player: str) -> None:
        """Drive the cart to the human or AI side."""
        self.send({"type": "move", "player": player})

    def stop(self) -> None:
        self.send({"type": "stop"})

    def home(self) -> None:
        self.send({"type": "home"})
