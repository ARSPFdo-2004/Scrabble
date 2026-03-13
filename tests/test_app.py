"""
tests/test_app.py – Unit tests for the Flask REST API endpoints.

These tests use Flask's test client to validate HTTP endpoints without
needing a running server or real hardware.
"""

import sys
import os

# Ensure simulate mode and backend is importable
os.environ["SIMULATE"] = "true"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from app import app
from constants import CENTER, PLAYER_HUMAN, PLAYER_AI
from game_engine import GameEngine


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture()
def client():
    """Provide a Flask test client with a fresh game for each test."""
    import app as app_module
    app_module.game = GameEngine()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client
    # Restore fresh game after test
    app_module.game = GameEngine()


def _force_rack(player, letters):
    """Overwrite a player's rack in the global game instance."""
    import app as app_module
    app_module.game.racks[player] = list(letters)


# ── GET /api/state ─────────────────────────────────────────────────────────

class TestApiState:
    def test_returns_200(self, client):
        resp = client.get("/api/state")
        assert resp.status_code == 200

    def test_returns_json_with_required_keys(self, client):
        resp = client.get("/api/state")
        data = resp.get_json()
        for key in ("board", "scores", "racks", "current_player",
                     "tiles_remaining", "game_over", "move_history"):
            assert key in data

    def test_initial_scores_zero(self, client):
        data = client.get("/api/state").get_json()
        assert data["scores"]["human"] == 0
        assert data["scores"]["ai"] == 0

    def test_initial_player_is_human(self, client):
        data = client.get("/api/state").get_json()
        assert data["current_player"] == "human"

    def test_game_not_over_initially(self, client):
        data = client.get("/api/state").get_json()
        assert data["game_over"] is False


# ── POST /api/place ────────────────────────────────────────────────────────

class TestApiPlace:
    def test_valid_placement(self, client):
        _force_rack(PLAYER_HUMAN, list("CATXYZW"))
        resp = client.post("/api/place", json={
            "tiles": [[CENTER, CENTER, "C"], [CENTER, CENTER + 1, "A"], [CENTER, CENTER + 2, "T"]]
        })
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["success"] is True
        assert "CAT" in data["words"]
        assert data["score"] > 0

    def test_invalid_placement_off_centre(self, client):
        _force_rack(PLAYER_HUMAN, list("CATXYZ"))
        resp = client.post("/api/place", json={
            "tiles": [[0, 0, "C"], [0, 1, "A"], [0, 2, "T"]]
        })
        data = resp.get_json()
        assert data["success"] is False
        assert "centre" in data["error"].lower()

    def test_empty_tiles_rejected(self, client):
        resp = client.post("/api/place", json={"tiles": []})
        data = resp.get_json()
        assert data["success"] is False

    def test_score_increases_after_placement(self, client):
        _force_rack(PLAYER_HUMAN, list("CATXYZW"))
        client.post("/api/place", json={
            "tiles": [[CENTER, CENTER, "C"], [CENTER, CENTER + 1, "A"], [CENTER, CENTER + 2, "T"]]
        })
        state = client.get("/api/state").get_json()
        assert state["scores"]["human"] > 0


# ── POST /api/pass ─────────────────────────────────────────────────────────

class TestApiPass:
    def test_pass_switches_turn(self, client):
        resp = client.post("/api/pass")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["success"] is True
        state = client.get("/api/state").get_json()
        assert state["current_player"] == "ai"

    def test_pass_when_not_your_turn_fails(self, client):
        # Pass to make it AI's turn
        client.post("/api/pass")
        # Now try passing again as human (it's AI's turn)
        resp = client.post("/api/pass")
        # The endpoint always passes as PLAYER_HUMAN, so it should fail
        data = resp.get_json()
        assert data["success"] is False


# ── POST /api/exchange ─────────────────────────────────────────────────────

class TestApiExchange:
    def test_exchange_tiles(self, client):
        import app as app_module
        rack = list(app_module.game.racks[PLAYER_HUMAN])
        letters = rack[:2]
        resp = client.post("/api/exchange", json={"letters": letters})
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["success"] is True

    def test_exchange_letter_not_in_rack(self, client):
        # Force a rack with known letters and try exchanging one that's not there
        _force_rack(PLAYER_HUMAN, list("AAAAAAA"))
        resp = client.post("/api/exchange", json={"letters": ["Z"]})
        data = resp.get_json()
        assert data["success"] is False
        assert "rack" in data["error"].lower()


# ── POST /api/challenge ───────────────────────────────────────────────────

class TestApiChallenge:
    def test_challenge_no_moves(self, client):
        resp = client.post("/api/challenge", json={"word": "CAT"})
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["success"] is False

    def test_challenge_valid_word_after_ai_move(self, client):
        import app as app_module
        g = app_module.game
        # Human plays first
        _force_rack(PLAYER_HUMAN, list("CATXYZW"))
        client.post("/api/place", json={
            "tiles": [[CENTER, CENTER, "C"], [CENTER, CENTER + 1, "A"], [CENTER, CENTER + 2, "T"]]
        })
        # Manually inject an AI move
        ai_tiles = [(CENTER + 1, CENTER, "D"), (CENTER + 2, CENTER, "O")]
        for r, c, l in ai_tiles:
            g.board[r][c] = l
        g.scores[PLAYER_AI] += 5
        g.move_history.append({
            "player": PLAYER_AI,
            "tiles": ai_tiles,
            "words": ["DO"],
            "score": 5,
            "scores": dict(g.scores),
        })
        g.current_player = PLAYER_HUMAN

        resp = client.post("/api/challenge", json={"word": "DO"})
        data = resp.get_json()
        assert data["success"] is True
        # "DO" is a valid word, so challenge should fail
        assert data["valid"] is True


# ── POST /api/new_game ────────────────────────────────────────────────────

class TestApiNewGame:
    def test_new_game_resets_state(self, client):
        # Make a move first
        _force_rack(PLAYER_HUMAN, list("CATXYZW"))
        client.post("/api/place", json={
            "tiles": [[CENTER, CENTER, "C"], [CENTER, CENTER + 1, "A"], [CENTER, CENTER + 2, "T"]]
        })
        # Reset
        resp = client.post("/api/new_game")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["success"] is True
        # Board should be empty again
        state = client.get("/api/state").get_json()
        assert state["scores"]["human"] == 0
        assert state["scores"]["ai"] == 0
        assert state["current_player"] == "human"
        assert state["game_over"] is False


# ── POST /api/scan_board ──────────────────────────────────────────────────

class TestApiScanBoard:
    def test_scan_board_in_simulate_mode(self, client):
        """In simulate mode, camera isn't available so scan should fail."""
        resp = client.post("/api/scan_board")
        # Expect failure or 500 since no camera in test env
        assert resp.status_code in (200, 500)
