"""Command-line shell for the search engine.

Implements the four commands required by the brief — ``build``,
``load``, ``print``, ``find`` — as a ``cmd.Cmd`` subclass. Using the
standard library's ``cmd`` module gives us tab completion, command
history, and ``help <command>`` for free, and keeps the file structure
clean (one ``do_X`` method per command, with the docstring serving as
the help text).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import cmd

from src.crawler import Crawler
from src.indexer import Indexer
from src.search import SearchEngine

# Path of the on-disk index. Module-level so tests can monkeypatch it.
INDEX_PATH = Path("data/index.json")


class SearchShell(cmd.Cmd):
    """Interactive shell exposing build / load / print / find."""

    intro = (
        "Quotes search engine.\n"
        "Commands: build, load, print <word>, find <query>, help, quit.\n"
        'Tip: wrap a query in double quotes for phrase search '
        '(find "good friends").'
    )
    prompt = "> "

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.index: Indexer = Indexer()
        self.search_engine: SearchEngine | None = None

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    def do_build(self, arg: str) -> None:
        """build [fresh]: crawl the site, build the index, and save it.
        Pass 'fresh' to bypass the HTML cache and re-crawl from the
        live site."""
        use_cache = "fresh" not in arg.lower().split()
        if use_cache:
            print("Crawling (cached HTML will be reused where available)...")
        else:
            print("Crawling fresh — this will respect the 6s politeness window.")

        crawler = Crawler(use_cache=use_cache)
        pages = crawler.crawl()
        print(f"Fetched {len(pages)} pages.")

        print("Building inverted index...")
        self.index = Indexer()
        self.index.build(pages)

        print(f"Saving index to {INDEX_PATH}...")
        self.index.save(INDEX_PATH)

        self.search_engine = SearchEngine(self.index)
        print(
            f"Done. {self.index.doc_count} documents, "
            f"{len(self.index)} unique terms."
        )

    def do_load(self, arg: str) -> None:
        """load: load a previously built index from disk."""
        if not INDEX_PATH.exists():
            print(f"No index found at {INDEX_PATH}. Run 'build' first.")
            return
        self.index = Indexer()
        self.index.load(INDEX_PATH)
        self.search_engine = SearchEngine(self.index)
        print(
            f"Loaded {self.index.doc_count} documents, "
            f"{len(self.index)} unique terms from {INDEX_PATH}."
        )

    def do_print(self, arg: str) -> None:
        """print <word>: print the inverted-index entry for a word."""
        if not self._require_index():
            return
        if not arg.strip():
            print("Usage: print <word>")
            return
        assert self.search_engine is not None  # narrowed by _require_index
        print(self.search_engine.print_term(arg))

    def do_find(self, arg: str) -> None:
        """find <query>: list pages matching <query>, ranked by TF-IDF.

        Plain query (find good friends) returns pages containing every
        term anywhere in the document. Quoted query (find "good
        friends") returns only pages where the terms appear adjacent
        in that order — phrase search."""
        if not self._require_index():
            return
        query = arg.strip()
        if not query:
            print('Usage: find <query>  (or  find "<phrase>"  for phrase search)')
            return
        assert self.search_engine is not None
        results = self.search_engine.find(query)
        if not results:
            print(f"No results for '{query}'.")
            return
        print(f"Found {len(results)} result(s) for '{query}':")
        for rank, (url, score) in enumerate(results, start=1):
            print(f"  {rank}. {url}  (score: {score:.4f})")

    def do_quit(self, arg: str) -> bool:
        """quit: exit the shell."""
        print("Goodbye.")
        return True

    # Aliases so users can type whatever feels natural.
    do_exit = do_quit
    do_EOF = do_quit  # Ctrl-D

    # ------------------------------------------------------------------
    # cmd.Cmd hooks
    # ------------------------------------------------------------------
    def emptyline(self) -> None:
        """Override default cmd behaviour of repeating the last command."""
        return None

    def default(self, line: str) -> None:
        """Handle any command we didn't define."""
        token = line.split()[0] if line.strip() else ""
        print(f"Unknown command: '{token}'. Type 'help' for available commands.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _require_index(self) -> bool:
        """True if an index is loaded; otherwise prints a hint and False."""
        if self.search_engine is None:
            print("No index loaded. Run 'build' first, or 'load' to read a saved one.")
            return False
        return True


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    shell = SearchShell()
    try:
        shell.cmdloop()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)


if __name__ == "__main__":
    main()