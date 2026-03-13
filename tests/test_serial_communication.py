"""
tests/test_serial_communication.py – Tests for the serial communication
wrappers in simulation mode.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from serial_communication import ArduinoController, TileCartController


class TestArduinoController:
    def test_connect_simulate(self):
        arduino = ArduinoController(simulate=True)
        assert arduino.connect()

    def test_send_scores_no_error(self):
        arduino = ArduinoController(simulate=True)
        arduino.connect()
        # Should not raise
        arduino.update_scores(42, 17)

    def test_send_words_no_error(self):
        arduino = ArduinoController(simulate=True)
        arduino.connect()
        arduino.send_challengeable_words(["CAT", "DOG"])

    def test_send_challenge_result(self):
        arduino = ArduinoController(simulate=True)
        arduino.connect()
        arduino.send_challenge_result(valid=False, word="XYZ", points=15)

    def test_send_turn(self):
        arduino = ArduinoController(simulate=True)
        arduino.connect()
        arduino.send_turn("human")

    def test_message_callback(self):
        received = []
        arduino = ArduinoController(simulate=True)
        arduino.on_message(received.append)
        # Simulate is True, so _on_message won't fire via serial thread,
        # but we can invoke it manually
        arduino._on_message({"type": "challenge", "word": "CAT"})
        assert received == [{"type": "challenge", "word": "CAT"}]


class TestTileCartController:
    def test_connect_simulate(self):
        cart = TileCartController(simulate=True)
        assert cart.connect()

    def test_move_to_player_no_error(self):
        cart = TileCartController(simulate=True)
        cart.connect()
        cart.move_to_player("human")
        cart.move_to_player("ai")

    def test_stop_no_error(self):
        cart = TileCartController(simulate=True)
        cart.connect()
        cart.stop()

    def test_home_no_error(self):
        cart = TileCartController(simulate=True)
        cart.connect()
        cart.home()
