# RFC 0005: Semantic Embedding Search

**Issue**: #9  
**Status**: Draft — awaiting approval  
**Branch**: `rfc/issue-9-embedding-search`

---

## Problem

Current search (`db.search()`) uses SQLite FTS5 with full-text matching. FTS5 has language-specific limitations:

- **Tokenization is Latin-script biased** — Spanish accented characters (é, ñ, ü), Greek math symbols, and Cyrillic degrade match quality.
- **No synonym matching** — searching "cálculo" won't match a document whose title is "Calculus".
- **No semantic proximity** — "differential geometry" doesn't match "geometría diferencial" even though they're the same topic.
- **No fuzzy matching** — a typo ("calculs") returns zero results.

The issue notes "many bugs for different languages" as the core symptom.

---

## Proposed Solution

Add **semantic embedding search** alongside the existing FTS5 search:

1. At `wst topics build` time (when embeddings are already computed), **persist document embeddings** to a vector index on disk.
2. At search time, embed the query with the same model and **retrieve top-K documents by cosine similarity**.
3. Blend or replace the FTS5 results with embedding results depending on a `--mode` flag.

### Architecture

#### Step 1 — Persist embeddings

During `build_vocabulary` (which already embeds all documents), save the embeddings to a binary file alongside the DB:

```
~/.wst/library/
  wst.db
  embeddings.npy        ← (n_docs, 384) float32 array
  embeddings_ids.json   ← [doc_id, doc_id, ...] ordered parallel to rows
```

Or store in a dedicated SQLite table as BLOB for portability.

**Implementation** (in `topics.py` or a new `search_index.py`):

```python
def save_embeddings(library_path: Path, doc_ids: list[int], embeddings: np.ndarray) -> None:
    np.save(library_path / "embeddings.npy", embeddings.astype(np.float32))
    (library_path / "embeddings_ids.json").write_text(json.dumps(doc_ids))

def load_embeddings(library_path: Path) -> tuple[list[int], np.ndarray] | None:
    emb_path = library_path / "embeddings.npy"
    ids_path = library_path / "embeddings_ids.json"
    if not emb_path.exists() or not ids_path.exists():
        return None
    ids = json.loads(ids_path.read_text())
    emb = np.load(emb_path)
    return ids, emb
```

#### Step 2 — Embed the query at search time

```python
def semantic_search(
    library_path: Path,
    db: Database,
    query: str,
    top_k: int = 20,
) -> list[LibraryEntry]:
    from sentence_transformers import SentenceTransformer
    import numpy as np

    data = load_embeddings(library_path)
    if data is None:
        return []   # fall back to FTS

    doc_ids, embeddings = data
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    q_emb = model.encode([query])[0]

    # Cosine similarity
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    sim = (embeddings / norms) @ (q_emb / np.linalg.norm(q_emb))
    top_indices = np.argsort(sim)[::-1][:top_k]
    ranked_ids = [doc_ids[i] for i in top_indices]

    entries = db.get_by_ids(ranked_ids)
    return sorted(entries, key=lambda e: ranked_ids.index(e.id))
```

#### Step 3 — Add `--mode` to `wst search`

```
wst search "cálculo" --mode fts       # existing behavior (default for now)
wst search "cálculo" --mode semantic  # new embedding-based search
wst search "cálculo" --mode hybrid    # union of both, deduplicated
```

**Default**: keep `fts` as default until embeddings are validated. Users who've run `wst topics build` get `semantic` as the default.

### Model reuse

The same `paraphrase-multilingual-MiniLM-L12-v2` model already used for topics clustering is reused here — no new models or dependencies.

### Dependency

Requires `sentence-transformers` (already in the `[topics]` optional group). Semantic search is only available if the user has installed the topics extras:

```
pip install 'wst-library[topics]'
```

Graceful fallback to FTS if sentence-transformers is unavailable.

---

## Incremental update

When a new document is ingested, its embedding needs to be appended to `embeddings.npy`. Add a `update_embedding(library_path, doc_id, text)` function called from `ingest_file`:

```python
def update_embedding(library_path: Path, doc_id: int, text: str) -> None:
    from sentence_transformers import SentenceTransformer
    emb = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2").encode([text])[0]
    # Append to .npy or rebuild from scratch if small corpus
    ...
```

For simplicity (and because ingesting is rare), **rebuild the full index** on each ingest if it already exists. For large libraries (>1000 docs), incremental append would be better — defer to a follow-up.

---

## Open Questions

> **Q1**: Should `semantic` become the default search mode once embeddings exist, or keep `fts` as default with `--semantic` flag?

> **Q2**: How should we handle the app's search (which calls `wst search` via `run_wst_command`)? Should the app detect if embeddings exist and auto-use semantic mode?

> **Q3**: Should we store embeddings in SQLite as BLOBs (single file, portable) or as `.npy` files (fast, simple, but extra files)? The corpus is small (<10k docs), so either is fine.

> **Q4**: Should we auto-rebuild the embedding index after `wst ingest`, or keep it as an explicit `wst topics build` step?

---

## Files Changed (implementation phase)

- `src/wst/topics.py` — save embeddings at the end of `build_vocabulary`
- `src/wst/db.py` — add `get_by_ids(ids: list[int])` method
- `src/wst/cli.py` — add `--mode` option to `wst search`; add `semantic_search` function or module
- `src/wst/search.py` (new) — `semantic_search`, `save_embeddings`, `load_embeddings`
