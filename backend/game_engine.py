"""
game_engine.py – Scrabble game logic: board state, move validation, scoring,
turn management, and challenge handling.
"""

import random
import logging
from typing import List, Optional, Tuple, Dict, Any

from constants import (
    BOARD_SIZE, CENTER, BOARD_LAYOUT,
    LETTER_VALUES, TILE_DISTRIBUTION,
    DOUBLE_LETTER, TRIPLE_LETTER, DOUBLE_WORD, TRIPLE_WORD, NORMAL,
    PLAYER_HUMAN, PLAYER_AI,
)
from dictionary import is_valid_word

logger = logging.getLogger(__name__)

# Rack size
RACK_SIZE = 7


class GameEngine:
    """Manages the full state of a two-player Scrabble game."""

    def __init__(self):
        self.board: List[List[Optional[str]]] = [
            [None] * BOARD_SIZE for _ in range(BOARD_SIZE)
        ]
        self.scores: Dict[str, int] = {PLAYER_HUMAN: 0, PLAYER_AI: 0}
        self.racks: Dict[str, List[str]] = {PLAYER_HUMAN: [], PLAYER_AI: []}
        self.bag: List[str] = self._build_bag()
        self.current_player: str = PLAYER_HUMAN
        self.move_history: List[Dict[str, Any]] = []
        self.game_over: bool = False
        self.last_placed_word: Optional[str] = None
        self.last_placed_tiles: List[Tuple[int, int, str]] = []
        self.consecutive_passes: int = 0

        # Fill initial racks
        self._refill_rack(PLAYER_HUMAN)
        self._refill_rack(PLAYER_AI)

    # ------------------------------------------------------------------
    # Bag / rack helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_bag() -> List[str]:
        bag: List[str] = []
        for letter, count in TILE_DISTRIBUTION.items():
            bag.extend([letter] * count)
        random.shuffle(bag)
        return bag

    def _refill_rack(self, player: str) -> None:
        rack = self.racks[player]
        while len(rack) < RACK_SIZE and self.bag:
            rack.append(self.bag.pop())

    def tiles_remaining(self) -> int:
        return len(self.bag)

    # ------------------------------------------------------------------
    # Move validation
    # ------------------------------------------------------------------

    def _is_first_move(self) -> bool:
        return all(self.board[r][c] is None for r in range(BOARD_SIZE) for c in range(BOARD_SIZE))

    def _cells_connected(self, tiles: List[Tuple[int, int, str]]) -> bool:
        """Return True if the placed tiles are in a single row or column."""
        rows = {r for r, _, _ in tiles}
        cols = {c for _, c, _ in tiles}
        return len(rows) == 1 or len(cols) == 1

    def _get_word_at(self, row: int, col: int, horizontal: bool) -> Tuple[str, List[Tuple[int, int]]]:
        """Extract the full word touching (row, col) in the given direction."""
        if horizontal:
            c = col
            while c > 0 and self.board[row][c - 1] is not None:
                c -= 1
            word, positions = [], []
            while c < BOARD_SIZE and self.board[row][c] is not None:
                word.append(self.board[row][c])
                positions.append((row, c))
                c += 1
        else:
            r = row
            while r > 0 and self.board[r - 1][col] is not None:
                r -= 1
            word, positions = [], []
            while r < BOARD_SIZE and self.board[r][col] is not None:
                word.append(self.board[r][col])
                positions.append((r, col))
                r += 1
        return "".join(word), positions

    def _all_words_from_placement(self, tiles: List[Tuple[int, int, str]]) -> List[Tuple[str, List[Tuple[int, int]]]]:
        """Return all words created by placing *tiles* on the board."""
        rows = {r for r, _, _ in tiles}
        cols = {c for _, c, _ in tiles}
        words = []
        seen = set()

        if len(rows) == 1:
            # Primary direction is horizontal
            r = next(iter(rows))
            c_min = min(cols)
            word, positions = self._get_word_at(r, c_min, horizontal=True)
            key = tuple(positions)
            if len(word) > 1 and key not in seen:
                seen.add(key)
                words.append((word, positions))
            # Cross words (vertical)
            for r2, c2, _ in tiles:
                word2, pos2 = self._get_word_at(r2, c2, horizontal=False)
                key2 = tuple(pos2)
                if len(word2) > 1 and key2 not in seen:
                    seen.add(key2)
                    words.append((word2, pos2))
        else:
            # Primary direction is vertical
            c = next(iter(cols))
            r_min = min(rows)
            word, positions = self._get_word_at(r_min, c, horizontal=False)
            key = tuple(positions)
            if len(word) > 1 and key not in seen:
                seen.add(key)
                words.append((word, positions))
            # Cross words (horizontal)
            for r2, c2, _ in tiles:
                word2, pos2 = self._get_word_at(r2, c2, horizontal=True)
                key2 = tuple(pos2)
                if len(word2) > 1 and key2 not in seen:
                    seen.add(key2)
                    words.append((word2, pos2))
        return words

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _score_word(self, positions: List[Tuple[int, int]], new_positions: set) -> int:
        """Score a single word; apply multipliers only for newly placed tiles."""
        word_multiplier = 1
        word_score = 0
        for r, c in positions:
            letter = self.board[r][c]
            letter_val = LETTER_VALUES.get(letter, 0)
            sq = BOARD_LAYOUT[r][c] if (r, c) in new_positions else NORMAL
            if sq == DOUBLE_LETTER:
                letter_val *= 2
            elif sq == TRIPLE_LETTER:
                letter_val *= 3
            elif sq == DOUBLE_WORD:
                word_multiplier *= 2
            elif sq == TRIPLE_WORD:
                word_multiplier *= 3
            word_score += letter_val
        return word_score * word_multiplier

    # ------------------------------------------------------------------
    # Public move API
    # ------------------------------------------------------------------

    def place_tiles(
        self,
        player: str,
        tiles: List[Tuple[int, int, str]],
    ) -> Dict[str, Any]:
        """
        Place *tiles* on the board for *player*.

        tiles: list of (row, col, letter) tuples.

        Returns a result dict with keys:
            success (bool), words (list[str]), score (int), error (str|None)
        """
        if self.game_over:
            return {"success": False, "error": "Game is over", "words": [], "score": 0}
        if player != self.current_player:
            return {"success": False, "error": "Not your turn", "words": [], "score": 0}

        # Basic validation
        if not tiles:
            return {"success": False, "error": "No tiles provided", "words": [], "score": 0}
        if not self._cells_connected(tiles):
            return {"success": False, "error": "Tiles must be in a single row or column", "words": [], "score": 0}

        # Check placement cells are empty
        for r, c, letter in tiles:
            if not (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE):
                return {"success": False, "error": f"Cell ({r},{c}) is off the board", "words": [], "score": 0}
            if self.board[r][c] is not None:
                return {"success": False, "error": f"Cell ({r},{c}) is already occupied", "words": [], "score": 0}

        # First move must cover centre
        if self._is_first_move():
            centres = {(r, c) for r, c, _ in tiles}
            if (CENTER, CENTER) not in centres:
                return {"success": False, "error": "First move must cover the centre square", "words": [], "score": 0}

        # Check player has required letters
        rack = list(self.racks[player])
        for _, _, letter in tiles:
            if letter in rack:
                rack.remove(letter)
            elif ' ' in rack:   # blank tile
                rack.remove(' ')
            else:
                return {"success": False, "error": f"Letter '{letter}' not in rack", "words": [], "score": 0}

        # Place tiles temporarily
        new_positions = set()
        for r, c, letter in tiles:
            self.board[r][c] = letter
            new_positions.add((r, c))

        # Gather formed words
        formed = self._all_words_from_placement(tiles)
        if not formed:
            # Undo
            for r, c, _ in tiles:
                self.board[r][c] = None
            return {"success": False, "error": "No valid word formed", "words": [], "score": 0}

        # Validate all words
        for word, _ in formed:
            if not is_valid_word(word):
                for r, c, _ in tiles:
                    self.board[r][c] = None
                return {"success": False, "error": f"'{word}' is not a valid word", "words": [], "score": 0}

        # Score
        total_score = sum(self._score_word(pos, new_positions) for _, pos in formed)
        if len(tiles) == RACK_SIZE:
            total_score += 50  # Bingo bonus

        # Commit
        self.scores[player] += total_score
        self.racks[player] = rack
        self._refill_rack(player)
        self.consecutive_passes = 0

        word_strings = [w for w, _ in formed]
        self.last_placed_word = word_strings[0] if word_strings else None
        self.last_placed_tiles = tiles

        record = {
            "player": player,
            "tiles": tiles,
            "words": word_strings,
            "score": total_score,
            "scores": dict(self.scores),
        }
        self.move_history.append(record)
        logger.info("Player %s placed %s for %d points", player, word_strings, total_score)

        self._switch_turn()
        self._check_game_over()
        return {"success": True, "words": word_strings, "score": total_score, "error": None}

    def pass_turn(self, player: str) -> Dict[str, Any]:
        """Player passes their turn."""
        if player != self.current_player:
            return {"success": False, "error": "Not your turn"}
        self.consecutive_passes += 1
        self.move_history.append({"player": player, "action": "pass", "scores": dict(self.scores)})
        self._switch_turn()
        self._check_game_over()
        return {"success": True}

    def exchange_tiles(self, player: str, letters: List[str]) -> Dict[str, Any]:
        """Exchange tiles from the rack with new ones from the bag."""
        if player != self.current_player:
            return {"success": False, "error": "Not your turn"}
        if len(self.bag) < len(letters):
            return {"success": False, "error": "Not enough tiles in bag"}
        rack = self.racks[player]
        new_rack = list(rack)
        returned = []
        for letter in letters:
            if letter in new_rack:
                new_rack.remove(letter)
                returned.append(letter)
            else:
                return {"success": False, "error": f"Letter '{letter}' not in rack"}
        # Draw new tiles first, then return old ones
        drawn = [self.bag.pop() for _ in range(len(returned))]
        new_rack.extend(drawn)
        self.bag.extend(returned)
        random.shuffle(self.bag)
        self.racks[player] = new_rack
        self.consecutive_passes += 1
        self._switch_turn()
        self._check_game_over()
        return {"success": True, "new_rack": new_rack}

    # ------------------------------------------------------------------
    # Challenge
    # ------------------------------------------------------------------

    def challenge_word(self, challenging_player: str, word: str) -> Dict[str, Any]:
        """
        Challenge a word placed by the opponent.

        If the word is invalid, the opponent's last move is undone and the
        challenging player earns the points.  If the word is valid, the
        challenging player loses their turn.
        """
        opponent = PLAYER_AI if challenging_player == PLAYER_HUMAN else PLAYER_HUMAN

        if not self.move_history:
            return {"success": False, "error": "No moves to challenge"}

        last_move = self.move_history[-1]
        if last_move.get("player") != opponent:
            return {"success": False, "error": "Can only challenge the opponent's last move"}

        if is_valid_word(word):
            # Challenge fails – challenger loses turn
            self.move_history.append({
                "player": challenging_player,
                "action": "challenge_failed",
                "word": word,
                "scores": dict(self.scores),
            })
            self._switch_turn()
            return {
                "success": True,
                "valid": True,
                "message": f"'{word}' is valid. Challenge failed – you lose your turn.",
            }
        else:
            # Challenge succeeds – undo opponent's last move
            lost_score = last_move.get("score", 0)
            self.scores[opponent] = max(0, self.scores[opponent] - lost_score)
            # Remove tiles from board
            for r, c, _ in last_move.get("tiles", []):
                self.board[r][c] = None
            # Return tiles to opponent's rack
            for _, _, letter in last_move.get("tiles", []):
                self.racks[opponent].append(letter)
            self.move_history.pop()
            self.move_history.append({
                "player": challenging_player,
                "action": "challenge_succeeded",
                "word": word,
                "scores": dict(self.scores),
            })
            # Challenger earns the points that were scored
            self.scores[challenging_player] += lost_score
            return {
                "success": True,
                "valid": False,
                "message": f"'{word}' is not valid. Challenge succeeded! You earn {lost_score} points.",
                "points_awarded": lost_score,
            }

    # ------------------------------------------------------------------
    # Game state helpers
    # ------------------------------------------------------------------

    def _switch_turn(self) -> None:
        self.current_player = PLAYER_AI if self.current_player == PLAYER_HUMAN else PLAYER_HUMAN

    def _check_game_over(self) -> None:
        if self.consecutive_passes >= 4:
            self.game_over = True
            logger.info("Game over – 4 consecutive passes")
            return
        # Game over when a player empties their rack AND bag is empty
        for player in (PLAYER_HUMAN, PLAYER_AI):
            if not self.racks[player] and not self.bag:
                self.game_over = True
                logger.info("Game over – %s emptied rack", player)
                return

    def get_state(self) -> Dict[str, Any]:
        """Return a serialisable snapshot of the current game state."""
        return {
            "board": self.board,
            "scores": self.scores,
            "racks": {
                PLAYER_HUMAN: self.racks[PLAYER_HUMAN],
                PLAYER_AI: "?" * len(self.racks[PLAYER_AI]),  # hide AI tiles from client
            },
            "current_player": self.current_player,
            "tiles_remaining": self.tiles_remaining(),
            "game_over": self.game_over,
            "move_history": self.move_history[-10:],  # last 10 moves
            "last_placed_word": self.last_placed_word,
            "last_placed_tiles": [list(t) for t in self.last_placed_tiles],
            "board_layout": BOARD_LAYOUT,
        }

    def update_board_from_scan(self, scanned_board: List[List[Optional[str]]]) -> None:
        """Overwrite the internal board with data from the OpenCV scanner."""
        self.board = scanned_board
