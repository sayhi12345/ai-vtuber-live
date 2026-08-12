# 容容角色與專屬 Live2D V 皮設計

## 目標

新增角色 `rongrong`（容容），定位為親切活潑、擅長聊天互動的生活型直播主。容容使用新版 Haru texture；既有角色露娜與艾莉亞仍使用原本的 Live2D V 皮。

## 設計

- 新增容容角色 YAML，並以既有 `profile.avatar` 欄位指向 `/live2d/haru/rongrong.model3.json`。
- 新增語意化的 `texture_00_rongrong.png` 與 `texture_01_rongrong.png`；不覆寫原 Haru texture。
- `rongrong.model3.json` 僅替換 texture references，其餘 rig、動作、表情、physics 與 pose 沿用原 Haru。
- 主聊天頁依目前角色的 `avatar` 載入 V 皮；獨立 Stage URL 攜帶 `character_id` 並解析同一欄位。
- 露娜與艾莉亞維持 `avatar: null`，繼續使用前端預設模型。

本次不修改 `.moc3`、mesh、physics、pose、motions 或 expressions，因此只改外觀，不改模型輪廓與動作能力。內部 ID 與檔名保留 `rongrong`，中文顯示名稱使用「容容」。

## 驗證

- 預設 registry 包含容容，且既有角色 avatar 仍為空。
- 容容 manifest 只引用兩張專屬 2048x2048 RGBA texture。
- 原 Haru manifest 仍引用原始 texture。
- 主頁與獨立 Stage 都依角色 avatar 選擇模型。
- 後端測試、前端 Node 測試與 production build 通過。
