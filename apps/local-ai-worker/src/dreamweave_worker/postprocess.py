from __future__ import annotations

import re
from difflib import SequenceMatcher


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
PLAYER_INNER_STATE_PATTERNS = [
    r"你决定",
    r"你感到",
    r"你认为",
    r"你想要",
    r"你知道",
    r"你不知道",
    r"你以为",
    r"你能感觉到",
    r"你感觉",
    r"你心中",
    r"心中[燃有升]",
    r"心里",
    r"内心",
    r"恐惧感",
    r"兴趣",
    r"激动",
    r"窒息",
]


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
    cleaned = dedupe_repeated_paragraphs(cleaned)
    cleaned = dedupe_repeated_sentences(cleaned)
    cleaned = remove_player_inner_state_sentences(cleaned)
    return trim_to_complete_sentence(cleaned.strip())


def dedupe_repeated_paragraphs(content: str) -> str:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", content) if paragraph.strip()]
    if len(paragraphs) <= 1:
        return content

    kept: list[str] = []
    for paragraph in paragraphs:
        normalized = re.sub(r"\s+", "", paragraph)
        duplicate = False
        for existing in kept:
            existing_normalized = re.sub(r"\s+", "", existing)
            if normalized == existing_normalized:
                duplicate = True
                break
            if SequenceMatcher(None, normalized, existing_normalized).ratio() >= 0.92:
                duplicate = True
                break

        if not duplicate:
            kept.append(paragraph)

    return "\n\n".join(kept)


def dedupe_repeated_sentences(content: str) -> str:
    sentences = re.findall(r"[^。！？!?]+[。！？!?]?", content)
    if len(sentences) <= 2:
        return content

    kept: list[str] = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        normalized = re.sub(r"\s+", "", sentence)
        duplicate = False
        for existing in kept:
            existing_normalized = re.sub(r"\s+", "", existing)
            if normalized == existing_normalized:
                duplicate = True
                break
            if len(normalized) >= 18 and SequenceMatcher(None, normalized, existing_normalized).ratio() >= 0.9:
                duplicate = True
                break

        if not duplicate:
            kept.append(sentence)

    return "".join(kept)


def remove_player_inner_state_sentences(content: str) -> str:
    sentences = re.findall(r"[^。！？!?]+[。！？!?]?", content)
    if not sentences:
        return content

    kept: list[str] = []
    for sentence in sentences:
        stripped = sentence.strip()
        if not stripped:
            continue
        if any(re.search(pattern, stripped) for pattern in PLAYER_INNER_STATE_PATTERNS):
            continue
        kept.append(stripped)

    if not kept:
        return content

    return "".join(kept)


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
