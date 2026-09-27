"""Health response schemas."""

from typing import Literal

from pydantic import BaseModel


class ServiceHealth(BaseModel):
    status: Literal["ok"]
    service: str
    environment: str


class DependencyHealth(BaseModel):
    status: Literal["ok"]
    s3: Literal["reachable"]
    athena: Literal["reachable"]
