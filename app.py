import os
import json
import requests
import urllib3
import numpy as np
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
# 🔥 記得加 ImageMessage
from linebot.models import MessageEvent, TextMessage, ImageMessage, FlexSendMessage, TextSendMessage

# 🔥 匯入飲食小幫手模組
from diet_helper import handle_diet_image

# 關閉 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ==========================================
# 0. 環境變數與設定
# ==========================================
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DB_MORTGAGE = os.getenv("DB_MORTGAGE")
DB_SNAPSHOT = os.getenv("DB_SNAPSHOT")
DB_BUDGET = os.getenv("BUDGET_DB_ID")

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
# 1. 資料讀取函式 (Finance) - 維持原樣
# ==========================================
def extract_number(prop):
    if not prop: return 0
    p_type = prop.get("type")
    if p_type == "number": return prop.get("number", 0) or 0
    elif p_type == "formula": return prop.get("formula", {}).get("number", 0) or 0
    elif p_type == "rollup":
        rollup = prop.get("rollup", {})
        r_type = rollup.get("type")
        if r_type == "number": return rollup.get("number", 0) or 0
        elif r_type == "array":
            total = 0
            for item in rollup.get("array", []):
                if item.get("type") == "number": total += item.get("number", 0) or 0
                elif item.get("type") == "formula": total += item.get("formula", {}).get("number", 0) or 0
            return total
    return 0

def get_current_mortgage():
    try:
        res = requests.post(f"https://api.notion.com/v1/databases/{DB_MORTGAGE}/query", headers=NOTION_HEADERS, json={"page_size": 1}, verify=False)
        data = res.json()
        if data["results"]: return extract_number(data["results"][0]["properties"].get("剩餘本金", {}))
    except: pass
    return LOAN_TOTAL_PRINCIPAL

def get_asset_history(days=120):
    query = {"page_size": days, "sorts": [{"property": "日期", "direction": "descending"}]}
    try:
        res = requests.post(f"https://api.notion.com/v1/databases/{DB_SNAPSHOT}/query", headers=NOTION_HEADERS, json=query, verify=False)
        data = res.json()
        results = data.get("results", [])
        history = {"dates": [], "crypto": [], "us_stock": [], "tw_stock": [], "gold": [], "cash": [], "btc_holdings": [], "total_assets": []}
        for p in reversed(results):
            props = p["properties"]
            d = props.get("日期", {}).get("date", {}).get("start", "")
            if not d: continue
            history["dates"].append(datetime.strptime(d, "%Y-%m-%d").strftime("%m/%d"))
            def gn(k): return extract_number(props.get(k, {}))
            history["crypto"].append(gn("Crypto"))
            history["us_stock"].append(gn("美股複委託"))
            history["tw_stock"].append(gn("台股證券戶"))
            history["gold"].append(gn("Gold"))
            history["cash"].append(gn("活存"))
            history["btc_holdings"].append(gn("BTC持有量"))
            history["total_assets"].append(gn("總資產"))
        return history
    except: return None

def get_budget_monthly_6m():
    query = {"page_size": 100, "sorts": [{"property": "預算類別", "direction": "descending"}]}
    try:
        res = requests.post(f"https://api.notion.com/v1/databases/{DB_BUDGET}/query", headers=NOTION_HEADERS, json=query, verify=False)
        data = res.json()
        monthly_data = {}
        all_cats = set()
        now = datetime.now()
        current_ym_str = now.strftime("%Y%m")
        if now.month == 1: last_month_date = datetime(now.year - 1, 12, 1)
        else: last_month_date = datetime(now.year, now.month - 1, 1)
        target_last_m_fmt = last_month_date.strftime("%y-%m")

        for p in data.get("results", []):
            props = p["properties"]
            title_list = props.get("預算類別", {}).get("title", [])
            if not title_list: continue
            full_title = title_list[0]["plain_text"]
            spent = abs(extract_number(props.get("實際花費", {})))
            if len(full_title) > 6 and full_title[:6].isdigit():
                ym_raw = full_title[:6]
                if ym_raw > current_ym_str: continue 
                cat = full_title[6:]
                m_fmt = f"{ym_raw[2:4]}-{ym_raw[4:]}"
                if m_fmt not in monthly_data: monthly_data[m_fmt] = {}
                monthly_data[m_fmt][cat] = monthly_data[m_fmt].get(cat, 0) + spent
                all_cats.add(cat)

        sorted_months = sorted(list(monthly_data.keys()))[-6:] 
        datasets = []
        colors = ["#ff6384", "#36a2eb", "#cc65fe", "#ffce56", "#4bc0c0", "#9966ff", "#ff9f40", "#c9cbcf"]
        
        top_cat_name, top_cat_amount = "N/A", 0
        if target_last_m_fmt in monthly_data:
            for cat, val in monthly_data[target_last_m_fmt].items():
                if val > top_cat_amount: top_cat_amount = val; top_cat_name = cat

        for i, cat in enumerate(all_cats):
            data_points = []
            for m in sorted_months: data_points.append(int(monthly_data[m].get(cat, 0) / 1000))
            if sum(data_points) > 0:
                datasets.append({"label": cat, "data": data_points, "borderColor": colors[i % len(colors)], "fill": False, "pointRadius": 3})
        return sorted_months, datasets, top_cat_name, top_cat_amount
    except: return [], [], "N/A", 0

