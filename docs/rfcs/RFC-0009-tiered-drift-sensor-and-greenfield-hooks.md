---
number: 9
title: Tiered Conformance Sensor and Greenfield Hook Architecture
status: accepted
date: 2026-06-25
authors:
  - obzenner
depends_on:
  - path: ../rfcs/RFC-0002-staleness-detection.md
    required_status:
      - accepted
  - path: ../rfcs/RFC-0001-hook-driven-adr-validation.md
    required_status:
      - accepted
tracks:
  - path: plugins/docs-toolkit/scripts/validate.py
    last_verified: "2026-06-25"
  - path: plugins/docs-toolkit/scripts/stop_gate.py
    last_verified: "2026-06-25"
  - path: plugins/docs-toolkit/hooks/hooks.json
    last_verified: "2026-06-25"
  - path: plugins/docs-toolkit/schemas/adr.json
    last_verified: "2026-06-25"
---

# RFC-0009: Tiered Conformance Sensor and Greenfield Hook Architecture

> Supersedes the drift model of RFC-0002. RFC-0002's `tracks.stale` rule is kept only as
> the weakest, advisory signal (Tier 0). This RFC replaces "is this doc old?" with "do its
> references still resolve, and did the surface it depends on change?" — and re-architects
> the hook layer around the Claude Code contract that RFC-0001 predates.

## Problem

**The current drift sensor measures *age* and calls it *drift*. That is a Goodhart proxy, and
it fails structurally — not by mis-tuning.**

RFC-0002's `tracks.stale` rule fires when a tracked file's last git-commit date is newer than
the doc's `last_verified` date. Measured on a real 43-ADR repository (reasa) on 2026-06-25:

- **178 `tracks.stale` errors. A semantic audit (each ADR's decision read against its code
  diff) found exactly 1 genuine decision-drift → ~0.6% precision.**
- The 177 false positives have three structural causes, none fixable by a better date compare:
  1. **Bulk-restamp collision.** 157 of 178 traced to one "refresh all docs" commit that
     stamped a single date across the tree; any later touch to a hot file (`api.py`,
     `state.py`) then trips *every* doc tracking it. The signal is "this file is popular,"
     not "this doc drifted."
  2. **Refactor-not-reversal.** A facade extraction (reasa ADR-0030) *moved* code behind
     re-exports. The decisions were untouched; every tracking doc went red. The rule cannot
     tell a rename from a reversal.
  3. **Terminal-status docs flagged forever.** 4 `superseded` ADRs (reasa 0006/0007/0011/
     0012) track files that keep changing, so they are *permanently* "stale" — yet a
     superseded decision is a true historical fact, not a drift. The current `adr.json`
     schema requires `tracks` on every doc with no terminal-state exemption, so this class
     is baked in.

The consequence is the **boy-who-cried-wolf failure**: at 0.6% precision the rational user
response is `sed -i` the date across all docs — which RFC-0002 itself names as the resolution
("Bumping `last_verified` is the 'I've reviewed this' signal"). **A sensor that is cheaper to
silence than to satisfy trains users to defeat it, then protects nothing.**

**Two deeper problems compound it:**

- **Wrong frame for decision records.** The ADR community (Nygard; MADR; adr-tools) treats a
  decision as having an append-only *lifecycle* — `proposed → accepted → deprecated →
  superseded` — never a freshness date. An ADR is never "stale"; it is current, deprecated,
  or superseded. Conflating "old" with "wrong" is a category error.
- **The hook layer predates the platform it targets.** RFC-0001's two hooks (SessionStart,
  Stop) were designed against a 2-event mental model. The current Claude Code hook contract
  exposes ~25 events with per-event blocking asymmetry, a documented Bash-bypass gap, and
  prompt/agent hook types — none of which the current `hooks.json` uses. The gate keys on
  `Edit|Write` and so **misses any doc written via `Bash`** (heredoc, `sed`, `cat >`).

### What the prior art proves (researched, sourced)

