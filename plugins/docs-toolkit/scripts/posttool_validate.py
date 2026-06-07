# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""PostToolUse hook: validate the single doc just written/edited.

Reads tool_input.file_path from stdin. If it is a known doc type, runs
validate.py on that one file. On errors, feeds a quiet system reminder to
Claude via hookSpecificOutput.additionalContext (not shown to the user).
Valid file or non-doc → emits nothing. Per-file feedback only; cross-file
integrity is gated separately at Stop.
"""

import json
import subprocess
import sys
from pathlib import Path


def main():
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    file_path = payload.get("tool_input", {}).get("file_path", "")
    if not file_path or not file_path.endswith(".md"):
        sys.exit(0)

    if not Path(file_path).is_file():
        sys.exit(0)

    validate_py = Path(__file__).parent / "validate.py"
    result = subprocess.run(
        ["uv", "run", "--script", str(validate_py), file_path, "--format", "text"],
        capture_output=True, text=True,
    )

    # exit 0 → file clean or not a classified doc; nothing to report.
    if result.returncode == 0 or not result.stdout.strip():
        sys.exit(0)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                "docs-toolkit: the doc you just edited has validation errors:\n"
                + result.stdout.strip()
            ),
        }
    }))
    sys.exit(0)


if __name__ == "__main__":
    main()
