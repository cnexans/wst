"""Query parser for wst search.

Syntax:
  word                  FTS full-text search
  "quoted phrase"       FTS phrase search
  field:value           substring/exact match on field
  field:>value          range comparison (works on year)
  field:~pattern        regex match (case-insensitive)
  AND / OR / NOT        boolean operators (implicit AND between terms)

Supported fields: title, author, type, year, subject, topic, tag, language, isbn

Examples:
  author:Knuth
  type:book topic:algorithms
  author:~Knuth.* year:>1990
  "linear algebra" NOT author:Strang
  type:book OR type:paper
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import field as _field

KNOWN_FIELDS = frozenset(
    {"title", "author", "type", "year", "subject", "topic", "tag", "language", "isbn"}
)

_COL: dict[str, str] = {
    "title": "d.title",
    "author": "d.author",
    "type": "d.doc_type",
    "year": "d.year",
    "subject": "d.subject",
    "topic": "d.topics",
    "tag": "d.tags",
    "language": "d.language",
    "isbn": "d.isbn",
}
_EXACT_FIELDS = frozenset({"type", "isbn"})
_NUMERIC_FIELDS = frozenset({"year"})

# Columns searched when an FTS term must be converted to SQL LIKE (mixed-OR case)
_FALLBACK_COLS = ("d.title", "d.author", "d.tags", "d.subject", "d.summary")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class FieldFilter:
    field: str
    op: str  # "match" | "gt" | "lt" | "gte" | "lte" | "regex"
    value: str


@dataclass
class FtsText:
    text: str  # bare word or "quoted phrase" (quotes preserved)
    negated: bool = False


@dataclass
class QueryTerm:
    bool_op: str | None  # None = first term; "AND" | "OR" for subsequent
    content: FieldFilter | FtsText


@dataclass
class ParsedQuery:
    terms: list[QueryTerm] = _field(default_factory=list)
    warnings: list[str] = _field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.terms


# ---------------------------------------------------------------------------
# Tokenizer + parser
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r'"[^"]*"'  # "quoted phrase"
    r"|(?:AND|OR|NOT)\b"  # boolean operators
    r"|(?:\w[\w-]*):[~<>]?=?[^\s\"]+"  # field:value  (with optional op prefix)
    r"|\S+",  # bare word
    re.IGNORECASE,
)


def parse_query(raw: str) -> ParsedQuery:
    """Parse a query string into a ParsedQuery."""
    pq = ParsedQuery()
    pending_op: str | None = None
    pending_not = False

    for tok in _TOKEN_RE.findall(raw.strip()):
        upper = tok.upper()

        if upper in ("AND", "OR"):
            pending_op = upper
            continue
        if upper == "NOT":
            pending_not = True
            continue

        bool_op = pending_op
        pending_op = None

        # Quoted phrase
        if tok.startswith('"'):
            pq.terms.append(QueryTerm(bool_op, FtsText(tok, negated=pending_not)))
            pending_not = False
            continue

        # Possible field:value
        colon = tok.find(":")
        if colon > 0:
            fname = tok[:colon].lower()
            rest = tok[colon + 1 :]

            if fname not in KNOWN_FIELDS:
                pq.warnings.append(
                    f"Unknown field '{fname}:' — treating as text. "
                    f"Known fields: {', '.join(sorted(KNOWN_FIELDS))}"
                )
                pq.terms.append(QueryTerm(bool_op, FtsText(tok, negated=pending_not)))
                pending_not = False
                continue

            if rest.startswith("~"):
                fop, fval = "regex", rest[1:]
            elif rest.startswith(">="):
                fop, fval = "gte", rest[2:]
            elif rest.startswith("<="):
                fop, fval = "lte", rest[2:]
            elif rest.startswith(">"):
                fop, fval = "gt", rest[1:]
            elif rest.startswith("<"):
                fop, fval = "lt", rest[1:]
            else:
                fop, fval = "match", rest

            # NOT before a field filter is stored as bool_op="NOT"
            effective_op = "NOT" if pending_not else bool_op
            pq.terms.append(QueryTerm(effective_op, FieldFilter(fname, fop, fval)))
            pending_not = False
            continue

        # Bare word
        pq.terms.append(QueryTerm(bool_op, FtsText(tok, negated=pending_not)))
        pending_not = False

    return pq


# ---------------------------------------------------------------------------
# SQL generation
# ---------------------------------------------------------------------------


def to_sql(pq: ParsedQuery) -> tuple[str, list, bool]:
    """Convert a ParsedQuery to a SQL WHERE fragment.

    Returns:
        (where_clause, params, needs_fts_join)

    needs_fts_join=True means the query must JOIN documents_fts.
    """
    if pq.is_empty:
        return "1=1", [], False

    # If any OR bridges a FieldFilter and an FtsText, we cannot use the FTS JOIN
    # (which is AND-combined with the rest of the WHERE). Fall back to SQL LIKE.
    use_fts = not _has_mixed_or(pq.terms)

    sql_parts: list[str] = []
    params: list = []
    fts_tokens: list[tuple[str | None, FtsText]] = []

    for qt in pq.terms:
        if isinstance(qt.content, FieldFilter):
            s, p = _filter_sql(qt.content)
            if qt.bool_op == "NOT":
                s = f"NOT ({s})"
                op = "" if not sql_parts else "AND"
            else:
                op = "" if not sql_parts else (qt.bool_op or "AND")
            _add(sql_parts, params, op, s, p)

        else:  # FtsText
            if use_fts:
                fts_op = None if not fts_tokens else (qt.bool_op or "AND")
                fts_tokens.append((fts_op, qt.content))
            else:
                s, p = _fts_to_like(qt.content)
                op = "" if not sql_parts else (qt.bool_op or "AND")
                _add(sql_parts, params, op, s, p)

    if use_fts and fts_tokens:
        fts_str = _build_fts_str(fts_tokens)
        connector = " AND " if sql_parts else ""
        sql_parts.append(f"{connector}documents_fts MATCH ?")
        params.append(fts_str)

    where = "".join(sql_parts) if sql_parts else "1=1"
    return where, params, use_fts and bool(fts_tokens)


def _add(parts: list, params: list, op: str, sql: str, p: list) -> None:
    parts.append(f" {op} {sql}" if op else sql)
    params.extend(p)


def _filter_sql(f: FieldFilter) -> tuple[str, list]:
    col = _COL[f.field]

    if f.op == "regex":
        return f"{col} REGEXP ?", [f.value]

    if f.field in _NUMERIC_FIELDS:
        op_map = {"match": "=", "gt": ">", "lt": "<", "gte": ">=", "lte": "<="}
        sql_op = op_map.get(f.op, "=")
        try:
            return f"{col} {sql_op} ?", [int(f.value)]
        except ValueError:
            return f"{col} {sql_op} ?", [f.value]

    if f.field in _EXACT_FIELDS or f.op in ("gt", "lt", "gte", "lte"):
        return f"{col} = ?", [f.value.lower() if f.field == "type" else f.value]

    return f"LOWER({col}) LIKE LOWER(?)", [f"%{f.value}%"]


def _fts_to_like(ft: FtsText) -> tuple[str, list]:
    """Broad SQL LIKE across searchable columns (fallback for mixed-OR queries)."""
    raw = ft.text.strip('"')
    conds = " OR ".join(f"LOWER({c}) LIKE LOWER(?)" for c in _FALLBACK_COLS)
    sql = f"({'NOT ' if ft.negated else ''}({conds}))"
    return sql, [f"%{raw}%"] * len(_FALLBACK_COLS)


def _build_fts_str(tokens: list[tuple[str | None, FtsText]]) -> str:
    parts: list[str] = []
    for op, ft in tokens:
        text = ft.text
        if ft.negated:
            text = f"NOT {text}"
        parts.append(f" {op} {text}" if (op and parts) else text)
    return "".join(parts)


def _has_mixed_or(terms: list[QueryTerm]) -> bool:
    """True if an OR operator connects a FieldFilter term and an FtsText term."""
    prev_type: type | None = None
    for qt in terms:
        cur_type = type(qt.content)
        if qt.bool_op == "OR" and prev_type is not None and prev_type is not cur_type:
            return True
        prev_type = cur_type
    return False
