# Scrabble – Hardware-Assisted Score Automation

## Quick Start (no hardware required)

> **Requirements:** Python 3.8 or newer.

```bash
# 1. Clone and enter the repo
git clone https://github.com/ARSPFdo-2004/Scrabble.git
cd Scrabble

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install Python dependencies
pip install -r backend/requirements.txt

# 4. Create the environment file (simulation mode is on by default)
cp backend/.env.example backend/.env

# 5. Start the web server
cd backend
python app.py
```

Then open **http://localhost:5000** in your browser to play.  
All hardware (camera, plotter, Arduino, ESP32) is simulated automatically
because `SIMULATE=true` is the default in `.env.example`.

To run the test suite:

```bash
pip install pytest          # one-time
python -m pytest tests/ -v
```

---

A full-stack system for a two-player Scrabble game where:

- **Human player** places tiles on a physical board
- **AI player** places tiles using an XYZ plotter head
- A **top-mounted camera** scans the board via OpenCV
- A **Flask web server** provides a live-score website (WebSocket)
- An **Arduino** drives the 20×4 LCD score display and handles the challenge navigation buttons
- An **ESP32** controls a motorised tile cart that delivers tiles to the current player

---

## Repository structure

```
Scrabble/
├── backend/
│   ├── app.py                  # Flask + Socket.IO web server (entry point)
│   ├── game_engine.py          # Scrabble rules, scoring, challenge logic
│   ├── board_analysis.py       # OpenCV board scanner & letter recognition
│   ├── ai_player.py            # AI word-placement engine
│   ├── plotter_control.py      # XYZ plotter serial control (G-code)
│   ├── serial_communication.py # Arduino & ESP32 serial bridge
│   ├── dictionary.py           # Word validation
│   ├── constants.py            # Board layout, letter values, tile counts
│   ├── requirements.txt        # Python dependencies
│   └── .env.example            # Environment variable template
├── frontend/
│   ├── index.html              # Live-score single-page app
│   └── static/
│       ├── css/style.css
│       └── js/app.js
├── arduino/
│   ├── score_display/
│   │   └── score_display.ino   # Arduino score display + challenge nav
│   └── tile_cart/
│       └── tile_cart.ino       # ESP32 tile cart motor controller
└── tests/
    ├── conftest.py
    ├── test_game_engine.py
    ├── test_board_analysis.py
    ├── test_plotter_control.py
    ├── test_serial_communication.py
    └── test_dictionary.py
```

---

## Hardware requirements

| Component | Details |
|-----------|---------|
| XYZ plotter | Any GRBL-compatible 3-axis CNC / plotter |
| Camera | USB webcam or Raspberry Pi Camera (top-mounted, 1280×720+) |
| Arduino Mega/Uno | Score display + challenge buttons |
| 20×4 I2C LCD | Address 0x27, connected to Arduino |
| Navigation buttons | 3 buttons (UP / DOWN / SELECT) wired to Arduino digital pins |
| ESP32 dev board | Tile cart motor control |
| L298N motor driver | Dual H-bridge for cart wheels |
| 2× IR sensors | End-stop detection for tile cart |
| Raspberry Pi / PC | Runs the Python backend |

---

## Software setup

### Python backend

```bash
cd backend
cp .env.example .env        # edit serial ports, camera index, etc.
pip install -r requirements.txt
python app.py               # default: http://0.0.0.0:5000
```

Set `SIMULATE=true` in `.env` to run without physical hardware.

### Arduino libraries (install via Arduino IDE Library Manager)

- `LiquidCrystal_I2C` by Frank de Brabander
- `ArduinoJson` by Benoit Blanchon (v6)

Flash `arduino/score_display/score_display.ino` to the Arduino.

### ESP32 libraries

- `ArduinoJson` by Benoit Blanchon (v6)

Flash `arduino/tile_cart/tile_cart.ino` to the ESP32.

---

## Running the live-score website

1. Start the backend (`python app.py`).
2. Open a browser and navigate to `http://<server-ip>:5000`.
3. The live board, scores, move history, and camera feed are displayed.
4. Use the **Place Tiles** form to enter moves (format: `row,col,letter` one per line).
5. Click **Challenge** to challenge the AI's last word.

---

## Game rules summary

- Standard 15×15 Scrabble board with all premium squares.
- Two players: **Human** (👤) and **AI** (🤖).
- Human player moves first.
- AI automatically picks the highest-scoring word from its rack.
- The human can **challenge** any word placed by the AI.
  - Valid word → challenger loses their turn.
  - Invalid word → opponent's tiles are removed, challenger earns the points.
- Bingo bonus: +50 points for using all 7 rack tiles in one move.
- Game ends when a player empties their rack with an empty bag, or after 4 consecutive passes.

---

## Running tests

```bash
pip install pytest
python -m pytest tests/ -v
```

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SIMULATE` | `true` | Skip real hardware (serial / camera) |
| `PORT` | `5000` | HTTP port |
| `AI_DIFFICULTY` | `hard` | `easy` / `medium` / `hard` |
| `CAMERA_INDEX` | `0` | OpenCV camera index |
| `PLOTTER_PORT` | `/dev/ttyUSB0` | Plotter serial port |
| `ARDUINO_PORT` | `/dev/ttyACM0` | Arduino serial port |
| `TILE_CART_PORT` | `/dev/ttyUSB1` | ESP32 tile cart port |
| `CELL_SIZE_MM` | `30.0` | Physical board cell size (mm) |
| `ORIGIN_X_MM` | `0.0` | Plotter X origin offset (mm) |
| `ORIGIN_Y_MM` | `0.0` | Plotter Y origin offset (mm) |
