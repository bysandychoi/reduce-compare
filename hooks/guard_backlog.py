#!/usr/bin/env python3
"""PreToolUse: backlog.json을 직접 읽거나 고치는 것을 막고 CLI 사용을 안내한다.

Claude(Read/Write/Edit/MultiEdit/NotebookEdit/Grep/Glob/Bash)와
Codex(apply_patch/셸 명령) 양쪽의 tool_input 모양을 모두 흡수한다.
"""
import os

from common import config, emit, extract_file_paths, extract_shell_command, mentions_name, read_input


def guide(cli, target):
    return (
        f"{target} 파일은 직접 조회·수정할 수 없습니다. 백로그 CLI를 사용하세요:\n"
        f"  조회: {cli} list [-e E3] [-s todo] [-r] [-q 검색어] | {cli} next | {cli} show T033 | {cli} stats\n"
        f"  수정: {cli} update T033 --min 25 --add-dep T007 --add-ac \"완료 기준\"\n"
        f"        {cli} status T010 in_progress|done|blocked\n"
        f"  추가: {cli} add -e E13 -t \"제목\" -m 20 --dep T131 --ac \"완료 기준\"\n"
        f"  삭제: {cli} rm T108 · 검사: {cli} validate · 도움말: {cli} --help\n"
        "백로그가 바뀌면 훅이 자동으로 커밋하고, 상태가 done이 되면 전체 작업을 커밋·push합니다."
    )


def is_protected_name(path, names):
    return bool(path) and os.path.basename(path.rstrip("/\\")) in names


def main():
    data = read_input()
    cfg = config()
    names = cfg.get("protected_files", ["backlog.json"])
    cli = cfg.get("backlog_cli", "python backlog.py")
    ti = data.get("tool_input") or {}

    blocked = False

    # 1) 파일 수정/조회 도구(Claude Write/Edit/Read/NotebookEdit, Codex apply_patch)
    for p in extract_file_paths(ti):
        if is_protected_name(p, names):
            blocked = True
            break

    # 2) Grep/Glob (Claude 전용 도구 — Codex엔 없지만 확인해서 손해 없음)
    if not blocked:
        if is_protected_name(ti.get("path"), names) or any(n in (ti.get("glob") or "") for n in names):
            blocked = True
        elif any(n in (ti.get("pattern") or "") for n in names):
            blocked = True

    # 3) 셸 명령 (cat/sed/grep/git diff 등으로 우회 접근)
    if not blocked:
        cmd = extract_shell_command(ti)
        if cmd is not None and mentions_name(cmd, names):
            blocked = True

    if blocked:
        emit({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": guide(cli, ", ".join(names)),
        }})


if __name__ == "__main__":
    main()
