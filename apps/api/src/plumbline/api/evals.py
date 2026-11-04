"""How the served answers held up in production (Lane D, for Lane P's nightly online
evaluation, P8b): the last nights' faithfulness on a sample of real answers, for the public
/evals page. Each night is one eval_runs row (`online-<day>`, golden file `production`)
whose summary P8b writes; it holds counts and a rate, never a question or an answer.

    GET /api/evals/online   the last NIGHTS nights, newest first ([] before the first)
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Final

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plumbline.api.problems import MEDIA_TYPE
from plumbline.db.models import PUBLIC_TENANT, EvalRunRow
from plumbline.db.session import tenant_session

NIGHTS: Final = 14
PREFIX: Final = "online-"
GOLDEN_FILE: Final = "production"
MAX_AGE_S: Final = 3600  # a new night arrives once a day, at 04:15 UTC

router = APIRouter(prefix="/api/evals", tags=["evals"])

Share = Annotated[float, Field(ge=0, le=1)]


class OnlineNight(BaseModel):
    """One night's judged sample of the previous day's answers."""

    day: date  # the UTC day whose answers were judged
    config_name: str  # the configuration that served most of them
    answered: int = Field(ge=0)  # the day's answers that could be judged
    sampled: int = Field(ge=0)
    judged: int = Field(ge=0)
    faithful: int = Field(ge=0)
    faithfulness: Share | None  # faithful / judged; None when nothing was judged
    interval_95: tuple[Share, Share] | None  # Wilson, None when nothing was judged


def night(row: EvalRunRow) -> OnlineNight | None:
    """The night a row records, or None when its summary is not P8b's shape."""
    summary: Any = row.summary
    if not isinstance(summary, dict):
        return None
    try:
        return OnlineNight.model_validate({**summary, "config_name": row.config_name})
    except ValidationError:
        return None


@router.get(
    "/online",
    responses={
        503: {
            "description": "The results cannot be read right now (the database is down).",
            "content": {MEDIA_TYPE: {"schema": {"$ref": "#/components/schemas/Problem"}}},
        }
    },
)
async def online(request: Request, response: Response) -> list[OnlineNight]:
    sessions: async_sessionmaker[AsyncSession] = request.app.state.sessions
    query = (
        select(EvalRunRow)
        .where(EvalRunRow.golden_file == GOLDEN_FILE, EvalRunRow.run_id.startswith(PREFIX))
        .order_by(EvalRunRow.run_id.desc())  # online-YYYY-MM-DD sorts by day
        .limit(NIGHTS)
    )
    try:
        async with tenant_session(sessions, PUBLIC_TENANT) as session:
            rows = list(await session.scalars(query))
    except (SQLAlchemyError, OSError) as exc:
        raise HTTPException(503, "The evaluation results cannot be read now.") from exc
    response.headers["Cache-Control"] = f"public, max-age={MAX_AGE_S}"
    return [found for row in rows if (found := night(row)) is not None]
