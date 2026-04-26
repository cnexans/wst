"""Topic modeling for the wst library.

Generates a vocabulary of high-level topics (e.g. "Cálculo", "Álgebra Lineal")
from the document corpus using sentence embeddings + KMeans clustering, then lets
an AI backend name each cluster.  Documents are then assigned 1-3 topics from the
fixed vocabulary.
"""

from __future__ import annotations

import json
import re

from wst.ai import AIBackend
from wst.db import Database

# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------


def _build_cluster_naming_prompt(cluster_docs: list[dict]) -> str:
    """Build a prompt asking Claude to name a cluster of documents."""
    docs_str = json.dumps(cluster_docs, ensure_ascii=False, indent=2)
    return f"""You are helping build a topic vocabulary for an academic/personal library.

Below are representative documents from a single cluster (grouped by semantic similarity).
Your task: give this cluster a SHORT, DESCRIPTIVE name (1-3 words in Spanish) that
captures the broad academic/literary area. Examples: "Cálculo", "Álgebra Lineal",
"Literatura Fantástica", "Física Clásica", "Programación", "Economía".

Rules:
- 1 to 3 words maximum.
- In Spanish.
- General / high-level (not a specific subtopic).
- Return ONLY the topic name, nothing else — no explanation, no punctuation, no quotes.

Documents:
{docs_str}"""


