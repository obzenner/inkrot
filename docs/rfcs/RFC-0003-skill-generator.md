---
number: 3
title: Schema-Driven Validation and Skill Generation
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
  - path: plugins/docs-toolkit/scripts/
    last_verified: "2026-05-19"
  - path: plugins/docs-toolkit/skills/
    last_verified: "2026-05-19"
---

# RFC-0003: Schema-Driven Validation and Skill Generation

## Problem

Two problems, one root cause:

1. **Validation rules are hardcoded in Python** — `DOC_TYPES` in `validate.py` defines rules as a Python dict with `re.compile()` and `frozenset()`. Not portable, not inspectable by other tools, not usable as a schema definition.

2. **Skills go stale** — the `docs-toolkit:new` skill hardcodes ADR knowledge. When doc types change in the validator, the skill drifts. No mechanism to prevent it.

Both problems exist because there's no formal schema. The schema should be the single source of truth that drives both validation and skill generation.

## Proposal

### Core idea

JSON schema files define each doc type completely. Two consumers read them:
- `validate.py` — validates documents against the schema
- `gen_skills.py` — generates SKILL.md and asset templates from the schema

### Architecture

```
plugins/docs-toolkit/
├── schemas/
│   ├── adr.json
│   ├── rfc.json
│   ├── spec.json
│   ├── runbook.json
│   ├── tasks.json
│   └── learnings.json
├── scripts/
│   ├── validate.py           # Reads schemas/, validates docs
│   └── gen_skills.py         # Reads schemas/, generates skills
├── skills/
│   └── create-document/
│       ├── SKILL.md.tmpl     # Template with placeholders
│       ├── SKILL.md          # Generated (write-protected)
│       └── assets/
│           └── *.md          # Generated templates per doc type
```

### Schema format (per doc type)

```json
{
  "type": "adr",
  "naming": {
    "pattern": "^(\\d{4,})-[a-z0-9]+(?:-[a-z0-9]+)*\\.md$",
    "description": "NNNN-slug.md (zero-padded number, lowercase kebab)",
    "example": "0001-use-postgres.md"
  },
  "discovery": {
    "config_key": "decisions",
    "defaults": ["decisions", "docs/decisions", "adrs", "docs/adrs"]
  },
  "frontmatter": {
    "fields": [
      {"name": "number", "type": "integer", "required": true},
      {"name": "title", "type": "string", "required": true},
      {"name": "status", "type": "enum", "required": true, "values": ["proposed", "accepted", "deprecated", "superseded", "rejected"]},
      {"name": "date", "type": "date", "required": true},
      {"name": "decision-makers", "type": "array", "required": false},
      {"name": "consulted", "type": "array", "required": false},
      {"name": "informed", "type": "array", "required": false},
      {"name": "tags", "type": "array", "required": false},
      {"name": "references", "type": "array", "required": false},
      {"name": "tracks", "type": "tracks", "required": true}
    ]
  },
  "sections": {
    "required": [
      {"name": "Context and Problem Statement", "description": "What is the issue and why does it need a decision?"},
      {"name": "Decision Outcome", "description": "What was decided and why?"}
    ],
    "recommended": [
      {"name": "Considered Options", "description": "What alternatives were evaluated?"},
      {"name": "Decision Drivers", "description": "What forces influence this decision?"}
    ]
  },
  "numbering": {
    "enabled": true,
    "field": "number",
    "filename_group": 1
  },
  "template": {
    "initial_status": "proposed",
    "placeholder_sections": true
  }
}
```

### Field types

| Type | Validation |
|------|-----------|
| `string` | Non-empty string |
| `integer` | Parseable as int |
| `date` | YYYY-MM-DD format |
| `enum` | Value in `values` array |
| `array` | List (can be empty) |
| `tracks` | Array of `{path, last_verified}` entries — existing tracks validation rules apply |

### Learnings: subtype-dependent sections

The learnings schema has an additional `subtypes` field:

```json
{
  "type": "learnings",
  "subtypes": {
    "field": "subtype",
    "values": {
      "incident": {
        "required_sections": ["Timeline", "Impact", "Root Cause", "Remediation", "Prevention"]
      },
      "retrospective": {
        "required_sections": ["Context", "What Went Well", "What Didn't", "Action Items"]
      },
      "til": {
        "required_sections": ["Discovery", "Context", "Implication", "References"]
      }
    }
  }
}
```

### validate.py refactor

Current `DOC_TYPES` dict gets replaced with schema loading:

```python
def load_schemas(schema_dir: Path) -> dict:
    schemas = {}
    for f in schema_dir.glob("*.json"):
        schema = json.loads(f.read_text())
        schemas[schema["type"]] = schema
    return schemas
```

Check functions become generic — they read field definitions from the schema instead of hardcoded constants:

```python
def check_frontmatter_fields(meta: dict, schema: dict) -> list[Violation]:
    required = [f for f in schema["frontmatter"]["fields"] if f["required"]]
    missing = [f["name"] for f in required if f["name"] not in meta]
    ...

def check_field_type(name: str, value, field_def: dict) -> list[Violation]:
    match field_def["type"]:
        case "integer": ...
        case "date": ...
        case "enum": ...
        case "string": ...
        case "array": ...
        case "tracks": ...
```

### gen_skills.py

Reads the same schemas and produces:

1. **SKILL.md** — from `SKILL.md.tmpl`, filling placeholders with data derived from all schemas
2. **Asset templates** — one per doc type, with correct frontmatter fields and section headings from the schema

### Write protection

`PreToolUse` hook blocks `Write|Edit` to generated files:

```json
{
  "PreToolUse": [
    {
      "matcher": "Write|Edit",
      "hooks": [
        {
          "type": "command",
          "command": "uv run \"${CLAUDE_PLUGIN_ROOT}/scripts/protect_generated.py\""
        }
      ]
    }
  ]
}
```

Deny message: "This file is generated. Edit schemas/ and run `uv run scripts/gen_skills.py` to regenerate."

### Staleness detection

Stop hook runs `gen_skills.py --dry-run`. Exit 1 → stale → block → agent regenerates.

### Workflow for adding/changing a doc type

1. Edit or add a schema file in `schemas/`
2. Run `uv run scripts/gen_skills.py` (or let the Stop hook catch it)
3. `validate.py` automatically picks up the new schema on next run

One file to edit. Two scripts consume it. Everything stays in sync.

## Alternatives

- **Keep DOC_TYPES as Python dict**: Rejected — not portable to gen_skills.py without import hacks or fragile regex parsing.
- **YAML schemas**: Rejected — YAML needs its own validation. JSON validates itself (`json.loads()` either parses or fails).
- **Manual skill maintenance**: Rejected — per ADR-0002.

## Resolution

Draft. Pending implementation.
