# Claude Code entry point

공통 작업 규칙은 [`rules/agent-workflow.md`](./rules/agent-workflow.md)를 따릅니다.
Claude Code 전용 실행 방법은 `.claude/agents/`와 `.claude/settings.json`에 있습니다.

- Task Analysis: `.claude/agents/task-briefer.md`
- Adversarial Review: `.claude/agents/adversarial-reviewer.md`
- Hooks: `.claude/settings.json`에서 공통 `hooks/` 스크립트를 호출

Claude 전용 파일은 공통 규칙을 재정의하지 않습니다. 충돌하면 `rules/agent-workflow.md`가 우선합니다.
