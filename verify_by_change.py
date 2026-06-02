#!/usr/bin/env python3
"""Suggest verification steps based on changed files."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import shlex
import subprocess
from collections import OrderedDict

NODE_CODE_EXTENSIONS = {".js", ".mjs", ".cjs", ".ts"}
NODE_CLI_COMMANDS = [
    "Run the closest Node test/build command for the changed CLI or library path.",
    "Exercise the affected CLI/script path with a small safe input.",
]
PYTHON_CLI_COMMANDS = [
    "Run `python3 -m pip install -e .` in a clean environment or current virtualenv.",
    "Exercise the affected console script with `--help` or a small safe input.",
    "Run `python3 -m unittest discover -s tests` or the closest targeted Python tests.",
]
SECRET_MATERIAL_COMMANDS = [
    "Inspect the diff for real credentials, private keys, API tokens, webhook URLs, or production identifiers.",
    "If a real secret was committed, rotate it and remove it from git history before publishing.",
    "Run the closest secret scanning or pre-commit check if one exists.",
]
SECURITY_SENSITIVE_COMMANDS = [
    "Run targeted tests for authorization, denial, expiry, approval, and failure paths.",
    "Exercise at least one negative path; do not verify only the happy path.",
    "Review logs, errors, and receipts for accidental secret or approval-payload leakage.",
]
SECRET_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.test",
}
SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
SECRET_TOKENS = {"secret", "secrets", "credential", "credentials", "token", "tokens", "private", "key"}
SECURITY_TOKENS = {
    "auth",
    "authorize",
    "authorization",
    "approval",
    "approvals",
    "deploy",
    "guard",
    "permission",
    "permissions",
    "policy",
    "policies",
    "receipt",
    "receipts",
}

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
    if secret_material_change(normalized):
        return "secret_material", {"commands": SECRET_MATERIAL_COMMANDS}
    if security_sensitive_change(normalized):
        return "security_sensitive", {"commands": SECURITY_SENSITIVE_COMMANDS}
    return None


def path_tokens(normalized: str) -> set[str]:
    return {token for token in re.split(r"[/._-]+", normalized) if token}


def secret_material_change(normalized: str) -> bool:
    path = pathlib.Path(normalized)
    if path.name in SECRET_FILENAMES or path.suffix in SECRET_SUFFIXES:
        return True
    return bool(path_tokens(normalized) & SECRET_TOKENS)


def security_sensitive_change(normalized: str) -> bool:
    return bool(path_tokens(normalized) & SECURITY_TOKENS)


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


def review_packet_changed_files(packet_path: pathlib.Path) -> list[str]:
    content = packet_path.read_text(encoding="utf-8")
    section = markdown_section(content, "Changed Files")
    return unique_ordered(inline_code_bullets(section))


def review_packet_repo(packet_path: pathlib.Path) -> pathlib.Path | None:
    content = packet_path.read_text(encoding="utf-8")
    repo = first_inline_code(content, "Repo")
    if not repo:
        return None
    path = pathlib.Path(repo)
    return path if path.exists() else None


def review_packet_readiness(packet_path: pathlib.Path) -> dict[str, object] | None:
    content = packet_path.read_text(encoding="utf-8")
    section = markdown_section(content, "Repo Readiness")
    if not section.strip():
        return None

    summary = {
        "present": True,
        "contract": inline_metric(section, "Contract"),
        "ready": bool_metric(section, "Ready"),
        "score": None,
        "points_possible": None,
        "threshold": int_metric(section, "Threshold"),
        "stack": inline_metric(section, "Stack"),
        "required_blockers": None,
        "recommendations": None,
        "passed": None,
        "warnings": None,
        "failed": None,
        "critical_failures": None,
    }

    score = inline_metric(section, "Score")
    if score:
        summary["score"], summary["points_possible"] = score_metric(score)

    summary_text = inline_summary_line(section)
    if summary_text:
        summary.update(summary_metrics(summary_text))

    return summary


def review_packet_task_contract(packet_path: pathlib.Path) -> dict[str, object] | None:
    content = packet_path.read_text(encoding="utf-8")
    section = markdown_section(content, "Task Contract")
    if not section.strip():
        return None

    status = inline_metric(section, "Status")
    if not status:
        return None

    return {
        "present": True,
        "source": first_inline_code(section, "Source"),
        "status": status,
        "required_sections": inline_metric(section, "Required sections"),
        "missing_sections": list_metric(section, "Missing sections"),
        "placeholder_markers": list_metric(section, "Placeholder markers"),
    }


def first_inline_code(markdown: str, label: str) -> str | None:
    match = re.search(rf"^{re.escape(label)}:\s+`([^`]+)`", markdown, flags=re.MULTILINE)
    return match.group(1) if match else None


def inline_metric(markdown: str, label: str) -> str | None:
    match = re.search(rf"^- {re.escape(label)}: `([^`]+)`", markdown, flags=re.MULTILINE)
    return match.group(1) if match else None


def bool_metric(markdown: str, label: str) -> bool | None:
    value = inline_metric(markdown, label)
    if value is None:
        return None
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return None


def int_metric(markdown: str, label: str) -> int | None:
    value = inline_metric(markdown, label)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def list_metric(markdown: str, label: str) -> list[str]:
    match = re.search(rf"^- {re.escape(label)}: (.+)$", markdown, flags=re.MULTILINE)
    if not match:
        return []
    value = match.group(1).strip()
    if value.lower() == "none":
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def score_metric(value: str) -> tuple[int | None, int | None]:
    if "/" not in value:
        return int_or_none(value), None
    left, right = value.split("/", 1)
    return int_or_none(left), int_or_none(right)


def inline_summary_line(markdown: str) -> str | None:
    match = re.search(r"^- Summary: (.+)$", markdown, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def summary_metrics(summary: str) -> dict[str, int | None]:
    return {
        "required_blockers": labeled_count(summary, "required blockers"),
        "recommendations": labeled_count(summary, "recommendations"),
        "passed": labeled_count(summary, "passed"),
        "warnings": labeled_count(summary, "warnings"),
        "failed": labeled_count(summary, "failed"),
        "critical_failures": labeled_count(summary, "critical failures"),
    }


def labeled_count(summary: str, label: str) -> int | None:
    match = re.search(rf"`?(\d+)`?\s+{re.escape(label)}", summary)
    return int(match.group(1)) if match else None


def int_or_none(value: str) -> int | None:
    try:
        return int(value.strip())
    except ValueError:
        return None


def markdown_section(markdown: str, title: str) -> str:
    lines = markdown.splitlines()
    selected: list[str] = []
    inside = False
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            inside = line[3:].strip() == title
            continue
        if inside:
            selected.append(line)
    return "\n".join(selected)


def inline_code_bullets(markdown: str) -> list[str]:
    paths: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        if stripped == "- No changed files detected.":
            continue
        if stripped.startswith("- `") and stripped.endswith("`"):
            paths.append(stripped[3:-1])
    return paths


def repo_context(repo: pathlib.Path | None) -> dict[str, object]:
    if repo is None:
        return {"node_cli": False, "python_cli": False}

    package_json = repo / "package.json"
    node_cli = False
    if package_json.exists():
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            package = {}

        bin_field = package.get("bin")
        scripts = package.get("scripts", {})
        has_bin = isinstance(bin_field, (str, dict)) and bool(bin_field)
        has_node_scripts = isinstance(scripts, dict) and any(
            name in scripts for name in ("test", "build", "lint", "check")
        )
        node_cli = has_bin and has_node_scripts

    pyproject = repo / "pyproject.toml"
    python_cli = pyproject.exists() and has_pyproject_scripts(pyproject.read_text(encoding="utf-8"))
    return {"node_cli": node_cli, "python_cli": python_cli}


def has_pyproject_scripts(pyproject: str) -> bool:
    in_scripts = False
    for raw_line in pyproject.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        heading = re.match(r"^\[([^\]]+)\]$", line)
        if heading:
            in_scripts = heading.group(1).strip() == "project.scripts"
            continue
        if in_scripts and re.match(r"^[A-Za-z0-9_.-]+\s*=\s*['\"][^'\"]+['\"]", line):
            return True
    return False


def node_cli_change(raw: str, context: dict[str, object]) -> bool:
    suffix = pathlib.Path(raw).suffix.lower()
    if suffix not in NODE_CODE_EXTENSIONS:
        return False

    normalized = raw.replace("\\", "/").lower()
    stem = pathlib.Path(normalized).stem
    if normalized.startswith(("bin/", "cli/")) or stem == "cli":
        return True
    if stem == "index" and context.get("node_cli"):
        return True
    return bool(context.get("node_cli"))


def python_cli_change(raw: str, context: dict[str, object]) -> bool:
    if not context.get("python_cli"):
        return False

    normalized = raw.replace("\\", "/").lower()
    suffix = pathlib.Path(normalized).suffix
    stem = pathlib.Path(normalized).stem
    if normalized == "pyproject.toml":
        return True
    if suffix != ".py":
        return False
    if stem in {"cli", "__main__"}:
        return True
    return normalized.startswith(("src/", "bin/", "cli/"))


def classify(paths: list[str], context: dict[str, object] | None = None) -> dict[str, dict[str, list[str]]]:
    context = context or {}
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
        if node_cli_change(raw, context):
            bucket = selected.setdefault("node_cli", {"files": [], "commands": list(NODE_CLI_COMMANDS)})
            bucket["files"].append(raw)
            continue
        if python_cli_change(raw, context):
            bucket = selected.setdefault("python_cli", {"files": [], "commands": list(PYTHON_CLI_COMMANDS)})
            bucket["files"].append(raw)
            continue

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
    repo_readiness: dict[str, object] | None = None,
    task_contract: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "verify-by-change.v1",
        "source": source,
        "changed_files": paths,
        "empty": len(paths) == 0,
        "categories": classified,
    }
    if repo_readiness is not None:
        payload["repo_readiness"] = repo_readiness
    if task_contract is not None:
        payload["task_contract"] = task_contract
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Explicit changed file paths.")
    parser.add_argument("--repo", help="Optional repository path for git-based detection.")
    parser.add_argument("--review-packet", help="Optional codex-review-packet Markdown file to read changed files from.")
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
    repo_readiness = None
    task_contract = None
    context: dict[str, object] = {}
    if args.review_packet and (args.paths or args.repo):
        raise SystemExit("Use --review-packet by itself, without explicit paths or --repo.")

    if args.paths:
        paths = args.paths
        source = {
            "type": "explicit_paths",
            "repo": None,
            "base": None,
            "staged": False,
            "include_working_tree": False,
        }
    elif args.review_packet:
        packet_path = pathlib.Path(args.review_packet).resolve()
        if not packet_path.exists():
            raise SystemExit(f"Review packet not found: {packet_path}")
        paths = review_packet_changed_files(packet_path)
        repo_readiness = review_packet_readiness(packet_path)
        task_contract = review_packet_task_contract(packet_path)
        packet_repo = review_packet_repo(packet_path)
        context = repo_context(packet_repo)
        source = {
            "type": "review_packet",
            "repo": str(packet_repo) if packet_repo else None,
            "base": None,
            "staged": False,
            "include_working_tree": False,
            "review_packet": str(packet_path),
        }
    elif args.repo:
        repo = pathlib.Path(args.repo).resolve()
        context = repo_context(repo)
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

    classified = classify(paths, context)
    if args.json_envelope:
        output = json.dumps(json_envelope(paths, classified, source, repo_readiness, task_contract), indent=2) + "\n"
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
