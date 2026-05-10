# `tokeniser.py` — Documentation

## Overview

`tokeniser.py` exposes a single function, `tokenise`, that converts a
string of text into an ordered list of lowercase word tokens.

The tokeniser is its own module rather than a method on the indexer
because **both the indexer and the search layer must tokenise
identically**. The indexer tokenises page text during `build`; the
search layer tokenises the user's query during `find`. If the two
diverge — e.g. one strips apostrophes and the other keeps them — then
`find don't` won't match a document that contains "don't", and the
search engine silently fails. Sharing one function eliminates that
class of bug by construction.

## Module-level constants

### `_TOKEN_RE`

```python
re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
```

A pre-compiled regular expression that matches a single token.
Pre-compiling at module load avoids re-parsing the pattern on every
call.

Pattern, piece by piece:

- `[a-z0-9]+` — one or more letters or digits. The leading character
  of every token. The bracket class is lowercase only because
  `tokenise` lowercases its input before matching, so we never need
  to consider uppercase.
- `(?:'[a-z]+)?` — an *optional, non-capturing* group consisting of
  an apostrophe followed by one or more letters. This is how
  contractions like `don't` and `it's` survive as single tokens.
- Standalone apostrophes (e.g. quote marks around words: `'quoted'`)
  are *not* matched, because they aren't preceded by a letter/digit
  inside the same match. They become token boundaries instead.

## Function: `tokenise(text) -> list[str]`

Returns the ordered list of word tokens in `text`.

Step by step:

1. Guard: if `text` is empty (or any falsy value), return `[]`. This
   short-circuits a regex call we don't need.
2. Lowercase the entire input with `text.lower()`. Doing it once,
   here, means everything downstream — the regex, the index lookup,
   user queries — can be case-insensitive without any extra work.
3. Run `_TOKEN_RE.findall(...)`, which returns every non-overlapping
   match in document order. That ordering is essential: the indexer
   uses `enumerate()` over the result to record each token's
   position, which the phrase-search feature relies on.
4. Return the list.

## Worked examples

| Input                                | Output                                            |
|--------------------------------------|---------------------------------------------------|
| `"Hello, world!"`                    | `["hello", "world"]`                              |
| `"Hello WORLD Hello"`                | `["hello", "world", "hello"]`                     |
| `"don't won't it's"`                 | `["don't", "won't", "it's"]`                      |
| `"'quoted' words"`                   | `["quoted", "words"]`                             |
| `"Year 1984 was 40 years ago"`       | `["year", "1984", "was", "40", "years", "ago"]`   |
| `""`                                 | `[]`                                              |
| `"!!! ... ???"`                      | `[]`                                              |

## Design rationale

- **Lowercase everything.** The brief explicitly says search is not
  case-sensitive, so canonicalising at tokenisation time is the
  cheapest place to enforce it.
- **Keep digits.** Quotes contain dates and numbers; `find 1984`
  should work.
- **Keep contractions whole.** A naive split-on-non-word would turn
  `don't` into `don` and `t`, polluting the index with thousands of
  bogus single-letter `t` tokens. Keeping `don't` whole is both
  intuitive for users and keeps the index cleaner.
- **No stemming.** Stemming (`running` → `run`) is a defensible
  upgrade, but it complicates the implementation, makes `print`
  output less obvious, and the brief's example queries
  (`indifference`, `nonsense`, `good friends`) don't depend on it.
  Worth flagging in the video as a deliberate trade-off.
- **No stopword removal.** The brief's example `find good friends`
  treats `good` as a content word; aggressive stopword lists
  sometimes drop it. Indexing every token keeps behaviour predictable.