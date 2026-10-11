"""Shared refusal type for the dispatch lane."""

from __future__ import annotations


class LaneError(Exception):
    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code
