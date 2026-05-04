# RFC 0001: Soft/Fuzzy Clustering for Topic Vocabulary

**Issue**: #7  
**Status**: Draft — awaiting approval  
**Branch**: `rfc/issue-7-soft-clustering`

---

## Problem

The current `build_vocabulary` in `src/wst/topics.py` uses **KMeans** (hard clustering): each document belongs to exactly one cluster. This causes two concrete problems:

1. **Incoherent border clusters** — a document like "Vector Calculus, Linear Algebra and Differential Forms" gets arbitrarily assigned to a single cluster, polluting it with mixed signals and producing a catch-all label like "Cálculo Multivariable" that doesn't accurately represent the cluster's core.

2. **Near-duplicate topic names** — because mixed-signal documents push cluster centroids toward each other, the AI ends up naming two clusters almost identically (e.g., "Cálculo" and "Cálculo Multivariable"), creating a noisy vocabulary.

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

### 5. Update CLI (`wst topics build`)

Add `--method` option:

```python
@click.option("--method", default="gmm", type=click.Choice(["gmm", "kmeans"]),
              help="Clustering method (default: gmm)")
```

### 6. No changes to `assign_topics`

Topic assignment is a separate step and already uses the AI with the fixed vocabulary — no changes needed there.

---

## Migration / Backward Compatibility

- Existing vocabularies in the DB are unaffected; `wst topics build` rebuilds from scratch anyway
- Default changes from `kmeans` → `gmm`; users who want the old behavior can pass `--method kmeans`

---

## Open Questions

> **Q1**: Should we also support HDBSCAN as `--method hdbscan` in the same PR, or defer to a follow-up? HDBSCAN adds useful outlier handling for heterogeneous corpora but is more complex to implement and test.

> **Q2**: Do you want `gmm` to be the new default immediately, or keep `kmeans` as default with `gmm` opt-in until we validate quality on your corpus?

> **Q3**: Should we expose the `n_topics` cap differently for GMM? With GMM + BIC, very large `k` values are penalized automatically, so `--n-topics` could remain as an upper bound rather than an exact target.

---

## Files Changed (implementation phase)

- `src/wst/topics.py` — add GMM clustering, update `build_vocabulary`, add `_optimal_k_gmm`, `_soft_cluster_gmm`
- `src/wst/cli.py` — add `--method` option to `wst topics build`
- `tests/test_topics.py` — unit tests for GMM path (if test file exists)
