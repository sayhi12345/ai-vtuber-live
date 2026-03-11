#!/usr/bin/env python3
"""
塔羅牌抽牌指令碼 — 實現 SKILL.md 定義的完整抽牌演算法。

用法:
  python3 draw.py --spread single
  python3 draw.py --spread three --question "事業方向"
  python3 draw.py --spread celtic --question "感情" --seed 12345
"""

import argparse
import hashlib
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

# 指令碼自身所在目錄（不依賴呼叫路徑，適配任意安裝位置）
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent

# ─── 78 張牌定義（與 cards.md 標題完全一致） ───

MAJOR_ARCANA = [
    "愚者", "魔術師", "女祭司", "女皇", "皇帝", "教皇", "戀人", "戰車",
    "力量", "隱士", "命運之輪", "正義", "倒吊人", "死神", "節制", "惡魔",
    "高塔", "星星", "月亮", "太陽", "審判", "世界",
]

SUITS = {
    "權杖": "火",
    "聖盃": "水",
    "寶劍": "風",
    "星幣": "土",
}

RANKS = ["Ace", "二", "三", "四", "五", "六", "七", "八", "九", "十",
         "侍從", "騎士", "皇后", "國王"]

MINOR_ARCANA = [f"{suit}{rank}" for suit in SUITS for rank in RANKS]

ALL_CARDS = MAJOR_ARCANA + MINOR_ARCANA  # 22 + 56 = 78

# 大阿卡納的元素歸屬（用於時段因子）
MAJOR_ELEMENT = {
    "愚者": "風", "魔術師": "風", "女祭司": "水", "女皇": "土",
    "皇帝": "火", "教皇": "土", "戀人": "風", "戰車": "水",
    "力量": "火", "隱士": "土", "命運之輪": "火", "正義": "風",
    "倒吊人": "水", "死神": "水", "節制": "火", "惡魔": "土",
    "高塔": "火", "星星": "風", "月亮": "水", "太陽": "火",
    "審判": "火", "世界": "土",
}

# ─── 牌陣定義（與 spreads.md 一致） ───

SPREADS = {
    "single": {
        "name": "單張牌",
        "positions": [
            {"name": "當前指引", "key_position": True},
        ],
    },
    "three": {
        "name": "三牌陣",
        "positions": [
            {"name": "過去", "key_position": False},
            {"name": "現在", "key_position": True},
            {"name": "未來", "key_position": False, "favor_upright": True},
        ],
    },
    "diamond": {
        "name": "五牌陣",
        "positions": [
            {"name": "核心", "key_position": True},
            {"name": "根源", "key_position": False},
            {"name": "阻力", "key_position": False},
            {"name": "潛力", "key_position": False},
            {"name": "建議", "key_position": True, "favor_upright": True},
        ],
    },
    "moon": {
        "name": "月亮牌陣",
        "positions": [
            {"name": "新月", "key_position": True},
            {"name": "上弦", "key_position": False},
            {"name": "滿月", "key_position": True},
            {"name": "下弦", "key_position": False},
        ],
    },
    "horseshoe": {
        "name": "馬蹄形",
        "positions": [
            {"name": "遠期過去", "key_position": False},
            {"name": "近期過去", "key_position": False},
            {"name": "當前", "key_position": True},
            {"name": "近期未來", "key_position": False},
            {"name": "外部影響", "key_position": True},
            {"name": "建議", "key_position": False, "favor_upright": True},
            {"name": "結果", "key_position": True, "favor_upright": True},
        ],
    },
    "celtic": {
        "name": "凱爾特十字",
        "positions": [
            {"name": "核心", "key_position": True},
            {"name": "交叉", "key_position": False},
            {"name": "意識目標", "key_position": False},
            {"name": "根基過去", "key_position": False},
            {"name": "近期過去", "key_position": True},
            {"name": "近期未來", "key_position": False},
            {"name": "自我", "key_position": False},
            {"name": "環境", "key_position": False},
            {"name": "希望與恐懼", "key_position": False},
            {"name": "結果", "key_position": True, "favor_upright": True},
        ],
    },
}

# ─── 時段因子 ───

