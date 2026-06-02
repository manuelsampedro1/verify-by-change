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
