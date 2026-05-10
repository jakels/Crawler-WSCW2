# `search.py` — Documentation

## Overview

`search.py` defines `SearchEngine`, the query layer that sits on top
of an `Indexer`. It is responsible for:

1. Looking up a single word's postings (powering `print`).
2. Finding the documents that contain *every* term in a multi-word
   query (powering `find`, with conjunctive AND semantics as per the
   brief's `find good friends` example).
3. Ranking those documents by **TF-IDF** so the most relevant page
   appears first.

The engine holds a reference to an `Indexer` rather than subclassing
it. Composition keeps the two responsibilities separate: the indexer
*stores* term statistics, the engine *uses* them. This means you can
unit-test search behaviour with synthetic indexes (as the test suite
does) without involving the crawler, BeautifulSoup, or the file
system.

## Class: `SearchEngine`

### `__init__(self, index: Indexer) -> None`

Stores the passed-in `Indexer` on `self.index`. There is no other
state — the engine is otherwise stateless, so you can build many
engines over the same index, or swap an index in and out, without
worrying about cached query results going stale.

### `find(self, query: str) -> list[tuple[str, float]]`

Returns ranked `(url, score)` pairs for documents containing every
term in `query`. Empty list if there are no matches, no terms, or any
single term is unknown.

Step by step:

1. **Tokenise the query** with the shared `tokenise` function. Doing
   this here means `find Good FRIENDS,` is equivalent to `find good
   friends` — case folding, punctuation stripping, and contraction
   handling all happen in one place.
2. **Empty-query guard.** If tokenisation yields nothing (empty
   string, whitespace, punctuation only) return `[]` immediately.
   Without this the next step would `IndexError` on
   `postings_per_term[0]`.
3. **Look up postings for each term.** `postings_per_term[i]` is the
   `{url: posting}` dict for query term `i`. Looked up once, used
   twice (for intersection and for scoring) — avoids re-walking the
   index.
4. **Short-circuit on unknown terms.** If any term has an empty
   postings dict, the AND-intersection is necessarily empty, so we
   bail out immediately.
5. **Compute the intersection of URLs.** Start from the first term's
   set of URLs and `&=` each subsequent term's. The result is the
   set of documents that contain every query term.
6. **Empty-intersection guard.** If the intersection is empty the
   query has no results.
7. **Score each surviving URL** with `_tf_idf_score`.
8. **Sort by score, descending,** and return.

### `_tf_idf_score(self, url, terms, postings_per_term) -> float`

Computes `Σ over terms t of: tf_norm(t, url) × idf(t)`.

Formula, term by term:

```
tf_norm = tf(t, url) / max(doc_length(url), 1)
idf     = log((N + 1) / (df(t) + 1)) + 1
score  += tf_norm * idf
```

- **`tf` (term frequency)** — how often the term appears in the
  document. Already stored on the posting.
- **`tf_norm`** — `tf` divided by the document's token count. A long
  page that mentions "good" five times shouldn't outrank a focused
  ten-word page that mentions it three times. Normalisation prevents
  that.
- **`df` (document frequency)** — the number of documents containing
  the term. `len(postings)` since `postings` is `{url: ...}` keyed by
  every doc that contains the term.
- **`idf`** — inverse document frequency. Common terms (high `df`)
  get a low IDF; rare terms get a high one. The `+1` smoothing in
  numerator and denominator prevents `log(0)` and the outer `+1`
  ensures every matching term contributes some positive weight even
  if it appears in every document. This particular smoothing is the
  one used by scikit-learn's `TfidfVectorizer` — well-tested and
  well-known.
- **`max(..., 1)`** on `n_docs` and `doc_length` is defensive: it
  prevents a division-by-zero or `log(1/0)` if the engine is queried
  against an empty index or a zero-length document.

### `print_term(self, raw_term: str) -> str`

Returns a multi-line, human-readable rendering of a single term's
postings, for the `print` CLI command.

Step by step:

1. **Tokenise the input.** This canonicalises it the same way
   `find` does, so `print Hello,`, `print "hello"`, and `print HELLO`
   all look up the term `hello`.
2. **Empty-token guard.** If the input contained no actual letters
   or digits, return `"No valid term provided."`.
3. **First-token-wins.** If the user typed multiple words, only the
   first is looked up. Multi-word lookups belong in `find`. (The
   alternative — erroring on multi-word input — feels punishing for
   minimal benefit.)
4. **Look up postings.** If empty, return `"No occurrences of '...'
   in the index."`.
5. **Format the output:** a header naming the term, the document
   frequency, the total occurrence count across the corpus, then a
   per-URL block with `tf` and a position list (truncated to the
   first ten with a `+N more` annotation if longer).

The position truncation matters in practice: for a stopword-like
term the position list could be hundreds of integers per page, which
makes the terminal output unreadable.

## Design rationale (talking points for the video)

- **AND, not OR.** The brief's `find good friends` example clearly
  intends documents containing both words. AND is the right default;
  OR would deluge the user with marginally-relevant pages.
- **TF-IDF over raw frequency.** Raw frequency would let a single
  long page dominate every result list. TF-IDF respects both how
  central a term is to a document and how distinctive it is across
  the corpus.
- **Length normalisation.** Without it, longer documents always win.
  A focused short page about "indifference" should beat a long page
  that mentions it once in passing.
- **Smoothed IDF.** The `+1`s make the formula robust to corner cases
  (term in every doc, term in no doc) without changing the shape of
  the ranking on normal inputs.
- **Engine separate from index.** Lets the CLI rebuild the index
  (via `do_load`) and hand a fresh `SearchEngine` to subsequent
  queries without a complicated reset protocol.
- **Position list truncation in `print`.** Prevents the demo terminal
  from drowning in numbers when printing a common word.