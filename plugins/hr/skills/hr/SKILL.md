---
name: hr
description: >
  Generate a professional competency profile for a task — the kind internal HR
  uses to staff a role. Produces title, level, technical skills, domain knowledge,
  tools, judgment markers, and anti-patterns. Use when configuring a subagent
  persona, adopting expertise for a task, or when asked "what kind of engineer
  does this need", "build me a profile", "who would I hire for this", "staff
  this", or any variation of role/skill matching to a task description.
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

## Calibration

- **Level is about judgment, not years.** Staff ≠ Senior + 3 years. Staff designs the system others implement. If the task doesn't need that, don't spec it.
- **The profile serves the task.** Minimum viable expert for THIS work. Not a dream hire.
- **Specialization over breadth.** "Full-stack engineer" usually means the task is under-specified. Push back, or produce two profiles.
- **Multiple roles are fine.** If the task genuinely needs different expertise, produce separate profiles. Label which aspect each covers.
- **Some tasks don't need a profile.** If it's a well-defined implementation task any mid-level engineer handles: say so in one line with the key requirement.
