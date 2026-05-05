# RFC 0009: Reliable releases on merge to main

**Issue**: #25
**Status**: Implementing
**Branch**: `rfc/25-release-on-merge`

---

## Problem

Issue #25 reports that merging PR #24 to `main` (run [25399495953](https://github.com/cnexans/wst/actions/runs/25399495953)) did not publish a release with artifacts. Investigation shows this is **working as designed** — but the design is fragile and surprising.

`auto-release.yml` runs on every push to `main`, but its `check` job gates the rest of the workflow on a single condition:

```yaml
if gh release view "v$VERSION" > /dev/null 2>&1; then
  echo "should_release=false"
else
  echo "should_release=true"
fi
```

So a release fires **only** when `pyproject.toml`'s `version` field is set to a value that has no matching GitHub release yet. In practice this means:

- Merging a `chore: bump version to X.Y.Z` PR → release fires.
- Merging anything else (feature, fix, RFC, refactor) without a bump → silent skip.

The current workflow run that prompted the issue is exactly this case: PR #24 (an RFC merge) didn't bump the version, so the `check` job set `should_release=false` and the `test`/`pypi`/`dmg`/`release` jobs were all skipped. From the user's point of view this looks broken — the workflow says "success" but no artifacts appear on the Releases page.

There are two real problems here:

1. **Trigger model is implicit.** Contributors must remember to bump `pyproject.toml` in the same PR (or a follow-up PR) as any user-visible change. Forgetting silently swallows the release.
2. **Workflow sprawl.** Four release-related workflows exist with overlapping responsibilities — easy to lose track of which one actually fires:

   | Workflow | Trigger | Purpose |
   |---|---|---|
   | `auto-release.yml` | push to `main` | Build + publish if `pyproject.toml` version is unreleased |
   | `release-on-tag.yml` | push tag `v*` | Calls `release.yml`, then creates GitHub release |
   | `release.yml` | `workflow_call` | Reusable test/pypi/dmg/chocolatey jobs |
   | `tag-release.yml` | `workflow_dispatch` | Manual: bump version, tag, call `release.yml` |

   `auto-release.yml` and `release-on-tag.yml` both build artifacts, both create a release, both run on different events. A version bump merged to main races against an explicit `vX.Y.Z` tag push — whichever finishes second errors out trying to create a duplicate release/tag.

## Proposed Solution

Pick **one canonical trigger** and remove the others. Two viable directions:

### Option A — Auto-bump on merge (recommended for low ceremony)

Every merge to `main` with a `feat:` / `fix:` / `perf:` conventional-commit prefix auto-bumps the patch (or minor) version, commits the bump, tags it, and releases. RFC-only / chore / docs / refactor merges do nothing.

Pros: contributors stop thinking about versioning. Releases happen automatically when user-visible code changes.
Cons: requires conventional-commit discipline; auto-bump commits add noise to git log; harder to "batch" several commits into one release.

Implementation sketch:
- Replace `auto-release.yml` with a workflow that:
  1. Inspects commits in the push (`git log <before>..<after>`).
  2. Determines bump kind: `feat:`/`feat!:` → minor, `fix:`/`perf:` → patch, anything else → no release.
  3. Edits `pyproject.toml`, commits with `[skip ci]` to avoid recursion, pushes a tag.
- Delete `tag-release.yml` (manual bump becomes obsolete) and let `release-on-tag.yml` handle the build/publish path.

### Option B — Tag-driven only (recommended for explicit control)

