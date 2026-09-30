#!/usr/bin/env python3
"""PreToolUse: backlog.json을 직접 읽거나 고치는 것을 막고 CLI 사용을 안내한다."""
import os
import re

from _common import config, emit, read_input

CLI_RE = re.compile(r"(^|[\s/\"'])backlog\.py([\s\"']|$)")
SPLIT_RE = re.compile(r"&&|\|\||;|\||\n")


def guide(cli, target):
    return (
        f"{target} 파일은 직접 조회·수정할 수 없습니다. 백로그 CLI를 사용하세요:\n"
        f"  조회: {cli} list [-e E3] [-s todo] [-r] [-q 검색어] | {cli} next | {cli} show T033 | {cli} stats\n"
        f"  수정: {cli} update T033 --min 25 --add-dep T007 --add-ac \"완료 기준\"\n"
        f"        {cli} status T010 in_progress|done|blocked\n"
        f"  추가: {cli} add -e E13 -t \"제목\" -m 20 --dep T131 --ac \"완료 기준\"\n"
        f"  삭제: {cli} rm T108 · 검사: {cli} validate · 도움말: {cli} --help\n"
        "백로그가 바뀌면 훅이 자동으로 커밋하고, 상태가 done이 되면 전체 작업을 커밋·푸시합니다."
    )


def mentions(text, names):
    return any(n in (text or "") for n in names)


def is_protected_path(path, names):
    return bool(path) and os.path.basename(path.rstrip("/")) in names


def bash_violation(command, names):
    for seg in SPLIT_RE.split(command or ""):
        if mentions(seg, names) and not CLI_RE.search(seg):
            return seg.strip()
    return None


def main():
    data = read_input()
    cfg = config()
    names = cfg.get("protected_files", ["backlog.json"])
    cli = cfg.get("backlog_cli", "python3 backlog.py")
    tool, ti = data.get("tool_name", ""), data.get("tool_input", {}) or {}

    blocked = False
    if tool in ("Read", "Write", "Edit", "MultiEdit", "NotebookEdit"):
        blocked = is_protected_path(ti.get("file_path") or ti.get("notebook_path"), names)
    elif tool == "Grep":
        blocked = is_protected_path(ti.get("path"), names) or mentions(ti.get("glob"), names)
    elif tool == "Glob":
        blocked = mentions(ti.get("pattern"), names)
    elif tool == "Bash":
        blocked = bash_violation(ti.get("command"), names) is not None

    if blocked:
        emit({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": guide(cli, ", ".join(names)),
        }})


if __name__ == "__main__":
    main()
