#!/usr/bin/env python3
"""PreToolUse(Write|Edit|MultiEdit|NotebookEdit): in_progress 태스크 없이 파일을 고치지 못하게 막는다.

docs/tasks/, .claude/ 같은 예외 경로는 통과시킨다 (config의 task_guard.exempt).
"""
import json
import os

from _common import PROJECT, config, emit, match_glob, read_input, rel


def in_progress_tasks():
    try:
        with open(os.path.join(PROJECT, "backlog.json"), encoding="utf-8") as f:
            tasks = json.load(f).get("tasks", [])
    except (OSError, ValueError):
        return None
    return [t for t in tasks if t.get("status") == "in_progress"]


def main():
    data = read_input()
    ti = data.get("tool_input") or {}
    fp = ti.get("file_path") or ti.get("notebook_path")
    if not fp:
        return
    path = rel(fp)
    cfg = config()
    guard = cfg.get("task_guard", {})
    if not guard.get("enabled", True) or path.startswith(".."):
        return
    if any(match_glob(path, g) for g in guard.get("exempt", [])):
        return

    active = in_progress_tasks()
    if active is None or active:
        return  # 백로그가 없으면 검사하지 않음

    cli = cfg.get("backlog_cli", "python3 backlog.py")
    reason = (
        f"in_progress 상태인 태스크가 없어서 {path}을(를) 수정할 수 없습니다.\n"
        "작업을 시작하려면:\n"
        f"  1. {cli} next  (시작 가능한 태스크 확인)\n"
        f"  2. {cli} status <ID> in_progress\n"
        "  3. task-briefer 서브에이전트로 docs/tasks/<ID>.md 작성\n"
        "그 다음 파일을 수정하세요. 어떤 태스크인지 모르겠으면 사용자에게 먼저 물어보세요."
    )
    emit({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }})


if __name__ == "__main__":
    main()
