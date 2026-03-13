"""
app.py – Flask + Flask-SocketIO web application.

Serves the live-score website and provides REST/WebSocket endpoints that:
  • Stream the current game state to all connected browsers in real time
  • Accept move submissions from the human player
  • Trigger AI moves via the AI player module
  • Relay challenge requests received from the Arduino
  • Serve the camera live feed (MJPEG)
"""

import logging
import os
import threading
import time
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit

from ai_player import AIPlayer
from board_analysis import BoardAnalyzer
from constants import BOARD_SIZE, PLAYER_AI, PLAYER_HUMAN
from game_engine import GameEngine
from plotter_control import PlotterController
from serial_communication import ArduinoController, TileCartController

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Flask / SocketIO setup
# ---------------------------------------------------------------------------
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR  = os.path.join(BASE_DIR, "..", "frontend", "static")
TEMPLATE_DIR = os.path.join(BASE_DIR, "..", "frontend")

app = Flask(
    __name__,
    static_folder=STATIC_DIR,
    template_folder=TEMPLATE_DIR,
)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "scrabble-secret-key")
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# ---------------------------------------------------------------------------
# Hardware / game objects
# ---------------------------------------------------------------------------
SIMULATE = os.environ.get("SIMULATE", "true").lower() in ("1", "true", "yes")

game        = GameEngine()
ai_player   = AIPlayer(difficulty=os.environ.get("AI_DIFFICULTY", "hard"))
analyzer    = BoardAnalyzer(
    camera_index=int(os.environ.get("CAMERA_INDEX", "0")),
)
plotter     = PlotterController(
    port=os.environ.get("PLOTTER_PORT", "/dev/ttyUSB0"),
    simulate=SIMULATE,
)
arduino     = ArduinoController(
    port=os.environ.get("ARDUINO_PORT", "/dev/ttyACM0"),
    simulate=SIMULATE,
)
tile_cart   = TileCartController(
    port=os.environ.get("TILE_CART_PORT", "/dev/ttyUSB1"),
    simulate=SIMULATE,
)

# Board cell physical size and rack storage positions (mm)
CELL_SIZE_MM  = float(os.environ.get("CELL_SIZE_MM", "30.0"))
ORIGIN_X_MM   = float(os.environ.get("ORIGIN_X_MM", "0.0"))
ORIGIN_Y_MM   = float(os.environ.get("ORIGIN_Y_MM", "0.0"))

# Tile rack storage: letter → (x_mm, y_mm) – override via env or calibration
TILE_RACK_POSITIONS: Dict[str, tuple] = {}


def cell_to_mm(row: int, col: int) -> tuple:
    return analyzer.cell_to_mm(row, col, CELL_SIZE_MM, ORIGIN_X_MM, ORIGIN_Y_MM)


# ---------------------------------------------------------------------------
# Arduino message handler
# ---------------------------------------------------------------------------

def _on_arduino_message(data: Dict[str, Any]) -> None:
    """Handle messages received from the Arduino (challenge, navigate)."""
    msg_type = data.get("type")
    if msg_type == "challenge":
        word = data.get("word", "")
        logger.info("Challenge received from Arduino: '%s'", word)
        result = game.challenge_word(PLAYER_HUMAN, word)
        _broadcast_state()
        arduino.update_scores(game.scores[PLAYER_HUMAN], game.scores[PLAYER_AI])
        arduino.send_challenge_result(
            result.get("valid", False),
            word,
            result.get("points_awarded", 0),
        )
        socketio.emit("challenge_result", result)
    elif msg_type == "navigate":
        socketio.emit("navigate", data)


arduino.on_message(_on_arduino_message)


def _on_tile_cart_message(data: Dict[str, Any]) -> None:
    logger.debug("TileCart: %s", data)
    socketio.emit("tile_cart_status", data)


tile_cart.on_message(_on_tile_cart_message)

# ---------------------------------------------------------------------------
# Board scanning thread
# ---------------------------------------------------------------------------
_scan_lock = threading.Lock()


def _board_scan_loop(interval: float = 3.0) -> None:
    """Periodically scan the board and detect newly placed tiles."""
    logger.info("Board scan loop started (interval=%.1fs)", interval)
    while True:
        time.sleep(interval)
        if game.game_over:
            continue
        try:
            new_board = analyzer.analyse_board()
            if new_board is None:
                continue
            with _scan_lock:
                new_tiles = analyzer.detect_new_tiles(new_board)
                if new_tiles and game.current_player == PLAYER_HUMAN:
                    logger.info("Scanner detected new tiles: %s", new_tiles)
                    result = game.place_tiles(PLAYER_HUMAN, new_tiles)
                    if result["success"]:
                        _broadcast_state()
                        arduino.update_scores(
                            game.scores[PLAYER_HUMAN],
                            game.scores[PLAYER_AI],
                        )
                        tile_cart.move_to_player(PLAYER_AI)
                        # Trigger AI after short delay
                        threading.Timer(2.0, _trigger_ai_move).start()
                    else:
                        logger.warning("Invalid human move: %s", result.get("error"))
        except Exception as exc:
            logger.error("Board scan error: %s", exc, exc_info=True)


