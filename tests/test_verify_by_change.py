from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from verify_by_change import classify, parse_status_paths, render_text, repo_changed_files, unique_ordered  # noqa: E402


def run(*args: str, cwd: pathlib.Path) -> None:
    subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=True)


class VerifyByChangeTests(unittest.TestCase):
    def test_classifies_known_extensions_and_uncategorized_files(self) -> None:
        classified = classify(["README.md", "scripts/deploy.sh", ".github/workflows/ci.yml", "Sources/App.swift", "asset.bin"])

        self.assertEqual(classified["docs"]["files"], ["README.md"])
        self.assertEqual(classified["shell"]["files"], ["scripts/deploy.sh"])
        self.assertEqual(classified["config"]["files"], [".github/workflows/ci.yml"])
        self.assertEqual(classified["swift"]["files"], ["Sources/App.swift"])
        self.assertEqual(classified["uncategorized"]["files"], ["asset.bin"])

    def test_render_text_contains_files_and_commands(self) -> None:
        checklist = render_text(classify(["verify_by_change.py", "README.md"]))

        self.assertIn("# Verification Checklist", checklist)
        self.assertIn("## Python", checklist)
        self.assertIn("`verify_by_change.py`", checklist)
        self.assertIn("python3 -m py_compile", checklist)
        self.assertIn("## Docs", checklist)

    def test_render_text_handles_empty_changes_explicitly(self) -> None:
        checklist = render_text({})

        self.assertIn("No changed files detected.", checklist)
        self.assertIn("Confirm the target ref", checklist)

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