# ==========================================
# 2. 圖表生成 (POST) - 維持原樣
# ==========================================
def get_chart_url_post(config):
    config["options"]["layout"] = {"padding": {"left": 20, "right": 40, "top": 20, "bottom": 50}}
    config["options"]["legend"] = {"labels": {"fontColor": "#fff", "fontSize": 10}}
    if "scales" in config["options"]:
        for axis in ["xAxes", "yAxes"]:
            for scale in config["options"]["scales"].get(axis, []):
                scale["gridLines"] = {"color": "#333"}; scale["ticks"] = {"fontColor": "#bbb", "fontSize": 10}
    try:
        res = requests.post("https://quickchart.io/chart/create", json={"chart": config, "width": 500, "height": 300, "backgroundColor": "#121212"}, verify=False)
        if res.status_code == 200: return res.json().get('url')
    except: pass
    return "https://via.placeholder.com/500x300?text=Error"

def gen_monte_carlo(history_totals):
    if not history_totals or len(history_totals) < 5: return "", 0
    arr = np.array(history_totals); arr[arr == 0] = 1 
    daily_returns = np.diff(arr) / arr[:-1]
    cagr = (1 + np.mean(daily_returns)) ** 365 - 1
    vol = np.std(daily_returns) * np.sqrt(365)
    cagr = max(min(cagr, 0.30), 0.02); vol = max(min(vol, 0.40), 0.05)
    current_assets = arr[-1]
    
    years = 10; sims = 500
    labels = [str(datetime.now().year + i) for i in range(1, years + 1)]
    results = []
    for _ in range(sims):
        p = [current_assets]
        for _ in range(years): p.append(p[-1] * (1 + np.random.normal(cagr, vol)))
        results.append(p[1:])
    res = np.array(results)
    
    def to_m(arr): return [round(x / 1000000, 1) for x in arr]
    d90 = to_m(np.percentile(res, 90, axis=0))
    d50 = to_m(np.percentile(res, 50, axis=0))
    d10 = to_m(np.percentile(res, 10, axis=0))
    median_val = int(np.percentile(res, 50, axis=0)[-1])

    config = {
        "type": "line",
        "data": {"labels": labels, "datasets": [
            {"label": "Best", "data": d90, "borderColor": "#00ff00", "fill": False, "pointRadius": 0},
            {"label": "Median", "data": d50, "borderColor": "#0099ff", "fill": False, "pointRadius": 0},
            {"label": "Worst", "data": d10, "borderColor": "#ff3333", "fill": False, "pointRadius": 0}
        ]},
        "options": {"title": {"display": True, "text": f"CAGR: {cagr:.1%} (Unit: M)", "fontColor": "#ddd"}}
    }
    return get_chart_url_post(config), median_val

