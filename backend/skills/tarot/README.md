# 🔮 Tarot Skill

AI 塔羅占卜 Agent Skill，為 Cursor / Claude Code / OpenClaw 等 AI agent 提供專業級塔羅解讀能力。

## 特性

- **78 張完整牌義**：韋特 + 托特 + 現代心理塔羅三大系統融合，每張大阿卡納含心理原型與托特視角
- **6 種牌陣**：單張 / 三牌陣 / 五牌陣 / 月亮牌陣 / 馬蹄形 / 凱爾特十字
- **牌間關係理論體系**：愚人之旅 / 數字旅程 / 牌性（Elemental Dignities）/ 對位牌 / 宮廷牌關係網 / 生命之樹，覆蓋所有可能的牌對組合
- **真隨機抽牌指令碼**：Python 指令碼 `scripts/draw.py`，密碼學安全隨機源，位置權重、時段因子、正逆位機率全內建
- **解讀方法論**：四維透鏡模型 / 牌間關係推理 / 敘事弧串聯 / 反巴納姆檢驗
- **語言約束與安全邊界**：禁用巴納姆廢話清單、自傷訊號處理協議

## 檔案結構

```
SKILL.md                        # 主技能文件（工作流 + 解讀方法論 + 輸出格式）
references/
  cards.md                      # 78 張牌義（~1100 行）
  card-relations.md             # 牌間關係理論體系（6 套理論 / 2 層架構）
  combinations.md               # 經典牌間組合 + 花色集中/密度規則
  spreads.md                    # 6 種牌陣佈局與解讀順序
scripts/
  draw.py                       # 真隨機抽牌指令碼（Python 3）
```

## 快速使用

### 作為 Agent Skill 安裝

將本倉庫內容放入 agent 的 skills 目錄：

```bash
# Cursor
cp -r . ~/.cursor/skills/tarot/

# Claude Code
cp -r . ~/.claude/skills/tarot/

# OpenClaw agents
cp -r . ~/.agents/skills/tarot/
```

### 抽牌指令碼

```bash
# 單張今日指引
python3 scripts/draw.py --spread single

# 三牌陣 + 問題
python3 scripts/draw.py --spread three --question "事業方向"

# 凱爾特十字
python3 scripts/draw.py --spread celtic --question "感情"

# 指定種子復現
python3 scripts/draw.py --spread three --question "事業" --seed 42
```

## 許可

MIT
