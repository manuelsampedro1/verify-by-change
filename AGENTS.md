# AGENTS.md

## Purpose

`verify-by-change` is a small Python CLI that turns changed file paths into a practical verification checklist for Codex and human review handoffs.

## Constraints

- Keep the CLI standard-library only unless a dependency removes clear operational risk.
- Preserve backward-compatible output for `--json`; use `--json-envelope` for richer automation metadata.
- Prefer explicit, reviewable rules over broad inference that can create noisy checklists.
- Do not add network calls, telemetry, secrets, or repo-specific assumptions to the default CLI.

## Verification

Run these before closing a change:

```sh
make test
make build
make lint
python3 verify_by_change.py verify_by_change.py README.md
```

For automation changes, also verify:

```sh
python3 verify_by_change.py verify_by_change.py README.md --json-envelope
python3 verify_by_change.py --repo . --base HEAD --include-working-tree
```
