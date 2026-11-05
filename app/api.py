"""REST API for historical Dota 2 match analytics."""

import os
from pathlib import Path
from typing import Annotated, Literal, Protocol, cast, runtime_checkable

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.history.domain import HistoricalMatch
from app.storage import SQLiteRepository


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "autopilot.db"
PROJECT_NAME = "Dota 2 Analytics"
PROJECT_DESCRIPTION = (
    "Команды, турниры и результаты сохранённых матчей. "
    "Отправная точка для исследования игры."
)
templates = Jinja2Templates(
    directory=[Path(__file__).with_name("templates"), Path(__file__).parent]
)
router = APIRouter(prefix="/api")


class MatchRepository(Protocol):
    def list_historical_matches(self) -> list[HistoricalMatch]: ...

    def get_historical_match_by_source(
        self, source: str, source_match_id: str
    ) -> HistoricalMatch | None: ...


@runtime_checkable
class MatchEconomyRepository(Protocol):
    def list_historical_match_economy(
        self, source: str, source_match_id: str
    ) -> list[dict[str, int | float]]: ...


class HistoricalEconomySnapshot(BaseModel):
    actual_game_time_seconds: float
    replay_tick: int
    radiant_net_worth: int
    dire_net_worth: int
    radiant_current_gold: int
    dire_current_gold: int
    radiant_total_xp: int
    dire_total_xp: int


@runtime_checkable
class MatchPOVRepository(Protocol):
    def list_historical_match_pov(
        self, source: str, source_match_id: str
    ) -> list[dict[str, int | float | str | None]]: ...


class HistoricalPOVSnapshot(BaseModel):
    actual_game_time_seconds: float
    replay_tick: int
    pov_team: Literal["RADIANT", "DIRE"]
    visible_enemy_count: int
    visible_enemy_with_position_count: int
    hidden_enemy_count: int
    own_team_spread: float | None
    nearest_visible_enemy_distance: float | None
    own_team_spread_status: str
    nearest_visible_enemy_status: str


def get_repository(request: Request) -> MatchRepository:
    return cast(MatchRepository, request.app.state.repository)


@router.get("/matches", response_model=list[HistoricalMatch])
def list_matches(
    repository: Annotated[MatchRepository, Depends(get_repository)],
) -> list[HistoricalMatch]:
    return repository.list_historical_matches()


@router.get("/matches/{source}/{source_match_id}", response_model=HistoricalMatch)
def get_match(
    source: str,
    source_match_id: str,
    repository: Annotated[MatchRepository, Depends(get_repository)],
) -> HistoricalMatch:
    match = repository.get_historical_match_by_source(source, source_match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Historical match not found.")
    return match


@router.get(
    "/matches/{source}/{source_match_id}/economy",
    response_model=list[HistoricalEconomySnapshot],
)
def get_match_economy(
    source: str,
    source_match_id: str,
    repository: Annotated[MatchRepository, Depends(get_repository)],
) -> list[dict[str, int | float]]:
    if not isinstance(repository, MatchEconomyRepository):
        raise HTTPException(
            status_code=501,
            detail="Historical match economy is not supported by this database backend.",
        )
    get_match(source, source_match_id, repository)
    return repository.list_historical_match_economy(source, source_match_id)


@router.get(
    "/matches/{source}/{source_match_id}/pov",
    response_model=list[HistoricalPOVSnapshot],
)
def get_match_pov(
    source: str,
    source_match_id: str,
    repository: Annotated[MatchRepository, Depends(get_repository)],
) -> list[dict[str, int | float | str | None]]:
    if not isinstance(repository, MatchPOVRepository):
        raise HTTPException(
            status_code=501,
            detail="Historical match POV is not supported by this database backend.",
        )
    get_match(source, source_match_id, repository)
    return repository.list_historical_match_pov(source, source_match_id)


def create_app(db_path: str | Path | None = None) -> FastAPI:
    """Create an application with the explicitly selected database backend."""
    backend = os.environ.get("DOTA_ANALYTICS_DB_BACKEND", "sqlite").strip().lower()
    repository: MatchRepository
    if backend == "sqlite":
        selected_path = (
            Path(db_path)
            if db_path is not None
            else Path(os.environ.get("DOTA_ANALYTICS_DB_PATH", DEFAULT_DB_PATH))
        )
        repository = SQLiteRepository(selected_path)
    elif backend == "postgresql":
        if db_path is not None:
            raise ValueError("db_path is only supported by the SQLite backend.")
        from app.storage.postgres import PostgresMatchRepository

        repository = PostgresMatchRepository.from_env()
    else:
        raise ValueError("DOTA_ANALYTICS_DB_BACKEND must be sqlite or postgresql.")
    application = FastAPI(
        title="Dota 2 Live Analytics & Prediction Platform",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    application.state.repository = repository
    application.include_router(router)

    @application.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "project_name": PROJECT_NAME,
                "project_description": PROJECT_DESCRIPTION,
            },
        )

    return application
