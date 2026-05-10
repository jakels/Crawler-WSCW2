"""Tests for the SearchEngine."""

from __future__ import annotations

from src.indexer import Indexer
from src.search import SearchEngine


def _engine(docs: dict[str, str]) -> SearchEngine:
    idx = Indexer()
    for url, text in docs.items():
        idx.add_document(url, text)
    return SearchEngine(idx)


# ---------------------------------------------------------------------
# find
# ---------------------------------------------------------------------
def test_find_single_term_returns_matching_docs() -> None:
    engine = _engine({
        "u1": "good morning",
        "u2": "bad day",
        "u3": "good night",
    })
    urls = [url for url, _ in engine.find("good")]
    assert set(urls) == {"u1", "u3"}


def test_find_multi_term_uses_intersection() -> None:
    engine = _engine({
        "u1": "good friends are great",
        "u2": "good day everyone",
        "u3": "friends forever",
    })
    urls = [url for url, _ in engine.find("good friends")]
    assert urls == ["u1"]


def test_find_returns_empty_for_unknown_term() -> None:
    engine = _engine({"u1": "hello world"})
    assert engine.find("missing") == []


def test_find_returns_empty_for_no_intersection() -> None:
    engine = _engine({
        "u1": "good morning",
        "u2": "bad night",
    })
    assert engine.find("good night") == []


def test_find_returns_empty_for_empty_query() -> None:
    engine = _engine({"u1": "hello"})
    assert engine.find("") == []
    assert engine.find("    ") == []
    assert engine.find("!!!") == []  # punctuation tokenises to nothing


def test_find_is_case_insensitive() -> None:
    engine = _engine({"u1": "good morning"})
    urls = [url for url, _ in engine.find("GOOD")]
    assert urls == ["u1"]


def test_find_strips_punctuation_from_query() -> None:
    engine = _engine({"u1": "good morning"})
    urls = [url for url, _ in engine.find("good,")]
    assert urls == ["u1"]


def test_find_ranks_higher_tf_above_lower_tf() -> None:
    # Both docs match; the one mentioning the term more often (relative
    # to its length) should rank first.
    engine = _engine({
        "u1": "rare common",                    # tf=1, len=2 → tf_norm 0.5
        "u2": "rare rare rare common common",   # tf=3, len=5 → tf_norm 0.6
    })
    urls = [url for url, _ in engine.find("rare")]
    assert urls == ["u2", "u1"]


def test_find_rare_term_outranks_common_term_for_same_doc() -> None:
    # IDF should weight a term that appears in 1/3 docs more heavily
    # than one that appears in 3/3.
    engine = _engine({
        "u1": "common rare",
        "u2": "common other",
        "u3": "common again",
    })
    rare_results = engine.find("rare")
    common_results = engine.find("common")
    rare_score = rare_results[0][1]
    common_score = next(score for url, score in common_results if url == "u1")
    assert rare_score > common_score


# ---------------------------------------------------------------------
# print_term
# ---------------------------------------------------------------------
def test_print_term_shows_tf_and_url() -> None:
    engine = _engine({"u1": "hello world hello"})
    out = engine.print_term("hello")
    assert "hello" in out
    assert "u1" in out
    assert "tf=2" in out


def test_print_term_for_unknown_word() -> None:
    engine = _engine({"u1": "hello"})
    out = engine.print_term("missing")
    assert "missing" in out
    assert "no occurrences" in out.lower()


def test_print_term_is_case_insensitive() -> None:
    engine = _engine({"u1": "Good"})
    out = engine.print_term("GOOD")
    assert "good" in out
    assert "tf=1" in out


def test_print_term_strips_query_punctuation() -> None:
    engine = _engine({"u1": "good"})
    out = engine.print_term("good,")
    assert "tf=1" in out


def test_print_term_for_empty_input() -> None:
    engine = _engine({"u1": "hello"})
    out = engine.print_term("")
    assert "no valid term" in out.lower()


def test_print_term_includes_position_list() -> None:
    engine = _engine({"u1": "a b a b a"})
    out = engine.print_term("a")
    assert "[0, 2, 4]" in out