| Source | Finding | Implication for us |
|---|---|---|
| **`adrs` CLI** (Rotenberg, v0.7.3; rules source-verified in `mdbook-lint-rulesets`) | `doctor` does **zero** code-drift — it reads only ADR markdown. 17 rules in 3 tiers (Error/Warning/Info) with stable IDs (`ADR001…017`), split into per-document vs collection (graph) families. Errors = corpus structurally broken; warnings = convention; info = style. Ran on reasa: **0 errors.** | The code↔doc quadrant is *empty* across the whole ADR-tooling lineage. That empty quadrant is docs-toolkit's reason to exist — but it must be filled with a *trustworthy* signal, not the 0.6% one. Steal the rule-ID + 3-tier-severity + per-doc/collection split. |
| **Drift-detection SOTA** (doctest/rustdoc; Sphinx nitpicky; Swimm; Panthaplackel JIT benchmark; ROSE co-change, Zimmermann TSE 2005) | **No tool verifies a prose decision is still *true*.** Symbol-reference integrity and public-surface diffing are deterministic and precise; co-change coupling at `conf≥0.9, support≥3` gives **>66% precision, ~3% fire-rate** (rare but trustworthy). LLM semantic checks: zero-shot F1 ~62–69 (worse than a 2021 BiGRU), **P~51/R~99** at the JIT task, and temp-0 is **not reproducible** (vendor-stated; batch-invariance). | Rank signals: symbol-resolution & status-integrity (best) > public-surface diff > co-change > **age (worst)**. Keep the LLM **out of the blocking hook** — async/advisory only. |
| **Hook architectures** (Claude Code hooks reference; pre-commit; lefthook/husky; git hooks) | Per-event blocking asymmetry: `PreToolUse` deny is tamper-proof even under bypass; `PostToolUse` can only flag (tool already ran); `Stop` can re-open a turn but caps at 8 blocks (`stop_hook_active`). **Bash bypasses `Edit\|Write` matchers** — catch completeness with a `Stop`-time `git status --porcelain` scan. Filtering belongs in declarative config, not hook-internal branching. Distribution = enforceability (ship in plugin/committed settings). A documented bypass (`--no-verify`) is a *feature*. | Gate at Pre/Post, verify-before-close at Stop, prime at SessionStart. Two-tier severity matched to *confidence*: deterministic→fail-closed; semantic→fail-open/inform. Push a one-line verdict, pull the detail. |

## Proposal

Replace the age-based drift model with a **tiered conformance sensor** whose iron rule is:
**the blocking hook fires only on signals that are deterministic and specific; everything
probabilistic is advisory.** Re-architect the hooks around the real Claude Code contract.

### Part A — The tiered sensor (replaces `tracks.stale` as the drift mechanism)

**Tier 0 — age, demoted to advisory (was the error gate).**
`tracks.stale` survives only as a **warning**, surfaced on-demand / in a scheduled CI cron —
never in a blocking hook. It is a faint "you may want to look" nudge, not a gate. This alone
removes the 0.6%-precision error wall.

**Tier 1 — symbol-anchored references (the new primary signal, deterministic, fail-closed).**
A doc cites code as a *resolvable anchor*, not a bare path:
`reasa/discovery.py::ProjectLayout.resolve_program` (file `::` dotted-symbol). The sensor
resolves each anchor against the live tree via a language-agnostic AST/`tree-sitter` query.
A **dangling anchor is an error** (symbol renamed/removed). This is rank-1 in the research:
high precision, offline, fast, and — critically — **it stays silent on the refactors that
wrecked the 0.6%** (a moved-but-preserved symbol still resolves). New optional per-track key,
additive (the `tracks` entry shape is already unvalidated/extensible in `validate.py`):

```yaml
tracks:
  - path: reasa/discovery.py
    symbol: ProjectLayout.resolve_program   # NEW: resolvable anchor; dangling → error
    surface: public                         # NEW: gate candidacy on exported signature only
    last_verified: "2026-06-25"             # kept, but Tier-0 advisory only
```

**Tier 1 also — status-lifecycle integrity (the *right* frame for decisions, deterministic).**
Validate the status enum, supersede-link bidirectionality, and no-dangling-supersessor — the
`adrs` collection-family checks. And the policy `adrs` omits: **terminal-status docs
(`superseded`/`deprecated`/`rejected`) are excluded from conformance checks entirely.** A dead
decision cannot drift. This deletes false-positive class (3) by construction.

**Tier 2 — public-surface gate + co-change coupling (deterministic, candidate-narrowing).**
A tracked file becomes a *drift candidate* only when its **exported signature** changed
(a `tree-sitter` projection of public symbols, diffed — internal refactors and reformats are
invisible: kills false-positive class (2)). Optionally augment with a precomputed **co-change
table** (`confidence(code⇒doc) ≥ 0.9 ∧ support ≥ 3`): flag when the code changed, coupling is
high, and the doc did not. Per ROSE this fires ~3% of the time at >66% precision — rare and
trustworthy. The coupling oracle already lives in git history (verified on reasa:
`executor.py` co-commits with `test_executor.py`/`state.py`/`api.py`); precompute offline →
sub-100ms hook lookup.

