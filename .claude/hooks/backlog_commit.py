#!/usr/bin/env python3
"""PostToolUse(Bash): 백로그 CLI로 backlog.json이 바뀌면 커밋한다.

- 일반 변경: backlog.json만 커밋
- 상태가 done으로 바뀐 태스크가 있으면: lint·build 통과 확인 → 전체 작업 커밋 → push
  (실패하거나 보호 브랜치면 done을 in_progress로 되돌리고 Claude에게 알림)
"""
import json
import os
import re
import shlex

from _common import (PROJECT, config, current_branch, emit, git, head_file, is_git_repo,
                     quality_gate, read_input, run)

BACKLOG = "backlog.json"
CLI_RE = re.compile(r"(^|[\s/\"'])backlog\.py([\s\"']|$)")


def tasks_of(text):
    try:
        return {t["id"]: t for t in json.loads(text).get("tasks", [])}
    except (ValueError, TypeError, AttributeError):
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
    """done 전에 필요한 리뷰 조건을 검사해서 문제 목록을 돌려준다."""
    rv = cfg.get("review", {})
    if not rv.get("required_for_done", True):
        return []
    tdir = rv.get("dir", "docs/tasks")
    _, status = git("status", "--porcelain", "--untracked-files=all")
    changed = [ln[3:].split(" -> ")[-1] for ln in status.splitlines()]
    changed = [p for p in changed if p != BACKLOG and not p.startswith(tdir + "/")
               and os.path.isfile(os.path.join(PROJECT, p))]
    newest = max((os.path.getmtime(os.path.join(PROJECT, p)) for p in changed), default=0)
    out = []
    for i in ids:
        if new[i].get("epic") in rv.get("exempt_epics", []):
            continue
        path = os.path.join(PROJECT, tdir, f"{i}.review.md")
        if not os.path.isfile(path):
            out.append(f"- {i}: {tdir}/{i}.review.md 가 없습니다")
            continue
        with open(path, encoding="utf-8") as f:
            verdicts = re.findall(r"^(?:Verdict|판정):\s*(.+?)\s*$", f.read(), re.M)
        if not verdicts or verdicts[-1] != "PASS":
            out.append(f"- {i}: 마지막 판정이 '{verdicts[-1] if verdicts else '없음'}'입니다")
        elif os.path.getmtime(path) < newest:
            out.append(f"- {i}: 마지막 리뷰 이후에 바뀐 파일이 있습니다 (다시 리뷰 필요)")
    return out


def revert_done(ids, cli):
    run(shlex.split(cli) + ["-f", os.path.join(PROJECT, BACKLOG), "status", *ids, "in_progress", "--force"])


def done_flow(cfg, newly_done, new, old):
    cli = cfg.get("backlog_cli", "python3 backlog.py")
    branch = current_branch()
    ids = ", ".join(newly_done)

    if branch in cfg.get("protected_branches", ["master", "main"]):
        revert_done(newly_done, cli)
        work = cfg.get("work_branch", "dev")
        return (f"'{branch}' 브랜치에서는 done 커밋·푸시를 하지 않습니다. {ids}를 in_progress로 되돌렸습니다. "
                f"`git switch {work}`(없으면 `git switch -c {work}`)로 전환한 뒤 다시 done 처리하세요."), None

    problems = review_problems(cfg, newly_done, new)
    if problems:
        revert_done(newly_done, cli)
        return (f"적대적 리뷰 PASS가 없어서 {ids}의 done 처리를 in_progress로 되돌렸습니다.\n"
                + "\n".join(problems) +
                "\nadversarial-reviewer 서브에이전트로 리뷰를 받고, PASS가 나오면 다시 done 처리하세요."), None

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
    body = ("완료 태스크\n" + "\n".join(titles) +
            f"\n\n백로그 변경: {diff_summary(old, new)}" +
            f"\n진행률: {fin}/{total}분 ({fin / total * 100:.0f}%)" +
            f"\n\n품질 게이트\n{summary}\n\n변경 파일\n{files}")
    code, out = git("commit", "-m", head, "-m", body)
    if code != 0:
        return f"done 커밋에 실패했습니다:\n{out}", None

    if git("rev-parse", "--abbrev-ref", "@{u}")[0] == 0:
        pcode, pout = git("push")
    elif git("remote")[1].strip():
        remote = git("remote")[1].split()[0]
        pcode, pout = git("push", "-u", remote, branch)
    else:
        return None, f"{head} 커밋 완료. 원격 저장소가 없어 push는 건너뛰었습니다."
    if pcode != 0:
        return None, f"{head} 커밋 완료. push 실패 — 직접 확인하세요:\n{pout[-600:]}"
    return None, f"{head} 커밋 후 {branch}에 push했습니다."


def main():
    data = read_input()
    cmd = (data.get("tool_input") or {}).get("command", "")
    if not CLI_RE.search(cmd) or not is_git_repo():
        return
    if not git("status", "--porcelain", "--", BACKLOG)[1].strip():
        return  # 조회만 했거나 변경 없음

    cfg = config()
    old = tasks_of(head_file(BACKLOG) or "{}")
    with open(os.path.join(PROJECT, BACKLOG), encoding="utf-8") as f:
        new = tasks_of(f.read())
    newly_done = [i for i, t in new.items()
                  if t.get("status") == "done" and old.get(i, {}).get("status") != "done"]

    if newly_done:
        problem, info = done_flow(cfg, newly_done, new, old)
        if problem:
            with open(os.path.join(PROJECT, BACKLOG), encoding="utf-8") as f:
                new = tasks_of(f.read())
            if git("status", "--porcelain", "--", BACKLOG)[1].strip():
                commit_backlog_only(diff_summary(old, new))
            emit({"decision": "block", "reason": problem, "systemMessage": problem.splitlines()[0]})
        emit({"systemMessage": info,
              "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": info}})

    ok, out = commit_backlog_only(diff_summary(old, new))
    msg = f"백로그 변경을 커밋했습니다: {diff_summary(old, new)}" if ok else f"백로그 자동 커밋 실패:\n{out}"
    emit({"systemMessage": msg.splitlines()[0],
          "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}})


if __name__ == "__main__":
    main()
