# 容容角色與專屬 Live2D V 皮設計

## 目標

新增角色 `rongrong`（容容），定位為親切活潑、擅長聊天互動的生活型直播主。容容使用本次產生的新版 Haru texture；既有角色露娜與艾莉亞仍使用原本的 Live2D V 皮。

## 範圍

- 新增容容的後端角色 YAML。
- 讓角色摘要既有的 `profile.avatar` 欄位實際控制前端 Live2D 模型路徑。
- 建立語意化的容容 model manifest 與兩張 texture 副本。
- 讓主聊天頁與獨立 Stage 頁依 session 綁定角色顯示正確 V 皮。
- 增加最小回歸測試，防止既有角色意外切換 V 皮。

不修改 `.moc3`、physics、pose、motions 或 expressions。容容和原 Haru 共用這些 rig 資產，因此本次只改外觀，不改模型輪廓或動作能力。

## 角色設定

新增 `backend/app/characters/definitions/rongrong.yaml`：

- `id`: `rongrong`
- 名稱：容容
- 短介：親切活潑的生活型直播主
- 個性：自然外向、重視觀眾感受、善於從日常話題延伸互動
- 說話方式：繁體中文、口語但不浮誇、短句為主、主動接話
- 邊界：沿用既有角色的政治、醫療、法律與危險行為限制
- 背景：以生活分享與聊天互動為主要直播內容
- `profile.avatar`: `/live2d/haru/rongrong.model3.json`

既有 `luna.yaml` 與 `aria.yaml` 保持 `avatar: null`，代表使用前端預設 Haru manifest。

## Live2D 資產

在既有 Haru 目錄新增：

- `rongrong.model3.json`
- `haru_greeter_t03.2048/texture_00_rongrong.png`
- `haru_greeter_t03.2048/texture_01_rongrong.png`

兩張 texture 分別由目前已驗證的 `texture_00_reference_face_v2.png` 與 `texture_01_reference_striped_outfit.png` 複製並改名。`rongrong.model3.json` 只把 texture references 改為新檔名；其餘 `.moc3`、physics、pose、expressions 與 motions 路徑沿用原 Haru manifest。

原 manifest 和原 texture 不改名、不覆寫，確保既有角色外觀不受影響。

## 資料流

後端 `/api/characters` 已透過 `Character.to_summary()` 回傳 `avatar`，不新增 API 欄位。

主聊天頁：

1. 載入角色列表。
2. 依 `characterId` 找到目前角色。
3. 將角色的 `avatar` 傳給 `Live2DStage.modelPath`；`avatar` 為空時沿用 `Live2DStage` 預設模型。
4. 切換角色時，現有 `modelPath` effect 會卸載舊模型並載入新模型。

獨立 Stage 頁：

1. 從目前 session 資料取得 `character_id`。
2. 載入角色列表並解析該角色的 `avatar`。
3. 將解析後路徑傳給 `Live2DStage`。
4. 查不到角色或 `avatar` 為空時使用預設模型；既有 fallback avatar 錯誤處理維持不變。

不建立新的角色到模型 mapping 檔，避免讓後端 YAML 與前端硬編碼重複成為兩個來源。

## 驗證

後端測試：

- 預設 registry 包含 `rongrong`。
- 容容摘要名稱與 `avatar` 正確。
- 露娜與艾莉亞的 `avatar` 仍為 `null`。

Live2D 資產測試：

- `rongrong.model3.json` 只引用兩張容容 texture。
- 容容 texture 是 2048x2048 RGBA，alpha 與各自來源完全一致。
- 原 Haru manifest 仍引用原始 `texture_00.png`、`texture_01.png`。

前端測試採用目前已存在的輕量 Node 測試風格，鎖定角色 avatar 到 `Live2DStage.modelPath` 的選擇與 Stage session 路徑，不引入新測試框架。

最後執行後端測試、前端 build、靜態資產 HTTP 檢查，並在瀏覽器切換容容／露娜／艾莉亞做視覺驗證。
