---
number: 6
title: All Skills Must Be Generated from Templates
status: draft
date: 2026-05-12
authors:
  - obzenner
depends_on:
  - path: ../decisions/0002-skill-generation-from-templates.md
    required_status:
      - proposed
      - accepted
tracks:
  - path: plugins/docs-toolkit/skills/
    last_verified: "2026-05-12"
---

# RFC-0006: All Skills Must Be Generated from Templates

## Problem

Only `create-document` is generated from a template. `docs-migrate` and `docs-status` are hand-written SKILL.md files. This creates two problems:

1. **Drift.** `docs-migrate` contains a classification table that references doc types, sections, and content signals — all derived from schemas. When schemas change, this table goes stale silently. There's no mechanism to catch it.

2. **Inconsistency.** The PreToolUse write-protection hook only blocks edits to `create-document/SKILL.md`. The other skills can be edited directly, bypassing the "schemas are SSOT" principle. An agent (or human) can modify `docs-migrate/SKILL.md` without touching schemas, creating a divergence.

The ADR-0002 decision says "skills are generated from templates using DOC_TYPES as source of truth." This isn't fully implemented — only one of three skills follows this pattern.

## Proposal

Every skill in the plugin must have a `.tmpl` source file. `gen_skills.py` generates ALL SKILL.md files from templates. The PreToolUse hook blocks writes to ALL generated SKILL.md files.

### What changes

1. **`docs-migrate/SKILL.md.tmpl`** — template with `{{DOC_TYPES_TABLE}}`, `{{CLASSIFICATION_TABLE}}`, `{{DISCOVERY_DEFAULTS}}` placeholders. The classification signals table is derived from schemas.

2. **`docs-status/SKILL.md.tmpl`** — template with `{{STATUS_TRANSITIONS}}` placeholder. The status table per doc type is derived from schemas.

3. **`gen_skills.py` expanded** — discovers all `.tmpl` files in `skills/*/`, not just `skills/create-document/`. Generates SKILL.md for each.

4. **`protect_generated.py` expanded** — blocks writes to ALL `skills/*/SKILL.md` files, not just create-document.

### What content is schema-derived in each skill

| Skill | Schema-derived content |
|-------|----------------------|
| create-document | Doc types table, default paths, supported types list |
| docs-migrate | Classification signals table, doc type sections, default directories |
| docs-status | Valid statuses per type, transition rules |

### What content is static (stays in template)

| Skill | Static content |
|-------|---------------|
| create-document | Workflow steps, error handling |
| docs-migrate | Workflow phases, rules, error handling |
| docs-status | Workflow steps, enforcement rules logic |

### Template placeholder design

New placeholders for gen_skills.py to resolve:

- `{{CLASSIFICATION_TABLE}}` — signals → doc type mapping (derived from schemas' sections + discovery defaults)
- `{{STATUS_TRANSITIONS}}` — markdown table of type → valid statuses (from schemas' frontmatter enum fields)
- `{{ALL_SCHEMAS_SUMMARY}}` — compact summary of all schemas for inline reference

## Alternatives

- **Keep some skills hand-written:** Rejected — this is what we have now and it causes drift.
- **Only protect files that have schema-derived content:** Rejected — partial protection is confusing. All or nothing.
- **Lint for staleness instead of blocking edits:** Rejected — staleness detection after the fact is weaker than preventing direct edits.

## Resolution

Draft. Pending implementation.
