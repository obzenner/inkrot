---
number: 2
title: Staleness Detection
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
  - path: plugins/docs-toolkit/scripts/validate.py
    last_verified: "2026-05-12"
---

# RFC-0002: Staleness Detection

## Problem

Documentation drifts from code silently. A spec describes architecture that no longer exists. An ADR references paths that were renamed. There's no signal that a doc is stale until someone reads it and notices.

We need a deterministic mechanism that detects when tracked code has changed relative to what the doc last described, and surfaces this as an error the agent must resolve.

## Proposal

Documents declare which paths (files or directories) they track via a `tracks` field in frontmatter. Each entry records a `last_verified` date. Validation compares this date against the last git commit touching that path. If the path has commits after `last_verified` → error.

One mechanism. No hashes. Git is the SSOT for "when did this change."

## Alternatives

- **Content hash per file**: Rejected — forces file-level granularity, unmaintainable at scale (2000 files = 2000 hash entries). Every whitespace change triggers staleness.
- **Git-independent file mtime**: Rejected — unreliable (clones reset mtimes, builds touch files).
- **LLM semantic comparison**: Rejected — non-deterministic, expensive, not suitable for hooks.

## Resolution

Accepted. `last_verified` + git commit date comparison. Simple, scales to directories of any size, one entry per tracked path.

## Mechanism

### Frontmatter Declaration

```yaml
---
number: 1
title: Docs Toolkit Plugin
status: accepted
date: 2026-05-12
tracks:
  - path: plugins/docs-toolkit/
    last_verified: 2026-05-12
  - path: .docs-toolkit.yml
    last_verified: 2026-05-12
---
```

- `tracks` — optional array, available on all document types
- `path` — relative to repo root (file or directory)
- `last_verified` — date (YYYY-MM-DD) when the doc was last confirmed accurate against this path

### Validation Rules

| Rule ID | Severity | Check |
|---------|----------|-------|
| `tracks.stale` | ERROR | Last git commit in path > `last_verified` date |
| `tracks.path-missing` | ERROR | Tracked path does not exist |
| `tracks.path-format` | ERROR | Path must be relative (no leading `/`), must not contain `..` |
| `tracks.no-date` | ERROR | Entry missing `last_verified` field |

### Staleness Check

```python
import subprocess

def last_commit_date(path: str, repo_root: Path) -> str | None:
    result = subprocess.run(
        ["git", "log", "-1", "--format=%Y-%m-%d", "--", path],
        capture_output=True, text=True, cwd=repo_root,
    )
    return result.stdout.strip() or None
```

Compare: if `last_commit_date > last_verified` → error.

YYYY-MM-DD strings sort lexicographically — no date parsing needed.

### Resolution Flow

When the Stop hook blocks on `tracks.stale`:

1. Agent runs `git diff <last_verified>..HEAD -- <path>` to see what changed
2. Agent reads the doc
3. Agent decides:
   - **Doc needs update** → updates doc content, sets `last_verified` to today
   - **Doc is still accurate** → sets `last_verified` to today only
4. Validation passes on next Stop

Bumping `last_verified` is the "I've reviewed this" signal.

## Agent Resolution Guidance

The Stop hook's `systemMessage`:

```
Error: docs/decisions/0001-docs-toolkit-plugin.md [tracks.stale]
  'plugins/docs-toolkit/' has commits after last_verified (2026-05-10).
  Last commit: 2026-05-12.

  Resolution: Run `git diff 2026-05-10..HEAD -- plugins/docs-toolkit/` to see changes.
  If doc is still accurate, update last_verified to today.
  If doc is outdated, update the doc content AND last_verified.
```

## Testing Plan

### Test 1: Staleness detected (red phase)

1. Create a doc with `tracks: [{path: "plugins/docs-toolkit/", last_verified: "2020-01-01"}]`
2. Run validation → expect `tracks.stale` error (commits exist after 2020)

### Test 2: Up-to-date path (green phase)

1. Create a doc with `last_verified` set to today
2. Run validation → no error

### Test 3: Missing path

1. Track a path that doesn't exist
2. Run validation → expect `tracks.path-missing` error

### Test 4: Invalid path format

1. Track `/absolute/path` or `../escape`
2. Run validation → expect `tracks.path-format` error

### Test 5: Missing last_verified

1. Entry with `path` but no `last_verified`
2. Run validation → expect `tracks.no-date` error

### Test 6: Stop hook blocks and agent resolves

1. Doc tracks a directory with old `last_verified`
2. Stop hook fires, blocks
3. Agent reads git diff, determines doc is fine
4. Agent bumps `last_verified`
5. Stop hook passes

## Dependencies

- Same as slice 1 (Python 3.11+, uv, strictyaml)
- `git` — required for `last_verified` checks

## Assumptions

1. Git is available in the execution environment
2. YYYY-MM-DD string comparison is sufficient (lexicographic = chronological)
3. The agent can read git diffs and determine whether a doc is still accurate
4. Paths with no git history (brand new, never committed) are not stale

## Scope Boundaries (NOT in slice 2)

- No automatic `last_verified` stamping on doc creation (future `docs-new` skill)
- No glob patterns
- No "ignore specific commits" mechanism
