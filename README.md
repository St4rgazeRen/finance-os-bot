# 🤖 Finance OS Bot (LINE Webhook)

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-Web_Framework-000000?style=flat&logo=flask&logoColor=white)
![LINE API](https://img.shields.io/badge/LINE-Messaging_API-00C300?style=flat&logo=line&logoColor=white)
![Render](https://img.shields.io/badge/Render-Deploy-46E3B7?style=flat&logo=render&logoColor=white)
![Gemini](https://img.shields.io/badge/Google%20AI-Gemini%202.5-8E75B2?style=flat&logo=googlebard&logoColor=white)

這是 **Finance OS** 的即時互動核心。
本專案是一個 **Flask Web Server**，部署於 **Render** 雲端平台。它負責 24 小時監聽 LINE 的 Webhook 事件。
除了基礎的記帳與資產查詢，**v3.0** 引入了強大的 **RAG (檢索增強生成)** 系統，整合 **15+ 個 Notion 資料庫**，讓機器人化身為全能的財務與生活助理，能聽懂自然語言並給予專業分析。

---

## 📜 版本歷程 (Version History)

### `app.py`
- **v3.0 (Major Update)**：
    - **RAG 逆向查詢大腦**：不再只能看圖，現在能「讀取」Notion 資料庫。支援投資、財務、健康、知識四大領域的自然語言問答（例如：「上個月飲料花多少？」、「台積電現在庫存？」）。
    - **極速並行架構 (Concurrent Fetching)**：導入 `ThreadPoolExecutor` 多執行緒技術，同時撈取多個資料庫，查詢速度提升 500%。
    - **混合式 UI 回覆**：首創「Flex Message 儀表板 + Text 詳細分析」混合回覆模式，解決單一卡片資訊量不足的問題。
    - **額度熔斷機制 (Quota Protection)**：自動偵測 Gemini API `429` 錯誤，當額度用罄時優雅降級提醒，防止系統崩潰。

### `diet_helper.py`
- **v1.1 (Update)**：
    - **時區校正 (Timezone Fix)**：全面採用台灣時間 (UTC+8)，解決跨日與餐別判斷錯誤。
    - **Flex Message 升級**：新增「營養素進度條」視覺化卡片，紅/黃/藍三色呈現蛋白質/碳水/脂肪比例。
    - **Notion 寫入優化**：自動將識別出的食物名稱填入標題，並在 Callout區塊 顯示詳細數值與百分比。
    - **Prompt 精確控制**：限制 AI 建議字數 (30-50字)，確保手機閱讀體驗最佳化。
    - **穩定性提升**：強制關閉 SSL 驗證以適應各種網路環境。
- **v1.0**：
    - **AI 營養師**：整合 Gemini 2.5 Flash，實現「看圖算熱量」。
    - **雙圖比對**：支援餐前/餐後照片比對，計算完食率。

### 歷史版本
- **v1.2**：
    - **五大指令集結**：新增「預測」與「消費比較」。
    - **萬能數值提取器**：完美支援 Notion Rollup 與 Formula。
    - **UI 優化**：實作雙層輪播 (Split Carousel)。
- **v1.0**：核心功能上線，支援基礎資產查詢。

---

## ✨ 機器人功能 (Bot Features)

系統支援 **「關鍵字指令」**、**「圖片分析」** 與 **「自然語言問答」** 三種模式。

| 模式 | 關鍵字 / 動作 | 說明 | 視覺呈現 | 資料來源 |
| :--- | :--- | :--- | :--- | :--- |
| **指令** | **`房貸`** | 查詢房貸剩餘本金與進度。 | **Mega** (中型卡片) | `DB_MORTGAGE` |
| **指令** | **`BTC`** | 查詢比特幣持有量與目標進度。 | **Mega** (中型卡片) | `DB_SNAPSHOT` |
| **指令** | **`總資產`** | 生成過去 120 天資產堆疊圖。 | **Giga** (大型圖表) | `DB_SNAPSHOT` |
| **指令** | **`預測`** | 蒙地卡羅模擬未來 10 年資產。 | **Giga** (大型圖表) | `DB_SNAPSHOT` |
| **指令** | **`消費比較`** | 近 6 個月消費折線圖與最大開銷。 | **Giga** (大型圖表) | `DB_BUDGET` |
| **視覺** | **`(傳送食物照)`** | AI 自動辨識食物、計算熱量與營養素。 | **Flex Message** (營養進度條) | `DIET_DB_ID` |
| **RAG** | **`(自然語言提問)`** | 例：「上個月花多少？」、「台股庫存？」、「最近有吃太油嗎？」 | **Mega** (數據卡) + **Text** (AI分析) | **全資料庫聯網** |

---

## 🛠️ 技術架構 (Tech Stack)

- **Web Framework**: [Flask](https://flask.palletsprojects.com/)
- **Server**: [Gunicorn](https://gunicorn.org/)
- **AI Core**: **Google Gemini 2.5 Flash** (主力)
- **RAG Engine**: 
    - **Router**: 意圖識別 (Intent Recognition)
    - **Retriever**: `concurrent.futures` (並行撈取 Notion API)
    - **Generator**: 混合式回應生成 (JSON + Natural Language)
- **Database**: Notion API (深度整合 15+ 資料庫)

---

## 🚀 部署教學 (Deployment on Render)

### 1. 準備檔案
確保 Repository 包含：
- `app.py` (主程式)
- `diet_helper_v1_1.py` (AI 營養師)
- `rag_helper_v1_0.py` (RAG 逆向查詢引擎)
- `requirements.txt`
- `Procfile`

### 2. 環境變數設定 (Environment Variables)
**⚠️ v3.0 重大更新：必須補齊 RAG 所需的所有資料庫 ID**

請在 Render Dashboard > Environment 填入：

**基礎設定**
- `LINE_CHANNEL_ACCESS_TOKEN` / `LINE_CHANNEL_SECRET`
- `NOTION_TOKEN` / `GOOGLE_API_KEY`

**財務資料庫 (Finance)**
- `DB_MORTGAGE` (房貸)
- `DB_SNAPSHOT` (資產快照)
- `BUDGET_DB_ID` (預算)
- `TRANSACTIONS_DB_ID` (流水帳 - 核心)
- `INCOME_DB_ID` (收入)
- `DB_ACCOUNT` (帳戶總覽)

**投資資料庫 (Investment)**
- `DB_TW_STOCK` (台股)
- `DB_US_STOCK` (美股)
- `DB_CRYPTO` (加密貨幣)
- `DB_GOLD` (黃金)
- `PAY_LOSS_DB_ID` (已實現損益)

**生活與知識 (Life & Knowledge)**
- `DIET_DB_ID` (飲食紀錄)
- `FLASH_DB_ID` (閃電筆記)
- `LITERATURE_DB_ID` (文獻筆記)
- `PERMAMENT_DB_ID` (永久筆記)

### 3. 設定 LINE Webhook
Webhook URL：`https://你的Render網址/callback`

---

## 📝 關鍵邏輯說明 (v3.0 Highlight)

### 1. RAG 動態路由 (Intent Router)
當使用者輸入非指令文字時，系統會先透過 Gemini 判斷意圖：
- **INVESTMENT**: 鎖定股票、幣、資產 DB。
- **FINANCE**: 鎖定記帳、預算、房貸 DB。
- **HEALTH**: 鎖定飲食 DB。
- **KNOWLEDGE**: 全域搜尋筆記 DB。
系統只會開啟相關的資料庫進行搜尋，節省資源並提高準確度。

### 2. 極速並行撈取 (Concurrent Fetching)
為了處理跨資料庫查詢（例如同時查台股+美股+匯率），程式使用了 Python 的 `ThreadPoolExecutor`。
這讓機器人能**同時**發送多個 Notion API 請求，將原本需要 10-15 秒的查詢時間壓縮至 **2-3 秒**。

### 3. 混合式 UI 回覆 (Hybrid Response)
Flex Message 雖然美觀但有長度限制。v3.0 採用混合策略：
- **Flex Message**: 顯示 `title`, `main_stat` (總金額/總熱量), `details` (前 5 大項目)。根據領域自動切換主題色（紅/藍/綠/橘）。
- **Text Message**: 緊隨其後發送 AI 的詳細分析建議，保留了 LLM 的深度推理價值。

### 4. 額度熔斷保護
針對 Gemini API 的 Rate Limit (`429 Quota Exceeded`)，系統在 `ask_gemini` 與 `analyze_image` 層級都加入了攔截器。一旦偵測到額度用罄，會即時回傳友善提示（「💸 今日 TOKEN 已用罄」），確保機器人不會因報錯而停止運作。

### 5. AI 營養師進化 (Diet Helper v1.1)
- **視覺化回饋**：不再只是文字，現在會回傳一張包含熱量環狀圖與三大營養素進度條的 Flex Message。
- **精準數據寫入**：優化寫入 Notion 的邏輯，確保時間戳記為台灣時間，並自動計算每日目標百分比 (基於 2300kcal/100p/280c/75f)。

---

## ⚠️ 注意事項
- **Render 休眠**：免費版 15 分鐘無人使用會休眠，喚醒時第一則訊息可能延遲。
- **Gemini Quota**：Gemini 2.5 Flash 每日約 20 次限制，若用量大建議申請多組 API Key 或切換至 Lite 模型。
- **Notion 權限**：新增資料庫 ID 後，務必記得在 Notion 頁面將該資料庫 **Share** 給 Integration Robot。
