#!/usr/bin/env python3
"""SessionEnd: 미커밋 변경, 진행 중 태스크, 마지막 검사 결과를 docs/session-log.md에 짧게 남긴다.

시간 예산이 1초 안팎으로 매우 짧다 (Codex 기준 최대 3초) — lint/build처럼 무거운 명령은
절대 돌리지 않고, 이미 캐시된 값과 빠른 git 상태 조회만 쓴다. 무엇을 하든 실패해도
세션 종료를 막지 않는다 (항상 조용히 끝난다).
"""
import datetime
import json
import os

from common import PROJECT, git, is_git_repo, read_input, state_get

LOG = os.path.join(PROJECT, "docs", "session-log.md")


def uncommitted_files():
    if not is_git_repo():
        return None
    _, out = git("status", "--porcelain", "--untracked-files=normal")
    return [ln[3:] for ln in out.splitlines()][:20]


def in_progress_tasks():
    try:
        with open(os.path.join(PROJECT, "backlog.json"), encoding="utf-8") as f:
            tasks = json.load(f).get("tasks", [])
    except (OSError, ValueError):
        return []
    return [f"{t['id']} {t['title']}" for t in tasks if t.get("status") == "in_progress"]


def build_entry():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    files = uncommitted_files()
    files_line = "git 저장소 아님" if files is None else (
        f"{len(files)}개: " + ", ".join(files[:8]) + (" ..." if len(files) > 8 else "") if files else "없음")
    active = in_progress_tasks()
    active_line = ", ".join(active) if active else "없음"
    gate = state_get("last_gate_result")
    gate_line = "확인 안 됨" if not gate else ("통과" if gate.get("ok") else "실패")
    return (f"## {now}\n"
            f"- 미커밋 변경: {files_line}\n"
            f"- 진행 중 태스크: {active_line}\n"
            f"- 마지막 lint/build 결과: {gate_line}\n\n")


def main():
    read_input()
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(build_entry())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
