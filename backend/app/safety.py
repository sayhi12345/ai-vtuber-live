from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True)
class SafetyResult:
    allowed: bool
    text: str
    reason: str | None = None


class SafetyPipeline:
    def __init__(self, blocklist: list[str]) -> None:
        escaped = [re.escape(word.strip()) for word in blocklist if word.strip()]
        self._patterns = [re.compile(pattern, re.IGNORECASE) for pattern in escaped]

    def filter_input(self, text: str) -> SafetyResult:
        if self._contains_blocked(text):
            return SafetyResult(
                allowed=False,
                text="",
                reason="Input contains blocked content.",
            )
        return SafetyResult(allowed=True, text=text)

    def filter_output(self, text: str) -> SafetyResult:
        if self._contains_blocked(text):
            sanitized = text
            for pattern in self._patterns:
                sanitized = pattern.sub("[REDACTED]", sanitized)
            return SafetyResult(
                allowed=True,
                text=sanitized,
                reason="Output was sanitized due to blocked content.",
            )
        return SafetyResult(allowed=True, text=text)

    def _contains_blocked(self, text: str) -> bool:
        return any(pattern.search(text) for pattern in self._patterns)
