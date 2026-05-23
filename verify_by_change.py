#!/usr/bin/env python3
"""Suggest verification steps based on changed files."""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
from collections import OrderedDict

RULES = OrderedDict(
    [
        (
            "docs",
            {
                "match": {".md", ".txt"},
                "commands": ["Review rendered Markdown and verify links if public-facing."],
            },
        ),
        (
            "shell",
            {
                "match": {".sh"},
                "commands": ["Run `bash -n` on changed scripts.", "Execute the script path on a safe example if possible."],
            },
        ),
        (
            "python",
            {
                "match": {".py"},
                "commands": ["Run `python3 -m py_compile` on changed Python files.", "Run the closest targeted script or tests."],
            },
        ),
        (
            "web",
            {
                "match": {".js", ".jsx", ".ts", ".tsx", ".css", ".html"},
                "commands": ["Run the closest frontend test/build command.", "Open the affected UI and verify the changed path manually."],
            },
        ),
        (
            "swift",
            {
                "match": {".swift"},
                "commands": ["Build the affected Xcode target.", "Run targeted tests or simulator checks for the changed flow."],
            },
        ),
    ]
)


def repo_changed_files(repo: pathlib.Path, base: str | None) -> list[str]:
    args = ["git", "-C", str(repo), "diff", "--name-only"]
    if base:
        args.append(f"{base}...HEAD")
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or "git diff failed")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def classify(paths: list[str]) -> dict[str, dict[str, list[str]]]:
    selected: dict[str, dict[str, list[str]]] = OrderedDict()
    uncategorized: list[str] = []
    for raw in paths:
        suffix = pathlib.Path(raw).suffix.lower()
        matched = False
        for name, rule in RULES.items():
            if suffix in rule["match"]:
                bucket = selected.setdefault(name, {"files": [], "commands": list(rule["commands"])})
                bucket["files"].append(raw)
                matched = True
                break
        if not matched:
            uncategorized.append(raw)
    if uncategorized:
        selected["uncategorized"] = {
            "files": uncategorized,
            "commands": ["Inspect these files manually and run the closest repo-specific verification."],
        }
    return selected


def render_text(classified: dict[str, dict[str, list[str]]]) -> str:
    lines = ["# Verification Checklist", ""]
    for name, payload in classified.items():
        lines.append(f"## {name.title()}")
        lines.append("")
        lines.extend(f"- `{path}`" for path in payload["files"])
        lines.append("")
        lines.extend(f"- {command}" for command in payload["commands"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Explicit changed file paths.")
    parser.add_argument("--repo", help="Optional repository path for git-based detection.")
    parser.add_argument("--base", help="Optional base ref, for example origin/main.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.paths:
        paths = args.paths
    elif args.repo:
        paths = repo_changed_files(pathlib.Path(args.repo).resolve(), args.base)
    else:
        raise SystemExit("Provide explicit paths or --repo.")

    classified = classify(paths)
    if args.json:
        print(json.dumps(classified, indent=2))
    else:
        print(render_text(classified), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
