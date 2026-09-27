"""Translate internal data-service failures into safe API responses."""

import logging
from collections.abc import Callable
from typing import TypeVar

from fastapi import HTTPException, status

LOGGER = logging.getLogger(__name__)
Result = TypeVar("Result")


def safely(load: Callable[[], Result]) -> Result:
    try:
        return load()
    except HTTPException:
        raise
    except Exception as error:
        LOGGER.exception("Dashboard data request failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Safety data is temporarily unavailable. Please try again shortly.",
        ) from error