Drop the push-to-main trigger entirely. Releases happen **only** when a maintainer pushes a `vX.Y.Z` tag (manually or via `tag-release.yml`'s `workflow_dispatch`). Update CONTRIBUTING / README to make this explicit.

Pros: zero magic, no auto-commits, single trigger to reason about.
Cons: maintainer must remember to cut releases; merges that should ship do not ship until someone tags.

Implementation sketch:
- Delete `auto-release.yml`.
- Keep `release-on-tag.yml` and `tag-release.yml` as the only paths.
- Add a CI check that warns (not blocks) on PRs containing `feat:` / `fix:` commits without a matching version-bump PR queued.

### Either way: collapse the workflow sprawl

Regardless of which trigger model we pick, the build/publish steps should live in a single reusable workflow (`release.yml`'s current shape) called by exactly one trigger workflow. Today `auto-release.yml` duplicates the build steps inline instead of reusing `release.yml` — that drift is why the macOS build steps in the two files differ (e.g. `auto-release.yml` collects `numpy`/`sklearn`/`scipy`; `release.yml` does not).

## Alternatives Considered

| Alternative | Why rejected (or kept as fallback) |
|---|---|
| Keep current behavior, document it loudly in CONTRIBUTING | Doesn't solve the silent-skip surprise. The workflow run reports `success` even when nothing was released — that's the actual UX bug. |
| Trigger release on every push to main, regardless of version | Creates duplicate-tag/release errors and republishes identical artifacts under new versions. PyPI also rejects republishing the same version. |
| Use `release-please` or `semantic-release` GitHub Apps | Heavier dependency; project is small enough that 30–50 lines of bash beats pulling in a release bot. Worth revisiting if Option A's bump logic grows complex. |
| Keep `auto-release.yml` and have it **fail loudly** when commits since last release contain `feat:`/`fix:` but version wasn't bumped | Decent middle ground but still requires manual bump PRs. Could be a stepping stone toward Option A. |

## Resolved Decisions

User answers from issue #25 review:

| # | Decision |
|---|---|
| Q1 | **Option A — Auto-bump on merge to main.** |
| Q2 | **Conventional Commits drive the bump.** `feat:` → minor, `fix:`/`perf:` → patch, anything else (`refactor:`, `chore:`, `docs:`, `rfc:`, `test:`, `style:`, `ci:`) → no release. A `BREAKING CHANGE:` footer or `feat!:`/`fix!:` bumps minor (we're pre-1.0; no major bumps until 1.0). |
| Q3 | **Direct commit on `main`** by `github-actions[bot]`. No auto-merging PR; less churn. |
| Q4 | **Unify the build matrix.** Collapse `auto-release.yml` and `release.yml` into a single reusable workflow that has the union of both (numpy/sklearn/scipy `--collect-all` flags, Chocolatey job kept as `continue-on-error`). |
| Q5 | **This restructuring lands *before* RFC 0007 (PR #23).** That keeps #23's diff scoped to "add Windows + Linux jobs to the existing reusable workflow" rather than "rewrite the release pipeline AND add platforms." |

## Architecture After This RFC

```
Push to main
  └─► .github/workflows/auto-release.yml   (rewritten as bump-only)
        ├─ inspect commits via Conventional Commits
        ├─ if bump kind ∈ {minor, patch}:
        │     ├─ edit pyproject.toml
        │     ├─ commit "chore: bump version to X.Y.Z [skip ci]"
        │     └─ push tag vX.Y.Z (the tag push triggers the next workflow)
        └─ else: no-op

Push tag v*
  └─► .github/workflows/release-on-tag.yml  (kept, lightly edited)
        └─ calls release.yml (reusable) with version + creates GitHub release

release.yml (reusable, consolidated build matrix)
  ├─ test          (ruff + pytest)
  ├─ pypi          (build wheel + sdist, publish)
  ├─ dmg           (macOS — pyinstaller CLI sidecar + Tauri .dmg, with numpy/sklearn/scipy collected)
  ├─ chocolatey    (Windows — continue-on-error, registry push only)
  └─ github-release (download artifacts, attach to release)
```

`tag-release.yml` (manual `workflow_dispatch`) is deleted. With auto-bump in place, the manual path is no longer needed; an emergency hotfix can still be cut by pushing a `vX.Y.Z` tag directly.

## Implementation Plan

- [x] **Delete** `tag-release.yml` (manual bump path becomes obsolete).
- [x] **Rewrite** `auto-release.yml` as bump-only: parses commit subjects in `${{ github.event.before }}..${{ github.sha }}` via Conventional Commits, decides bump kind (`minor` for `feat:`/`feat!:`/`BREAKING CHANGE:`, `patch` for `fix:`/`perf:`), edits `pyproject.toml`, commits `chore: bump version to X.Y.Z [skip ci]` as `github-actions[bot]`, pushes tag `vX.Y.Z`.
- [x] **Consolidate** `release.yml`: macOS `dmg` job now installs `numpy`/`scikit-learn`/`scipy` and runs PyInstaller with `--collect-all` for each. `pypi`, `test`, `chocolatey` jobs unchanged.
- [x] **Move artifact attachment** into `release-on-tag.yml`'s `github-release` job using `softprops/action-gh-release@v2` with `files:` for wheel/sdist/dmg.
- [x] **Empty-push guard** added (handles force-push and zero-SHA initial pushes).
- [x] **Recursion guards (×2)**: `[skip ci]` on the bump commit + a workflow-level `if:` filter on actor + commit message prefix.
- [x] **Document** the new flow in `README.md` (Releasing section).
- [ ] **Smoke test** — happens when this PR merges (the merge itself uses `feat:` so a release should fire; after merge, look for `v0.11.0` to be auto-tagged and built end-to-end).
- [ ] **Hand off to PR #23** once merged: that PR adds Windows + Linux jobs to the consolidated `release.yml` (not to `auto-release.yml`). PR #23 will need a small rebase since the `dmg` job already absorbed the divergent flags.

## Risk: recursion guard

The auto-bump commit must not re-trigger `auto-release.yml`. Two layers:

1. Append `[skip ci]` to the commit message (GitHub Actions native).
2. The workflow itself filters: if `github.actor == 'github-actions[bot]'` and `github.event.head_commit.message` starts with `chore: bump version to`, exit early.

Belt-and-suspenders — if `[skip ci]` ever stops working (its semantics have shifted before), the actor+message filter still catches it.

## Risk: PR #23 conflict

PR #23 currently edits `release.yml` to add Windows installer + Linux package jobs. Once this RFC merges, PR #23 will need a rebase since `release.yml`'s `dmg` job will have absorbed `auto-release.yml`'s build flags. The diff in #23 should shrink (no longer needs to mirror the divergent macOS build steps). Will coordinate with the next iteration of #23 after #25 ships.
