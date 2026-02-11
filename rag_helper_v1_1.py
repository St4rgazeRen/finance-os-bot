import os
import requests
import json
import concurrent.futures
import time
import re
import urllib3
from datetime import datetime
from linebot.models import TextSendMessage, FlexSendMessage

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 環境變數
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

GLOBAL_DBS = ["FLASH_DB_ID", "LITERATURE_DB_ID", "PERMAMENT_DB_ID"]
DOMAIN_MAP = {
    "INVESTMENT": ["DB_TW_STOCK", "DB_US_STOCK", "DB_CRYPTO", "DB_GOLD", "PAY_LOSS_DB_ID", "DB_SNAPSHOT"],
    "FINANCE": ["TRANSACTIONS_DB_ID", "BUDGET_DB_ID", "INCOME_DB_ID", "DB_ACCOUNT", "DB_MORTGAGE"],
    "HEALTH": ["DIET_DB_ID"],
    "KNOWLEDGE": GLOBAL_DBS
}
FINANCE_DATE_PROP = "日期" 
MODEL_NAME = "gemini-2.5-flash"

def ask_gemini_json(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GOOGLE_API_KEY}"
    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        # 維持 80 秒，但資料變輕了，應該會過
        r = requests.post(url, headers=headers, json=data, verify=False, timeout=80)
        if r.status_code == 200:
            raw = r.json()['candidates'][0]['content']['parts'][0]['text']
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            return json.loads(match.group(0)) if match else None
        raise Exception(f"Gemini API Error: {r.status_code}")
    except Exception as e:
        print(f"❌ Gemini Request Failed: {e}")
        raise e

def analyze_query_intent(user_query):
    now_str = datetime.now().strftime("%Y-%m-%d")
    prompt = f"Today is {now_str}. User asked: '{user_query}'. Determine domain (INVESTMENT, FINANCE, HEALTH, KNOWLEDGE, OTHER) and date range (start/end YYYY-MM-DD). Return JSON only."
    return ask_gemini_json(prompt)

def extract_notion_value(prop):
    """[瘦身關鍵] 只提取數值，不保留類型標籤"""
    p_type = prop.get("type")
    if p_type == "title": return prop["title"][0]["plain_text"] if prop["title"] else ""
    if p_type == "rich_text": return prop["rich_text"][0]["plain_text"] if prop["rich_text"] else ""
    if p_type == "number": return prop["number"]
    if p_type == "select": return prop["select"]["name"] if prop["select"] else ""
    if p_type == "status": return prop["status"]["name"] if prop["status"] else ""
    if p_type == "date": return prop["date"]["start"] if prop["date"] else ""
    if p_type == "formula": return prop["formula"].get("number") or prop["formula"].get("string")
    if p_type == "rollup": return prop["rollup"].get("number")
    return None

def fetch_notion_data(db_env_key, domain, date_filter=None):
    db_id = os.getenv(db_env_key)
    if not db_id: return []
    
    # 🔥 調整：上限降到 60 筆，降低運算壓力
    limit = 60 if (date_filter and date_filter.get("start")) else 30
    payload = {"page_size": limit}
    
    if date_filter and date_filter.get("start"):
        date_prop = FINANCE_DATE_PROP if domain == "FINANCE" else None 
        if date_prop:
            payload["filter"] = {"and": [{"property": date_prop, "date": {"on_or_after": date_filter["start"]}}]}
            if date_filter.get("end"): payload["filter"]["and"].append({"property": date_prop, "date": {"on_or_before": date_filter["end"]}})
        else:
            payload["filter"] = {"timestamp": "created_time", "created_time": {"on_or_after": date_filter["start"]}}

    if domain in ["FINANCE", "HEALTH", "INVESTMENT"]:
        payload["sorts"] = [{"timestamp": "created_time", "direction": "descending"}]

    try:
        r = requests.post(f"https://api.notion.com/v1/databases/{db_id}/query", headers=NOTION_HEADERS, json=payload, verify=False)
        data = r.json()
        results = []
        for page in data.get("results", []):
            simple = {}
            for k, v in page["properties"].items():
                val = extract_notion_value(v)
                if val: simple[k] = val # 🔥 只存有值的，沒值的直接砍掉
            results.append(simple)
        return results
    except: return []

def generate_rag_response(user_query, domain, raw_data):
    # 🔥 極致瘦身：移除縮排，縮小 JSON 體積
    context = json.dumps(raw_data, ensure_ascii=False)
    if len(context) > 50000: context = context[:50000]

    prompt = f"Query: {user_query}\nData: {context}\nAnalyze as Finance/Life assistant. Return JSON with 'card_data' (title, main_stat, details list) and 'detailed_analysis' (list of {{title, content}})."
    return ask_gemini_json(prompt)

