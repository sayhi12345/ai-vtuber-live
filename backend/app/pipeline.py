from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


SENTENCE_SPLIT_PATTERN = re.compile(r"(.+?[。！？!?\.]+)")


def sse_pack(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


@dataclass
class SegmentAccumulator:
    buffer: str = ""
    _pattern: re.Pattern[str] = field(default=SENTENCE_SPLIT_PATTERN)

    def feed(self, chunk: str) -> list[str]:
        self.buffer += chunk
        segments: list[str] = []
        while True:
            match = self._pattern.search(self.buffer)
            if not match:
                break
            segment = match.group(1).strip()
            if segment:
                segments.append(segment)
            self.buffer = self.buffer[match.end() :]
        return segments

    def flush(self) -> str:
        remaining = self.buffer.strip()
        self.buffer = ""
        return remaining


def detect_emotion(text: str) -> str:
    source = text.lower()
    if any(token in source for token in ["驚", "wow", "surprise", "真的假的"]):
        return "surprised"
    if any(token in source for token in ["!", "！", "開心", "great", "happy", "太好了"]):
        return "happy"
    if any(token in source for token in ["難過", "sad", "抱歉", "對不起"]):
        return "sad"
    if any(token in source for token in ["生氣", "angry", "火大", "憤怒"]):
        return "angry"
    return "neutral"
