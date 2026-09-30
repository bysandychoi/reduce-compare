#!/usr/bin/env python3
"""Stop: 작업을 끝내기 전에 lint·build를 강제하고, 끝나면 팝업을 띄운다.

- 마지막 통과 이후 코드가 바뀌었으면 lint·build 실행. 실패하면 종료를 막고 고치게 한다.
- 같은 세션에서 연속 gate_max_blocks번 실패하면 무한 반복에 빠지지 않도록 종료를 허용하고 알린다.
- backlog.json에 커밋 안 된 변경이 남아 있으면(git 저장소일 때만) 커밋한다.
"""
import hashlib
import os

from common import (PROJECT, block_stop, config, emit, git, is_git_repo, popup,
                     quality_gate, read_input, state_get, state_set)


def fingerprint():
    """코드 변경 상태를 요약한 해시 (백로그·훅 상태 파일 제외)."""
    if not is_git_repo():
        return None
    _, status = git("status", "--porcelain", "--untracked-files=all")
    _, diff = git("diff", "HEAD")
    lines = [ln for ln in status.splitlines() if "backlog.json" not in ln and "hooks/.state" not in ln]
    return hashlib.sha1(("\n".join(lines) + diff).encode()).hexdigest()


def commit_leftover_backlog():
    if is_git_repo() and git("status", "--porcelain", "--", "backlog.json")[1].strip():
        git("add", "backlog.json")
        git("commit", "-m", "backlog: 세션 종료 시 남은 변경", "--", "backlog.json")


def main():
    data = read_input()
    cfg = config()
    sid = data.get("session_id", "default")
    project = os.path.basename(PROJECT)
    style = cfg.get("popup", {}).get("style", "notification")

    fp = fingerprint()
    if fp is None or fp != state_get("gate_pass_fp"):
        ok, summary, detail = quality_gate(cfg)
        state_set("last_gate_result", {"ok": ok, "summary": summary})
        if ok:
            state_set("gate_pass_fp", fp)
            state_set(f"blocks_{sid}", 0)
        else:
            n = (state_get(f"blocks_{sid}", 0) or 0) + 1
            if n < cfg.get("gate_max_blocks", 3):
                state_set(f"blocks_{sid}", n)
                block_stop(f"작업을 끝내기 전에 lint/build를 통과해야 합니다 ({n}번째 실패).\n{summary}\n\n{detail}")
            state_set(f"blocks_{sid}", 0)
            commit_leftover_backlog()
            msg = f"lint/build가 {n}번 연속 실패한 상태로 작업을 멈췄습니다. 직접 확인이 필요합니다."
            if cfg.get("popup", {}).get("on_stop", True):
                popup(f"{project}", "⚠ " + msg, style)
            emit({"systemMessage": f"⚠ {msg}\n{summary}"})

    commit_leftover_backlog()
    if cfg.get("popup", {}).get("on_stop", True):
        last = (data.get("last_assistant_message") or "").strip().splitlines()
        popup(f"{project}", "작업이 끝났습니다. " + (last[0][:120] if last else ""), style)


if __name__ == "__main__":
    main()
