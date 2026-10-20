"""Errors as problem details (RFC 9457): every error the API answers is
application/problem+json with a title, the status and, where it helps, a detail and the
fields that failed validation, so the browser handles all of them one way.

An unexpected exception answers 500 with a fixed detail and is logged in full: its
message may hold internals and never reaches the client. Validation errors list each
field's location and message, never the exception's text, which can carry file paths.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from http import HTTPStatus
from typing import Final

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)

MEDIA_TYPE: Final = "application/problem+json"


class FieldError(BaseModel):
    loc: list[str | int]  # where the value was: ["body", "reasons", 0]
    msg: str
    type: str


class Problem(BaseModel):
    type: str = "about:blank"  # no problem type of our own yet: the status says it all
    title: str
    status: int
    detail: str | None = None
    errors: list[FieldError] | None = None  # for a 422, one per field that failed


def problem(
    status: int,
    detail: str | None = None,
    errors: list[FieldError] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = Problem(title=HTTPStatus(status).phrase, status=status, detail=detail, errors=errors)
    return JSONResponse(
        body.model_dump(mode="json", exclude_none=True),
        status_code=status,
        media_type=MEDIA_TYPE,
        headers=headers,
    )


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):  # registered for that class only
        raise exc
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail else None
    if detail == HTTPStatus(exc.status_code).phrase:
        detail = None  # Starlette's own 404 and 405 repeat the title
    return problem(exc.status_code, detail, headers=exc.headers)


async def _invalid(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):  # registered for that class only
        raise exc
    errors = [
        FieldError(loc=list(error["loc"]), msg=error["msg"], type=error["type"])
        for error in exc.errors()
    ]
    return problem(422, "The request is not valid.", errors)


async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unexpected error on %s %s", request.method, request.url.path)
    return problem(500, "Something went wrong on our side. Please try again.")


def install(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _invalid)
    app.add_exception_handler(Exception, _unexpected)
