# Codex CLI entry point

Read and follow `rules/agent-workflow.md`; it is the shared source of truth for Claude Code and Codex CLI. Do not implement a raw backlog item before Task Analysis has produced or refreshed `docs/tasks/<TASK_ID>.md`.

## Codex execution mapping

Codex does not copy Claude's subagent syntax. It performs the same responsibilities as explicit workflow stages:

- **Task Analysis:** follow the shared contract and write only `docs/tasks/<TASK_ID>.md`. Read backlog data only with `python backlog.py`.
- **Visual sample:** when a task creates or changes a graph, screen, report layout, or other visual output, also create `docs/tasks/<TASK_ID>.sample.png` from representative synthetic data and embed it in the task guide. The sample is a design/verification reference, not production evidence.
- **Implementation:** verify the selected task is `in_progress`, implement only the task-context scope, and run tests.
- **Adversarial Review:** after changing the task to `review`, review without editing implementation and write only `docs/tasks/<TASK_ID>.review.md`.
- **Completion:** apply the exact PASS / NEEDS_FIX / HUMAN_REVIEW transitions in the shared workflow. Never mark a task done on self-assertion alone.

If Codex hooks are unavailable, execute the same checks manually before every mutation and status transition. Missing automation does not weaken the rule.

Business logic lives in `hooks/`; `.codex/hooks.json` is only a runtime adapter.
