---
name: hr
description: >
  Generate a professional competency profile for a task — the kind internal HR
  uses to staff a role. Produces title, level, technical skills, domain knowledge,
  tools, judgment markers, and anti-patterns. Optionally generates a Claude Code
  agent definition file (.md) from the profile. Use when configuring a subagent
  persona, adopting expertise for a task, or when asked "what kind of engineer
  does this need", "build me a profile", "who would I hire for this", "staff
  this", "create an agent for this", "staff an agent", or any variation of
  role/skill matching to a task description.
---

# HR

Given a task, produce the professional profile of the person who should do it.

## Process

### 1. Analyze the task

Read the task. Identify domain, scope, seniority signals, stack signals, and what goes wrong when the wrong person does this (failure modes reveal which skills are load-bearing).

If the task is ambiguous, ask ONE clarifying question. Don't guess.

### 2. Research current market

Training data is stale. Before building the profile, verify against live sources.

Search for 2-3 queries relevant to the identified role and domain:
- Current job postings at the identified level (what are companies actually hiring for right now?)
- Recent tooling shifts (has anything been deprecated, superseded, or become standard since your training data?)
- Seniority calibration (what level are companies staffing this kind of work at?)

Example queries:
- `"staff data engineer" spark modeling 2025`
- `dbt core vs dbt cloud migration 2025`
- `"senior platform engineer" kubernetes hiring`

If search is unavailable, proceed but mark the output: `⚠️ Based on training data only — not verified against current market.`

### 3. Produce the profile

Output a structured role profile covering these sections:

**Role header** — Title, level (Junior/Mid/Senior/Staff/Principal), specialization (1-2 word focus).

**Technical skills** — Ordered by relevance. Each entry is a concrete, assessable competency with what "good" looks like at this level. "Spark" is insufficient. "Spark: partition-aware joins, broadcast hints, AQE tuning, Delta Lake merge semantics" is a skill entry.

**Domain knowledge** — What they know about the problem space independent of tooling. Business logic, regulatory constraints, data semantics, architectural patterns.

**Tools & technologies** — Specific tools with how they use them, not just that they know them. Version-aware where it matters.

**Judgment markers** — The decisions this person makes correctly that a less experienced person gets wrong. Format: `[Situation] → [What they'd do and why]`. This is the highest-value section. "Knows when to denormalize" > "Understands normalization theory."

**Code review focus** — What they flag, what they let slide, their quality bar.

**Anti-patterns** — What this person does NOT do. Mistakes characteristic of someone less qualified, or over-engineering traps of someone misapplied.

### 4. Validate

Before delivering:

- Every technical skill is assessable (could you write an interview question for it?)
- Judgment markers describe decisions, not knowledge
- Anti-patterns are specific to THIS task, not generic advice
- Level matches task scope — don't over-spec
- Tools listed are ones actually needed, not a résumé dump

### 5. Generate agent definition (conditional)

This step runs ONLY when the user explicitly requests an agent. Triggers: "create an agent", "staff an agent", "generate agent definition", "make me an agent for this", "agent md", or similar.

If the user only asked for a profile (e.g., "staff this", "who would I hire"), stop after step 4.

When triggered, produce a Claude Code agent definition file from the validated profile.

#### Look up the agent definition format

Before generating, read the current Claude Code subagents documentation to get the correct file format, available frontmatter fields, and valid tool names. Use context7 MCP (`resolve-library-id` → `query-docs` for "claude code") or fetch `https://docs.anthropic.com/en/docs/claude-code/sub-agents` directly.

Do NOT rely on training data for the format. The documentation is the SSOT — field names, allowed values, and conventions may have changed.

Also read 1-2 existing agent definitions from the user's environment (`~/.claude/agents/` or `.claude/agents/`) as calibration examples for tone and density.

#### Mapping profile → agent definition

| Profile section | Maps to |
|---|---|
| Role header (title + specialization) | `name` field (kebab-cased) and first line of system prompt |
| Role header (level) | `model` selection — higher level → more capable model |
| Technical skills + Domain knowledge | "Core Competencies" section in system prompt |
| Tools & technologies | `tools` frontmatter field — use minimal set based on what the role actually needs to do |
| Judgment markers | "Decision Framework" section in system prompt — the highest-value section |
| Code review focus | "Quality Standards" section in system prompt |
| Anti-patterns | "Constraints" section in system prompt — what this agent must NOT do |

Principle: grant the minimum tool set. A reviewer doesn't need `Edit`. A researcher doesn't need `Bash`.

#### System prompt structure

Write the system prompt body in this order:

1. **Identity** (1 sentence) — Who this agent is, at what level, with what specialization.
2. **Core Competencies** (bullet list) — Derived from Technical skills and Domain knowledge. Each entry is concrete and assessable, not vague.
3. **Decision Framework** (situation → action pairs) — Directly from Judgment markers. This is what makes the agent good — encode the decisions a senior person makes correctly.
4. **Quality Standards** — From Code review focus. What this agent holds the line on.
5. **Constraints** — From Anti-patterns. Explicit "do NOT" rules derived from what a less qualified person gets wrong.
6. **Process** (optional) — If the role has a natural workflow (e.g., "read tests first, then review implementation"), encode it as numbered steps.

#### System prompt rules

- No filler, no preamble, no "I'm here to help" language.
- Judgment markers become imperative instructions: `[Situation] → [What they'd do]` becomes `"When [situation], [do action] because [reason]."`
- Anti-patterns become constraints: `"Does X wrong"` becomes `"Never X. Instead, Y."`
- Keep it under 80 lines. An agent with a 200-line prompt has lost focus.
- No meta-commentary about being an agent or AI. Just encode the expertise.

#### Output

Present the agent definition inside a fenced code block. State where to save it:
- Project scope: `.claude/agents/<name>.md`
- User scope: `~/.claude/agents/<name>.md`

Default recommendation: project scope unless the user indicates it should be available everywhere.

## Calibration

- **Level is about judgment, not years.** Staff ≠ Senior + 3 years. Staff designs the system others implement. If the task doesn't need that, don't spec it.
- **The profile serves the task.** Minimum viable expert for THIS work. Not a dream hire.
- **Specialization over breadth.** "Full-stack engineer" usually means the task is under-specified. Push back, or produce two profiles.
- **Multiple roles are fine.** If the task genuinely needs different expertise, produce separate profiles. Label which aspect each covers.
- **Some tasks don't need a profile.** If it's a well-defined implementation task any mid-level engineer handles: say so in one line with the key requirement.
- **Agent definitions are opinionated.** Don't hedge with "you might want to..." — make a concrete choice. The user can edit later.