**Tier 3 — semantic LLM check (advisory, async/CI, never blocking).**
Runs **only on the small candidate set** Tier-1/2 flag, **content-hash-cached** (skip if
neither the doc nor the referenced code-region changed since the last verdict), emits a
structured `{verdict, evidence, confidence}` as a PR comment or `additionalContext` — never a
`decision: block`. Justification is non-negotiable: vendors state temp-0 is not reproducible,
and a non-deterministic verdict at a gate is exactly what teaches `--no-verify`.

**Severity model (stolen from `adrs`, stable rule IDs `DOC001…`):**

| Tier | Signal | Severity | Channel |
|---|---|---|---|
| 1 | Dangling symbol anchor | **Error** (fail-closed) | blocks at Stop / pre-commit |
| 1 | Status-lifecycle malformed (bad enum, dangling supersessor) | **Error** | blocks |
| 1 | Intra-corpus broken link / duplicate number | **Error** | blocks |
| 2 | Public-surface of tracked file changed (candidate) | **Warning** | informs (agent-visible) |
| 2 | Co-change coupling fired | **Warning** | informs |
| 3 | LLM judges decision contradicted | **Info/advisory** | PR comment, async |
| 0 | `last_verified` older than last commit | **Warning** (was Error) | on-demand / cron only |

### Part B — Greenfield hook architecture

Targets the *actual* Claude Code hook contract (researched and enumerated). Principles:

1. **Right event for the job.**
   - `SessionStart` → **prime once** (inject conventions + a one-line health summary via
     `additionalContext`; never block).
   - `PostToolUse` (Edit|Write on `*.md`) → **fast per-file structural feedback** (naming,
     frontmatter, sections) as agent-visible advice. Cannot undo; informs only.
   - `Stop` → **verify-before-close, the completeness gate.** Scan `git status --porcelain`
     for *all* changed docs+code (catches `Bash`-written files the Edit|Write matcher misses),
     run Tier-1 deterministic checks, `decision: block` **only** on Tier-1 errors. **Guard the
     8-block cap**: read `stop_hook_active`, exit 0 if already active so the agent never wedges.
   - **No `Stop` block on Tier-0/2/3** — warnings and semantic findings inform, never gate.

2. **Confidence-matched fail mode.** Deterministic + high-confidence → block (exit 2 / Stop
   `decision: block`). Probabilistic/semantic → inform (`additionalContext`, exit 0). Never a
   probabilistic blocker.

3. **Push a verdict, pull the detail.** One-line `additionalContext`
   (`DOC003: ADR-0042 cites reasa/state.py::State.fold — symbol not found. Run docs-toolkit
   explain 0042 for the diff.`) + `suppressOutput` on noise. Never dump full diffs into context
   every turn — that token/noise tax is what gets hooks disabled.

4. **Idempotent, order-independent, side-effect-isolated.** Hooks run in parallel, dedup, and
   race on `updatedInput`; no shared mutable state, no reliance on a sibling's verdict.

5. **Performance budget.** Sub-second on hot paths; Tier-1 is AST-resolution + table lookup,
   no network. Tier-3 (network, slow, non-deterministic) lives off the hot path by construction.

6. **Distribution = enforceability; bypass is first-class.** Ship the gate in the plugin's
   `hooks/hooks.json` (committed, team-wide). Provide a documented, single, auditable bypass
   and log its use. "Honest by default, overridable on the record" beats "unbypassable, ergo
   globally disabled."

7. **Machine-readable by default.** `--format json` with stable rule IDs + `file:line` +
   severity + tier, so the sensor can feed an agent loop or CI — not the human-text-only output
   `adrs doctor` is limited to.

### Naming (principle: new mechanism, new name)

The mechanism is no longer "staleness." Per the new-concept-new-name discipline, rename the
command surface from a date check to a **conformance check** (working name `docs-toolkit
conform` / rule family `DOCnnn`), so the name describes what it does — verify doc↔code
conformance via resolvable anchors — not the proxy it replaced.

## Alternatives

- **Tune the date heuristic (narrower tracks, ignore-commit lists).** Rejected — the failure
  is structural (age ≠ drift), not a tuning problem. Narrower tracks trade false positives for
  maintenance burden and still can't tell a refactor from a reversal.
- **Go straight to an LLM drift judge.** Rejected — zero-shot F1 ~62–69 (P~51/R~99 = flags
  everything) and temp-0 is non-reproducible; a non-deterministic blocking gate is the fastest
  route to `--no-verify`. The LLM earns its place only async, on a pre-filtered candidate set.
