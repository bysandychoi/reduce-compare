#!/usr/bin/env python3
"""PostToolUse: backlog.py CLI로 backlog.json이 바뀌면 커밋하고,
상태가 done으로 바뀐 태스크가 있으면 lint/build 확인 후 전체 작업을 커밋·push한다.

- 일반 변경: backlog.json만 커밋 (추가/삭제/상태 변경 요약을 메시지에 넣는다)
- done 전환: lint/build 통과 확인 → 전체 커밋 → 원격이 있으면 push
  실패하거나 보호 브랜치·git 저장소 없음이면 done을 in_progress로 되돌리고 이유를 알린다.
- 원격 유무는 실행할 때마다 새로 확인한다 (나중에 원격을 추가하면 바로 push된다).

apply_patch처럼 파일을 직접 바꾸는 호출은 extract_shell_command()가 None을 돌려주므로
이 훅은 자동으로 아무것도 하지 않는다 (셸에서 backlog.py CLI를 실행했을 때만 반응).
"""
import json
import os
import re
import shlex
import sys

from common import (
    PROJECT,
    config,
    current_branch,
    emit,
    extract_shell_command,
    git,
    has_remote,
    has_upstream,
    head_file,
    is_git_repo,
    quality_gate,
    read_input,
    run,
    state_get,
    state_set,
)

BACKLOG = "backlog.json"
CLI_RE = re.compile(r"(^|[\s/\"'])backlog\.py([\s\"']|$)")
SNAPSHOT_KEY = "backlog_snapshot.json"


def tasks_of(text):
    try:
        return {t["id"]: t for t in json.loads(text).get("tasks", [])}
    except (ValueError, TypeError, AttributeError):
        return {}


def current_tasks():
    try:
        with open(os.path.join(PROJECT, BACKLOG), encoding="utf-8") as f:
            return tasks_of(f.read())
    except OSError:
        return {}


def diff_summary(old, new):
    added = [i for i in new if i not in old]
    removed = [i for i in old if i not in new]
    changed = []
    for i in new:
        if i in old and new[i] != old[i]:
            keys = [k for k in new[i] if new[i].get(k) != old[i].get(k)]
            if "status" in keys:
                changed.append(f"{i} {old[i].get('status')}→{new[i]['status']}")
            else:
                changed.append(f"{i}({','.join(keys)})")
    parts = [f"+{i}" for i in added] + [f"-{i}" for i in removed] + changed
    return ", ".join(parts) or "메타데이터 변경"


def commit_backlog_only(summary):
    git("add", BACKLOG)
    code, out = git("commit", "-m", f"backlog: {summary}", "--", BACKLOG)
    return code == 0, out


def review_problems(cfg, ids, new):
    """Return missing, stale, or non-PASS review errors for done transitions."""
    rv = cfg.get("review", {})
    if not rv.get("required_for_done", True):
        return []
    review_dir = rv.get("dir", "docs/tasks")
    _, status = git("status", "--porcelain", "--untracked-files=all")
    changed = [line[3:].split(" -> ")[-1] for line in status.splitlines()]
    changed = [path for path in changed if path != BACKLOG
               and not path.startswith(review_dir + "/")
               and os.path.isfile(os.path.join(PROJECT, path))]
    newest_change = max((os.path.getmtime(os.path.join(PROJECT, path))
                         for path in changed), default=0)
    problems = []
    for task_id in ids:
        if new[task_id].get("epic") in rv.get("exempt_epics", []):
            continue
        path = os.path.join(PROJECT, review_dir, f"{task_id}.review.md")
        if not os.path.isfile(path):
            problems.append(f"- {task_id}: {review_dir}/{task_id}.review.md is missing")
            continue
        with open(path, encoding="utf-8") as stream:
            verdicts = re.findall(r"^(?:Verdict|판정):\s*(.+?)\s*$", stream.read(), re.MULTILINE)
        verdict = verdicts[-1] if verdicts else "missing"
        if verdict != "PASS":
            problems.append(f"- {task_id}: latest review verdict is {verdict}")
        elif os.path.getmtime(path) < newest_change:
            problems.append(f"- {task_id}: files changed after the latest PASS review")
    return problems


def revert_done(ids, cli):
    run(shlex.split(cli) + ["-f", os.path.join(PROJECT, BACKLOG), "status", *ids, "in_progress", "--force"])


def push_if_possible(branch):
    if has_upstream():
        code, out = git("push")
        return None if code == 0 else f"push 실패 — 직접 확인하세요:\n{out[-600:]}"
    if has_remote():
        remote = git("remote")[1].split()[0]
        code, out = git("push", "-u", remote, branch)
        return None if code == 0 else f"push 실패 — 직접 확인하세요:\n{out[-600:]}"
    return "원격 저장소가 없어 push는 건너뛰었습니다."


