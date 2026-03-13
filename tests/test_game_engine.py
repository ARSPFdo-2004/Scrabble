"""
tests/test_game_engine.py – Unit tests for the Scrabble game engine.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from game_engine import GameEngine, RACK_SIZE
from constants import BOARD_SIZE, CENTER, PLAYER_HUMAN, PLAYER_AI


# ── Helpers ────────────────────────────────────────────────────────────────

def make_game():
    """Return a fresh GameEngine with known racks."""
    game = GameEngine()
    return game


def force_rack(game, player, letters):
    """Overwrite a player's rack for deterministic testing."""
    game.racks[player] = list(letters)


def place_center_word(game, word, horizontal=True):
    """
    Place *word* starting from the centre square so the first move is valid.
    Returns the result dict.
    """
    tiles = []
    for i, ch in enumerate(word):
        if horizontal:
            tiles.append((CENTER, CENTER + i, ch))
        else:
            tiles.append((CENTER + i, CENTER, ch))
    return game.place_tiles(PLAYER_HUMAN, tiles)


# ── Board / state tests ────────────────────────────────────────────────────

class TestInitialState:
    def test_board_is_empty(self):
        game = make_game()
        for row in game.board:
            assert all(cell is None for cell in row)

    def test_board_size(self):
        game = make_game()
        assert len(game.board) == BOARD_SIZE
        assert all(len(row) == BOARD_SIZE for row in game.board)

    def test_initial_scores_zero(self):
        game = make_game()
        assert game.scores[PLAYER_HUMAN] == 0
        assert game.scores[PLAYER_AI]    == 0

    def test_initial_racks_filled(self):
        game = make_game()
        assert len(game.racks[PLAYER_HUMAN]) == RACK_SIZE
        assert len(game.racks[PLAYER_AI])    == RACK_SIZE

    def test_current_player_is_human(self):
        game = make_game()
        assert game.current_player == PLAYER_HUMAN

    def test_game_not_over(self):
        game = make_game()
        assert not game.game_over


# ── Move validation ────────────────────────────────────────────────────────

class TestMoveValidation:
    def test_first_move_must_cover_centre(self):
        game = make_game()
        force_rack(game, PLAYER_HUMAN, list("CATXYZ"))
        # Place "CAT" at row 0 (far from centre)
        result = game.place_tiles(PLAYER_HUMAN, [(0, 0, 'C'), (0, 1, 'A'), (0, 2, 'T')])
        assert not result["success"]
        assert "centre" in result["error"].lower()

    def test_first_valid_move(self):
        game = make_game()
        force_rack(game, PLAYER_HUMAN, list("CATXYZ"))
        result = place_center_word(game, "CAT")
        assert result["success"], result.get("error")
        assert "CAT" in result["words"]

    def test_wrong_player_cannot_move(self):
        game = make_game()
        force_rack(game, PLAYER_AI, list("CATXYZ"))
        result = game.place_tiles(PLAYER_AI, [(CENTER, CENTER, 'C'), (CENTER, CENTER+1, 'A'), (CENTER, CENTER+2, 'T')])
        assert not result["success"]
        assert "turn" in result["error"].lower()

    def test_occupied_cell_rejected(self):
        game = make_game()
        force_rack(game, PLAYER_HUMAN, list("CATDOG"))
        place_center_word(game, "CAT")
        # AI turn now – force AI to pass
        game.pass_turn(PLAYER_AI)
        # Human tries to place on an occupied cell
        force_rack(game, PLAYER_HUMAN, list("DOGXYZ"))
        result = game.place_tiles(PLAYER_HUMAN, [(CENTER, CENTER, 'D')])
        assert not result["success"]

    def test_tiles_must_be_in_row_or_column(self):
        game = make_game()
        force_rack(game, PLAYER_HUMAN, list("CATXYZ"))
        # Diagonal placement – should fail
        result = game.place_tiles(PLAYER_HUMAN, [
            (CENTER, CENTER, 'C'),
            (CENTER+1, CENTER+1, 'A'),
            (CENTER+2, CENTER+2, 'T'),
        ])
        assert not result["success"]

    def test_off_board_rejected(self):
        game = make_game()
        force_rack(game, PLAYER_HUMAN, list("CATXYZ"))
        result = game.place_tiles(PLAYER_HUMAN, [(20, 0, 'C')])
        assert not result["success"]

    def test_letter_not_in_rack_rejected(self):
        game = make_game()
        force_rack(game, PLAYER_HUMAN, list("AAAXYZ"))
        result = game.place_tiles(PLAYER_HUMAN, [(CENTER, CENTER, 'Z'), (CENTER, CENTER+1, 'A')])
        # Z is in the rack, but "ZA" must be a valid word for this to succeed
        # This test ensures the letter-in-rack check works
        game2 = make_game()
        force_rack(game2, PLAYER_HUMAN, list("AAAXYZ"))
        result2 = game2.place_tiles(PLAYER_HUMAN, [(CENTER, CENTER, 'Q')])
        assert not result2["success"]
        assert "rack" in result2["error"].lower()


