"""Tokenisation: text → ordered list of lowercase word tokens.

Kept as its own module so both the indexer (during build) and the search
layer (when parsing user queries) tokenise identically. Identical
tokenisation on both sides is what makes search work — if the indexer
stores ``don't`` and the query layer strips the apostrophe, lookups miss.
"""

from __future__ import annotations

import re

# A "word" is one or more letters/digits, optionally followed by an
# in-word apostrophe-and-letters group (so "don't" stays whole).
# Everything else (commas, full stops, em-dashes, parentheses, etc.) is
# treated as a token boundary.
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")


def tokenise(text: str) -> list[str]:
    """Return the lowercase word tokens of ``text`` in document order.

    >>> tokenise("Hello, world! Hello.")
    ['hello', 'world', 'hello']
    >>> tokenise("It's a 'good' don't-quote situation.")
    ['it's', 'a', 'good', "don't", 'quote', 'situation']
    >>> tokenise("")
    []
    """
    if not text:
        return []
    return _TOKEN_RE.findall(text.lower())