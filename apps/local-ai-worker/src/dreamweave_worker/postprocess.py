from __future__ import annotations

import re


TRIM_MARKERS = [
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

SENTENCE_ENDINGS = "。！？!?……」”』）)"


def clean_story_output(content: str) -> str:
    cleaned = content.replace("\r\n", "\n").strip()

    for marker in TRIM_MARKERS:
        index = cleaned.find(marker)
        if index >= 0:
            cleaned = cleaned[:index].strip()

    lines = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        if re.fullmatch(r"[-*_]{3,}", stripped):
            continue
        if re.fullmatch(r"\*\[[^\]]+\]\*", stripped):
            continue
        if re.fullmatch(r"\*\*\[[^\]]+\]\*\*", stripped):
            continue
        if stripped in {"小说正文：", "续写：", "正文："}:
            continue
        lines.append(stripped)

    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return trim_to_complete_sentence(cleaned.strip())


def trim_to_complete_sentence(content: str) -> str:
    if not content or content[-1] in SENTENCE_ENDINGS:
        return content

    last_index = -1
    for index, char in enumerate(content):
        if char in SENTENCE_ENDINGS:
            last_index = index

    if last_index < 60:
        return content

    return content[: last_index + 1].strip()
