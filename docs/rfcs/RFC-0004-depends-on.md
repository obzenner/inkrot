---
number: 4
title: Replace references with depends_on
status: accepted
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
  - path: plugins/docs-toolkit/scripts/validate.py
    last_verified: "2026-05-19"
---

# RFC-0004: Replace references with depends_on

## Problem

The plugin has three linking mechanisms: `references` (dead-link check), `tracks` (code staleness), and a proposed `depends_on` (structural dependency with status enforcement). But `references` adds no value that `depends_on` doesn't already cover — if a doc structurally depends on another, `depends_on` checks both existence AND status. If a doc merely mentions another for navigation, a markdown link in the body suffices. `references` is a middle ground nobody needs.

## Proposal

Remove `references` from all schemas. Replace with `depends_on`:

```yaml
depends_on:
  - path: ../decisions/0001-docs-toolkit-plugin.md
    required_status:
      - accepted
```

**Validation rules:**

| Rule ID | Severity | Check |
|---------|----------|-------|
| `depends_on.missing` | ERROR | Dependency path doesn't resolve to existing file |
| `depends_on.invalid-status` | ERROR | Dependency exists but status not in `required_status` |
| `depends_on.no-status` | ERROR | Entry missing `required_status` field |
| `depends_on.circular` | ERROR | A→B→...→A cycle detected |

**Field shape:**
- `depends_on` — optional array (not required on every doc — a root ADR may have no dependencies)
- Each entry: `{path: string, required_status: string[]}`
- Path is relative to the doc's directory (same as current references)
- `required_status` lists acceptable statuses — if the dependency's current status isn't in this list, error

**What breaks when violated:**
- Dependency doesn't exist → doc is orphaned (maybe dependency was deleted/moved)
- Dependency in wrong status → doc needs review (the decision it implements was rejected/superseded)
- Circular dependency → logical error in doc hierarchy

**Cycle detection:**
Build a directed graph from all `depends_on` entries across all docs in the validation run. If any cycle exists → error on all docs in the cycle.

**What gets removed:**
- `references` field from all 6 schemas
- `check_references_exist` function from validate.py
- `check_references_superseded` function from validate.py (superseded check moves into depends_on status validation)

**Migration:**
Existing `references` entries in our RFCs become `depends_on` entries with `required_status: [proposed, accepted]`.

## Alternatives

- Keep `references` alongside `depends_on`: Rejected — two mechanisms for doc-to-doc linking creates confusion about when to use which.
- Make `depends_on` required: Rejected — root docs (the first ADR, a standalone learning) may have no dependencies.
- Use `references` with a status check option: Rejected — that's just reinventing `depends_on` with a worse name.

## Resolution

Accepted. Implement immediately.