def gen_total_asset_url(hist):
    if not hist["dates"]: return ""
    sample = max(1, len(hist["dates"]) // 10); dates = hist["dates"][::sample]
    def get_d(k): return [round(x/1000, 0) for x in hist[k][::sample]]
    datasets = [
        {"label": "Crypto", "data": get_d("crypto"), "borderColor": "#fdd835", "backgroundColor": "rgba(253,216,53,0.7)", "fill": True, "pointRadius": 0},
        {"label": "US", "data": get_d("us_stock"), "borderColor": "#42a5f5", "backgroundColor": "rgba(66,165,245,0.7)", "fill": True, "pointRadius": 0},
        {"label": "TW", "data": get_d("tw_stock"), "borderColor": "#ff5252", "backgroundColor": "rgba(255,82,82,0.7)", "fill": True, "pointRadius": 0},
        {"label": "Gold", "data": get_d("gold"), "borderColor": "#ffa726", "backgroundColor": "rgba(255,167,38,0.7)", "fill": True, "pointRadius": 0},
        {"label": "Cash", "data": get_d("cash"), "borderColor": "#66bb6a", "backgroundColor": "rgba(102,187,106,0.7)", "fill": True, "pointRadius": 0}
    ]
    config = {"type": "line", "data": {"labels": dates, "datasets": datasets}, "options": {"title": {"display": False}, "scales": {"yAxes": [{"stacked": True}], "xAxes": [{"offset": True}]}, "legend": {"display": False}}}
    return get_chart_url_post(config)

def gen_budget_chart_url(labels, datasets):
    config = {"type": "line", "data": {"labels": labels, "datasets": datasets}, "options": {"title": {"display": True, "text": "Spending Trend (Unit: k)", "fontColor": "#ddd"}, "scales": {"yAxes": [{"stacked": False}]}, "legend": {"position": "bottom", "labels": {"boxWidth": 10}}}}
    return get_chart_url_post(config)

# ==========================================
# 3. 卡片生成 - 維持原樣
# ==========================================
def card_mortgage(rem):
    paid = LOAN_TOTAL_PRINCIPAL - rem; pct = (paid / LOAN_TOTAL_PRINCIPAL) * 100
    return {"type": "bubble", "size": "mega", "header": {"type": "box", "layout": "vertical", "backgroundColor": "#1e1e1e", "contents": [{"type": "text", "text": "MORTGAGE", "color": "#27ae60", "size": "xs", "weight": "bold"}, {"type": "text", "text": "房貸進度", "weight": "bold", "size": "xl", "color": "#ffffff"}]}, "body": {"type": "box", "layout": "vertical", "backgroundColor": "#1e1e1e", "contents": [{"type": "box", "layout": "horizontal", "contents": [{"type": "text", "text": "剩餘本金", "size": "sm", "color": "#aaaaaa"}, {"type": "text", "text": f"${rem:,.0f}", "weight": "bold", "color": "#ef5350", "align": "end"}]}, {"type": "separator", "margin": "md", "color": "#333333"}, {"type": "box", "layout": "vertical", "margin": "md", "contents": [{"type": "text", "text": f"{pct:.2f}%", "size": "xs", "color": "#27ae60", "align": "end"}, {"type": "box", "layout": "vertical", "backgroundColor": "#333333", "height": "6px", "cornerRadius": "30px", "contents": [{"type": "box", "layout": "vertical", "width": f"{pct}%", "backgroundColor": "#27ae60", "height": "6px", "cornerRadius": "30px", "contents": []}]}]}]}}

def card_btc(curr):
    pct = (curr / BTC_GOAL) * 100
    return {"type": "bubble", "size": "mega", "header": {"type": "box", "layout": "vertical", "backgroundColor": "#1e1e1e", "contents": [{"type": "text", "text": "BITCOIN", "color": "#F7931A", "size": "xs", "weight": "bold"}, {"type": "text", "text": "BTC 計畫", "weight": "bold", "size": "xl", "color": "#ffffff"}]}, "body": {"type": "box", "layout": "vertical", "backgroundColor": "#1e1e1e", "contents": [{"type": "box", "layout": "horizontal", "contents": [{"type": "text", "text": "持有", "size": "sm", "color": "#aaaaaa"}, {"type": "text", "text": f"{curr:.4f}", "weight": "bold", "color": "#ffffff", "align": "end"}]}, {"type": "separator", "margin": "md", "color": "#333333"}, {"type": "box", "layout": "vertical", "margin": "md", "contents": [{"type": "text", "text": f"{pct:.2f}%", "size": "xs", "color": "#F7931A", "align": "end"}, {"type": "box", "layout": "vertical", "backgroundColor": "#333333", "height": "6px", "cornerRadius": "30px", "contents": [{"type": "box", "layout": "vertical", "width": f"{pct}%", "backgroundColor": "#F7931A", "height": "6px", "cornerRadius": "30px", "contents": []}]}]}]}}

def card_assets_v1(hist, url_total):
    curr = hist["total_assets"][-1]; last_week = hist["total_assets"][min(7, len(hist["total_assets"])-1)]; diff = curr - last_week; color = "#27ae60" if diff >= 0 else "#eb3b5a"; arrow = "▲" if diff >= 0 else "▼"
    return {"type": "bubble", "size": "giga", "header": {"type": "box", "layout": "vertical", "backgroundColor": "#1e1e1e", "contents": [{"type": "text", "text": "TOTAL NET WORTH", "color": "#27ae60", "size": "xs", "weight": "bold"}, {"type": "text", "text": "總資產趨勢", "weight": "bold", "size": "xl", "color": "#ffffff"}]}, "hero": {"type": "image", "url": url_total, "size": "full", "aspectRatio": "20:13", "aspectMode": "cover"}, "body": {"type": "box", "layout": "vertical", "backgroundColor": "#1e1e1e", "contents": [{"type": "text", "text": f"${curr:,.0f}", "size": "xxl", "weight": "bold", "color": "#ffffff", "align": "center"}, {"type": "text", "text": f"{arrow} ${abs(diff):,.0f} (7d)", "size": "sm", "color": color, "align": "center", "margin": "sm"}]}}

def card_chart_giga(title, url, val_text, sub_text=""):
    return {"type": "bubble", "size": "giga", "header": {"type": "box", "layout": "vertical", "backgroundColor": "#1e1e1e", "contents": [{"type": "text", "text": sub_text, "color": "#42a5f5", "size": "xs", "weight": "bold"}, {"type": "text", "text": title, "weight": "bold", "size": "xl", "color": "#ffffff"}]}, "hero": {"type": "image", "url": url, "size": "full", "aspectRatio": "20:13", "aspectMode": "cover"}, "body": {"type": "box", "layout": "vertical", "backgroundColor": "#1e1e1e", "contents": [{"type": "text", "text": val_text, "size": "xxl", "weight": "bold", "color": "#42a5f5", "align": "center"}]}}

def card_spending_giga(title, url, cat_name, cat_amount):
    return {"type": "bubble", "size": "giga", "header": {"type": "box", "layout": "vertical", "backgroundColor": "#1e1e1e", "contents": [{"type": "text", "text": "SPENDING TREND", "color": "#42a5f5", "size": "xs", "weight": "bold"}, {"type": "text", "text": title, "weight": "bold", "size": "xl", "color": "#ffffff"}]}, "hero": {"type": "image", "url": url, "size": "full", "aspectRatio": "20:13", "aspectMode": "cover"}, "body": {"type": "box", "layout": "horizontal", "backgroundColor": "#1e1e1e", "contents": [{"type": "text", "text": f"上月最大: {cat_name}", "size": "sm", "color": "#aaaaaa", "flex": 1, "gravity": "center"}, {"type": "text", "text": f"${cat_amount:,.0f}", "size": "xl", "weight": "bold", "color": "#ef5350", "align": "end", "flex": 1}]}}

# ==========================================
# 4. Webhook 監聽
# ==========================================
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@app.route("/", methods=['GET'])
def home():
    return "Bot is awake!", 200

# --- 文字訊息處理 (Finance) ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip().upper()
    
    if msg == "房貸":
        rem = get_current_mortgage()
        card = card_mortgage(rem)
        line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="房貸", contents=card))
    
    elif msg == "BTC":
        hist = get_asset_history(1) 
        if hist:
            btc = hist["btc_holdings"][0] if hist["btc_holdings"] else 0
            card = card_btc(btc)
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="BTC", contents=card))
            
    elif msg == "總資產":
        hist = get_asset_history(120)
        if hist and hist["total_assets"]:
            url_total = gen_total_asset_url(hist)
            card = card_assets_v1(hist, url_total)
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="總資產", contents=card))
            
    elif msg == "預測":
        hist = get_asset_history(120)
        if hist and hist["total_assets"]:
            url_mc, med = gen_monte_carlo(hist["total_assets"])
            card = card_chart_giga("未來資產 (10Y)", url_mc, f"${med:,.0f}", "MONTE CARLO")
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="預測", contents=card))
            
    elif msg == "消費比較":
        ml, md, top_cat, top_val = get_budget_monthly_6m()
        if ml:
            url_budget = gen_budget_chart_url(ml, md)
            card = card_spending_giga("每月消費變化 (6M)", url_budget, top_cat, top_val)
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="消費比較", contents=card))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 無法取得消費數據 (請檢查 BUDGET_DB_ID)"))

# --- 圖片訊息處理 (Diet) ---
@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    user_id = event.source.user_id
    msg_id = event.message.id
    
    # 從 LINE 伺服器下載圖片內容 (Bytes)
    message_content = line_bot_api.get_message_content(msg_id)
    image_bytes = message_content.content
    
    # 交給飲食小幫手處理
    handle_diet_image(user_id, image_bytes, event.reply_token, line_bot_api)

if __name__ == "__main__":
    app.run()
