---
name: issue-rfc-flow
description: Processes GitHub issues in an RFC-driven development loop using GitHub labels as the state machine. Opens RFCs, waits for label-based approval, implements, and tracks progress entirely through issue/PR labels so the /loop can monitor state transitions without reading comments.
---

# Issue RFC Flow

Automates an RFC-driven development cycle for GitHub issues using **GitHub labels as the state machine**. The loop reads label states, takes action on transitions, and writes labels back — no manual comment parsing needed.

## Label State Machine

### Labels on Issues

| Label | Set by | Meaning |
|-------|--------|---------|
| `open-questions` | AI | RFC has unresolved questions — AI is waiting for user input before proceeding |
| `approved` | User | User approved the plan; AI can move to implementation |

### Labels on PRs

| Label | Set by | Meaning |
|-------|--------|---------|
| `analysis` | AI | PR contains only the RFC — awaiting review before implementation |
| `open-questions` | AI | RFC has unresolved questions that need user input |
| `needs-review` | AI | Implementation complete — awaiting user review/merge |
| `approved` | User | User approved this PR (RFC or implementation) |

### State Transitions

```
Issue created
  └─► AI creates RFC PR → PR gets label: analysis
        ├─ (if RFC has open questions) → PR + Issue get label: open-questions
        │     User answers → User removes open-questions label
        └─ User adds approved to ISSUE → AI implements
              AI removes: analysis, open-questions
              AI adds: needs-review to PR
              User reviews → User adds approved to PR
              User merges PR → issue auto-closes (via "Closes #N" in PR body)
```

### When user adds `approved` to any issue or PR

The AI must **immediately remove all other state labels** (`analysis`, `open-questions`, `needs-review`) from that item, keeping only `approved`. This signals clean approval state.

---

## Bootstrap — Run on Every Loop Iteration

### Step 1 — Ensure labels exist

Create any missing labels (idempotent — safe to run every time):

```bash
gh label create "open-questions" --color "FBCA04" --description "Waiting for user input" 2>/dev/null || true
gh label create "approved"       --color "0E8A16" --description "Approved — proceed"     2>/dev/null || true
gh label create "analysis"       --color "BFD4F2" --description "RFC under review"       2>/dev/null || true
gh label create "needs-review"   --color "D4C5F9" --description "Implementation ready for review" 2>/dev/null || true
```

### Step 2 — Fetch open issues and their linked PRs

```bash
gh issue list --state open --json number,title,labels --limit 100
```

For each open issue, find its linked PR:

```bash
gh pr list --search "closes #<issue-number>" --state open --json number,title,labels,headRefName
```

### Step 3 — Derive current state from labels

For each issue + PR pair, read labels and determine state:

| Issue labels | PR labels | Derived state | Next action |
|---|---|---|---|
| (no special labels, no PR) | — | `rfc_pending` | Create RFC + PR |
| `open-questions` | any | `blocked_questions` | Wait — do not proceed |
| (none) | `analysis`, no `approved` | `awaiting_rfc_approval` | Wait |
| (none) | `analysis` + `open-questions` | `blocked_questions` | Wait |
| `approved` | `analysis` | `implementing` | Implement (see Phase 4) |
| (none) | `needs-review`, no `approved` | `awaiting_impl_review` | Wait |
| (none) | `needs-review` + `approved` | `done` | PR ready to merge |
| PR merged / issue closed | — | `done` | Skip |

---

## Phase 1 — Refine (per issue in `rfc_pending`)

1. Read the issue body and **all comments** on the original issue:
   ```bash
   gh api repos/:owner/:repo/issues/<issue-number>/comments \
     --jq '.[] | {user: .user.login, body: .body}'
   ```
2. Identify:
   - **Goal**: one sentence describing the desired outcome.
   - **Acceptance criteria**: "done when…" bullets.
   - **Out of scope**: what will NOT be done.
   - **Open questions**: anything ambiguous that needs user input.
3. Do NOT write any code yet.

---

## Phase 2 — RFC Pull Request

1. Create a branch: `rfc/<issue-number>-<slug>` (slug = first 5 words of issue title, kebab-case).
2. Use the `/rfc` skill to write `docs/rfcs/NNNN-<slug>.md`.
3. `git add`, `git commit -m "rfc: <title> (#<issue-number>)"`, `git push`.
4. Open a **draft** PR:
   ```bash
   gh pr create --draft \
     --title "RFC: <issue title>" \
     --body "$(cat <<'EOF'
   Closes #<issue-number>

   RFC for #<issue-number>. Implementation follows once the RFC is approved.

   **To approve:** add the \`approved\` label to this issue (#<issue-number>).
   **To request changes:** leave a comment on this PR or the issue with your feedback.
   EOF
   )"
   ```
5. Add `analysis` label to the PR:
   ```bash
   gh pr edit <pr-number> --add-label "analysis"
   ```
