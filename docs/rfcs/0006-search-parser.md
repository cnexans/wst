# RFC 0006: Structured Search Query Parser

**Issue**: #10  
**Status**: Draft — awaiting approval  
**Branch**: `rfc/issue-10-search-parser`

---

## Problem

Current `wst search` only supports a plain text query passed to SQLite FTS5. There is no way to express structured queries like:

- `author:Knuth` — search by field
- `type:book AND topic:cálculo` — boolean filter
- `"The Art of" year:>1990` — phrase + range
- `calculus NOT numerical` — exclusion

Users must combine separate `--author`, `--type`, `--topic` flags, which is verbose and doesn't compose well (no OR, no NOT, no range operators).

---

## Proposed Solution

Add a **query parser** that interprets a structured query string and translates it to the SQL + FTS5 query. The syntax is inspired by GitHub search and notmuch.

### Query syntax

```
<field>:<value>        field match (exact or LIKE)
"<phrase>"             phrase search in FTS (passed through to FTS5)
<word>                 bare word — FTS full-text search
AND / OR / NOT         boolean operators (case-insensitive)
<field>:><value>       range (year:>2000, year:<1990)
<field>:~<value>       substring match (author:~Knuth)
```

**Supported fields**: `title`, `author`, `type`, `year`, `subject`, `topic`, `tag`, `language`, `isbn`

### Examples

```
wst search 'author:Knuth type:book'
wst search 'topic:cálculo year:>2010'
wst search '"linear algebra" NOT author:Strang'
wst search 'type:paper OR type:guide-theory topic:ML'
```

### Parser design

A simple recursive-descent parser (no external deps) in `src/wst/query_parser.py`:

```python
@dataclass
class ParsedQuery:
    fts_query: str | None        # passed to FTS5 MATCH
    filters: list[SqlFilter]     # AND-combined SQL predicates
    
@dataclass 
class SqlFilter:
    field: str
    op: str       # "=", "LIKE", ">", "<", "!="
    value: str
```

The parser:
1. Tokenizes the input (quoted strings, `field:value` pairs, bare words, operators)
2. Groups bare words and quoted phrases into the FTS query
3. Translates `field:value` pairs into SQL filters
4. Handles `AND`/`OR`/`NOT` at the SQL level for filters; passes AND/NOT into FTS5 syntax for full-text terms

**FTS5 native syntax** is preserved — users can still use `NEAR`, `*` (prefix), etc., as part of the bare-word portion.

### Integration with `db.search()`

Extend the signature:

```python
def search(
    self,
    query: str,                    # now parsed before passing to FTS
    doc_type: str | None = None,   # kept for backward compat
    author: str | None = None,
    subject: str | None = None,
    topic: str | None = None,
    parsed: ParsedQuery | None = None,   # pre-parsed; overrides bare query if provided
) -> list[LibraryEntry]:
```

`wst search` calls `parse_query(query_string)` before calling `db.search()`.

### Backward compatibility

- Bare words without field prefixes continue to work exactly as today
- `--author`, `--type`, `--topic`, `--subject` flags are kept and merged with parsed filters
- If the parser encounters an unrecognized `field:value` pair, it treats it as a bare FTS term (no error)

---

## Scope boundary

This RFC covers the **CLI parser** only. Integration with semantic search (RFC 0005) is a follow-up: eventually `wst search 'topic:cálculo nearest:"integral equations"'` could route part of the query to the embedding index and part to SQL.

---

## Open Questions

> **Q1**: Should the query parser also be exposed via the Tauri app's search bar? The app currently calls `wst search` via CLI, so it would inherit the parser automatically. But the UI search bar might need to teach users the syntax.

> **Q2**: Should `OR` at the top level also apply to field filters (generating SQL `OR` clauses), or only to full-text terms? Full SQL OR support is more complex to implement.

> **Q3**: Should unknown fields (`unknownfield:value`) silently fall back to FTS, or produce a warning? Silent fallback is friendlier; a warning helps catch typos.

> **Q4**: Do you want regex support (`field:~pattern` with regex rather than LIKE)? SQLite supports `REGEXP` if we register a Python function.

---

## Files Changed (implementation phase)

- `src/wst/query_parser.py` (new) — tokenizer, parser, `ParsedQuery`, `parse_query()`
- `src/wst/db.py` — update `search()` to accept and apply `ParsedQuery`
- `src/wst/cli.py` — call `parse_query()` in `wst search` before `db.search()`
- `tests/test_query_parser.py` (new) — unit tests for parser edge cases
