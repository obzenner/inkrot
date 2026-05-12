---
name: create-document
description: Create a new documentation file (adr, explanation, learnings, reference, rfc, runbook, spec, tasks) with correct structure, numbering, and frontmatter. Use when the user says "create an ADR", "new decision record", "write an RFC", "new spec", "new runbook", "new task list", "new learning", or any variation of starting a new document.
metadata:
  version: "0.1.0"
---

# Skill: new

## Purpose

Scaffold a new document with correct structure, auto-incremented numbering, and valid frontmatter — so it passes validation from the start.

## Trigger

- User says "create an ADR", "new ADR", "new decision", "document this decision"
- User says "create an RFC", "new spec", "new runbook", "new task list", "new learning"
- User invokes `/new`

## Supported Document Types

| Type | Naming | Required Sections | Statuses |
|------|--------|-------------------|----------|
| adr | `NNNN-slug.md (zero-padded number, lowercase kebab)` | Context and Problem Statement, Decision Outcome | accepted, deprecated, proposed, rejected, superseded |
| explanation | `slug.md (lowercase kebab, no prefix)` |  | N/A |
| learnings | `LEARNING-NNNN-slug.md (uppercase LEARNING prefix, zero-padded number, lowercase kebab slug)` | (subtype-dependent) | archived, draft, published |
| reference | `slug.md (lowercase kebab, no prefix)` |  | N/A |
| rfc | `RFC-NNNN-slug.md (uppercase RFC prefix, zero-padded number, lowercase kebab slug)` | Problem, Proposal, Alternatives, Resolution | accepted, draft, open, rejected, withdrawn |
| runbook | `RUNBOOK-slug.md (uppercase RUNBOOK prefix, lowercase kebab slug)` | Purpose, Prerequisites, Steps, Rollback, Escalation | active, deprecated, draft |
| spec | `SPEC-slug.md (uppercase SPEC prefix, lowercase kebab slug)` | User Scenarios, Requirements, Success Criteria, Assumptions | abandoned, approved, draft, implemented |
| tasks | `TASK-slug.md (uppercase TASK prefix, lowercase kebab slug)` | Phases, Task Items, Dependencies | abandoned, active, completed |

## Workflow

### Step 1: Determine Document Type

Ask if not obvious from context. Supported types: adr, explanation, learnings, reference, rfc, runbook, spec, tasks.

### Step 2: Determine Target Directory

1. Read `.docs-toolkit.yml` at repo root for configured paths
2. If no config, use defaults:

   - adr: `decisions`, `docs/decisions`, `adrs`, `docs/adrs`
   - explanation: `topics`, `docs/topics`, `explanations`, `docs/explanations`
   - learnings: `learnings`, `docs/learnings`
   - reference: `references`, `docs/references`, `domain-knowledge`, `docs/domain-knowledge`
   - rfc: `rfcs`, `docs/rfcs`
   - runbook: `runbooks`, `docs/runbooks`
   - spec: `specs`, `docs/specs`
   - tasks: `tasks`, `docs/tasks`

3. If directory doesn't exist, create it

### Step 3: Auto-Increment Number (if applicable)

For numbered types (ADR, RFC, Learnings):
1. Scan the target directory for existing files matching the naming pattern
2. Find the highest number
3. Next number = highest + 1, zero-padded to 4 digits

### Step 4: Get Title and Context from User

Ask the user:
- What is the document about? (becomes the title)
- What code paths will this relate to? (becomes `tracks`)
- For learnings: which subtype? (incident, retrospective, til)

Generate the slug from the title: lowercase, spaces to hyphens, remove special chars.

### Step 5: Create the File

1. Read the appropriate template from `assets/`
2. Fill placeholders (NUMBER, TITLE, DATE, TRACKS_PATH, etc.)
3. Write to the target directory with correct filename

### Step 6: Verify

Run the validation script on the new file:

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/validate.py" <new_file_path> --format text
```

If errors: fix them before reporting success.
If warnings only: report them to user as suggestions.

## Error Handling

- Target directory doesn't exist → create it
- No existing docs → start at 0001 for numbered types
- Slug collision → append number suffix
- Validation fails after creation → fix inline, don't leave broken files
