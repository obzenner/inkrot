---
number: 8
title: Hook-Enforced Regeneration and Version Bump
status: draft
date: 2026-05-12
authors:
  - obzenner
depends_on:
  - path: ../rfcs/RFC-0006-all-skills-generated.md
    required_status:
      - draft
      - accepted
  - path: ../rfcs/RFC-0007-generated-claude-md.md
    required_status:
      - draft
      - accepted
tracks:
  - path: .claude/settings.json
    last_verified: "2026-05-12"
---

# RFC-0008: Hook-Enforced Regeneration and Version Bump

## Problem

Two failure modes exist after RFC-0006 and RFC-0007:

1. **Stale output.** An agent edits a schema or `.tmpl` file but forgets to run the generators. Generated files drift from their sources. The `--dry-run` checks exist but nothing triggers them automatically during a session.

2. **Missing version bump.** Any change that alters generated output is a user-visible change — it should bump the semver in `plugin.json`. Agents don't do this unless told.

Both are enforcement gaps: the tools exist but nothing forces their use at the right time.

## Proposal

Two repo-level hooks in `.claude/settings.json`, running on SessionStart and Stop. These are **not** plugin hooks — they apply only when working on the inkrot repo itself.

### Hook 1: Stop — staleness advisory

On every `Stop` event, run `check_freshness.py`. If generated files are stale or the version wasn't bumped, emit plain text that gets injected as `additionalContext` — the agent sees it and can self-correct without user intervention.

We explicitly do NOT use `"continue": false` because that blocks the session but the agent never sees the reason — only the user does. Plain text output is the mechanism that gives the agent visibility.

### Hook 2: SessionStart — freshness check on load

On session start, run the same check. If the agent enters a session with already-stale files (e.g. someone edited a schema manually), it knows immediately and can fix them.

### Script: `scripts/check_freshness.py`

Combines checks across both generators:

1. Run `plugins/inkrot/scripts/gen_skills.py --dry-run` — are plugin-internal files stale?
2. Run `scripts/gen_claude_md.py --dry-run` — is CLAUDE.md stale?
3. If anything is stale, check if `plugin.json` version was bumped vs last committed version

Output:
- If fresh → silent exit (no output)
- If stale → plain text with fix instructions (injected as additionalContext to the agent on both SessionStart and Stop)

### Version bump rules

| Change | Bump |
|--------|------|
| Fix typo in template | PATCH |
| Add/modify schema field | MINOR |
| Add new doc type schema | MINOR |
| Add new skill template | MINOR |
| Change gen_skills.py rendering logic | MINOR |
| Remove a doc type or skill | MAJOR |

### .claude/settings.json

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "uv run scripts/protect_claude_md.py"
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "uv run scripts/check_freshness.py"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "uv run scripts/check_freshness.py"
          }
        ]
      }
    ]
  }
}
```

## Alternatives

- **CI-only check (GitHub Action):** Rejected — catches staleness after push, not during the session where the agent can fix it.
- **PostToolUse advisory after each source write:** Rejected — too noisy. SessionStart + Stop is sufficient.
- **Auto-bump version in gen_skills.py:** Rejected — the script shouldn't decide PATCH vs MINOR. The agent should decide.
- **Put these hooks in the plugin's hooks.json:** Rejected — these are development-time concerns for this repo. The plugin's hooks are for consumer repos.

## Resolution

Draft. Pending implementation.
