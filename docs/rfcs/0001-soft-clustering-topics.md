# RFC 0001: Soft/Fuzzy Clustering for Topic Vocabulary

**Issue**: #7
**Status**: Draft — awaiting approval (revised after RFC 0011)
**Branch**: `rfc/issue-7-soft-clustering`

---

## Problem

The current `build_vocabulary` in `src/wst/topics.py` uses **KMeans** (hard clustering): each document belongs to exactly one cluster. This causes two concrete problems:

1. **Incoherent border clusters** — a document like "Vector Calculus, Linear Algebra and Differential Forms" gets arbitrarily assigned to a single cluster, polluting it with mixed signals and producing a catch-all label like "Cálculo Multivariable" that doesn't accurately represent the cluster's core.

2. **Near-duplicate topic names** — because mixed-signal documents push cluster centroids toward each other, the AI ends up naming two clusters almost identically (e.g., "Cálculo" and "Cálculo Multivariable"), creating a noisy vocabulary.

### Relationship to RFC 0011

RFC 0011 (content_preview ladder) lands a richer per-document signal: the embedding text is now `title | tags | content_preview[:1500]` (drawn from summary → TOC → intro chapter → first pages) instead of `title | tags | summary[:300]`. **That fix raises signal quality but does not change which clustering algorithm runs.** The two failure modes above persist for genuinely multi-topic documents — a calculus + linear algebra textbook still has one centroid in KMeans, no matter how rich its `content_preview` is. Richer signal means cluster *positions* are better; soft clustering means *membership* can be split when a document legitimately spans topics.

This RFC therefore complements RFC 0011 rather than competing with it. The implementation plan below assumes the post-0011 codebase (`build_vocabulary` reads `m.content_preview` with summary fallback; the per-doc dict passed to the naming prompt includes `content_preview[:600]`).

---

## Proposed Solution

Replace KMeans with **soft (probabilistic) clustering** so that multi-topic documents can influence multiple cluster names without distorting any single one.

### Option A — Gaussian Mixture Model (GMM)
- `sklearn.mixture.GaussianMixture` (already in scikit-learn, no new deps)
- Returns `predict_proba(embeddings)` → shape `(n_docs, k)` membership probabilities
- Name each cluster using documents with highest probability for that component
- Optimal `k` selection: use BIC (lower = better) instead of silhouette

