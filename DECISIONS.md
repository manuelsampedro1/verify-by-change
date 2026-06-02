# Decisions

## Conservative Rules

Use a small built-in mapping instead of trying to infer every framework.

Rationale:

- Better to suggest a few honest checks than a long noisy list.
- Repo owners can fork or edit the script easily.
- This keeps the tool readable during code review.

## Checklist Before Automation

Default output is a human-readable checklist. JSON is optional.

Rationale:

- The first user is the engineer closing a Codex task.
- The second user is automation that wants structured output.
- That order keeps the default UX practical.

## Working Tree Detection

When `--repo` is used without a base ref, inspect Git status instead of only `git diff`.

Rationale:

- Codex handoffs often include staged files, unstaged edits, and new files at the same time.
- A verification checklist is weaker if it silently misses untracked files.
- `--staged` remains available when a reviewer wants the narrower index-only view.

## Explicit Empty Diffs

Say when no changed files were detected, and let CI opt into failure with `--fail-on-empty`.

Rationale:

- An empty checklist can look like a rendering bug or a skipped scan.
- Local users often just need the clarification, not a failing command.
- Automation can use exit code `2` when a diff was expected but no files were found.

## Base Diff Plus Working Tree

Keep `--base` focused on committed changes by default, but allow `--include-working-tree` to merge in staged, unstaged, and untracked files.

Rationale:

- Some review flows want only the committed PR diff against a base ref.
- Codex sessions often have both committed follow-ups and local draft edits in the same repo.
- Making the merged mode explicit avoids surprising CI users while still supporting full-session verification.

## JSON Envelope for Automation

Keep legacy `--json` as the category map, and add `--json-envelope` for automation that needs metadata.

Rationale:

- Existing callers may expect the compact category object.
- Gates and downstream tools need schema, source, changed files, and empty-state metadata.
- Making the richer shape opt-in avoids a breaking output change while still supporting machine-readable handoffs.

## Repo Readiness Contract

Expose standard verification targets, package metadata, examples, license, and an agent contract even though the implementation remains a single-file CLI.

Rationale:

- A small repo still needs fast local reproduction for reviewers and automation.
- Standard `make test`, `make build`, and `make lint` commands make CI parity obvious.
- Keeping metadata lightweight improves trust without adding runtime dependencies or fake complexity.

## Path-Specific Agent Safety Checks

Classify `action.yml`, `action.yaml`, and `.github/workflows/*.{yml,yaml}` before generic extension-based config rules.

Rationale:

- GitHub Action and workflow changes often affect deploy gates, permissions, secrets, and fail-open behavior.
- Treating them as generic YAML hides the exact review questions that matter for agent safety.
- Path-specific rules keep the tool small while making high-risk automation changes easier to verify honestly.

## Review Packet as a Path Source

Allow `--review-packet` to read changed files from a `codex-review-packet` Markdown handoff.

Rationale:

- Reviewers sometimes have the packet artifact but not the original repo state.
- Reusing the packet's changed-file section keeps verification guidance aligned with the review handoff.
- The packet remains only a source of paths; it is not treated as proof that checks were executed.

## Task Contract Metadata in Envelopes

When `--review-packet --json-envelope` sees a rendered `## Task Contract` section, preserve the contract status, source, required-section count, missing sections, and placeholder markers in the envelope.

Rationale:

- Verification guidance is stronger when downstream tools can see whether it was planned against a complete task boundary.
- The task contract is context metadata, not proof that checks ran, so it belongs beside `repo_readiness` in the envelope.
- Keeping it optional avoids breaking existing Markdown output or callers that only need changed-file categories.

## Secret and Permission Paths Before Generic Extensions

Classify secret material and authorization, approval, permission, receipt, guard, and deploy paths before generic language or config rules.

Rationale:

- A changed `.env`, private key fixture, approval handler, or deploy guard needs a different closeout than a generic Python, shell, or docs edit.
- Agent closeouts should include negative-path and leakage checks for permission-sensitive work.
- The rule remains path-based and conservative; it raises review questions without pretending to inspect diff contents.
