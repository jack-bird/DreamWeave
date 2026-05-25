from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


PROTOCOL_VERSION = "0.1"


def make_request_id(prefix: str = "req") -> str:
    return f"{prefix}_{uuid4().hex}"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def make_message(message_type: str, payload: dict[str, Any], request_id: str | None = None) -> dict[str, Any]:
    return {
        "type": message_type,
        "request_id": request_id or make_request_id(),
        "timestamp": utc_now_iso(),
        "payload": payload,
    }


def make_error_message(
    error_code: str,
    message: str,
    request_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error_code": error_code,
        "message": message,
    }
    if detail:
        payload["detail"] = detail

    return make_message("error", payload, request_id=request_id)
