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


def make_result_message(
    task_id: str,
    content: str,
    model: str,
    worker_id: str,
    request_id: str | None = None,
    state_update: dict[str, Any] | None = None,
    agent_trace: dict[str, Any] | None = None,
    duration_ms: int | None = None,
) -> dict[str, Any]:
    """Create a successful task result message."""
    payload: dict[str, Any] = {
        "task_id": task_id,
        "status": "success",
        "content": content,
        "model": model,
        "worker_id": worker_id,
    }
    
    if state_update:
        payload["state_update"] = state_update
    
    if agent_trace:
        payload["agent_trace"] = agent_trace
    
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    
    return make_message("ai.result", payload, request_id=request_id)


def make_task_error_message(
    task_id: str,
    error_code: str,
    message: str,
    worker_id: str,
    request_id: str | None = None,
    retryable: bool = False,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a task error message."""
    payload: dict[str, Any] = {
        "task_id": task_id,
        "status": "error",
        "error_code": error_code,
        "message": message,
        "worker_id": worker_id,
        "retryable": retryable,
    }
    
    if detail:
        payload["detail"] = detail
    
    return make_message("ai.task_error", payload, request_id=request_id)
