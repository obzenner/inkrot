# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Stop hook: the verify-before-close completeness gate (RFC-0009, greenfield hooks).

Why a Stop gate at all, and why a wrapper around validate.py:

  - **Catches Bash-written docs.** PostToolUse fires only on Edit|Write, so a doc written
    via `cat >`, `sed`, or a heredoc escapes per-edit validation. validate.py `--scope
    changed` detects changes via git (`diff HEAD` + untracked), so it sees every changed
    doc regardless of HOW it was written — closing the Bash bypass the Edit|Write matcher
    has.
  - **Blocks only on DETERMINISTIC errors (fail-closed where confidence is high).** The
    gate runs the full per-doc check on changed docs and blocks the turn only if validate.py
    reports errors (missing tracked path, malformed frontmatter, broken intra-corpus link).
    `tracks.stale` is a WARNING now (RFC-0009) — age is a proxy, not drift — so it never
    blocks; it informs via the pull channel.
  - **Guards the 8-block cap.** Claude overrides a Stop hook after 8 consecutive blocks
    without progress. If `stop_hook_active` is already set, this gate exits 0 immediately so
    it can never wedge the agent in a block loop — the agent has already been told; nagging
    further is worse than letting it stop.

This is a thin adapter: validate.py stays a pure sensor (no hook-stdin coupling), and the
hook channels (session/posttool/stop) each get their own small wrapper that shapes the
sensor's output for that channel."""

import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        payload = {}

    # 8-block-cap guard: if the Stop hook is already active (we blocked on a prior turn and
    # the agent kept working), do not block again — exit silent so we never wedge the loop.
    if payload.get("stop_hook_active"):
        sys.exit(0)

    validate_py = Path(__file__).parent / "validate.py"
    # Full deterministic check, scoped to docs changed vs HEAD (git-based → catches
    # Bash-written files too). `--format text` gives the human-readable error list; we shape
    # it into a NON-BLOCKING advisory below.
    result = subprocess.run(
        ["uv", "run", "--script", str(validate_py),
         "--format", "text", "--scope", "changed", "--require-activation"],
        capture_output=True, text=True,
    )

    # The Stop gate INFORMS — it does NOT block. Why not `decision: block`:
    # `--scope changed` is `git diff HEAD`, which cannot distinguish THIS session's edits from
    # a COLLABORATOR's uncommitted work-in-progress in a shared tree. A hard block on drift the
    # current turn did not author wedges every agent's turn on someone else's migration — the
    # over-gate failure this plugin exists to avoid, relocated to the turn boundary. At Stop,
    # the change is not attributable, so we fail OPEN: surface the findings as a non-blocking
    # `systemMessage` (the agent and user see it and can act) and let the turn close. Hard,
    # attributable enforcement of doc drift belongs at commit time or in CI — not at every
    # turn boundary. (`reset --hard` of this stance would be wrong; see RFC-0009 §Resolution.)
    if result.returncode == 1 and result.stdout.strip():
        print(json.dumps({
            "systemMessage": "docs-toolkit (advisory — not blocking): documentation drift "
                             "in changed docs. Resolve before commit, or supersede the doc:\n"
                             + result.stdout.strip()
        }))
    sys.exit(0)


if __name__ == "__main__":
    main()
