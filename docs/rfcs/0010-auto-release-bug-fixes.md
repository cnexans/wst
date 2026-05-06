# RFC 0010: Auto-release bug fixes (skip-ci leak + squash-bullet parser)

**Issue**: #27
**Status**: Implementing
**Branch**: `rfc/27-skip-ci-and-squash-parser`

**Resolutions** (from #27 comments):
- **Q1**: Drop `[skip ci]` entirely; rely on the actor+message guard.
- **Q2**: Manually push `v0.11.0` at `ad48d8c` to ship #26's intended smoke-test release.

---

## Problem

Two bugs in `auto-release.yml` (introduced in #25 / commit `ad48d8c`) caused the smoke-test release to silently fail:

### Bug 1 — `[skip ci]` leaked from prose into a real commit message

PR #26's squash-merge commit body contains the literal string `[skip ci]` in an explanatory sentence: *"commit as github-actions[bot] with `[skip ci]`, push vX.Y.Z tag."* GitHub honors `[skip ci]` on **any line** of the commit message. Result: zero workflows fired for `ad48d8c` — neither `Auto Release` nor `CI`.

This will keep happening any time prose about the workflow's behavior gets squashed into a real commit message.

### Bug 2 — Conventional-Commits parser doesn't handle squash-merge bullets

`auto-release.yml` greps for `^(feat|fix|perf)…:` against `git log --format='%s%n%b%n---' BEFORE..AFTER`. GitHub's "Squash and merge" produces a commit with each squashed source commit prefixed with `* `:

```
RFC: Reliable releases on merge to main (#26)

* rfc: reliable releases on merge to main (#25)
* rfc: address review feedback (#25)
* feat(ci): auto-bump version on merge via Conventional Commits
   …body…
```

The `^` anchor never matches the bulleted line because of the leading `* `. The squash subject (`RFC: …`) doesn't match either. So even if Bug 1 hadn't fired, no version bump would have happened.

---

## Proposed Solution

Two small changes to `auto-release.yml`, plus a project-wide convention.

### Fix 1 — Strip `* ` bullets before grepping (and broaden the prefix scan)

Pre-process the commit messages to remove leading `* ` (squash-merge bullet) and leading whitespace, then run the same regex:

```bash
MESSAGES=$(git log --format='%s%n%b%n---' "$BEFORE..$AFTER" \
  | sed 's/^[[:space:]]*\* //')
```

After the strip, both `* feat(ci): …` and a plain `feat(ci): …` line match `^(feat|fix|perf)…`.

### Fix 2 — Recognize non-literal `[skip ci]` mentions safely

Two layers, defense-in-depth:

1. **Don't put `[skip ci]` in any commit message we don't actually want skipped.** Update PR templates / RFC writing guidance to escape the token in prose: write it as `[skip-ci]` (hyphenated) or wrap it in a code fence the squash strips out, or simply spell it differently in narrative ("the workflow appends a CI-skip directive").
2. **Workflow-level guard:** before triggering a release, the workflow can re-check the head commit message for an *unintended* `[skip ci]`. There is no clean way to tell intent apart from accident inside the workflow itself, so the only mechanically-safe option is **stop using `[skip ci]` for the auto-bump commit** — switch to the actor-+-message recursion guard alone:

```yaml
if: |
  !(github.actor == 'github-actions[bot]'
    && startsWith(github.event.head_commit.message, 'chore: bump version to'))
```

The actor check is sufficient on its own — `github-actions[bot]` only authors the bump commit, and the subject prefix is unique. Removing `[skip ci]` from the bump commit message means we no longer have to worry about *anyone* accidentally quoting that token in any future commit.

### Convention

Add a one-paragraph note to the `Releasing` section of `README.md`: *"Don't include the literal token `[skip ci]` (with brackets and a space) in commit messages or PR descriptions for changes that should run CI. GitHub interprets it anywhere in the message and silently skips all workflows."*

---

## Alternatives Considered

| Alternative | Why rejected |
|---|---|
| Keep `[skip ci]` on the bump commit AND the actor guard, just escape the token in prose | The escape is fragile — relies on every future contributor (and Claude) to remember. The actor guard alone is just as safe. |
| Detect `[skip ci]` in commit body via a pre-flight workflow that fails noisily | Doesn't help: GitHub already swallows the workflow before the pre-flight runs. |
| Switch from "Squash and merge" to "Rebase and merge" or "Create a merge commit" | Bigger workflow change; would also lose the clean per-PR commit summary. The bullet-strip fix is one line of `sed`. |
| Require all PR titles to start with a Conventional-Commits prefix | Reasonable hygiene but doesn't help RFC PRs that don't ship code (`RFC:` is a perfectly valid title for a doc-only PR). The bullet-strip fix removes the reliance on PR-title convention. |

---

## Implementation Plan

- [ ] Add `sed 's/^[[:space:]]*\* //'` strip to the `Determine bump kind from commits` step in `auto-release.yml`.
- [ ] Remove `[skip ci]` from the bump commit message; keep the `github-actions[bot]` actor + `chore: bump version to` subject guard as the sole recursion check.
- [ ] Update `README.md`'s Releasing section with the no-`[skip ci]`-in-prose note.
- [ ] After the fixes merge, manually push `v0.11.0` at `ad48d8c` (or the merge commit of this PR if a fresh tag is cleaner) to validate the end-to-end bump-and-release pipeline by shipping #26's intended smoke-test release.
- [ ] Smoke-test by including a tiny `fix:` commit alongside the parser fix in this PR's merge — once `auto-release.yml` is patched, the merge of *this* PR should auto-bump (patch).
