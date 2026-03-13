from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
TAROT_DIR = BACKEND_DIR / "skills" / "tarot"
DRAW_SCRIPT = TAROT_DIR / "scripts" / "draw.py"

STRONG_TAROT_TRIGGERS = (
    "tarot",
    "塔羅",
    "塔罗",
    "占卜",
    "抽牌",
    "抽一張",
    "抽一张",
    "牌陣",
    "牌阵",
    "塔羅牌",
    "塔罗牌",
    "翻牌",
    "開牌",
    "开牌",
)

SOFT_TAROT_TRIGGERS = (
    "今日運勢",
    "今天運勢",
    "今天运势",
    "最近運勢",
    "最近运势",
    "運勢如何",
    "运势如何",
    "算一卦",
    "幫我算算",
    "帮我算算",
    "幫我算一下",
    "帮我算一下",
    "幫我看看",
    "帮我看看",
    "問一下牌",
    "问一下牌",
    "求籤",
    "求签",
    "測一下",
    "测一下",
    "給我一個指引",
    "给我一个指引",
    "抽張牌",
    "抽张牌",
    "每日一牌",
    "能量指引",
    "心靈指引",
    "心灵指引",
    "感情方面",
    "事業怎麼樣",
    "事业怎么样",
)

TIME_FACTOR_LABELS = {
    "morning": "早晨，火與風元素較活躍。",
    "afternoon": "午後，水與土元素較活躍。",
    "night": "夜晚，大阿卡納的靈性訊息通常更鮮明。",
}

_STRONG_PATTERNS = tuple(
    re.compile(re.escape(token), re.IGNORECASE) for token in STRONG_TAROT_TRIGGERS
)
_SOFT_PATTERNS = tuple(
    re.compile(re.escape(token), re.IGNORECASE) for token in SOFT_TAROT_TRIGGERS
)


class TarotError(RuntimeError):
    pass


@dataclass(slots=True)
class TarotCard:
    position: str
    card: str
    orientation: str
    is_major: bool


@dataclass(slots=True)
class TarotDraw:
    seed: int
    spread: str
    spread_name: str
    question: str
    time_factor: str
    cards: list[TarotCard]


def is_tarot_query(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return any(pattern.search(stripped) for pattern in (*_STRONG_PATTERNS, *_SOFT_PATTERNS))


async def draw_cards(question: str, spread: str = "three") -> TarotDraw:
    if not DRAW_SCRIPT.exists():
        raise TarotError(f"Draw script not found: {DRAW_SCRIPT}")

    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(DRAW_SCRIPT),
        "--spread",
        spread,
        "--question",
        question,
        "--json-only",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        detail = stderr.decode("utf-8", errors="ignore").strip() or "unknown tarot draw error"
        raise TarotError(detail)

    try:
        payload = json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise TarotError("Tarot draw returned invalid JSON.") from exc

    return TarotDraw(
        seed=int(payload["seed"]),
        spread=str(payload["spread"]),
        spread_name=str(payload["spread_name"]),
        question=str(payload["question"]),
        time_factor=str(payload["time_factor"]),
        cards=[
            TarotCard(
                position=str(card["position"]),
                card=str(card["card"]),
                orientation=str(card["orientation"]),
                is_major=bool(card["is_major"]),
            )
            for card in payload["cards"]
        ],
    )


async def draw_tarot_cards(question: str, spread: str = "three") -> dict[str, object]:
    draw = await draw_cards(question=question, spread=spread)
    return {
        "seed": draw.seed,
        "spread": draw.spread,
        "spread_name": _normalize_display_text(draw.spread_name),
        "question": draw.question,
        "time_factor": draw.time_factor,
        "time_factor_label": TIME_FACTOR_LABELS.get(draw.time_factor, draw.time_factor),
        "cards": [
            {
                "position": card.position,
                "card": _normalize_card_name(card.card),
                "orientation": card.orientation,
                "is_major": card.is_major,
            }
            for card in draw.cards
        ],
    }


def _normalize_display_text(text: str) -> str:
    return (
        text.replace("阵", "陣")
        .replace("单", "單")
        .replace("马", "馬")
        .replace("凯", "凱")
    )


def _normalize_card_name(text: str) -> str:
    return (
        text.replace("圣", "聖")
        .replace("杯", "盃")
        .replace("剑", "劍")
        .replace("宝", "寶")
        .replace("币", "幣")
    )
