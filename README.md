# verify-by-change

Suggest verification steps from the files you changed.

The problem: after a Codex edit, the next question is usually "what should I run now?" This repo gives a small local CLI that maps changed paths to a verification checklist so the final answer is less hand-wavy.

## What It Does

- Reads changed files from a git repo or from explicit file paths.
- Buckets the change into simple categories such as docs, shell, Python, JS/TS, and Swift.
- Prints a compact checklist with the most likely verification commands.
- Supports JSON output for automation.

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

## Status

Working v1 with built-in rules. It is intentionally small and conservative.

## Verification

Run from this repo:

```sh
python3 -m py_compile verify_by_change.py
python3 verify_by_change.py verify_by_change.py README.md >/tmp/verify-output.txt
test -s /tmp/verify-output.txt
```

## Files

- `verify_by_change.py`: CLI entrypoint.
- `DECISIONS.md`: repo design notes.

