#!/usr/bin/env python3
"""PreToolUse: reject project mutation when no task is in_progress."""
import json
import os

from common import PROJECT, config, emit, extract_file_paths, match_glob, read_input, rel


def active_tasks():
    try:
        with open(os.path.join(PROJECT, "backlog.json"), encoding="utf-8") as stream:
            tasks = json.load(stream).get("tasks", [])
    except (OSError, ValueError):
        return None
    return [task for task in tasks if task.get("status") == "in_progress"]


def main():
    data = read_input()
    paths = [rel(path) for path in extract_file_paths(data.get("tool_input") or {})]
    paths = [path for path in paths if not path.startswith("..")]
    if not paths:
        return

    guard = config().get("task_guard", {})
    if not guard.get("enabled", True):
        return
    guarded = [path for path in paths
               if not any(match_glob(path, pattern) for pattern in guard.get("exempt", []))]
    if not guarded:
        return

    active = active_tasks()
    if active is None or active:
        return
    reason = (
        "No backlog task is in_progress, so project files cannot be changed: "
        + ", ".join(guarded)
        + "\nRun Task Analysis first, then `python backlog.py status <ID> in_progress`."
    )
    emit({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }})


if __name__ == "__main__":
    main()
