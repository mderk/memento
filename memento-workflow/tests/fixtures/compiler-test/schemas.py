"""Pydantic output schemas for compiler test workflow."""

from pydantic import BaseModel


class SummaryOutput(BaseModel):
    total_items: int
    status: str
    notes: str = ""