- **Adopt `adrs` wholesale.** Rejected — `adrs doctor` does zero code-drift (its entire value
  is intra-corpus health, which it does well). We steal its severity/rule-ID/graph model and
  *add* the missing conformance family; we don't replace our reason to exist with it.
- **Executable-docs (doctest-style) for ADRs.** Rejected as the primary mechanism — prose
  decisions have no executable region to bind; applicable only to docs that embed runnable
  examples (a future, separate rule).
- **Keep RFC-0001's two-hook design.** Rejected — it predates the platform, keys on
  `Edit|Write` (misses Bash-written docs), and blocks at Stop on a 0.6%-precision signal.

## Resolution

**Slices 1 and 3 implemented** on branch `feat/rfc-0009-conformance-hooks` (2026-06-25).

1. **Slice 1 (precision win) — DONE.** `tracks.stale` demoted error→warning in `validate.py`;
   `terminal_statuses` added to all 6 status-bearing schemas; terminal-status docs
   (`superseded`/`deprecated`/`rejected`/`archived`/`withdrawn`/`abandoned`) skip the age
   check. **Measured on the reasa corpus (79 docs): errors 178 → 39**, and the 39 are real
   `tracks.path-missing` (a tracked file was renamed/deleted) — a high-precision deterministic
   signal, not age noise. All remaining `tracks.stale` are now warnings; the SessionStart
   one-liner went from "178 error(s)" to "39 error(s)". No regression: the 39 `path-missing`
   errors predate this change (they were masked by the stale wall).
2. **Slice 3 (greenfield Stop gate) — DONE, then CORRECTED (0.6.1).** New `stop_gate.py`
   wraps `validate.py --scope changed` (git-detected → catches Bash-written docs the
   `Edit|Write` matcher misses) and guards the 8-block cap via `stop_hook_active`.
   `--scope changed` also filters *per-doc* results so an untouched doc's pre-existing error
   never re-fires.

   **Two corrections came from dogfooding 0.6.0 against a real multi-author tree (a
   collaborator's mid-migration reasa checkout), caught in a clean worktree:**

   - **(a) Terminal docs must skip `path-missing`, not just `stale`.** 0.6.0 exempted
     terminal-status docs from the *age* check but still errored on a dangling path. A
     superseded ADR's code is *supposed* to be gone — that is what superseding means — so a
     dangling reference is expected, not a defect. The same "old ≠ wrong" category error,
     one level deeper. Fix: terminal docs skip BOTH drift checks (`stale` + `path-missing`),
     keep the *authoring* checks (`path-format`, `no-date`) which are timeless. Flag renamed
     `skip_stale` → `skip_drift`.
   - **(b) The Stop gate must INFORM, not BLOCK.** This is the load-bearing reversal of the
     original design. `--scope changed` is `git diff HEAD`, which cannot distinguish *this*
     session's edits from a *collaborator's* uncommitted WIP in a shared tree. A
     `decision: block` on drift the current turn did not author wedges every agent's turn on
     someone else's migration — the over-gate failure this RFC exists to kill, relocated to
     the turn boundary. At Stop the change is **not attributable**, so the gate now fails
     OPEN: surfaces findings as a non-blocking `systemMessage` and lets the turn close. Hard,
     attributable enforcement of doc drift belongs at **commit-time / CI**, not at every turn
     boundary. (Proven side-by-side on the real dirty tree: 0.6.0 emits `block` and wedges the
     turn; 0.6.1 emits an advisory and the turn closes, drift still surfaced.)

   `hooks.json` Stop calls `stop_gate.py`. Plugin 0.5.0 → 0.6.0 → **0.6.1** (the fix is a
   PATCH: a behavior correction, no new surface). Manifest description updated to
   "surfaces drift as a non-blocking advisory at the turn boundary; hard enforcement at CI."
3. **Slice 2 — DEFERRED (open):** symbol-anchored references (`symbol:` track key +
   `tree-sitter` resolver) and the public-surface candidate gate. The `path-missing` check is
   the file-granularity proto-version already landed; symbol-granularity is the next step.
4. **Slice 4 — DEFERRED (open):** co-change precompute (Tier 2) and the async LLM advisory
   (Tier 3).

Each slice is independently shippable and measurable against the reasa corpus — the sensor's
own precision is the acceptance criterion (the refuting observation, designed first: *does the
gate stay silent on a pure refactor / unchanged doc, and fire on a real broken reference?* —
verified by the five tests above). The tool that checks doc↔code conformance is itself
conformance-checked at the layer the requirement lives: its precision on a real corpus, not
its unit tests.
