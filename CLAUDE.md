# inkrot

Schema-driven documentation validation plugin for Claude Code. Enforces structure, naming, frontmatter, and status lifecycle across 8 document types — all derived from JSON schemas as the single source of truth.

## Quick Start

1. Install as a Claude Code plugin (`.claude-plugin/plugin.json`)
2. Create docs with `/new` (scaffolds valid structure automatically)
3. Migrate existing docs with `/docs-migrate`
4. Change document status with `/docs-status`

Validation runs automatically on session start and stop via hooks.

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

## Contributing

### Add a new document type

1. Create `schemas/<type>.json` following the schema structure
2. Run `uv run scripts/gen_skills.py` — generates the asset template and updates all SKILL.md files

### Add a new skill

1. Create `skills/<name>/SKILL.md.tmpl` with placeholders for schema-derived content
2. Add any new placeholder renderers to `gen_skills.py`
3. Run `uv run scripts/gen_skills.py`

### Modify a skill

Edit the `.tmpl` file, never the generated `SKILL.md`. Run the generator after changes.

### Validate

```bash
uv run scripts/validate.py --format text          # check all docs
uv run scripts/validate.py <path> --format text   # check one file
uv run scripts/gen_skills.py --dry-run            # check for stale generated files
```
