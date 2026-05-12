# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""PreToolUse hook: block writes to generated files.

Reads tool_input from stdin, checks if file_path targets a generated file.
If so, outputs a deny decision pointing to the regeneration command.
"""

import json
import re
import sys
from pathlib import Path

GENERATED_PATTERNS = [
    re.compile(r"^skills/[^/]+/SKILL\.md$"),
    re.compile(r"^skills/create-document/assets/[a-z]+-template\.md$"),
    re.compile(r"^CLAUDE\.md$"),
]


def is_generated(relative: str) -> bool:
    return any(pattern.match(relative) for pattern in GENERATED_PATTERNS)


def main():
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    file_path = payload.get("tool_input", {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    path = Path(file_path)
    plugin_marker = "plugins/docs-toolkit/"
    if plugin_marker not in str(path):
        sys.exit(0)

    relative = str(path).split(plugin_marker, 1)[1] if plugin_marker in str(path) else ""

    if is_generated(relative):
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"'{relative}' is generated from schemas. "
                    "Edit the .tmpl file or schemas/ and run `uv run scripts/gen_skills.py` to regenerate."
                ),
            }
        }
        print(json.dumps(output))

    sys.exit(0)


if __name__ == "__main__":
    main()
