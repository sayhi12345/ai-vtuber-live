# Live2D 載入設計

日期：2026-03-09

## 需求確認

- 導入 Live2D 模型載入能力。
- 預設模型路徑：`frontend/public/live2d/model.model3.json`。
- 本次不做表情映射，列為 TODO。

## 採用方案

採用 `pixi.js + pixi-live2d-display`：

- 以 `Live2DStage` 取代主舞台渲染。
- 透過 `VITE_LIVE2D_MODEL_PATH` 設定模型檔路徑。
- 模型載入失敗時自動 fallback 到既有 `StageAvatar`，不中斷字幕/音訊流程。

## 控制策略

- 嘴型同步：若模型存在 `ParamMouthOpenY`，使用現有 `mouthOpen` 值驅動。
- 表情映射：暫不實作（TODO）。

## 影響範圍

- `frontend/package.json` 新增 Live2D 相關依賴。
- `frontend/src/components` 新增 `Live2DStage.jsx`。
- `frontend/src/App.jsx` 兩處舞台元件改用 `Live2DStage`。
- `frontend/src/styles.css` 新增 Live2D canvas 相關樣式。
- `.env.example` 與 `README.md` 補充模型路徑與資產放置說明。
