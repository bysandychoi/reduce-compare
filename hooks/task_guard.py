#!/usr/bin/env python3
"""PreToolUse: Active Task 상태를 scripts/check_task_status.py에 위임해서 확인한다.

Business Rule(어떤 파일이 예외인지, active task가 in_progress인지)은 전부
scripts/check_task_status.py에 있다 — 이 훅은 그 결과를 Claude 형식으로만 옮긴다
(Claude Hook -> scripts/check_task_status.py -> .agent/active_task -> backlog.json).
"""
import sys

from common import (
    PROJECT,
    emit,
    extract_file_paths,
    read_input,
    rel,
    run,
)


def main():
    data = read_input()
    paths = [rel(path) for path in extract_file_paths(data.get("tool_input") or {})]
    paths = [path for path in paths if not path.startswith("..")]
    if not paths:
        return

    code, out = run([sys.executable, "scripts/check_task_status.py", *paths], cwd=PROJECT)
    if code != 0:
        reason = out.strip() or "Active Task 상태를 확인할 수 없습니다."
        emit({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }})


if __name__ == "__main__":
    main()
