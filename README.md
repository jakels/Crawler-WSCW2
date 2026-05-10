# WS-CW2 Crawler Project
A Python web crawler built for coursework 2 of web services by Jake Lowther-Spittlehouse (ll22jls@leeds.ac.uk)

### Project Overview

A command-line search engine over [quotes.toscrape.com](https://quotes.toscrape.com/),
built for COMP3011 Web Services and Web Data Coursework 2. The tool
performs a polite breadth-first crawl of the target site, constructs
an inverted index over every word encountered, and exposes a small
REPL with the four commands required by the brief — `build`, `load`,
`print`, `find` — for inspecting the index and querying it.

Key technical features:

- **Polite crawling** with a 6-second window between live HTTP
  requests, exponential backoff on transient failures, and on-disk
  caching so the development loop doesn't pay the crawl cost on every
  iteration.
- **Inverted index** storing term frequency and positions per
  `(term, document)` pair, alongside per-document length and total
  document count for ranking.
- **TF-IDF ranking** with length normalisation and smoothed IDF for
  multi-word queries.
- **Phrase search** via double-quoted queries (`find "good friends"`)
  using stored positions to require contiguous adjacency in that
  order.

The project is split across five source modules and a mirrored test
suite:

```
.
├── src/
│   ├── crawler.py      # Polite BFS crawler with caching and retries
│   ├── tokeniser.py    # Lowercase word tokenisation
│   ├── indexer.py      # Inverted index build / save / load
│   ├── search.py       # TF-IDF ranked retrieval (AND + phrase)
│   └── main.py         # CLI shell (cmd.Cmd)
├── tests/              # Unit tests across all modules; no live HTTP
├── data/               # Compiled index (index.json)
├── cache/              # Cached HTML from previous crawls
├── docs/               # Per-module documentation
├── requirements.txt
├── pyproject.toml
└── README.md
```

Per-module documentation lives in `docs/<module>_documentation.md`
and walks each function step by step, alongside the design rationale
for that module.

### Installation

**Prerequisites:** Python 3.10 or newer.

Clone the repository and install dependencies into a virtual
environment:

```bash
git clone https://github.com/jakels/Crawler-WSCW2.git
cd Crawler-WSCW2

python -m venv .venv

# Windows (PowerShell):
.venv\Scripts\Activate.ps1

# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

No further configuration is required. The first `build` will create
the `data/` and `cache/` directories automatically.

### Example Usage

Launch the interactive shell:

```bash
python -m src.main
```

You'll see:

```
Quotes search engine.
Commands: build, load, print <word>, find <query>, help, quit.
Tip: wrap a query in double quotes for phrase search (find "good friends").
> 
```

**`build`** — crawl the target site, build the inverted index, save
it to `data/index.json`. The first live crawl takes around 5–10
minutes (10 paginated quote pages plus the linked author detail
pages, separated by the 6-second politeness window). Subsequent
builds read from `cache/` and complete in seconds.

```
> build
Crawling (cached HTML will be reused where available)...
Fetched 60 pages.
Building inverted index...
Saving index to data/index.json...
Done. 61 documents, 4650 unique terms.
```

Pass `fresh` to bypass the cache and force a live re-crawl:

```
> build fresh
```

**`load`** — load a previously built index from disk:

```
> load
Loaded 61 documents, 4650 unique terms from data/index.json.
```

**`print <word>`** — display the inverted index entry for a word
(case-insensitive). Position lists are truncated to the first ten
entries to keep output readable:

```
> print nonsense
Inverted index for 'nonsense':
  Document frequency: 2
  Total occurrences:  3
  https://quotes.toscrape.com/page/4/
    tf=2, positions=[112, 145]
  https://quotes.toscrape.com/page/8/
    tf=1, positions=[67]
```

**`find <query>`** — list pages matching the query, ranked by TF-IDF
(descending).

Single term:

```
> find indifference
Found 1 result(s) for 'indifference':
  1. https://quotes.toscrape.com/page/3/  (score: 0.0421)
```

Multi-word — returns pages containing *every* term (AND semantics):

```
> find good friends
Found 3 result(s) for 'good friends':
  1. https://quotes.toscrape.com/page/2/  (score: 0.0185)
  2. https://quotes.toscrape.com/page/5/  (score: 0.0142)
  3. https://quotes.toscrape.com/page/7/  (score: 0.0093)
```

Quoted — phrase search: returns only pages where the terms appear
in the given order at consecutive positions:

```
> find "good friends"
Found 1 result(s) for '"good friends"':
  1. https://quotes.toscrape.com/page/5/  (score: 0.0387)
```

**`quit`** — exit the shell. `exit` and `Ctrl-D` are also accepted.
`help <command>` prints the docstring for any command.

### Testing Procedure

The test suite covers all five modules. Every test uses mocked HTTP
(via the `responses` library) so the suite never touches the live
site and completes in under a second.

Run the full suite:

```bash
pytest
```

Run with coverage:

```bash
pytest --cov=src --cov-report=term-missing
```

Run a single module's tests:

```bash
pytest tests/test_crawler.py -v
```

Run a single test by name:

```bash
pytest -k test_phrase_matches_adjacent_words
```

Test files mirror the source layout: `tests/test_crawler.py`,
`tests/test_tokeniser.py`, `tests/test_indexer.py`,
`tests/test_search.py`, and `tests/test_main.py`. Tests use
`pytest`'s `tmp_path` fixture for file-system isolation and
`monkeypatch` to redirect `INDEX_PATH` onto a throwaway location so
they exercise `do_build` / `do_load` against real (temporary) files
rather than mocks. The CLI tests use `capsys` to capture stdout
produced by `do_*` methods. No test writes outside its temporary
directory.

### Dependency List

Runtime dependencies:

- **`requests`** (≥2.31) — composes HTTP requests for the crawler.
- **`beautifulsoup4`** (≥4.12) — parses HTML to extract links during
  crawling and to strip markup from page text before indexing.

Development / test dependencies:

- **`pytest`** (≥8.0) — test runner.
- **`pytest-cov`** (≥5.0) — coverage plugin for `pytest`.
- **`responses`** (≥0.25) — mocks the `requests` library so tests
  don't hit the live site.

Pinned versions live in `requirements.txt`. Install all of them at
once with:

```bash
pip install -r requirements.txt
```

### License

This project is licensed under the MIT License — see the `LICENSE`
file for details.
