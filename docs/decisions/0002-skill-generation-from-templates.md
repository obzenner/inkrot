---
number: 2
title: Skill Generation from Templates
status: proposed
date: 2026-05-12
decision-makers:
consulted:
informed:
tags:
tracks:
  - path: plugins/docs-toolkit/skills/
    last_verified: "2026-05-12"
---

# Skill Generation from Templates

## Context and Problem Statement

Skills contain instructions that reference doc types, required sections, naming conventions, and validation rules. These facts are already defined in `validate.py` (the `DOC_TYPES` dict). When we add a new doc type or change validation rules, the skills become stale — but there's no mechanism to detect or prevent this drift.

The agentskills spec has no built-in staleness mechanism. gstack solves this by treating SKILL.md as a generated artifact: a `.tmpl` template + a generator script that reads source code = the SKILL.md. CI runs `--dry-run` to catch drift.

## Decision Drivers

- Skills must stay in sync with validation rules (DOC_TYPES is the SSOT)
- Manual updates are error-prone and don't scale
- The pattern is proven (gstack uses it in production across 30+ skills)
- Should work with the existing hook infrastructure (staleness → error → agent fixes)

## Considered Options

- Manual skill maintenance with tracks-based staleness detection
- Template generation from DOC_TYPES (gstack pattern)
- LLM-based skill rewriting on each validation change

## Decision Outcome

Chosen option: "Template generation from DOC_TYPES", because it's deterministic, CI-checkable, and the source of truth for doc types already exists in code.

### Implementation

1. `skills/create-document/SKILL.md.tmpl` — template with `{{DOC_TYPES_TABLE}}`, `{{DEFAULT_PATHS}}` placeholders
2. `scripts/gen_skills.py` — PEP 723 script that reads DOC_TYPES from validate.py and fills templates
3. `SKILL.md` becomes a generated file (header: `<!-- AUTO-GENERATED — do not edit directly -->`)
4. Stop hook or pre-commit: `gen_skills.py --dry-run` flags drift
5. Agent resolves by running `gen_skills.py` to regenerate

### Generator reads from validate.py

The generator imports or parses `DOC_TYPES` and produces:
- Doc type table (type, naming, sections, statuses)
- Default directory paths per type
- Template file list in assets/

This means adding a new doc type to `DOC_TYPES` automatically propagates to the skill — no manual skill editing needed.

## More Information

Prior art: gstack's `gen-skill-docs.ts` + `SKILL.md.tmpl` pattern. Their generator also supports `--dry-run` for CI freshness checks and multi-host output (Claude, Codex, Factory). We only need single-host (Claude) for now.
