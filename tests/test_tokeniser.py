"""Tests for the tokeniser."""

from __future__ import annotations

from src.tokeniser import tokenise


def test_empty_string_returns_empty_list() -> None:
    assert tokenise("") == []


def test_simple_sentence() -> None:
    assert tokenise("hello world") == ["hello", "world"]


def test_lowercases_input() -> None:
    assert tokenise("Hello WORLD Hello") == ["hello", "world", "hello"]


def test_strips_punctuation() -> None:
    assert tokenise("Hello, world! How are you?") == [
        "hello", "world", "how", "are", "you"
    ]


def test_preserves_apostrophes_in_contractions() -> None:
    assert tokenise("don't won't it's") == ["don't", "won't", "it's"]


def test_strips_standalone_apostrophes_and_quotes() -> None:
    assert tokenise("'quoted' words") == ["quoted", "words"]


def test_keeps_digits() -> None:
    assert tokenise("Year 1984 was 40 years ago") == [
        "year", "1984", "was", "40", "years", "ago"
    ]


def test_collapses_whitespace() -> None:
    assert tokenise("hello\n\tworld\r\n   foo") == ["hello", "world", "foo"]


def test_punctuation_only_returns_empty() -> None:
    assert tokenise("!!! ... ???") == []


def test_preserves_token_order_for_positions() -> None:
    # The indexer relies on this ordering to record positions correctly.
    assert tokenise("a b c a b a") == ["a", "b", "c", "a", "b", "a"]