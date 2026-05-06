# RFC 0012: Releases not being created after merging to main

**Issue**: #31
**Status**: Implementing
**Branch**: `rfc/31-releases-not-firing`

**Resolutions** (from #31 comments):
- **Q1**: Single combined `v0.11.0` covering both #23 and #28. Pushed manually out of band.
- **Q2**: Strict enforcement — the skip-ci-guard fails the PR check (blocks merge) when the literal token is found.
- **Q3**: Title + body only.
- **Q4**: Out of scope — the release-gap monitor is **not** included in this implementation. The guard alone (Q2) is the prevention; if a future leak path slips through, we can add the monitor in a follow-up.

---

## Problem

The auto-release pipeline introduced by RFC 0009 and patched by RFC 0010 is, on paper, correct. In practice the last two releasable merges to `main` produced **no release at all**, and the user filed #31 noticing that fact. Investigation:

1. **State of `main`**. Last published release is `v0.10.3` (2026-05-05). Two commits sit ahead of it:
   - `681e554` — *RFC: Soporte multiplataforma (Windows + Linux releases) (#23)* (merged 2026-05-06 11:23 UTC)
   - `2ec493b` — *RFC: Auto-release bug fixes (skip-ci leak + squash-bullet parser) (#28)* (merged 2026-05-06 11:24 UTC)

2. **PR #23 — workflow ran, picked the wrong bump.** `Auto Release` (run `25432315902`) finished `success` but the bump-detection step logged `Bump kind: none`. The squashed body's only release-worthy line was `* feat(ci): add Windows + Linux release builds`. The pre-#28 regex (`^feat: …`) anchored to start-of-line, so the `* ` bullet prefix introduced by GitHub's squash-merge defeated the match. **PR #28 already fixed this** — the workflow now strips leading `* ` before grepping (`.github/workflows/auto-release.yml:62-65`). So the failure mode is closed for any future merge, but `v0.11.0` for #23 was never produced.

3. **PR #28 — workflow never ran at all.**
   ```
   gh api "repos/cnexans/wst/actions/runs?head_sha=2ec493b…" --jq '.total_count'
   → 0
   ```
   GitHub silently skipped every workflow for that push because the squash commit body contains the literal substring `[skip ci]` inside the prose:
   > Q1: drop **[skip ci]** from bump commit (rely on actor+subject guard alone).

   GitHub honors that directive on **any line of any commit message** in a push, before the workflow event even fires ([docs](https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-workflow-runs/skipping-workflow-runs)). The release fix that PR #28 was specifically designed to ship was killed by the very class of bug it was documenting.

4. **Net effect.** Two unreleased changes — multiplatform builds (user-visible feature) and the auto-release recovery fix (infrastructure) — sit on `main` with no tag or artifacts. The README post-#28 (line 196) already warns about this trap, but documentation alone didn't prevent it from biting the same PR that wrote the warning.

The two failure modes are independent. **#23's mode is already fixed in code; only #28's mode (skip-ci leak) remains active.** The RFC focuses on closing that one and on a backstop for future surprises.

---

## Proposed Solution

Three pieces, in order of importance:

1. **Recovery** (one-shot, out-of-band): cut a single `v0.11.0` tag from current `main` so users get the merged-but-unreleased changes. This is a manual `git tag` + `git push` rather than something the workflow does on its own — see *Recovery* below.
2. **Prevention** (the RFC's main payload): a `pull_request` workflow that fails any PR whose **title or body** contains a literal CI-skip directive. Catches the trap before squash-merge writes that prose into the commit.
3. **Detection** (backstop): a small scheduled job that warns when `main` has commits past the latest tag but no `Auto Release` run is recorded for the head SHA — covers any future skip-ci-style silent failure regardless of cause.

### 1. Recovery

The two unreleased changes ship together as `v0.11.0`. Tagging is manual since `auto-release.yml` won't retroactively process commits that never triggered it:

```bash
git checkout main
git pull --ff-only
# bump pyproject.toml manually
sed -i '' 's/^version = ".*"/version = "0.11.0"/' pyproject.toml
git add pyproject.toml
git commit -m "chore: bump version to 0.11.0"
git tag v0.11.0 -m "Release v0.11.0"
git push origin main v0.11.0
```

The bump commit's subject matches the recursion-guard prefix (`chore: bump version to`), so `auto-release.yml` will skip it cleanly. The `v0.11.0` tag triggers `release-on-tag.yml`, which produces the actual artifacts.

This recovery is described in the RFC for traceability but is intended to be executed by a human with push access — not as a step the merge workflow takes on its own.

### 2. Prevention — PR-body skip-ci linter

Add `.github/workflows/skip-ci-guard.yml`:

```yaml
name: Skip-CI Guard
on:
  pull_request:
    types: [opened, edited, reopened, synchronize]
    branches: [main]

permissions:
  pull-requests: read

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - name: Reject literal CI-skip tokens in PR title/body
        env:
          PR_TITLE: ${{ github.event.pull_request.title }}
          PR_BODY:  ${{ github.event.pull_request.body }}
        run: |
          set -eo pipefail
          # GitHub's documented skip directives, matched as standalone tokens.
          PATTERN='\[(skip ci|ci skip|no ci|skip actions|actions skip)\]'
          BLOB="$PR_TITLE"$'\n'"$PR_BODY"
          if printf '%s' "$BLOB" | grep -Eqi "$PATTERN"; then
            echo "::error::PR title or body contains a literal CI-skip directive."
            echo "GitHub honors these tokens on any line of the squash commit and"
            echo "silently skips all workflows for the merge — including auto-release."
            echo "Hyphenate it as [skip-ci] or wrap in inline code (\`[skip ci]\`) when"
            echo "you must reference it in prose. See README §Releasing."
            exit 1
          fi
          echo "OK — no skip-ci leak detected."
```

Why this rather than a server-side or commit-message check:

- GitHub's squash-merge concatenates **PR title + PR body** into the commit message. Checking the PR title+body is the only enforcement point that runs *before* the bad commit message exists. After the merge, the workflow has already been suppressed and there is nothing to lint.
- The check is a single shell line — no Node action, no checkout, no token usage beyond the default `pull_request` event.
- Inline-code (`` `[skip ci]` ``) and hyphenated forms (`[skip-ci]`) survive squash-merging unchanged but don't trigger GitHub's regex, so the README's existing escape advice still works for prose that legitimately needs to discuss the token.

### 3. Detection — release-gap monitor

A daily (or post-push) scheduled job that compares `main`'s current head against the most recent tag, and pings the user when something looks off:

```yaml
name: Release Gap Monitor
on:
  schedule: [{cron: "17 6 * * *"}]   # 06:17 UTC daily
  workflow_dispatch: {}

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - name: Detect release gap
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          set -euo pipefail
          LATEST_TAG=$(git tag --list 'v*' --sort=-v:refname | head -1)
          HEAD_SHA=$(git rev-parse origin/main)

          # If there are no commits past the latest tag, nothing to check.
          AHEAD=$(git rev-list --count "${LATEST_TAG}..origin/main")
          if [ "$AHEAD" -eq 0 ]; then
            echo "main is at $LATEST_TAG — no gap."
            exit 0
          fi

          # Did Auto Release run for the head?
          RUNS=$(gh api "repos/${{ github.repository }}/actions/runs?head_sha=$HEAD_SHA&workflow=auto-release.yml" --jq '.total_count')
          if [ "$RUNS" -eq 0 ]; then
            gh issue create \
              --title "Release gap: main is $AHEAD commits past $LATEST_TAG with no Auto Release run for $HEAD_SHA" \
              --body "Likely a CI-skip leak or workflow-skip event. Inspect commit message for [skip ci] tokens and re-run \`auto-release.yml\` manually if appropriate."
          fi
```

This is intentionally narrow — it doesn't try to predict whether a feat/fix should have triggered a bump, only whether the workflow ran at all. The Q4 question below asks whether to expand this scope.

---

## Alternatives Considered

| Alternative | Why rejected |
|-------------|-------------|
| Strip skip-ci tokens from the squash commit message after merge | GitHub honors the directive *before* the workflow fires; nothing on the receiving end can "rescue" the push. Has to be pre-merge. |
| Branch-protection rule "require a status check" | Doesn't help — when the workflow is skipped, the required check never reports, but that blocks merging entirely rather than blocking the offending PR. Also surfaces as a confusing UX (status missing vs. status failing). |
| Server-side `pre-receive` hook | Not available on GitHub.com Cloud (only Enterprise Server). Out of reach for this repo. |
| Convert squash-merge to merge-commit so the bot commit's subject matches `feat:`/`fix:` directly | Loses the clean linear history the project currently has and is a much larger workflow change than warranted by this bug. |
| PR template that mentions the trap | Already done implicitly via README §Releasing; the README warning didn't prevent #28 from tripping it. Documentation has lower compliance than a CI gate. |
| Detect-only (no PR-time gate), rely on the gap monitor + manual recovery | Cheaper but accepts every leak as a deferred ops task. The gate-and-monitor combo trades ~20 lines of YAML for the recovery toil being a one-time event. |

---

## Open Questions

> **Q1** — Recovery cadence: do we cut a single `v0.11.0` covering both #23 (`feat`) and #28 (`fix`), or split into `v0.11.0` for #23 and `v0.11.1` for #28? A combined release matches what auto-release would have produced if it had picked up #23 correctly (minor wins over patch in the same window). Splitting requires tagging an intermediate SHA between the two merges and produces two releases for users to read changelogs on.

> **Q2** — Skip-ci-guard enforcement: hard-fail the PR check (blocks merge unless the token is hyphenated/code-wrapped), or warn-only (label `skip-ci-leak` + annotation, but doesn't gate merge)? Strict prevents the bug entirely; warn-only is friendlier when someone *intentionally* wants to merge with CI skipped (rare on `main` for this project) but trusts the author to scrub prose tokens before squash. Proposal: **strict**, since the cost of a missed release on `main` is the exact pain we're trying to avoid.

> **Q3** — Scope of the body scan: title + body only, or also PR review comments / inline review bodies? GitHub's squash-merge only embeds title+body into the commit, so comments/reviews can never reach the merged commit. Proposal: **title + body only.** Out of scope unless you've seen a different leak path.

> **Q4** — Backstop monitor scope: detect only "no Auto Release run at all" (the #28 failure mode), or also "Auto Release ran but returned `Bump kind: none` despite a feat/fix commit being present in the diff" (the #23 failure mode)? The latter is more code (re-implements the parser), and #23's mode is already fixed in workflow code, so the value is mostly insurance against regressing the parser. Proposal: **start with the narrow form** (no run at all). Revisit if a future parser bug slips through.

---

## Implementation Plan

- [ ] Cut `v0.11.0` recovery tag manually (out of band — see *Recovery* above) covering #23 + #28. Per Q1: a single combined release.
- [ ] Add `.github/workflows/skip-ci-guard.yml` enforcing the title/body scan on PRs targeting `main`. Per Q2: strict — the check fails (non-zero exit) on a hit. Per Q3: title + body only.
- [ ] Branch-protect `main` to require the *Skip-CI Guard / scan* check (GitHub UI step, performed by the user after the workflow lands and has been observed to pass on a clean PR).
- [ ] Update `README.md` §Releasing to mention the new guard (one line; the existing trap warning stays in place as the developer-facing rationale).
- [ ] Smoke-test the guard by opening a throwaway PR whose body contains the literal CI-skip token in prose and verifying the check fails; then escape it (hyphenated or wrapped in inline code) and verify it passes.
