# RFC 0005: Semantic Embedding Search (multilingual)

**Issue**: #9  
**Status**: Approved — implementation in progress  
**Branch**: `rfc/issue-9-embedding-search`

---

## Problem

Current search uses SQLite FTS5, which has language-specific limitations:

- Tokenization is Latin-script biased — accented characters (é, ñ) degrade match quality.
- No synonym matching — "cálculo" won't match a document titled "Calculus".
- No semantic proximity — "differential geometry" doesn't match "geometría diferencial".
- Typos return zero results.

---

## Approved Solution

Add semantic embedding search as the **default mode** when an index exists:

1. `wst topics build` computes all document embeddings (already done) and persists them to a new `embeddings` SQLite table as BLOB columns.
2. `wst search` detects if the index exists and uses cosine-similarity search by default; falls back to FTS if not.
3. New documents added via `wst ingest` are automatically embedded and added to the index (if it already exists).
4. `wst search --mode fts` forces FTS for users who need keyword-exact behavior.

### Approved answers

- **Q1**: Semantic is default when the index exists; `--mode fts` overrides.
- **Q2**: App auto-uses semantic — since `wst search` auto-detects, `run_wst_command` requires no changes.
- **Q3**: SQLite BLOBs — embeddings stored in `embeddings` table, single file, portable.
- **Q4**: Incremental — after `wst ingest`, the new doc is added to the existing index automatically.

### Storage: `embeddings` table

```sql
CREATE TABLE IF NOT EXISTS embeddings (
    doc_id INTEGER PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    embedding BLOB NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

Each embedding is a `float32` numpy array serialized via `.tobytes()` (~1.5 KB per doc for 384-dim). `ON DELETE CASCADE` keeps the index clean when documents are deleted.

### Search flow

```
wst search "cálculo diferencial"
  └─ mode == "auto" AND query non-empty AND db.count_embeddings() > 0?
       yes → semantic search
               → embed query with SentenceTransformer (multilingual)
               → cosine similarity over all stored embeddings
               → apply field filters (--type, --author, etc.) in memory
               → return ranked LibraryEntry list
       no  → db.search() FTS fallback (existing behavior)
```

### Reuse existing model

`paraphrase-multilingual-MiniLM-L12-v2` (already in `[topics]` extras) is reused — no new dependencies.

---

## Files Changed

- `src/wst/search.py` (new) — `build_index`, `build_index_from_embeddings`, `upsert_entry`, `search`
- `src/wst/db.py` — add `embeddings` table with FK cascade, enable FK enforcement, `upsert_embedding`, `load_all_embeddings`, `count_embeddings`, `get_by_ids`
- `src/wst/topics.py` — save embeddings to DB at the end of `build_vocabulary`
- `src/wst/ingest.py` — call `search.upsert_entry` after inserting a new document
- `src/wst/cli.py` — add `--mode auto|fts|semantic` to `wst search`; route through semantic when index exists
