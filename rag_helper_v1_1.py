import os
import requests
import json
import concurrent.futures
import time
import re
import urllib3
from datetime import datetime
from linebot.models import TextSendMessage, FlexSendMessage

# --- 關閉 SSL 警告 ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 環境變數 ---
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
# 🔥 新增：為了繞過 SDK 直接發送請求，需要讀取這個 Token
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# --- 領域與資料庫對應 ---
GLOBAL_DBS = ["FLASH_DB_ID", "LITERATURE_DB_ID", "PERMAMENT_DB_ID"]

DOMAIN_MAP = {
    "INVESTMENT": [
        "DB_TW_STOCK", "DB_US_STOCK", "DB_CRYPTO", 
        "DB_GOLD", "PAY_LOSS_DB_ID", "DB_SNAPSHOT"
    ],
    "FINANCE": [
        "TRANSACTIONS_DB_ID", "BUDGET_DB_ID", 
        "INCOME_DB_ID", "DB_ACCOUNT", "DB_MORTGAGE"
    ],
    "HEALTH": [
        "DIET_DB_ID"
    ],
    "KNOWLEDGE": GLOBAL_DBS
}

# 流水帳資料庫中的日期欄位名稱
FINANCE_DATE_PROP = "日期" 

# 使用的模型
MODEL_NAME = "gemini-2.5-flash"

# --- Gemini API 請求 ---
def ask_gemini_json(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GOOGLE_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ]
    
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "safetySettings": safety_settings
    }
    
    try:
        # Timeout 設為 60 秒 (確保比 Gunicorn 短)
        r = requests.post(url, headers=headers, json=data, verify=False, timeout=60)
        if r.status_code == 200:
            try:
                raw = r.json()['candidates'][0]['content']['parts'][0]['text']
                match = re.search(r'\{.*\}', raw, re.DOTALL)
                if match:
                    return json.loads(match.group(0))
                else:
                    match_list = re.search(r'\[.*\]', raw, re.DOTALL)
                    return json.loads(match_list.group(0)) if match_list else None
            except Exception as e:
                print(f"❌ JSON Parse Error: {e} | Raw: {raw}")
                return None
        else:
            print(f"❌ Gemini API Error ({r.status_code}): {r.text}")
    except Exception as e:
        print(f"❌ Request Failed: {e}")
        # 這裡拋出異常，讓 app.py 的 try-except 抓到並發送錯誤訊息
        raise e 
    return None

# --- 意圖與日期分析 ---
def analyze_query_intent(user_query):
    now_str = datetime.now().strftime("%Y-%m-%d")
    prompt = f"""
    今天是 {now_str}。使用者問："{user_query}"
    
    請做兩件事：
    1. 判斷領域 (INVESTMENT, FINANCE, HEALTH, KNOWLEDGE, OTHER)。
    2. 解析時間範圍 start_date 和 end_date (YYYY-MM-DD)。
       - 若無特定時間，留空字串 ""。
       - 如果是比較兩個月(如"本月跟上個月")，start_date 必須包含較早的那個月份的第一天。
    
    回傳 JSON:
    {{
        "domain": "FINANCE",
        "date_filter": {{ "start": "2026-01-01", "end": "2026-02-11" }} 
    }}
    """
    return ask_gemini_json(prompt)

# --- Notion 資料處理 ---
def extract_notion_value(prop):
    p_type = prop.get("type")
    if p_type == "title": return prop["title"][0]["plain_text"] if prop["title"] else ""
    elif p_type == "rich_text": return prop["rich_text"][0]["plain_text"] if prop["rich_text"] else ""
    elif p_type == "number": return prop["number"]
    elif p_type == "select": return prop["select"]["name"] if prop["select"] else ""
    elif p_type == "status": return prop["status"]["name"] if prop["status"] else ""
    elif p_type == "date": return prop["date"]["start"] if prop["date"] else ""
    elif p_type == "checkbox": return prop["checkbox"]
    elif p_type == "formula":
        f = prop["formula"]
        if f["type"] == "number": return f["number"]
        if f["type"] == "string": return f["string"]
    elif p_type == "rollup":
        if prop["rollup"]["type"] == "number": return prop["rollup"]["number"]
    return None

def fetch_page_content(page_id):
    url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=30"
    try:
        r = requests.get(url, headers=NOTION_HEADERS, verify=False)
        data = r.json()
        content_text = ""
        for block in data.get("results", []):
            b_type = block.get("type")
            if b_type in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item", "to_do"]:
                rich_text = block.get(b_type, {}).get("rich_text", [])
                if rich_text:
                    content_text += rich_text[0].get("plain_text", "") + "\n"
        return content_text
    except:
        return ""