### Option B — HDBSCAN with soft clustering
- `sklearn.cluster.HDBSCAN` (available in scikit-learn ≥ 1.3, already required)
- `membership_vector` from `hdbscan.membership_vector()` gives soft probabilities
- Does not require specifying `k` upfront — discovers it from data density
- Handles outliers (low-probability documents don't distort any cluster name)

### Recommendation

**Use GMM as the default, keep KMeans as a fallback.**

Rationale:
- GMM is a direct drop-in that requires zero new dependencies (scikit-learn is already required)
- BIC-based model selection is more principled than silhouette for GMMs
- HDBSCAN's outlier handling is powerful but adds implementation complexity and may produce very small clusters for small corpora
- KMeans is preserved as `--method kmeans` for users who want the current behavior

---

## Implementation Plan

### 1. Add `method` parameter to `build_vocabulary`

```python
def build_vocabulary(
    db: Database,
    ai_backend: AIBackend,
    n_topics: int | None = None,
    method: str = "gmm",   # "gmm" | "kmeans"
) -> tuple[list[str], dict[int, list[str]]]:
```

### 2. Implement `_soft_cluster_gmm`

```python
def _soft_cluster_gmm(embeddings, k: int) -> np.ndarray:
    """Returns (n_docs, k) probability matrix."""
    from sklearn.mixture import GaussianMixture
    gmm = GaussianMixture(n_components=k, random_state=42, n_init=3)
    gmm.fit(embeddings)
    return gmm.predict_proba(embeddings)
```

### 3. Implement `_optimal_k_gmm`

Use BIC score instead of silhouette (lower BIC = better fit):

```python
def _optimal_k_gmm(embeddings, min_k: int = 2, max_k: int = 20) -> int:
    from sklearn.mixture import GaussianMixture
    best_k, best_bic = min_k, np.inf
    for k in range(min_k, min(max_k, len(embeddings) - 1) + 1):
        gmm = GaussianMixture(n_components=k, random_state=42, n_init=3)
        gmm.fit(embeddings)
        bic = gmm.bic(embeddings)
        if bic < best_bic:
            best_bic, best_k = bic, k
    return best_k
```

### 4. Update cluster representative selection

Instead of picking documents closest to the centroid (Euclidean distance), pick the top-N documents by **membership probability** for each cluster:

```python
# For cluster i:
probs_for_cluster = prob_matrix[:, i]
top_indices = np.argsort(probs_for_cluster)[::-1][:5]
cluster_docs = [doc_metas[j] for j in top_indices]
```

This ensures that only documents that strongly belong to a cluster contribute to its name — cross-topic documents are included in multiple clusters with lower weight, but their probability rank keeps them from dominating any single cluster's name.

The `doc_metas` entry already carries `content_preview[:600]` after RFC 0011, so the cluster-naming prompt automatically gets richer per-doc context for whichever documents this step picks. **No change to the naming prompt itself is needed** — only the *selection* of representatives changes, not what gets shown to the AI.

### 5. Update CLI (`wst topics build`)

Add `--method` option:

```python
@click.option("--method", default="gmm", type=click.Choice(["gmm", "kmeans"]),
              help="Clustering method (default: gmm)")
```

### 6. Soft topic assignment (optional, off by default)

`assign_topics` currently asks the AI to pick 1–3 topics from the vocabulary per document. A natural extension under GMM is to skip the AI call for documents whose membership probability vector is unambiguous (one component dominates) and only invoke the AI for genuinely cross-topic documents. This is **out of scope for the first cut** — the easiest path is to keep `assign_topics` as-is and only change `build_vocabulary`. Revisit if AI-call cost becomes the bottleneck.

### 7. Multi-topic disambiguation cap

GMM raises the chance that a document gets credible probability for ≥3 components. The existing per-document `topics` cap (3) in `_parse_json_list` ([`topics.py`](../../src/wst/topics.py)) is unchanged; the AI is still the gatekeeper for which topics get attached to a document. The probability matrix is used **only** for cluster *naming*, not for assignment.

---

## Migration / Backward Compatibility

- Existing vocabularies in the DB are unaffected; `wst topics build` rebuilds from scratch anyway
- Default changes from `kmeans` → `gmm`; users who want the old behavior can pass `--method kmeans`

---

## Open Questions

> **Q1**: Should we also support HDBSCAN as `--method hdbscan` in the same PR, or defer to a follow-up? HDBSCAN adds useful outlier handling for heterogeneous corpora but is more complex to implement and test.

> **Q2**: Do you want `gmm` to be the new default immediately, or keep `kmeans` as default with `gmm` opt-in until we validate quality on your corpus? Now that RFC 0011 has improved input signal, the validation can compare three runs on the user's corpus: (a) KMeans + summary (pre-0011), (b) KMeans + content_preview (current), (c) GMM + content_preview (this RFC) — using the same library snapshot.

> **Q3**: Should we expose the `n_topics` cap differently for GMM? With GMM + BIC, very large `k` values are penalized automatically, so `--n-topics` could remain as an upper bound rather than an exact target.

> **Q4**: Should representative-doc selection prefer documents whose `content_preview_source` is high-quality (e.g. `intro` or `toc` over `title-only`)? A doc whose preview is just title+tags has thinner cluster-naming signal even if its membership probability is high. Proposal: tie-break by source quality only when the top membership-probability slot would otherwise be filled by a `title-only` / `none` doc, since those carry minimal information for the AI naming prompt.

---

## Files Changed (implementation phase)

- `src/wst/topics.py` — add GMM clustering, update `build_vocabulary` (the post-0011 version that already reads `m.content_preview`), add `_optimal_k_gmm` and `_soft_cluster_gmm`. Representative-doc selection switches from Euclidean-to-centroid to membership-probability ranking.
- `src/wst/cli.py` — add `--method` option to `wst topics build`. The existing content_preview backfill step (RFC 0011) runs unchanged before clustering.
- `tests/test_topics.py` — unit tests for the GMM path (parallel to the existing KMeans tests).
