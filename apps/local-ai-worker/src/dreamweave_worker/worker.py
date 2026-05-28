from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx

from .agent_nodes import execute_agent_workflow
from .config import WorkerConfig
from .ollama_client import OllamaClient
from .postprocess import clean_story_output
from .prompt import render_story_prompt
from .protocol import make_error_message, make_message, make_request_id, make_result_message, make_task_error_message
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

    async def handle_task_with_agent(self, task: AITask) -> AIResult:
        """Handle task using the new agent workflow."""
        model = task.model or self.config.ollama_model
        timeout = self._resolve_task_timeout(task)

        try:
            return await asyncio.wait_for(self._run_agent_task(task, model), timeout=timeout)
        except asyncio.TimeoutError:
            return AIResult(
                task_id=task.task_id,
                status="error",
                model=model,
                error_code="TASK_TIMEOUT",
                message=f"AI Agent 任务处理超时：{timeout:.0f} 秒",
            )

    async def _run_agent_task(self, task: AITask, model: str) -> AIResult:
        """Run the task using the agent workflow."""
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

                task_dict = task.to_dict()
                task_dict["model"] = model

                # Execute agent workflow
                result = await asyncio.to_thread(
                    execute_agent_workflow,
                    task_dict,
                    self.ollama,
                    None  # worlds_path will use default
                )

                # Convert agent result back to AIResult
                if result.get('status') == 'success':
                    return AIResult(
                        task_id=task.task_id,
                        status='success',
                        content=result.get('content', ''),
                        model=model,
                        state_update=result.get('state_update'),
                        agent_trace=result.get('agent_trace')
                    )
                else:
                    detail = {
                        "quality_issues": result.get("quality_issues") or [],
                        "agent_trace": result.get("agent_trace") or {},
                    }
                    if result.get("content"):
                        detail["content_preview"] = str(result.get("content"))[:160]
                    return AIResult(
                        task_id=task.task_id,
                        status='error',
                        model=model,
                        error_code=result.get('error_code', 'AGENT_ERROR'),
                        message=result.get('error_message', 'Agent workflow failed'),
                        state_update=result.get('state_update'),
                        agent_trace=result.get('agent_trace'),
                        detail=detail,
                    )

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
            # Use agent workflow for better narrative generation
            result = await self.handle_task_with_agent(task)
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
        # Use new protocol functions that support state_update and agent_trace
        if result.status == "success":
            await self._send_json(
                websocket,
                make_result_message(
                    task_id=result.task_id,
                    content=result.content or "",
                    model=result.model,
                    worker_id=self.config.worker_id,
                    request_id=request_id,
                    state_update=getattr(result, 'state_update', None),
                    agent_trace=getattr(result, 'agent_trace', None),
                    duration_ms=duration_ms
                )
            )
        else:
            await self._send_json(
                websocket,
                make_task_error_message(
                    task_id=result.task_id,
                    error_code=result.error_code or "UNKNOWN_ERROR",
                    message=result.message or "Unknown error",
                    worker_id=self.config.worker_id,
                    request_id=request_id,
                    retryable=result.error_code in RETRYABLE_ERROR_CODES,
                    detail=getattr(result, "detail", None) or _build_error_detail(result),
                )
            )

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


def _build_error_detail(result: AIResult) -> dict[str, Any] | None:
    detail: dict[str, Any] = {}
    if result.agent_trace:
        detail["agent_trace"] = result.agent_trace
    if result.state_update:
        detail["state_update"] = result.state_update
    return detail or None