def fetch_notion_data(db_env_key, domain, date_filter=None):
    db_id = os.getenv(db_env_key)
    if not db_id: return []
    
    limit = 200 if (date_filter and date_filter.get("start")) else 30
    payload = {"page_size": limit}
    
    if date_filter and date_filter.get("start"):
        date_prop = FINANCE_DATE_PROP if domain == "FINANCE" else None 
        filter_condition = {
            "and": [{"property": date_prop, "date": {"on_or_after": date_filter["start"]}}]
        }
        if date_filter.get("end"):
            filter_condition["and"].append({"property": date_prop, "date": {"on_or_before": date_filter["end"]}})

        if not date_prop:
             payload["filter"] = {
                 "timestamp": "created_time", 
                 "created_time": {"on_or_after": date_filter["start"]}
             }
        else:
            payload["filter"] = filter_condition

    if domain in ["FINANCE", "HEALTH", "INVESTMENT"]:
        payload["sorts"] = [{"timestamp": "created_time", "direction": "descending"}]

    try:
        r = requests.post(f"https://api.notion.com/v1/databases/{db_id}/query", headers=NOTION_HEADERS, json=payload, verify=False)
        data = r.json()
        results = []
        fetch_content_flag = (domain == "KNOWLEDGE")

        for page in data.get("results", []):
            simple = {}
            if fetch_content_flag: simple["id"] = page["id"]

            for k, v in page["properties"].items():
                val = extract_notion_value(v)
                if val is not None and val != "": simple[k] = val
            
            if fetch_content_flag:
                content = fetch_page_content(page["id"])
                if content:
                    simple["content_body"] = content[:500]
                del simple["id"]
            
            results.append(simple)
        return results
    except Exception as e:
        print(f"Fetch Error ({db_env_key}): {e}")
        return []

# --- RAG 回應生成 ---
def generate_rag_response(user_query, domain, raw_data):
    context = json.dumps(raw_data, ensure_ascii=False, indent=2)
    if len(context) > 60000: context = context[:60000] + "...(略)"

    prompt = f"""
    你是 AI 財務與生活助理。使用者問："{user_query}"
    資料庫 ({domain}) 紀錄：
    {context}
    
    請回傳 JSON 物件：
    1. "card_data": UI 摘要
       - title: 標題 (精簡有力)
       - main_stat: 核心數據 (如 "NT$52,597")
       - details: list [{{ "label": "項目", "value": "數值" }}] (最多5項)
    
    2. "detailed_analysis": 詳細回答 (3-4個重點)
       - list [{{ "title": "重點標題", "content": "重點內容(建議50字內)" }}]
       - 內容請具體分析數據，不要只列數字。
    """
    return ask_gemini_json(prompt)

# --- Flex Message 建構 ---
def create_summary_flex(domain, data):
    colors = {
        "INVESTMENT": "#ef5350", "FINANCE": "#42a5f5", 
        "HEALTH": "#66bb6a", "KNOWLEDGE": "#ffa726"
    }
    theme_color = colors.get(domain, "#999999")
    
    detail_boxes = []
    details = data.get('details', [])
    if not isinstance(details, list): details = []

    for item in details[:5]: 
        if isinstance(item, str): label, value = item, ""
        else: label, value = str(item.get('label', '項目')), str(item.get('value', ''))

        detail_boxes.append({
            "type": "box", "layout": "horizontal",
            "contents": [
                {"type": "text", "text": label, "size": "sm", "color": "#aaaaaa", "flex": 2, "wrap": True},
                {"type": "text", "text": value, "size": "sm", "color": "#ffffff", "align": "end", "flex": 4, "wrap": True}
            ]
        })

    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box", "layout": "vertical", "backgroundColor": theme_color,
            "contents": [
                {"type": "text", "text": f"{domain} INTELLIGENCE", "color": "#ffffff", "weight": "bold", "size": "xxs"},
                {"type": "text", "text": str(data.get('title', '查詢結果')), "weight": "bold", "size": "xl", "color": "#ffffff", "wrap": True}
            ]
        },
        "body": {
            "type": "box", "layout": "vertical", "backgroundColor": "#1e1e1e",
            "contents": [
                *([{"type": "text", "text": str(data['main_stat']), "size": "4xl", "weight": "bold", "color": theme_color, "align": "center", "margin": "md", "adjustMode": "shrink-to-fit"}] if data.get('main_stat') else []),
                {"type": "separator", "margin": "lg", "color": "#333333"},
                {"type": "box", "layout": "vertical", "margin": "lg", "spacing": "sm", "contents": detail_boxes}
            ]
        }
    }

