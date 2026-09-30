#!/usr/bin/env python3
"""SessionStart: 현재 브랜치, 진행 중인 태스크, 지금 시작할 수 있는 태스크를 알린다.

Claude Code와 Codex CLI 둘 다 같은 모양으로 호출한다 (source: startup|resume|clear|compact).
"""
import json
import os

from common import PROJECT, config, current_branch, emit, git, is_git_repo, read_input

BACKLOG = "backlog.json"


def load_tasks():
    try:
        with open(os.path.join(PROJECT, BACKLOG), encoding="utf-8") as f:
            return json.load(f).get("tasks", [])
    except (OSError, ValueError):
        return None


def task_summary():
    """(사용자용 한 줄, 에이전트용 설명) 반환."""
    tasks = load_tasks()
    if tasks is None:
        return "", ""
    by_id = {t["id"]: t for t in tasks}
    active = [t for t in tasks if t.get("status") == "in_progress"]
    ready = [t for t in tasks if t.get("status") == "todo"
             and all(by_id.get(d, {}).get("status") == "done" for d in t.get("depends_on", []))][:5]

    active_txt = ", ".join(f"{t['id']} {t['title']}" for t in active) or "없음"
    ready_txt = ", ".join(f"{t['id']} {t['title']}" for t in ready) or "없음"
    user = f" · 진행 중: {active_txt} · 시작 가능: {ready_txt}"
    ctx = (f"진행 중인 태스크: {active_txt}. 지금 시작할 수 있는 태스크: {ready_txt}. "
           "새로 시작하기 전에 사용자와 태스크를 정하고, 진행 중인 태스크가 있으면 관련 docs/tasks/<ID>.md를 먼저 읽으세요.")
    return user, ctx


def main():
    read_input()
    cfg = config()
    work = cfg.get("work_branch", "dev")
    protected = cfg.get("protected_branches", ["master", "main"])
    task_user, task_ctx = task_summary()

    if not is_git_repo():
        msg = f"⚠ git 저장소가 아닙니다. `git init` 후 `{work}` 브랜치에서 작업하세요 (자동 커밋 훅이 동작하지 않고, done 처리도 반려됩니다)."
        emit({"systemMessage": msg + task_user,
              "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": msg + "\n" + task_ctx}})

    branch = current_branch() or "(알 수 없음)"
    if branch in protected:
        has_work = git("rev-parse", "--verify", "--quiet", work)[0] == 0
        how = f"git switch {work}" if has_work else f"git switch -c {work}"
        user_msg = f"⚠ 현재 브랜치: {branch} — {work} 브랜치로 전환하세요: `{how}`"
        ctx = (f"현재 git 브랜치는 '{branch}'입니다. 이 프로젝트는 '{branch}'에서 직접 작업하지 않습니다. "
               f"코드나 백로그를 수정하기 전에 사용자에게 '{work}' 브랜치로 전환하도록 안내하세요 (`{how}`).")
    else:
        user_msg = f"현재 브랜치: {branch}"
        ctx = f"현재 git 브랜치는 '{branch}'입니다."
    emit({"systemMessage": user_msg + task_user,
          "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx + "\n" + task_ctx}})


if __name__ == "__main__":
    main()
