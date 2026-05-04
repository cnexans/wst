# RFC 0003: Subject Assignment by Clustering

**Issue**: #12  
**Status**: Draft — awaiting approval  
**Branch**: `rfc/issue-12-subject-by-clustering`

---

## Problem

Currently, the `subject` field (e.g., "Mathematics", "Computer Science") is assigned by the LLM during `wst ingest`, using only the individual document's content as context. This produces two problems:

1. **Inconsistency across the corpus** — two books on Calculus may get "Mathematics" and "Matemáticas" (or "Cálculo" vs "Math") depending on the document's language and the LLM's mood.

2. **Redundancy with topics** — once `wst topics build` runs, the library already has a curated, consistent topic vocabulary (e.g., "Cálculo", "Álgebra Lineal"). The `subject` field is supposed to be the broader parent area ("Mathematics"), but currently it's set independently and often overlaps with or contradicts the topic assignments.

---

## Proposed Solution

Replace per-document LLM subject inference with **cluster-derived subjects**: after `wst topics build`, assign `subject` values from a small, fixed set of broad academic areas based on the document's assigned topics.

### Two-phase approach

#### Phase 1 — Cluster → broad-area mapping (happens during `wst topics build`)

When the AI names each cluster, also ask it for the cluster's **broad academic area** (1-2 words, e.g., "Mathematics", "Physics", "Computer Science", "Literature"). Store this as a `cluster_subjects` mapping in the `topics_vocabulary` DB row (or as a separate DB table).

Changes to `_build_cluster_naming_prompt` (or a new prompt):

```python
"""...
Also return the BROAD ACADEMIC AREA for this cluster (1-2 words in English,
e.g. "Mathematics", "Computer Science", "Literature", "Physics").
Return as JSON: {"name": "<topic name>", "subject": "<broad area>"}
"""
```

#### Phase 2 — Subject backfill during `wst topics assign`

After topics are assigned to each document, set `subject` from the topic → subject map:

```python
# For each document, pick subject from its primary topic
for doc_id, topics in topic_assignments.items():
    if topics:
        primary_topic = topics[0]
        subject = topic_to_subject.get(primary_topic)
        if subject:
            db.update_subject(doc_id, subject)
```

If a document has multiple topics that map to different subjects (e.g., "Cálculo" → "Mathematics", "Programación" → "Computer Science"), use the subject of the **first (highest-confidence) topic**.

### Backward compatibility

- During `wst ingest`, continue setting `subject` via LLM as today (provides a subject even before topics are built)
- `wst topics assign` (or `wst topics build --assign`) overwrites `subject` with the cluster-derived value
- Add a `--skip-subject` flag to `wst topics assign` for users who want to preserve LLM-generated subjects

### Data model change

Extend the stored vocabulary format from `list[str]` to:

```json
{
  "topics": ["Cálculo", "Álgebra Lineal", "Programación"],
  "subjects": {
    "Cálculo": "Mathematics",
    "Álgebra Lineal": "Mathematics",
    "Programación": "Computer Science"
  }
}
```

Or keep as parallel lists; either way requires a DB schema migration or re-running `wst topics build`.

---

## Open Questions

> **Q1**: Should `subject` be updated automatically when `wst topics assign` runs, or should it require an explicit `--update-subject` flag so users can opt in?

> **Q2**: For documents that haven't been through `wst topics build` yet (newly ingested), should we keep the LLM-generated subject or leave `subject` null until topics are built?

> **Q3**: Should we expose the topic→subject mapping in the CLI for users to inspect or override (e.g., `wst topics subjects`)? This would let users fix cases where the AI mapped "Cálculo" → "Science" instead of "Mathematics".

> **Q4**: The current `topic_to_subject` mapping comes from the AI naming the cluster. Would you prefer a hardcoded allow-list of subjects (e.g., the Dewey decimal top-level categories) to enforce consistency, letting the AI only *choose* from the list?

---

## Files Changed (implementation phase)

- `src/wst/topics.py` — update `_build_cluster_naming_prompt` to also return subject; update `build_vocabulary` to store subject mapping; add `backfill_subjects` function
- `src/wst/db.py` — update `save_topics_vocabulary` / `load_topics_vocabulary` to handle the extended format; add `update_subject(doc_id, subject)`
- `src/wst/cli.py` — update `wst topics build` and `wst topics assign` to run subject backfill
