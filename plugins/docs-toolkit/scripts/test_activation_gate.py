# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Regression test: the automatic hook channels must stay dormant in repos that never
adopted docs-toolkit, and fire in repos that did (opt-in via a `.docs-toolkit.yml` marker).

This guards the "hooks leak into other repos" bug: installed plugin hooks run in EVERY
session in EVERY repo, so without an opt-in gate they injected docs-toolkit findings into
any project that merely had a default-named doc dir (`specs`, `docs/decisions`, ...).

Runs the REAL hook commands (validate.py --format session, stop_gate.py, posttool_validate.py)
against throwaway git repos — the same surface a live session exercises. Self-contained:
`uv run --script test_activation_gate.py`. Exit 0 = all pass.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).parent
VALIDATE = SCRIPTS / "validate.py"
STOP_GATE = SCRIPTS / "stop_gate.py"
POSTTOOL = SCRIPTS / "posttool_validate.py"

FOREIGN_SPEC = "# My Feature Spec\n\nPlain notes, no frontmatter.\n"
MARKER = "paths:\n  specs:\n    - specs\n"


def sh(args: list[str], cwd: Path, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, input=stdin, capture_output=True, text=True)


def make_repo(root: Path, *, opted_in: bool) -> None:
    (root / "specs").mkdir(parents=True)
    (root / "specs" / "my-feature.md").write_text(FOREIGN_SPEC)
    if opted_in:
        (root / ".docs-toolkit.yml").write_text(MARKER)
    sh(["git", "init", "-q"], root)
    sh(["git", "config", "user.email", "t@t.co"], root)
    sh(["git", "config", "user.name", "t"], root)
    sh(["git", "add", "-A"], root)
    sh(["git", "commit", "-qm", "init"], root)
    # a post-commit edit so --scope changed / stop_gate sees a changed doc
    (root / "specs" / "my-feature.md").write_text(FOREIGN_SPEC + "\nedited\n")


def run_hooks(root: Path) -> dict[str, str]:
    """Returns {channel: stdout} for the three automatic channels."""
    spec = str(root / "specs" / "my-feature.md")
    session = sh(["uv", "run", "--script", str(VALIDATE),
                  "--format", "session", "--require-activation"], root)
    stop = sh(["uv", "run", "--script", str(STOP_GATE)], root, stdin="{}")
    posttool = sh(["uv", "run", "--script", str(POSTTOOL)], root,
                  stdin=json.dumps({"tool_input": {"file_path": spec}}))
    return {
        "SessionStart": session.stdout.strip(),
        "Stop": stop.stdout.strip(),
        "PostToolUse": posttool.stdout.strip(),
    }


def make_scope_repo(root: Path) -> None:
    """Adopted repo with an unrelated `.md` OUTSIDE every discovery dir plus a real tracked doc."""
    (root / "src").mkdir(parents=True)
    (root / "src" / "button-notes.md").write_text("# Button notes\n\nplain notes\n")
    (root / "README.md").write_text("# Readme\n\nhello\n")
    (root / "specs").mkdir(parents=True)
    (root / "specs" / "SPEC-real.md").write_text("# Real spec\n\nno frontmatter\n")
    (root / ".docs-toolkit.yml").write_text(MARKER)
    sh(["git", "init", "-q"], root)
    sh(["git", "config", "user.email", "t@t.co"], root)
    sh(["git", "config", "user.name", "t"], root)
    sh(["git", "add", "-A"], root)
    sh(["git", "commit", "-qm", "init"], root)


def posttool_on(root: Path, rel: str) -> str:
    return sh(["uv", "run", "--script", str(POSTTOOL)], root,
              stdin=json.dumps({"tool_input": {"file_path": str(root / rel)}})).stdout.strip()


def main() -> None:
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        foreign = Path(tmp) / "foreign"
        make_repo(foreign, opted_in=False)
        for channel, out in run_hooks(foreign).items():
            if out:
                failures.append(f"LEAK: {channel} emitted output in a repo with no marker:\n{out}")

    # PostToolUse must scope to TRACKED docs even inside an adopted repo: an edit to an `.md`
    # outside every discovery dir is not the plugin's business (the "spying on unrelated md"
    # noise), while a real tracked doc still gets validated.
    with tempfile.TemporaryDirectory() as tmp:
        scoped = Path(tmp) / "scoped"
        make_scope_repo(scoped)
        for rel in ("src/button-notes.md", "README.md"):
            out = posttool_on(scoped, rel)
            if out:
                failures.append(f"NOISE: PostToolUse fired on untracked '{rel}' in an adopted repo:\n{out}")
        if not posttool_on(scoped, "specs/SPEC-real.md"):
            failures.append("SILENT: PostToolUse ignored a real tracked doc (specs/SPEC-real.md)")

    with tempfile.TemporaryDirectory() as tmp:
        adopted = Path(tmp) / "adopted"
        make_repo(adopted, opted_in=True)
        for channel, out in run_hooks(adopted).items():
            if not out:
                failures.append(f"SILENT: {channel} emitted nothing in an opted-in repo (should fire)")

    # CLI (no --require-activation) must stay ungated: run anywhere on demand.
    with tempfile.TemporaryDirectory() as tmp:
        bare = Path(tmp) / "bare"
        make_repo(bare, opted_in=False)
        cli = sh(["uv", "run", "--script", str(VALIDATE),
                  "--format", "text", "specs/my-feature.md"], bare)
        if "frontmatter.present" not in cli.stdout:
            failures.append(f"CLI regression: ungated validate.py produced no findings:\n{cli.stdout}")

    if failures:
        print("FAIL\n" + "\n".join(f"  - {f}" for f in failures))
        sys.exit(1)
    print("PASS: hooks dormant without marker, active with marker, scoped to tracked docs, CLI ungated.")


if __name__ == "__main__":
    main()
