"""도구 중립 훅 공통 기능.

Claude Code와 Codex CLI 양쪽에서 같은 스크립트를 그대로 쓸 수 있도록
- 프로젝트 루트 자동 탐지
- 두 도구의 서로 다른 stdin 모양(tool_input)에서 파일 경로/셸 명령 뽑기
- 설정 읽기, 명령 실행, git, 팝업, 상태 저장
을 표준 라이브러리만으로 제공한다.
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

HOOK_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(HOOK_DIR, ".state")

# 콘솔 코드페이지(cp949 등)와 무관하게 항상 UTF-8로 내보낸다 — Claude Code/Codex 둘 다
# stdout/stderr을 UTF-8로 읽는다고 가정하므로, 이 프로세스의 출력 인코딩을 강제로 맞춘다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

# apply_patch(Codex)가 쓰는 V4A 패치 봉투 마커
_PATCH_BEGIN = "*** Begin Patch"
_PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.M)
_PATCH_MOVE_RE = re.compile(r"^\*\*\* Move to: (.+)$", re.M)


# ---------- 입출력 ----------
def read_input():
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}


def emit(obj):
    """JSON을 stdout으로 내보내고 종료 (exit 0). Claude·Codex 둘 다 같은 모양을 읽는다."""
    print(json.dumps(obj, ensure_ascii=False))
    sys.exit(0)


def block_stop(message):
    """Stop 훅에서 종료를 막고 에이전트에게 이유를 전달."""
    print(message, file=sys.stderr)
    sys.exit(2)


# ---------- 프로젝트 루트 ----------
def _script_root():
    """hooks/ 스크립트 위치의 상위 폴더 = 항상 프로젝트 루트 (레이아웃으로 보장)."""
    return os.path.dirname(HOOK_DIR)


def project_root(data=None):
    """CLAUDE_PROJECT_DIR → 스크립트 위치 → stdin의 cwd(Codex) → git 루트 순으로 찾는다."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and os.path.isdir(env):
        return os.path.abspath(env)
    root = _script_root()
    if os.path.isfile(os.path.join(root, "backlog.py")):
        return root
    cwd = (data or {}).get("cwd")
    if cwd and os.path.isdir(cwd):
        return os.path.abspath(cwd)
    code, out = _run_raw(["git", "rev-parse", "--show-toplevel"], cwd=root)
    if code == 0 and out.strip():
        return out.strip()
    return root


PROJECT = project_root()


def config():
    with open(os.path.join(HOOK_DIR, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def rel(path):
    p = os.path.abspath(os.path.join(PROJECT, path)) if not os.path.isabs(path) else path
    return os.path.relpath(p, PROJECT).replace(os.sep, "/")


# ---------- 도구별 tool_input 모양 흡수 ----------
def extract_file_paths(tool_input):
    """Claude(file_path/notebook_path)와 Codex(apply_patch 패치 텍스트)에서 건드린 파일 경로 목록을 뽑는다.

    apply_patch 한 번 호출로 여러 파일이 바뀔 수 있어 리스트로 반환한다.
    """
    tool_input = tool_input or {}
    paths = []
    fp = tool_input.get("file_path") or tool_input.get("notebook_path")
    if fp:
        paths.append(fp)
    patch_values = [tool_input.get(key) for key in ("command", "patch", "input")]
    patch_values.extend(value for value in tool_input.values() if isinstance(value, str))
    for patch in dict.fromkeys(value for value in patch_values if isinstance(value, str)):
        if _PATCH_BEGIN not in patch:
            continue
        paths.extend(m.strip() for m in _PATCH_FILE_RE.findall(patch))
        paths.extend(m.strip() for m in _PATCH_MOVE_RE.findall(patch))
    return paths


def extract_shell_command(tool_input):
    """진짜 셸 명령이면 문자열을, apply_patch 패치 텍스트거나 없으면 None을 돌려준다."""
    cmd = (tool_input or {}).get("command")
    if not isinstance(cmd, str) or not cmd.strip():
        return None
    if _PATCH_BEGIN in cmd:
        return None
    return cmd


SPLIT_RE = re.compile(r"&&|\|\||;|\||\n")


def mentions_name(command, names):
    """셸 명령 조각 중 backlog.py CLI를 거치지 않고 이름을 언급하는 부분이 있으면 그 조각을 돌려준다."""
    cli_re = re.compile(r"(^|[\s/\"'])backlog\.py([\s\"']|$)")
    for seg in SPLIT_RE.split(command or ""):
        if any(n in seg for n in names) and not cli_re.search(seg):
            return seg.strip()
    return None


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


def _run_raw(args, cwd=None, timeout=600):
    exe = shutil.which(args[0])
    if not exe:
        return 127, f"명령을 찾을 수 없습니다: {args[0]}"
    args = [exe, *args[1:]]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout, env=env)
        text = _decode_best_effort(p.stdout) + _decode_best_effort(p.stderr)
        return p.returncode, text.strip()
    except subprocess.TimeoutExpired:
        return 124, f"시간 초과 ({timeout}초): {' '.join(args)}"


def run(cmd, cwd=None, timeout=600):
    """(returncode, 출력) 반환. 명령이 없으면 127."""
    args = shlex.split(cmd, posix=(os.name != "nt")) if isinstance(cmd, str) else cmd
    return _run_raw(args, cwd=cwd or PROJECT, timeout=timeout)


def tail(text, n=40):
    lines = text.splitlines()
    return "\n".join(lines[-n:]) if len(lines) > n else text


# ---------- git ----------
def git(*args):
    return run(["git", *args])


def is_git_repo():
    return git("rev-parse", "--is-inside-work-tree")[0] == 0


def has_remote():
    return is_git_repo() and bool(git("remote")[1].strip())


def has_upstream():
    return is_git_repo() and git("rev-parse", "--abbrev-ref", "@{u}")[0] == 0


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
    """(통과 여부, 요약, 실패 상세) 반환. requires 경로가 없으면 그 단계는 건너뛴다."""
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
    """OS 알림을 띄운다. 실패해도 조용히 넘어간다 (훅을 절대 실패시키지 않음)."""
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
            # DETACHED_PROCESS는 창(윈도 스테이션)까지 분리시켜 MessageBox가 안 뜨게 만든다 —
            # 콘솔 창만 숨기는 CREATE_NO_WINDOW를 쓴다.
            subprocess.Popen(["powershell", "-NoProfile", "-STA", "-Command", ps],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        elif shutil.which("notify-send"):
            subprocess.Popen(["notify-send", "-u", "normal", title, message])
        elif shutil.which("zenity"):
            subprocess.Popen(["zenity", "--info", f"--title={title}", f"--text={message}"])
    except OSError:
        pass
