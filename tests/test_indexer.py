"""Tests for the Indexer."""

from __future__ import annotations

from pathlib import Path

from src.indexer import Indexer


def test_add_single_document_records_tf_and_positions() -> None:
    idx = Indexer()
    idx.add_document("u1", "hello world hello")

    assert idx.doc_count == 1
    assert idx.doc_lengths["u1"] == 3
    assert idx.postings["hello"]["u1"] == {"tf": 2, "positions": [0, 2]}
    assert idx.postings["world"]["u1"] == {"tf": 1, "positions": [1]}


def test_indexing_is_case_insensitive() -> None:
    idx = Indexer()
    idx.add_document("u1", "Good GOOD good")
    assert idx.postings["good"]["u1"]["tf"] == 3
    assert "Good" not in idx.postings
    assert "GOOD" not in idx.postings


def test_punctuation_is_stripped_from_tokens() -> None:
    idx = Indexer()
    idx.add_document("u1", "Hello, world! Hello.")
    assert "hello" in idx.postings
    assert "world" in idx.postings
    assert "hello," not in idx.postings


def test_multiple_documents_share_terms() -> None:
    idx = Indexer()
    idx.add_document("u1", "hello world")
    idx.add_document("u2", "hello there")

    assert idx.doc_count == 2
    assert set(idx.postings["hello"]) == {"u1", "u2"}
    assert set(idx.postings["world"]) == {"u1"}
    assert set(idx.postings["there"]) == {"u2"}


def test_build_strips_html_tags_and_scripts() -> None:
    pages = {
        "u1": """
        <html>
          <head><style>body { color: red; }</style></head>
          <body>
            <script>alert('hi');</script>
            <p>Hello <b>world</b></p>
          </body>
        </html>
        """,
    }
    idx = Indexer()
    idx.build(pages)

    assert "hello" in idx.postings
    assert "world" in idx.postings
    assert "alert" not in idx.postings  # script body excluded
    assert "color" not in idx.postings  # style body excluded
    assert "p" not in idx.postings      # tag names not indexed
    assert "b" not in idx.postings


def test_build_resets_existing_state() -> None:
    idx = Indexer()
    idx.add_document("old", "stale data")
    idx.build({"new": "fresh data"})

    assert idx.doc_count == 1
    assert "stale" not in idx.postings
    assert "fresh" in idx.postings


def test_empty_document_still_counts() -> None:
    idx = Indexer()
    idx.add_document("u1", "")
    assert idx.doc_count == 1
    assert idx.doc_lengths["u1"] == 0
    assert idx.postings == {}


def test_get_postings_for_unknown_term_returns_empty_dict() -> None:
    idx = Indexer()
    idx.add_document("u1", "hello")
    assert idx.get_postings("missing") == {}


def test_document_frequency() -> None:
    idx = Indexer()
    idx.add_document("u1", "hello world")
    idx.add_document("u2", "hello there")
    idx.add_document("u3", "goodbye")

    assert idx.document_frequency("hello") == 2
    assert idx.document_frequency("world") == 1
    assert idx.document_frequency("missing") == 0


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    idx = Indexer()
    idx.add_document("u1", "hello world hello")
    idx.add_document("u2", "world peace")
    path = tmp_path / "data" / "index.json"
    idx.save(path)

    loaded = Indexer()
    loaded.load(path)

    assert loaded.doc_count == idx.doc_count
    assert loaded.postings == idx.postings
    assert loaded.doc_lengths == idx.doc_lengths


def test_contains_and_len() -> None:
    idx = Indexer()
    idx.add_document("u1", "hello world")
    assert "hello" in idx
    assert "HELLO" in idx          # case-insensitive
    assert "missing" not in idx
    assert len(idx) == 2            # vocabulary size