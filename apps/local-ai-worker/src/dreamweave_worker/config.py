from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerConfig:
    ollama_host: str
    ollama_model: str
    worker_id: str
    worker_name: str
    protocol_version: str
    server_ws: str
    max_concurrency: int
    task_timeout: float
    request_timeout: float
    heartbeat_interval: float
    reconnect_min_delay: float
    reconnect_max_delay: float
    num_predict: int
    temperature: float
    top_p: float
    repeat_penalty: float
    think: bool


def load_config() -> WorkerConfig:
    return WorkerConfig(
        ollama_host=os.getenv("DREAMWEAVE_OLLAMA_HOST", "http://127.0.0.1:11434"),
        ollama_model=os.getenv("DREAMWEAVE_OLLAMA_MODEL", "qwen3:14b"),
        worker_id=os.getenv("DREAMWEAVE_WORKER_ID", "local-dev-001"),
        worker_name=os.getenv("DREAMWEAVE_WORKER_NAME", "DreamWeave Local Worker"),
        protocol_version=os.getenv("DREAMWEAVE_PROTOCOL_VERSION", "0.1"),
        server_ws=os.getenv("DREAMWEAVE_SERVER_WS", "ws://127.0.0.1:3000/ws/worker"),
        max_concurrency=int(os.getenv("DREAMWEAVE_MAX_CONCURRENCY", "1")),
        task_timeout=float(os.getenv("DREAMWEAVE_TASK_TIMEOUT", "180")),
        request_timeout=float(os.getenv("DREAMWEAVE_REQUEST_TIMEOUT", "180")),
        heartbeat_interval=float(os.getenv("DREAMWEAVE_HEARTBEAT_INTERVAL", "15")),
        reconnect_min_delay=float(os.getenv("DREAMWEAVE_RECONNECT_MIN_DELAY", "3")),
        reconnect_max_delay=float(os.getenv("DREAMWEAVE_RECONNECT_MAX_DELAY", "30")),
        num_predict=int(os.getenv("DREAMWEAVE_NUM_PREDICT", "220")),
        temperature=float(os.getenv("DREAMWEAVE_TEMPERATURE", "0.66")),
        top_p=float(os.getenv("DREAMWEAVE_TOP_P", "0.85")),
        repeat_penalty=float(os.getenv("DREAMWEAVE_REPEAT_PENALTY", "1.08")),
        think=os.getenv("DREAMWEAVE_THINK", "false").strip().lower() in {"1", "true", "yes", "on"},
    )
