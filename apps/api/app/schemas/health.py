from typing import Literal

from pydantic import BaseModel


class DependencyStatus(BaseModel):
    ok: bool
    detail: str


class HealthRead(BaseModel):
    status: Literal["ok", "degraded"]
    postgres: DependencyStatus
    ollama: DependencyStatus
