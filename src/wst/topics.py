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


def _build_cluster_naming_prompt(cluster_docs: list[dict], used_names: list[str] | None = None) -> str:
    """Build a prompt asking Claude to name a cluster of documents."""
    docs_str = json.dumps(cluster_docs, ensure_ascii=False, indent=2)
    used_names_section = ""
    if used_names:
        names_str = ", ".join(used_names)
        used_names_section = f"\nNombres ya usados para otros clusters (NO repetir): {names_str}\n"
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
- Choose a name DIFFERENT from any already-used names listed below.
{used_names_section}
Documents:
{docs_str}"""


def _build_disambiguate_prompt(name: str, docs_a: list[dict], docs_b: list[dict]) -> str:
    """Build a prompt asking the AI to give two different names to two duplicate-named clusters."""
    titles_a = [d["title"] for d in docs_a]
    titles_b = [d["title"] for d in docs_b]
    tags_a = list({tag for d in docs_a for tag in (d.get("tags") or [])})
    tags_b = list({tag for d in docs_b for tag in (d.get("tags") or [])})

    def _fmt(titles: list[str], tags: list[str]) -> str:
        lines = [f"  - {t}" for t in titles]
        if tags:
            lines.append(f"  Tags representativos: {', '.join(tags)}")
        return "\n".join(lines)

    return f"""Tenés dos grupos de documentos que nombraste igual ("{name}").
Necesitás darles nombres DISTINTOS y específicos para diferenciarlos.

Grupo A (documentos):
{_fmt(titles_a, tags_a)}

Grupo B (documentos):
{_fmt(titles_b, tags_b)}

Respondé con exactamente dos nombres, uno por línea, en español, 1-3 palabras cada uno.
No pongas explicaciones, numeración, ni puntuación — solo los dos nombres."""


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
    except (ImportError, OSError) as e:
        import platform
        import sys

        base_msg = (
            f"Topic modeling requires additional dependencies: {e}. "
            "Install them with:\n\n"
            "    pip install 'wst-library[topics]'\n\n"
            "or:\n\n"
            "    pip install sentence-transformers scikit-learn"
        )
        macos_note = ""
        if sys.platform == "darwin" and platform.machine() == "arm64":
            macos_note = (
                "\n\nOn macOS (Apple Silicon) with Python 3.14+ (Homebrew), you may hit a "
                "libexpat version mismatch. Workaround:\n\n"
                "    DYLD_LIBRARY_PATH=/opt/homebrew/Cellar/expat/2.7.5/lib "
                "pip install 'wst-library[topics]'\n\n"
                "Or use the Makefile target:\n\n"
                "    make install-topics"
            )
        raise RuntimeError(base_msg + macos_note) from e

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
    cluster_docs_map: list[list[dict]] = []
    used_names: list[str] = []
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
        # Pass already-assigned names so the AI picks a different one upfront
        topic_name = _name_cluster(ai_backend, cluster_docs, used_names=used_names)
        vocabulary.append(topic_name)
        cluster_docs_map.append(cluster_docs)
        used_names.append(topic_name)

    # Resolve duplicate names (e.g. two clusters both named "Álgebra Lineal")
    _deduplicate_vocabulary(ai_backend, vocabulary, cluster_docs_map)

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


def _name_cluster(
    ai_backend: AIBackend,
    cluster_docs: list[dict],
    used_names: list[str] | None = None,
) -> str:
    """Ask the AI to name a cluster. Returns a clean 1-3 word string.

    Args:
        ai_backend: The AI backend to use.
        cluster_docs: Representative documents for the cluster.
        used_names: Names already assigned to previous clusters so the AI can
            avoid picking the same name again.
    """
    prompt = _build_cluster_naming_prompt(cluster_docs, used_names=used_names)
    result = _call_ai_raw(ai_backend, prompt)
    # Clean up any stray whitespace / quotes
    return result.strip().strip('"').strip("'").strip()


def _deduplicate_vocabulary(
    ai_backend: AIBackend,
    vocabulary: list[str],
    cluster_docs_map: list[list[dict]],
    max_iterations: int = 5,
) -> list[str]:
    """Resolve duplicate topic names in the vocabulary.

    For each group of clusters that share the same name, asks the AI to
    produce distinct replacement names using both clusters' documents as
    context.  Iterates until no duplicates remain or max_iterations is hit.

    Args:
        ai_backend: The AI backend to use for renaming.
        vocabulary: Mutable list of topic names (one per cluster, same order
            as cluster_docs_map).
        cluster_docs_map: List where index i holds the representative docs for
            cluster i — parallel to vocabulary.
        max_iterations: Safety cap to avoid infinite loops (default 5).

    Returns:
        The deduplicated vocabulary (same list object, mutated in-place and
        also returned for convenience).
    """
    for _iteration in range(max_iterations):
        # Build a map: name (lowercased) -> list of indices with that name
        name_to_indices: dict[str, list[int]] = {}
        for idx, name in enumerate(vocabulary):
            key = name.lower()
            name_to_indices.setdefault(key, []).append(idx)

        # Find groups with more than one cluster sharing a name
        duplicates = {k: v for k, v in name_to_indices.items() if len(v) > 1}
        if not duplicates:
            break  # All names are unique — we're done

        for _name_key, indices in duplicates.items():
            # Disambiguate pairs of duplicates sequentially
            # (covers the case where 3+ clusters share the same name)
            while len(indices) > 1:
                idx_a, idx_b = indices[0], indices[1]
                current_name = vocabulary[idx_a]
                docs_a = cluster_docs_map[idx_a]
                docs_b = cluster_docs_map[idx_b]

                prompt = _build_disambiguate_prompt(current_name, docs_a, docs_b)
                raw = _call_ai_raw(ai_backend, prompt)

                # Parse exactly two names (one per line)
                lines = [
                    ln.strip().strip('"').strip("'").strip()
                    for ln in raw.strip().splitlines()
                    if ln.strip()
                ]
                if len(lines) >= 2:
                    vocabulary[idx_a] = lines[0]
                    vocabulary[idx_b] = lines[1]
                else:
                    # Fallback: append a distinguishing suffix so we don't loop forever
                    vocabulary[idx_b] = f"{current_name} II"

                # After resolving this pair, remove them from the indices list
                indices = indices[2:]

    return vocabulary


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