def _trigger_ai_move() -> None:
    """Find and execute the AI's move."""
    if game.game_over or game.current_player != PLAYER_AI:
        return
    with _scan_lock:
        tiles = ai_player.choose_move(game.board, game.racks[PLAYER_AI])
        if tiles is None:
            game.pass_turn(PLAYER_AI)
            logger.info("AI passed its turn")
        else:
            result = game.place_tiles(PLAYER_AI, tiles)
            if result["success"]:
                logger.info("AI placed %s for %d points", result["words"], result["score"])
                # Execute physical move via plotter
                if not SIMULATE:
                    plotter.execute_move(tiles, TILE_RACK_POSITIONS, cell_to_mm)
                # Notify Arduino of words that can be challenged
                arduino.send_challengeable_words(result["words"])
                tile_cart.move_to_player(PLAYER_HUMAN)
            else:
                logger.warning("AI move failed: %s", result.get("error"))
        _broadcast_state()
        arduino.update_scores(game.scores[PLAYER_HUMAN], game.scores[PLAYER_AI])
        arduino.send_turn(game.current_player)


# ---------------------------------------------------------------------------
# SocketIO helpers
# ---------------------------------------------------------------------------

def _broadcast_state() -> None:
    """Emit the current game state to all connected WebSocket clients."""
    socketio.emit("game_state", game.get_state())


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state", methods=["GET"])
def api_state():
    return jsonify(game.get_state())


@app.route("/api/place", methods=["POST"])
def api_place():
    """
    Place tiles on behalf of the human player.

    Expected JSON body:
        {"tiles": [[row, col, letter], ...]}
    """
    data = request.get_json(force=True)
    tiles = [(int(t[0]), int(t[1]), str(t[2]).upper()) for t in data.get("tiles", [])]
    result = game.place_tiles(PLAYER_HUMAN, tiles)
    if result["success"]:
        _broadcast_state()
        arduino.update_scores(game.scores[PLAYER_HUMAN], game.scores[PLAYER_AI])
        tile_cart.move_to_player(PLAYER_AI)
        threading.Timer(2.0, _trigger_ai_move).start()
    return jsonify(result)


@app.route("/api/pass", methods=["POST"])
def api_pass():
    result = game.pass_turn(PLAYER_HUMAN)
    if result["success"]:
        _broadcast_state()
        threading.Timer(1.0, _trigger_ai_move).start()
    return jsonify(result)


@app.route("/api/exchange", methods=["POST"])
def api_exchange():
    data = request.get_json(force=True)
    letters = [str(l).upper() for l in data.get("letters", [])]
    result = game.exchange_tiles(PLAYER_HUMAN, letters)
    if result["success"]:
        _broadcast_state()
        threading.Timer(1.0, _trigger_ai_move).start()
    return jsonify(result)


@app.route("/api/challenge", methods=["POST"])
def api_challenge():
    """
    Challenge a word via the web interface.

    Expected JSON body:
        {"word": "<word>"}
    """
    data = request.get_json(force=True)
    word = str(data.get("word", "")).upper()
    result = game.challenge_word(PLAYER_HUMAN, word)
    _broadcast_state()
    arduino.update_scores(game.scores[PLAYER_HUMAN], game.scores[PLAYER_AI])
    arduino.send_challenge_result(
        result.get("valid", False), word, result.get("points_awarded", 0)
    )
    return jsonify(result)


@app.route("/api/new_game", methods=["POST"])
def api_new_game():
    global game
    game = GameEngine()
    _broadcast_state()
    return jsonify({"success": True})


@app.route("/api/scan_board", methods=["POST"])
def api_scan_board():
    """Manually trigger a board scan and return the result."""
    board = analyzer.analyse_board()
    if board is None:
        return jsonify({"success": False, "error": "Board not detected"}), 500
    return jsonify({"success": True, "board": board})


@app.route("/video_feed")
def video_feed():
    """MJPEG live camera stream."""
    def generate():
        while True:
            frame_bytes = analyzer.get_latest_frame_jpeg()
            if frame_bytes:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + frame_bytes
                    + b"\r\n"
                )
            time.sleep(0.1)

    return Response(
        generate(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


# ---------------------------------------------------------------------------
# SocketIO events
# ---------------------------------------------------------------------------

@socketio.on("connect")
def on_connect():
    logger.info("WebSocket client connected: %s", request.sid)
    emit("game_state", game.get_state())


@socketio.on("disconnect")
def on_disconnect():
    logger.info("WebSocket client disconnected: %s", request.sid)


@socketio.on("place_tiles")
def ws_place_tiles(data):
    tiles = [(int(t[0]), int(t[1]), str(t[2]).upper()) for t in data.get("tiles", [])]
    result = game.place_tiles(PLAYER_HUMAN, tiles)
    if result["success"]:
        _broadcast_state()
        arduino.update_scores(game.scores[PLAYER_HUMAN], game.scores[PLAYER_AI])
        tile_cart.move_to_player(PLAYER_AI)
        threading.Timer(2.0, _trigger_ai_move).start()
    emit("place_result", result)


@socketio.on("challenge")
def ws_challenge(data):
    word = str(data.get("word", "")).upper()
    result = game.challenge_word(PLAYER_HUMAN, word)
    _broadcast_state()
    emit("challenge_result", result)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def _init_hardware():
    plotter.connect()
    arduino.connect()
    tile_cart.connect()
    if not SIMULATE:
        plotter.home()


if __name__ == "__main__":
    _init_hardware()

    # Start board scan loop in background (only when camera is available)
    if not SIMULATE:
        scan_thread = threading.Thread(target=_board_scan_loop, daemon=True)
        scan_thread.start()

    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() in ("1", "true", "yes")
    logger.info("Starting Scrabble server on port %d (simulate=%s)", port, SIMULATE)
    socketio.run(app, host="0.0.0.0", port=port, debug=debug)
