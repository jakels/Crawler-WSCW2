# `indexer.py` — Documentation

## Overview

`indexer.py` defines the `Indexer` class, which builds an inverted
index from `{url: html}` pages, persists it to a single JSON file,
and exposes a small query API for the search layer.

An **inverted index** is the data structure at the heart of every
classical search engine. Instead of storing "document → words"
(forward index), it stores "word → documents" — exactly the lookup
direction a search query needs. Computing it once at build time turns
every query from "scan every page" into "look up one dict key".

## Data structure

The index has three parts:

```python
postings:    dict[str, dict[str, {"tf": int, "positions": list[int]}]]
doc_lengths: dict[str, int]
doc_count:   int
```

- `postings[term][url]` — for each (term, url) pair, the term
  frequency in that document and the ordered list of token positions.
  Positions are needed for phrase search; tf is needed for ranking.
- `doc_lengths[url]` — token count of each document. Length
  normalisation is a key part of TF-IDF and BM25.
- `doc_count` — total number of indexed documents. The `N` in
  `idf = log(N / df)`.

## Class: `Posting` (TypedDict)

A typed structural alias for the per-(term, url) value:
`{"tf": int, "positions": list[int]}`. Provides editor autocomplete
and lets `mypy` catch typos like `posting["positon"]` at lint time.

## Class: `Indexer`

### `__init__(self) -> None`

Initialises an empty index — empty `postings`, empty `doc_lengths`,
`doc_count = 0`.

### `build(self, pages) -> None`

Replaces any existing index with one built from `pages` (a `{url:
html}` mapping, typically produced by `Crawler.crawl`).

Step by step:

1. Call `_reset()` to wipe any existing state. Without this, calling
   `build` twice would silently merge two corpora — surprising and
   wrong.
2. For each `(url, html)`:
   1. Convert the HTML to plain text via `_extract_text`.
   2. Pass it to `add_document`.
3. Log the final document and vocabulary counts so the video demo
   can show progress at a glance.

### `add_document(self, url, text) -> None`

Tokenises `text` and merges its terms into the postings list under
`url`. Public so the test suite can drive the indexer with synthetic
inputs that bypass HTML parsing entirely.

Step by step:

1. `tokens = tokenise(text)` — delegate to the shared tokeniser.
2. Record the document's length: `doc_lengths[url] = len(tokens)`.
3. Increment `doc_count`.
4. For each `(position, token)` from `enumerate(tokens)`:
   1. `setdefault(token, {})` — ensure the token has an entry in
      `postings`.
   2. `setdefault(url, {"tf": 0, "positions": []})` — ensure that
      token has an entry for this URL. Two `setdefault` calls form a
      compact replacement for nested `if not in: ... = ...` blocks.
   3. Increment `tf`.
   4. Append `position` to `positions`.

### `_extract_text(html) -> str` (static)

Strips HTML markup and returns the visible text.

Step by step:

1. Parse the HTML with BeautifulSoup using the built-in
   `html.parser` backend.
2. **Remove `<script>` and `<style>` elements.** Their contents
   aren't visible to the user and shouldn't be searchable. Without
   this step the index would contain JavaScript identifiers and CSS
   property names — a classic search-quality bug. The
   `test_build_strips_html_tags_and_scripts` test guards against
   regressions here.
3. Call `get_text(separator=" ")` so adjacent block-level tags don't
   accidentally fuse two words (`<p>good</p><p>day</p>` should yield
   `good day`, not `goodday`).

### `_reset(self) -> None`

Clears all three index structures back to their empty state.

### `save(self, path) -> None`

Writes the index to a single JSON file.

Step by step:

1. Coerce `path` to a `Path`, then create any missing parent
   directories. Lets you call `save("data/index.json")` without
   having to mkdir first.
2. Build a single dict containing `postings`, `doc_lengths`, and
   `doc_count`.
3. `json.dump` it to the file.

JSON is chosen over `pickle` for three reasons:

- It's human-inspectable — `cat data/index.json | python -m json.tool`
  during the video demo proves the index contains what you say it
  contains.
- It's portable — no Python version coupling.
- It refuses to serialise unexpected types, which surfaces bugs
  (e.g. accidentally storing a `set` as a posting) instead of hiding
  them.

### `load(self, path) -> None`

Replaces the in-memory index with one read from `path`.

Step by step:

1. Open the file and `json.load` it.
2. Assign each of the three keys back onto `self`. There's no
   defensive validation — if the file is corrupt, `json.load` will
   raise, which is what we want to surface to the caller.

### `get_postings(self, term) -> dict[str, Posting]`

Returns the postings dict for `term`, lowercased. Returns `{}` if the
term is absent — never raises `KeyError`. The `print` and `find`
commands both rely on this empty-dict-on-miss behaviour to show "no
results" cleanly.

### `document_frequency(self, term) -> int`

Returns `len(get_postings(term))` — the number of documents
containing `term`. Used as `df` in `idf = log(N / df)` for TF-IDF
ranking later in the search module.

### `__contains__(self, term) -> bool`

Lets us write `if "good" in index:`. Lowercases its argument so
membership checks are case-insensitive in line with the rest of the
search engine.

### `__len__(self) -> int`

Returns the vocabulary size (number of unique terms). Useful for
quick health checks: a freshly built quotes.toscrape.com index has
roughly 2,000–3,000 unique terms, so `len(idx)` returning 3 means
something has gone badly wrong.

## Design rationale (talking points for the video)

- **Positions stored, not just frequencies.** The brief asks for
  "frequency, position, etc". Storing positions costs a little space
  but enables phrase search (`find "good friends"` matching only
  adjacent occurrences) — a top-band feature for ~30 lines of code.
- **Document length stored.** Necessary for TF-IDF or BM25 length
  normalisation. A long page that mentions "good" five times
  shouldn't outrank a focused page that mentions it three times in
  ten words.
- **`setdefault` over `defaultdict`.** `defaultdict` serialises
  awkwardly through JSON and pickles its `default_factory` —
  `setdefault` keeps the data structure a plain dict, which is what
  ends up in the file.
- **Separate `add_document` from `build`.** Lets unit tests drive
  the indexer with raw text and skip the HTML pipeline. Several
  tests rely on this.
- **JSON, not pickle.** Inspectable, portable, no Python-version
  coupling. The video can `cat` the index file as evidence.