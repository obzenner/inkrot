# inkrot

This repo hosts multiple Claude Code plugins:

- **inkrot** (`plugins/inkrot/`) — Schema-driven documentation validation. Enforces structure, naming, frontmatter, and status lifecycle across 8 document types, all derived from JSON schemas as the single source of truth.
- **hr** (`plugins/hr/`) — Role profiling for agent configuration. Takes a task description, researches the current market, and produces a professional HR-style competency profile so agents can adopt the right expertise.

## Installation

```
/plugin marketplace add obzenner/inkrot
/plugin install inkrot@inkrot
/plugin install inkrot@hr
```

## Document Types

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

## Default Discovery Paths

   - adr: `decisions`, `docs/decisions`, `adrs`, `docs/adrs`
   - explanation: `topics`, `docs/topics`, `explanations`, `docs/explanations`
   - learnings: `learnings`, `docs/learnings`
   - reference: `references`, `docs/references`, `domain-knowledge`, `docs/domain-knowledge`
   - rfc: `rfcs`, `docs/rfcs`
   - runbook: `runbooks`, `docs/runbooks`
   - spec: `specs`, `docs/specs`
   - tasks: `tasks`, `docs/tasks`

## Skills

| Skill | Description |
|-------|-------------|
| `create-document` | Create a new documentation file (adr, explanation, learnings, reference, rfc, runbook, spec, tasks) with correct structure, numbering, and frontmatter. Use when the user says "create an ADR", "new decision record", "write an RFC", "new spec", "new runbook", "new task list", "new learning", or any variation of starting a new document. |
| `docs-migrate` | Migrate existing documentation to docs-toolkit standards. Performs full repository scan, maps every markdown file to a schema, proposes directory structure and migration plan. Use when adopting docs-toolkit in a repo, when asked to "migrate docs", "standardize documentation", "set up docs-toolkit", or "organize docs". |
| `docs-status` | Change a document's status with enforcement of transition rules. Use when marking an ADR as accepted, superseding a decision, deprecating a runbook, or any status lifecycle change that requires cross-reference integrity. |

## Architecture

```
schemas/*.json          ← Single source of truth
    │
    ▼
scripts/gen_skills.py   ← Generates all derived files
    │
    ├── skills/*/SKILL.md        (agent instructions)
    ├── skills/*/assets/*.md     (document templates)
    └── CLAUDE.md                (this file)

hooks/hooks.json        ← Runtime enforcement
    ├── PreToolUse: protect_generated.py (block edits to generated files)
    ├── SessionStart: validate.py       (check docs on load)
    └── Stop: validate.py              (check docs on exit)
```
