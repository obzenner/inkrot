# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Generate CLAUDE.md from CLAUDE.md.tmpl using plugin schemas.

Usage:
  uv run scripts/gen_claude_md.py [OPTIONS]

Options:
  --dry-run    Exit 1 if CLAUDE.md is stale
  --help       Show this help
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "docs-toolkit"


def load_doc_schemas() -> list[dict]:
    return [
        schema
        for f in sorted((PLUGIN_ROOT / "schemas").glob("*.json"))
        if (schema := json.loads(f.read_text()))["type"] != "skill"
    ]


def render_doc_types_table(schemas: list[dict]) -> str:
    rows = ["| Type | Naming | Required Sections | Statuses |", "|------|--------|-------------------|----------|"]

    def format_row(s: dict) -> str:
        doc_type = s["type"]
        naming = s["naming"]["description"]
        sections = ", ".join(sec["name"] for sec in s["sections"]["required"])
        if not sections and "subtypes" in s:
            sections = "(subtype-dependent)"
        status_field = next((f for f in s["frontmatter"]["fields"] if f["name"] == "status"), None)
        statuses = ", ".join(sorted(status_field["values"])) if status_field else "N/A"
        return f"| {doc_type} | `{naming}` | {sections} | {statuses} |"

    return "\n".join(rows + [format_row(s) for s in schemas])


def render_default_paths(schemas: list[dict]) -> str:
    def format_entry(s: dict) -> str:
        defaults = ", ".join(f"`{d}`" for d in s["discovery"]["defaults"])
        return f"   - {s['type']}: {defaults}"

    return "\n".join(format_entry(s) for s in schemas)


def render_supported_types(schemas: list[dict]) -> str:
    return ", ".join(s["type"] for s in schemas)


def render_schema_count(schemas: list[dict]) -> str:
    return str(len(schemas))


def render_skills_table(schemas: list[dict]) -> str:
    rows = ["| Skill | Description |", "|-------|-------------|"]

    def resolve_inline(text: str) -> str:
        return text.replace("{{SUPPORTED_TYPES}}", render_supported_types(schemas))

    def parse_tmpl_frontmatter(tmpl_path: Path) -> tuple[str, str] | None:
        content = tmpl_path.read_text()
        match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not match:
            return None
        fm = match.group(1)
        name = ""
        desc = ""
        for line in fm.splitlines():
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("description:"):
                desc = resolve_inline(line.split(":", 1)[1].strip())
        return (name, desc) if name else None

    skills_root = PLUGIN_ROOT / "skills"
    entries = [
        parsed
        for tmpl in sorted(skills_root.glob("*/SKILL.md.tmpl"))
        if (parsed := parse_tmpl_frontmatter(tmpl))
    ]

    return "\n".join(rows + [f"| `{name}` | {desc} |" for name, desc in entries])


RENDERERS: dict[str, callable] = {
    "{{DOC_TYPES_TABLE}}": render_doc_types_table,
    "{{DEFAULT_PATHS}}": render_default_paths,
    "{{SUPPORTED_TYPES}}": render_supported_types,
    "{{SCHEMA_COUNT}}": render_schema_count,
}


def render(tmpl_content: str, schemas: list[dict]) -> str:
    result = tmpl_content
    for placeholder, renderer in RENDERERS.items():
        if placeholder in result:
            result = result.replace(placeholder, renderer(schemas))
    if "{{SKILLS_TABLE}}" in result:
        result = result.replace("{{SKILLS_TABLE}}", render_skills_table(schemas))
    return result


def main():
    if "--help" in sys.argv:
        print(__doc__)
        sys.exit(0)

    dry_run = "--dry-run" in sys.argv
    tmpl_path = REPO_ROOT / "CLAUDE.md.tmpl"
    output_path = REPO_ROOT / "CLAUDE.md"

    if not tmpl_path.exists():
        print(f"Error: {tmpl_path} not found", file=sys.stderr)
        sys.exit(2)

    schemas = load_doc_schemas()
    generated = render(tmpl_path.read_text(), schemas)

    if dry_run:
        current = output_path.read_text() if output_path.exists() else ""
        if current != generated:
            print("CLAUDE.md is stale")
            sys.exit(1)
        sys.exit(0)

    output_path.write_text(generated)
    print(f"  generated: CLAUDE.md")


if __name__ == "__main__":
    main()