def get_time_factor():
    """根據當前小時返回時段及受 +8% 加成的元素列表。"""
    hour = datetime.now().hour
    if 6 <= hour < 12:
        return "morning", ["火", "風"]
    elif 12 <= hour < 18:
        return "afternoon", ["水", "土"]
    else:
        return "night", ["major"]  # 夜晚加成大阿卡納整體


def card_element(card_name: str) -> str | None:
    """返回牌的元素；大阿卡納返回其對應元素，小阿卡納返回花色元素。"""
    if card_name in MAJOR_ELEMENT:
        return MAJOR_ELEMENT[card_name]
    for suit, element in SUITS.items():
        if card_name.startswith(suit):
            return element
    return None


# ─── 抽牌核心 ───

def draw_cards(spread_key: str, question: str, seed: int | None = None):
    if spread_key not in SPREADS:
        print(f"錯誤：未知牌陣 '{spread_key}'", file=sys.stderr)
        print(f"可選：{', '.join(SPREADS.keys())}", file=sys.stderr)
        sys.exit(1)

    spread = SPREADS[spread_key]
    positions = spread["positions"]

    if seed is None:
        raw = hashlib.sha256(f"{time.time_ns()}{question}".encode()).hexdigest()
        seed = int(raw[:16], 16)

    rng = random.Random(seed)
    time_factor_name, boosted = get_time_factor()
    pool = list(ALL_CARDS)
    drawn = []

    for i, pos in enumerate(positions):
        is_key = pos.get("key_position", False)
        favor_upright = pos.get("favor_upright", False)

        weights = []
        for card in pool:
            is_major = card in MAJOR_ARCANA
            w = 1.0

            # 位置權重：關鍵位置大阿卡納 60%，普通位置 28%
            if is_key and is_major:
                w *= 60 / 28  # ~2.14x
            elif not is_key and is_major:
                w *= 1.0  # 自然機率

            # 時段因子 +8%
            elem = card_element(card)
            if "major" in boosted and is_major:
                w *= 1.08
            elif elem in boosted:
                w *= 1.08

            weights.append(w)

        chosen_idx = rng.choices(range(len(pool)), weights=weights, k=1)[0]
        chosen_card = pool.pop(chosen_idx)

        # 正逆位
        upright_prob = 0.70 if favor_upright else 0.60
        orientation = "正位" if rng.random() < upright_prob else "逆位"

        drawn.append({
            "position": pos["name"],
            "card": chosen_card,
            "orientation": orientation,
            "is_major": chosen_card in MAJOR_ARCANA,
        })

    return {
        "seed": seed,
        "spread": spread_key,
        "spread_name": spread["name"],
        "question": question,
        "time_factor": time_factor_name,
        "cards": drawn,
    }


# ─── 人類可讀輸出 ───

TIME_FACTOR_LABEL = {
    "morning": "早晨（火/風元素活躍期）",
    "afternoon": "午後（水/土元素活躍期）",
    "night": "夜晚（靈性/潛意識活躍期）",
}

def print_human_readable(result: dict):
    print(f"\n{'=' * 40}")
    print(f"🔮 {result['spread_name']}")
    if result["question"]:
        print(f"❓ 問題：{result['question']}")
    print(f"🕐 時段：{TIME_FACTOR_LABEL[result['time_factor']]}")
    print(f"🌱 種子：{result['seed']}")
    print(f"{'=' * 40}\n")

    for c in result["cards"]:
        arrow = "⬆️" if c["orientation"] == "正位" else "⬇️"
        major_tag = " [大阿卡納]" if c["is_major"] else ""
        print(f"  {c['position']:　<8} 🃏 {c['card']} {arrow}{c['orientation']}{major_tag}")

    print()


# ─── CLI ───

def main():
    parser = argparse.ArgumentParser(description="塔羅牌抽牌指令碼")
    parser.add_argument("--spread", required=True, choices=SPREADS.keys(),
                        help="牌陣型別")
    parser.add_argument("--question", default="", help="問卜問題（可選）")
    parser.add_argument("--seed", type=int, default=None,
                        help="指定隨機種子（用於復現）")
    parser.add_argument("--json-only", action="store_true",
                        help="僅輸出 JSON，不輸出人類可讀文字")
    args = parser.parse_args()

    result = draw_cards(args.spread, args.question, args.seed)

    if not args.json_only:
        print_human_readable(result)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
