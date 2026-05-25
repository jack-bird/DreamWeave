from __future__ import annotations

import json
from typing import Any

import httpx


DEFAULT_STOP_SEQUENCES = [
    "我该怎么办？",
    "我该怎么办?",
    "请选择",
    "请直接输入",
    "生成引擎",
    "\n用户：",
    "\n用户:",
    "\n助手：",
    "\n助手:",
    "\n系统：",
    "\n系统:",
    "\nAI：",
    "\nAI:",
    "\n---",
    "\n**[",
]


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 180,
        num_predict: int = 220,
        temperature: float = 0.66,
        top_p: float = 0.85,
        repeat_penalty: float = 1.08,
        think: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.num_predict = num_predict
        self.temperature = temperature
        self.top_p = top_p
        self.repeat_penalty = repeat_penalty
        self.think = think

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            response = await client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            payload = response.json()

        return [item["name"] for item in payload.get("models", [])]

    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        generation_options: dict[str, Any] | None = None,
    ) -> str:
        options, think = self._build_request_options(generation_options)
        request_payload: dict[str, Any] = {
            "model": model or self.model,
            "prompt": prompt,
            "stream": True,
            "think": think,
            "options": options,
        }

        chunks: list[str] = []
        timeout = httpx.Timeout(self.timeout, connect=10)

        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            async with client.stream("POST", f"{self.base_url}/api/generate", json=request_payload) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    payload = json.loads(line)
                    chunks.append(str(payload.get("response") or ""))

                    if payload.get("done"):
                        break

        return "".join(chunks).strip()

    def _build_request_options(self, generation_options: dict[str, Any] | None) -> tuple[dict[str, Any], bool]:
        raw_options = dict(generation_options or {})
        raw_think = raw_options.pop("think", None)

        options: dict[str, Any] = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "repeat_penalty": self.repeat_penalty,
            "num_predict": self.num_predict,
            "stop": DEFAULT_STOP_SEQUENCES,
        }

        for key, value in raw_options.items():
            if value is not None:
                options[key] = value

        think = self.think if raw_think is None else _to_bool(raw_think)
        return options, think


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False
