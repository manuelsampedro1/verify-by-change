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
