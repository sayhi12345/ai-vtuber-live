# AI-VTuber 產品需求與技術規格書

> **文件類型**: PRD + SPEC  
> **版本**: v0.3.0  
> **日期**: 2026-03-09  
> **狀態**: Draft  
> **產品方向**: Character-first conversational web app  
> **參考案例**: [Neuro-sama](https://www.youtube.com/@Neurosama) · [AIRI](https://github.com/moeru-ai/airi) · [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/open-llm-vtuber)

---

## 1. 執行摘要

AI-VTuber 第一版不是直播平台工具，而是一個以角色體驗為核心的對話式 Web App。使用者以文字輸入與角色互動，系統生成回覆、播放語音、同步字幕，並驅動 VTuber 的嘴型與表情。頁面本身就是互動舞台，同時保留未來嵌入 OBS 的能力。

這份文件同時承擔產品需求與技術規格兩個目的。產品層定義我們要為誰做、要驗證什麼體驗、MVP 包含哪些能力；技術層定義如何以低延遲、可替換、安全可控的方式完成角色回覆、TTS、表情與渲染整合。

本期成功標準不是高吞吐直播互動，而是證明一個角色化 AI 對話體驗可以成立：看起來像角色、聽起來像角色、回覆節奏自然、表情與語音不脫節。

---

## 2. 產品背景與願景

### 2.1 背景

AI VTuber 的魅力不只來自「會聊天」，更來自「像角色」。如果只有文字回應，再好的 LLM 也容易被感知成聊天機器；但當角色有穩定語氣、自然語音、同步嘴型與表情時，使用者才會開始把它視為可互動角色。

直接從直播平台切入會同時引入聊天室節流、平台串接、營運風險與高併發互動，會模糊掉最核心的產品問題：角色本身是否有吸引力。因此第一版先把場景收斂到可控的 Web App，優先驗證角色體驗。

### 2.2 產品願景

打造一個可複用的 AI 角色互動骨架，讓創作者或開發者能快速完成：

- 建立角色人格與口吻
- 使用文字與角色對話
- 播放具角色感的語音回覆
- 顯示同步嘴型、表情與字幕
- 在未來無需重構核心流程即可接到 OBS 或直播場景

---

## 3. 目標用戶與核心場景

### 3.1 目標用戶

| Persona | 角色 | 主要需求 |
|---------|------|----------|
| 獨立創作者 | 想快速打造 AI 角色原型的創作者 | 角色存在感強、部署簡單、可直接展示 |
| 角色設計者 | 想測試人設、語氣、表情表演的一人團隊 | 可反覆微調人格、聲線與表情映射 |
| 技術原型開發者 | 想驗證 AI 角色互動體驗的工程師 | 模組清晰、方便替換 LLM/TTS/Renderer |

### 3.2 核心使用場景

1. 使用者打字給角色，角色在短時間內以語音、字幕與表情回應。
2. 使用者持續多輪對話，角色在數輪對話內維持相對一致的人格與口吻。
3. 使用者觀看角色回應時，可感知到嘴型、表情、字幕與語音的同步，而不是各自分離。
4. 創作者在本地或 demo 場景中開啟頁面，即可展示角色互動效果，必要時可嵌入 OBS。

### 3.3 Jobs To Be Done

- 當我在設計 AI 角色時，我希望能快速看到角色如何說話、如何表情反應，這樣我才能判斷角色是否成立。
- 當我在和角色對話時，我希望它回應自然、像有個性的人物，而不是單純朗讀文字。
- 當我在展示原型時，我希望頁面本身就足夠完整，不需要先接直播平台才能驗證價值。

---

## 4. 問題定義與產品目標

### 4.1 問題定義

要讓 AI VTuber 的角色體驗成立，系統至少要同時滿足五件事：

1. 輸入順暢：使用者能快速送出文字，不被繁瑣操作打斷。
2. 人格一致：角色的語氣、措辭與情緒反應有辨識度。
3. 表達自然：文字回覆能轉成可聽、可看的演出。
4. 同步可信：語音、字幕、嘴型與表情不能明顯錯位。
5. 安全可控：回覆不可失控，且需支援人工中止與內容約束。

第一版最大的風險不是模型不夠強，而是角色演出被割裂成幾個彼此不協調的零件。

### 4.2 產品目標

| 目標 | 定義 |
|------|------|
| 角色存在感 | 使用者明確感知角色有固定語氣、表情風格與回應節奏 |
| 對話順暢 | 文字送出後，角色在可接受延遲內開始回應 |
| 演出同步 | 語音、字幕、嘴型與表情連動，不出現明顯脫節 |
| 互動可展示 | 單一 Web App 即可完成可 demo 的互動流程 |
| 未來可擴展 | 架構保留嵌入 OBS 與接入直播平台的可能性 |

### 4.3 非目標

以下內容不屬於本期 MVP：

- Twitch / YouTube 直播平台接入
- 語音輸入或即時 ASR
- 多角色同台互動
- 長期記憶與複雜角色成長系統
- 商業化營運後台或多租戶配置
- 遊戲畫面理解與多模態觀察

---

## 5. MVP 定義與版本策略

### 5.1 MVP 假設

我們相信，只要先做出一個 `文字輸入 → AI 回覆 → 語音播出 → VTuber 表情/嘴型同步` 的完整舞台，就能有效驗證角色體驗是否有吸引力，並為後續擴展到 OBS 與直播場景提供穩定骨架。

### 5.2 MVP 範圍

| 類別 | MVP 內容 | 優先級 |
|------|----------|--------|
| 介面 | 單頁 Web App，含角色舞台、字幕區、對話紀錄、文字輸入框 | P0 |
| 對話 | 角色人格提示、短期上下文、多輪對話 | P0 |
| 語音 | 串流或低延遲 TTS，支援至少 1 個角色聲線 | P0 |
| 角色表演 | 基本嘴型同步與 3 到 5 種表情切換 | P0 |
| 字幕 | 回覆逐段顯示，與語音播放節奏一致 | P0 |
| 安全 | 輸入前與輸出前過濾、人工靜音或停止回覆 | P0 |
| OBS 相容 | 支援透明背景或獨立舞台視圖，便於嵌入 Browser Source | P1 |
| 記錄與監控 | 對話 log、延遲指標、錯誤訊息 | P1 |
| 長期記憶 | 角色與使用者長期偏好記憶 | P2 |

### 5.3 版本策略

| 版本 | 核心目的 | 說明 |
|------|----------|------|
| Phase 0 | Character Loop | 驗證文字輸入、回覆、語音、字幕、嘴型能完整串起 |
| Phase 1 | Demo Ready | 補齊角色舞台、表情、安全與穩定性，可用於展示與內測 |
| Phase 2 | Broadcast Ready | 增加 OBS 相容視圖、更多角色配置與後續直播擴展點 |

---

## 6. 功能需求與驗收標準

### 6.1 核心使用者流程

```text
使用者輸入文字
→ UI 顯示使用者訊息
→ 安全過濾與上下文組裝
→ LLM 生成角色回覆與情緒標籤
→ 字幕逐段顯示
→ TTS 生成並播放語音
→ VTuber 同步嘴型與表情
→ 對話紀錄寫入 session log
```

### 6.2 Functional Requirements

| ID | Requirement | Priority | 驗收標準 |
|----|-------------|----------|----------|
| FR1 | 系統提供以角色舞台為主體的單頁 Web App | P0 | 首屏可看到 VTuber、字幕區、對話紀錄與輸入區 |
| FR2 | 使用者可用文字輸入與角色進行多輪對話 | P0 | 可連續送出多則訊息，歷史訊息保留於當前 session |
| FR3 | 系統可根據角色設定生成一致風格的回覆 | P0 | 同一 session 內無明顯人格漂移，語氣符合角色設定 |
| FR4 | 系統可播放 AI 回覆語音，且不需等待全文完成 | P0 | 回覆可在可接受延遲內開始播音 |
| FR5 | 系統可同步驅動嘴型與基礎表情 | P0 | 語音播放時角色嘴型同步，情緒標籤可驅動至少 3 種表情 |
| FR6 | 系統可逐段顯示字幕並與語音節奏對齊 | P0 | 字幕更新不明顯落後於語音播放 |
| FR7 | 系統需有輸入前與輸出前的安全過濾 | P0 | 高風險內容可攔截、替換或中止，不直接播出 |
| FR8 | 系統保留人工停止播放或靜音的能力 | P1 | 使用者可快速停止當前回覆或關閉語音 |
| FR9 | 系統提供可嵌入 OBS 的舞台視圖 | P1 | 能以 Browser Source 方式顯示角色畫面與字幕 |
| FR10 | 系統記錄關鍵延遲與錯誤事件 | P1 | 可查詢 TTFT、TTFA、TTS/Renderer 失敗事件 |

### 6.3 User Stories

**US1**  
作為使用者，我希望輸入一句話後，角色能很快開口並做出表情反應，這樣我才會感覺自己是在和角色互動。  
Acceptance Criteria:
- 輸入後，角色在目標延遲內開始回應
- 語音、字幕與表情都能被感知到
- 整體互動不需要切換其他頁面或工具

**US2**  
作為創作者，我希望角色的回覆風格穩定，這樣我才能判斷這個人設是否成立。  
Acceptance Criteria:
- 角色人格可透過 prompt 或配置描述
- 多輪對話中語氣與措辭維持一致
- 情緒表現與角色設定不衝突

**US3**  
作為展示者，我希望這個頁面能直接拿來 demo，必要時再嵌到 OBS，而不是先做一整套直播平台整合。  
Acceptance Criteria:
- Web App 可獨立運作
- 角色舞台視圖可獨立輸出
- OBS 相容是加分需求，不阻塞核心互動

---

## 7. 成功指標、非功能需求與風險

### 7.1 Success Metrics

| 指標 | 目標 | 說明 |
|------|------|------|
| TTFA（輸入到首段音頻） | P50 < 1.5 秒，P95 < 2.5 秒 | 對話體感底線 |
| 表演同步品質 | 內部評估 4/5 以上 | 觀察嘴型、表情、字幕與語音是否協調 |
| 角色一致性感知 | 內部試用者 80% 以上認為角色風格穩定 | 驗證人格是否成立 |
| 回覆成功率 | > 95% | 從輸入到播音完整成功的比例 |
| Demo 可用性 | 30 分鐘展示過程重大故障 0 次 | 驗證原型可展示 |

### 7.2 Non-Functional Requirements

| 類別 | 要求 |
|------|------|
| 效能 | 回應延遲需足以維持角色互動感，不出現長時間空白 |
| 可用性 | 單次互動或 demo 過程需穩定，錯誤可恢復 |
| 可配置性 | 角色 prompt、聲線、表情映射與舞台配置可調整 |
| 可觀測性 | 需追蹤 TTFT、TTFA、TTS/Renderer 失敗率 |
| 安全性 | 輸入與輸出均需過濾，金鑰與敏感設定不可暴露前端 |
| 可維護性 | LLM、TTS、Renderer 模組可替換 |

### 7.3 主要風險與對策

| 風險 | 影響 | 對策 |
|------|------|------|
| 角色像聊天機器而不像角色 | 核心價值不成立 | 強化 persona prompt、字幕語氣、聲線選擇與表情映射 |
| 語音、嘴型、字幕不同步 | 沉浸感破壞 | 以音訊時間軸為主，字幕與表情跟隨播放狀態更新 |
| 回應延遲過高 | 體驗變鈍 | 串流 LLM、句段切分、低延遲 TTS |
| TTS 或渲染失敗造成整體中斷 | demo 不可用 | 模組降級，至少保留文字回覆與錯誤提示 |
| OBS 相容需求過早擴大 | 分散 MVP 焦點 | 將 OBS 視圖列為 P1，相容但不主導設計 |

### 7.4 里程碑

| 里程碑 | 交付內容 | 成功標準 |
|--------|----------|----------|
| M1 - Character Loop | 文字輸入 → LLM → TTS → 嘴型 | 可完成最小互動循環 |
| M2 - Demo Ready | 角色舞台、字幕、表情、安全層 | 可進行穩定展示 |
| M3 - Broadcast Compatible | 透明舞台視圖、OBS 相容輸出 | 可嵌入 Browser Source |
| M4 - Expanded Interaction | 更多角色配置、記錄與優化 | 角色體驗與可調性提升 |

---

## 8. 技術方案總覽

### 8.1 設計原則

1. 角色表演優先於聊天吞吐。
2. 低延遲優先於極致回答品質。
3. 頁面本身就是舞台，不把 VTuber 當成附屬元件。
4. 模組替換性優先於綁定單一供應商。
5. OBS 相容要預留，但不應主導 MVP 架構。

### 8.2 技術範圍

技術方案層回答以下問題：

- 如何從 Web UI 的文字輸入生成角色回覆
- 如何讓語音、字幕、嘴型與表情協同工作
- 如何把角色舞台做成可獨立展示、可嵌入 OBS 的視圖
- 如何讓系統安全、可追蹤且可替換

---

## 9. 系統架構與模組規格

### 9.1 高層架構

```text
Presentation Layer
  ├─ Character Stage UI
  ├─ Chat Transcript UI
  ├─ Subtitle Overlay
  └─ Text Input Composer

Interaction Layer
  ├─ Session Manager
  ├─ Persona Prompt Builder
  └─ Safety Pipeline

Generation Layer
  ├─ LLM Runtime
  ├─ Emotion Tagger
  └─ Response Segmenter

Performance Layer
  ├─ TTS Streamer
  ├─ Lip Sync Controller
  └─ Expression Mapper

Delivery Layer
  ├─ Audio Playback
  ├─ Stage Renderer
  └─ OBS-Compatible Stage View

Ops Layer
  ├─ Metrics
  ├─ Logs
  └─ Manual Controls
```

### 9.2 模組說明

#### Presentation Layer

- `Character Stage UI`: 頁面視覺主體，呈現 Live2D 或 VRM 角色
- `Chat Transcript UI`: 顯示使用者輸入與 AI 回覆歷史
- `Subtitle Overlay`: 顯示當前口播內容
- `Text Input Composer`: 主要輸入方式，支援送出、停止、重試等操作

#### Interaction Layer

- `Session Manager`: 維護當前對話 session、短期上下文與訊息狀態
- `Persona Prompt Builder`: 注入角色名稱、性格、語氣、禁區與回覆風格
- `Safety Pipeline`: 對輸入與輸出做規則過濾與審查

建議最小訊息格式：

```json
{
  "role": "user",
  "content": "你今天心情怎麼樣？",
  "timestamp": "2026-03-09T17:10:00+08:00",
  "session_id": "local-session-001"
}
```

#### Generation Layer

- `LLM Runtime`: 生成角色回覆，支援串流輸出
- `Emotion Tagger`: 為回覆附加情緒標籤，供表演層使用
- `Response Segmenter`: 將長回覆拆成可播出的句段，平衡自然度與延遲

情緒輸出格式示例：

```text
[EMOTION:happy] 我今天心情很好，因為你先來找我說話了。
```

#### Performance Layer

- `TTS Streamer`: 逐段合成並輸出語音
- `Lip Sync Controller`: 根據音訊包絡或音素資訊驅動嘴型
- `Expression Mapper`: 將情緒標籤映射為表情參數與切換節奏

建議最小表情集合：

| Emotion | Expression ID |
|---------|---------------|
| happy | exp_smile |
| sad | exp_sad |
| angry | exp_angry |
| surprised | exp_surprised |
| neutral | exp_default |

#### Delivery Layer

- `Audio Playback`: 負責頁面內播放角色語音
- `Stage Renderer`: 渲染角色、字幕與舞台視覺
- `OBS-Compatible Stage View`: 提供可獨立輸出的舞台路由，供 Browser Source 使用

#### Ops Layer

- `Metrics`: 記錄 TTFT、TTFA、播放長度、錯誤率
- `Logs`: 保存對話與錯誤事件
- `Manual Controls`: 提供停止當前回覆、切換靜音、重置 session

---

## 10. 延遲預算、可靠性與安全

### 10.1 端到端延遲預算

| 階段 | 目標延遲 |
|------|----------|
| UI input submit | < 30ms |
| Pre-filter | < 30ms |
| LLM TTFT | < 700ms |
| 句段切分 | < 250ms |
| TTS TTFA | < 400ms |
| 總計 | < 1,500ms |

目標體驗是：使用者送出文字後，約 1.5 秒內聽到角色開始回應。

### 10.2 可靠性要求

- 若 TTS 失敗，至少保留文字回覆與字幕
- 若表情或嘴型模組失敗，不應阻塞語音主流程
- 若單次回覆失敗，session 不應被破壞，可繼續下一輪對話
- 每次失敗需能追溯到請求、模型、TTS 供應商與前端播放狀態

### 10.3 安全要求

- 所有第三方金鑰僅存於後端或安全代理層
- 輸入與輸出皆需經過安全檢查
- 角色 prompt 需明確定義禁區與行為邊界
- 需支援人工停止、敏感詞替換與高風險回覆中止

---

## 11. 技術選型原則與建議基線

### 11.1 LLM 選型原則

選擇 LLM 時，優先順序如下：

1. 是否支援穩定串流輸出
2. 是否能維持角色口吻與短期上下文
3. TTFT 是否足以支撐即時體感
4. 成本與部署彈性
5. 是否容易透過系統提示控制輸出格式

建議基線：

- 雲端方案：低 TTFT、支援串流、可穩定格式化輸出
- 本地方案：在現有硬體上可維持穩定吞吐與角色一致性
- 抽象層：以 provider adapter 封裝，避免綁死單一模型

### 11.2 TTS 選型原則

選擇 TTS 時，優先順序如下：

1. 是否支援真正低延遲或串流輸出
2. 聲線是否具角色辨識度
3. TTFA 是否足夠低
4. 是否支援目標語言
5. 是否需要聲音克隆

建議基線：

- 第一版先求穩定與低延遲，不急著導入重型聲音克隆
- 若角色聲線辨識度成為關鍵，再進一步評估聲音克隆方案

### 11.3 Renderer 與整合建議

| 類別 | 建議 |
|------|------|
| Backend | Python 3.11+，FastAPI / WebSocket |
| Session / Logs | SQLite 或等價儲存 |
| Renderer | Live2D 或 VRM 的 Web Renderer |
| Audio Analysis | Web Audio API 或等價音訊分析 |
| OBS Compatibility | 獨立舞台路由 + 透明背景配置 |

### 11.4 建議技術基線

```text
Backend: Python 3.11+, FastAPI, WebSocket
LLM Adapter: OpenAI-compatible API 或本地推理服務
TTS Adapter: Streaming 或低延遲 TTS API / 本地 TTS
Session Store: SQLite
Frontend: Vue 3 或輕量 Web App
Live2D/VRM: pixi-live2d-display 或 Three.js VRM
Audio Sync: Web Audio API
Monitoring: structured logs + metrics exporter
```

---

## 12. 開放問題

- 第一版是否需要角色設定面板，還是先把角色 prompt 固定寫死？
- 角色舞台是否需要兩種視圖：互動版與純舞台版？
- TTS 是否要支援播放中斷與打字中斷重生成？
- 字幕應該逐 token、逐句，還是逐語音片段更新？
- OBS 相容要做到哪個程度才算 Phase 2 可交付？

---

## 13. 附錄：參考資源

| 資源 | 說明 |
|------|------|
| [Neuro-sama](https://www.youtube.com/@Neurosama) | 角色化 AI 互動體驗的代表案例 |
| [AIRI](https://github.com/moeru-ai/airi) | 開源 AI VTuber 專案，適合參考角色互動模組切分 |
| [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/open-llm-vtuber) | LLM、TTS、角色渲染整合範例 |
| [VTube Studio](https://denchisoft.com/) | Live2D 控制與整合常見方案 |
| [pixi-live2d-display](https://github.com/guansss/pixi-live2d-display) | Web 端 Live2D 渲染函式庫 |
| [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) | 本地聲音克隆與 TTS 研究方向 |
