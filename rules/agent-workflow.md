# Shared agent workflow

This file is the source of truth for Claude Code and Codex CLI. Product-specific entry points may explain how to invoke a step, but must not change this workflow.

## Shared artifacts

- Requirements: `problem.md`
- Backlog: `backlog.json`, accessed only through `python backlog.py`
- Task context: `docs/tasks/<TASK_ID>.md`
- Review record: `docs/tasks/<TASK_ID>.review.md`
- Guards and quality gates: `hooks/`

Do not duplicate these artifacts, scripts, tests, or application code for a specific agent runtime.

## Workflow

1. Select a task with the user. If none was named, show `python backlog.py next` and let the user choose. Never choose a backlog item implicitly.
2. Run Task Analysis before implementation. Read the task through `python backlog.py show <TASK_ID>`, inspect dependencies and `problem.md`, then create or refresh `docs/tasks/<TASK_ID>.md`.
3. Change the selected task to `in_progress`. Project-file mutation is forbidden unless a task is `in_progress`. Prefer only one active task.
4. Implement only the recorded scope and run proportional tests. Add out-of-scope work as a separate backlog task.
5. Change the task to `review` and run Adversarial Review. The reviewer reads the task, context, requirements, diff, and test output; it writes only `docs/tasks/<TASK_ID>.review.md` and never fixes implementation.
6. Apply the verdict:
   - `PASS` -> `done`
   - `NEEDS_FIX` -> `in_progress`, fix, test, return to `review`, review again
   - `HUMAN_REVIEW` -> `human_required` and stop for a human decision

Any implementation change after PASS invalidates that PASS. Only a current PASS may transition to `done`.

## Task Analysis contract

Record task and dependency status, scope, non-goals, acceptance criteria, relevant requirements, existing/expected files, tests, edge cases, and line limits. Mark unknown facts as unknown. Task Analysis may only write the task context.

## Adversarial Review contract

Check every acceptance criterion and relevant empty, missing, malformed, boundary, encoding, numerical, performance, and security case. Each finding includes severity, `file:line`, a reproducible failure, and fix direction. End with exactly one of:

```text
Verdict: PASS
Verdict: NEEDS_FIX
Verdict: HUMAN_REVIEW
```

Use `HUMAN_REVIEW` only for a genuine product, policy, or irreversible decision that repository evidence cannot resolve.

## Guard behavior

- Never read or edit `backlog.json` directly; use the CLI.
- `hooks/task_guard.py` enforces the `in_progress` mutation rule.
- `hooks/backlog_sync.py` rejects `done` without a fresh PASS review, then runs lint/build and commits only after all gates pass.
- Work on `dev`, never directly on `main` or `master`.
