# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""PreToolUse hook: block writes to generated files.

Reads tool_input from stdin, checks if file_path targets a generated file.
If so, outputs a deny decision pointing to the regeneration command.
"""

import json
import sys
from pathlib import Path

GENERATED_FILES = {
    "skills/create-document/SKILL.md",
    "skills/create-document/assets/adr-template.md",
    "skills/create-document/assets/rfc-template.md",
    "skills/create-document/assets/spec-template.md",
    "skills/create-document/assets/runbook-template.md",
    "skills/create-document/assets/tasks-template.md",
    "skills/create-document/assets/learnings-template.md",
}


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

    if relative in GENERATED_FILES:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"'{relative}' is generated from schemas. "
                    "Edit schemas/ and run `uv run scripts/gen_skills.py` to regenerate."
                ),
            }
        }
        print(json.dumps(output))

    sys.exit(0)


if __name__ == "__main__":
    main()
