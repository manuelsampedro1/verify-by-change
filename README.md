# verify-by-change

Suggest verification steps from the files you changed.

The problem: after a Codex edit, the next question is usually "what should I run now?" This repo gives a small local CLI that maps changed paths to a verification checklist so the final answer is less hand-wavy.

## What It Does

- Reads changed files from a git repo or from explicit file paths.
- Detects staged, unstaged, and untracked files when scanning a working tree.
- Can combine a base-ref diff with current working-tree changes when a Codex run has both committed and uncommitted edits.
- Buckets the change into simple categories such as docs, shell, Python, JS/TS, config, and Swift.
- Prints a compact checklist with the most likely verification commands.
- Supports JSON output for automation.
- Writes output to a file when a handoff artifact is needed.
- Prints an explicit empty-change message, with `--fail-on-empty` for CI guards.

## Why This Exists

I wanted a default verification layer that is small enough to trust and easy to customize per repo. This is useful in Codex sessions where fast, honest verification matters more than generic advice.

## Stack

- Python 3.11+
- Standard library only

## Quick Start

Against the current repo:

```sh
python3 verify_by_change.py --repo /path/to/repo --base origin/main
```

With explicit files:

```sh
python3 verify_by_change.py README.md scripts/deploy.sh
```

JSON mode:

```sh
python3 verify_by_change.py --repo . --json
```

Staged-only check:

```sh
python3 verify_by_change.py --repo . --staged
```

Base diff plus current working tree:

```sh
python3 verify_by_change.py --repo . --base origin/main --include-working-tree
```

Fail when automation expected changed files:

```sh
python3 verify_by_change.py --repo . --fail-on-empty
```

Write an artifact:

```sh
python3 verify_by_change.py --repo . --output /tmp/verification-checklist.md
python3 verify_by_change.py --repo . --json --output /tmp/verification-checklist.json
```

## Status

Working v1 with built-in rules. It is intentionally small and conservative.

## Verification

Run from this repo:

```sh
python3 -m py_compile verify_by_change.py
python3 -m unittest discover -s tests
python3 verify_by_change.py verify_by_change.py README.md >/tmp/verify-output.txt
python3 verify_by_change.py --repo . --staged --json --output /tmp/verify-staged.json
python3 verify_by_change.py --repo . --base HEAD --include-working-tree >/tmp/verify-base-plus-working-tree.txt
python3 verify_by_change.py --repo . --fail-on-empty >/tmp/verify-empty-check.txt || test $? -eq 2
test -s /tmp/verify-output.txt
```

## Files

- `verify_by_change.py`: CLI entrypoint.
- `tests/`: working-tree detection, renderer, and CLI coverage.
- `DECISIONS.md`: repo design notes.
