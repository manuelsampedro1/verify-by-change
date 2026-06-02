from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from verify_by_change import classify, has_pyproject_scripts, json_envelope, matching_path_rule, parse_status_paths, render_text, repo_changed_files, repo_context, review_packet_changed_files, review_packet_readiness, unique_ordered  # noqa: E402


def run(*args: str, cwd: pathlib.Path) -> None:
    subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=True)


class VerifyByChangeTests(unittest.TestCase):
    def test_classifies_known_extensions_and_uncategorized_files(self) -> None:
        classified = classify(["README.md", "scripts/deploy.sh", ".github/workflows/ci.yml", "Sources/App.swift", "asset.bin"])

        self.assertEqual(classified["docs"]["files"], ["README.md"])
        self.assertEqual(classified["shell"]["files"], ["scripts/deploy.sh"])
        self.assertEqual(classified["github_workflow"]["files"], [".github/workflows/ci.yml"])
        self.assertEqual(classified["swift"]["files"], ["Sources/App.swift"])
        self.assertEqual(classified["uncategorized"]["files"], ["asset.bin"])

    def test_path_rules_take_precedence_for_github_actions(self) -> None:
        classified = classify(["action.yml", ".github/workflows/deploy-gate.yaml", "config/settings.yml"])

        self.assertEqual(classified["github_action"]["files"], ["action.yml"])
        self.assertIn("fail-open/fail-closed", " ".join(classified["github_action"]["commands"]))
        self.assertEqual(classified["github_workflow"]["files"], [".github/workflows/deploy-gate.yaml"])
        self.assertIn("workflow triggers", " ".join(classified["github_workflow"]["commands"]))
        self.assertEqual(classified["config"]["files"], ["config/settings.yml"])

    def test_js_paths_stay_web_without_node_cli_context(self) -> None:
        classified = classify(["app.js"])

        self.assertEqual(classified["web"]["files"], ["app.js"])
        self.assertNotIn("node_cli", classified)

    def test_node_cli_context_classifies_js_as_cli_runtime(self) -> None:
        classified = classify(["src/cli.js"], {"node_cli": True})

        self.assertEqual(classified["node_cli"]["files"], ["src/cli.js"])
        self.assertIn("Node test/build", " ".join(classified["node_cli"]["commands"]))
        self.assertNotIn("web", classified)

    def test_python_cli_context_classifies_entrypoint_changes(self) -> None:
        classified = classify(["pyproject.toml", "src/demo/cli.py", "src/demo/core.py"], {"python_cli": True})

        self.assertEqual(classified["python_cli"]["files"], ["pyproject.toml", "src/demo/cli.py", "src/demo/core.py"])
        self.assertIn("pip install -e", " ".join(classified["python_cli"]["commands"]))
        self.assertIn("console script", " ".join(classified["python_cli"]["commands"]))
        self.assertNotIn("config", classified)
        self.assertNotIn("python", classified)

    def test_repo_context_detects_node_cli_package(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = pathlib.Path(raw)
            (repo / "package.json").write_text(
                json.dumps(
                    {
                        "bin": {"demo": "bin/demo.js"},
                        "scripts": {"test": "node --test", "build": "node scripts/build.js"},
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(repo_context(repo), {"node_cli": True, "python_cli": False})

    def test_repo_context_detects_python_cli_pyproject(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = pathlib.Path(raw)
            (repo / "pyproject.toml").write_text(
                """[project]
name = "demo"

[project.scripts]
demo = "demo.cli:main"
""",
                encoding="utf-8",
            )

            self.assertTrue(has_pyproject_scripts((repo / "pyproject.toml").read_text(encoding="utf-8")))
            self.assertEqual(repo_context(repo), {"node_cli": False, "python_cli": True})

    def test_matching_path_rule_handles_windows_separators_and_case(self) -> None:
        workflow_rule = matching_path_rule(".GITHUB\\workflows\\CI.YML")
        action_rule = matching_path_rule("ACTION.YAML")

        self.assertEqual(workflow_rule[0] if workflow_rule else None, "github_workflow")
        self.assertEqual(action_rule[0] if action_rule else None, "github_action")

    def test_render_text_contains_files_and_commands(self) -> None:
        checklist = render_text(classify(["verify_by_change.py", "README.md"]))

        self.assertIn("# Verification Checklist", checklist)
        self.assertIn("## Python", checklist)
        self.assertIn("`verify_by_change.py`", checklist)
        self.assertIn("python3 -m py_compile", checklist)
        self.assertIn("## Docs", checklist)

    def test_render_text_humanizes_underscore_category_names(self) -> None:
        checklist = render_text(classify(["action.yml"]))

        self.assertIn("## Github Action", checklist)

    def test_render_text_handles_empty_changes_explicitly(self) -> None:
        checklist = render_text({})

        self.assertIn("No changed files detected.", checklist)
        self.assertIn("Confirm the target ref", checklist)

    def test_json_envelope_includes_schema_source_and_empty_state(self) -> None:
        payload = json_envelope(
            ["README.md"],
            classify(["README.md"]),
            {
                "type": "explicit_paths",
                "repo": None,
                "base": None,
                "staged": False,
                "include_working_tree": False,
            },
        )

        self.assertEqual(payload["schema_version"], "verify-by-change.v1")
        self.assertEqual(payload["changed_files"], ["README.md"])
        self.assertFalse(payload["empty"])
        self.assertEqual(payload["source"]["type"], "explicit_paths")
        self.assertIn("docs", payload["categories"])

    def test_parse_status_paths_handles_renames(self) -> None:
        output = " M README.md\nA  script.sh\nR  old.txt -> new.txt\n?? scratch.js\n"

        self.assertEqual(
            parse_status_paths(output),
            ["README.md", "script.sh", "new.txt", "scratch.js"],
        )

    def test_unique_ordered_keeps_first_path_occurrence(self) -> None:
        self.assertEqual(unique_ordered(["README.md", "app.js", "README.md"]), ["README.md", "app.js"])

    def test_repo_changed_files_without_base_includes_staged_unstaged_and_untracked(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = pathlib.Path(raw)
            run("git", "init", cwd=repo)
            run("git", "config", "user.name", "Test User", cwd=repo)
            run("git", "config", "user.email", "test@example.com", cwd=repo)
            (repo / "README.md").write_text("initial\n", encoding="utf-8")
            run("git", "add", "README.md", cwd=repo)
            run("git", "commit", "-m", "initial", cwd=repo)

            (repo / "README.md").write_text("changed\n", encoding="utf-8")
            (repo / "script.sh").write_text("echo ok\n", encoding="utf-8")
            run("git", "add", "script.sh", cwd=repo)
            (repo / "scratch.js").write_text("console.log('ok')\n", encoding="utf-8")

            self.assertEqual(
                sorted(repo_changed_files(repo, base=None)),
                ["README.md", "scratch.js", "script.sh"],
            )

    def test_repo_changed_files_staged_only(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = pathlib.Path(raw)
            run("git", "init", cwd=repo)
            run("git", "config", "user.name", "Test User", cwd=repo)
            run("git", "config", "user.email", "test@example.com", cwd=repo)
            (repo / "README.md").write_text("initial\n", encoding="utf-8")
            run("git", "add", "README.md", cwd=repo)
            run("git", "commit", "-m", "initial", cwd=repo)

            (repo / "README.md").write_text("changed\n", encoding="utf-8")
            (repo / "script.sh").write_text("echo ok\n", encoding="utf-8")
            run("git", "add", "script.sh", cwd=repo)

            self.assertEqual(repo_changed_files(repo, base=None, staged=True), ["script.sh"])

    def test_repo_changed_files_can_include_base_diff_and_working_tree(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = pathlib.Path(raw)
            run("git", "init", cwd=repo)
            run("git", "config", "user.name", "Test User", cwd=repo)
            run("git", "config", "user.email", "test@example.com", cwd=repo)
            (repo / "README.md").write_text("initial\n", encoding="utf-8")
            run("git", "add", "README.md", cwd=repo)
            run("git", "commit", "-m", "initial", cwd=repo)
            run("git", "tag", "base", cwd=repo)

            (repo / "README.md").write_text("committed change\n", encoding="utf-8")
            run("git", "add", "README.md", cwd=repo)
            run("git", "commit", "-m", "docs change", cwd=repo)
            (repo / "package.json").write_text('{"scripts":{"test":"node --test"}}\n', encoding="utf-8")
            (repo / "scratch.py").write_text("print('draft')\n", encoding="utf-8")

            self.assertEqual(
                repo_changed_files(repo, base="base", include_working_tree=True),
                ["README.md", "package.json", "scratch.py"],
            )

    def test_review_packet_changed_files_extracts_changed_file_bullets(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            packet = pathlib.Path(raw) / "review-packet.md"
            packet.write_text(
                """# Review Packet

Repo: `/tmp/repo`
Base: `working tree`

## Changed Files

- `README.md`
- `src/app.py`
- `README.md`

## Review Map

### Product and docs

- `README.md`
""",
                encoding="utf-8",
            )

            self.assertEqual(review_packet_changed_files(packet), ["README.md", "src/app.py"])

    def test_review_packet_changed_files_handles_empty_packet_changes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            packet = pathlib.Path(raw) / "review-packet.md"
            packet.write_text(
                """# Review Packet

## Changed Files

- No changed files detected.

## Diff
""",
                encoding="utf-8",
            )

            self.assertEqual(review_packet_changed_files(packet), [])

    def test_review_packet_readiness_extracts_contract_summary(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            packet = pathlib.Path(raw) / "review-packet.md"
            packet.write_text(
                """# Review Packet

## Changed Files

- `README.md`

## Repo Readiness

Source: `/tmp/readiness-contract.json`

- Contract: `repo-flightcheck.agent-contract.v1`
- Ready: `false`
- Score: `96/100`
- Threshold: `80`
- Stack: `node`
- Summary: `1` required blockers, `2` recommendations, `0` critical failures.

Required before agent:

- `WARN` Working tree: Working tree has changed paths.

## Diff
""",
                encoding="utf-8",
            )

            readiness = review_packet_readiness(packet)

            self.assertIsNotNone(readiness)
            self.assertEqual(readiness["contract"], "repo-flightcheck.agent-contract.v1")
            self.assertEqual(readiness["ready"], False)
            self.assertEqual(readiness["score"], 96)
            self.assertEqual(readiness["points_possible"], 100)
            self.assertEqual(readiness["threshold"], 80)
            self.assertEqual(readiness["stack"], "node")
            self.assertEqual(readiness["required_blockers"], 1)
            self.assertEqual(readiness["recommendations"], 2)
            self.assertEqual(readiness["critical_failures"], 0)

    def test_review_packet_readiness_extracts_full_report_summary(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            packet = pathlib.Path(raw) / "review-packet.md"
            packet.write_text(
                """# Review Packet

## Repo Readiness

Source: `/tmp/readiness.json`

- Score: `84/100`
- Stack: `python`
- Summary: `10` passed, `2` warnings, `1` failed, `1` critical failures.

Attention checks:

- `FAIL` Verification command: No reliable verification command detected.

## Diff
""",
                encoding="utf-8",
            )

            readiness = review_packet_readiness(packet)

            self.assertIsNotNone(readiness)
            self.assertIsNone(readiness["contract"])
            self.assertIsNone(readiness["ready"])
            self.assertEqual(readiness["score"], 84)
            self.assertEqual(readiness["points_possible"], 100)
            self.assertEqual(readiness["stack"], "python")
            self.assertEqual(readiness["passed"], 10)
            self.assertEqual(readiness["warnings"], 2)
            self.assertEqual(readiness["failed"], 1)
            self.assertEqual(readiness["critical_failures"], 1)


class CliTests(unittest.TestCase):
    def test_cli_json_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            out = pathlib.Path(raw) / "checks.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "verify_by_change.py"),
                    "README.md",
                    "app.js",
                    "--json",
                    "--output",
                    str(out),
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            self.assertIn("Wrote verification checklist", result.stdout)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["docs"]["files"], ["README.md"])
            self.assertEqual(payload["web"]["files"], ["app.js"])

    def test_cli_empty_json_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = pathlib.Path(raw) / "repo"
            repo.mkdir()
            run("git", "init", cwd=repo)
            run("git", "config", "user.name", "Test User", cwd=repo)
            run("git", "config", "user.email", "test@example.com", cwd=repo)
            (repo / "README.md").write_text("initial\n", encoding="utf-8")
            run("git", "add", "README.md", cwd=repo)
            run("git", "commit", "-m", "initial", cwd=repo)
            out = pathlib.Path(raw) / "checks.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "verify_by_change.py"),
                    "--repo",
                    str(repo),
                    "--json",
                    "--output",
                    str(out),
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            self.assertIn("Wrote verification checklist", result.stdout)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8")), {})

    def test_cli_json_envelope_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            out = pathlib.Path(raw) / "checks-envelope.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "verify_by_change.py"),
                    "README.md",
                    "app.js",
                    "--json-envelope",
                    "--output",
                    str(out),
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            self.assertIn("Wrote verification checklist", result.stdout)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "verify-by-change.v1")
            self.assertEqual(payload["source"]["type"], "explicit_paths")
            self.assertEqual(payload["changed_files"], ["README.md", "app.js"])
            self.assertFalse(payload["empty"])
            self.assertEqual(payload["categories"]["docs"]["files"], ["README.md"])
            self.assertEqual(payload["categories"]["web"]["files"], ["app.js"])

    def test_cli_json_envelope_marks_empty_repo_scan(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = pathlib.Path(raw) / "repo"
            repo.mkdir()
            run("git", "init", cwd=repo)
            run("git", "config", "user.name", "Test User", cwd=repo)
            run("git", "config", "user.email", "test@example.com", cwd=repo)
            (repo / "README.md").write_text("initial\n", encoding="utf-8")
            run("git", "add", "README.md", cwd=repo)
            run("git", "commit", "-m", "initial", cwd=repo)

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "verify_by_change.py"),
                    "--repo",
                    str(repo),
                    "--json-envelope",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(result.stdout)
            self.assertTrue(payload["empty"])
            self.assertEqual(payload["changed_files"], [])
            self.assertEqual(payload["categories"], {})
            self.assertEqual(payload["source"]["type"], "git")
            self.assertEqual(pathlib.Path(payload["source"]["repo"]).resolve(), repo.resolve())

    def test_cli_can_include_base_diff_and_working_tree(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = pathlib.Path(raw)
            run("git", "init", cwd=repo)
            run("git", "config", "user.name", "Test User", cwd=repo)
            run("git", "config", "user.email", "test@example.com", cwd=repo)
            (repo / "README.md").write_text("initial\n", encoding="utf-8")
            run("git", "add", "README.md", cwd=repo)
            run("git", "commit", "-m", "initial", cwd=repo)
            run("git", "tag", "base", cwd=repo)
            (repo / "README.md").write_text("committed change\n", encoding="utf-8")
            run("git", "add", "README.md", cwd=repo)
            run("git", "commit", "-m", "docs change", cwd=repo)
            (repo / "scratch.py").write_text("print('draft')\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "verify_by_change.py"),
                    "--repo",
                    str(repo),
                    "--base",
                    "base",
                    "--include-working-tree",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            self.assertIn("`README.md`", result.stdout)
            self.assertIn("`scratch.py`", result.stdout)

    def test_cli_repo_scan_uses_node_cli_context(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = pathlib.Path(raw)
            run("git", "init", cwd=repo)
            run("git", "config", "user.name", "Test User", cwd=repo)
            run("git", "config", "user.email", "test@example.com", cwd=repo)
            (repo / "package.json").write_text(
                json.dumps(
                    {
                        "bin": {"demo": "bin/demo.js"},
                        "scripts": {"test": "node --test", "build": "node scripts/build.js"},
                    }
                ),
                encoding="utf-8",
            )
            run("git", "add", "package.json", cwd=repo)
            run("git", "commit", "-m", "initial", cwd=repo)
            (repo / "src").mkdir()
            (repo / "src" / "cli.js").write_text("console.log('ok')\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "verify_by_change.py"),
                    "--repo",
                    str(repo),
                    "--json",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual(payload["node_cli"]["files"], ["src/cli.js"])
            self.assertIn("Node test/build", " ".join(payload["node_cli"]["commands"]))
            self.assertNotIn("web", payload)

    def test_cli_repo_scan_uses_python_cli_context(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = pathlib.Path(raw)
            run("git", "init", cwd=repo)
            run("git", "config", "user.name", "Test User", cwd=repo)
            run("git", "config", "user.email", "test@example.com", cwd=repo)
            (repo / "pyproject.toml").write_text(
                """[project]
name = "demo"

[project.scripts]
demo = "demo.cli:main"
""",
                encoding="utf-8",
            )
            run("git", "add", "pyproject.toml", cwd=repo)
            run("git", "commit", "-m", "initial", cwd=repo)
            (repo / "src" / "demo").mkdir(parents=True)
            (repo / "src" / "demo" / "cli.py").write_text("def main():\n    return 0\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "verify_by_change.py"),
                    "--repo",
                    str(repo),
                    "--json",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual(payload["python_cli"]["files"], ["src/demo/cli.py"])
            self.assertIn("pip install -e", " ".join(payload["python_cli"]["commands"]))
            self.assertNotIn("python", payload)

    def test_cli_can_read_paths_from_review_packet(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            packet = pathlib.Path(raw) / "review-packet.md"
            packet.write_text(
                """# Review Packet

Repo: `/tmp/repo`
Base: `working tree`

## Changed Files

- `README.md`
- `action.yml`

## Review Map
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "verify_by_change.py"),
                    "--review-packet",
                    str(packet),
                    "--json-envelope",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual(payload["source"]["type"], "review_packet")
            self.assertEqual(payload["changed_files"], ["README.md", "action.yml"])
            self.assertEqual(payload["categories"]["docs"]["files"], ["README.md"])
            self.assertEqual(payload["categories"]["github_action"]["files"], ["action.yml"])
            self.assertNotIn("repo_readiness", payload)

    def test_cli_review_packet_uses_packet_repo_context(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = pathlib.Path(raw) / "repo"
            repo.mkdir()
            (repo / "package.json").write_text(
                json.dumps(
                    {
                        "bin": {"demo": "bin/demo.js"},
                        "scripts": {"test": "node --test", "lint": "node scripts/lint.js"},
                    }
                ),
                encoding="utf-8",
            )
            packet = pathlib.Path(raw) / "review-packet.md"
            packet.write_text(
                f"""# Review Packet

Repo: `{repo}`
Base: `working tree`

## Changed Files

- `src/cli.js`

## Review Map
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "verify_by_change.py"),
                    "--review-packet",
                    str(packet),
                    "--json-envelope",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual(pathlib.Path(payload["source"]["repo"]).resolve(), repo.resolve())
            self.assertEqual(payload["changed_files"], ["src/cli.js"])
            self.assertEqual(payload["categories"]["node_cli"]["files"], ["src/cli.js"])
            self.assertNotIn("web", payload["categories"])

    def test_cli_json_envelope_includes_review_packet_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            packet = pathlib.Path(raw) / "review-packet.md"
            packet.write_text(
                """# Review Packet

## Changed Files

- `README.md`

## Repo Readiness

Source: `/tmp/readiness-contract.json`

- Contract: `repo-flightcheck.agent-contract.v1`
- Ready: `true`
- Score: `100/100`
- Threshold: `80`
- Stack: `node`
- Summary: `0` required blockers, `0` recommendations, `0` critical failures.

## Diff
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "verify_by_change.py"),
                    "--review-packet",
                    str(packet),
                    "--json-envelope",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual(payload["changed_files"], ["README.md"])
            self.assertEqual(payload["repo_readiness"]["contract"], "repo-flightcheck.agent-contract.v1")
            self.assertEqual(payload["repo_readiness"]["ready"], True)
            self.assertEqual(payload["repo_readiness"]["score"], 100)
            self.assertEqual(payload["repo_readiness"]["required_blockers"], 0)

    def test_cli_rejects_review_packet_with_other_sources(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            packet = pathlib.Path(raw) / "review-packet.md"
            packet.write_text("# Review Packet\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "verify_by_change.py"),
                    "README.md",
                    "--review-packet",
                    str(packet),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Use --review-packet by itself", result.stderr)

    def test_cli_reports_missing_review_packet_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            missing = pathlib.Path(raw) / "missing.md"

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "verify_by_change.py"),
                    "--review-packet",
                    str(missing),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Review packet not found", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_cli_fail_on_empty_clean_repo(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = pathlib.Path(raw)
            run("git", "init", cwd=repo)
            run("git", "config", "user.name", "Test User", cwd=repo)
            run("git", "config", "user.email", "test@example.com", cwd=repo)
            (repo / "README.md").write_text("initial\n", encoding="utf-8")
            run("git", "add", "README.md", cwd=repo)
            run("git", "commit", "-m", "initial", cwd=repo)

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "verify_by_change.py"),
                    "--repo",
                    str(repo),
                    "--fail-on-empty",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("No changed files detected.", result.stdout)


if __name__ == "__main__":
    unittest.main()
