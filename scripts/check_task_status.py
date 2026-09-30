#!/usr/bin/env python3
"""공용 Active Task Guard — 표준 라이브러리만 사용, Claude/Codex 어디서나 동일하게 동작.

`.agent/active_task`에 적힌 Task ID를 backlog.json에서 찾아 상태가
`in_progress`일 때만 프로젝트 파일 수정을 허용한다. Claude Code에서는
`hooks/task_guard.py`가 이 스크립트를 그대로 호출하고, Codex 등 PreToolUse가
없는 도구에서는 파일을 고치기 전에 사람 또는 에이전트가 직접 이 스크립트를
실행해서 확인한다.

사용법:
  python scripts/check_task_status.py [건드릴 파일 경로 ...]
  (경로를 안 주면 "지금 아무 파일이나 고쳐도 되는가"를 확인한다)

종료 코드: 0 = ALLOW, 0이 아니면 = BLOCK (이유는 stderr에 출력).
기본 정책은 "확실히 허용되는 경우만 ALLOW" — active task가 없거나
backlog를 읽을 수 없거나 Task ID를 못 찾으면 전부 BLOCK이다.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hooks"))
from common import (
    config,
    match_glob,
)

ACTIVE_TASK_FILE = os.path.join(ROOT, ".agent", "active_task")
BACKLOG_FILE = os.path.join(ROOT, "backlog.json")

# Workflow 통제용 파일만 예외로 허용한다 — Application Source Code로 확장하지 않는다.
DEFAULT_EXEMPT = [
    ".agent/**", "backlog.json", "docs/tasks/**", "rules/**",
    ".claude/**", ".codex/**", ".vscode/**", "hooks/**", "scripts/check_task_status.py",
    "CLAUDE.md", "AGENTS.md", "README.md", ".gitignore", "problem.md", "backlog.py",
]


def _exempt_globs():
    try:
        return config().get("task_guard", {}).get("exempt", DEFAULT_EXEMPT)
    except (OSError, ValueError):
        return DEFAULT_EXEMPT


def is_exempt(rel_path, globs):
    rel_path = rel_path.replace(os.sep, "/")
    rel_path = rel_path.removeprefix("./")
    return any(match_glob(rel_path, g) for g in globs)


def block(reason):
    print(reason, file=sys.stderr)
    sys.exit(1)


def read_active_task():
    try:
        with open(ACTIVE_TASK_FILE, encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def read_task(task_id):
    """(task 또는 None, 오류메시지 또는 None) 반환."""
    try:
        with open(BACKLOG_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None, "backlog.json을 읽을 수 없습니다."
    for t in data.get("tasks", []):
        if t.get("id") == task_id:
            return t, None
    return None, f"{task_id}가 backlog에 없습니다."


def main():
    paths = [p for p in sys.argv[1:] if p]
    globs = _exempt_globs()
    to_check = [p for p in paths if not is_exempt(p, globs)] if paths else [None]
    if not to_check:
        return  # 건드리는 파일이 전부 예외 경로 -> ALLOW

    task_id = read_active_task()
    if not task_id:
        block(
            "File modification blocked:\n"
            "활성 Task가 없습니다 (.agent/active_task 비어 있음). "
            "Project File은 Active Task가 'in_progress'인 경우에만 수정할 수 있습니다."
        )

    task, err = read_task(task_id)
    if err:
        block(f"File modification blocked:\n{err} Task 상태를 확인할 수 없어 차단합니다.")

    status = task.get("status")
    if status != "in_progress":
        block(
            f"File modification blocked:\n"
            f"{task_id}의 현재 상태는 '{status}'입니다. "
            "Project File은 Active Task가 'in_progress'인 경우에만 수정할 수 있습니다."
        )


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - 예상 못한 내부 오류도 기본 정책(BLOCK)을 따른다.
        block(f"File modification blocked:\nGuard 내부 오류로 판정할 수 없어 차단합니다: {exc}")
