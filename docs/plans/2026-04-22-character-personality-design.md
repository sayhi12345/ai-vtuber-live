# 角色性格系統設計

> 日期：2026-04-22
> 分支：`feat-character-personality`
> 狀態：設計已核准，待實作

## 目標

把目前扁平的 `default_persona_prompt` 單一字串擴展為結構化的多角色系統，支援使用者在前端切換角色，讓不同角色有可辨識的人格、說話風格與背景。

## 範圍決策

| 決策 | 選擇 | 原因 |
|------|------|------|
| 角色數量 | 多角色可切換，不做編輯 UI | 符合 SPEC「Character-first」方向，但避免過早做 CMS |
| 儲存來源 | YAML 檔案（隨 repo 版控） | 創作者友善、PR 可 diff、無需 migration |
| 選角方式 | 前端下拉選單，選擇跟著 session 走 | 符合 SPEC 角色舞台體驗 |
| Schema 結構 | 輕結構：`profile` 有少量結構化欄位，其他面向為自由文字 | YAGNI，避免 schema 綁死 |
| 聲線／模型綁定 | 不綁，沿用現有預設 | 降低首版範圍，未來再擴 |
| 舊欄位處理 | 完全取代（`default_persona_prompt`、`persona_prompt`） | 目前無下游依賴，軟遷移徒增複雜 |
| 載入策略 | 啟動時一次載入記憶體（靜態） | 無狀態、最簡、角色變更重啟即生效 |

## 檔案佈局

```
backend/app/characters/
  __init__.py
  loader.py              # 啟動時掃描 + 載入 YAML → CharacterRegistry
  schema.py              # Character dataclass + prompt 組裝
  definitions/
    luna.yaml
    aria.yaml
```

修改：
- `backend/app/config.py` — 移除 `default_persona_prompt`，新增 `default_character_id`
- `backend/app/models.py` — `ChatRequest.persona_prompt` → `character_id: str | None`
- `backend/app/main.py` — 注入 `CharacterRegistry`，`/chat` 依 `character_id` 取 persona，新增 `GET /characters`
- `frontend/src/` — `CharacterSelector` 元件、`/characters` 拉清單、`/chat` 帶 `character_id`

## YAML Schema

```yaml
id: luna                                # 必填，須與檔名相符
profile:
  name: 露娜                            # 必填
  short_description: 月之塔的神祕占卜師  # 必填
  avatar: /avatars/luna.png             # 選填
personality: |                          # 必填，自由文字
  ...
speaking_style: |                       # 必填，自由文字
  ...
boundaries: |                           # 必填，自由文字
  ...
backstory: |                            # 必填，自由文字
  ...
```

**驗證規則**
- `id`、`profile.name`、`profile.short_description`、四個面向皆必填
- `id` 必須與檔名一致
- 啟動時任一檔案驗證失敗 → fail fast，不啟動

## Prompt 組裝

`Character.to_system_prompt()`：

```
你是 {profile.name}，{profile.short_description}。

【人格設定】
{personality}

【說話風格】
{speaking_style}

【關係邊界】
{boundaries}

【背景故事】
{backstory}
```

下游 agent routing (`_compose_agent_system_prompt`) 不變，會在此基礎上再接 agent runtime instructions。

## API

```
GET /characters
→ 200 [{"id":"luna","name":"露娜","short_description":"...","avatar":"..."}, ...]

POST /chat
body: { "character_id": "luna" | null, "message": "...", ... }
- 未傳或為 null → 使用 settings.default_character_id
- character_id 不存在 → 400 CharacterNotFound
```

## 前端行為

- `CharacterSelector` 元件放在聊天面板上方
- 啟動時呼叫 `GET /characters` 快取於 state
- 選擇狀態存於前端 session state（重新整理 → 回到預設角色）
- 下拉項目呈現 `avatar` + `name` + `short_description`；無 `avatar` 顯示 placeholder
- 每次 `/chat` 帶上當前 `character_id`

## 遷移步驟

1. 刪除 `config.py::default_persona_prompt`，新增 `default_character_id`（env `DEFAULT_CHARACTER_ID`，預設 `luna`）
2. 移除 `ChatRequest.persona_prompt`，新增 `character_id: str | None`
3. `main.py` 用 registry 查 persona、組 system prompt
4. 更新 `.env.example`（若有）與 `README.md` 設定章節
5. Seed `luna.yaml` 與 `aria.yaml`（風格反差以驗證切換有感）

## 測試策略

- **Unit**：`loader.py` 對合法／非法 YAML 的行為（缺欄位、id 不符、檔案不存在）
- **Unit**：`Character.to_system_prompt()` 輸出快照測試
- **Integration**：`GET /characters` 回傳形狀、`POST /chat` 帶不同 `character_id` 時 system prompt 對應變化、不存在 id 回 400
- **手動**：前端切換角色後，同一個問題的回答風格有可辨識差異

## 不做的事（YAGNI）

- 不做角色編輯 UI
- 不綁定 TTS voice / Live2D model
- 不做熱重載 / 檔案 watcher
- 不引入 DB schema / migration
- 不保留舊 `persona_prompt` override 欄位
