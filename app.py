import os
import json
import requests
import urllib3
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, FlexSendMessage

# 關閉 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ==========================================
# 0. 環境變數與設定
# ==========================================
# 注意：部署到 Render 時，這些變數要在 Render 後台設定
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DB_MORTGAGE = os.getenv("DB_MORTGAGE")
DB_SNAPSHOT = os.getenv("DB_SNAPSHOT")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# 參數設定
LOAN_TOTAL_PRINCIPAL = 5330000
BTC_GOAL = 1.0

# ==========================================
# 1. Notion 資料讀取函式 (沿用 v1.0)
# ==========================================
def get_current_mortgage():
    try:
        res = requests.post(f"https://api.notion.com/v1/databases/{DB_MORTGAGE}/query", headers=NOTION_HEADERS, json={"page_size": 1}, verify=False)
        data = res.json()
        if data["results"]:
            props = data["results"][0]["properties"]
            return props.get("剩餘本金", {}).get("number", LOAN_TOTAL_PRINCIPAL)
    except: pass
    return LOAN_TOTAL_PRINCIPAL

def get_asset_history(days=30):
    query = {"page_size": days, "sorts": [{"property": "日期", "direction": "descending"}]}
    try:
        res = requests.post(f"https://api.notion.com/v1/databases/{DB_SNAPSHOT}/query", headers=NOTION_HEADERS, json=query, verify=False)
        data = res.json()
        results = data.get("results", [])
        
        history = {"dates": [], "crypto": [], "us_stock": [], "tw_stock": [], "gold": [], "cash": [], "btc_holdings": []}
        
        for p in reversed(results):
            props = p["properties"]
            date_str = props.get("日期", {}).get("date", {}).get("start", "")
            if not date_str: continue
            
            d_fmt = datetime.strptime(date_str, "%Y-%m-%d").strftime("%m/%d")
            history["dates"].append(d_fmt)
            history["crypto"].append(props.get("Crypto", {}).get("number", 0) or 0)
            history["us_stock"].append(props.get("美股複委託", {}).get("number", 0) or 0)
            history["tw_stock"].append(props.get("台股證券戶", {}).get("number", 0) or 0)
            history["gold"].append(props.get("Gold", {}).get("number", 0) or 0)
            history["cash"].append(props.get("活存", {}).get("number", 0) or 0)
            history["btc_holdings"].append(props.get("BTC持有量", {}).get("number", 0) or 0)
        return history
    except: return None

# ==========================================
# 2. 圖表生成工具
# ==========================================
def get_chart_url(chart_config):
    chart_config["options"]["layout"] = {"padding": {"left": 20, "right": 20, "top": 20, "bottom": 10}}
    scales = {
        "xAxes": [{"gridLines": {"color": "#333333", "zeroLineColor": "#555555"}, "ticks": {"fontColor": "#bbbbbb", "fontSize": 10}}],
        "yAxes": [{"gridLines": {"color": "#333333", "zeroLineColor": "#555555"}, "ticks": {"fontColor": "#bbbbbb", "fontSize": 10}, "stacked": True}]
    }
    chart_config["options"]["scales"] = scales
    chart_config["options"]["legend"] = {"labels": {"fontColor": "#ffffff", "fontSize": 11}}
    
    payload = {"chart": chart_config, "width": 500, "height": 300, "backgroundColor": "#121212"}
    try:
        res = requests.post("https://quickchart.io/chart/create", json=payload, verify=False)
        if res.status_code == 200: return res.json().get('url')
    except: pass
    return "https://via.placeholder.com/500x300?text=Chart+Error"

# ==========================================
# 3. 卡片生成器
# ==========================================
def create_mortgage_card(remaining):
    paid = LOAN_TOTAL_PRINCIPAL - remaining
    percent = (paid / LOAN_TOTAL_PRINCIPAL) * 100
    bar_width = f"{min(percent, 100)}%"
    return {
        "type": "bubble", "size": "giga",
        "header": {
            "type": "box", "layout": "vertical", "backgroundColor": "#1e1e1e", "paddingAll": "20px",
            "contents": [
                {"type": "text", "text": "MORTGAGE PROGRESS", "color": "#27ae60", "size": "xs", "weight": "bold"},
                {"type": "text", "text": "劍潭房貸還款進度", "weight": "bold", "size": "xl", "color": "#ffffff"}
            ]
        },
        "body": {
            "type": "box", "layout": "vertical", "backgroundColor": "#1e1e1e", "paddingAll": "20px",
            "contents": [
                {"type": "box", "layout": "horizontal", "contents": [{"type": "text", "text": "剩餘本金", "size": "sm", "color": "#aaaaaa", "flex": 1}, {"type": "text", "text": f"${remaining:,.0f}", "weight": "bold", "color": "#ef5350", "align": "end"}]},
                {"type": "separator", "margin": "lg", "color": "#333333"},
                {"type": "box", "layout": "vertical", "margin": "lg", "spacing": "sm", "contents": [
                    {"type": "box", "layout": "baseline", "contents": [{"type": "text", "text": "還款進度", "size": "xs", "color": "#aaaaaa", "flex": 1}, {"type": "text", "text": f"{percent:.2f}%", "size": "xs", "color": "#27ae60", "weight": "bold", "align": "end"}]},
                    {"type": "box", "layout": "vertical", "backgroundColor": "#333333", "height": "6px", "cornerRadius": "30px", "contents": [{"type": "box", "layout": "vertical", "width": bar_width, "backgroundColor": "#27ae60", "height": "6px", "cornerRadius": "30px", "contents": []}], "contents": []}
                ]}
            ]
        }
    }

