#!/usr/bin/env python3
"""PostToolUse(Edit|Write|MultiEdit): 줄 수 한도 확인 + 수정한 파일 lint.

- 파일·함수 줄 수가 한도의 85% 이상이면 경고, 100%를 넘으면 다시 작업하라고 되돌려 보낸다.
- config의 lint_on_edit 경로에 해당하는 파일은 수정 직후 lint를 돌리고, 오류가 있으면 고치라고 되돌려 보낸다.
"""
import ast
import os
import re

from _common import PROJECT, config, emit, match_glob, read_input, rel, run, tail

FUNC_TS = re.compile(r"^\s*(export\s+)?(default\s+)?(async\s+)?(function\s+(\w+)|(const|let)\s+(\w+)\s*=\s*(async\s*)?\(?[^=]*\)?\s*=>)")


def count(lines, mode):
    return sum(1 for ln in lines if ln.strip()) if mode == "non_blank" else len(lines)


def py_functions(src):
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    return [(n.name, n.lineno, n.end_lineno) for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def ts_functions(lines):
    found = []
    for i, ln in enumerate(lines):
        m = FUNC_TS.match(ln)
        if not m or "{" not in "".join(lines[i:i + 3]):
            continue
        depth, started = 0, False
        for j in range(i, len(lines)):
            depth += lines[j].count("{") - lines[j].count("}")
            started = started or "{" in lines[j]
            if started and depth <= 0:
                found.append((m.group(5) or m.group(7), i + 1, j + 1))
                break
    return found


def check_limits(path, text, cfg):
    ll = cfg.get("line_limits", {})
    rule = next((r for r in ll.get("rules", []) if match_glob(path, r["glob"])), None)
    if not rule:
        return [], []
    mode, warn = ll.get("count", "non_blank"), ll.get("warn_ratio", 0.85)
    lines = text.splitlines()
    items = [(f"파일 {path}", count(lines, mode), rule["max_file"])]
    if rule.get("max_function"):
        funcs = py_functions(text) if path.endswith(".py") else (
            ts_functions(lines) if path.endswith((".ts", ".tsx", ".js", ".jsx")) else [])
        for name, a, b in funcs:
            items.append((f"함수 {name}() {path}:{a}", count(lines[a - 1:b], mode), rule["max_function"]))
    warns, overs = [], []
    for label, n, mx in items:
        ratio = n / mx
        line = f"- {label}: {n}/{mx}줄 ({ratio * 100:.0f}%) · 규칙 '{rule['name']}'"
        if ratio > 1:
            overs.append(line)
        elif ratio >= warn:
            warns.append(line)
    return warns, overs


def lint_file(path, cfg):
    for spec in cfg.get("lint_on_edit", []):
        if not any(match_glob(path, g) for g in spec["glob"]):
            continue
        cwd = os.path.join(PROJECT, spec.get("cwd", "."))
        if not os.path.isdir(cwd):
            continue
        code, out = run(spec["cmd"].format(file=os.path.join(PROJECT, path)), cwd=cwd, timeout=120)
        if code == 127:
            return f"lint 도구가 없습니다 ({spec['cmd'].split()[0]}). 설치 후 다시 시도하세요."
        if code != 0:
            return f"`{spec['cmd'].format(file=path)}` 실패:\n{tail(out, 30)}"
    return None


def main():
    data = read_input()
    fp = (data.get("tool_input") or {}).get("file_path")
    if not fp:
        return
    path = rel(fp)
    full = os.path.join(PROJECT, path)
    if path.startswith("..") or not os.path.isfile(full):
        return
    cfg = config()
    with open(full, encoding="utf-8", errors="replace") as f:
        text = f.read()

    warns, overs = check_limits(path, text, cfg)
    lint_err = lint_file(path, cfg)

    problems = []
    if overs:
        problems.append("줄 수 한도(100%)를 넘었습니다. 기능을 나누거나 함수를 분리해서 다시 작업하세요:\n" + "\n".join(overs))
    if lint_err:
        problems.append("lint 오류를 고치세요:\n" + lint_err)
    if problems:
        reason = "\n\n".join(problems + (["한도 85% 이상(경고):\n" + "\n".join(warns)] if warns else []))
        emit({"decision": "block", "reason": reason, "systemMessage": f"⛔ {path}: " + reason.splitlines()[0]})
    if warns:
        msg = "줄 수가 한도의 85% 이상입니다. 더 늘리기 전에 분리를 고려하세요:\n" + "\n".join(warns)
        emit({"systemMessage": f"⚠ {path}: 줄 수 한도 85% 이상",
              "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}})


if __name__ == "__main__":
    main()
