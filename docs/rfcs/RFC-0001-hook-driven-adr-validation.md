---
number: 1
title: Hook-Driven ADR Validation
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
    last_verified: "2026-05-19"
  - path: plugins/docs-toolkit/hooks/hooks.json
    last_verified: "2026-05-19"
---

# RFC-0001: Hook-Driven ADR Validation

## Problem

We need automatic validation of ADR documents inside Claude Code sessions. Validation must be deterministic (script, not LLM interpretation), fire at the right moments (not mid-authoring), and produce structured output the agent can report to the user.

## Proposal

A Claude Code plugin that ships:
1. A Python validation script (self-contained, PEP 723 inline deps)
2. Two hooks that call the script at natural boundaries (SessionStart, Stop)

No skills in this slice. Skills (docs-new, docs-migrate, docs-status) come in later slices.

## Alternatives

- **External CLI tool (adrs, adr-tools)**: Rejected — brittle regex heuristics, false positives on valid content, external binary dependency.
- **Per-repo Python validation scripts**: Rejected — not portable, each repo reinvents.
- **LLM-only validation (prompt-based)**: Rejected — non-deterministic, expensive, can't be used in CI.

## Resolution

Accepted. Implemented as described. Validation script + hooks approach proved out in testing — deterministic, fast (<100ms), zero-config for users after plugin install.

## Architecture

```
plugins/docs-toolkit/
├── .claude-plugin/
│   └── plugin.json           # Plugin manifest
├── hooks/
│   └── hooks.json            # SessionStart + Stop hook definitions
└── scripts/
    └── validate.py       # ADR validation, PEP 723 self-contained
```

## Script Design (validate.py)

### Language Choice: Python

- PEP 723 inline dependencies → single file, no separate manifest
- Run with `uv run` (fast, cached, no install step)
- `strictyaml` for frontmatter parsing (same lib used by agentskills/skills-ref)
- `compatibility` field in plugin.json states: "Requires Python 3.11+ and uv"

### Interface (following agentskills script design guidelines)

**Invocation:**
```bash
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/validate.py" [PATH...]
```

- `PATH` — one or more files or directories to validate
- If no PATH given, scan current working directory for tracked doc directories
- `--help` — usage + examples (agent-readable)
- `--format json|text|hook` — output format (default: json)
  - `json`: structured report for programmatic consumption
  - `text`: human-readable report
  - `hook`: Stop hook output — wraps text report in `decision`/`systemMessage` JSON
- `--type adr` — filter to specific document type (default: all supported types)

**Exit codes:**
- 0: all documents valid
- 1: validation errors found (output contains structured report)
- 2: invocation error (bad arguments, missing dependencies)

**Output (JSON, stdout):**
```json
{
  "scanned": 3,
  "errors": 1,
  "warnings": 1,
  "results": [
    {
      "file": "docs/decisions/0001-docs-toolkit-plugin.md",
      "status": "pass",
      "errors": [],
      "warnings": []
    },
    {
      "file": "docs/decisions/0002-bad-adr.md",
      "status": "fail",
      "errors": [
        {"rule": "frontmatter.status", "message": "Invalid status \"draft\" — must be one of: proposed, accepted, deprecated, superseded, rejected"}
      ],
      "warnings": [
        {"rule": "sections.recommended", "message": "Missing recommended section: \"Considered Options\""}
      ]
    }
  ]
}
```

**Diagnostics → stderr.** Progress, debug info, non-structured messages go to stderr only.

### Validation Rules (ADR only, slice 1)

| Rule ID | Severity | Check |
|---------|----------|-------|
| `naming.pattern` | CRITICAL | Filename matches `NNNN-slug.md` (zero-padded number, lowercase kebab slug) |
| `frontmatter.present` | CRITICAL | File starts with `---` delimited YAML frontmatter |
| `frontmatter.required` | CRITICAL | Fields present: `number` (int), `title` (string), `status` (string), `date` (string YYYY-MM-DD) |
| `frontmatter.status` | CRITICAL | Status is one of: proposed, accepted, deprecated, superseded, rejected |
| `frontmatter.number-match` | ERROR | `number` field matches filename numeric prefix (integer comparison: 1 == 0001) |
| `frontmatter.date-format` | ERROR | `date` field is valid YYYY-MM-DD |
| `sections.required` | ERROR | H2 headings present: "Context and Problem Statement", "Decision Outcome" |
| `sections.recommended` | WARNING | H2 headings present: "Considered Options", "Decision Drivers" |
| `references.exist` | ERROR | If `references` array in frontmatter, each entry resolves to existing file |
| `references.superseded` | ERROR | If status is `superseded`, frontmatter must contain a reference |
| `numbering.unique` | ERROR | No duplicate `number` values within same directory |

### Non-interactive

- No prompts, no confirmation dialogs
- All input via CLI arguments
- Fails fast with clear error messages on bad input

### Idempotent

- Read-only operation — never modifies files
- Safe to run repeatedly, same input → same output

## Hook Design (hooks.json)

### Hook 1: SessionStart

**Purpose:** Surface existing drift once, on session open.

**Behavior:**
- Calls `validate.py --format json` (scans cwd for doc directories)
- If all docs pass: no stdout, Claude sees nothing
- If violations exist: JSON report on stdout, Claude sees it as session context

```json
{
  "type": "command",
  "command": "uv run \"${CLAUDE_PLUGIN_ROOT}/scripts/validate.py\" --format json 2>/dev/null || true"
}
```

