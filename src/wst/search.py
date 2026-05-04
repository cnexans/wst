"""Semantic search via sentence embeddings stored in SQLite."""

from __future__ import annotations

from wst.db import Database
from wst.models import LibraryEntry

_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def _entry_text(entry: LibraryEntry) -> str:
    m = entry.metadata
    parts = [m.title]
    if m.tags:
        parts.append(", ".join(m.tags))
    if m.summary:
        parts.append(m.summary[:300])
    return " | ".join(parts)


def build_index(db: Database, entries: list[LibraryEntry]) -> int:
    """Embed all entries and persist to the DB embeddings table.

    Returns the number of embeddings stored, or 0 if sentence-transformers
    is not available.
    """
    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
    except (ImportError, OSError):
        return 0

    model = SentenceTransformer(_MODEL_NAME)
    texts = [_entry_text(e) for e in entries]
    embeddings = model.encode(texts, show_progress_bar=False)
    for entry, emb in zip(entries, embeddings):
        db.upsert_embedding(entry.id, emb.astype(np.float32).tobytes())
    return len(entries)


def build_index_from_embeddings(
    db: Database,
    doc_metas: list[dict],
    embeddings,
) -> None:
    """Persist pre-computed numpy embeddings from topics build.

    Called from topics.build_vocabulary() to avoid re-embedding.
    doc_metas must have an 'id' key for each row.
    """
    import numpy as np

    for meta, emb in zip(doc_metas, embeddings):
        db.upsert_embedding(meta["id"], emb.astype(np.float32).tobytes())


def upsert_entry(db: Database, entry: LibraryEntry) -> None:
    """Compute and store/update the embedding for a single entry.

    No-op if the index is empty (not yet built) or if sentence-transformers
    is not installed — callers should not fail on this.
    """
    if db.count_embeddings() == 0:
        return
    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
    except (ImportError, OSError):
        return

    model = SentenceTransformer(_MODEL_NAME)
    emb = model.encode([_entry_text(entry)], show_progress_bar=False)[0]
    db.upsert_embedding(entry.id, emb.astype(np.float32).tobytes())


def search(
    db: Database,
    query: str,
    top_k: int = 50,
) -> list[LibraryEntry] | None:
    """Semantic search over the embedding index.

    Returns a ranked list of LibraryEntry objects, or None when:
    - the index is empty (caller should fall back to FTS), or
    - sentence-transformers is not installed.
    """
    if db.count_embeddings() == 0:
        return None

    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
    except (ImportError, OSError):
        return None

    all_embs = db.load_all_embeddings()
    if not all_embs:
        return None

    doc_ids = list(all_embs.keys())
    emb_matrix = np.stack([np.frombuffer(all_embs[d], dtype=np.float32) for d in doc_ids])

    model = SentenceTransformer(_MODEL_NAME)
    q_emb = model.encode([query], show_progress_bar=False)[0]

    q_norm = float(np.linalg.norm(q_emb))
    if q_norm == 0:
        return None

    norms = np.linalg.norm(emb_matrix, axis=1, keepdims=True)
    sim = (emb_matrix / (norms + 1e-10)) @ (q_emb / q_norm)
    top_indices = np.argsort(sim)[::-1][:top_k]
    ranked_ids = [doc_ids[i] for i in top_indices]

    entries = db.get_by_ids(ranked_ids)
    id_to_entry = {e.id: e for e in entries}
    return [id_to_entry[i] for i in ranked_ids if i in id_to_entry]
