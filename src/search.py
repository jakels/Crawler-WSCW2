"""Search: query parsing, AND-intersection retrieval, TF-IDF ranking.

The brief requires `find` to return all pages containing every query
term (set intersection over per-term postings lists). On top of that
correctness requirement, results are ranked by TF-IDF so the most
relevant page comes first — a top-band feature for ~30 lines of code.
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
    # find
    # ------------------------------------------------------------------
    def find(self, query: str) -> list[tuple[str, float]]:
        """Return ``[(url, score), ...]`` ranked by TF-IDF (descending).

        Documents must contain *every* tokenised query term — i.e.
        conjunctive (AND) semantics, as the brief's ``find good friends``
        example requires. The empty list is returned for empty queries,
        unknown terms, or when no document contains all terms.
        """
        terms = tokenise(query)
        if not terms:
            return []

        # One postings dict per query term, in query order.
        postings_per_term = [self.index.get_postings(t) for t in terms]

        # Short-circuit: any term with no postings means no document
        # can satisfy the AND, so the intersection is empty.
        if any(not p for p in postings_per_term):
            return []

        # Set intersection. Starting from the smallest postings list
        # would be marginally faster, but the gain is irrelevant at this
        # scale and ordering by query position keeps behaviour
        # predictable.
        matching: set[str] = set(postings_per_term[0])
        for postings in postings_per_term[1:]:
            matching &= set(postings)

        if not matching:
            return []

        scored = [
            (url, self._tf_idf_score(url, terms, postings_per_term))
            for url in matching
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
          term contributing something even when present in every doc.
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