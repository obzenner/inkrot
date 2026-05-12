---
name: docs-migrate
description: Migrate existing documentation to docs-toolkit standards. Performs full repository scan, maps every markdown file to a schema, proposes directory structure and migration plan. Use when adopting docs-toolkit in a repo, when asked to "migrate docs", "standardize documentation", "set up docs-toolkit", or "organize docs".
metadata:
  version: "0.2.0"
---

# Skill: docs-migrate

## Purpose

Full-repo documentation audit and migration. Discovers ALL markdown files, classifies them against plugin schemas, proposes a logical directory structure, and executes the migration per-file.

## Trigger

- User says "migrate docs", "standardize docs", "organize documentation"
- User says "adopt docs-toolkit", "set up docs-toolkit for this project"
- User invokes `/docs-migrate`

## Workflow

### Phase 1: Full Repository Scan

Discover every markdown file in the repository:

```bash
git ls-files '*.md'
```

For EACH file found, read and record:
- Full path
- Has YAML frontmatter (yes/no)
- Frontmatter fields if present
- All H2 headings
- First H1 heading (title signal)
- Filename pattern
- Parent directory name
- File size (proxy for content depth)
- Last git commit date

**Exclude from classification** (non-doc files):
- `README.md` at any level
- `CONTRIBUTING.md`, `CHANGELOG.md`, `LICENSE.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`
- Files not tracked by git (gitignored paths are already excluded by `git ls-files`)
- SKILL.md files (agentskills format, not docs-toolkit)
- CLAUDE.md files

**Do NOT exclude anything else.** Every other `.md` file is a candidate.

### Phase 2: Map to Schemas

Read all schemas from the plugin's `schemas/` directory. For each candidate file, score it against every schema:

**Scoring signals (weighted):**

| Signal | Weight | How to check |
|--------|--------|--------------|
| Directory name matches schema defaults | HIGH | `decisions/` → ADR, `rfcs/` → RFC, `topics/` → Explanation |
| Filename matches schema naming pattern | HIGH | `0001-foo.md` → ADR, `RFC-0001-foo.md` → RFC |
| Has required sections for a schema | MEDIUM | H2 headings match `sections.required` |
| Has frontmatter fields matching a schema | MEDIUM | Fields present match `frontmatter.fields` |
| Content signals | LOW | Keywords, patterns, checkbox items |

**Content signal table:**

| Pattern | Suggests |
|---------|----------|
| "Context and Problem Statement", "Decision Outcome" | ADR |
| "Problem", "Proposal", "Alternatives", "Resolution" | RFC |
| "User Scenarios", "Requirements", "Success Criteria" | Spec |
| "Purpose", "Prerequisites", "Steps", "Rollback", "Escalation" | Runbook |
| Checkbox items `- [ ]`, "Phase", "Dependencies" | Tasks |
| "Timeline", "Root Cause", "Impact", "Remediation" | Learnings (incident) |
| "What Went Well", "What Didn't", "Action Items" | Learnings (retrospective) |
| "Discovery", "Implication" | Learnings (TIL) |
| Explains concepts, "why", "because", "historically", design rationale | Explanation |
| API specs, parameter tables, CLI flags, config shapes, type definitions | Reference |

**If no schema matches (score too low):** classify as `explanation` (default for unstructured knowledge docs) or ask the user.

### Phase 3: Present Inventory

Show the complete inventory as a structured report:

```
## Documentation Inventory

### Already conforming (N files)
  ✓ docs/decisions/0001-use-postgres.md → ADR (valid)

### Classified — needs migration (M files)
  → docs/proposals/new-api.md → RFC (missing frontmatter, wrong directory)
  → docs/procedures/deploy.md → Runbook (missing frontmatter, wrong naming)
  → docs/architecture/auth-flow.md → Explanation (no frontmatter)
  → docs/api/endpoints.md → Reference (no frontmatter)
  → notes/outage-jan.md → Learnings/incident (wrong directory, no frontmatter)

### Unclassified (K files) — need your input
  ? docs/misc/random-notes.md — could be Explanation or Learnings/TIL
  ? old/legacy-design.md — could be ADR or RFC

### Excluded (J files)
  - README.md, CONTRIBUTING.md, etc.
```

Ask user to confirm or override classifications for the "Classified" group and resolve the "Unclassified" group.

### Phase 4: Propose Directory Structure

Based on classifications, propose where docs should live:

```
## Proposed Structure

decisions/          ← ADRs (2 files)
rfcs/               ← RFCs (3 files)
specs/              ← Feature specs (1 file)
runbooks/           ← Operational procedures (2 files)
tasks/              ← Task lists (0 files)
learnings/          ← Incidents, retros, TILs (1 file)
topics/             ← Explanations (4 files)
references/         ← API docs, domain knowledge (3 files)

Config (.docs-toolkit.yml):
  decisions: [decisions]
  rfcs: [rfcs]
  specs: [specs]
  runbooks: [runbooks]
  tasks: [tasks]
  learnings: [learnings]
  explanations: [topics]
  references: [references]
```

Ask user to confirm structure or adjust.

### Phase 5: Generate Migration Plan

For each file that needs migration, produce a concrete action list:

```
## Migration Plan

### docs/proposals/new-api.md → rfcs/RFC-0001-new-api.md
  1. Move: docs/proposals/new-api.md → rfcs/RFC-0001-new-api.md
  2. Add frontmatter: number: 1, title: "New API", status: draft, date: 2025-03-15, authors: [inferred from git]
  3. Add depends_on: [ask user]
  4. Add tracks: [ask user for code paths]
  5. Rename heading "Background" → "Problem"
  6. Add missing sections: "Alternatives", "Resolution" (placeholder)

### docs/architecture/auth-flow.md → topics/authentication-flow.md
  1. Move: docs/architecture/auth-flow.md → topics/authentication-flow.md
  2. Add frontmatter: title: "Authentication Flow", date: 2025-06-01
  3. Add tracks: [ask user for code paths]
  4. No section changes needed (explanations have no required sections)
```

Present FULL plan to user before executing anything.

### Phase 6: Execute

After user approves the plan:

1. Create target directories if they don't exist
2. For each file (one at a time):
   - Apply frontmatter changes
   - Rename headings where mapped
   - Add missing section headings
   - Move/rename file
   - Run `uv run "${CLAUDE_PLUGIN_ROOT}/scripts/validate.py" <file> --format text`
   - Report result
3. Create/update `.docs-toolkit.yml`
4. Run full validation
5. Report summary

## Rules

- **Scan everything.** Don't assume docs only live in known directories. Find ALL markdown files.
- **Never delete content.** Only add, rename, move, or restructure.
- **Never rewrite prose.** Section content stays as-is.
- **Infer from git.** Dates, authors — use `git log` when possible.
- **Full plan before execution.** User sees and approves the entire migration before anything moves.
- **One file at a time during execution.** Validate after each.
- **Naming conventions apply to directories too.** When proposing directory structure, prefer names that match schema defaults (e.g. `decisions/` not `adrs/`, `topics/` not `explanations/`, `references/` not `domain-knowledge/`). Use lowercase kebab-case for all directory names. This isn't script-enforced but produces a cleaner, more predictable project layout.
- **Ask, don't guess.** Ambiguous classification → ask. Missing context → ask.

## Error Handling

- File matches no schema → show content excerpt, ask user to classify or skip
- File matches multiple schemas equally → present options with reasoning, user decides
- Target path already exists → error, user resolves conflict
- Git history unavailable → use file mtime as fallback, warn user
- Validation fails after migration → show errors, fix inline before proceeding
