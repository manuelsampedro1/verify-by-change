# verify-by-change

Suggest verification steps from the files you changed.

The problem: after a Codex edit, the next question is usually "what should I run now?" This repo gives a small local CLI that maps changed paths to a verification checklist so the final answer is less hand-wavy.

## What It Does

- Reads changed files from a git repo or from explicit file paths.
- Can read changed files from a `codex-review-packet` Markdown handoff.
- When reading a review packet, can carry its `## Repo Readiness` summary into the JSON envelope.
- Detects staged, unstaged, and untracked files when scanning a working tree.
- Can combine a base-ref diff with current working-tree changes when a Codex run has both committed and uncommitted edits.
- Buckets the change into simple categories such as docs, shell, Python, Python CLI context, web JS/TS, Node CLI context, config, Swift, GitHub Actions, GitHub workflows, secret material, and security-sensitive authorization or deploy paths.
- Prints a compact checklist with the most likely verification commands.
- Supports JSON output for automation.
- Supports an optional JSON envelope with schema, source, changed files, empty state, and categories.
- Writes output to a file when a handoff artifact is needed.
- Prints an explicit empty-change message, with `--fail-on-empty` for CI guards.

## Why This Exists

I wanted a default verification layer that is small enough to trust and easy to customize per repo. This is useful in Codex sessions where fast, honest verification matters more than generic advice.

## Stack

- Python 3.11+
- Standard library only

## Quick Start

Install locally when you want the `verify-by-change` command on your PATH:

```sh
python3 -m pip install -e .
```

Against the current repo:

```sh
python3 verify_by_change.py --repo /path/to/repo --base origin/main
```

With explicit files:

```sh
python3 verify_by_change.py README.md scripts/deploy.sh
```

GitHub Action and workflow changes get path-specific guidance:

```sh
python3 verify_by_change.py action.yml .github/workflows/deploy-gate.yml
```

Node CLI packages with `bin` plus test/build/lint/check scripts get CLI/runtime guidance instead of web UI guidance:

```sh
python3 verify_by_change.py --repo /path/to/node-cli --json
```

Python CLI packages with `pyproject.toml` `[project.scripts]` get install-and-smoke guidance when entrypoint paths change:

```sh
python3 verify_by_change.py --repo /path/to/python-cli --json
```

Secret or authorization-sensitive paths get negative-path and secret-hygiene guidance:

```sh
python3 verify_by_change.py .env permission_protocol/client.py scripts/deploy.sh
```

JSON mode:

```sh
python3 verify_by_change.py --repo . --json
```

JSON envelope for automation:

```sh
python3 verify_by_change.py --repo . --json-envelope --output /tmp/verification-checklist.json
```

Staged-only check:

```sh
python3 verify_by_change.py --repo . --staged
```

Base diff plus current working tree:

```sh
python3 verify_by_change.py --repo . --base origin/main --include-working-tree
```

From a generated review packet:

```sh
python3 /path/to/codex-review-packet/codex_review_packet.py --repo . --output /tmp/review-packet.md
python3 verify_by_change.py --review-packet /tmp/review-packet.md
python3 verify_by_change.py --review-packet /tmp/review-packet.md --json-envelope
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

## Examples

- `examples/verification-envelope.json`: stable JSON envelope shape for automation handoffs.

## Verification

Run from this repo:

```sh
make test
make build
make lint
python3 -m py_compile verify_by_change.py
python3 -m unittest discover -s tests
python3 verify_by_change.py verify_by_change.py README.md >/tmp/verify-output.txt
python3 verify_by_change.py action.yml .github/workflows/deploy-gate.yml >/tmp/verify-action-output.txt
python3 /Users/manuelsampedro/Documents/Codex/2026-05-24/flagships/codex-review-packet/codex_review_packet.py --repo . --output /tmp/verify-review-packet.md
python3 verify_by_change.py --review-packet /tmp/verify-review-packet.md >/tmp/verify-from-review-packet.txt
python3 verify_by_change.py --review-packet /tmp/verify-review-packet.md --json-envelope >/tmp/verify-from-review-packet-envelope.json
python3 verify_by_change.py --repo . --staged --json --output /tmp/verify-staged.json
python3 verify_by_change.py verify_by_change.py README.md --json-envelope >/tmp/verify-envelope.json
python3 verify_by_change.py --repo . --base HEAD --include-working-tree >/tmp/verify-base-plus-working-tree.txt
python3 verify_by_change.py --repo . --fail-on-empty >/tmp/verify-empty-check.txt || test $? -eq 2
test -s /tmp/verify-output.txt
test -s /tmp/verify-action-output.txt
test -s /tmp/verify-from-review-packet.txt
test -s /tmp/verify-from-review-packet-envelope.json
```

## Files

- `verify_by_change.py`: CLI entrypoint.
- `tests/`: working-tree detection, renderer, and CLI coverage.
- `examples/`: stable output examples for review and automation.
- `Makefile`: standard local verification targets.
- `pyproject.toml`: package metadata and CLI entrypoint.
- `AGENTS.md`: agent-facing maintenance contract.
- `DECISIONS.md`: repo design notes.