def _build_assign_topics_prompt(vocabulary: list[str], doc: dict) -> str:
    """Build a prompt asking Claude to assign topics to a document."""
    vocab_str = ", ".join(f'"{t}"' for t in vocabulary)
    doc_str = json.dumps(doc, ensure_ascii=False, indent=2)
    return f"""You are classifying a document into a fixed topic vocabulary.

Vocabulary (choose only from these): [{vocab_str}]

Document:
{doc_str}

Assign 1 to 3 topics from the vocabulary above that best match this document.
Return ONLY a JSON array of strings, e.g.: ["Cálculo", "Álgebra Lineal"]
No explanation, no extra text."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_vocabulary(
    db: Database,
    ai_backend: AIBackend,
    n_topics: int | None = None,
) -> list[str]:
    """Generate a topic vocabulary from the document corpus.

    Steps:
      1. Extract all documents.
      2. Embed title + tags + summary with a multilingual sentence-transformer.
      3. Determine optimal cluster count (silhouette) or use n_topics.
      4. KMeans clustering.
      5. For each cluster, name it via AI.

    Returns a list of topic name strings (the vocabulary).
    """
    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
        from sklearn.cluster import KMeans  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError(
            f"Topic modeling requires additional dependencies: {e}. "
            "Install them with: pip install sentence-transformers scikit-learn"
        ) from e

    entries = db.list_all()
    if not entries:
        return []

    # Build text representations
    texts: list[str] = []
    doc_metas: list[dict] = []
    for entry in entries:
        m = entry.metadata
        parts = [m.title]
        if m.tags:
            parts.append(", ".join(m.tags))
        if m.summary:
            parts.append(m.summary[:300])
        texts.append(" | ".join(parts))
        doc_metas.append(
            {
                "id": entry.id,
                "title": m.title,
                "tags": m.tags,
                "summary": (m.summary or "")[:200],
            }
        )

    # Embed
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    embeddings = model.encode(texts, show_progress_bar=False)

    n_docs = len(entries)
    if n_docs < 2:
        # Can't cluster a single document — just name it directly
        topic = _name_cluster(ai_backend, doc_metas[:1])
        return [topic]

    # Determine number of clusters
    if n_topics is not None:
        k = max(2, min(n_topics, n_docs))
    else:
        k = _optimal_k(embeddings, min_k=min(2, n_docs), max_k=min(20, n_docs))

    # KMeans clustering
    km = KMeans(n_clusters=k, random_state=42, n_init="auto")
    labels = km.fit_predict(embeddings)
    centroids = km.cluster_centers_

    # For each cluster, find 5 docs closest to centroid
    vocabulary: list[str] = []
    for cluster_idx in range(k):
        mask = labels == cluster_idx
        cluster_indices = np.where(mask)[0]
        cluster_embeddings = embeddings[cluster_indices]
        centroid = centroids[cluster_idx]

        # Distances to centroid
        dists = np.linalg.norm(cluster_embeddings - centroid, axis=1)
        top_n = min(5, len(cluster_indices))
        closest = cluster_indices[np.argsort(dists)[:top_n]]

        cluster_docs = [doc_metas[i] for i in closest]
        topic_name = _name_cluster(ai_backend, cluster_docs)
        vocabulary.append(topic_name)

    return vocabulary


def _optimal_k(embeddings, min_k: int = 2, max_k: int = 20) -> int:
    """Find the optimal number of clusters using the silhouette score."""
    from sklearn.cluster import KMeans  # type: ignore[import-not-found]
    from sklearn.metrics import silhouette_score  # type: ignore[import-not-found]

    best_k = min_k
    best_score = -1.0
    actual_max = min(max_k, len(embeddings) - 1)
    if actual_max < min_k:
        return min_k

    for k in range(min_k, actual_max + 1):
        km = KMeans(n_clusters=k, random_state=42, n_init="auto")
        labels = km.fit_predict(embeddings)
        try:
            score = silhouette_score(embeddings, labels)
        except Exception:
            continue
        if score > best_score:
            best_score = score
            best_k = k

    return best_k


def _name_cluster(ai_backend: AIBackend, cluster_docs: list[dict]) -> str:
    """Ask the AI to name a cluster. Returns a clean 1-3 word string."""
    prompt = _build_cluster_naming_prompt(cluster_docs)
    result = _call_ai_raw(ai_backend, prompt)
    # Clean up any stray whitespace / quotes
    return result.strip().strip('"').strip("'").strip()


def assign_topics(
    db: Database,
    ai_backend: AIBackend,
    vocabulary: list[str],
) -> dict[int, list[str]]:
    """Assign 1-3 topics from vocabulary to every document.

    Returns {doc_id: [topic1, topic2, ...]}
    """
    entries = db.list_all()
    assignments: dict[int, list[str]] = {}

    for entry in entries:
        m = entry.metadata
        doc = {
            "title": m.title,
            "author": m.author,
            "tags": m.tags,
            "summary": (m.summary or "")[:300],
            "subject": m.subject,
        }
        prompt = _build_assign_topics_prompt(vocabulary, doc)
        raw = _call_ai_raw(ai_backend, prompt)
        topics = _parse_json_list(raw, vocabulary)
        assignments[entry.id] = topics  # type: ignore[assignment]

    return assignments


def _call_ai_raw(ai_backend: AIBackend, prompt: str) -> str:
    """Call the AI backend with a raw prompt and return the raw string result."""
    # ClaudeCLIBackend has _run_claude, CodexCLIBackend has _run_codex.
    # We detect via attribute presence.
    if hasattr(ai_backend, "_run_claude"):
        return ai_backend._run_claude(prompt)  # type: ignore[attr-defined]
    if hasattr(ai_backend, "_run_codex"):
        return ai_backend._run_codex(prompt)  # type: ignore[attr-defined]
    raise RuntimeError(f"AI backend {type(ai_backend)} does not expose a raw call method.")


def _parse_json_list(raw: str, vocabulary: list[str]) -> list[str]:
    """Parse a JSON list from raw AI output, validating against vocabulary."""
    raw = raw.strip()
    # Try to extract a JSON array even if there's surrounding text
    match = re.search(r"\[.*?\]", raw, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                # Filter to only valid vocabulary items (case-insensitive)
                vocab_lower = {t.lower(): t for t in vocabulary}
                result = []
                for item in parsed:
                    if isinstance(item, str):
                        canonical = vocab_lower.get(item.strip().lower())
                        if canonical:
                            result.append(canonical)
                if result:
                    return result[:3]
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback: return empty list if parsing fails
    return []


def save_vocabulary(db: Database, vocabulary: list[str]) -> None:
    """Persist the vocabulary in the DB."""
    db.save_topics_vocabulary(vocabulary)


def load_vocabulary(db: Database) -> list[str] | None:
    """Load the persisted vocabulary from the DB (None if not set)."""
    return db.load_topics_vocabulary()
