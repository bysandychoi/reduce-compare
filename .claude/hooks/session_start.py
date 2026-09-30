#!/usr/bin/env python3
"""SessionStart: 현재 브랜치와 진행 중인 태스크를 알리고, master/main이면 dev로 전환하라고 안내한다."""
import json
import os

from _common import PROJECT, config, current_branch, emit, git, is_git_repo, read_input


def task_summary():
    """(사용자용 한 줄, Claude용 설명) 반환."""
    try:
        with open(os.path.join(PROJECT, "backlog.json"), encoding="utf-8") as f:
            tasks = json.load(f).get("tasks", [])
    except (OSError, ValueError):
        return "", ""
    by_id = {t["id"]: t for t in tasks}
    active = [t for t in tasks if t.get("status") == "in_progress"]
    ready = [t for t in tasks if t.get("status") == "todo"
             and all(by_id.get(d, {}).get("status") == "done" for d in t.get("depends_on", []))][:5]
    if active:
        names = ", ".join(f"{t['id']} {t['title']}" for t in active)
        user = f" · 진행 중: {names}"
        ctx = (f"진행 중인 태스크: {names}. 이어서 작업하기 전에 docs/tasks/<ID>.md와 "
               f"docs/tasks/<ID>.review.md를 먼저 읽으세요.")
    else:
        names = ", ".join(f"{t['id']} {t['title']}" for t in ready)
        user = " · 진행 중인 태스크 없음"
        ctx = (f"진행 중인 태스크가 없습니다. 파일을 고치기 전에 사용자와 작업할 태스크를 정하고 "
               f"`status <ID> in_progress` → task-briefer 순서로 시작하세요. 시작 가능: {names or '없음'}")
    return user, ctx


def main():
    read_input()
    cfg = config()
    work = cfg.get("work_branch", "dev")
    protected = cfg.get("protected_branches", ["master", "main"])
    task_user, task_ctx = task_summary()

    if not is_git_repo():
        msg = f"⚠ git 저장소가 아닙니다. `git init` 후 `{work}` 브랜치에서 작업하세요 (자동 커밋 훅이 동작하지 않습니다)."
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