def create_analysis_flex(analysis_data):
    if isinstance(analysis_data, str): analysis_data = [{"title": "分析結果", "content": analysis_data}]
    elif not isinstance(analysis_data, list): analysis_data = [{"title": "提示", "content": "無詳細分析資料"}]

    contents = []
    for section in analysis_data:
        if isinstance(section, dict):
            title = str(section.get('title', '重點'))
            content = str(section.get('content', ''))
        else:
            title, content = "重點", str(section)

        contents.append({
            "type": "box", "layout": "vertical", "margin": "lg",
            "contents": [
                {"type": "text", "text": f"📌 {title}", "weight": "bold", "color": "#FFD700", "size": "sm", "wrap": True},
                {"type": "text", "text": content, "color": "#cccccc", "size": "sm", "wrap": True, "margin": "xs"}
            ]
        })

    return {
        "type": "bubble",
        "size": "mega",
        "body": {
            "type": "box", "layout": "vertical", "backgroundColor": "#2b2b2b",
            "contents": [
                {"type": "text", "text": "AI 深度解析", "weight": "bold", "size": "md", "color": "#ffffff", "align": "center"},
                {"type": "separator", "margin": "md", "color": "#555555"},
                *contents
            ]
        }
    }

# 🔥 新增：使用 requests 直接發送 LINE 訊息 (繞過 SDK 的 SSL 驗證)
def reply_line_message(reply_token, messages):
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    
    # 將 FlexSendMessage 物件轉為 dict
    msg_list = []
    for msg in messages:
        if isinstance(msg, FlexSendMessage):
            msg_list.append({
                "type": "flex",
                "altText": msg.alt_text,
                "contents": msg.contents
            })
        elif isinstance(msg, TextSendMessage):
            msg_list.append({
                "type": "text",
                "text": msg.text
            })
            
    payload = {
        "replyToken": reply_token,
        "messages": msg_list
    }
    
    try:
        # 🔥 重點：verify=False
        requests.post(url, headers=headers, json=payload, verify=False, timeout=10)
    except Exception as e:
        print(f"❌ LINE Reply Failed: {e}")

# --- 主入口函式 ---
def handle_rag_query(user_query, reply_token, line_bot_api):
    # 1. 意圖分析
    intent = analyze_query_intent(user_query)
    domain = intent.get("domain") if intent else "OTHER"
    date_filter = intent.get("date_filter")
    
    if domain == "OTHER":
        # 改用 requests 發送
        reply_line_message(reply_token, [TextSendMessage(text="🤖 請輸入投資、記帳、健康或筆記相關問題。")])
        return

    # 2. 決定查詢目標
    target_dbs = list(set(DOMAIN_MAP.get(domain, []) + GLOBAL_DBS)) if domain != "KNOWLEDGE" else GLOBAL_DBS
    raw_data = {}
    
    # 3. 並行撈取資料
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_db = {executor.submit(fetch_notion_data, db, domain, date_filter): db for db in target_dbs}
        for future in concurrent.futures.as_completed(future_to_db):
            db_name = future_to_db[future]
            res = future.result()
            if res: raw_data[db_name] = res

    if not raw_data:
        reply_line_message(reply_token, [TextSendMessage(text=f"⚠️ 在 {domain} 領域查無資料 (日期範圍可能無數據)。")])
        return

    # 4. 生成 AI 回應
    ai_result = generate_rag_response(user_query, domain, raw_data)
    
    if ai_result:
        # 5. 製作兩張 Flex Message
        card_data = ai_result.get("card_data", {})
        analysis_data = ai_result.get("detailed_analysis", [])
        
        flex1_content = create_summary_flex(domain, card_data)
        flex1_msg = FlexSendMessage(alt_text=f"{domain} 查詢摘要", contents=flex1_content)
        
        flex2_content = create_analysis_flex(analysis_data)
        flex2_msg = FlexSendMessage(alt_text=f"{domain} 詳細分析", contents=flex2_content)
        
        # 🔥 改用 requests 發送
        reply_line_message(reply_token, [flex1_msg, flex2_msg])
    else:
        reply_line_message(reply_token, [TextSendMessage(text="⚠️ AI 生成回應失敗。")])
