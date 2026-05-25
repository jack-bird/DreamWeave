from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


TaskStatus = Literal["success", "error"]


@dataclass(frozen=True)
class StoryContext:
    story_title: str = "黑夜古堡"
    world_setting: str = "中世纪奇幻世界"
    character_setting: str = "用户是失忆的贵族继承人"
    recent_messages: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "StoryContext":
        if not data:
            return cls()

        recent_messages = data.get("recent_messages") or []
        return cls(
            story_title=str(data.get("story_title") or cls.story_title),
            world_setting=str(data.get("world_setting") or cls.world_setting),
            character_setting=str(data.get("character_setting") or cls.character_setting),
            recent_messages=[str(item) for item in recent_messages],
        )


@dataclass(frozen=True)
class AITask:
    task_id: str
    task_type: str
    user_id: str
    session_id: str
    story_id: str
    input: str
    model: str | None = None
    timeout_ms: int | None = None
    generation_options: dict[str, Any] = field(default_factory=dict)
    context: StoryContext = field(default_factory=StoryContext)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AITask":
        return cls(
            task_id=str(data["task_id"]),
            task_type=str(data.get("task_type") or "story_continue"),
            user_id=str(data.get("user_id") or ""),
            session_id=str(data.get("session_id") or ""),
            story_id=str(data.get("story_id") or ""),
            input=str(data["input"]),
            model=str(data["model"]) if data.get("model") else None,
            timeout_ms=int(data["timeout_ms"]) if data.get("timeout_ms") else None,
            generation_options=dict(data.get("generation_options") or data.get("options") or {}),
            context=StoryContext.from_dict(data.get("context")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AIResult:
    task_id: str
    status: TaskStatus
    content: str = ""
    model: str | None = None
    error_code: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {key: value for key, value in data.items() if value is not None}
