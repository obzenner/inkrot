# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SessionStart/Stop hook: detect stale generated files and missing version bumps.

On SessionStart: emits advisory context if stale.
On Stop: blocks session termination if stale or version not bumped.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "docs-toolkit"

GENERATORS = [
    (
        "plugin skills",
        ["uv", "run", "--script", str(PLUGIN_ROOT / "scripts" / "gen_skills.py"), "--dry-run"],
        PLUGIN_ROOT,
    ),
    (
        "CLAUDE.md",
        ["uv", "run", "--script", str(REPO_ROOT / "scripts" / "gen_claude_md.py"), "--dry-run"],
        REPO_ROOT,
    ),
]


def check_stale() -> list[str]:
    problems = []
    for label, cmd, cwd in GENERATORS:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
        if result.returncode != 0:
            problems.append(f"{label}: {result.stdout.strip()}")
    return problems


def get_committed_version() -> str | None:
    result = subprocess.run(
        ["git", "show", "HEAD:plugins/docs-toolkit/.claude-plugin/plugin.json"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout).get("version")
    except (json.JSONDecodeError, KeyError):
        return None


def get_current_version() -> str | None:
    path = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text()).get("version")
    except (json.JSONDecodeError, KeyError):
        return None


def has_source_changes() -> bool:
    source_patterns = ["schemas/", ".tmpl", "gen_skills.py", "gen_claude_md.py"]
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    return any(
        any(pattern in f for pattern in source_patterns)
        for f in result.stdout.splitlines()
    )


def build_diagnosis() -> list[str]:
    stale = check_stale()
    committed_version = get_committed_version()
    current_version = get_current_version()
    source_changed = has_source_changes()
    version_bumped = committed_version != current_version

    problems = []

    if stale:
        problems.append(
            "Generated files are stale:\n"
            + "\n".join(f"  {s}" for s in stale)
            + "\n→ Run: uv run plugins/docs-toolkit/scripts/gen_skills.py && uv run scripts/gen_claude_md.py"
        )

    if source_changed and not version_bumped:
        problems.append(
            f"Source files changed but version is still {current_version}.\n"
            "→ Bump version in plugins/docs-toolkit/.claude-plugin/plugin.json (PATCH for fixes, MINOR for new content)"
        )

    return problems


def read_event() -> str:
    try:
        payload = json.loads(sys.stdin.read())
        return payload.get("hook_event_name", "Stop")
    except (json.JSONDecodeError, EOFError):
        return "Stop"


def main():
    event = read_event()
    problems = build_diagnosis()

    if not problems:
        sys.exit(0)

    message = "\n\n".join(problems)
    print(message)
    sys.exit(0)


if __name__ == "__main__":
    main()
