"""Tests for the CLI shell.

We drive the Cmd subclass directly (calling do_* methods) and capture
its stdout via pytest's ``capsys`` fixture. This is faster and far more
deterministic than spawning a subprocess and pumping stdin.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.indexer import Indexer
from src.main import SearchShell


@pytest.fixture
def shell_with_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SearchShell:
    """A shell with a tiny pre-built index already loaded."""
    idx = Indexer()
    idx.add_document("https://example.com/u1", "good morning friends")
    idx.add_document("https://example.com/u2", "good night")
    index_path = tmp_path / "index.json"
    idx.save(index_path)

    monkeypatch.setattr("src.main.INDEX_PATH", index_path)
    shell = SearchShell()
    shell.do_load("")
    return shell


def test_load_succeeds_and_reports_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    idx = Indexer()
    idx.add_document("https://example.com/u1", "good morning friends")
    idx.add_document("https://example.com/u2", "good night")
    index_path = tmp_path / "index.json"
    idx.save(index_path)
    monkeypatch.setattr("src.main.INDEX_PATH", index_path)

    SearchShell().do_load("")

    out = capsys.readouterr().out
    assert "Loaded 2 documents" in out


def test_load_fails_when_no_index_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("src.main.INDEX_PATH", tmp_path / "missing.json")
    SearchShell().do_load("")
    out = capsys.readouterr().out
    assert "No index found" in out


def test_find_lists_results(
    shell_with_index: SearchShell, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()  # discard load output
    shell_with_index.do_find("good")
    out = capsys.readouterr().out
    assert "u1" in out
    assert "u2" in out
    assert "score:" in out


def test_find_intersection_for_multi_word_query(
    shell_with_index: SearchShell, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    shell_with_index.do_find("good friends")
    out = capsys.readouterr().out
    assert "u1" in out
    assert "u2" not in out  # u2 doesn't contain "friends"


def test_find_no_results(
    shell_with_index: SearchShell, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    shell_with_index.do_find("xyzzy")
    out = capsys.readouterr().out
    assert "No results" in out


def test_find_empty_shows_usage(
    shell_with_index: SearchShell, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    shell_with_index.do_find("   ")
    out = capsys.readouterr().out
    assert "Usage:" in out


def test_print_word_shows_postings(
    shell_with_index: SearchShell, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    shell_with_index.do_print("good")
    out = capsys.readouterr().out
    assert "good" in out
    assert "u1" in out
    assert "u2" in out
    assert "tf=" in out


def test_print_unknown_word(
    shell_with_index: SearchShell, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    shell_with_index.do_print("xyzzy")
    out = capsys.readouterr().out
    assert "No occurrences" in out


def test_print_empty_shows_usage(
    shell_with_index: SearchShell, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    shell_with_index.do_print("")
    out = capsys.readouterr().out
    assert "Usage:" in out


def test_commands_require_an_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("src.main.INDEX_PATH", tmp_path / "missing.json")
    shell = SearchShell()

    shell.do_find("good")
    assert "No index loaded" in capsys.readouterr().out

    shell.do_print("good")
    assert "No index loaded" in capsys.readouterr().out


def test_unknown_command(capsys: pytest.CaptureFixture[str]) -> None:
    SearchShell().default("frobnicate the widgets")
    out = capsys.readouterr().out
    assert "Unknown command" in out
    assert "frobnicate" in out


def test_emptyline_does_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    assert SearchShell().emptyline() is None
    assert capsys.readouterr().out == ""


def test_quit_returns_true(capsys: pytest.CaptureFixture[str]) -> None:
    assert SearchShell().do_quit("") is True
    assert "Goodbye" in capsys.readouterr().out