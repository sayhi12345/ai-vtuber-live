from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
TAROT_DIR = BACKEND_DIR / "skills" / "tarot"
DRAW_SCRIPT = TAROT_DIR / "scripts" / "draw.py"
CARDS_REFERENCE = TAROT_DIR / "references" / "cards.md"

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

TAROT_DRAW_FAILURE_TEXT = (
    "我剛剛在洗牌時出了點問題，這次沒能順利抽出三張牌。"
    "你可以再問我一次，我會重新為你抽牌。"
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


async def prepare_tarot_turn(
    *,
    question: str,
    history: list[dict[str, str]],
    persona_prompt: str,
) -> tuple[str, list[dict[str, str]]]:
    draw = await draw_cards(question)
    system_prompt = build_tarot_system_prompt(persona_prompt)
    message = build_tarot_user_prompt(question=question, history=history, draw=draw)
    return system_prompt, [{"role": "user", "content": message}]


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


def build_tarot_system_prompt(persona_prompt: str) -> str:
    return (
        f"{persona_prompt}\n\n"
        "你現在處於塔羅解讀模式。"
        "全程使用繁體中文回答，維持自然、可口播的 VTuber 語氣。"
        "塔羅是鏡子，不是命定預言；先共情，再解讀，最後把主權交還給使用者。"
        "牌已由系統真實抽出，你只能根據提供的牌面、牌位、seed、時段與本地牌義片段解讀，"
        "禁止自行改牌、補牌、重抽或假裝看到額外牌面。"
        "解讀時要兼顧具體與溫度，避免空泛雞湯，也避免恐嚇、宿命式斷言、醫療化日常痛苦。"
        "至少提到一次本次抽牌 seed，並說明可用該 seed 重現抽牌。"
        "三牌陣一律視為過去、現在、未來。"
        "輸出請包含：整體能量概覽、牌陣展示、逐牌解讀、牌間關係分析、"
        "綜合解讀、3-4 字能量總結詞，以及一個開放式結尾問題。"
        "行動建議必須具體到本週可執行，不可只說抽象價值觀。"
    )


def build_tarot_user_prompt(
    *,
    question: str,
    history: list[dict[str, str]],
    draw: TarotDraw,
) -> str:
    cards_summary = "\n".join(
        f"- {card.position}：{card.card}（{card.orientation}）"
        for card in draw.cards
    )
    history_summary = _format_recent_context(history)
    card_reference = _build_card_reference(draw.cards)
    time_factor = TIME_FACTOR_LABELS.get(draw.time_factor, draw.time_factor)
    spread_name = _normalize_display_text(draw.spread_name)

    return (
        f"使用者問題：\n{question}\n\n"
        f"最近對話上下文：\n{history_summary}\n\n"
        "系統已完成真實抽牌，請嚴格依照以下結果解讀，不可自行改牌：\n"
        f"- 牌陣：{spread_name}\n"
        f"- 時段訊息：{time_factor}\n"
        f"- 抽牌種子：{draw.seed}\n"
        f"- 牌面：\n{cards_summary}\n\n"
        "本地牌義參考：\n"
        f"{card_reference}\n\n"
        "請依此產出一份完整但可口播的塔羅回覆，並遵守以下要求：\n"
        "1. 開頭先用 1-2 句共情使用者此刻的狀態。\n"
        "2. 明確展示 seed，讓使用者知道這次抽牌可以重現。\n"
        "3. 用過去 / 現在 / 未來解讀三張牌，並至少引用一次本地牌義片段。\n"
        "4. 補一段牌間關係分析，說明這三張牌之間是因果、對話、遞進或轉折。\n"
        "5. 給一個本週可執行的具體行動建議。\n"
        "6. 最後加上一句：牌顯示的是當下能量，你的選擇隨時可以改變走向。\n"
        "7. 結尾用一個開放式問題把主權交還給使用者。"
    )


def _format_recent_context(history: list[dict[str, str]], limit: int = 4) -> str:
    relevant = history[:-1] if history else []
    if not relevant:
        return "- 無前文，可直接針對本次問題解讀。"

    lines: list[str] = []
    for message in relevant[-limit:]:
        role = "你" if message["role"] == "user" else "VTuber"
        content = re.sub(r"\s+", " ", message["content"]).strip()
        if len(content) > 220:
            content = f"{content[:217]}..."
        lines.append(f"- {role}：{content}")
    return "\n".join(lines)


def _build_card_reference(cards: list[TarotCard]) -> str:
    index = _load_card_reference_index()
    sections: list[str] = []
    for card in cards:
        section = index.get(card.card) or index.get(_normalize_card_name(card.card))
        if not section:
            continue
        sections.append(section)
    if not sections:
        return "- 找不到對應牌義片段，請僅根據牌名、牌位與正逆位解讀。"
    return "\n\n---\n\n".join(sections)


@lru_cache(maxsize=1)
def _load_card_reference_index() -> dict[str, str]:
    if not CARDS_REFERENCE.exists():
        raise TarotError(f"Cards reference not found: {CARDS_REFERENCE}")

    lines = CARDS_REFERENCE.read_text(encoding="utf-8").splitlines()
    index: dict[str, str] = {}
    current_name: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_name, current_lines
        if current_name and current_lines:
            index[current_name] = "\n".join(current_lines).strip()
        current_name = None
        current_lines = []

    for line in lines:
        heading_name = _extract_card_name_from_heading(line)
        if heading_name:
            flush()
            current_name = heading_name
            current_lines = [line]
            continue
        if current_name:
            if line.startswith("# "):
                flush()
                continue
            current_lines.append(line)

    flush()
    return index


def _extract_card_name_from_heading(line: str) -> str | None:
    major_match = re.match(r"##\s+\d+\.\s+([^\s]+)", line)
    if major_match:
        return major_match.group(1)
    minor_match = re.match(r"###\s+(.+)", line)
    if minor_match:
        return _normalize_card_name(minor_match.group(1).strip())
    return None


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
