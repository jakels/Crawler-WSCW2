# `search.py` — Documentation

## Overview

`search.py` defines `SearchEngine`, the query layer that sits on top
of an `Indexer`. It is responsible for:

1. Looking up a single word's postings (powering `print`).
2. Finding the documents that match a multi-word query (powering
   `find`), in one of two modes:
   - **AND** (default) — documents containing every query term, as
     the brief's `find good friends` example requires.
   - **Phrase** (quoted) — documents where the terms appear in the
     given order at consecutive positions, e.g.
     `find "good friends"`.
3. Ranking matched documents by **TF-IDF** so the most relevant page
   appears first.

The engine holds a reference to an `Indexer` rather than subclassing
it. Composition keeps responsibilities separate: the indexer *stores*
term statistics, the engine *uses* them. This means search behaviour
can be unit-tested with synthetic indexes (as the test suite does)
without involving the crawler, BeautifulSoup, or the file system.

## Class: `SearchEngine`

### `__init__(self, index: Indexer) -> None`

Stores the passed-in `Indexer` on `self.index`. There is no other
state — the engine is otherwise stateless, so you can build many
engines over the same index, or swap an index in and out, without
worrying about cached query results going stale.

### `find(self, query: str) -> list[tuple[str, float]]`

Public entry point. Returns ranked `(url, score)` pairs.

Step by step:

1. **Detect mode** with `_is_phrase_query`. A query that strips down
   to something starting with `"` and ending with `"` is a phrase
   query; everything else is AND.
2. If phrase, **strip the outer quotes**. The contents are the phrase.
3. **Tokenise** with the shared `tokeniser.tokenise`. Identical
   tokenisation on both sides is what makes lookups work.
4. **Empty-token guard.** Empty/whitespace/punctuation-only queries
   short-circuit to `[]`.
5. **Look up postings for each term.** `postings_per_term[i]` is the
   `{url: posting}` dict for term `i`.
6. **Short-circuit on unknown terms.** If any term has no postings,
   neither AND nor phrase can match — return `[]`.
7. **Compute the AND-intersection of URLs.** Both modes need the set
   of documents containing every term as a starting point. Phrase
   search then narrows further; AND search uses it as-is.
8. **Dispatch** to `_rank_phrase` or `_rank_and`.

### Phrase detection

#### `_is_phrase_query(query) -> bool` (static)

Returns `True` if and only if the trimmed query is at least two
characters long and starts and ends with `"`. Two characters because
`""` is the smallest possible phrase wrapping (and tokenises to
nothing, which is handled correctly downstream).

### AND ranking

#### `_rank_and(self, urls, terms, postings_per_term)`

Scores each URL with `_tf_idf_score`, sorts descending, returns.

#### `_tf_idf_score(self, url, terms, postings_per_term) -> float`

Computes `Σ over terms t of: tf_norm(t, url) × idf(t)`.

```
tf_norm = tf(t, url) / max(doc_length(url), 1)
idf     = log((N + 1) / (df(t) + 1)) + 1
score  += tf_norm * idf
```

- **`tf` (term frequency)** — how often the term appears in the
  document. Already stored on the posting.
- **`tf_norm`** — `tf` divided by the document's token count. A long
  page that mentions "good" five times shouldn't outrank a focused
  ten-word page that mentions it three times.
- **`df` (document frequency)** — number of documents containing the
  term. `len(postings)` since `postings` is `{url: ...}` keyed by
  every doc that contains the term.
- **`idf`** — inverse document frequency. Common terms (high `df`)
  get a low IDF; rare terms get a high one. The smoothing in
  numerator and denominator prevents `log(0)` and the outer `+1`
  ensures every matching term contributes some positive weight.
  This is the same smoothing scikit-learn's `TfidfVectorizer` uses.
- **`max(..., 1)`** on `n_docs` and `doc_length` is defensive: it
  prevents division by zero or `log(1/0)` against an empty index or
  a zero-length document.

### Phrase ranking

#### `_rank_phrase(self, urls, terms, postings_per_term)`

Filters AND candidates to those where the terms are *contiguous*,
then ranks them by a TF-IDF variant where the **phrase is the unit**.

Step by step:

1. For each candidate URL, call `_phrase_count` to compute how many
   times the phrase begins in that document. Discard URLs with zero.
2. **Phrase document frequency** is the number of surviving URLs.
3. **Phrase IDF** is `log((N + 1) / (phrase_df + 1)) + 1`, identical
   in shape to the AND IDF formula but using the phrase as the unit.
4. For each surviving URL, score `(phrase_count / doc_length) × idf`.
5. Sort descending, return.

Using the phrase as the ranking unit is what makes "the phrase
appears five times" outrank "the phrase appears once" in the same
way the AND formula ranks single-term repetition.

#### `_phrase_count(url, terms, postings_per_term) -> int` (static)

Returns how many positions in `url` are valid starts for the phrase.

Step by step:

1. Empty terms → 0; single term → equivalent to plain `tf`.
2. Build position **sets** for terms 1..n-1 — the inner loop needs
   O(1) membership tests, not O(n) list scans.
3. For each occurrence position `p` of the *first* term, check that
   `p + offset` is a position of term `offset` for every subsequent
   `offset`. If so, count it as a phrase start.
4. Return the count.

The algorithm is `O(|first-term positions| × |phrase length|)` per
document, which is cheap given the position lists for any single
term in a single document are small.

### `print_term(self, raw_term: str) -> str`

Returns a multi-line, human-readable rendering of a single term's
postings, for the `print` CLI command.

Step by step:

1. **Tokenise the input.** Canonicalises it the same way `find` does,
   so `print Hello,`, `print "hello"`, and `print HELLO` all look up
   the term `hello`.
2. **Empty-token guard.** Return `"No valid term provided."` if the
   input had no letters or digits.
3. **First-token-wins** for multi-word input. Multi-word lookups
   belong in `find`.
4. **Look up postings.** If empty, return `"No occurrences of '...'
   in the index."`.
5. **Format the output:** a header with the term, document
   frequency, and total occurrence count, followed by a per-URL
   block with `tf` and a position list (truncated to the first ten
   with a `+N more` annotation if longer). Truncation prevents the
   demo terminal drowning in numbers when printing a stopword-like
   word.

## Design rationale (talking points for the video)

- **AND, not OR, by default.** The brief's `find good friends`
  example clearly intends documents containing both words. AND is the
  right default; OR would deluge the user with marginally-relevant
  pages.
- **Phrase search by quoting.** Mirrors Google and other search
  engines, so users discover it by intuition. The CLI passes the raw
  string through unchanged; the search layer owns the parsing.
- **Phrase as the ranking unit, not term.** A document containing
  "good morning" five times is more relevant to `"good morning"` than
  one containing it once, *regardless* of how often "good" or
  "morning" appear separately. Counting phrase starts captures that.
- **Same IDF formula in both modes.** Keeps the score scale
  comparable and the formula easy to remember when explaining it on
  camera.
- **Length normalisation.** Without it, longer documents always win.
  A focused short page about "indifference" should beat a long page
  that mentions it once in passing.
- **Smoothed IDF.** The `+1`s make the formula robust to corner cases
  (term in every doc, term in no doc) without changing the shape of
  the ranking on normal inputs.
- **Position-set lookup in `_phrase_count`.** O(1) membership against
  a `set` instead of O(n) against a list. The phrase check is in the
  inner loop, so the constant factor matters more than it looks like
  it should.
- **Engine separate from index.** Lets the CLI rebuild the index
  (via `do_load`) and hand a fresh `SearchEngine` to subsequent
  queries without a complicated reset protocol.