"""Canonical JSON, hashes, and the process exit used by the PROD matrix."""

from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA_VERSION = 1
TOOL_VERSION = "1"
QUESTION_LIMIT = 20000
READ_LIMIT = 500
WALL_SECONDS = 600
REQUEST_FAMILY = "authz"

SUMMARY_1 = "authorization only; questions are the explicit list, not exhaustive"
SUMMARY_2 = "not-asked: {not_asked}; names-not-enumerated: {names_not_enumerated}; named-subresource-not-asked: {named_subresource_not_asked}"

WRITE_VERBS = frozenset(
    {
        "create",
        "update",
        "patch",
        "delete",
        "deletecollection",
        "bind",
        "escalate",
        "impersonate",
        "approve",
        "use",
    }
)


class MatrixExit(Exception):
    """Stop the tool with a fixed exit code. Message goes to stderr."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def canonical_bytes(value: Any) -> bytes:
    """UTF-8 canonical JSON: sorted keys, separators ',' and ':', non-ASCII kept."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def dump_line(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def summary_line(not_asked: int, names_not_enumerated: int, named_subresource_not_asked: int) -> str:
    return SUMMARY_2.format(
        not_asked=not_asked,
        names_not_enumerated=names_not_enumerated,
        named_subresource_not_asked=named_subresource_not_asked,
    )


def question_id(request_hash: str) -> str:
    return "q-" + request_hash[:16]
