# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""PreToolUse hook: block writes to generated CLAUDE.md at repo root."""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PROTECTED = REPO_ROOT / "CLAUDE.md"


def main():
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    file_path = payload.get("tool_input", {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    if Path(file_path).resolve() == PROTECTED.resolve():
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "CLAUDE.md is generated. Edit CLAUDE.md.tmpl and run "
                    "`uv run scripts/gen_claude_md.py` to regenerate."
                ),
            }
        }
        print(json.dumps(output))

    sys.exit(0)


if __name__ == "__main__":
    main()