# --- UI & LINE 發送 (保持原樣，修復了 BubbleContainer 問題) ---
def create_summary_flex(domain, data):
    colors = {"INVESTMENT": "#ef5350", "FINANCE": "#42a5f5", "HEALTH": "#66bb6a", "KNOWLEDGE": "#ffa726"}
    theme_color = colors.get(domain, "#999999")
    detail_boxes = []
    details = data.get('details', [])
    for item in details[:5]:
        label = item if isinstance(item, str) else item.get('label', 'Item')
        value = "" if isinstance(item, str) else item.get('value', '')
        detail_boxes.append({"type": "box", "layout": "horizontal", "contents": [
            {"type": "text", "text": str(label), "size": "sm", "color": "#aaaaaa", "flex": 2, "wrap": True},
            {"type": "text", "text": str(value), "size": "sm", "color": "#ffffff", "align": "end", "flex": 4, "wrap": True}
        ]})
    return {"type": "bubble", "size": "mega", "header": {"type": "box", "layout": "vertical", "backgroundColor": theme_color, "contents": [
        {"type": "text", "text": f"{domain} INTELLIGENCE", "color": "#ffffff", "weight": "bold", "size": "xxs"},
        {"type": "text", "text": str(data.get('title', 'Result')), "weight": "bold", "size": "xl", "color": "#ffffff", "wrap": True}
    ]}, "body": {"type": "box", "layout": "vertical", "backgroundColor": "#1e1e1e", "contents": [
        *([{"type": "text", "text": str(data['main_stat']), "size": "4xl", "weight": "bold", "color": theme_color, "align": "center", "margin": "md", "adjustMode": "shrink-to-fit"}] if data.get('main_stat') else []),
        {"type": "separator", "margin": "lg", "color": "#333333"},
        {"type": "box", "layout": "vertical", "margin": "lg", "spacing": "sm", "contents": detail_boxes}
    ]}}

def create_analysis_flex(analysis_data):
    if isinstance(analysis_data, str): analysis_data = [{"title": "Analysis", "content": analysis_data}]
    contents = [{"type": "box", "layout": "vertical", "margin": "lg", "contents": [
        {"type": "text", "text": f"📌 {str(sec.get('title', 'Point'))}", "weight": "bold", "color": "#FFD700", "size": "sm", "wrap": True},
        {"type": "text", "text": str(sec.get('content', '')), "color": "#cccccc", "size": "sm", "wrap": True, "margin": "xs"}
    ]} for sec in analysis_data[:4]]
    return {"type": "bubble", "size": "mega", "body": {"type": "box", "layout": "vertical", "backgroundColor": "#2b2b2b", "contents": [
        {"type": "text", "text": "AI 深度解析", "weight": "bold", "size": "md", "color": "#ffffff", "align": "center"},
        {"type": "separator", "margin": "md", "color": "#555555"},
        *contents
    ]}}

def reply_line_message(reply_token, messages):
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    msg_list = []
    for msg in messages:
        if isinstance(msg, FlexSendMessage):
            c = msg.contents
            if hasattr(c, 'as_json_dict'): c = c.as_json_dict()
            msg_list.append({"type": "flex", "altText": msg.alt_text, "contents": c})
        elif isinstance(msg, TextSendMessage):
            msg_list.append({"type": "text", "text": msg.text})
    try: requests.post(url, headers=headers, json={"replyToken": reply_token, "messages": msg_list}, verify=False, timeout=10)
    except: pass

def handle_rag_query(user_query, reply_token, line_bot_api):
    intent = analyze_query_intent(user_query)
    domain = intent.get("domain", "OTHER")
    date_filter = intent.get("date_filter")
    if domain == "OTHER":
        reply_line_message(reply_token, [TextSendMessage(text="🤖 請詢問財務、健康或知識庫相關問題。")])
        return
    target_dbs = list(set(DOMAIN_MAP.get(domain, []) + GLOBAL_DBS))
    raw_data = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_db = {executor.submit(fetch_notion_data, db, domain, date_filter): db for db in target_dbs}
        for future in concurrent.futures.as_completed(future_to_db):
            db_name = future_to_db[future]
            res = future.result()
            if res: raw_data[db_name] = res
    if not raw_data:
        reply_line_message(reply_token, [TextSendMessage(text="⚠️ 查無相關資料。")])
        return
    ai_result = generate_rag_response(user_query, domain, raw_data)
    if ai_result:
        f1 = FlexSendMessage(alt_text="Summary", contents=create_summary_flex(domain, ai_result.get("card_data", {})))
        f2 = FlexSendMessage(alt_text="Analysis", contents=create_analysis_flex(ai_result.get("detailed_analysis", [])))
        reply_line_message(reply_token, [f1, f2])