6. If the RFC has open questions, add `open-questions` to **both** the issue and the PR:
   ```bash
   gh issue edit <issue-number> --add-label "open-questions"
   gh pr edit <pr-number> --add-label "open-questions"
   ```
7. Comment on the original issue linking to the PR:
   ```bash
   gh issue comment <issue-number> \
     --body "RFC opened in #<pr-number>. Add the \`approved\` label to this issue to proceed with implementation."
   ```

---

## Phase 3 — Awaiting Input / Approval

**Do not block.** While an issue is waiting, move on to the next `rfc_pending` issue.

On each loop iteration, re-derive state from labels (Bootstrap Step 3). Transitions to watch:

- **`open-questions` removed from issue/PR** → user answered; re-read issue comments to incorporate answers into the RFC, then re-evaluate state.
- **`approved` added to issue** → transition to Phase 4 (implement).
- **Comment on issue or PR** → check for feedback or change requests even if labels haven't changed yet. Read:
  ```bash
  gh api repos/:owner/:repo/issues/<issue-number>/comments --jq '.[] | {user: .user.login, body: .body}'
  gh api repos/:owner/:repo/issues/<pr-number>/comments   --jq '.[] | {user: .user.login, body: .body}'
  gh api repos/:owner/:repo/pulls/<pr-number>/reviews     --jq '.[] | {user: .user.login, state: .state, body: .body}'
  ```
  If there is substantive feedback (change requests, corrections, new requirements), update the RFC proactively — don't wait for a label change.

---

## Phase 4 — Implement

Triggered when issue has label `approved`.

1. Check out the RFC branch:
   ```bash
   git checkout rfc/<issue-number>-<slug>
   ```
2. Update RFC `Status` to `Implementing` and fill in the **Implementation Plan** section.
3. Remove `analysis` and `open-questions` labels from the PR; add `needs-review`:
   ```bash
   gh pr edit <pr-number> --remove-label "analysis" --remove-label "open-questions" --add-label "needs-review"
   ```
4. Also remove `approved` and `open-questions` from the issue (approved has been acted on):
   ```bash
   gh issue edit <issue-number> --remove-label "approved" --remove-label "open-questions"
   ```
5. Implement the feature/fix following the RFC plan. Keep commits small and focused (`feat:`, `fix:`, `refactor:`).
6. Mark the PR as ready for review:
   ```bash
   gh pr ready <pr-number>
   ```
7. Comment on the PR:
   ```bash
   gh pr comment <pr-number> --body "Implementation complete. Ready for final review. Add \`approved\` label to this PR to signal it's ready to merge."
   ```

---

## Phase 5 — RFC Iteration (changes requested via comments)

When a user leaves substantive feedback on the issue or PR **without** adding `approved`:

1. Parse feedback from comments (check issue + PR + PR reviews — see Phase 3).
2. Update `docs/rfcs/NNNN-<slug>.md` — revise relevant sections.
3. If open questions were answered in comments, incorporate answers inline and remove the question blockquotes.
4. If `open-questions` label is now resolved, remove it:
   ```bash
   gh issue edit <issue-number> --remove-label "open-questions"
   gh pr edit <pr-number> --remove-label "open-questions"
   ```
5. Commit: `rfc: address review feedback (#<issue-number>)` and push.
6. Comment on the PR summarizing what changed.

---

## Phase 6 — Approved for Merge (`needs-review` + `approved` on PR)

When PR has both `needs-review` and `approved`:

1. Remove `needs-review` and `approved` labels from the PR:
   ```bash
   gh pr edit <pr-number> --remove-label "needs-review" --remove-label "approved"
   ```
2. Comment: "PR approved. Ready to merge — merging will auto-close issue #<issue-number>."
3. Mark issue state as `done` in the status table.

> **Note:** Do NOT merge PRs automatically. The user merges. The `Closes #N` in the PR body ensures the issue auto-closes on merge.

---

## Concurrency Rules

- Multiple issues can be in `awaiting_rfc_approval` or `awaiting_impl_review` simultaneously.
- **At most one issue** in active `implementing` at a time.
- Always prefer advancing a `blocked_questions` issue (once unblocked) over starting a new one.

---

## Output Format

After each loop iteration, print:

```
Issue  | PR    | Labels (issue)       | Labels (PR)            | State
-------|-------|----------------------|------------------------|------------------------
#7     | #15   | —                    | analysis               | awaiting_rfc_approval
#21    | #23   | —                    | analysis               | awaiting_rfc_approval
#22    | #24   | —                    | needs-review           | awaiting_impl_review
```

---

## Error Handling

- If `gh` is not authenticated → tell user to run `gh auth login`.
- If an issue is already linked to an open PR → skip RFC creation, attach to existing PR.
- If a label operation fails (e.g. label doesn't exist) → run the bootstrap label-creation step first.
- If a PR is already merged → mark issue as `done`, skip it.
