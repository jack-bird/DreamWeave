from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx

from .config import WorkerConfig
from .ollama_client import OllamaClient
from .postprocess import clean_story_output
from .prompt import render_story_prompt
from .protocol import make_error_message, make_message, make_request_id
from .schemas import AIResult, AITask


logger = logging.getLogger(__name__)


RETRYABLE_ERROR_CODES = {
    "OLLAMA_TIMEOUT",
    "OLLAMA_HTTP_ERROR",
    "EMPTY_RESPONSE",
    "TASK_TIMEOUT",
    "WORKER_BUSY",
}


class LocalAIWorker:
    def __init__(self, config: WorkerConfig) -> None:
        self.config = config
        self.ollama = OllamaClient(
            base_url=config.ollama_host,
            model=config.ollama_model,
            timeout=config.request_timeout,
            num_predict=config.num_predict,
            temperature=config.temperature,
            top_p=config.top_p,
            repeat_penalty=config.repeat_penalty,
            think=config.think,
        )
        self.semaphore = asyncio.Semaphore(config.max_concurrency)
        self.running_tasks: dict[str, asyncio.Task[None]] = {}
        self.available_models: list[str] = []

    async def health(self) -> dict[str, Any]:
        models = await self.ollama.list_models()
        return {
            "worker_id": self.config.worker_id,
            "ollama_host": self.config.ollama_host,
            "ollama_model": self.config.ollama_model,
            "model_available": self.config.ollama_model in models,
            "models": models,
        }

    async def handle_task(self, task: AITask) -> AIResult:
        model = task.model or self.config.ollama_model
        timeout = self._resolve_task_timeout(task)

        try:
            return await asyncio.wait_for(self._run_task(task, model), timeout=timeout)
        except asyncio.TimeoutError:
            return AIResult(
                task_id=task.task_id,
                status="error",
                model=model,
                error_code="TASK_TIMEOUT",
                message=f"AI 任务处理超时：{timeout:.0f} 秒",
            )

    async def _run_task(self, task: AITask, model: str) -> AIResult:
        async with self.semaphore:
            try:
                if task.model:
                    models = await self.ollama.list_models()
                    if model not in models:
                        return AIResult(
                            task_id=task.task_id,
                            status="error",
                            model=model,
                            error_code="MODEL_NOT_FOUND",
                            message=f"本地 Ollama 未找到模型：{model}",
                        )

                prompt = render_story_prompt(task.context, task.input)
                content = clean_story_output(
                    await self.ollama.generate(
                        prompt,
                        model=model,
                        generation_options=task.generation_options,
                    )
                )

                if not content:
                    return AIResult(
                        task_id=task.task_id,
                        status="error",
                        model=model,
                        error_code="EMPTY_RESPONSE",
                        message="Ollama 返回内容为空",
                    )

                return AIResult(task_id=task.task_id, status="success", content=content, model=model)
            except httpx.TimeoutException:
                return AIResult(
                    task_id=task.task_id,
                    status="error",
                    model=model,
                    error_code="OLLAMA_TIMEOUT",
                    message="Ollama 生成超时",
                )
            except httpx.HTTPStatusError as exc:
                return AIResult(
                    task_id=task.task_id,
                    status="error",
                    model=model,
                    error_code="OLLAMA_HTTP_ERROR",
                    message=f"Ollama HTTP 错误：{exc.response.status_code}",
                )
            except Exception as exc:  # noqa: BLE001
                return AIResult(
                    task_id=task.task_id,
                    status="error",
                    model=model,
                    error_code="WORKER_ERROR",
                    message=str(exc),
                )

    def _resolve_task_timeout(self, task: AITask) -> float:
        if task.timeout_ms is not None:
            return max(task.timeout_ms / 1000, 1)
        return max(self.config.task_timeout, 1)

    async def connect(self, server_url: str) -> None:
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError("缺少 websockets 依赖，请先安装 requirements.txt") from exc

        reconnect_delay = self.config.reconnect_min_delay

        while True:
            try:
                await self._connect_once(websockets, server_url)
                reconnect_delay = self.config.reconnect_min_delay
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Worker WebSocket disconnected: %s. Reconnecting in %.1f seconds.",
                    exc,
                    reconnect_delay,
                )
                await self._cancel_running_tasks()
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, self.config.reconnect_max_delay)

    async def _connect_once(self, websockets: Any, server_url: str) -> None:
        async with websockets.connect(server_url, ping_interval=20, ping_timeout=20) as websocket:
            await self._send_register(websocket)
            heartbeat_interval = await self._wait_for_registration(websocket)

            heartbeat_task = asyncio.create_task(self._heartbeat_loop(websocket, heartbeat_interval))
            try:
                async for raw_message in websocket:
                    await self._handle_ws_message(websocket, raw_message)
            finally:
                heartbeat_task.cancel()
                await asyncio.gather(heartbeat_task, return_exceptions=True)

    async def _send_register(self, websocket: Any) -> None:
        self.available_models = await self.ollama.list_models()
        payload = {
            "worker_id": self.config.worker_id,
            "worker_name": self.config.worker_name,
            "protocol_version": self.config.protocol_version,
            "default_model": self.config.ollama_model,
            "available_models": self.available_models,
            "max_concurrency": self.config.max_concurrency,
            "capabilities": {
                "story_continue": True,
                "stream_result": False,
                "thinking_control": True,
            },
        }
        await self._send_json(websocket, make_message("worker.register", payload, make_request_id("req_register")))

    async def _wait_for_registration(self, websocket: Any) -> float:
        raw_message = await asyncio.wait_for(websocket.recv(), timeout=10)
        message = self._parse_message(raw_message)
        message_type = message.get("type")
        payload = message.get("payload") or {}

        if message_type == "worker.rejected":
            raise RuntimeError(payload.get("message") or "Worker registration rejected")

        if message_type != "worker.registered":
            raise RuntimeError(f"Expected worker.registered, got {message_type}")

        interval_ms = payload.get("heartbeat_interval_ms")
        if interval_ms:
            return max(float(interval_ms) / 1000, 1)

        return max(self.config.heartbeat_interval, 1)

    async def _heartbeat_loop(self, websocket: Any, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            await self._send_heartbeat(websocket)

    async def _send_heartbeat(self, websocket: Any) -> None:
        payload = {
            "worker_id": self.config.worker_id,
            "status": "busy" if self.running_tasks else "idle",
            "running_tasks": len(self.running_tasks),
            "max_concurrency": self.config.max_concurrency,
            "default_model": self.config.ollama_model,
            "available_models": self.available_models,
        }
        await self._send_json(websocket, make_message("worker.heartbeat", payload, make_request_id("req_heartbeat")))

    async def _handle_ws_message(self, websocket: Any, raw_message: str) -> None:
        try:
            message = self._parse_message(raw_message)
        except ValueError as exc:
            await self._send_json(websocket, make_error_message("INVALID_MESSAGE", str(exc)))
            return

        message_type = message.get("type")
        request_id = message.get("request_id")
        payload = message.get("payload") or {}

        if message_type == "worker.heartbeat_ack":
            return

        if message_type == "ai.task":
            await self._start_ws_task(websocket, payload, request_id)
            return

        if message_type == "ai.task_cancel":
            await self._cancel_ws_task(websocket, payload, request_id)
            return

        if message_type in {"worker.registered", "worker.rejected"}:
            return

        await self._send_json(
            websocket,
            make_error_message(
                "UNSUPPORTED_MESSAGE_TYPE",
                f"不支持的消息类型：{message_type}",
                request_id=request_id,
            ),
        )

    async def _start_ws_task(self, websocket: Any, payload: dict[str, Any], request_id: str | None) -> None:
        try:
            task = AITask.from_dict(payload)
        except Exception as exc:  # noqa: BLE001
            await self._send_json(
                websocket,
                make_error_message(
                    "INVALID_PAYLOAD",
                    f"AI 任务 payload 不合法：{exc}",
                    request_id=request_id,
                ),
            )
            return

        if len(self.running_tasks) >= self.config.max_concurrency:
            result = AIResult(
                task_id=task.task_id,
                status="error",
                model=task.model or self.config.ollama_model,
                error_code="WORKER_BUSY",
                message="Worker 当前并发已满",
            )
            await self._safe_send_task_result(websocket, result, request_id)
            return

        runner = asyncio.create_task(self._run_ws_task(websocket, task, request_id))
        self.running_tasks[task.task_id] = runner

    async def _run_ws_task(self, websocket: Any, task: AITask, request_id: str | None) -> None:
        started_at = time.perf_counter()
        try:
            result = await self.handle_task(task)
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            await self._safe_send_task_result(websocket, result, request_id, duration_ms=duration_ms)
        except asyncio.CancelledError:
            result = AIResult(
                task_id=task.task_id,
                status="error",
                model=task.model or self.config.ollama_model,
                error_code="TASK_CANCELLED",
                message="任务已取消",
            )
            await self._safe_send_task_result(websocket, result, request_id, duration_ms=None)
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("WebSocket task failed before result could be delivered: %s", exc)
        finally:
            self.running_tasks.pop(task.task_id, None)

    async def _safe_send_task_result(
        self,
        websocket: Any,
        result: AIResult,
        request_id: str | None,
        duration_ms: int | None = None,
    ) -> None:
        try:
            await self._send_task_result(websocket, result, request_id, duration_ms=duration_ms)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to send task result for %s: %s", result.task_id, exc)

    async def _cancel_ws_task(self, websocket: Any, payload: dict[str, Any], request_id: str | None) -> None:
        task_id = payload.get("task_id")
        if not task_id:
            await self._send_json(
                websocket,
                make_error_message("INVALID_PAYLOAD", "取消任务缺少 task_id", request_id=request_id),
            )
            return

        task = self.running_tasks.get(str(task_id))
        if task:
            task.cancel()
            return

        await self._send_json(
            websocket,
            make_error_message(
                "INVALID_PAYLOAD",
                f"未找到正在运行的任务：{task_id}",
                request_id=request_id,
            ),
        )

    async def _send_task_result(
        self,
        websocket: Any,
        result: AIResult,
        request_id: str | None,
        duration_ms: int | None = None,
    ) -> None:
        payload = result.to_dict()
        payload["worker_id"] = self.config.worker_id
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms

        if result.status == "success":
            payload.setdefault(
                "usage",
                {
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "total_tokens": None,
                },
            )
            await self._send_json(websocket, make_message("ai.result", payload, request_id=request_id))
            return

        payload["retryable"] = result.error_code in RETRYABLE_ERROR_CODES
        await self._send_json(websocket, make_message("ai.task_error", payload, request_id=request_id))

    async def _cancel_running_tasks(self) -> None:
        if not self.running_tasks:
            return

        for task in self.running_tasks.values():
            task.cancel()

        await asyncio.gather(*self.running_tasks.values(), return_exceptions=True)
        self.running_tasks.clear()

    def _parse_message(self, raw_message: str) -> dict[str, Any]:
        try:
            message = json.loads(raw_message)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON 解析失败：{exc}") from exc

        if not isinstance(message, dict):
            raise ValueError("消息必须是 JSON object")

        if not message.get("type"):
            raise ValueError("消息缺少 type 字段")

        payload = message.get("payload")
        if payload is None:
            message["payload"] = {}
        elif not isinstance(payload, dict):
            raise ValueError("payload 必须是 JSON object")

        return message

    async def _send_json(self, websocket: Any, message: dict[str, Any]) -> None:
        await websocket.send(json.dumps(message, ensure_ascii=False))
