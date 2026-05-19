---
number: 5
title: Explanation and Reference Document Types
status: draft
date: 2026-05-12
authors:
  - obzenner
depends_on:
  - path: ../decisions/0001-docs-toolkit-plugin.md
    required_status:
      - proposed
      - accepted
tracks:
  - path: plugins/docs-toolkit/schemas/
    last_verified: "2026-05-19"
---

# RFC-0005: Explanation and Reference Document Types

## Problem

Engineering teams produce two kinds of knowledge documentation that don't fit existing types:

1. **Explanations** — "How does X work?" and "Why is it this way?" Understanding-oriented prose that provides context, rationale, and mental models. Currently exists as `topics/` directories in some repos.

2. **References** — "What are the exact parameters/shapes/APIs?" Information-oriented lookup material that mirrors product structure. Currently exists as `references/` and `domain-knowledge/` directories.

These are the two "cognition" quadrants from the Diataxis documentation framework (Explanation = cognition + acquisition; Reference = cognition + application). The plugin validates 6 doc types but none cover pure knowledge documentation.

## Proposal

Add two new doc types to the plugin schemas.

### Explanation

**Purpose:** Understanding-oriented. Provides context, rationale, history, and mental models. Answers "why?" and "how does this work conceptually?"

**Prior art:** Diataxis "Explanation" quadrant. Titles implicitly prefixed with "About" (e.g., "About authentication flow").

```json
{
  "type": "explanation",
  "naming": {
    "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*\\.md$",
    "description": "slug.md (lowercase kebab, no prefix)",
    "example": "authentication-flow.md"
  },
  "discovery": {
    "config_key": "explanations",
    "defaults": ["topics", "docs/topics", "explanations", "docs/explanations"]
  },
  "frontmatter": {
    "fields": [
      {"name": "title", "type": "string", "required": true},
      {"name": "date", "type": "date", "required": true},
      {"name": "depends_on", "type": "depends_on", "required": false},
      {"name": "tags", "type": "array", "required": false},
      {"name": "tracks", "type": "tracks", "required": true}
    ]
  },
  "sections": {
    "required": [],
    "recommended": []
  },
  "numbering": {
    "enabled": false
  }
}
```

**No required sections.** Diataxis explicitly says explanation structure should emerge from the topic's conceptual boundaries, not a rigid template. Validation focuses on frontmatter correctness, naming, and tracks — not section headings.

**No status field.** Explanations aren't lifecycle documents. They're living knowledge — always evolving, never "approved" or "rejected." Staleness is caught via `tracks`.

### Reference

**Purpose:** Information-oriented. Provides exact specifications, parameters, shapes, APIs. Mirrors the product structure. Answers "what are the options?" and "what does this accept?"

**Prior art:** Diataxis "Reference" quadrant. Structure mirrors the thing being documented (API endpoints map to headings, CLI flags map to definition lists).

```json
{
  "type": "reference",
  "naming": {
    "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*\\.md$",
    "description": "slug.md (lowercase kebab, no prefix)",
    "example": "api-endpoints.md"
  },
  "discovery": {
    "config_key": "references",
    "defaults": ["references", "docs/references", "domain-knowledge", "docs/domain-knowledge"]
  },
  "frontmatter": {
    "fields": [
      {"name": "title", "type": "string", "required": true},
      {"name": "date", "type": "date", "required": true},
      {"name": "depends_on", "type": "depends_on", "required": false},
      {"name": "tags", "type": "array", "required": false},
      {"name": "tracks", "type": "tracks", "required": true}
    ]
  },
  "sections": {
    "required": [],
    "recommended": []
  },
  "numbering": {
    "enabled": false
  }
}
```

**No required sections.** Reference docs mirror product structure — their headings should correspond to the thing they document (API routes, CLI commands, config keys), not a plugin-imposed template.

**No status field.** Same reasoning as explanation — living documents, not lifecycle artifacts. `tracks` handles staleness.

### Why no required sections?

The existing types (ADR, RFC, Spec, Runbook, Tasks) are **process documents** — they follow a workflow with defined steps. Their sections encode that workflow.

Explanation and Reference are **knowledge documents** — their structure is dictated by the subject matter, not a process. Forcing "## Overview" and "## Details" on every explanation would be arbitrary. Forcing "## API" and "## Parameters" on every reference would be wrong for a reference about config file formats.

What we DO validate:
- Frontmatter present and correct
- Naming convention (simple slug, no prefix — these aren't numbered)
- `tracks` present (they describe something, must be traceable)
- Unknown fields rejected

### Naming: no prefix, no number

Explanations and references are looked up by topic name, not by sequence number. `authentication-flow.md` is better than `EXPLANATION-0001-authentication-flow.md`. The directory provides the type context (`topics/authentication-flow.md`).

### Discovery defaults

Both types support the directory names already in use:
- Explanations: `topics/`, `docs/topics/`, `explanations/`, `docs/explanations/`
- References: `references/`, `docs/references/`, `domain-knowledge/`, `docs/domain-knowledge/`

## Alternatives

- **Merge into one "knowledge" type:** Rejected — explanation and reference serve different purposes (understanding vs. lookup), live in different directories, and would confuse classification.
- **Add required sections (Overview, Details, etc.):** Rejected — per Diataxis, these doc types derive structure from their subject, not from a template. Rigid sections would produce bad docs.
- **Add status lifecycle:** Rejected — knowledge docs don't get "approved" or "rejected." They get updated or deleted. `tracks` detects when they need updating.

## Resolution

Draft. Pending implementation.
