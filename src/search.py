"""Search: query parsing, AND-intersection retrieval, TF-IDF ranking,
and phrase search.

A plain query (``find good friends``) returns documents containing
every tokenised query term — conjunctive (AND) semantics, as the
brief's ``find good friends`` example requires.

A quoted query (``find "good friends"``) switches to phrase search:
only documents where the terms appear in the given order at
consecutive positions are returned. The positional metadata stored
by the indexer makes this a small extension on top of the existing
AND machinery.

In both modes results are ranked by TF-IDF so the most relevant page
appears first.
"""

from __future__ import annotations

import math
from typing import Iterable

from src.indexer import Indexer, Posting
from src.tokeniser import tokenise


class SearchEngine:
    """Stateless query layer over an Indexer.

    Composition over inheritance: the engine holds a reference to an
    Indexer rather than subclassing it, so the index can be swapped
    (e.g. with a mock in tests) without touching the search logic.
    """

    def __init__(self, index: Indexer) -> None:
        self.index = index

    # ------------------------------------------------------------------
    # find — public entry point with dispatch on query syntax
    # ------------------------------------------------------------------
    def find(self, query: str) -> list[tuple[str, float]]:
        """Return ``[(url, score), ...]`` ranked by TF-IDF (descending).

        - Plain query ``good friends`` → AND search.
        - Quoted query ``"good friends"`` → phrase search (terms must
          appear in the given order at consecutive positions).
        - A single-word phrase is equivalent to the unquoted form.

        Returns ``[]`` for empty queries, unknown terms, or when no
        document satisfies the chosen mode.
        """
        is_phrase = self._is_phrase_query(query)
        if is_phrase:
            # Strip the outer quotes; whatever's inside is the phrase.
            query = query.strip()[1:-1]

        terms = tokenise(query)
        if not terms:
            return []

        postings_per_term = [self.index.get_postings(t) for t in terms]
        if any(not p for p in postings_per_term):
            return []

        # Set intersection — common starting point for both modes.
        candidates: set[str] = set(postings_per_term[0])
        for postings in postings_per_term[1:]:
            candidates &= set(postings)
        if not candidates:
            return []

        if is_phrase:
            return self._rank_phrase(candidates, terms, postings_per_term)
        return self._rank_and(candidates, terms, postings_per_term)

    # ------------------------------------------------------------------
    # Phrase detection
    # ------------------------------------------------------------------
    @staticmethod
    def _is_phrase_query(query: str) -> bool:
        """True iff ``query`` is wrapped in matching double quotes."""
        q = query.strip()
        return len(q) >= 2 and q.startswith('"') and q.endswith('"')

    # ------------------------------------------------------------------
    # AND ranking
    # ------------------------------------------------------------------
    def _rank_and(
        self,
        urls: set[str],
        terms: list[str],
        postings_per_term: list[dict[str, Posting]],
    ) -> list[tuple[str, float]]:
        """Score every URL in ``urls`` by summed TF-IDF and sort."""
        scored = [
            (url, self._tf_idf_score(url, terms, postings_per_term))
            for url in urls
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored

    def _tf_idf_score(
        self,
        url: str,
        terms: Iterable[str],
        postings_per_term: list[dict[str, Posting]],
    ) -> float:
        """Sum of TF-IDF contributions of each query term for ``url``.

        - ``tf`` is normalised by document length so long pages don't
          win by sheer size.
        - ``idf`` uses ``log((N + 1) / (df + 1)) + 1`` — the ``+1``
          smoothing avoids ``log(0)`` and the outer ``+1`` keeps every
          term contributing positively even when present in every doc.
        """
        n_docs = max(self.index.doc_count, 1)
        doc_length = max(self.index.doc_lengths.get(url, 1), 1)
        score = 0.0
        for postings in postings_per_term:
            tf = postings[url]["tf"]
            df = len(postings)
            tf_norm = tf / doc_length
            idf = math.log((n_docs + 1) / (df + 1)) + 1.0
            score += tf_norm * idf
        return score

    # ------------------------------------------------------------------
    # Phrase ranking
    # ------------------------------------------------------------------
    def _rank_phrase(
        self,
        urls: set[str],
        terms: list[str],
        postings_per_term: list[dict[str, Posting]],
    ) -> list[tuple[str, float]]:
        """Filter AND candidates to phrase matches and rank them.

        Scoring is a TF-IDF variant where the *phrase* is the unit:
        ``tf`` is the number of times the phrase begins in the doc,
        ``df`` is the number of docs containing the phrase. This keeps
        ranking semantically aligned with what the user actually
        searched for.
        """
        counts: dict[str, int] = {}
        for url in urls:
            count = self._phrase_count(url, terms, postings_per_term)
            if count > 0:
                counts[url] = count

        if not counts:
            return []

        phrase_df = len(counts)
        n_docs = max(self.index.doc_count, 1)
        idf = math.log((n_docs + 1) / (phrase_df + 1)) + 1.0

        scored: list[tuple[str, float]] = []
        for url, count in counts.items():
            doc_length = max(self.index.doc_lengths.get(url, 1), 1)
            tf_norm = count / doc_length
            scored.append((url, tf_norm * idf))

        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored

    @staticmethod
    def _phrase_count(
        url: str,
        terms: list[str],
        postings_per_term: list[dict[str, Posting]],
    ) -> int:
        """Return how many times the phrase begins in ``url``.

        For each occurrence of the *first* term at position ``p``, the
        phrase matches iff term ``i`` occurs at position ``p + i`` for
        every subsequent ``i``.
        """
        if not terms:
            return 0
        if len(terms) == 1:
            return postings_per_term[0][url]["tf"]

        # O(1) membership tests for terms 1..n-1.
        later_positions = [
            set(postings_per_term[i][url]["positions"])
            for i in range(1, len(terms))
        ]

        count = 0
        for start in postings_per_term[0][url]["positions"]:
            if all(
                (start + offset) in positions
                for offset, positions in enumerate(later_positions, start=1)
            ):
                count += 1
        return count

    # ------------------------------------------------------------------
    # print
    # ------------------------------------------------------------------
    def print_term(self, raw_term: str) -> str:
        """Format the postings list for a single term as a string.

        Runs the input through the shared tokeniser so ``print Hello,``
        and ``print hello`` are equivalent. If the input contains more
        than one token, only the first is looked up; ``find`` is the
        right command for multi-word queries.
        """
        tokens = tokenise(raw_term)
        if not tokens:
            return "No valid term provided."

        term = tokens[0]
        postings = self.index.get_postings(term)
        if not postings:
            return f"No occurrences of '{term}' in the index."

        lines: list[str] = [
            f"Inverted index for '{term}':",
            f"  Document frequency: {len(postings)}",
            f"  Total occurrences:  {sum(p['tf'] for p in postings.values())}",
        ]
        for url in sorted(postings):
            data = postings[url]
            tf = data["tf"]
            positions = data["positions"]
            preview = positions[:10]
            more = f" (+{len(positions) - 10} more)" if len(positions) > 10 else ""
            lines.append(f"  {url}")
            lines.append(f"    tf={tf}, positions={preview}{more}")
        return "\n".join(lines)