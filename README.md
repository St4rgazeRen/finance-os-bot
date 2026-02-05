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
- **v1.0**：核心功能上線。支援「房貸、BTC、總資產」關鍵字，整合 QuickChart 繪製黑底財經圖表，並回傳 LINE Flex Message。
- **v1.1**：新增健康檢查路由 (`/`)。支援 UptimeRobot 定時監控，防止 Render 免費版進入休眠模式，消除 Cold Start 延遲。

---

## ✨ 機器人功能 (Bot Features)

當你在 LINE 聊天室輸入以下關鍵字時，機器人會觸發對應動作：

| 關鍵字 | 動作 | 資料來源 |
| :--- | :--- | :--- |
| **`房貸`** | 查詢房貸資料庫，計算剩餘本金與還款進度百分比，回傳進度條卡片。 | Notion `DB_MORTGAGE` |
| **`BTC`** | 查詢資產快照，取得最新比特幣持有量，計算距離 1 顆 BTC 的目標進度。 | Notion `DB_SNAPSHOT` |
| **`總資產`** | 撈取過去 30 天的資產快照，透過 QuickChart 生成「堆疊面積圖 (Stacked Area Chart)」，顯示資產變化趨勢。 | Notion `DB_SNAPSHOT` |

---

## 🛠️ 技術架構 (Tech Stack)

- **Web Framework**: [Flask](https://flask.palletsprojects.com/) (Python)
- **WSGI Server**: [Gunicorn](https://gunicorn.org/) (用於生產環境部署)
- **Visualization**: [QuickChart.io](https://quickchart.io/) (生成靜態圖表圖片)
- **Messaging**: [LINE Bot SDK](https://github.com/line/line-bot-sdk-python)
- **Database**: Notion API (作為 Backend Database)

---

## 🚀 部署教學 (Deployment on Render)

本專案已優化為可直接部署於 **Render.com** (Free Web Service)。

### 1. 準備檔案
確保 Repository 包含以下關鍵檔案：
- `app.py`: 主程式邏輯。
- `requirements.txt`: 依賴套件清單 (`flask`, `line-bot-sdk`, `gunicorn`, etc.)。
- `Procfile`: Render 啟動指令 (`web: gunicorn app:app`)。

### 2. Render 設定
1. 在 Render 新增 **Web Service**，連結此 GitHub Repo。
2. **Name**: `finance-os-bot` (或自訂)
3. **Region**: Singapore (建議，離台灣近)
4. **Branch**: `main`
5. **Runtime**: `Python 3`
6. **Build Command**: `pip install -r requirements.txt`
7. **Start Command**: `gunicorn app:app`

### 3. 設定環境變數 (Environment Variables)
在 Render Dashboard 的 **Environment** 分頁，填入以下變數：

| Key | Value |
| :--- | :--- |
| `LINE_CHANNEL_ACCESS_TOKEN` | 你的 LINE Channel Access Token |
| `LINE_CHANNEL_SECRET` | 你的 LINE Channel Secret |
| `NOTION_TOKEN` | Notion Integration Token |
| `DB_MORTGAGE` | 房貸資料庫 ID |
| `DB_SNAPSHOT` | 每日資產快照資料庫 ID |
| `PYTHON_VERSION` | `3.10.0` (建議指定版本) |

### 4. 設定 LINE Webhook
1. 等待 Render 部署完成，取得 Service URL (例如 `https://finance-os-bot.onrender.com`)。
2. 前往 **LINE Developers Console** > Messaging API > Webhook settings。
3. 填入 Webhook URL：`https://你的Render網址/callback`
4. 點擊 **Verify** 確認連線成功。
5. 開啟 **Use webhook**。

---

## 💻 本地開發 (Local Development)

若要在本機測試 (需使用 Ngrok 穿透或僅測試邏輯)：

1. **安裝套件**
   ```bash
   pip install -r requirements.txt
   ```

2. **設定環境變數**
   建立 `.env` 檔案：
   ```ini
   LINE_CHANNEL_ACCESS_TOKEN=...
   LINE_CHANNEL_SECRET=...
   NOTION_TOKEN=...
   DB_MORTGAGE=...
   DB_SNAPSHOT=...
   ```

3. **啟動伺服器**
   ```bash
   python app.py
   # 或是
   flask run
   ```
   伺服器將啟動於 `http://127.0.0.1:5000`。

---

## 📝 檔案結構

```text
.
├── app.py              # 核心程式：Flask Server + LINE Bot 邏輯
├── Procfile            # Render 部署指令
├── requirements.txt    # 套件依賴清單
└── README.md           # 專案說明
```

---

## ⚠️ 注意事項
- **Render 免費版限制**：若網站 15 分鐘無人存取，會進入休眠。喚醒時（第一次傳訊息）可能會有 30-50 秒的延遲，此為正常現象。
- **圖表生成**：依賴 QuickChart 免費 API，若圖表顯示失敗，請檢查網路連線或 QuickChart 服務狀態。
