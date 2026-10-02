"""훅 스크립트 공통 기능: 설정, 입력, 출력, git, 명령 실행, 팝업."""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

HOOK_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(os.path.dirname(HOOK_DIR))
STATE_DIR = os.path.join(HOOK_DIR, ".state")


def config():
    with open(os.path.join(HOOK_DIR, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def read_input():
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}


def emit(obj):
    """JSON을 stdout으로 내보내고 종료 (exit 0)."""
    print(json.dumps(obj, ensure_ascii=False))
    sys.exit(0)


def block_stop(message):
    """Stop 훅에서 종료를 막고 Claude에게 이유를 전달."""
    print(message, file=sys.stderr)
    sys.exit(2)


def rel(path):
    p = os.path.abspath(os.path.join(PROJECT, path)) if not os.path.isabs(path) else path
    return os.path.relpath(p, PROJECT).replace(os.sep, "/")


# ---------- 명령 실행 ----------
def _decode_best_effort(raw):
    """UTF-8(우리 도구들)부터 시도하고, 안 되면 OS 로캘(Windows cp949 등 OS 자체 메시지)로 시도한다."""
    if not raw:
        return ""
    candidates = ["utf-8"]
    if os.name == "nt":
        candidates.append("mbcs")  # 현재 Windows ANSI 코드페이지 (cp949 등)
    for enc in candidates:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def run(cmd, cwd=None, timeout=600):
    """(returncode, 출력) 반환. 명령이 없으면 127."""
    args = shlex.split(cmd, posix=(os.name != "nt")) if isinstance(cmd, str) else cmd
    exe = shutil.which(args[0])
    if not exe:
        return 127, f"명령을 찾을 수 없습니다: {args[0]}"
    args = [exe, *args[1:]]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        p = subprocess.run(args, cwd=cwd or PROJECT, capture_output=True, timeout=timeout, env=env)
        text = _decode_best_effort(p.stdout) + _decode_best_effort(p.stderr)
        return p.returncode, text.strip()
    except subprocess.TimeoutExpired:
        return 124, f"시간 초과 ({timeout}초): {cmd}"


def tail(text, n=40):
    lines = text.splitlines()
    return "\n".join(lines[-n:]) if len(lines) > n else text


# ---------- git ----------
def git(*args):
    return run(["git", *args])


def is_git_repo():
    return git("rev-parse", "--is-inside-work-tree")[0] == 0


def current_branch():
    code, out = git("symbolic-ref", "--short", "HEAD")
    if code == 0:
        return out
    code, out = git("rev-parse", "--short", "HEAD")
    return f"(detached {out})" if code == 0 else None


def head_file(path):
    code, out = git("show", f"HEAD:{path}")
    return out if code == 0 else None


# ---------- 경로 패턴 ----------
def glob_regex(pattern):
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"; i += 3
        elif pattern.startswith("**", i):
            out += ".*"; i += 2
        elif pattern[i] == "*":
            out += "[^/]*"; i += 1
        elif pattern[i] == "?":
            out += "[^/]"; i += 1
        else:
            out += re.escape(pattern[i]); i += 1
    return re.compile("^" + out + "$")


def match_glob(path, pattern):
    return bool(glob_regex(pattern).match(path))


# ---------- 상태 파일 ----------
def state_get(name, default=None):
    try:
        with open(os.path.join(STATE_DIR, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def state_set(name, value):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(os.path.join(STATE_DIR, name), "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False)


# ---------- 품질 게이트 (lint + build) ----------
def quality_gate(cfg):
    """(통과 여부, 요약, 실패 상세) 반환."""
    results, failures = [], []
    for step in cfg.get("quality_gate", []):
        if not os.path.exists(os.path.join(PROJECT, step["requires"])):
            results.append(f"- {step['name']}: 건너뜀 ({step['requires']} 없음)")
            continue
        code, out = run(step["cmd"], cwd=os.path.join(PROJECT, step.get("cwd", ".")))
        if code == 0:
            results.append(f"- {step['name']}: 통과")
        else:
            results.append(f"- {step['name']}: 실패 (exit {code})")
            failures.append(f"### {step['name']} · `{step['cmd']}`\n{tail(out)}")
    return not failures, "\n".join(results), "\n\n".join(failures)


# ---------- 팝업 ----------
def _esc_as(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def popup(title, message, style="notification"):
    """OS 알림을 띄운다. 실패해도 조용히 넘어간다."""
    message = message.replace("\n", " ")[:220]
    try:
        if sys.platform == "darwin":
            if style == "dialog":
                script = f'display dialog "{_esc_as(message)}" with title "{_esc_as(title)}" buttons {{"확인"}} giving up after 60'
            else:
                script = f'display notification "{_esc_as(message)}" with title "{_esc_as(title)}" sound name "Glass"'
            subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform.startswith("win"):
            ps = ("Add-Type -AssemblyName System.Windows.Forms;"
                  f"[System.Windows.Forms.MessageBox]::Show('{message.replace(chr(39), chr(39) * 2)}',"
                  f"'{title.replace(chr(39), chr(39) * 2)}')")
            subprocess.Popen(["powershell", "-NoProfile", "-Command", ps],
                             creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        elif shutil.which("notify-send"):
            subprocess.Popen(["notify-send", "-u", "normal", title, message])
        elif shutil.which("zenity"):
            subprocess.Popen(["zenity", "--info", f"--title={title}", f"--text={message}"])
    except OSError:
        pass
