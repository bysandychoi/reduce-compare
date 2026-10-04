"""FastAPI 앱 진입점 (T011).

실행:
    cd backend && uvicorn app.main:app --reload --port 8000
확인:
    curl http://127.0.0.1:8000/health
"""
from fastapi import FastAPI
from pydantic import BaseModel

from app import __version__
from app.api.boxplots import router as boxplots_router
from app.api.category_ratios import router as category_ratios_router
from app.api.columns import router as columns_router
from app.api.correlation_networks import router as correlation_networks_router
from app.api.distributions import router as distributions_router
from app.api.groups import router as groups_router
from app.api.jobs import router as jobs_router
from app.api.results import router as results_router
from app.api.runs import router as runs_router
from app.api.visualizations import router as visualizations_router

app = FastAPI(
    title="Reduce & Compare API",
    version=__version__,
    description="대규모 표 데이터를 축소하고 원본과의 유사도를 계산하는 로컬 API",
)
app.include_router(jobs_router)
app.include_router(groups_router)
app.include_router(columns_router)
app.include_router(runs_router)
app.include_router(results_router)
app.include_router(visualizations_router)
app.include_router(distributions_router)
app.include_router(boxplots_router)
app.include_router(category_ratios_router)
app.include_router(correlation_networks_router)


class Health(BaseModel):
    """상태 확인 응답."""

    status: str
    version: str


@app.get("/health", response_model=Health, summary="서버 상태 확인")
def health() -> Health:
    return Health(status="ok", version=__version__)
