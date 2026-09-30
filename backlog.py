#!/usr/bin/env python3
"""backlog.json 조회·수정·추가 CLI (표준 라이브러리만 사용).

사용 예:
  python backlog.py list --epic E13 --status todo
  python backlog.py next
  python backlog.py show T033
  python backlog.py add --epic E13 --title "상관 결과 캐시" --min 20 --dep T131 --ac "재요청 시 재계산 없음"
  python backlog.py update T033 --min 25 --add-dep T007
  python backlog.py status T010 done
  python backlog.py rm T108
  python backlog.py stats
  python backlog.py validate
  python backlog.py epic list | epic add E15 "새 에픽"

파일 경로: --file 옵션 > 환경변수 BACKLOG_FILE > ./backlog.json
"""
import argparse
import json
import os
import re
import sys
import tempfile
import unicodedata

DEFAULT_STATUSES = ["todo", "in_progress", "done", "blocked"]


# ---------- 입출력 ----------
def load(path):
    if not os.path.exists(path):
        sys.exit(f"오류: 파일이 없습니다: {path}")
    with open(path, encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            sys.exit(f"오류: JSON 형식이 잘못됐습니다 ({path}): {e}")


def dump_text(data):
    """태스크는 한 줄에 하나씩 쓰는 기존 형식을 유지한다."""
    head = {k: v for k, v in data.items() if k != "tasks"}
    text = json.dumps(head, ensure_ascii=False, indent=2)
    body = ",\n".join("    " + json.dumps(t, ensure_ascii=False) for t in data.get("tasks", []))
    text = text[:-2] + (',\n  "tasks": [\n' + body + "\n  ]\n}\n" if body else ',\n  "tasks": []\n}\n')
    json.loads(text)  # 안전 확인
    return text


def save(path, data):
    errors = validate(data)
    if errors:
        print("저장하지 않았습니다. 검증 오류:", file=sys.stderr)
        for e in errors:
            print("  - " + e, file=sys.stderr)
        sys.exit(1)
    text = dump_text(data)
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".backlog-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


# ---------- 규칙 ----------
def rules(data):
    r = data.get("rules", {})
    return r.get("max_task_minutes", 30), r.get("status_values", DEFAULT_STATUSES)


def task_map(data):
    return {t["id"]: t for t in data.get("tasks", [])}


def id_num(tid):
    m = re.match(r"^T(\d+)$", tid)
    return int(m.group(1)) if m else 10 ** 9


def validate(data):
    errors = []
    max_min, statuses = rules(data)
    epics = {e["id"] for e in data.get("epics", [])}
    seen = set()
    tasks = data.get("tasks", [])
    ids = {t.get("id") for t in tasks}
    for t in tasks:
        tid = t.get("id", "?")
        if not re.match(r"^T\d+$", str(tid)):
            errors.append(f"{tid}: ID 형식은 T+숫자여야 합니다")
        if tid in seen:
            errors.append(f"{tid}: 중복 ID")
        seen.add(tid)
        for k in ("epic", "title", "estimate_min", "depends_on", "status"):
            if k not in t:
                errors.append(f"{tid}: '{k}' 누락")
        if t.get("epic") not in epics:
            errors.append(f"{tid}: 없는 에픽 {t.get('epic')}")
        m = t.get("estimate_min")
        if not isinstance(m, int) or m <= 0 or m > max_min:
            errors.append(f"{tid}: 예상 시간은 1~{max_min}분 정수여야 합니다 (현재 {m})")
        if t.get("status") not in statuses:
            errors.append(f"{tid}: 잘못된 상태 {t.get('status')} (허용: {', '.join(statuses)})")
        for d in t.get("depends_on", []):
            if d not in ids:
                errors.append(f"{tid}: 없는 의존 태스크 {d}")
            if d == tid:
                errors.append(f"{tid}: 자기 자신에 의존")
    # 순환 검사
    g = {t["id"]: [d for d in t.get("depends_on", []) if d in ids] for t in tasks if "id" in t}
    state = {}
    def dfs(n, path):
        state[n] = 1
        for m in g.get(n, []):
            if state.get(m) == 1:
                cyc = path[path.index(m):] + [m] if m in path else [n, m]
                errors.append("순환 의존: " + " → ".join(cyc))
            elif state.get(m) is None:
                dfs(m, path + [m])
        state[n] = 2
    for n in g:
        if state.get(n) is None:
            dfs(n, [n])
    return errors


def ready_tasks(data):
    tm = task_map(data)
    out = []
    for t in data["tasks"]:
        if t["status"] != "todo":
            continue
        if all(tm[d]["status"] == "done" for d in t["depends_on"] if d in tm):
            out.append(t)
    return out


def next_id(data, epic):
    ids = {t["id"] for t in data["tasks"]}
    same = [id_num(t["id"]) for t in data["tasks"] if t["epic"] == epic]
    start = (max(same) + 1) if same else ((max(id_num(i) for i in ids) // 10 + 1) * 10 if ids else 1)
    n = start
    while f"T{n:03d}" in ids:
        n += 1
    return f"T{n:03d}"


# ---------- 출력 ----------
USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
COLORS = {"todo": "0", "in_progress": "33", "done": "32", "blocked": "31"}


def c(text, code):
    return f"\033[{code}m{text}\033[0m" if USE_COLOR and code != "0" else text


def width(s):
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def pad(s, w):
    s = str(s)
    if width(s) > w:
        out = ""
        for ch in s:
            if width(out + ch) > w - 1:
                break
            out += ch
        s = out + "…"
    return s + " " * (w - width(s))


def print_table(tasks, data):
    if not tasks:
        print("(해당 태스크 없음)")
        return
    tm = task_map(data)
    print(pad("ID", 6), pad("에픽", 5), pad("상태", 12), pad("분", 4), pad("제목", 44), "의존")
    for t in tasks:
        deps = []
        for d in t["depends_on"]:
            done = tm.get(d, {}).get("status") == "done"
            deps.append(c(d, "32") if done else d)
        print(pad(t["id"], 6), pad(t["epic"], 5), c(pad(t["status"], 12), COLORS.get(t["status"], "0")),
              pad(t["estimate_min"], 4), pad(t["title"], 44), ",".join(deps))
    total = sum(t["estimate_min"] for t in tasks)
    print(f"\n{len(tasks)}개 · {total}분 ({total / 60:.1f}시간)")


def print_task(t, data):
    tm = task_map(data)
    epics = {e["id"]: e["title"] for e in data["epics"]}
    dependents = [x["id"] for x in data["tasks"] if t["id"] in x["depends_on"]]
    print(f"{t['id']}  {t['title']}")
    print(f"  에픽    : {t['epic']} {epics.get(t['epic'], '')}")
    print(f"  상태    : {c(t['status'], COLORS.get(t['status'], '0'))}")
    print(f"  예상    : {t['estimate_min']}분")
    print(f"  설명    : {t.get('description', '')}")
    dep_txt = ", ".join(f"{d}({tm[d]['status']})" if d in tm else d for d in t["depends_on"]) or "-"
    print(f"  의존    : {dep_txt}")
    print(f"  후행    : {', '.join(dependents) or '-'}")
    print("  완료 기준:")
    for a in t.get("acceptance_criteria", []) or ["-"]:
        print(f"    - {a}")


def find(data, tid):
    tid = tid.upper()
    if re.match(r"^T\d+$", tid) and not re.match(r"^T\d{3,}$", tid):
        tid = f"T{int(tid[1:]):03d}"
    t = task_map(data).get(tid)
    if not t:
        sys.exit(f"오류: 태스크 {tid}가 없습니다")
    return t


def norm_ids(ids):
    out = []
    for i in ids or []:
        for part in i.split(","):
            part = part.strip().upper()
            if part:
                out.append(f"T{int(part[1:]):03d}" if re.match(r"^T\d+$", part) else part)
    return out


# ---------- 명령 ----------
def cmd_list(a, data):
    ts = data["tasks"]
    if a.epic:
        ts = [t for t in ts if t["epic"] in [e.upper() for e in a.epic]]
    if a.status:
        ts = [t for t in ts if t["status"] in a.status]
    if a.ready:
        ready = {t["id"] for t in ready_tasks(data)}
        ts = [t for t in ts if t["id"] in ready]
    if a.search:
        q = a.search.lower()
        ts = [t for t in ts if q in t["title"].lower() or q in t.get("description", "").lower()]
    if a.json:
        print(json.dumps(ts, ensure_ascii=False, indent=2))
    else:
        print_table(ts, data)


def cmd_next(a, data):
    ts = sorted(ready_tasks(data), key=lambda t: id_num(t["id"]))
    if a.limit:
        ts = ts[: a.limit]
    print("지금 시작할 수 있는 태스크 (의존 태스크가 모두 done):\n")
    print_table(ts, data)


def cmd_show(a, data):
    for tid in a.ids:
        t = find(data, tid)
        if a.json:
            print(json.dumps(t, ensure_ascii=False, indent=2))
        else:
            print_task(t, data)
            print()


def cmd_add(a, data):
    epic = a.epic.upper()
    if epic not in {e["id"] for e in data["epics"]}:
        sys.exit(f"오류: 없는 에픽 {epic}. 'epic list'로 확인하거나 'epic add'로 먼저 추가하세요")
    tid = norm_ids([a.id])[0] if a.id else next_id(data, epic)
    if tid in task_map(data):
        sys.exit(f"오류: {tid}는 이미 있습니다")
    t = {"id": tid, "epic": epic, "title": a.title, "description": a.desc or "",
         "estimate_min": a.min, "depends_on": norm_ids(a.dep), "acceptance_criteria": a.ac or [],
         "status": a.status}
    data["tasks"].append(t)
    data["tasks"].sort(key=lambda x: id_num(x["id"]))
    save(a.file, data)
    print(f"추가됨: {tid}")
    print_task(t, data)


def cmd_update(a, data):
    t = find(data, a.id)
    changed = []
    for key, val in (("title", a.title), ("description", a.desc), ("estimate_min", a.min), ("status", a.status)):
        if val is not None:
            t[key] = val; changed.append(key)
    if a.epic:
        t["epic"] = a.epic.upper(); changed.append("epic")
    if a.set_dep is not None:
        t["depends_on"] = norm_ids(a.set_dep); changed.append("depends_on")
    for d in norm_ids(a.add_dep):
        if d not in t["depends_on"]:
            t["depends_on"].append(d); changed.append(f"+dep {d}")
    for d in norm_ids(a.rm_dep):
        if d in t["depends_on"]:
            t["depends_on"].remove(d); changed.append(f"-dep {d}")
    if a.set_ac is not None:
        t["acceptance_criteria"] = a.set_ac; changed.append("acceptance_criteria")
    for x in a.add_ac or []:
        t.setdefault("acceptance_criteria", []).append(x); changed.append("+ac")
    if not changed:
        sys.exit("변경할 항목이 없습니다. --help로 옵션을 확인하세요")
    save(a.file, data)
    print(f"수정됨: {t['id']} ({', '.join(changed)})")
    print_task(t, data)


def cmd_status(a, data):
    _, statuses = rules(data)
    if a.status not in statuses:
        sys.exit(f"오류: 상태는 {', '.join(statuses)} 중 하나여야 합니다")
    ids = [find(data, i)["id"] for i in a.ids]
    tm = task_map(data)
    for tid in ids:
        t = tm[tid]
        if a.status in ("in_progress", "done"):
            pending = [d for d in t["depends_on"] if tm[d]["status"] != "done"]
            if pending and not a.force:
                sys.exit(f"오류: {tid}의 의존 태스크가 아직 done이 아닙니다: {', '.join(pending)} (무시하려면 --force)")
        t["status"] = a.status
    save(a.file, data)
    print(f"{', '.join(ids)} → {a.status}")
    if a.status == "done":
        newly = [t for t in ready_tasks(data) if any(i in t["depends_on"] for i in ids)]
        if newly:
            print("\n이제 시작할 수 있는 태스크:")
            print_table(newly, data)


def cmd_rm(a, data):
    t = find(data, a.id)
    users = [x for x in data["tasks"] if t["id"] in x["depends_on"]]
    if users and not a.force:
        sys.exit(f"오류: 다음 태스크가 {t['id']}에 의존합니다: {', '.join(u['id'] for u in users)} "
                 f"(의존까지 함께 지우려면 --force)")
    for u in users:
        u["depends_on"].remove(t["id"])
    data["tasks"].remove(t)
    save(a.file, data)
    print(f"삭제됨: {t['id']} {t['title']}" + (f" (의존 제거: {', '.join(u['id'] for u in users)})" if users else ""))


def cmd_stats(a, data):
    _, statuses = rules(data)
    print(pad("에픽", 5), pad("제목", 30), pad("개수", 5), pad("분", 6), pad("완료", 12), " ".join(pad(s, 11) for s in statuses))
    rows = [(e["id"], e["title"], [t for t in data["tasks"] if t["epic"] == e["id"]]) for e in data["epics"]]
    rows.append(("합계", "", data["tasks"]))
    for eid, title, ts in rows:
        total = sum(t["estimate_min"] for t in ts)
        done = sum(t["estimate_min"] for t in ts if t["status"] == "done")
        pct = f"{done / total * 100:.0f}%" if total else "-"
        bar = "█" * round((done / total * 8) if total else 0)
        counts = " ".join(pad(sum(1 for t in ts if t["status"] == s), 11) for s in statuses)
        print(pad(eid, 5), pad(title, 30), pad(len(ts), 5), pad(total, 6), pad(f"{pad(bar, 8)}{pct}", 12), counts)
    remain = sum(t["estimate_min"] for t in data["tasks"] if t["status"] != "done")
    print(f"\n남은 작업: {remain}분 ({remain / 60:.1f}시간) · 지금 시작 가능: {len(ready_tasks(data))}개")


def cmd_validate(a, data):
    errors = validate(data)
    if errors:
        print("검증 실패:")
        for e in errors:
            print("  - " + e)
        sys.exit(1)
    print(f"문제 없음: 태스크 {len(data['tasks'])}개, 에픽 {len(data['epics'])}개")


def cmd_epic(a, data):
    if a.action == "list":
        for e in data["epics"]:
            n = sum(1 for t in data["tasks"] if t["epic"] == e["id"])
            print(pad(e["id"], 5), pad(e["title"], 36), f"{n}개")
    elif a.action == "add":
        if not a.epic_id or not a.title:
            sys.exit("사용법: epic add <ID> <제목>")
        eid = a.epic_id.upper()
        if eid in {e["id"] for e in data["epics"]}:
            sys.exit(f"오류: {eid}는 이미 있습니다")
        data["epics"].append({"id": eid, "title": a.title})
        save(a.file, data)
        print(f"에픽 추가됨: {eid} {a.title}")
    elif a.action == "rename":
        if not a.epic_id or not a.title:
            sys.exit("사용법: epic rename <ID> <새 제목>")
        e = next((e for e in data["epics"] if e["id"] == a.epic_id.upper()), None)
        if not e:
            sys.exit(f"오류: 없는 에픽 {a.epic_id}")
        e["title"] = a.title
        save(a.file, data)
        print(f"에픽 이름 변경: {e['id']} {a.title}")


# ---------- 인자 ----------
def build_parser():
    p = argparse.ArgumentParser(prog="backlog", description="backlog.json 조회·수정·추가 도구")
    p.add_argument("--file", "-f", default=os.environ.get("BACKLOG_FILE", "backlog.json"), help="백로그 파일 경로")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("list", aliases=["ls"], help="태스크 목록")
    s.add_argument("--epic", "-e", nargs="+", help="에픽 필터 (여러 개 가능)")
    s.add_argument("--status", "-s", nargs="+", help="상태 필터")
    s.add_argument("--ready", "-r", action="store_true", help="지금 시작 가능한 것만")
    s.add_argument("--search", "-q", help="제목·설명 검색")
    s.add_argument("--json", action="store_true", help="JSON으로 출력")
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("next", help="의존이 모두 끝나 지금 시작할 수 있는 태스크")
    s.add_argument("--limit", "-n", type=int)
    s.set_defaults(fn=cmd_next)

    s = sub.add_parser("show", help="태스크 상세")
    s.add_argument("ids", nargs="+")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser("add", help="태스크 추가 (ID는 에픽 안에서 자동 부여)")
    s.add_argument("--epic", "-e", required=True)
    s.add_argument("--title", "-t", required=True)
    s.add_argument("--min", "-m", type=int, required=True, help="예상 분 (최대값은 rules.max_task_minutes)")
    s.add_argument("--desc", "-d")
    s.add_argument("--dep", nargs="+", help="의존 태스크 ID (공백 또는 쉼표 구분)")
    s.add_argument("--ac", action="append", help="완료 기준 (여러 번 지정 가능)")
    s.add_argument("--status", default="todo")
    s.add_argument("--id", help="ID 직접 지정")
    s.set_defaults(fn=cmd_add)

    s = sub.add_parser("update", aliases=["edit"], help="태스크 수정")
    s.add_argument("id")
    s.add_argument("--title", "-t")
    s.add_argument("--desc", "-d")
    s.add_argument("--min", "-m", type=int)
    s.add_argument("--epic", "-e")
    s.add_argument("--status")
    s.add_argument("--add-dep", nargs="+")
    s.add_argument("--rm-dep", nargs="+")
    s.add_argument("--set-dep", nargs="*", help="의존 목록 통째로 교체 (값 없이 쓰면 비움)")
    s.add_argument("--add-ac", action="append", help="완료 기준 추가")
    s.add_argument("--set-ac", nargs="*", help="완료 기준 통째로 교체")
    s.set_defaults(fn=cmd_update)

    s = sub.add_parser("status", help="상태 변경 (여러 개 가능)")
    s.add_argument("ids", nargs="+", help="태스크 ID들, 마지막 값이 상태")
    s.add_argument("--force", action="store_true", help="의존 미완료여도 변경")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("rm", aliases=["delete"], help="태스크 삭제")
    s.add_argument("id")
    s.add_argument("--force", action="store_true", help="이 태스크에 대한 의존도 함께 제거")
    s.set_defaults(fn=cmd_rm)

    s = sub.add_parser("stats", help="에픽별 진행 현황")
    s.set_defaults(fn=cmd_stats)

    s = sub.add_parser("validate", help="규칙 검사 (시간 상한, 의존, 순환, 상태)")
    s.set_defaults(fn=cmd_validate)

    s = sub.add_parser("epic", help="에픽 관리: list | add <ID> <제목> | rename <ID> <제목>")
    s.add_argument("action", choices=["list", "add", "rename"])
    s.add_argument("epic_id", nargs="?")
    s.add_argument("title", nargs="?")
    s.set_defaults(fn=cmd_epic)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    if a.cmd == "status":
        if len(a.ids) < 2:
            sys.exit("사용법: status <ID> [<ID> ...] <상태>")
        a.status = a.ids.pop()
    data = load(a.file)
    data.setdefault("tasks", []); data.setdefault("epics", [])
    a.fn(a, data)


if __name__ == "__main__":
    try:
        import signal
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # `| head` 등에 연결해도 오류 없이 종료
    except (AttributeError, ValueError):
        pass  # Windows
    main()
