"""축소 파이프라인 백그라운드 실행 API (T062)."""
from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Literal

import numpy as np
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, ValidationError

from app.api.columns import _selected_names
from app.api.groups import calculate_groups, job_directory, saved_decisions
from app.core.pipeline import run_folder_pipeline
from app.models.results import PipelineResults

router = APIRouter(tags=["jobs"])
EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="reduction")
RUNS: dict[str, Future] = {}
RUNS_LOCK = threading.Lock()
LOCAL_PATH = re.compile(
    r"(?:[A-Za-z]:[\\/][^,\n\r;)'\"]+|(?<![\w.])/(?:[^/\s]+/)+[^,\s;)'\"]+)"
)


class RunOptions(BaseModel):
    target: float = Field(default=85, ge=0, le=100)
    seed: int = 0
    projection_method: Literal["pca", "umap"] = "pca"
    projection_dimensions: Literal[2, 3] = 2


class RunAccepted(BaseModel):
    job_id: str
    state: Literal["queued"]


class RunStatus(BaseModel):
    job_id: str
    state: Literal["idle", "queued", "running", "done", "failed"]
    progress: int = Field(ge=0, le=100)
    stage: str
    error: str | None = None


class PipelineProgressWriter:
    """Core pipeline progress callback that persists monotonic job state."""

    def __init__(self, directory: Path, progress: int = 20,
                 stage: str = "파일 및 스키마 확인 중") -> None:
        self.directory = directory
        self.progress = progress
        self.stage = stage

    def __call__(self, stage: str, fraction: float) -> None:
        bounded = max(0.0, min(1.0, fraction))
        self.progress = max(self.progress, min(85, 20 + round(65 * bounded)))
        self.stage = stage
        _write_json(self.directory / "run.json", {
            "state": "running", "progress": self.progress, "stage": self.stage,
        })


def _write_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    for attempt in range(5):
        try:
            temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.01)


def _failure_message(stage: str, error: Exception) -> str:
    if isinstance(error, UnicodeError):
        reason = "입력 파일의 인코딩을 읽을 수 없습니다"
    elif isinstance(error, ValueError):
        text = str(error).strip()
        first_line = text.splitlines()[0][:300] if text else "알 수 없는 오류"
        reason = LOCAL_PATH.sub("<로컬 경로>", first_line)
    elif isinstance(error, OSError):
        reason = "입력 또는 결과 파일을 읽고 쓰지 못했습니다"
    else:
        reason = "내부 처리 오류가 발생했습니다"
    return f"{stage} 단계에서 실패했습니다: {reason}"


def _save_reduced_frames(directory: Path, groups: list) -> None:
    """완료 그룹 순서와 같은 파일명으로 축소 프레임을 원자적으로 저장한다."""
    reduced_dir = directory / "reduced"
    reduced_dir.mkdir(exist_ok=True)
    for index, group in enumerate(groups):
        temporary = reduced_dir / f"group-{index + 1}.csv.tmp"
        group.chosen.frame.to_csv(temporary, index=False, encoding="utf-8-sig")
        temporary.replace(reduced_dir / f"group-{index + 1}.csv")


def _save_projection_sources(directory: Path, groups: list) -> None:
    """그래프 방식 전환용 특징 행렬과 대표 행 가중치를 성공 그룹 순서로 저장한다."""
    source_dir = directory / "projection-source"
    source_dir.mkdir(exist_ok=True)
    for index, group in enumerate(groups):
        original, reduced = group.projection_source
        with (source_dir / f"group-{index + 1}.npz").open("wb") as output:
            np.savez_compressed(
                output, original=original, reduced=reduced,
                weights=group.chosen.reduction.weights,
            )


def read_run_status(directory: Path, job_id: str) -> RunStatus:
    path = directory / "run.json"
    transient_error = None
    for attempt in range(5):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return RunStatus(job_id=job_id, **payload)
        except (OSError, json.JSONDecodeError) as error:
            transient_error = error
            if attempt < 4:
                time.sleep(0.01)
        except (TypeError, ValidationError) as error:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR, "작업 상태를 읽을 수 없습니다"
            ) from error
    raise HTTPException(
        status.HTTP_500_INTERNAL_SERVER_ERROR, "작업 상태를 읽을 수 없습니다"
    ) from transient_error


def _configuration(job_id: str) -> tuple[Path, dict[str, list[str]], dict[str, bool]]:
    directory, groups = calculate_groups(job_id)
    selections = {
        f"group-{index}": _selected_names(directory, f"group-{index}", group.columns)
        for index, group in enumerate(groups, start=1)
    }
    return directory, selections, saved_decisions(directory)


def _write_failed_state(directory: Path, error: Exception, progress: int,
                        stage: str, tracker: PipelineProgressWriter | None) -> None:
    if tracker and tracker.progress > progress:
        progress, stage = tracker.progress, tracker.stage
    _write_json(directory / "run.json", {
        "state": "failed", "progress": progress, "stage": "실패",
        "error": _failure_message(stage, error),
    })


def _execute(job_id: str, directory: Path, options: RunOptions,
             selections: dict[str, list[str]], decisions: dict[str, bool]) -> None:
    progress = 10
    stage = "파이프라인 준비"
    tracker = None
    try:
        _write_json(directory / "run.json", {
            "state": "running", "progress": progress, "stage": stage,
        })
        progress = 20
        stage = "파일 및 스키마 확인 중"
        _write_json(directory / "run.json", {
            "state": "running", "progress": progress, "stage": stage,
        })
        tracker = PipelineProgressWriter(directory, progress, stage)
        core = run_folder_pipeline(
            str(directory / "uploads"), target=options.target, seed=options.seed,
            projection_method=options.projection_method,
            projection_dimensions=options.projection_dimensions,
            selections=selections, merge_decisions=decisions,
            progress_callback=tracker,
        )
        core.folder = "uploads"
        progress = 90
        stage = "결과 저장"
        _write_json(directory / "run.json", {
            "state": "running", "progress": progress, "stage": stage,
        })
        _save_reduced_frames(directory, core.groups)
        _save_projection_sources(directory, core.groups)
        result = json.loads(PipelineResults.from_core(core).model_dump_json())
        _write_json(directory / "result.json", result)
        _write_json(directory / "run.json", {
            "state": "done", "progress": 100, "stage": "완료",
        })
    except Exception as exc:
        _write_failed_state(directory, exc, progress, stage, tracker)


@router.post("/jobs/{job_id}/run", response_model=RunAccepted,
             status_code=status.HTTP_202_ACCEPTED)
def start_run(job_id: str, options: RunOptions | None = None) -> RunAccepted:
    directory = job_directory(job_id)
    resolved = options or RunOptions()
    with RUNS_LOCK:
        current = RUNS.get(job_id)
        if current is not None and not current.done():
            raise HTTPException(status.HTTP_409_CONFLICT, "이미 실행 중인 작업입니다")
        directory, selections, decisions = _configuration(job_id)
        _write_json(directory / "run.json", {
            "state": "queued", "progress": 0, "stage": "대기",
        })
        RUNS[job_id] = EXECUTOR.submit(
            _execute, job_id, directory, resolved, selections, decisions,
        )
    return RunAccepted(job_id=job_id, state="queued")


@router.get("/jobs/{job_id}/status", response_model=RunStatus)
def get_run_status(job_id: str) -> RunStatus:
    directory = job_directory(job_id)
    path = directory / "run.json"
    if not path.is_file():
        return RunStatus(job_id=job_id, state="idle", progress=0, stage="실행 전")
    return read_run_status(directory, job_id)
