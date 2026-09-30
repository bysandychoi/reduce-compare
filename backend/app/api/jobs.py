"""Upload-backed job creation endpoints."""

from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.core.ingest import CSV_SUFFIXES

router = APIRouter(tags=["jobs"])
JOB_ROOT = Path(__file__).resolve().parents[3] / "tmp" / "jobs"
CHUNK_SIZE = 1024 * 1024


class JobCreated(BaseModel):
    job_id: str
    files: list[str]


def safe_relative_name(filename: str | None) -> Path:
    raw = (filename or "").replace("\\", "/")
    parts = raw.split("/")
    path = PurePosixPath(raw)
    if not raw or raw.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "안전하지 않은 파일 경로입니다")
    if ":" in parts[0] or path.suffix.lower() not in CSV_SUFFIXES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "지원하지 않는 파일입니다")
    return Path(*path.parts)


async def save_upload(upload: UploadFile, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as output:
        while chunk := await upload.read(CHUNK_SIZE):
            output.write(chunk)
    await upload.close()


@router.post("/jobs", response_model=JobCreated, status_code=status.HTTP_201_CREATED)
async def create_job(files: Annotated[list[UploadFile], File()]) -> JobCreated:
    accepted = [
        upload
        for upload in files
        if Path(upload.filename or "").suffix.lower() in CSV_SUFFIXES
    ]
    if not accepted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "업로드할 표 파일이 없습니다")

    paths = [safe_relative_name(upload.filename) for upload in accepted]
    if len(set(paths)) != len(paths):
        raise HTTPException(status.HTTP_409_CONFLICT, "같은 경로의 파일이 중복되었습니다")

    job_id = uuid4().hex
    job_dir = JOB_ROOT / job_id
    try:
        for upload, relative in zip(accepted, paths, strict=True):
            await save_upload(upload, job_dir / "uploads" / relative)
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    return JobCreated(job_id=job_id, files=[path.as_posix() for path in paths])
