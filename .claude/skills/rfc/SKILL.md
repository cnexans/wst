---
name: rfc
description: Create or update an RFC (Request for Comments) document in the wst project. Use when the user asks to write, draft, or propose an RFC, architectural decision, or design document.
---

# RFC Skill — wst Project

Write RFCs following the wst project's flat-file convention under `docs/rfcs/`.

## RFC Structure

Every RFC is a **single markdown file** under `docs/rfcs/`:

```
docs/rfcs/NNNN-kebab-case-title.md
```

## Naming Convention

- **Filename**: zero-padded 4-digit number + descriptive kebab-case title.
  - Example: `0005-embedding-search.md`, `0006-search-parser.md`
- **Number**: next sequential number after the highest existing RFC.
  - Check with: `ls docs/rfcs/ | tail -1`

## RFC Document Format

Use this template:

```markdown
# RFC NNNN: Title

**Issue**: #<number>
**Status**: Draft — awaiting approval
**Branch**: `rfc/issue-<number>-<slug>`

---

## Problem

Why this change is needed. What problem it solves.

## Proposed Solution

High-level design and approach.

### <Subsection if needed>

Deeper technical details, data models, CLI changes, APIs.

## Alternatives Considered

| Alternative | Why rejected |
|-------------|-------------|
| <alt> | <reason> |

## Open Questions

- <Unresolved decision that needs input>

## Implementation Plan

- [ ] Step 1
- [ ] Step 2
```

Sections are flexible — add or remove as the scope demands. The header block (`Issue`, `Status`, `Branch`) and **Problem** + **Proposed Solution** sections are required.

## Diagrams

When a diagram would help explain the design, use PlantUML:

- **Source files**: `docs/plantuml/<descriptive_name>.puml` (shared directory, not per-RFC)
- **Compiled output**: `docs/images/<descriptive_name>.png` (generated, do not edit)
- **Reference in RFC**: `![Title](../images/descriptive_name.png)` (relative path from `docs/rfcs/`)
- **Compile**: `make docs` (compiles all `.puml` → `.png`)
  - Or single file: `plantuml -tpng -o $(pwd)/docs/images docs/plantuml/name.puml`

### PlantUML style

```plantuml
@startuml descriptive_name
!theme plain
skinparam backgroundColor white

' diagram content here

@enduml
```

### Diagram types to consider

| Diagram | PlantUML type | When to use |
|---------|---------------|-------------|
| System architecture | component | Structural changes, new subsystems |
| Message / data flow | sequence | APIs, multi-component interactions |
| State machine | state | Lifecycle management, process flows |
| Data model | class | Schema changes, new entities |

**Never** inline PlantUML in the RFC markdown — always write separate `.puml` files and reference the compiled PNG.

## Workflow

1. **Determine the next RFC number**: `ls docs/rfcs/ | tail -1` → increment by 1.
2. **Create the file**: `docs/rfcs/NNNN-kebab-case-title.md`
3. **Write the RFC** following the template above.
4. **If diagrams are needed**:
   - Write `.puml` files in `docs/plantuml/`
   - Run `make docs` to compile
   - Verify PNGs appear in `docs/images/` and paths in the RFC are correct
5. **Commit**: all RFC and diagram files in one commit — `git commit -m "rfc: <title> (#<issue>)"`

## Tone & Style

- Technical but conversational — write for a senior engineer joining the project.
- Lead with **why**, then **what**, then **how**.
- Use tables for comparisons and tradeoff analysis.
- Keep sections focused — if a section exceeds ~40 lines, consider splitting.
- Reference existing RFCs by number when building on prior decisions (e.g., "see RFC 0003").
