"""
ai_player.py – AI player logic for the Scrabble automation system.

The AI searches for the highest-scoring word it can form from its rack
that fits on the current board, using a simple but effective strategy:
  1. Generate candidate words from the rack letters.
  2. Try to anchor each candidate to an existing tile on the board.
  3. Score all valid placements and pick the best one.
"""

import itertools
import logging
import random
from typing import Dict, List, Optional, Tuple

from constants import BOARD_SIZE, CENTER, LETTER_VALUES, PLAYER_AI
from dictionary import is_valid_word

logger = logging.getLogger(__name__)


class AIPlayer:
    """
    Generates the best possible move for the AI player.

    Parameters
    ----------
    difficulty : str
        'easy'   – picks a random valid word (short)
        'medium' – picks a valid word with above-average score
        'hard'   – picks the highest-scoring valid placement (default)
    """

    def __init__(self, difficulty: str = "hard"):
        self.difficulty = difficulty

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def choose_move(
        self,
        board: List[List[Optional[str]]],
        rack: List[str],
    ) -> Optional[List[Tuple[int, int, str]]]:
        """
        Return a list of (row, col, letter) tuples representing the best
        move, or None if no valid placement was found.
        """
        candidates = self._find_all_placements(board, rack)
        if not candidates:
            logger.info("AI: no valid placement found – will pass")
            return None

        if self.difficulty == "easy":
            # Pick the shortest word
            candidates.sort(key=lambda x: len(x))
            return candidates[0]
        elif self.difficulty == "medium":
            # Pick a random candidate from the top half by score
            scored = self._score_candidates(board, candidates)
            half = max(1, len(scored) // 2)
            top_half = scored[:half]
            return random.choice(top_half)[1]
        else:
            # Hard – highest score
            scored = self._score_candidates(board, candidates)
            return scored[0][1]

    # ------------------------------------------------------------------
    # Candidate generation
    # ------------------------------------------------------------------

    def _is_first_move(self, board: List[List[Optional[str]]]) -> bool:
        return all(board[r][c] is None for r in range(BOARD_SIZE) for c in range(BOARD_SIZE))

    def _get_anchor_cells(self, board: List[List[Optional[str]]]) -> List[Tuple[int, int]]:
        """
        Return cells adjacent to existing tiles (or the centre for the
        first move) where a new word can start.
        """
        if self._is_first_move(board):
            return [(CENTER, CENTER)]

        anchors = set()
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if board[r][c] is not None:
                    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE and board[nr][nc] is None:
                            anchors.add((nr, nc))
        return list(anchors)

    def _generate_words_from_rack(self, rack: List[str], min_length: int = 2) -> List[str]:
        """Generate all valid words that can be formed from *rack*."""
        words = set()
        letters = rack[:]
        # Replace blanks with all possible letters
        has_blank = ' ' in letters
        non_blank = [l for l in letters if l != ' ']

        max_len = min(len(letters), 7)
        for length in range(min_length, max_len + 1):
            for perm in itertools.permutations(non_blank, length):
                word = "".join(perm)
                if is_valid_word(word):
                    words.add(word)
            if has_blank:
                for sub_length in range(min_length, length + 1):
                    for perm in itertools.permutations(non_blank, sub_length - 1):
                        for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                            word = "".join(perm) + ch
                            if is_valid_word(word):
                                words.add(word)
        return list(words)

    def _try_place_horizontal(
        self,
        board: List[List[Optional[str]]],
        word: str,
        row: int,
        col: int,
        rack: List[str],
    ) -> Optional[List[Tuple[int, int, str]]]:
        """
        Try to place *word* horizontally starting at (row, col).
        Returns the list of (row, col, letter) tiles needed, or None.
        """
        if col + len(word) > BOARD_SIZE:
            return None
        tiles = []
        rack_copy = list(rack)
        for i, ch in enumerate(word):
            c = col + i
            existing = board[row][c]
            if existing is not None:
                if existing != ch:
                    return None  # conflicts with existing tile
                # No tile needed from rack
            else:
                if ch in rack_copy:
                    rack_copy.remove(ch)
                    tiles.append((row, c, ch))
                elif ' ' in rack_copy:
                    rack_copy.remove(' ')
                    tiles.append((row, c, ch))
                else:
                    return None
        return tiles if tiles else None

    def _try_place_vertical(
        self,
        board: List[List[Optional[str]]],
        word: str,
        row: int,
        col: int,
        rack: List[str],
    ) -> Optional[List[Tuple[int, int, str]]]:
        """
        Try to place *word* vertically starting at (row, col).
        Returns the list of (row, col, letter) tiles needed, or None.
        """
        if row + len(word) > BOARD_SIZE:
            return None
        tiles = []
        rack_copy = list(rack)
        for i, ch in enumerate(word):
            r = row + i
            existing = board[r][col]
            if existing is not None:
                if existing != ch:
                    return None
            else:
                if ch in rack_copy:
                    rack_copy.remove(ch)
                    tiles.append((r, col, ch))
                elif ' ' in rack_copy:
                    rack_copy.remove(' ')
                    tiles.append((r, col, ch))
                else:
                    return None
        return tiles if tiles else None

    def _find_all_placements(
        self,
        board: List[List[Optional[str]]],
        rack: List[str],
    ) -> List[List[Tuple[int, int, str]]]:
        """Find all valid tile placements from the current rack."""
        words = self._generate_words_from_rack(rack)
        anchors = self._get_anchor_cells(board)
        placements = []

        for word in words:
            for ar, ac in anchors:
                # Try horizontal placements that cover the anchor
                for start_col in range(max(0, ac - len(word) + 1), min(ac + 1, BOARD_SIZE)):
                    result = self._try_place_horizontal(board, word, ar, start_col, rack)
                    if result:
                        # Ensure at least one tile covers the anchor
                        positions = {(r, c) for r, c, _ in result}
                        if (ar, ac) in positions or any(
                            board[ar][start_col + i] is not None for i in range(len(word))
                        ):
                            placements.append(result)

                # Try vertical placements
                for start_row in range(max(0, ar - len(word) + 1), min(ar + 1, BOARD_SIZE)):
                    result = self._try_place_vertical(board, word, start_row, ac, rack)
                    if result:
                        positions = {(r, c) for r, c, _ in result}
                        if (ar, ac) in positions or any(
                            board[start_row + i][ac] is not None for i in range(len(word))
                        ):
                            placements.append(result)

        # Deduplicate
        seen = set()
        unique = []
        for placement in placements:
            key = tuple(sorted(placement))
            if key not in seen:
                seen.add(key)
                unique.append(placement)
        return unique

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _score_placement(
        self,
        board: List[List[Optional[str]]],
        tiles: List[Tuple[int, int, str]],
    ) -> int:
        """Estimate the score for a placement (no multipliers for simplicity)."""
        return sum(LETTER_VALUES.get(letter, 0) for _, _, letter in tiles)

    def _score_candidates(
        self,
        board: List[List[Optional[str]]],
        candidates: List[List[Tuple[int, int, str]]],
    ) -> List[Tuple[int, List[Tuple[int, int, str]]]]:
        """Return candidates sorted by estimated score (highest first)."""
        scored = [(self._score_placement(board, c), c) for c in candidates]
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored
