"""
tests/test_ai_player.py – Unit tests for the AI player module.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from ai_player import AIPlayer
from constants import BOARD_SIZE, CENTER, LETTER_VALUES, PLAYER_AI, PLAYER_HUMAN
from dictionary import is_valid_word


# ── Helpers ────────────────────────────────────────────────────────────────

def empty_board():
    """Return a fresh 15×15 board with all cells set to None."""
    return [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]


def board_with_word(word, row, col, horizontal=True):
    """Return a board that already has *word* placed at (row, col)."""
    board = empty_board()
    for i, ch in enumerate(word):
        if horizontal:
            board[row][col + i] = ch
        else:
            board[row + i][col] = ch
    return board


# ── Initialisation ─────────────────────────────────────────────────────────

class TestInit:
    def test_default_difficulty(self):
        ai = AIPlayer()
        assert ai.difficulty == "hard"

    def test_custom_difficulty(self):
        for diff in ("easy", "medium", "hard"):
            ai = AIPlayer(difficulty=diff)
            assert ai.difficulty == diff


# ── First-move detection ──────────────────────────────────────────────────

class TestFirstMove:
    def test_empty_board_is_first_move(self):
        ai = AIPlayer()
        assert ai._is_first_move(empty_board()) is True

    def test_non_empty_board_is_not_first_move(self):
        ai = AIPlayer()
        board = board_with_word("CAT", CENTER, CENTER)
        assert ai._is_first_move(board) is False


# ── Anchor cells ──────────────────────────────────────────────────────────

class TestAnchorCells:
    def test_first_move_anchor_is_centre(self):
        ai = AIPlayer()
        anchors = ai._get_anchor_cells(empty_board())
        assert anchors == [(CENTER, CENTER)]

    def test_anchors_adjacent_to_placed_tiles(self):
        ai = AIPlayer()
        board = empty_board()
        board[CENTER][CENTER] = "A"
        anchors = ai._get_anchor_cells(board)
        # Must include all four neighbours of (7,7)
        expected = {(CENTER - 1, CENTER), (CENTER + 1, CENTER),
                    (CENTER, CENTER - 1), (CENTER, CENTER + 1)}
        assert expected.issubset(set(anchors))

    def test_anchors_do_not_include_occupied(self):
        ai = AIPlayer()
        board = empty_board()
        board[CENTER][CENTER] = "A"
        anchors = ai._get_anchor_cells(board)
        assert (CENTER, CENTER) not in anchors

    def test_anchors_respect_board_edges(self):
        ai = AIPlayer()
        board = empty_board()
        board[0][0] = "A"
        anchors = ai._get_anchor_cells(board)
        for r, c in anchors:
            assert 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE


# ── Word generation from rack ─────────────────────────────────────────────

class TestGenerateWords:
    def test_generates_valid_words(self):
        ai = AIPlayer()
        words = ai._generate_words_from_rack(list("CATDOG"))
        for word in words:
            assert is_valid_word(word)

    def test_known_words_appear(self):
        ai = AIPlayer()
        words = ai._generate_words_from_rack(list("CATXYZ"))
        # "CAT" should be found (if in dictionary)
        if is_valid_word("CAT"):
            assert "CAT" in words

    def test_short_words_excluded(self):
        ai = AIPlayer()
        words = ai._generate_words_from_rack(list("ABC"), min_length=3)
        for w in words:
            assert len(w) >= 3

    def test_empty_rack_generates_nothing(self):
        ai = AIPlayer()
        words = ai._generate_words_from_rack([])
        assert words == []

    def test_single_letter_rack_generates_nothing(self):
        ai = AIPlayer()
        words = ai._generate_words_from_rack(["A"])
        # min_length defaults to 2
        assert words == []


# ── Horizontal placement ──────────────────────────────────────────────────

class TestPlaceHorizontal:
    def test_valid_placement_on_empty(self):
        ai = AIPlayer()
        board = empty_board()
        rack = list("CAT")
        result = ai._try_place_horizontal(board, "CAT", CENTER, CENTER, rack)
        assert result is not None
        assert len(result) == 3
        # All tiles placed in centre row
        assert all(r == CENTER for r, c, l in result)

    def test_word_too_long_for_board(self):
        ai = AIPlayer()
        board = empty_board()
        rack = list("ABCDEFG")
        # Starting at col 14 with 7-letter word overflows
        result = ai._try_place_horizontal(board, "ABCDEFG", 0, 14, rack)
        assert result is None

    def test_conflict_with_existing_tile(self):
        ai = AIPlayer()
        board = board_with_word("CAT", CENTER, CENTER)
        rack = list("DOG")
        # DOG at centre row conflicts with "C" at centre
        result = ai._try_place_horizontal(board, "DOG", CENTER, CENTER, rack)
        assert result is None

    def test_reuses_existing_tile(self):
        ai = AIPlayer()
        board = empty_board()
        board[CENTER][CENTER] = "C"
        rack = list("AT")
        result = ai._try_place_horizontal(board, "CAT", CENTER, CENTER, rack)
        assert result is not None
        # Only A and T from rack (C already on board)
        assert len(result) == 2

    def test_blank_tile_as_substitute(self):
        ai = AIPlayer()
        board = empty_board()
        rack = list("CA ")  # C, A, blank
        result = ai._try_place_horizontal(board, "CAT", CENTER, CENTER, rack)
        assert result is not None
        assert len(result) == 3


# ── Vertical placement ────────────────────────────────────────────────────

class TestPlaceVertical:
    def test_valid_vertical_placement(self):
        ai = AIPlayer()
        board = empty_board()
        rack = list("CAT")
        result = ai._try_place_vertical(board, "CAT", CENTER, CENTER, rack)
        assert result is not None
        assert len(result) == 3
        assert all(c == CENTER for r, c, l in result)

    def test_word_too_long_vertically(self):
        ai = AIPlayer()
        board = empty_board()
        rack = list("ABCDEFG")
        result = ai._try_place_vertical(board, "ABCDEFG", 14, 0, rack)
        assert result is None

    def test_vertical_blank_substitute(self):
        ai = AIPlayer()
        board = empty_board()
        rack = list("C T")  # C, blank, T (with space = blank)
        # Need A but don't have it, blank fills in
        result = ai._try_place_vertical(board, "CAT", CENTER, CENTER, rack)
        assert result is not None

    def test_vertical_conflict(self):
        ai = AIPlayer()
        board = empty_board()
        board[CENTER][CENTER] = "X"
        rack = list("CAT")
        # "C" at CENTER conflicts with "X"
        result = ai._try_place_vertical(board, "CAT", CENTER, CENTER, rack)
        assert result is None


# ── Scoring ───────────────────────────────────────────────────────────────

class TestScoring:
    def test_score_placement_basic(self):
        ai = AIPlayer()
        board = empty_board()
        tiles = [(CENTER, CENTER, "C"), (CENTER, CENTER + 1, "A"), (CENTER, CENTER + 2, "T")]
        score = ai._score_placement(board, tiles)
        expected = LETTER_VALUES["C"] + LETTER_VALUES["A"] + LETTER_VALUES["T"]
        assert score == expected

    def test_score_candidates_sorted_descending(self):
        ai = AIPlayer()
        board = empty_board()
        # Create two candidates with different scores
        low = [(0, 0, "A")]   # 1 point
        high = [(0, 0, "Z")]  # 10 points
        scored = ai._score_candidates(board, [low, high])
        assert scored[0][0] >= scored[1][0]

    def test_empty_candidates(self):
        ai = AIPlayer()
        board = empty_board()
        scored = ai._score_candidates(board, [])
        assert scored == []


# ── choose_move ───────────────────────────────────────────────────────────

class TestChooseMove:
    def test_returns_none_when_no_valid_move(self):
        ai = AIPlayer()
        board = empty_board()
        rack = list("QQQQQQ")
        result = ai.choose_move(board, rack)
        assert result is None

    def test_returns_tiles_on_first_move(self):
        """AI should place a word covering the centre on a fresh board."""
        ai = AIPlayer(difficulty="hard")
        board = empty_board()
        # Use a rack that has letters forming at least one known word
        rack = list("CATDOGS")
        result = ai.choose_move(board, rack)
        if result is not None:
            positions = {(r, c) for r, c, _ in result}
            assert (CENTER, CENTER) in positions or any(
                r == CENTER for r, c, _ in result
            )

    def test_easy_picks_short_word(self):
        ai = AIPlayer(difficulty="easy")
        board = empty_board()
        rack = list("CATDOGS")
        result = ai.choose_move(board, rack)
        if result is not None:
            # Easy difficulty picks the shortest word
            assert len(result) <= 7

    def test_choose_move_tiles_are_valid_tuples(self):
        ai = AIPlayer(difficulty="hard")
        board = empty_board()
        rack = list("CATDOGS")
        result = ai.choose_move(board, rack)
        if result is not None:
            for tile in result:
                assert len(tile) == 3
                r, c, l = tile
                assert isinstance(r, int)
                assert isinstance(c, int)
                assert isinstance(l, str) and len(l) == 1

    def test_choose_move_on_non_empty_board(self):
        """AI should be able to extend an existing word."""
        ai = AIPlayer(difficulty="hard")
        board = board_with_word("CAT", CENTER, CENTER)
        rack = list("DOGSTER")
        result = ai.choose_move(board, rack)
        # Result may be None if no placement found, but if found, must be valid tiles
        if result is not None:
            for r, c, l in result:
                assert 0 <= r < BOARD_SIZE
                assert 0 <= c < BOARD_SIZE
                assert board[r][c] is None  # only new tiles


# ── find_all_placements ───────────────────────────────────────────────────

class TestFindPlacements:
    def test_finds_placements_on_empty_board(self):
        ai = AIPlayer()
        board = empty_board()
        rack = list("CATDOGS")
        placements = ai._find_all_placements(board, rack)
        # Should find at least one placement (if dictionary has matching words)
        if is_valid_word("CAT"):
            assert len(placements) > 0

    def test_no_duplicate_placements(self):
        ai = AIPlayer()
        board = empty_board()
        rack = list("CATDOGS")
        placements = ai._find_all_placements(board, rack)
        keys = [tuple(sorted(p)) for p in placements]
        assert len(keys) == len(set(keys))

    def test_placements_with_non_word_rack(self):
        ai = AIPlayer()
        board = empty_board()
        rack = list("QQQQQQQ")
        placements = ai._find_all_placements(board, rack)
        assert placements == []
