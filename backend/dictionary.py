"""
dictionary.py – Word validation using a bundled word list.

The module loads /usr/share/dict/words (Linux) or the small built-in
fallback word list when the system dictionary is not available.
"""

import os
import logging

logger = logging.getLogger(__name__)

_FALLBACK_WORDS = {
    "AA", "AB", "AD", "AE", "AG", "AH", "AI", "AL", "AM", "AN", "AR", "AS",
    "AT", "AW", "AX", "AY", "BA", "BE", "BI", "BO", "BY", "DA", "DE", "DO",
    "ED", "EF", "EH", "EL", "EM", "EN", "ER", "ES", "ET", "EW", "EX", "FA",
    "FE", "GO", "HA", "HE", "HI", "HM", "HO", "ID", "IF", "IN", "IS", "IT",
    "JO", "KA", "KI", "LA", "LI", "LO", "MA", "ME", "MI", "MM", "MO", "MU",
    "MY", "NA", "NE", "NO", "NU", "OD", "OE", "OF", "OH", "OI", "OK", "OM",
    "ON", "OP", "OR", "OS", "OW", "OX", "OY", "PA", "PE", "PI", "PO", "QI",
    "RE", "SH", "SI", "SO", "TA", "TI", "TO", "UH", "UM", "UN", "UP", "US",
    "UT", "WE", "WO", "XI", "XU", "YA", "YE", "YO", "ZA",
    # Common words
    "CAT", "DOG", "WORD", "PLAY", "GAME", "SCORE", "TILE", "BOARD",
    "SCRABBLE", "LETTER", "PLACE", "TURN", "POINT", "RACK",
    "APPLE", "TREE", "HOUSE", "WATER", "STONE", "LIGHT", "DARK",
    "MOON", "SUN", "STAR", "RAIN", "WIND", "FIRE", "EARTH", "AIR",
    "LOVE", "LIFE", "TIME", "MIND", "WORK", "HAND", "HEAD", "DOOR",
    "BOOK", "LINE", "SIDE", "FACE", "FOOT", "ROAD", "ROOM", "WALL",
    "REST", "BEST", "NEXT", "LAST", "LONG", "GOOD", "HIGH", "DEEP",
    "OPEN", "FAST", "SLOW", "HARD", "SOFT", "WARM", "COLD", "SAFE",
    "ZONE", "ZEAL", "ZERO", "QUIT", "QUIZ", "JAZZ", "FIZZ", "FUZZ",
}


def _load_dictionary() -> set:
    """Load the system word list, falling back to a small built-in set."""
    system_paths = [
        "/usr/share/dict/words",
        "/usr/dict/words",
    ]
    for path in system_paths:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    words = {w.strip().upper() for w in fh if w.strip().isalpha()}
                logger.info("Loaded %d words from %s", len(words), path)
                return words
            except OSError as exc:
                logger.warning("Could not read %s: %s", path, exc)
    logger.warning("System dictionary not found – using built-in fallback (%d words)", len(_FALLBACK_WORDS))
    return set(_FALLBACK_WORDS)


_DICTIONARY: set = _load_dictionary()


def is_valid_word(word: str) -> bool:
    """Return True if *word* is a valid Scrabble dictionary word."""
    return word.upper() in _DICTIONARY


def get_word_count() -> int:
    """Return the number of words in the loaded dictionary."""
    return len(_DICTIONARY)
