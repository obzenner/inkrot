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
    # Full deterministic check, scoped to docs changed this session (git-based → catches
    # Bash-written files). `--format hook` emits a `decision: block` + reason ONLY on errors;
    # it is silent on warnings-only and on a clean tree.
    result = subprocess.run(
        ["uv", "run", "--script", str(validate_py),
         "--format", "hook", "--scope", "changed"],
        capture_output=True, text=True,
    )

    # validate.py --format hook prints the block-JSON on stdout (or nothing). Pass it
    # through verbatim; swallow any stderr/diagnostics so a tooling hiccup never blocks.
    out = result.stdout.strip()
    if out:
        print(out)
    sys.exit(0)


if __name__ == "__main__":
    main()
