# 🤖 Finance OS Bot (LINE Webhook)

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-Web_Framework-000000?style=flat&logo=flask&logoColor=white)
![LINE API](https://img.shields.io/badge/LINE-Messaging_API-00C300?style=flat&logo=line&logoColor=white)
![Render](https://img.shields.io/badge/Render-Deploy-46E3B7?style=flat&logo=render&logoColor=white)
![Gemini](https://img.shields.io/badge/Google%20AI-Gemini%202.5-8E75B2?style=flat&logo=googlebard&logoColor=white)

這是 **Finance OS** 的即時互動核心。
本專案是一個 **Flask Web Server**，部署於 **Render** 雲端平台。它負責 24 小時監聽 LINE 的 Webhook 事件，不僅能從 Notion 資料庫撈取財務數據，現在更整合了 **Google Gemini AI**，提供即時的飲食熱量分析與營養建議。

---

## 📜 版本歷程 (Version History)

### `app.py`
- **v2.1 (Latest)**：
    - **AI 營養師上線**：整合 **Google Gemini 2.5 Flash** 模型，實現「看圖算熱量」。
    - **雙圖比對邏輯**：支援「餐前」與「餐後」照片比對，自動計算完食率 (Consumption Rate)。
    - **營養素追蹤**：自動分析蛋白質、碳水、脂肪，並在 Flex Message 顯示每日攝取目標進度條。
    - **Notion 深度整合**：將分析結果寫入 Diet Log 資料庫，並將詳細建議寫入頁面內文 (Page Content)。
- **v1.2**：
    - **五大指令集結**：新增「預測」與「消費比較」功能。
    - **邏輯修復**：新增萬能數值提取器，完美支援 Notion Rollup 與 Formula 屬性。
    - **UI 優化**：實作 **「雙層輪播 (Split Carousel)」** 機制。
    - **圖表升級**：修正 QuickChart 邊距與中文亂碼問題。
- **v1.1**：新增健康檢查路由 (`/`)，支援 UptimeRobot 監控。
- **v1.0**：核心功能上線，支援基礎資產查詢。

---

## ✨ 機器人功能 (Bot Features)

系統支援 **「關鍵字查詢」** 與 **「圖片分析」** 雙模式。

| 關鍵字 / 動作 | 說明 | 視覺呈現 | 資料來源 |
| :--- | :--- | :--- | :--- |
| **`房貸`** | 查詢劍潭房貸剩餘本金與還款進度百分比。 | **Mega** (中型卡片) | `DB_MORTGAGE` |
| **`BTC`** | 查詢最新比特幣持有量，顯示距離 1 顆 BTC 的目標進度。 | **Mega** (中型卡片) | `DB_SNAPSHOT` |
| **`總資產`** | 撈取過去 120 天快照，生成堆疊面積圖，顯示資產結構變化。 | **Giga** (大型圖表) | `DB_SNAPSHOT` |
| **`預測`** | 基於歷史資產數據，透過 **蒙地卡羅 (Monte Carlo)** 模擬未來 10 年資產走勢。 | **Giga** (大型圖表) | `DB_SNAPSHOT` |
| **`消費比較`** | 顯示近 6 個月的消費折線圖，並自動計算上個月花費最高的類別與金額。 | **Giga** (大型圖表) | `DB_BUDGET` |
| **`(傳送圖片)`** | **v2.1 新增**：上傳餐前/餐後照片，AI 自動辨識食物、計算熱量與三大營養素，並給予建議。 | **Mega** (營養分析卡) | `DIET_DB_ID` (寫入) |

---

## 🛠️ 技術架構 (Tech Stack)

- **Web Framework**: [Flask](https://flask.palletsprojects.com/)
- **Server**: [Gunicorn](https://gunicorn.org/)
- **AI Model**: **Google Gemini 2.5 Flash** (via HTTP Requests)
- **Data Processing**: `NumPy` (模擬預測), `Base64` (影像處理)
- **Visualization**: [QuickChart.io](https://quickchart.io/) (生成靜態圖表)
- **Database**: Notion API (Rollup/Formula/Page Content 深度操作)

---

## 🚀 部署教學 (Deployment on Render)

### 1. 準備檔案
確保 Repository 包含：`app.py`, `diet_helper_v1_0.py`, `requirements.txt`, `Procfile`。

### 2. 環境變數設定 (Environment Variables)
**⚠️ v2.1 更新：必須新增 Google API Key 與 Diet DB ID**

請在 Render Dashboard > Environment 填入：

| Key | Value | 說明 |
| :--- | :--- | :--- |
| `LINE_CHANNEL_ACCESS_TOKEN` | (你的 Token) | LINE Messaging API |
| `LINE_CHANNEL_SECRET` | (你的 Secret) | LINE Messaging API |
| `NOTION_TOKEN` | (你的 Notion Token) | Notion Integration |
| `DB_MORTGAGE` | (房貸 DB ID) | 房貸管理 |
| `DB_SNAPSHOT` | (資產快照 DB ID) | 每日資產紀錄 |
| `BUDGET_DB_ID` | (預算 DB ID) | 預算控管 |
| **`GOOGLE_API_KEY`** | **(Gemini API Key)** | **v2.1 新增：AI 影像辨識** |
| **`DIET_DB_ID`** | **(飲食紀錄 DB ID)** | **v2.1 新增：飲食資料庫** |

### 3. 設定 LINE Webhook
Webhook URL：`https://你的Render網址/callback`

---

## 📝 關鍵邏輯說明

### 1. 萬能數值提取 (Universal Number Extractor)
Notion 的 API 針對 `Rollup` 和 `Formula` 的回傳格式非常複雜。本專案實作了 `extract_number()` 函式，能自動遞迴處理各種類型並自動取絕對值。

### 2. 雙層輪播 (Split Carousel)
為解決 LINE Flex Message 限制同一個 Carousel 內 Bubble Size 必須一致的問題，程式會將回應拆分為兩個獨立的 Flex Message 連續發送。

### 3. 未來月份過濾
讀取預算資料時，系統會自動比對當前日期，排除未來月份的空白資料。

### 4. AI 視覺分析與狀態機 (v2.1 New)
- **HTTP 請求繞過 SSL**：為解決 Render/Local 環境的 gRPC 連線問題，改用原生 `requests` 呼叫 Gemini API。
- **狀態機 (State Machine)**：系統在記憶體中維護使用者狀態 (`user_sessions`)，自動判斷傳來的圖片是「餐前 (Before)」還是「餐後 (After)」。
- **Notion 寫入策略**：因 Notion API 不支援直接上傳圖片檔，系統改將 AI 分析數據寫入 Properties，並將詳細文字建議與數據寫入 **Page Content (Block)**，實現無圖床的資料保存。

---

## ⚠️ 注意事項
- **Render 休眠**：免費版 15 分鐘無人使用會休眠，喚醒時第一則訊息可能延遲 30-50 秒。
- **Gemini Quota**：免費版 API 有速率限制，若頻繁傳圖可能會遇到 `429 Too Many Requests`。
- **QuickChart 中文支援**：圖表標籤建議使用英文或純數字以防亂碼。
