#!/usr/bin/env python3
"""Suggest verification steps based on changed files."""

from __future__ import annotations

import argparse
import json
import pathlib
import shlex
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
            "config",
            {
                "match": {".json", ".toml", ".yaml", ".yml"},
                "commands": ["Review config syntax and referenced paths.", "Run the commands or workflows affected by the config change."],
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

PATH_RULES = OrderedDict(
    [
        (
            "github_action",
            {
                "paths": {"action.yml", "action.yaml"},
                "commands": [
                    "Validate action inputs, outputs, runtime, and required shell/tool dependencies.",
                    "Run the repository's action contract checks, such as `make test`, `make build`, and `make lint` when available.",
                    "Review fail-open/fail-closed behavior before shipping safety, deploy, or approval actions.",
                ],
            },
        ),
        (
            "github_workflow",
            {
                "workflow_suffixes": {".yml", ".yaml"},
                "commands": [
                    "Review workflow triggers, permissions, secrets, and protected-branch assumptions.",
                    "Run the local commands invoked by the changed workflow, not only YAML syntax checks.",
                    "Check whether production or security-sensitive paths should fail closed.",
                ],
            },
        ),
    ]
)


def matching_path_rule(raw: str) -> tuple[str, dict[str, object]] | None:
    normalized = raw.replace("\\", "/").lower()
    suffix = pathlib.Path(normalized).suffix
    for name, rule in PATH_RULES.items():
        if normalized in rule.get("paths", set()):
            return name, rule
        if normalized.startswith(".github/workflows/") and suffix in rule.get("workflow_suffixes", set()):
            return name, rule
    return None


def parse_status_paths(output: str) -> list[str]:
    paths: list[str] = []
    for line in output.splitlines():
        if not line:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path:
            paths.append(path)
    return paths


def unique_ordered(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    selected: list[str] = []
    for path in paths:
        if path in seen:
            continue
        selected.append(path)
        seen.add(path)
    return selected


def repo_changed_files(
    repo: pathlib.Path,
    base: str | None,
    staged: bool = False,
    include_working_tree: bool = False,
) -> list[str]:
    if staged:
        args = ["git", "-C", str(repo), "diff", "--cached", "--name-only"]
    elif base:
        args = ["git", "-C", str(repo), "diff", "--name-only", f"{base}...HEAD"]
    else:
        args = ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"]
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or "git diff failed")
    if not base and not staged:
        return parse_status_paths(result.stdout)
    paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if base and include_working_tree:
        status_args = ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"]
        status_result = subprocess.run(status_args, text=True, capture_output=True, check=False)
        if status_result.returncode != 0:
            raise SystemExit(status_result.stderr.strip() or "git status failed")
        paths.extend(parse_status_paths(status_result.stdout))
    return unique_ordered(paths)


def classify(paths: list[str]) -> dict[str, dict[str, list[str]]]:
    selected: dict[str, dict[str, list[str]]] = OrderedDict()
    uncategorized: list[str] = []
    for raw in paths:
        path_rule = matching_path_rule(raw)
        if path_rule:
            name, rule = path_rule
            bucket = selected.setdefault(name, {"files": [], "commands": list(rule["commands"])})
            bucket["files"].append(raw)
            continue

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
    if not classified:
        lines.extend([
            "No changed files detected.",
            "",
            "- Confirm the target ref, staged state, or working tree is what you intended to verify.",
        ])
        return "\n".join(lines).rstrip() + "\n"
    for name, payload in classified.items():
        lines.append(f"## {name.replace('_', ' ').title()}")
        lines.append("")
        lines.extend(f"- `{path}`" for path in payload["files"])
        lines.append("")
        lines.extend(f"- {command}" for command in payload["commands"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def json_envelope(
    paths: list[str],
    classified: dict[str, dict[str, list[str]]],
    source: dict[str, str | bool | None],
) -> dict[str, object]:
    return {
        "schema_version": "verify-by-change.v1",
        "source": source,
        "changed_files": paths,
        "empty": len(paths) == 0,
        "categories": classified,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Explicit changed file paths.")
    parser.add_argument("--repo", help="Optional repository path for git-based detection.")
    parser.add_argument("--base", help="Optional base ref, for example origin/main.")
    parser.add_argument("--staged", action="store_true", help="Use staged changes from --repo.")
    parser.add_argument(
        "--include-working-tree",
        action="store_true",
        help="When --base is set, also include staged, unstaged, and untracked files.",
    )
    parser.add_argument("--fail-on-empty", action="store_true", help="Exit with code 2 when no changed files are detected.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown.")
    parser.add_argument("--json-envelope", action="store_true", help="Emit JSON with schema, source, changed files, and categories.")
    parser.add_argument("--output", help="Optional output file path.")
    return parser.parse_args()


def write_or_print(output: str, output_path: str | None) -> None:
    if not output_path:
        print(output, end="")
        return
    pathlib.Path(output_path).write_text(output, encoding="utf-8")
    print(f"Wrote verification checklist to {shlex.quote(output_path)}")


def main() -> int:
    args = parse_args()
    source: dict[str, str | bool | None]
    if args.paths:
        paths = args.paths
        source = {
            "type": "explicit_paths",
            "repo": None,
            "base": None,
            "staged": False,
            "include_working_tree": False,
        }
    elif args.repo:
        repo = pathlib.Path(args.repo).resolve()
        paths = repo_changed_files(
            repo,
            args.base,
            staged=args.staged,
            include_working_tree=args.include_working_tree,
        )
        source = {
            "type": "git",
            "repo": str(repo),
            "base": args.base,
            "staged": args.staged,
            "include_working_tree": args.include_working_tree,
        }
    else:
        raise SystemExit("Provide explicit paths or --repo.")

    classified = classify(paths)
    if args.json_envelope:
        output = json.dumps(json_envelope(paths, classified, source), indent=2) + "\n"
    elif args.json:
        output = json.dumps(classified, indent=2) + "\n"
    else:
        output = render_text(classified)
    write_or_print(output, args.output)
    if args.fail_on_empty and not paths:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
