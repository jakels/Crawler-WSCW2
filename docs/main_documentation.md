# `main.py` — Documentation

## Overview

`main.py` is the user-facing entry point: a REPL that exposes the
four commands required by the brief — `build`, `load`, `print`,
`find` — plus `help` and `quit`. It is a thin shell over the three
underlying modules:

```
   user input
       │
       ▼
  SearchShell  ──►  Crawler  (build only)
       │      ──►  Indexer   (build, load, and used by SearchEngine)
       ▼
  SearchEngine  ──►  print_term, find
```

The shell holds *no* search logic of its own. Every command is a
short orchestration of crawler/indexer/engine calls plus user-facing
formatting. That separation is what makes the indexer and search
modules testable in isolation, and it's what makes `main.py` itself
testable by driving `do_*` methods directly without spawning a
subprocess.

## Module-level constants

### `INDEX_PATH`

Default path the index is saved to and loaded from
(`data/index.json`). Defined at module scope so test code can
`monkeypatch` it onto a `tmp_path` and exercise `do_build` /
`do_load` against a throwaway location.

## Class: `SearchShell(cmd.Cmd)`

Subclasses `cmd.Cmd` from the standard library. The `cmd` module
gives us:

- A REPL loop (`cmdloop()`).
- Tab completion for command names.
- `help <command>` that prints each method's docstring.
- `EOF` (Ctrl-D) handling routed to `do_EOF`.

Using `cmd` rather than a hand-rolled `while True: input()` loop is
the same kind of "use the standard library well" choice the rubric
rewards under "Python best practices".

### `intro` and `prompt`

Class-level attributes consumed by `cmd.Cmd`. `intro` is printed
once when `cmdloop` starts; `prompt` precedes every input.

### `__init__(self, *args, **kwargs)`

Calls `super().__init__` (so `cmd.Cmd` can wire up readline etc.),
then initialises:

- `self.index` — an empty `Indexer`.
- `self.search_engine` — `None` until an index is built or loaded.
  The `None` sentinel is what `_require_index` checks for.

### `do_build(self, arg) -> None`

Implements `build [fresh]`.

Step by step:

1. Parse `arg` for the optional `fresh` flag. When present, the
   crawler is constructed with `use_cache=False` so every URL is
   re-fetched from the live site (respecting the 6-second politeness
   window).
2. Print a status message announcing the crawl.
3. Construct a `Crawler` and call `crawl()` to obtain
   `{url: html}`.
4. Print the page count.
5. Construct a fresh `Indexer` (so a previous index in memory is
   discarded), call `build(pages)`, then `save(INDEX_PATH)`.
6. Construct a `SearchEngine` over the new index and store it on
   `self`. From now on, `find` and `print` will work.
7. Print a final summary: documents indexed and vocabulary size.

### `do_load(self, arg) -> None`

Implements `load`.

Step by step:

1. Check the index file exists. If not, print a friendly error
   pointing at the `build` command and return.
2. Construct a fresh `Indexer` and call `load(INDEX_PATH)`.
3. Construct a `SearchEngine`.
4. Print a summary.

`load` deliberately does not call the crawler. It is the cheap path
for resuming work between sessions.

### `do_print(self, arg) -> None`

Implements `print <word>`.

Step by step:

1. `_require_index()` — refuse if nothing is loaded.
2. Refuse with a usage hint if `arg` is empty after stripping.
3. Delegate to `self.search_engine.print_term(arg)` and print the
   returned string.

The `print_term` call does its own tokenisation, so we pass `arg`
through untouched and let the search layer canonicalise.

### `do_find(self, arg) -> None`

Implements `find <query>`.

Step by step:

1. `_require_index()`.
2. Refuse on empty input with a usage hint.
3. Call `self.search_engine.find(query)`.
4. If empty, print `"No results for '...'"`.
5. Otherwise print a header and one numbered line per result, with
   the URL and the TF-IDF score formatted to four decimals. Numbered
   lines make the output feel like a search-engine result page and
   make it easier to refer to a specific hit during the video demo.

### `do_quit(self, arg) -> bool`

Implements `quit` (and, via the aliases below, `exit` and EOF).
Prints `"Goodbye."` and returns `True`. In `cmd.Cmd`, a truthy
return from a `do_X` method exits `cmdloop`.

### Aliases: `do_exit`, `do_EOF`

Both bound to `do_quit`. `do_EOF` is what `cmd` calls when the user
hits Ctrl-D, so binding it to `do_quit` makes Ctrl-D exit cleanly
instead of leaving the REPL in a weird state.

### `emptyline(self) -> None`

Overrides the default `cmd.Cmd` behaviour, which is to repeat the
last command on a blank line. Repeating a `find` is rarely what the
user meant, so we make blank input do nothing.

### `default(self, line: str) -> None`

Called by `cmd.Cmd` when the user types a command we don't
recognise. Prints a friendly `"Unknown command: 'X'. Type 'help'"`
message instead of `cmd`'s default cryptic error.

### `_require_index(self) -> bool`

Single source of truth for the "is an index loaded?" check. Returns
`True` if `self.search_engine` is set; otherwise prints a hint and
returns `False`. Centralising this means `do_find` and `do_print`
share one consistent error message and one consistent behaviour, so
adding a third query command later costs one line.

## Function: `main() -> None`

The script entry point.

Step by step:

1. Configure logging at WARNING level so user-facing CLI output
   isn't drowned by INFO messages from the crawler/indexer. Anyone
   debugging can flip to INFO with one edit.
2. Construct a `SearchShell` and run `cmdloop()`.
3. Catch `KeyboardInterrupt` (Ctrl-C) so the shell exits gracefully
   with a `\nInterrupted.` message rather than dumping a traceback.
   Exits with code `130` (the conventional shell exit code for
   "killed by SIGINT").

## `if __name__ == "__main__": main()`

Standard guard so `main.py` runs the REPL when executed directly
(`python -m src.main`) but importing `src.main` from a test module
doesn't accidentally start the loop.

## Design rationale (talking points for the video)

- **`cmd.Cmd` over a hand-rolled loop.** Free history, completion,
  help. Less code that can have bugs.
- **`SearchEngine` constructed inside the shell, not module-global.**
  Keeps state per-instance, which is what made `test_main.py` clean
  to write.
- **`INDEX_PATH` as a module-level constant.** Tests `monkeypatch` it
  to a `tmp_path` so they exercise `do_build` and `do_load` against
  a real (throwaway) file system, not a mock.
- **Separation between shell formatting and search logic.** The shell
  decides how a result *looks* (numbering, score precision); the
  engine decides which results *exist* and in what order. Either can
  be swapped without touching the other.
- **`_require_index` as a single guard.** One call site per
  command, one consistent error message.
- **Graceful Ctrl-C handling in `main`.** Small touch, but it's what
  separates "this looks like a tool" from "this looks like a script".