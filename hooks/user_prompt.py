#!/usr/bin/env python3
"""UserPromptSubmit: 매 요청마다 현재 브랜치·진행 중 태스크를 한두 줄로 붙인다.

백로그 전체를 붙이지 않고, 요청을 막지도 않는다 (항상 allow, 문맥만 추가).
"""
import json
import os

from common import PROJECT, current_branch, emit, read_input

BACKLOG = "backlog.json"


def in_progress_line():
    try:
        with open(os.path.join(PROJECT, BACKLOG), encoding="utf-8") as f:
            tasks = json.load(f).get("tasks", [])
    except (OSError, ValueError):
        return "진행 중인 태스크 없음 (backlog.json을 읽을 수 없음)"
    active = [f"{t['id']} {t['title']}" for t in tasks if t.get("status") == "in_progress"]
    return ", ".join(active) if active else "진행 중인 태스크 없음"


def main():
    read_input()
    branch = current_branch() or "(알 수 없음)"
    ctx = f"[브랜치: {branch}] [진행 중: {in_progress_line()}]"
    emit({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}})


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001, S110 - context decoration must not block prompts
        pass
