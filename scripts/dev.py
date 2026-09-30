"""Run the local FastAPI and Vite development servers together."""

from __future__ import annotations

import ctypes
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


class BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", BasicLimitInformation),
        ("IoInfo", ctypes.c_byte * 48),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def kernel32() -> ctypes.WinDLL:
    library = ctypes.WinDLL("kernel32", use_last_error=True)
    library.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    library.CreateJobObjectW.restype = wintypes.HANDLE
    library.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    library.SetInformationJobObject.restype = wintypes.BOOL
    library.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    library.AssignProcessToJobObject.restype = wintypes.BOOL
    library.CloseHandle.argtypes = [wintypes.HANDLE]
    library.CloseHandle.restype = wintypes.BOOL
    return library


def create_windows_job() -> object | None:
    if sys.platform != "win32":
        return None
    library = kernel32()
    job = library.CreateJobObjectW(None, None)
    info = ExtendedLimitInformation()
    info.BasicLimitInformation.LimitFlags = 0x2000
    if not job or not library.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
        raise OSError(ctypes.get_last_error(), "Windows 프로세스 정리 설정에 실패했습니다")
    return job


def assign_to_job(job: object | None, process: subprocess.Popen[bytes]) -> None:
    if job is None:
        return
    if not kernel32().AssignProcessToJobObject(job, wintypes.HANDLE(process._handle)):
        raise OSError(ctypes.get_last_error(), "자식 프로세스 등록에 실패했습니다")


def close_job(job: object | None) -> None:
    if job is not None:
        kernel32().CloseHandle(job)


def backend_python() -> Path:
    executable = "python.exe" if sys.platform == "win32" else "python"
    candidate = BACKEND / ".venv" / ("Scripts" if sys.platform == "win32" else "bin") / executable
    return candidate if candidate.is_file() else Path(sys.executable)


def commands() -> list[tuple[str, list[str], Path]]:
    python = backend_python()
    node = shutil.which("node")
    vite = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"

    if node is None:
        raise RuntimeError("Node.js를 찾지 못했습니다. Node.js를 설치해 주세요.")
    if not vite.is_file():
        raise RuntimeError("프론트엔드 의존성이 없습니다. frontend에서 npm install을 실행해 주세요.")

    backend_check = subprocess.run(
        [str(python), "-c", "import fastapi, uvicorn"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    if backend_check.returncode:
        raise RuntimeError("백엔드 의존성이 없습니다. backend 가상환경에 requirements.txt를 설치해 주세요.")

    return [
        (
            "backend",
            [str(python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
            BACKEND,
        ),
        (
            "frontend",
            [node, str(vite), "--host", "127.0.0.1", "--port", "5173", "--strictPort"],
            FRONTEND,
        ),
    ]


def stop_processes(processes: list[subprocess.Popen[bytes]]) -> None:
    running = [process for process in processes if process.poll() is None]
    if sys.platform == "win32":
        for process in running:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        return

    for process in running:
        process.terminate()

    deadline = time.monotonic() + 5
    while running and time.monotonic() < deadline:
        running = [process for process in running if process.poll() is None]
        time.sleep(0.1)

    for process in running:
        process.kill()


def run() -> int:
    processes: list[subprocess.Popen[bytes]] = []
    names: dict[int, str] = {}
    job = create_windows_job()
    try:
        for name, command, cwd in commands():
            process = subprocess.Popen(command, cwd=cwd)
            processes.append(process)
            names[process.pid] = name
            assign_to_job(job, process)

        print("로컬 앱 실행 중: http://127.0.0.1:5173 (종료: Ctrl+C)", flush=True)
        while True:
            for process in processes:
                code = process.poll()
                if code is not None:
                    print(f"{names[process.pid]} 서버가 종료되었습니다 (code={code}).", file=sys.stderr)
                    return code or 1
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n로컬 앱을 종료합니다.", flush=True)
        return 0
    except (OSError, RuntimeError) as error:
        print(f"실행 실패: {error}", file=sys.stderr)
        return 1
    finally:
        stop_processes(processes)
        close_job(job)


if __name__ == "__main__":
    raise SystemExit(run())
