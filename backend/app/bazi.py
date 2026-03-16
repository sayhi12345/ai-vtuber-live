from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from pathlib import Path
import re
from types import ModuleType
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
BAZI_DIR = BACKEND_DIR / "skills" / "bazi-mingli"
BAZI_SCRIPT = BAZI_DIR / "scripts" / "bazi_calc.py"

_BAZI_KEYWORDS = (
    "八字",
    "四柱",
    "命盤",
    "命盘",
    "排盤",
    "排盘",
    "生辰八字",
    "天干地支",
    "五行",
    "流年",
    "大運",
    "大运",
    "bazi",
    "four pillars",
    "chinese astrology",
    "birth chart",
)
_BAZI_PATTERNS = tuple(re.compile(re.escape(token), re.IGNORECASE) for token in _BAZI_KEYWORDS)


class BaziError(RuntimeError):
    pass


@dataclass(slots=True)
class BaziRequest:
    year: int
    month: int
    day: int
    hour: int
    gender: str = "男"


def is_bazi_query(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return any(pattern.search(stripped) for pattern in _BAZI_PATTERNS)


def calculate_bazi_chart(
    year: int,
    month: int,
    day: int,
    hour: int,
    gender: str = "男",
) -> dict[str, Any]:
    # Normalize gender to strictly "男" or "女" to prevent bazi_calc script errors
    gender_str = str(gender).strip().lower()
    norm_gender = "女" if "女" in gender_str or gender_str in ("f", "female", "woman", "girl") else "男"

    print(f"Calculating Bazi chart for: {year}-{month}-{day} {hour}:00 {norm_gender}")
    module = _load_bazi_module()
    paipan = getattr(module, "paipan", None)
    if not callable(paipan):
        raise BaziError("Bazi calculator module does not expose paipan().")

    try:
        result = paipan(year, month, day, hour, norm_gender)
    except Exception as exc:  # pragma: no cover - passthrough from skill script
        raise BaziError(str(exc)) from exc

    if not isinstance(result, dict):
        raise BaziError("Bazi calculator returned an unexpected payload.")
    return result


def _load_bazi_module() -> ModuleType:
    if not BAZI_SCRIPT.exists():
        raise BaziError(f"Bazi calculator script not found: {BAZI_SCRIPT}")

    spec = importlib.util.spec_from_file_location("app.skills.bazi_calc", BAZI_SCRIPT)
    if spec is None or spec.loader is None:
        raise BaziError(f"Unable to load bazi calculator script: {BAZI_SCRIPT}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
