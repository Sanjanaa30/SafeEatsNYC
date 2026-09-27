"""Whitelisted SQL helpers shared by dashboard services."""

import re

from fastapi import HTTPException, status

BOROUGHS = ("BRONX", "BROOKLYN", "MANHATTAN", "QUEENS", "STATEN ISLAND")
GRADES = ("A", "B", "C")


def normalized_borough(value: str | None) -> str | None:
    if value is None:
        return None
    borough = " ".join(value.strip().upper().split())
    if borough not in BOROUGHS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Borough must be one of the five NYC boroughs.",
        )
    return borough


def sql_string(value: str) -> str:
    """Quote one validated or length-bounded Athena string literal."""

    return "'" + value.replace("'", "''") + "'"


def sql_in(values: list[str]) -> str:
    return "(" + ", ".join(sql_string(value) for value in values) + ")"


def validated_key(value: str, label: str) -> str:
    if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{label} is invalid.",
        )
    return value
