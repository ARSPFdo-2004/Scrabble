"""
tests/test_dictionary.py – Tests for the word-validation module.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dictionary import is_valid_word, get_word_count


class TestDictionary:
    def test_common_words_valid(self):
        for word in ("CAT", "DOG", "WORD", "PLAY"):
            assert is_valid_word(word), f"Expected '{word}' to be valid"

    def test_case_insensitive(self):
        assert is_valid_word("cat")
        assert is_valid_word("Cat")
        assert is_valid_word("CAT")

    def test_nonsense_invalid(self):
        assert not is_valid_word("XQZJW")
        assert not is_valid_word("ZZZZZ")

    def test_empty_string_invalid(self):
        assert not is_valid_word("")

    def test_word_count_positive(self):
        assert get_word_count() > 0
