# 🤖 Finance OS Bot (LINE Webhook)

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-Web_Framework-000000?style=flat&logo=flask&logoColor=white)
![LINE API](https://img.shields.io/badge/LINE-Messaging_API-00C300?style=flat&logo=line&logoColor=white)
![Render](https://img.shields.io/badge/Render-Deploy-46E3B7?style=flat&logo=render&logoColor=white)

這是 **Finance OS** 的即時互動核心。
本專案是一個 **Flask Web Server**，部署於 **Render** 雲端平台。它負責 24 小時監聽 LINE 的 Webhook 事件，當使用者輸入特定關鍵字時，即時從 Notion 資料庫撈取數據、繪製圖表，並回傳精美的 Flex Message。

---

## 📜 版本歷程 (Version History)

### `app.py`
- **v1.2 (Current)**：
    - **五大指令集結**：新增「預測」與「消費比較」功能。
    - **邏輯修復**：新增萬能數值提取器 (Universal Extractor)，完美支援 Notion Rollup 與 Formula 屬性；增加月份過濾機制，防止讀取到未來日期的空白預算。
    - **UI 優化**：實作 **「雙層輪播 (Split Carousel)」** 機制，解決 LINE Flex Message 不同尺寸 (Mega/Giga) 無法混用的限制。
    - **圖表升級**：修正 QuickChart 邊距 (Padding)，確保 X 軸年份與月份不被裁切；優化蒙地卡羅模擬圖表，採用純數字 Y 軸與英文標籤以防亂碼。
- **v1.1**：新增健康檢查路由 (`/`)，支援 UptimeRobot 監控。
- **v1.0**：核心功能上線，支援基礎資產查詢。

---

## ✨ 機器人功能 (Bot Features)

系統支援 **「關鍵字 1 對 1」** 查詢，或輸入 **`Dashboard`** / **`資產`** 一次調閱所有卡片。

| 關鍵字 | 說明 | 視覺呈現 | 資料來源 |
| :--- | :--- | :--- | :--- |
| **`房貸`** | 查詢劍潭房貸剩餘本金與還款進度百分比。 | **Mega** (中型卡片) | `DB_MORTGAGE` |
| **`BTC`** | 查詢最新比特幣持有量，顯示距離 1 顆 BTC 的目標進度。 | **Mega** (中型卡片) | `DB_SNAPSHOT` |
| **`總資產`** | 撈取過去 120 天快照，生成堆疊面積圖，顯示資產結構變化。 | **Giga** (大型圖表) | `DB_SNAPSHOT` |
| **`預測`** | 基於歷史資產數據，透過 **蒙地卡羅 (Monte Carlo)** 模擬未來 10 年資產走勢 (含樂觀/中位/悲觀)。 | **Giga** (大型圖表) | `DB_SNAPSHOT` |
| **`消費比較`** | 顯示近 6 個月的消費折線圖，並自動計算上個月花費最高的類別與金額。 | **Giga** (大型圖表) | `DB_BUDGET` |

---

## 🛠️ 技術架構 (Tech Stack)

- **Web Framework**: [Flask](https://flask.palletsprojects.com/)
- **Server**: [Gunicorn](https://gunicorn.org/)
- **Data Processing**: `NumPy` (用於蒙地卡羅模擬與數據分析)
- **Visualization**: [QuickChart.io](https://quickchart.io/) (生成靜態圖表)
- **Database**: Notion API (Rollup/Formula 屬性深度解析)

---

## 🚀 部署教學 (Deployment on Render)

### 1. 準備檔案
確保 Repository 包含：`app.py`, `requirements.txt`, `Procfile`。

### 2. 環境變數設定 (Environment Variables)
**⚠️ v1.2 更新：必須新增 `BUDGET_DB_ID`**

請在 Render Dashboard > Environment 填入：

| Key | Value | 說明 |
| :--- | :--- | :--- |
| `LINE_CHANNEL_ACCESS_TOKEN` | (你的 Token) | LINE Messaging API |
| `LINE_CHANNEL_SECRET` | (你的 Secret) | LINE Messaging API |
| `NOTION_TOKEN` | (你的 Notion Token) | Notion Integration |
| `DB_MORTGAGE` | (房貸 DB ID) | 房貸管理 |
| `DB_SNAPSHOT` | (資產快照 DB ID) | 每日資產紀錄 |
| **`BUDGET_DB_ID`** | **(預算 DB ID)** | **v1.2 新增：預算控管** |

### 3. 設定 LINE Webhook
Webhook URL：`https://你的Render網址/callback`

---

## 📝 關鍵邏輯說明

### 1. 萬能數值提取 (Universal Number Extractor)
Notion 的 API 針對 `Rollup` 和 `Formula` 的回傳格式非常複雜。本專案實作了 `extract_number()` 函式，能自動遞迴處理：
- 純數字 (`number`)
- 公式計算結果 (`formula.number`)
- 關聯表匯總 (`rollup.number` 或 `rollup.array` 加總)
- **自動取絕對值**：針對消費支出負數，自動轉為正數以利圖表繪製。

### 2. 雙層輪播 (Split Carousel)
LINE Flex Message 限制同一個 Carousel 內的所有 Bubble Size 必須一致。
為了達成「房貸/BTC 用小卡(Mega)」、「圖表用大卡(Giga)」的設計，程式會將回應拆分為 **兩個獨立的 Flex Message** 連續發送。

### 3. 未來月份過濾
讀取預算資料時，系統會自動比對當前日期，**排除未來月份** (例如現在 2 月，會自動忽略已建立但空白的 3 月頁面)，確保「上月最大消費」計算正確。

---

## ⚠️ 注意事項
- **Render 休眠**：免費版 15 分鐘無人使用會休眠，喚醒時第一則訊息可能延遲 30-50 秒。
- **QuickChart 中文支援**：為避免中文亂碼，圖表標籤 (X/Y軸、Legend) 建議使用英文或純數字 (e.g., "26-02", "Spending Trend")。