def create_btc_card(current_btc):
    percent = (current_btc / BTC_GOAL) * 100
    bar_width = f"{min(percent, 100)}%"
    return {
        "type": "bubble", "size": "giga",
        "header": {
            "type": "box", "layout": "vertical", "backgroundColor": "#1e1e1e", "paddingAll": "20px",
            "contents": [
                {"type": "text", "text": "BITCOIN ROAD TO 1", "color": "#F7931A", "size": "xs", "weight": "bold"},
                {"type": "text", "text": "比特幣累積計畫", "weight": "bold", "size": "xl", "color": "#ffffff"}
            ]
        },
        "body": {
            "type": "box", "layout": "vertical", "backgroundColor": "#1e1e1e", "paddingAll": "20px",
            "contents": [
                {"type": "box", "layout": "horizontal", "contents": [{"type": "text", "text": "持有 (BTC)", "size": "sm", "color": "#aaaaaa", "flex": 1}, {"type": "text", "text": f"{current_btc:.8f}", "weight": "bold", "color": "#ffffff", "align": "end", "size": "lg"}]},
                {"type": "separator", "margin": "lg", "color": "#333333"},
                {"type": "box", "layout": "vertical", "margin": "lg", "spacing": "sm", "contents": [
                    {"type": "box", "layout": "baseline", "contents": [{"type": "text", "text": "目標進度", "size": "xs", "color": "#aaaaaa", "flex": 1}, {"type": "text", "text": f"{percent:.2f}%", "size": "xs", "color": "#F7931A", "weight": "bold", "align": "end"}]},
                    {"type": "box", "layout": "vertical", "backgroundColor": "#333333", "height": "6px", "cornerRadius": "30px", "contents": [{"type": "box", "layout": "vertical", "width": bar_width, "backgroundColor": "#F7931A", "height": "6px", "cornerRadius": "30px", "contents": []}], "contents": []}
                ]}
            ]
        }
    }

def create_asset_card(history):
    def to_k(data_list): return [round(x / 1000, 1) for x in data_list]
    datasets = [
        {"label": "Crypto", "data": to_k(history["crypto"]), "borderColor": "#fdd835", "backgroundColor": "rgba(253, 216, 53, 0.7)", "fill": True, "pointRadius": 0},
        {"label": "美股", "data": to_k(history["us_stock"]), "borderColor": "#42a5f5", "backgroundColor": "rgba(66, 165, 245, 0.7)", "fill": True, "pointRadius": 0},
        {"label": "台股", "data": to_k(history["tw_stock"]), "borderColor": "#ff5252", "backgroundColor": "rgba(255, 82, 82, 0.7)", "fill": True, "pointRadius": 0},
        {"label": "黃金", "data": to_k(history["gold"]), "borderColor": "#ffa726", "backgroundColor": "rgba(255, 167, 38, 0.7)", "fill": True, "pointRadius": 0},
        {"label": "現金", "data": to_k(history["cash"]), "borderColor": "#66bb6a", "backgroundColor": "rgba(102, 187, 106, 0.7)", "fill": True, "pointRadius": 0}
    ]
    chart_config = {"type": "line", "data": {"labels": history["dates"], "datasets": datasets}, "options": {"title": {"display": False}}}
    url = get_chart_url(chart_config)
    current_total = (history["crypto"][-1] + history["us_stock"][-1] + history["tw_stock"][-1] + history["gold"][-1] + history["cash"][-1]) if history["dates"] else 0
    
    return {
        "type": "bubble", "size": "giga",
        "header": {
            "type": "box", "layout": "vertical", "backgroundColor": "#1e1e1e", "paddingAll": "20px",
            "contents": [
                {"type": "text", "text": "ASSET ALLOCATION", "color": "#42a5f5", "size": "xs", "weight": "bold"},
                {"type": "text", "text": "總資產堆疊趨勢 (k TWD)", "weight": "bold", "size": "xl", "color": "#ffffff"}
            ]
        },
        "hero": {"type": "image", "url": url, "size": "full", "aspectRatio": "20:13", "aspectMode": "cover", "action": {"type": "uri", "uri": url}},
        "body": {
            "type": "box", "layout": "vertical", "backgroundColor": "#1e1e1e",
            "contents": [{"type": "box", "layout": "horizontal", "contents": [{"type": "text", "text": "目前總資產", "size": "sm", "color": "#aaaaaa"}, {"type": "text", "text": f"${current_total:,.0f}", "size": "lg", "color": "#42a5f5", "weight": "bold", "align": "end"}]}]
        }
    }

# ==========================================
# 4. Flask Webhook 監聽
# ==========================================
# --- 新增這段：健康檢查首頁 ---
@app.route("/")
def home():
    return "Finance Bot is Live! 機器人活著！"
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip().upper() # 轉大寫，方便比對
    
    # --- 關鍵字判斷 ---
    if msg == "房貸":
        remaining = get_current_mortgage()
        card = create_mortgage_card(remaining)
        line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="房貸進度", contents=card))
        
    elif msg == "BTC":
        history = get_asset_history(days=1) # 為了拿最新的 BTC，抓 1 天就夠，若要完整一點抓多天也行
        btc = history["btc_holdings"][0] if history and history["btc_holdings"] else 0
        card = create_btc_card(btc)
        line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="BTC進度", contents=card))
        
    elif msg == "總資產":
        history = get_asset_history(days=30)
        if history and history["dates"]:
            card = create_asset_card(history)
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="資產趨勢", contents=card))
        else:
            line_bot_api.reply_message(event.reply_token, TextMessage(text="⚠️ 目前無法讀取資產快照，請稍後再試。"))
            
    # 其他訊息不回應，避免干擾

if __name__ == "__main__":

    app.run()
