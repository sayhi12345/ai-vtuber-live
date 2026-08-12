# 鄧捷角色設計

## 目標

新增獨立角色「鄧捷」，讓角色選單可選取她並預覽專屬 Live2D V 皮。既有「容容」、Luna 與 Aria 的設定和資源維持不變。

## 角色設定

- 角色 ID：`dengjie`
- 顯示名稱：鄧捷
- 定位：陪伴型互動 AI 主播，主題涵蓋星座、MBTI、心理測驗、熱門話題與生活聊天。
- 關鍵字：溫柔、細膩、有共感、愛觀察、浪漫、可愛。
- 喜好：星座與星座排行、MBTI 與心理測驗、熱門話題與網路趨勢、動畫電影、可愛小物與娃娃收藏、攝影與拍照構圖、濾鏡分享、咖啡與甜點。
- 直播感：像熟悉且會陪伴聊天的朋友，先承接情緒，再自然延伸對話；避免分析師、老師或說教式口吻。

## Live2D 資源

沿用已完成且驗證過的獨立 V 皮內容，將檔名對齊角色 ID：

- Manifest：`/live2d/haru/dengjie.model3.json`
- 臉部與頭髮：`texture_00_dengjie.png`
- 服裝：`texture_01_dengjie.png`

Manifest 繼續使用 Haru 的 `.moc3`、physics、pose、expressions 和 motions，只替換兩張 texture。現有骨架輪廓不變，因此馬尾仍屬模型的一部分。

## 資料流

後端啟動時由既有角色 loader 自動讀取 `definitions/dengjie.yaml`。前端不新增專用 UI；既有角色選單透過角色摘要 API 顯示「鄧捷」，選取後使用摘要中的 avatar 路徑載入 `dengjie.model3.json`。

## 驗證

- 角色 registry 包含 `dengjie`，名稱、簡介與 avatar 路徑正確。
- 容容、Luna 與 Aria 的角色摘要不變。
- `dengjie.model3.json` 為有效 JSON，且引用的兩張 texture 存在。
- Manifest 與 texture 經前端 HTTP 請求皆回應 200。
- 在瀏覽器選取「鄧捷」後，模型成功載入且無白邊、UV 錯位或缺圖。
