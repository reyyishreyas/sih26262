"""Bounded list pagination.

List endpoints return arrays for backwards compatibility, but every list is now
bounded and reports its unfiltered total in ``X-Total-Count``. A caller that needs
more pages can use ``offset``.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Query, Response


@dataclass(frozen=True)
class PageParams:
    limit: int
    offset: int


def pagination(
    limit: int = Query(100, ge=1, le=500, description="Maximum rows to return"),
    offset: int = Query(0, ge=0, le=1_000_000, description="Rows to skip"),
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


def apply_page(query, page: PageParams):
    return query.limit(page.limit).offset(page.offset)


def set_total(response: Response, total: int) -> None:
    response.headers["X-Total-Count"] = str(total)
