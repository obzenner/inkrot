# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "strictyaml>=1.7.3",
# ]
# ///
"""Validate engineering documentation against JSON schemas.

Usage:
  uv run validate.py [OPTIONS] [PATH...]

Options:
  --format json|text|hook|session  Output format (default: json)
                           hook:    Stop-gate JSON — block+reason on errors, silent otherwise
                           session: SessionStart JSON — one-line additionalContext, errors only
  --type TYPE|all          Filter to document type (default: all)
  --scope all|changed      Limit to docs changed vs HEAD + untracked (default: all)
  --checks all|cross-file  Which checks to run (default: all)
                           cross-file: only duplicate-number + dependency-cycle/status gates
  --help                   Show this help

Arguments:
  PATH    Files or directories to validate. If omitted, scans cwd for
          tracked doc directories via .docs-toolkit.yml or defaults.

Exit codes:
  0  All documents valid
  1  Validation errors found
  2  Invocation error

Examples:
  uv run validate.py
  uv run validate.py plugins/docs-toolkit/docs/decisions/
  uv run validate.py --type spec --format text
"""

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import strictyaml

# --- Types ---

from typing import TypeAlias

Violation: TypeAlias = dict[str, str]
FileResult: TypeAlias = dict[str, str | list[Violation]]

# --- Schema loading ---

CONFIG_FILENAME = ".docs-toolkit.yml"


