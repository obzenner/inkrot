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
    return [
        schema
        for f in sorted(schema_dir.glob("*.json"))
        if (schema := json.loads(f.read_text()))["type"] != "skill"
    ]


def load_skill_schema(schema_dir: Path) -> dict:
    return json.loads((schema_dir / "skill.json").read_text())


# --- Placeholder renderers ---


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
    def format_type_defaults(s: dict) -> str:
        defaults = ", ".join(f"`{d}`" for d in s["discovery"]["defaults"])
        return f"   - {s['type']}: {defaults}"

    return "\n".join(format_type_defaults(s) for s in schemas)


def render_supported_types(schemas: list[dict]) -> str:
    return ", ".join(s["type"] for s in schemas)


def render_status_transitions(schemas: list[dict]) -> str:
    rows = ["| Type | Valid Statuses |", "|------|---------------|"]

    def format_row(s: dict) -> str | None:
        status_field = next((f for f in s["frontmatter"]["fields"] if f["name"] == "status"), None)
        if not status_field:
            return None
        statuses = ", ".join(sorted(status_field["values"]))
        return f"| {s['type'].title()} | {statuses} |"

    return "\n".join(rows + [row for s in schemas if (row := format_row(s))])


def render_classification_table(schemas: list[dict]) -> str:
    Signal = tuple[str, str]

    def signals_from_sections(s: dict) -> list[Signal]:
        required = s["sections"]["required"]
        if not required:
            return []
        section_names = ", ".join(f'"{sec["name"]}"' for sec in required)
        return [(section_names, s["type"].title())]

    def signals_from_subtypes(s: dict) -> list[Signal]:
        if "subtypes" not in s:
            return []
        return [
            (
                ", ".join(f'"{sec["name"]}"' for sec in info["required_sections"]),
                f"{s['type'].title()} ({subtype})",
            )
            for subtype, info in s["subtypes"]["values"].items()
        ]

    all_signals: list[Signal] = [
        signal
        for s in schemas
        for signal in signals_from_sections(s) + signals_from_subtypes(s)
    ]

    rows = ["| Pattern | Suggests |", "|---------|----------|"]
    return "\n".join(rows + [f"| {pattern} | {suggests} |" for pattern, suggests in all_signals])


def render_discovery_defaults(schemas: list[dict]) -> str:
    def format_entry(s: dict) -> str:
        dirs = ", ".join(f"`{d}/`" for d in s["discovery"]["defaults"])
        return f"- **{s['type']}**: {dirs}"

    return "\n".join(format_entry(s) for s in schemas)


# --- Template rendering ---


PLACEHOLDER_REGISTRY: dict[str, callable] = {
    "{{DOC_TYPES_TABLE}}": render_doc_types_table,
    "{{DEFAULT_PATHS}}": render_default_paths,
    "{{SUPPORTED_TYPES}}": render_supported_types,
    "{{STATUS_TRANSITIONS}}": render_status_transitions,
    "{{CLASSIFICATION_TABLE}}": render_classification_table,
    "{{DISCOVERY_DEFAULTS}}": render_discovery_defaults,
}


def render_template(tmpl_content: str, schemas: list[dict], version: str) -> str:
    result = tmpl_content.replace("{{VERSION}}", version)
    for placeholder, renderer in PLACEHOLDER_REGISTRY.items():
        if placeholder in result:
            result = result.replace(placeholder, renderer(schemas))
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


# --- Skill discovery ---


def discover_skill_templates(skills_root: Path) -> list[Path]:
    return sorted(skills_root.glob("*/SKILL.md.tmpl"))


# --- Main ---


def main():
    dry_run = "--dry-run" in sys.argv
    if "--help" in sys.argv:
        print(__doc__)
        sys.exit(0)

    plugin_root = find_plugin_root()
    schema_dir = plugin_root / "schemas"
    skills_root = plugin_root / "skills"

    if not schema_dir.is_dir():
        print(f"Error: Schema directory not found: {schema_dir}", file=sys.stderr)
        sys.exit(2)

    doc_schemas = load_doc_schemas(schema_dir)
    templates = discover_skill_templates(skills_root)

    if not templates:
        print("Error: No SKILL.md.tmpl files found", file=sys.stderr)
        sys.exit(2)

    all_outputs: dict[Path, str] = {}

    for tmpl_path in templates:
        skill_dir = tmpl_path.parent
        skill_md_path = skill_dir / "SKILL.md"
        current_version = read_current_version(skill_md_path)
        tmpl_content = tmpl_path.read_text()
        all_outputs[skill_md_path] = render_template(tmpl_content, doc_schemas, current_version)

    # Asset templates only for create-document
    create_doc_dir = skills_root / "create-document"
    assets_dir = create_doc_dir / "assets"
    for schema in doc_schemas:
        all_outputs[assets_dir / f"{schema['type']}-template.md"] = generate_asset_template(schema)

    if dry_run:
        stale = [
            str(path.relative_to(plugin_root))
            for path, expected in all_outputs.items()
            if (path.read_text() if path.exists() else "") != expected
        ]
        if stale:
            print(f"Stale files ({len(stale)}):")
            for s in stale:
                print(f"  {s}")
            sys.exit(1)
        print("All generated files are fresh.")
        sys.exit(0)

    assets_dir.mkdir(parents=True, exist_ok=True)
    for path, content in all_outputs.items():
        path.write_text(content)
        print(f"  generated: {path.relative_to(plugin_root)}")


if __name__ == "__main__":
    main()
