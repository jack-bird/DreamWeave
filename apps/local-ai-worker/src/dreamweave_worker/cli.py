from __future__ import annotations

import argparse
import asyncio
import json
from uuid import uuid4

from .config import load_config
from .schemas import AITask, StoryContext
from .worker import LocalAIWorker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DreamWeave local AI worker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("health", help="检查 Ollama 连接和模型列表")

    local = subparsers.add_parser("local", help="本地执行一次小说续写任务")
    local.add_argument("message", help="用户输入内容")
    local.add_argument("--story-title", default="黑夜古堡")
    local.add_argument("--world-setting", default="中世纪奇幻世界")
    local.add_argument("--character-setting", default="用户是失忆的贵族继承人")
    local.add_argument("--model", help="本次任务使用的 Ollama 模型，不传则使用 Worker 默认模型")
    local.add_argument("--task-timeout", type=float, help="本次任务处理超时时间，单位秒")
    local.add_argument("--num-predict", type=int, help="本次任务的最大生成 token 数")
    local.add_argument("--temperature", type=float, help="本次任务的 temperature")
    local.add_argument("--json", action="store_true", help="以 JSON 格式输出结果")

    connect = subparsers.add_parser("connect", help="连接线上服务器 WebSocket")
    connect.add_argument("--server", help="WebSocket 地址，默认读取 DREAMWEAVE_SERVER_WS")

    return parser


async def run_health() -> None:
    worker = LocalAIWorker(load_config())
    health = await worker.health()
    print(json.dumps(health, ensure_ascii=False, indent=2))


async def run_local(args: argparse.Namespace) -> None:
    worker = LocalAIWorker(load_config())
    task = AITask(
        task_id=f"local_{uuid4().hex}",
        task_type="story_continue",
        user_id="local_user",
        session_id="local_session",
        story_id="local_story",
        input=args.message,
        model=args.model,
        timeout_ms=int(args.task_timeout * 1000) if args.task_timeout is not None else None,
        generation_options={
            key: value
            for key, value in {
                "num_predict": args.num_predict,
                "temperature": args.temperature,
            }.items()
            if value is not None
        },
        context=StoryContext(
            story_title=args.story_title,
            world_setting=args.world_setting,
            character_setting=args.character_setting,
            recent_messages=[],
        ),
    )

    result = await worker.handle_task(task)
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    elif result.status == "success":
        print(result.content)
    else:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


async def run_connect(args: argparse.Namespace) -> None:
    config = load_config()
    worker = LocalAIWorker(config)
    await worker.connect(args.server or config.server_ws)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "health":
        asyncio.run(run_health())
        return

    if args.command == "local":
        asyncio.run(run_local(args))
        return

    if args.command == "connect":
        asyncio.run(run_connect(args))
        return

    parser.error(f"未知命令：{args.command}")
