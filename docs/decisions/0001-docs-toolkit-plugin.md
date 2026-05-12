---
number: 1
title: Docs Toolkit Plugin
status: proposed
date: 2026-05-11
decision-makers:
consulted:
informed:
tags:
tracks:
  - path: plugins/docs-toolkit/
    last_verified: "2026-05-12"
  - path: .docs-toolkit.yml
    last_verified: "2026-05-12"
---

# Docs Toolkit Plugin

## Context and Problem Statement

How should teams standardize documentation practices across repositories without coupling to repo-specific tooling or fragile CLI validators?

Engineering teams produce recurring document types — architecture decisions, RFCs, runbooks, specs — but each repo invents its own structure, naming, and validation. This leads to inconsistent quality, missing sections, stale status fields, and no portable way to enforce standards. External CLI tools (e.g. `adr-tools`, `adrs`) attempt to solve this but impose rigid heuristics that produce false positives on valid content (markdown tables misidentified as placeholder text, subsection depth confusing section parsers).

A Claude Code plugin can validate documentation structurally and semantically without brittle regex heuristics, and can also assist in creating, migrating, and maintaining docs — making it both a linter and a workflow tool.

## Decision Drivers

* Portable across any repository without repo-specific configuration scripts
* Supports industry-standard document formats (MADR 4.0, RFC, runbook, spec)
* Validates structure, status consistency, and cross-document linkage
* Can migrate existing non-conforming docs to the standard format
* No external binary dependencies — the plugin is self-contained
* Works as both a reactive validator (check existing docs) and proactive assistant (create new docs)

## Considered Options

* External CLI tool (adrs, adr-tools, log4brains) with CI integration
* Per-repo Python validation scripts
* Claude Code plugin with embedded standards and agentic validation

## Decision Outcome

Chosen option: "Claude Code plugin with embedded standards and agentic validation", because it eliminates external dependencies, handles semantic validation that regex-based tools cannot, and provides a migration path for existing repos with non-conforming documentation.

The plugin (`docs-toolkit`) ships as a skill-based Claude Code plugin in this marketplace. It defines four industry-standard document types with their schemas, required sections, and lifecycle rules. Validation is performed by Claude reading the actual documents and checking against the embedded standards — no shell-out to external binaries.

### Document Types

| Type | Standard / Prior Art | Required Sections | Statuses |
|------|---------------------|-------------------|----------|
| ADR | MADR 4.0.0 | Context and Problem Statement, Decision Outcome | proposed, accepted, deprecated, superseded, rejected |
| RFC | Rust RFC / Python PEP (structure only) | Problem, Proposal, Alternatives, Resolution | draft, open, accepted, rejected, withdrawn |
| Runbook | Google SRE Book Ch. 8 + PagerDuty template | Purpose, Prerequisites, Steps, Rollback, Escalation | active, deprecated, draft |
| Spec | spec-kit (funnel-io) | User Scenarios, Requirements, Success Criteria, Assumptions | draft, approved, implemented, abandoned |
| Tasks | spec-kit (funnel-io) | Phases, Task Items (checkboxed), Dependencies | active, completed, abandoned |
| Learnings | (new — see subtypes below) | Subtype-dependent (see below) | draft, published, archived |

#### Spec — Prior Art