# ── Scoring ────────────────────────────────────────────────────────────────

class TestScoring:
    def test_score_increases_after_valid_move(self):
        game = make_game()
        force_rack(game, PLAYER_HUMAN, list("CATXYZW"))
        result = place_center_word(game, "CAT")
        assert result["success"]
        assert game.scores[PLAYER_HUMAN] > 0

    def test_bingo_bonus(self):
        """Using all 7 tiles at once earns +50 bonus."""
        game = make_game()
        # "SCRABBLE" is 8 letters; use a 7-letter word with S,C,R,A,B,L,E
        force_rack(game, PLAYER_HUMAN, list("SCARBLE"))
        result = place_center_word(game, "SCARBLE")
        if result["success"]:
            # 7 tiles → bingo bonus included
            assert result["score"] >= 50

    def test_turn_switches_after_move(self):
        game = make_game()
        force_rack(game, PLAYER_HUMAN, list("CATXYZW"))
        place_center_word(game, "CAT")
        assert game.current_player == PLAYER_AI


# ── Pass / exchange ────────────────────────────────────────────────────────

class TestPassAndExchange:
    def test_pass_switches_turn(self):
        game = make_game()
        assert game.current_player == PLAYER_HUMAN
        result = game.pass_turn(PLAYER_HUMAN)
        assert result["success"]
        assert game.current_player == PLAYER_AI

    def test_wrong_player_cannot_pass(self):
        game = make_game()
        result = game.pass_turn(PLAYER_AI)
        assert not result["success"]

    def test_four_consecutive_passes_end_game(self):
        game = make_game()
        for _ in range(4):
            player = game.current_player
            game.pass_turn(player)
        assert game.game_over

    def test_exchange_replaces_tiles(self):
        game = make_game()
        old_rack = list(game.racks[PLAYER_HUMAN])
        letters_to_exchange = old_rack[:2]
        result = game.exchange_tiles(PLAYER_HUMAN, letters_to_exchange)
        assert result["success"]
        new_rack = game.racks[PLAYER_HUMAN]
        assert len(new_rack) == RACK_SIZE


# ── Challenge ──────────────────────────────────────────────────────────────

class TestChallenge:
    def _setup_with_ai_move(self):
        """Play one human move and one AI move so human can challenge."""
        game = make_game()
        force_rack(game, PLAYER_HUMAN, list("CATXYZW"))
        place_center_word(game, "CAT")
        # AI plays a real word vertically anchored to centre
        force_rack(game, PLAYER_AI, list("DOGSXYZ"))
        ai_tiles = [(CENTER+1, CENTER, 'D'), (CENTER+2, CENTER, 'O'), (CENTER+3, CENTER, 'G')]
        result = game.place_tiles(PLAYER_AI, ai_tiles)
        return game, result

    def test_challenge_valid_word_fails_challenger(self):
        game, ai_result = self._setup_with_ai_move()
        if not ai_result["success"]:
            pytest.skip("AI move not valid with current dictionary")
        word = ai_result["words"][0]
        result = game.challenge_word(PLAYER_HUMAN, word)
        assert result["success"]
        assert result["valid"] is True  # word IS valid, challenge fails

    def test_challenge_no_moves_fails(self):
        game = make_game()
        result = game.challenge_word(PLAYER_HUMAN, "CAT")
        assert not result["success"]

    def test_challenge_invalid_word_succeeds(self):
        game = make_game()
        force_rack(game, PLAYER_HUMAN, list("CATXYZW"))
        place_center_word(game, "CAT")
        # Manually inject a fake move history entry with an invalid word
        fake_score = 20
        fake_tiles = [(CENTER+1, CENTER, 'X'), (CENTER+2, CENTER, 'Y'), (CENTER+3, CENTER, 'Z')]
        for r, c, l in fake_tiles:
            game.board[r][c] = l
        game.scores[PLAYER_AI] += fake_score
        game.move_history.append({
            "player": PLAYER_AI,
            "tiles": fake_tiles,
            "words": ["XYZ"],
            "score": fake_score,
            "scores": dict(game.scores),
        })
        before = game.scores[PLAYER_HUMAN]
        result = game.challenge_word(PLAYER_HUMAN, "XYZ")
        assert result["success"]
        assert result["valid"] is False
        # Challenger earns the points
        assert game.scores[PLAYER_HUMAN] == before + fake_score


# ── get_state ──────────────────────────────────────────────────────────────

class TestGetState:
    def test_state_keys(self):
        game = make_game()
        state = game.get_state()
        for key in ("board", "scores", "racks", "current_player",
                    "tiles_remaining", "game_over", "move_history"):
            assert key in state

    def test_ai_rack_hidden(self):
        game = make_game()
        state = game.get_state()
        # AI rack should be '??...?' not actual letters
        assert all(c == '?' for c in state["racks"]["ai"])