SessionStart hook stdout is automatically injected as context Claude can read. No special JSON wrapping needed.

### Hook 2: Stop

**Purpose:** After each turn, validate all docs. Block on errors, surface warnings.

**Behavior:**
- Calls `validate.py --format hook` (scans all tracked doc directories)
- If all docs pass: no stdout, hook is invisible
- If errors exist: outputs `{"decision": "block", "reason": "...", "systemMessage": "..."}` — blocks the turn from ending, Claude must fix
- If warnings only: outputs `{"systemMessage": "..."}` — Claude sees the warnings but is not blocked

```json
{
  "type": "command",
  "command": "uv run \"${CLAUDE_PLUGIN_ROOT}/scripts/validate.py\" --format hook 2>/dev/null || true"
}
```

**Key difference from SessionStart:** Stop hooks do NOT inject stdout as context by default. They require structured JSON output with specific fields:
- `decision: "block"` — prevents Claude from stopping, forces correction
- `systemMessage` — the text Claude actually reads
- Without `decision: "block"`, `systemMessage` is surfaced but non-blocking

**Self-correction loop:** write doc → turn ends → validate → errors → block + systemMessage → agent fixes → turn ends → validate → clean.

### hooks.json structure

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "uv run \"${CLAUDE_PLUGIN_ROOT}/scripts/validate.py\" --format json 2>/dev/null || true"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "uv run \"${CLAUDE_PLUGIN_ROOT}/scripts/validate.py\" --format hook 2>/dev/null || true"
          }
        ]
      }
    ]
  }
}
```

### Hook Output Contracts

**SessionStart:**
- stdout (plain text or JSON) → injected as context to Claude
- Empty stdout → Claude sees nothing
- stderr → discarded (`2>/dev/null`)

**Stop:**
- stdout must be structured JSON with `decision` and/or `systemMessage` fields
- Empty stdout → hook is invisible
- `decision: "block"` → prevents turn from ending
- `systemMessage` → text Claude reads (whether blocked or not)
- stderr → discarded (`2>/dev/null`)

## Testing Plan — Results

### Manual test 1: Script standalone — PASSED

```bash
uv run plugins/docs-toolkit/scripts/validate.py docs/decisions/0001-docs-toolkit-plugin.md --format text
```

Result: exit 0, silence (no errors or warnings on the real ADR).

### Manual test 2: Script catches errors — PASSED

All 11 rules tested with deliberately broken ADRs:
- naming.pattern, frontmatter.present, frontmatter.required, frontmatter.status
- frontmatter.number-match, frontmatter.date-format
- sections.required, sections.recommended
- references.exist, references.superseded, numbering.unique

### Manual test 3: SessionStart hook — PASSED

```bash
claude --plugin-dir ./plugins/docs-toolkit
```

- Clean docs: hook is silent (confirmed by adding debug echo, then removing)
- Broken docs: JSON report injected as session context

### Manual test 4: Stop hook blocks on errors — PASSED

Created a broken ADR in-session. Stop hook fired, blocked with `decision: "block"`, showed systemMessage with validation errors. Agent self-corrected.

### Manual test 5: Stop hook silent on clean — PASSED

After fixing the broken ADR, Stop hook produced no output on subsequent turns.

## Dependencies

- Python 3.11+
- uv (for `uv run` with PEP 723 inline deps)
- Script inline deps: `strictyaml>=1.7.3` (YAML parsing), no others needed for slice 1

## Assumptions

1. Users of this plugin have `uv` installed (standard at Funnel) — **verified**
2. `${CLAUDE_PLUGIN_ROOT}` resolves correctly in hook commands — **verified**
3. Stop hook `decision: "block"` prevents turn from ending and `systemMessage` is read by Claude — **verified**
4. Running validate.py on every Stop is cheap enough (scanning a handful of markdown files) to not degrade session performance — **verified** (runs in <100ms)

## Coding Conventions

Per SOUL.md principles, applied to this script:

1. **Functional composition** — small pure functions, no classes. `validate_file(path) → Result`.
2. **Name transforms** — no inline logic in map/filter. Extract: `check_naming`, `check_frontmatter`, `check_sections`, etc.
3. **Conditions as data** — validation rules declared as a list of rule descriptors, not imperative if/elif chains. Active rules filtered, then mapped to results.
4. **No imperative slop** — no `errors = []; if x: errors.append(...)`. Rules produce results; results are collected via comprehension or functional pipeline.
5. **Modern tooling** — `uv run`, PEP 723 inline deps, `strictyaml`. No `pip`, no `argparse` (use `click` if arg parsing grows beyond trivial).
6. **One script per doc type** — `validate.py`, `validate_rfc.py`, etc. Each PEP 723 self-contained. A thin dispatcher (`validate.py`) arrives when there are 2+ types to route between.
7. **No premature abstraction across doc types** — slice 1 is ADR-only. Don't build a generic "doc type registry" until slice 2 proves what's actually shared.
8. **Structured output** — JSON on stdout, diagnostics on stderr. No mixed-format output.

## Scope Boundaries (NOT in slice 1)

- No RFC/Runbook/Spec/Tasks/Learnings validation
- No cross-reference bidirectional enforcement
- No cycle detection
- No docs-new, docs-migrate, docs-status skills
- No marketplace.json registration (manual plugin loading only for testing)