def done_flow(cfg, newly_done, new, old):
    cli = cfg.get("backlog_cli", "python backlog.py")
    branch = current_branch()
    ids = ", ".join(newly_done)

    if not is_git_repo():
        revert_done(newly_done, cli)
        return (f"git 저장소가 없어서 done 검사를 할 수 없습니다. {ids}를 in_progress로 되돌렸습니다. "
                f"`git init` 후 다시 `{cli} status {' '.join(newly_done)} done`을 실행하세요."), None

    if branch in cfg.get("protected_branches", ["master", "main"]):
        revert_done(newly_done, cli)
        work = cfg.get("work_branch", "dev")
        return (f"'{branch}' 브랜치에서는 done 커밋·푸시를 하지 않습니다. {ids}를 in_progress로 되돌렸습니다. "
                f"`git switch {work}`(없으면 `git switch -c {work}`)로 전환한 뒤 다시 done 처리하세요."), None

    problems = review_problems(cfg, newly_done, new)
    if problems:
        revert_done(newly_done, cli)
        return ("A fresh Adversarial Review PASS is required before done. "
                f"Reverted {ids} to in_progress.\n" + "\n".join(problems)), None

    ok, summary, detail = quality_gate(cfg)
    if not ok:
        revert_done(newly_done, cli)
        return (f"lint/build가 실패해서 {ids}의 done 처리를 in_progress로 되돌렸습니다. "
                f"아래 오류를 고친 뒤 다시 `{cli} status {' '.join(newly_done)} done` 하세요.\n"
                f"{summary}\n\n{detail}"), None

    git("add", "-A")
    _, files = git("diff", "--cached", "--name-status")
    titles = [f"- {i} {new[i]['title']} ({new[i]['epic']})" for i in newly_done]
    head = f"done: {newly_done[0]} {new[newly_done[0]]['title']}"
    if len(newly_done) > 1:
        head = f"done: {newly_done[0]} 외 {len(newly_done) - 1}건"
    total = sum(t["estimate_min"] for t in new.values())
    fin = sum(t["estimate_min"] for t in new.values() if t["status"] == "done")
    pct = f"{fin / total * 100:.0f}%" if total else "-"
    body = ("완료 태스크\n" + "\n".join(titles) +
            f"\n\n백로그 변경: {diff_summary(old, new)}" +
            f"\n진행률: {fin}/{total}분 ({pct})" +
            f"\n\n품질 게이트\n{summary}\n\n변경 파일\n{files}")
    code, out = git("commit", "-m", head, "-m", body)
    if code != 0:
        return f"done 커밋에 실패했습니다:\n{out}", None

    push_msg = push_if_possible(branch)
    info = f"{head} 커밋 완료." + (f" {push_msg}" if push_msg else f" {branch}에 push했습니다.")
    return None, info


def main():
    data = read_input()
    cmd = extract_shell_command(data.get("tool_input") or {})
    if cmd is None or not CLI_RE.search(cmd):
        return

    cfg = config()
    old = state_get(SNAPSHOT_KEY)
    if old is None:
        old = tasks_of(head_file(BACKLOG) or "{}")
        state_set(SNAPSHOT_KEY, old)
    new = current_tasks()
    if new == old:
        return  # 조회만 했거나 변경 없음

    newly_done = [i for i, t in new.items()
                  if t.get("status") == "done" and old.get(i, {}).get("status") != "done"]

    if newly_done:
        problem, info = done_flow(cfg, newly_done, new, old)
        if problem:
            reverted = current_tasks()
            if is_git_repo() and git("status", "--porcelain", "--", BACKLOG)[1].strip():
                commit_backlog_only(diff_summary(old, reverted))
            state_set(SNAPSHOT_KEY, reverted)
            emit({"decision": "block", "reason": problem, "systemMessage": problem.splitlines()[0]})
        state_set(SNAPSHOT_KEY, current_tasks())
        emit({"systemMessage": info.splitlines()[0],
              "hookSpecificOutput": {"additionalContext": info}})

    if is_git_repo():
        ok, out = commit_backlog_only(diff_summary(old, new))
        msg = f"백로그 변경을 커밋했습니다: {diff_summary(old, new)}" if ok else f"백로그 자동 커밋 실패:\n{out}"
    else:
        msg = f"백로그 변경 감지: {diff_summary(old, new)} (git 저장소가 없어 커밋하지 않았습니다)"
    state_set(SNAPSHOT_KEY, new)
    emit({"systemMessage": msg.splitlines()[0],
          "hookSpecificOutput": {"additionalContext": msg}})


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - 훅 버그로 다른 작업까지 막히면 안 된다.
        print(f"⚠ backlog_sync 훅 내부 오류로 자동 커밋을 건너뜁니다: {exc}", file=sys.stderr)
