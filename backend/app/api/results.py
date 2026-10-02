"""완료된 축소 파이프라인 결과 조회 API (T064)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import ValidationError

from app.api.groups import job_directory
from app.api.runs import RunStatus, read_run_status
from app.models.results import PipelineResults

router = APIRouter(tags=["jobs"])


def _run_state(directory, job_id: str) -> RunStatus:
    path = directory / "run.json"
    if not path.is_file():
        raise HTTPException(status.HTTP_409_CONFLICT, "아직 축소를 실행하지 않았습니다")
    return read_run_status(directory, job_id)


@router.get("/jobs/{job_id}/result", response_model=PipelineResults)
def get_result(job_id: str) -> PipelineResults:
    directory = job_directory(job_id)
    run_state = _run_state(directory, job_id)
    if run_state.state == "failed":
        message = run_state.error or "알 수 없는 오류"
        raise HTTPException(status.HTTP_409_CONFLICT, f"축소 작업이 실패했습니다: {message}")
    if run_state.state != "done":
        raise HTTPException(status.HTTP_409_CONFLICT, "축소 작업이 아직 완료되지 않았습니다")

    path = directory / "result.json"
    if not path.is_file():
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "완료 결과 파일이 없습니다")
    try:
        return PipelineResults.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "완료 결과가 올바른 스키마가 아닙니다"
        ) from exc


@router.get("/jobs/{job_id}/result/{group_name}/download", response_class=FileResponse)
def download_result(job_id: str, group_name: str) -> FileResponse:
    """완료 결과에서 선택한 그룹의 축소 행을 CSV로 내려준다."""
    result = get_result(job_id)
    index = next((i for i, group in enumerate(result.groups) if group.name == group_name), None)
    if index is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "결과 그룹을 찾을 수 없습니다")
    path = job_directory(job_id) / "reduced" / f"group-{index + 1}.csv"
    if not path.is_file():
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "축소본 CSV 파일이 없습니다")
    return FileResponse(
        path, media_type="text/csv; charset=utf-8", filename=f"{group_name}-reduced.csv"
    )