def find_schema_dir() -> Path:
    candidates = [
        Path(__file__).parent.parent / "schemas",
        Path.cwd() / "plugins" / "docs-toolkit" / "schemas",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return candidates[0]


GENERATOR_SCHEMAS = frozenset({"skill"})


def load_schemas(schema_dir: Path) -> dict:
    schemas = {}
    for f in sorted(schema_dir.glob("*.json")):
        schema = json.loads(f.read_text())
        if schema["type"] not in GENERATOR_SCHEMAS:
            schemas[schema["type"]] = schema
    return schemas


# --- Parsing ---


def parse_frontmatter(content: str) -> tuple[dict | None, str | None]:
    if not content.startswith("---"):
        return None, "File must start with YAML frontmatter (---)"

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None, "Frontmatter not properly closed with ---"

    try:
        parsed = strictyaml.load(parts[1])
        return parsed.data if isinstance(parsed.data, dict) else {}, None
    except strictyaml.YAMLError as e:
        return None, f"Invalid YAML in frontmatter: {e}"


def extract_h2_headings(content: str) -> list[str]:
    return [
        line[3:].strip()
        for line in content.splitlines()
        if line.startswith("## ")
    ]


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return start


def last_commit_date(path: str, repo_root: Path) -> str | None:
    result = subprocess.run(
        ["git", "log", "-1", "--format=%ad", "--date=short", "--", path],
        capture_output=True, text=True, cwd=repo_root,
    )
    return result.stdout.strip() or None


def git_changed_docs(repo_root: Path) -> set[Path]:
    """Resolved paths of docs changed this session: modified/staged vs HEAD, plus untracked."""
    def run(args: list[str]) -> list[str]:
        result = subprocess.run(
            ["git", *args], capture_output=True, text=True, cwd=repo_root,
        )
        return result.stdout.splitlines() if result.returncode == 0 else []

    rels = [
        *run(["diff", "--name-only", "HEAD"]),
        *run(["ls-files", "--others", "--exclude-standard"]),
    ]
    return {(repo_root / r).resolve() for r in rels if r.strip()}


# --- Field type validators ---


def validate_field(name: str, value, field_def: dict) -> list[Violation]:
    field_type = field_def["type"]

    match field_type:
        case "string":
            if not value or not isinstance(value, str) or not str(value).strip():
                return [{"rule": f"frontmatter.field.{name}", "severity": "error",
                         "message": f"Field '{name}' must be a non-empty string"}]
        case "integer":
            try:
                int(value)
            except (ValueError, TypeError):
                return [{"rule": f"frontmatter.field.{name}", "severity": "error",
                         "message": f"Field '{name}' must be an integer, got: {value}"}]
        case "date":
            try:
                date.fromisoformat(str(value))
            except ValueError:
                return [{"rule": f"frontmatter.field.{name}", "severity": "error",
                         "message": f"Field '{name}' value '{value}' is not valid YYYY-MM-DD"}]
        case "enum":
            allowed = field_def.get("values", [])
            if str(value).lower() not in [v.lower() for v in allowed]:
                return [{"rule": f"frontmatter.field.{name}", "severity": "critical",
                         "message": f"Invalid {name} \"{value}\" — must be one of: {', '.join(sorted(allowed))}"}]
        case "array":
            pass
        case "tracks":
            pass

    return []


# --- Checks (schema-driven) ---


def check_naming(path: Path, schema: dict) -> list[Violation]:
    pattern = re.compile(schema["naming"]["pattern"])
    if not pattern.match(path.name):
        return [{"rule": "naming.pattern", "severity": "critical",
                 "message": f"Filename '{path.name}' must match {schema['naming']['description']}"}]
    return []


def check_frontmatter_fields(meta: dict, schema: dict) -> list[Violation]:
    violations = []
    fields = schema["frontmatter"]["fields"]
    known_fields = {f["name"] for f in fields}

    required_fields = [f for f in fields if f["required"]]
    missing = [f["name"] for f in required_fields if f["name"] not in meta]
    if missing:
        violations.append({"rule": "frontmatter.required", "severity": "critical",
                           "message": f"Missing required fields: {', '.join(missing)}"})

    unknown = [k for k in meta if k not in known_fields]
    if unknown:
        violations.append({"rule": "frontmatter.unknown", "severity": "error",
                           "message": f"Unknown frontmatter fields: {', '.join(unknown)}. Remove or check schema."})

    for field_def in fields:
        name = field_def["name"]
        if name in meta and name not in missing:
            violations.extend(validate_field(name, meta[name], field_def))

    return violations


def check_numbering(meta: dict, path: Path, schema: dict) -> list[Violation]:
    numbering = schema.get("numbering", {})
    if not numbering.get("enabled"):
        return []

    field_name = numbering["field"]
    group_idx = numbering["filename_group"]
    number = meta.get(field_name)
    if number is None:
        return []

    pattern = re.compile(schema["naming"]["pattern"])
    match = pattern.match(path.name)
    if not match:
        return []

    file_number = int(match.group(group_idx))
    try:
        meta_number = int(number)
    except (ValueError, TypeError):
        return [{"rule": "frontmatter.number-match", "severity": "error",
                 "message": f"Field '{field_name}' must be an integer, got: {number}"}]

    if meta_number != file_number:
        return [{"rule": "frontmatter.number-match", "severity": "error",
                 "message": f"Frontmatter {field_name} ({meta_number}) does not match filename prefix ({file_number})"}]
    return []


def check_sections(headings: list[str], schema: dict) -> list[Violation]:
    violations = []

    required = schema.get("sections", {}).get("required", [])
    missing_required = [s["name"] for s in required if s["name"] not in headings]
    violations.extend(
        {"rule": "sections.required", "severity": "error",
         "message": f"Missing required section: \"{s}\""} for s in missing_required
    )

    recommended = schema.get("sections", {}).get("recommended", [])
    missing_recommended = [s["name"] for s in recommended if s["name"] not in headings]
    violations.extend(
        {"rule": "sections.recommended", "severity": "warning",
         "message": f"Missing recommended section: \"{s}\""} for s in missing_recommended
    )

    return violations


def check_subtypes(meta: dict, headings: list[str], schema: dict) -> list[Violation]:
    subtypes_def = schema.get("subtypes")
    if not subtypes_def:
        return []

    field_name = subtypes_def["field"]
    subtype_val = meta.get(field_name)
    if not subtype_val:
        return []

    subtype_str = str(subtype_val).lower()
    values = subtypes_def["values"]

    if subtype_str not in values:
        return [{"rule": f"frontmatter.{field_name}", "severity": "error",
                 "message": f"Invalid {field_name} \"{subtype_val}\" — must be one of: {', '.join(sorted(values.keys()))}"}]

    def section_name(s) -> str:
        return s["name"] if isinstance(s, dict) else s

    required_sections = values[subtype_str].get("required_sections", [])
    missing = [section_name(s) for s in required_sections if section_name(s) not in headings]
    return [
        {"rule": "sections.required", "severity": "error",
         "message": f"Missing required section for {subtype_str}: \"{s}\""} for s in missing
    ]


def validate_single_dependency(entry: dict, base_dir: Path) -> list[Violation]:
    if not isinstance(entry, dict):
        return []

    path_str = entry.get("path", "")
    required_status = entry.get("required_status")

    if not path_str:
        return [{"rule": "depends_on.missing", "severity": "error",
                 "message": "depends_on entry missing 'path' field"}]

    if not required_status or not isinstance(required_status, list):
        return [{"rule": "depends_on.no-status", "severity": "error",
                 "message": f"depends_on entry '{path_str}' missing required_status list"}]

    target = base_dir / path_str
    if not target.exists():
        return [{"rule": "depends_on.missing", "severity": "error",
                 "message": f"Dependency does not exist: '{path_str}'"}]

    dep_content = target.read_text(encoding="utf-8")
    dep_meta, dep_err = parse_frontmatter(dep_content)
    if dep_err or not dep_meta:
        return [{"rule": "depends_on.invalid-status", "severity": "error",
                 "message": f"Dependency '{path_str}' has invalid frontmatter, cannot check status"}]

    dep_status = str(dep_meta.get("status", "")).lower()
    allowed = [s.lower() for s in required_status]
    if dep_status not in allowed:
        return [{"rule": "depends_on.invalid-status", "severity": "error",
                 "message": f"Dependency '{path_str}' has status '{dep_status}', required: {', '.join(required_status)}"}]

    return []


def check_depends_on(meta: dict, base_dir: Path) -> list[Violation]:
    deps = meta.get("depends_on")
    if not deps or not isinstance(deps, list):
        return []
    return [v for entry in deps for v in validate_single_dependency(entry, base_dir)]


def validate_single_track(entry: dict, repo_root: Path, *, skip_stale: bool = False) -> list[Violation]:
    if not isinstance(entry, dict):
        return []

    path_str = entry.get("path", "")
    verified = entry.get("last_verified", "")

    if not path_str or path_str.startswith("/") or ".." in path_str:
        return [{"rule": "tracks.path-format", "severity": "error",
                 "message": f"Invalid track path: '{path_str}' — must be relative, no leading / or .."}]

    if not verified:
        return [{"rule": "tracks.no-date", "severity": "error",
                 "message": f"Track entry '{path_str}' missing last_verified date"}]

    target = repo_root / path_str
    if not target.exists():
        return [{"rule": "tracks.path-missing", "severity": "error",
                 "message": f"Tracked path does not exist: '{path_str}'"}]

    # `tracks.stale` is age, and age is a PROXY for drift, not drift (RFC-0009): a tracked
    # file's commit being newer than `last_verified` fires on refactors, renames, and bulk
    # re-stamps that never touched the decision. So it is a WARNING (a "you may want to
    # re-verify" nudge), never an error that blocks — a 0.6%-precision error gate just trains
    # users to bump the date to silence it. Terminal-status docs skip it entirely (a dead
    # decision cannot drift); the caller passes `skip_stale` for those.
    if skip_stale:
        return []
    commit_date = last_commit_date(path_str, repo_root)
    if commit_date and commit_date > str(verified):
        return [{"rule": "tracks.stale", "severity": "warning",
                 "message": f"'{path_str}' has commits after last_verified ({verified}). "
                            f"Last commit: {commit_date}. Re-verify the doc still matches, "
                            f"then bump last_verified — or supersede/deprecate it."}]

    return []


def is_terminal_status(meta: dict, schema: dict) -> bool:
    """A doc whose status is terminal — superseded/deprecated/rejected/archived/etc. — is a
    closed decision (RFC-0009). Its tracked code keeps evolving, but the doc is a true
    historical record, not live documentation, so it cannot 'drift'. Such docs are exempt
    from the `tracks.stale` age check (they would otherwise be flagged forever)."""
    terminal = {s.lower() for s in schema.get("terminal_statuses", [])}
    return str(meta.get("status", "")).lower() in terminal


def check_tracks(meta: dict, repo_root: Path, schema: dict) -> list[Violation]:
    if "tracks" not in meta:
        return [{"rule": "tracks.required", "severity": "error",
                 "message": "Missing required field: tracks. Every document must declare what it tracks."}]

    tracks = meta.get("tracks")
    if not tracks or not isinstance(tracks, list):
        return [{"rule": "tracks.empty", "severity": "error",
                 "message": "tracks field is empty. Declare at least one path to track."}]

    # Path-format / missing-date / missing-path are still enforced (a malformed track entry is
    # always an error); only the AGE check is skipped for terminal-status docs.
    skip_stale = is_terminal_status(meta, schema)
    return [v for entry in tracks for v in validate_single_track(entry, repo_root, skip_stale=skip_stale)]


# --- Validation pipeline ---


def validate_doc(path: Path, schema: dict) -> FileResult:
    content = path.read_text(encoding="utf-8")

    naming_violations = check_naming(path, schema)

    meta, parse_err = parse_frontmatter(content)
    if parse_err:
        all_violations = naming_violations + [
            {"rule": "frontmatter.present", "severity": "critical", "message": parse_err}
        ]
        errors = [v for v in all_violations if v["severity"] != "warning"]
        warnings = [v for v in all_violations if v["severity"] == "warning"]
        return {"file": str(path), "status": "fail", "errors": errors, "warnings": warnings}

    headings = extract_h2_headings(content)
    repo_root = find_repo_root(path.parent)

    checks = [
        *naming_violations,
        *check_frontmatter_fields(meta, schema),
        *check_numbering(meta, path, schema),
        *check_sections(headings, schema),
        *check_subtypes(meta, headings, schema),
        *check_depends_on(meta, path.parent),
        *check_tracks(meta, repo_root, schema),
    ]

    errors = [v for v in checks if v["severity"] != "warning"]
    warnings = [v for v in checks if v["severity"] == "warning"]
    status = "fail" if errors else "pass"

    return {"file": str(path), "status": status, "errors": errors, "warnings": warnings}


def check_duplicate_numbers(paths: list[Path], schema: dict, changed: set[Path] | None = None) -> list[Violation]:
    numbering = schema.get("numbering", {})
    if not numbering.get("enabled"):
        return []

    pattern = re.compile(schema["naming"]["pattern"])

    by_directory: dict[Path, dict[int, list[Path]]] = {}
    for path in paths:
        match = pattern.match(path.name)
        if match:
            num = int(match.group(numbering["filename_group"]))
            by_directory.setdefault(path.parent, {}).setdefault(num, []).append(path)

    def involves_changed(ps: list[Path]) -> bool:
        return changed is None or any(p.resolve() in changed for p in ps)

    return [
        {"rule": "numbering.unique", "severity": "error",
         "message": f"Duplicate number {n}: {', '.join(str(p) for p in ps)}"}
        for dir_numbers in by_directory.values()
        for n, ps in dir_numbers.items()
        if len(ps) > 1 and involves_changed(ps)
    ]


def check_dependency_cycles(typed_files: list[tuple[Path, str]], changed: set[Path] | None = None) -> list[Violation]:
    graph: dict[str, list[str]] = {}
    for path, _ in typed_files:
        content = path.read_text(encoding="utf-8")
        meta, err = parse_frontmatter(content)
        if err or not meta:
            continue
        deps = meta.get("depends_on")
        if not deps or not isinstance(deps, list):
            continue
        resolved = [
            str((path.parent / entry["path"]).resolve())
            for entry in deps
            if isinstance(entry, dict) and entry.get("path")
        ]
        graph[str(path.resolve())] = resolved

    def find_cycle(node: str, visited: set, stack: set) -> list[str] | None:
        visited.add(node)
        stack.add(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                cycle = find_cycle(neighbor, visited, stack)
                if cycle:
                    return cycle
            elif neighbor in stack:
                return [neighbor, node]
        stack.discard(node)
        return None

    changed_str = {str(p) for p in changed} if changed is not None else None

    visited: set[str] = set()
    for node in graph:
        if node not in visited:
            cycle = find_cycle(node, visited, set())
            if cycle:
                if changed_str is not None and not any(n in changed_str for n in cycle):
                    continue
                short_paths = [Path(p).name for p in cycle]
                return [{"rule": "depends_on.circular", "severity": "error",
                         "message": f"Circular dependency detected: {' → '.join(short_paths)}"}]
    return []


# --- Discovery ---


def load_directories(root: Path, schema: dict) -> tuple[str, ...]:
    config_path = root / CONFIG_FILENAME
    config_key = schema["discovery"]["config_key"]
    defaults = tuple(schema["discovery"]["defaults"])

    if not config_path.exists():
        return defaults

    try:
        parsed = strictyaml.load(config_path.read_text())
        data = parsed.data
    except strictyaml.YAMLError:
        return defaults

    if not isinstance(data, dict):
        return defaults

    paths = data.get("paths", {})
    if not isinstance(paths, dict):
        return defaults

    configured = paths.get(config_key)
    if not configured or not isinstance(configured, list):
        return defaults

    return tuple(configured)


def find_md_files(root: Path, directories: tuple[str, ...]) -> list[Path]:
    return [
        f
        for dir_name in directories
        if (root / dir_name).is_dir()
        for f in sorted((root / dir_name).glob("*.md"))
        if f.name.lower() not in ("readme.md", "index.md")
    ]


def check_undeclared_docs(root: Path, configured: tuple[str, ...], schema: dict) -> list[Violation]:
    defaults = tuple(schema["discovery"]["defaults"])
    configured_set = set(configured)
    undeclared_dirs = [
        d for d in defaults
        if d not in configured_set and (root / d).is_dir()
    ]
    undeclared_files = find_md_files(root, tuple(undeclared_dirs))
    return [
        {"rule": "discovery.undeclared", "severity": "warning",
         "message": f"Found {schema['type']} in '{f.relative_to(root)}' but its directory is not declared in {CONFIG_FILENAME}"}
        for f in undeclared_files
    ]


def discover_files(root: Path, schema: dict) -> tuple[list[Path], list[Violation]]:
    config_path = root / CONFIG_FILENAME
    configured = load_directories(root, schema)
    files = find_md_files(root, configured)

    undeclared_warnings = (
        check_undeclared_docs(root, configured, schema)
        if config_path.exists() else []
    )

    return files, undeclared_warnings


def classify_file(path: Path, schemas: dict) -> str | None:
    for type_name, schema in schemas.items():
        pattern = re.compile(schema["naming"]["pattern"])
        if pattern.match(path.name):
            return type_name
    return None


def resolve_paths(args: list[str], type_filter: str, schemas: dict) -> tuple[list[tuple[Path, str]], list[Violation]]:
    if not args:
        root = Path.cwd()
        all_files = []
        all_warnings = []

        types_to_scan = schemas.items() if type_filter == "all" else [(type_filter, schemas[type_filter])]

        for type_name, schema in types_to_scan:
            files, warnings = discover_files(root, schema)
            all_files.extend((f, type_name) for f in files)
            all_warnings.extend(warnings)

        return all_files, all_warnings

    files = []
    for arg in args:
        p = Path(arg)
        if p.is_file():
            doc_type = classify_file(p, schemas)
            if doc_type and (type_filter == "all" or type_filter == doc_type):
                files.append((p, doc_type))
            elif type_filter != "all":
                files.append((p, type_filter))
            else:
                first_type = next(iter(schemas))
                files.append((p, first_type))
        elif p.is_dir():
            for f in sorted(p.glob("*.md")):
                if f.name.lower() in ("readme.md", "index.md"):
                    continue
                doc_type = classify_file(f, schemas) or next(iter(schemas))
                if type_filter == "all" or type_filter == doc_type:
                    files.append((f, doc_type))
        else:
            print(f"Warning: '{arg}' is not a file or directory, skipping", file=sys.stderr)
    return files, []


# --- Output ---


def format_json(results: list[FileResult], cross_file: list[Violation], discovery_warnings: list[Violation]) -> str:
    error_count = sum(len(r["errors"]) for r in results) + len(cross_file)
    warning_count = sum(len(r["warnings"]) for r in results) + len(discovery_warnings)

    output = {
        "scanned": len(results),
        "errors": error_count,
        "warnings": warning_count,
        "results": results,
    }

    if cross_file:
        output["cross_file_errors"] = cross_file

    if discovery_warnings:
        output["discovery_warnings"] = discovery_warnings

    return json.dumps(output, indent=2)


def format_errors_only(results: list[FileResult], cross_file: list[Violation]) -> str:
    """Compact error-only report — no passed roster, no warnings. For push channels."""
    lines = []
    for r in results:
        for v in r["errors"]:
            lines.append(f"  {r['file']} [{v['rule']}] {v['message']}")
    for v in cross_file:
        lines.append(f"  [{v['rule']}] {v['message']}")
    return "\n".join(lines)


def format_text(results: list[FileResult], cross_file: list[Violation], discovery_warnings: list[Violation]) -> str:
    error_count = sum(len(r["errors"]) for r in results) + len(cross_file)
    warning_count = sum(len(r["warnings"]) for r in results) + len(discovery_warnings)

    lines = [
        f"Scanned: {len(results)} files",
        f"Result: {error_count} errors, {warning_count} warnings",
        "",
    ]

    failures = [r for r in results if r["status"] == "fail"]
    if failures:
        lines.append("Errors:")
        for r in failures:
            for v in r["errors"]:
                lines.append(f"  {r['file']} [{v['rule']}] {v['message']}")

    all_warnings = [
        (r["file"], v)
        for r in results
        for v in r["warnings"]
    ] + [("config", v) for v in discovery_warnings]

    if all_warnings:
        lines.append("")
        lines.append("Warnings:")
        for source, v in all_warnings:
            lines.append(f"  {source} [{v['rule']}] {v['message']}")

    if cross_file:
        lines.append("")
        lines.append("Cross-file errors:")
        for v in cross_file:
            lines.append(f"  [{v['rule']}] {v['message']}")

    passed = [r for r in results if r["status"] == "pass" and not r["warnings"]]
    if passed:
        lines.append("")
        lines.append("Passed:")
        for r in passed:
            lines.append(f"  {r['file']}")

    return "\n".join(lines)


# --- CLI ---


def parse_args(argv: list[str], schemas: dict) -> tuple[str, str, str, str, list[str]]:
    fmt = "json"
    doc_type = "all"
    scope = "all"
    checks = "all"
    paths = []

    valid_types = [*schemas.keys(), "all"]

    def take_value(name: str, allowed: tuple[str, ...], i: int) -> str:
        if i + 1 >= len(argv):
            print(f"Error: {name} requires a value.", file=sys.stderr)
            sys.exit(2)
        value = argv[i + 1]
        if value not in allowed:
            print(f"Error: {name} must be one of: {', '.join(allowed)}. Received: \"{value}\"", file=sys.stderr)
            sys.exit(2)
        return value

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--help":
            print(__doc__)
            sys.exit(0)
        elif arg == "--format":
            fmt = take_value("--format", ("json", "text", "hook", "session"), i)
            i += 2
        elif arg == "--type" and i + 1 < len(argv):
            doc_type = argv[i + 1]
            if doc_type not in valid_types:
                print(f"Error: --type must be one of: {', '.join(valid_types)}. Received: \"{doc_type}\"", file=sys.stderr)
                sys.exit(2)
            i += 2
        elif arg == "--scope":
            scope = take_value("--scope", ("all", "changed"), i)
            i += 2
        elif arg == "--checks":
            checks = take_value("--checks", ("all", "cross-file"), i)
            i += 2
        elif arg.startswith("--"):
            print(f"Error: Unknown option '{arg}'. Run with --help for usage.", file=sys.stderr)
            sys.exit(2)
        else:
            paths.append(arg)
            i += 1

    return fmt, doc_type, scope, checks, paths


def main():
    schemas = load_schemas(find_schema_dir())
    fmt, doc_type, scope, checks, paths = parse_args(sys.argv[1:], schemas)

    typed_files, discovery_warnings = resolve_paths(paths, doc_type, schemas)

    # --scope changed: only block on cross-file violations a session-changed doc
    # participates in. Cross-file checks still run over the FULL set (a duplicate
    # needs its twin to be detected) but are filtered to those touching `changed`.
    changed = git_changed_docs(find_repo_root(Path.cwd())) if scope == "changed" else None
    if scope == "changed" and not (changed & {p.resolve() for p, _ in typed_files}):
        sys.exit(0)  # no doc touched this session → nothing to gate

    if not typed_files and not discovery_warnings:
        sys.exit(0)

    # Per-doc checks honor --scope: with `changed`, validate ONLY the docs touched this
    # session (RFC-0009 Stop gate verifies what the turn changed, not the whole corpus — a
    # pre-existing error in an untouched doc must not block every turn). Cross-file checks
    # below still run over the full set, then filter to `changed`, because a duplicate needs
    # its twin to be seen.
    per_doc_files = (
        [(p, t) for p, t in typed_files if changed is None or p.resolve() in changed]
        if scope == "changed" else typed_files
    )
    results = [] if checks == "cross-file" else [validate_doc(path, schemas[t]) for path, t in per_doc_files]

    cross_file = [
        v
        for type_name, schema in schemas.items()
        for v in check_duplicate_numbers([p for p, t in typed_files if t == type_name], schema, changed)
    ] + check_dependency_cycles(typed_files, changed)

    error_count = sum(len(r["errors"]) for r in results) + len(cross_file)
    warning_count = sum(len(r["warnings"]) for r in results) + len(discovery_warnings)

    # Push channels (hook, session) are SILENT on success. Pull channels (json,
    # text) also exit 0 when fully clean, preserving prior behavior.
    if error_count == 0 and warning_count == 0:
        sys.exit(0)

    if fmt == "hook":
        # Stop gate: block on errors with a compact error-only reason; silent on
        # warnings-only (warnings never push — reach them via the CLI).
        if error_count > 0:
            print(json.dumps({
                "decision": "block",
                "reason": "Documentation validation failed. Fix these before continuing:\n"
                          + format_errors_only(results, cross_file),
            }))
        sys.exit(0)
    elif fmt == "session":
        # SessionStart: one-line awareness, errors only. additionalContext is
        # fed to Claude (not the user); suppressOutput hides any stray stdout.
        if error_count > 0:
            line = f"docs-toolkit: {len(typed_files)} docs, {error_count} error(s). Run `validate.py` for detail."
            print(json.dumps({
                "suppressOutput": True,
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": line,
                },
            }))
        sys.exit(0)
    else:
        report = format_json(results, cross_file, discovery_warnings) if fmt == "json" else format_text(results, cross_file, discovery_warnings)
        print(report)

    sys.exit(1 if error_count > 0 else 0)


if __name__ == "__main__":
    main()
