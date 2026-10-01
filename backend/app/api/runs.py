"""축소 파이프라인 백그라운드 실행 API (T062)."""
from __future__ import annotations

import json
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.columns import _selected_names
from app.api.groups import calculate_groups, job_directory, saved_decisions
from app.core.pipeline import run_folder_pipeline
from app.models.results import PipelineResults

router = APIRouter(tags=["jobs"])
EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="reduction")
RUNS: dict[str, Future] = {}
RUNS_LOCK = threading.Lock()


class RunOptions(BaseModel):
    target: float = Field(default=85, ge=0, le=100)
    seed: int = 0
    projection_method: Literal["pca", "umap"] = "pca"
    projection_dimensions: Literal[2, 3] = 2


class RunAccepted(BaseModel):
    job_id: str
    state: Literal["queued"]


def _write_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _configuration(job_id: str) -> tuple[Path, dict[str, list[str]], dict[str, bool]]:
    directory, groups = calculate_groups(job_id)
    selections = {
        f"group-{index}": _selected_names(directory, f"group-{index}", group.columns)
        for index, group in enumerate(groups, start=1)
    }
    return directory, selections, saved_decisions(directory)


def _execute(job_id: str, directory: Path, options: RunOptions,
             selections: dict[str, list[str]], decisions: dict[str, bool]) -> None:
    try:
        _write_json(directory / "run.json", {"state": "running"})
        core = run_folder_pipeline(
            str(directory / "uploads"), target=options.target, seed=options.seed,
            projection_method=options.projection_method,
            projection_dimensions=options.projection_dimensions,
            selections=selections, merge_decisions=decisions,
        )
        core.folder = "uploads"
        result = json.loads(PipelineResults.from_core(core).model_dump_json())
        _write_json(directory / "result.json", result)
        _write_json(directory / "run.json", {"state": "done"})
    except Exception as exc:
        _write_json(directory / "run.json", {"state": "failed", "error": str(exc)})


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
        _write_json(directory / "run.json", {"state": "queued"})
        RUNS[job_id] = EXECUTOR.submit(
            _execute, job_id, directory, resolved, selections, decisions,
        )
    return RunAccepted(job_id=job_id, state="queued")
