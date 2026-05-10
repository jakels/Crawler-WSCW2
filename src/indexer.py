"""Inverted-index construction and persistence.

The index maps each token to the documents that contain it, alongside
per-(token, document) statistics: term frequency and the list of token
positions inside that document. Document length and total document count
are also stored so the search layer can compute TF-IDF or BM25 scores
without re-scanning the corpus.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TypedDict

from bs4 import BeautifulSoup

from src.tokeniser import tokenise

logger = logging.getLogger(__name__)


class Posting(TypedDict):
    """Per-(term, document) statistics."""
    tf: int
    positions: list[int]


class Indexer:
    """Build, persist, and query an inverted index.

    The on-disk format is a single JSON file containing the postings
    dict, the per-document length map, and the total document count.
    JSON is chosen over pickle for inspectability — you can ``cat`` the
    index during the video demo and see exactly what's there.
    """

    def __init__(self) -> None:
        # term -> { url -> { "tf": int, "positions": [int, ...] } }
        self.postings: dict[str, dict[str, Posting]] = {}
        # url -> token count (for length normalisation in ranking)
        self.doc_lengths: dict[str, int] = {}
        # total documents indexed
        self.doc_count: int = 0

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def build(self, pages: dict[str, str]) -> None:
        """Replace any existing index with one built from ``pages``."""
        self._reset()
        for url, html in pages.items():
            text = self._extract_text(html)
            self.add_document(url, text)
        logger.info(
            "Indexed %d documents, %d unique terms",
            self.doc_count, len(self.postings),
        )

    def add_document(self, url: str, text: str) -> None:
        """Tokenise ``text`` and merge it into the index under ``url``."""
        tokens = tokenise(text)
        self.doc_lengths[url] = len(tokens)
        self.doc_count += 1
        for position, token in enumerate(tokens):
            term_postings = self.postings.setdefault(token, {})
            posting = term_postings.setdefault(url, {"tf": 0, "positions": []})
            posting["tf"] += 1
            posting["positions"].append(position)

    @staticmethod
    def _extract_text(html: str) -> str:
        """Strip HTML markup and return visible text only."""
        soup = BeautifulSoup(html, "html.parser")
        # Drop script and style outright; their contents shouldn't be
        # searchable text.
        for tag in soup(["script", "style"]):
            tag.decompose()
        return soup.get_text(separator=" ")

    def _reset(self) -> None:
        self.postings = {}
        self.doc_lengths = {}
        self.doc_count = 0

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save(self, path: str | Path) -> None:
        """Write the index to ``path`` as a single JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "postings": self.postings,
            "doc_lengths": self.doc_lengths,
            "doc_count": self.doc_count,
        }
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f)
        logger.info("Index saved to %s", path)

    def load(self, path: str | Path) -> None:
        """Replace the in-memory index with the one stored at ``path``."""
        path = Path(path)
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        self.postings = payload["postings"]
        self.doc_lengths = payload["doc_lengths"]
        self.doc_count = payload["doc_count"]
        logger.info(
            "Index loaded from %s: %d docs, %d terms",
            path, self.doc_count, len(self.postings),
        )

    # ------------------------------------------------------------------
    # Query helpers (used by the search module)
    # ------------------------------------------------------------------
    def get_postings(self, term: str) -> dict[str, Posting]:
        """Return the postings dict for ``term`` (empty if absent)."""
        return self.postings.get(term.lower(), {})

    def document_frequency(self, term: str) -> int:
        """Return the number of documents containing ``term``."""
        return len(self.get_postings(term))

    def __contains__(self, term: str) -> bool:
        return term.lower() in self.postings

    def __len__(self) -> int:
        """Vocabulary size."""
        return len(self.postings)