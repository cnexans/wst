---
name: issue-rfc-flow
description: Processes GitHub issues in an RFC-driven development loop. For each open issue: refines scope, opens a PR with an RFC, waits for admin approval in the issue/PR, then implements or iterates. Continues with the next issue while awaiting feedback.
---

# Issue RFC Flow

Automates an RFC-driven development cycle for GitHub issues: read → refine → RFC → wait for approval → implement → iterate.

## When to Use This Skill

- Working through a backlog of GitHub issues one by one
- You want a structured RFC review step before any code is written
- You need to parallelize: start the next issue while waiting for feedback on the previous one

## What This Skill Does

1. **Reads all open issues** from the GitHub repository
2. **Refines scope** for each issue before touching code
3. **Opens a draft PR** containing an RFC document that references the issue
4. **Waits for admin approval** (comment on the PR/issue) before implementing
5. **Implements or iterates** based on admin feedback, in the same PR
6. **Moves on** to the next issue while waiting for feedback on a blocked one

## Instructions

### Phase 0 — Bootstrap

1. Run `gh issue list --state open` to fetch all open issues. Sort by number ascending (oldest first).
2. Build a work queue. Each entry has:
   - `issue_number`
   - `status`: one of `rfc_pending | awaiting_approval | changes_requested | implementing | done`
   - `pr_number` (once created)
3. Print the queue as a table so the user can see what will be worked on.

### Phase 1 — Refine (per issue)

For each issue (process in parallel when possible):

1. Read the issue body and all comments with `gh issue view <number> --comments`.
2. Identify:
   - **Goal**: single sentence describing the desired outcome.
   - **Acceptance criteria**: bullet list of "done when…" statements.
   - **Out of scope**: what will NOT be done in this issue.
   - **Open questions**: anything ambiguous that needs admin input before design can be finalized.
3. Do NOT write any code yet.

### Phase 2 — RFC Pull Request

1. Create a branch: `rfc/<issue-number>-<slug>` (slug = first 5 words of issue title, kebab-case).
2. Write an RFC document at `docs/rfcs/<issue-number>-<slug>.md` using the template below.
3. `git add`, `git commit -m "rfc: <issue title> (#<issue-number>)"`, `git push`.
4. Open a **draft** PR:
   ```
   gh pr create --draft \
     --title "RFC: <issue title>" \
     --body "$(cat <<'EOF'
   Closes #<issue-number>

   This PR contains the RFC for #<issue-number>. Implementation will be added here once the RFC is approved.

   **Admin: please review the RFC in `docs/rfcs/<issue-number>-<slug>.md` and leave a comment on this PR with one of:**
   - ✅ `approved` — proceed with implementation
   - 🔁 `changes: <what to change>` — iterate on the RFC first

   Open questions (if any) are listed in the RFC.
   EOF
   )"
   ```
5. Also post a comment on the original issue linking to the PR:
   ```
   gh issue comment <issue-number> --body "RFC opened in #<pr-number>. Waiting for approval before implementing."
   ```
6. Set issue status → `awaiting_approval`.

#### RFC Document

Use the `/rfc` skill to create the RFC document. It handles naming, numbering, and template formatting automatically.

### Phase 3 — Awaiting Approval

While an issue is `awaiting_approval`, **do not block — move on** to the next issue in the queue and begin Phase 1 for it.

To check for approvals/feedback on blocked issues, you **must check both** the original issue AND the RFC PR — admins often reply directly on the issue, not the PR. Use the GitHub API (not `gh pr view`, which has a deprecated projects warning):

```bash
# Comments on the ORIGINAL issue (use the issue number, e.g. 21)
gh api repos/:owner/:repo/issues/<issue-number>/comments \
  --jq '.[] | {user: .user.login, body: .body}'

# Comments on the RFC PR (use the PR number, e.g. 23)
gh api repos/:owner/:repo/issues/<pr-number>/comments \
  --jq '.[] | {user: .user.login, body: .body}'

# Formal PR reviews
gh api repos/:owner/:repo/pulls/<pr-number>/reviews \
  --jq '.[] | {user: .user.login, state: .state, body: .body}'
```

Scan **all three** for each tracked issue/PR pair. Look for admin comments containing:
- `approved` (case-insensitive) → transition to Phase 4
- `changes:` or `change request` or `please update` → transition back to Phase 2 (update RFC)
- Inline answers to open questions → incorporate into the RFC before proceeding

### Phase 4 — Implement

1. Update the RFC's `Status` field to `Implementing` and fill in the **Implementation Plan** section.
2. Implement the feature/fix on the same branch following the plan.
3. Keep commits small and focused. Prefix messages: `feat:`, `fix:`, `refactor:`, etc.
4. Once done, mark the PR as **ready for review** (`gh pr ready <pr-number>`).
5. Post a comment on the PR: "Implementation complete. Ready for final review."
6. Set issue status → `done`.

### Phase 5 — Changes Requested (RFC Iteration)

If the admin requests changes to the RFC:

1. Parse the feedback from the comment.
2. Update `docs/rfcs/<issue-number>-<slug>.md` — revise the relevant sections.
3. If there were open questions in the RFC and the admin answered them, move the answers inline and remove the question blockquotes.
4. Commit: `rfc: address review feedback (#<issue-number>)` and push.
5. Reply on the PR summarizing what changed and re-request review.
6. Set issue status → `awaiting_approval` again.

### Concurrency Rules

- **At most one issue per status bucket** in active implementation at a time (to keep PRs focused).
- **Multiple issues** can be in `awaiting_approval` simultaneously.
- Always prefer moving a `changes_requested` issue forward over starting a new one.
- Print status updates whenever you transition an issue.

## Output Format

After each major action, print a status table:

```
Issue  | PR    | Status
-------|-------|-------------------
#12    | #34   | awaiting_approval
#15    | #35   | implementing
#18    | —     | rfc_pending
```

## Error Handling

- If `gh` is not authenticated, stop and tell the user to run `gh auth login`.
- If an issue is already linked to an open PR (check with `gh pr list --search "closes #<n>"`), skip the RFC creation step and attach to the existing PR instead.
- If you cannot determine the repository from the current directory, run `gh repo view` to confirm before proceeding.

## Example Workflow

```
User: /issue-rfc-flow

→ Fetching open issues...
  Found: #12 (add export command), #15 (fix PDF parsing), #18 (i18n support)

→ Processing #12: add export command
  Refined scope. Creating RFC branch and PR...
  PR #34 opened (draft). Waiting for approval.

→ Processing #15: fix PDF parsing (while #12 awaits approval)
  Refined scope. Creating RFC branch and PR...
  PR #35 opened (draft). Waiting for approval.

→ Status:
  Issue | PR  | Status
  ------|-----|-------------------
  #12   | #34 | awaiting_approval
  #15   | #35 | awaiting_approval
  #18   | —   | rfc_pending

→ No approvals yet. Will check again when you resume the skill.
   Run /issue-rfc-flow again to continue processing or pick up approvals.
```
