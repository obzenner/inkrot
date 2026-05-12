# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Generate SKILL.md and asset templates from JSON schemas.

Usage:
  uv run gen_skills.py [OPTIONS]

Options:
  --dry-run    Generate to memory, exit 1 if different from committed files
  --help       Show this help

Exit codes:
  0  All generated files are fresh (or successfully written)
  1  Stale files detected (--dry-run mode)
  2  Invocation error

Examples:
  uv run gen_skills.py
  uv run gen_skills.py --dry-run
"""

import json
import sys
from pathlib import Path


# --- Path resolution ---


def find_plugin_root() -> Path:
    current = Path(__file__).parent.parent
    if (current / ".claude-plugin").is_dir():
        return current
    return Path.cwd() / "plugins" / "docs-toolkit"


def load_doc_schemas(schema_dir: Path) -> list[dict]:
    schemas = []
    for f in sorted(schema_dir.glob("*.json")):
        schema = json.loads(f.read_text())
        if schema["type"] != "skill":
            schemas.append(schema)
    return schemas


def load_skill_schema(schema_dir: Path) -> dict:
    path = schema_dir / "skill.json"
    return json.loads(path.read_text())


# --- Template rendering ---


def render_doc_types_table(schemas: list[dict]) -> str:
    rows = ["| Type | Naming | Required Sections | Statuses |", "|------|--------|-------------------|----------|"]
    for s in schemas:
        doc_type = s["type"]
        naming = s["naming"]["description"]
        sections = ", ".join(sec["name"] for sec in s["sections"]["required"])
        if not sections and "subtypes" in s:
            sections = "(subtype-dependent)"
        status_field = next((f for f in s["frontmatter"]["fields"] if f["name"] == "status"), None)
        statuses = ", ".join(sorted(status_field["values"])) if status_field else "N/A"
        rows.append(f"| {doc_type} | `{naming}` | {sections} | {statuses} |")
    return "\n".join(rows)


def render_default_paths(schemas: list[dict]) -> str:
    lines = []
    for s in schemas:
        doc_type = s["type"]
        defaults = ", ".join(f"`{d}`" for d in s["discovery"]["defaults"])
        lines.append(f"   - {doc_type}: {defaults}")
    return "\n".join(lines)


def render_supported_types(schemas: list[dict]) -> str:
    return ", ".join(s["type"] for s in schemas)


def render_skill_md(tmpl_content: str, schemas: list[dict], version: str) -> str:
    replacements = {
        "{{DOC_TYPES_TABLE}}": render_doc_types_table(schemas),
        "{{DEFAULT_PATHS}}": render_default_paths(schemas),
        "{{SUPPORTED_TYPES}}": render_supported_types(schemas),
        "{{VERSION}}": version,
    }
    result = tmpl_content
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)
    return result


# --- Asset template generation ---


def render_frontmatter_field(field: dict, schema: dict) -> list[str]:
    name = field["name"]
    placeholder = field.get("placeholder")

    match field["type"]:
        case "tracks":
            tracks_ph = schema["template"].get("tracks_placeholder", "{{TRACKS_PATH}}")
            return ["tracks:", f"  - path: {tracks_ph}", f"    last_verified: \"{{{{DATE}}}}\""]
        case "enum" if name == "status":
            return [f"{name}: {schema['template']['initial_status']}"]
        case "array" if placeholder:
            return [f"{name}:", f"  - {placeholder}"]
        case "array":
            return [f"{name}:"]
        case _ if placeholder:
            return [f"{name}: {placeholder}"]
        case _:
            return [f"{name}:"]


def render_section(section: dict) -> list[str]:
    return [f"## {section['name']}", "", section["description"], ""]


def generate_asset_template(schema: dict) -> str:
    frontmatter_lines = [
        line
        for field in schema["frontmatter"]["fields"]
        for line in render_frontmatter_field(field, schema)
    ]

    section_lines = [
        line
        for section in schema["sections"]["required"]
        for line in render_section(section)
    ] + [
        line
        for section in schema["sections"].get("recommended", [])
        for line in render_section(section)
    ]

    subtype_note = (
        ["<!-- Sections depend on subtype. See schema for required sections per subtype. -->", ""]
        if "subtypes" in schema else []
    )

    parts = [
        ["---"],
        frontmatter_lines,
        ["---", ""],
        [schema["template"]["heading"], ""],
        section_lines,
        subtype_note,
    ]

    return "\n".join(line for part in parts for line in part)


# --- Version detection ---


def read_current_version(skill_md_path: Path) -> str:
    if not skill_md_path.exists():
        return "0.1.0"
    content = skill_md_path.read_text()
    for line in content.splitlines():
        if "version:" in line and "{{" not in line:
            return line.split("version:")[1].strip().strip('"').strip("'")
    return "0.1.0"


# --- Main ---


def main():
    dry_run = "--dry-run" in sys.argv
    if "--help" in sys.argv:
        print(__doc__)
        sys.exit(0)

    plugin_root = find_plugin_root()
    schema_dir = plugin_root / "schemas"
    skills_dir = plugin_root / "skills" / "create-document"
    assets_dir = skills_dir / "assets"

    if not schema_dir.is_dir():
        print(f"Error: Schema directory not found: {schema_dir}", file=sys.stderr)
        sys.exit(2)

    doc_schemas = load_doc_schemas(schema_dir)
    tmpl_path = skills_dir / "SKILL.md.tmpl"

    if not tmpl_path.exists():
        print(f"Error: Template not found: {tmpl_path}", file=sys.stderr)
        sys.exit(2)

    tmpl_content = tmpl_path.read_text()
    skill_md_path = skills_dir / "SKILL.md"
    current_version = read_current_version(skill_md_path)

    generated_skill = render_skill_md(tmpl_content, doc_schemas, current_version)

    generated_assets = {
        f"{schema['type']}-template.md": generate_asset_template(schema)
        for schema in doc_schemas
    }

    all_outputs = {skill_md_path: generated_skill}
    for filename, content in generated_assets.items():
        all_outputs[assets_dir / filename] = content

    if dry_run:
        stale = []
        for path, expected in all_outputs.items():
            current = path.read_text() if path.exists() else ""
            if current != expected:
                stale.append(str(path.relative_to(plugin_root)))
        if stale:
            print(f"Stale files ({len(stale)}):")
            for s in stale:
                print(f"  {s}")
            sys.exit(1)
        sys.exit(0)

    assets_dir.mkdir(parents=True, exist_ok=True)
    for path, content in all_outputs.items():
        path.write_text(content)
        print(f"  generated: {path.relative_to(plugin_root)}")


if __name__ == "__main__":
    main()