The Spec type adopts its structure from [spec-kit](https://github.com/funnel-io/spec-kit), a battle-tested specification workflow used internally. Required sections:

- **User Scenarios** — prioritized user journeys (P1, P2, P3…), each independently testable with Given/When/Then acceptance scenarios
- **Requirements** — numbered functional requirements (FR-001, FR-002…) using RFC 2119 language (MUST, SHOULD, MAY). Unclear requirements marked `[NEEDS CLARIFICATION]`
- **Success Criteria** — measurable outcomes (SC-001, SC-002…), technology-agnostic
- **Assumptions** — explicit assumptions about scope, environment, and dependencies

#### Tasks — Prior Art

The Tasks type adopts its structure from spec-kit's task breakdown workflow. Required structure:

- **Phases** — ordered groups (Setup → Foundation → User Stories → Polish), each with a stated purpose
- **Task Items** — checkboxed (`- [ ] T001 …`), with `[P]` marker for parallelizable tasks and `[US1]` labels for story traceability
- **Dependencies** — explicit phase ordering and within-phase dependency declarations
- **Checkpoints** — verification gates between phases

#### Learnings — Subtypes

Learnings is a parent type with three subtypes, each with distinct required sections:

| Subtype | Trigger | Required Sections |
|---------|---------|-------------------|
| Incident | Outage or failure event | Timeline, Impact, Root Cause, Remediation, Prevention |
| Retrospective | Project close or milestone | Context, What Went Well, What Didn't, Action Items |
| TIL | Knowledge discovery | Discovery, Context, Implication, References |

All subtypes share:
- YAML frontmatter with `subtype: incident|retrospective|til`, `title`, `date` (when the learning occurred, not when documented)
- Cross-references via the standard `references` field (links to relevant ADRs, specs, tasks, or other learnings)

### Skills

| Skill | Purpose |
|-------|---------|
| `create-document` | Create a new document from the correct template for its type |
| `docs-migrate` | Migrate existing non-conforming docs to standard format (agentic, per-file) |
| `docs-status` | Change document status with linkage enforcement (e.g. supersede requires reference) |

Validation is hook-driven (SessionStart + Stop), not a skill. The agent can run `validate.py` directly if manual validation is needed.

### Validation Rules (docs-doctor)

**Structural:**
- Required sections present for the document type
- YAML frontmatter contains required fields (see table below)
- Number in frontmatter matches filename prefix (ADRs, RFCs, Learnings)
- No duplicate document numbers within a type

**Required Frontmatter by Type:**

| Type | Required | Optional |
|------|----------|----------|
| ADR | `number`, `title`, `status`, `date`, `tracks` | `depends_on`, `decision-makers`, `tags` |
| RFC | `number`, `title`, `status`, `date`, `authors`, `tracks` | `depends_on`, `tags` |
| Runbook | `title`, `status`, `last-verified`, `tracks` | `depends_on`, `owner`, `tags` |
| Spec | `title`, `status`, `date`, `tracks` | `depends_on`, `branch`, `tags` |
| Tasks | `title`, `status`, `tracks` | `depends_on`, `tags` |
| Learnings | `number`, `subtype`, `title`, `status`, `date`, `tracks` | `depends_on`, `tags` |

**Dependencies (`depends_on`):**
- Every document type supports an optional `depends_on` array in frontmatter
- Each entry: `{path: relative_path, required_status: [list of acceptable statuses]}`
- Validation checks: dependency exists AND its status is in the required_status list
- Circular dependencies are detected and error across all docs in the cycle
- If a dependency's status changes to something not in required_status, all dependent docs get flagged

**Status and Linkage:**
- Status value is valid for the document type
- Replacement documents reference what they supersede (bidirectional — subset of the general cross-reference rule above)

**Naming:**
- ADRs: `NNNN-slug.md`
- RFCs: `RFC-NNNN-slug.md`
- Runbooks: `RUNBOOK-slug.md`
- Specs: `SPEC-slug.md`
- Tasks: `TASK-slug.md`
- Learnings: `LEARNING-NNNN-slug.md`

### Drift Prevention

The plugin ships two hooks calling a deterministic validation script (`validate.py`), chosen for their timing relative to authoring:

**Why not `PostToolUse` on Write|Edit?** That fires on every individual file write — including mid-authoring. If Claude is writing a doc in 3 edits (frontmatter, then Context section, then Decision Outcome), PostToolUse fires after edit 1 and complains about missing sections that haven't been written yet. This is noise, not enforcement.

**Hook 1: `SessionStart` — Awareness**

On session start, run the validation script. SessionStart hook stdout is automatically injected as context Claude can read. If all docs pass, the script produces no output (silent). If violations exist, Claude sees the report.

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
    ]
  }
}
```

**Hook 2: `Stop` — Enforcement**

After each Claude turn, run the validation script with `--format hook`. Stop hooks require structured JSON output — plain stdout is not injected as context. The script outputs:
- Errors: `{"decision": "block", "reason": "...", "systemMessage": "..."}` — blocks the turn from ending, forces Claude to fix
- Warnings only: `{"systemMessage": "..."}` — Claude sees them but is not blocked
- All clean: no output (silent)

```json
{
  "hooks": {
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

**Hook 3: `PreToolUse` — Write Protection**

Generated files (SKILL.md, asset templates) are produced by `gen_skills.py` from schemas. A PreToolUse hook blocks `Write|Edit` to these files, denying with a message pointing to the regeneration command.

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

**Why these three events:**

| Event | Purpose | Timing | Noise |
|-------|---------|--------|-------|
| `SessionStart` | Surface existing drift | Once per session | None |
| `Stop` | Block on errors, surface warnings | After each turn completes | Only when docs have violations |
| `PreToolUse` | Prevent edits to generated files | Before Write/Edit | Only on protected paths |

Together they cover: "know about existing problems" (SessionStart) + "don't create new ones" (Stop) + "don't hand-edit generated files" (PreToolUse). CI enforcement via `claude-code-action` remains as a fourth gate for PRs.

### Migration Approach

The `docs-migrate` skill operates per-file, interactively:

1. Detect document type from location, frontmatter, or content
2. Identify structural gaps (missing sections, wrong frontmatter fields)
3. Propose minimal edits to conform — add missing section headings with content extracted from existing prose where possible
4. Never delete or rewrite existing content — only restructure and annotate

This allows teams with existing documentation to adopt the standard incrementally without mass-rewriting their docs.

### Consequences

* Good, because no external binary dependencies — works anywhere Claude Code runs
* Good, because semantic validation avoids false positives from regex heuristics
* Good, because migration skill provides a path for existing repos without a big-bang rewrite
* Good, because one plugin serves all document types with a unified validation model
* Good, because bidirectional linkage enforcement catches orphaned supersede references
* Good, because drift prevention is automatic on install via SessionStart + Stop hooks — no user setup, no mid-authoring noise, validates at natural boundaries
* Good, because CI enforcement is trivial via `claude-code-action` — the plugin runs in GitHub Actions the same as locally (second gate for non-plugin workflows)
* Good, because Spec and Tasks types derive from a proven internal tool (spec-kit), not invented from scratch
* Bad, because the plugin must encode document standards in skill prose rather than a machine-readable schema
* Bad, because RFC, Runbook, and Learnings types lack a single citable versioned standard — the plugin defines its own conventions drawing from multiple sources

### Directory Discovery

The plugin discovers documentation directories via an optional config file (`.docs-toolkit.yml`) at the repo root. If no config exists, defaults apply.

**Config file (`.docs-toolkit.yml`):**

```yaml
paths:
  decisions:
    - docs/decisions
    - services/auth/docs/decisions
  rfcs:
    - docs/rfcs
  runbooks:
    - ops/runbooks
  specs:
    - docs/specs
  tasks:
    - docs/tasks
  learnings:
    - docs/learnings
```

**Default paths (when no config exists):**

| Type | Default directories scanned |
|------|----------------------------|
| ADR | `decisions/`, `docs/decisions/`, `adrs/`, `docs/adrs/` |
| RFC | `rfcs/`, `docs/rfcs/` |
| Runbook | `runbooks/`, `docs/runbooks/` |
| Spec | `specs/`, `docs/specs/` |
| Tasks | `tasks/`, `docs/tasks/` |
| Learnings | `learnings/`, `docs/learnings/` |

This supports monorepos (multiple paths per type), custom layouts (non-standard directory names), and zero-config repos (defaults just work).

## More Information

The plugin targets any repository that uses markdown-based documentation with YAML frontmatter. It discovers documents via the configurable path mechanism above, falling back to sensible defaults when no config is present.

CI enforcement uses `claude-code-action` (already deployed across Funnel repos). A PR-triggered workflow can invoke the validation script as a gate — same plugin, same rules, no separate scripts to maintain.
