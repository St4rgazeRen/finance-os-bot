import os
import requests
import json
import concurrent.futures
import time
from linebot.models import TextSendMessage, FlexSendMessage

# --- 環境變數 ---
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

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
    ]
}

MODEL_NAME = "gemini-2.5-flash"

def ask_gemini_json(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GOOGLE_API_KEY}"
    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        r = requests.post(url, headers=headers, json=data, verify=False)
        if r.status_code == 200:
            raw = r.json()['candidates'][0]['content']['parts'][0]['text']
            clean = raw.replace("```json", "").replace("```", "").strip()
            return json.loads(clean)
    except: pass
    return None

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
        if f["type"] in ["number", "string"]: return f[f["type"]]
        elif f["type"] == "date": return f["date"]["start"]
    elif p_type == "rollup":
        if prop["rollup"]["type"] == "number": return prop["rollup"]["number"]
    return None

def fetch_notion_data(db_env_key, limit=15):
    db_id = os.getenv(db_env_key)
    if not db_id: return []
    
    payload = {"page_size": limit}
    if db_env_key in ["TRANSACTIONS_DB_ID", "DIET_DB_ID", "DB_SNAPSHOT", "FLASH_DB_ID"]:
        payload["sorts"] = [{"timestamp": "created_time", "direction": "descending"}]

    try:
        r = requests.post(f"https://api.notion.com/v1/databases/{db_id}/query", headers=NOTION_HEADERS, json=payload, verify=False)
        data = r.json()
        results = []
        for page in data.get("results", []):
            simple = {}
            for k, v in page["properties"].items():
                val = extract_notion_value(v)
                if val is not None and val != "": simple[k] = val
            results.append(simple)
        return results
    except: return []

def determine_intent(user_query):
    prompt = f"""
    使用者問："{user_query}"
    判斷領域：
    - INVESTMENT (投資/股票/幣/資產)
    - FINANCE (記帳/花費/預算/房貸)
    - HEALTH (飲食/熱量/吃什麼)
    - KNOWLEDGE (筆記/想法/靈感)
    - OTHER (閒聊/無法判斷)
    回傳 JSON: {{ "domain": "INVESTMENT" }}
    """
    return ask_gemini_json(prompt)

def generate_rag_answer(user_query, domain, raw_data):
    # 限制 Context 長度
    context = json.dumps(raw_data, ensure_ascii=False, indent=2)
    if len(context) > 40000: context = context[:40000] + "...(略)"

    # 🔥 修改點：所有的 JSON 括號都要變成 {{ }}
    prompt = f"""
    你是 AI 財務與生活助理。使用者問："{user_query}"
    這是從 Notion ({domain}) 撈出的資料：
    {context}
    
    請依領域回傳 JSON 格式以便生成 UI：
    1. title: 標題 (如 "台股庫存概況" 或 "本週飲食摘要")
    2. main_stat: 核心數據 (如 "總市值 $1,200,000" 或 "平均熱量 2100kcal")，若無則留空。
    3. details: 一個 list，包含重點項目的 {{"label": "項目", "value": "數值/內容"}}。 
    4. summary: 一段簡短的總結分析 (100字內)。
    
    格式範例:
    {{
        "title": "資產查詢結果",
        "main_stat": "台積電: 5張",
        "details": [
            {{"label": "台積電", "value": "獲利 +20%"}},
            {{"label": "00878", "value": "獲利 +5%"}}
        ],
        "summary": "整體投資狀況良好，台積電貢獻最大獲利。"
    }}
    """
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GOOGLE_API_KEY}"
    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        r = requests.post(url, headers=headers, json=data, verify=False)
        if r.status_code == 200:
            raw = r.json()['candidates'][0]['content']['parts'][0]['text']
            clean = raw.replace("```json", "").replace("```", "").strip()
            return json.loads(clean)
    except: return None

# --- Flex Message 樣式工廠 ---
def create_rag_flex(domain, data):
    # 顏色主題
    colors = {
        "INVESTMENT": "#ef5350", # 紅 (漲)
        "FINANCE": "#42a5f5",    # 藍 (理財)
        "HEALTH": "#66bb6a",     # 綠 (健康)
        "KNOWLEDGE": "#ffa726"   # 橘 (筆記)
    }
    theme_color = colors.get(domain, "#999999")
    
    # 建構 Details 行
    detail_boxes = []
    for item in data.get('details', [])[:5]: # 最多顯示 5 行以免太長
        detail_boxes.append({
            "type": "box", "layout": "horizontal",
            "contents": [
                {"type": "text", "text": item['label'], "size": "sm", "color": "#aaaaaa", "flex": 2},
                {"type": "text", "text": str(item['value']), "size": "sm", "color": "#ffffff", "align": "end", "flex": 4, "wrap": True}
            ]
        })

    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box", "layout": "vertical", "backgroundColor": theme_color,
            "contents": [
                {"type": "text", "text": f"{domain} INTELLIGENCE", "color": "#ffffff", "weight": "bold", "size": "xxs"},
                {"type": "text", "text": data.get('title', '查詢結果'), "weight": "bold", "size": "xl", "color": "#ffffff"}
            ]
        },
        "body": {
            "type": "box", "layout": "vertical", "backgroundColor": "#1e1e1e",
            "contents": [
                # 核心數據 (如果有)
                *([{"type": "text", "text": data['main_stat'], "size": "3xl", "weight": "bold", "color": theme_color, "align": "center", "margin": "md"}] if data.get('main_stat') else []),
                
                {"type": "separator", "margin": "lg", "color": "#333333"},
                
                # 詳細列表
                {"type": "box", "layout": "vertical", "margin": "lg", "spacing": "sm", "contents": detail_boxes},
                
                {"type": "separator", "margin": "lg", "color": "#333333"},
                
                # AI 總結
                {
                    "type": "box", "layout": "vertical", "margin": "lg", "backgroundColor": "#333333", "cornerRadius": "md", "paddingAll": "md",
                    "contents": [
                        {"type": "text", "text": "💡 AI 分析：", "size": "xs", "color": "#cccccc", "weight": "bold"},
                        {"type": "text", "text": data.get('summary', ''), "size": "sm", "color": "#ffffff", "wrap": True, "margin": "sm"}
                    ]
                }
            ]
        }
    }

def handle_rag_query(user_query, reply_token, line_bot_api):
    # 1. 判斷意圖
    intent = determine_intent(user_query)
    domain = intent.get("domain") if intent else "OTHER"
    
    if domain == "OTHER":
        # 閒聊模式：不撈 DB，直接回覆 (這裡先簡單處理，可擴充)
        line_bot_api.reply_message(reply_token, TextSendMessage(text="🤖 請輸入具體的投資、記帳或健康問題，我才能幫你查資料喔！"))
        return

    # 2. 併發撈取資料
    target_dbs = list(set(DOMAIN_MAP.get(domain, []) + GLOBAL_DBS))
    raw_data = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_db = {executor.submit(fetch_notion_data, db, 15): db for db in target_dbs}
        for future in concurrent.futures.as_completed(future_to_db):
            db_name = future_to_db[future]
            res = future.result()
            if res: raw_data[db_name] = res

    if not raw_data:
        line_bot_api.reply_message(reply_token, TextSendMessage(text=f"⚠️ 在 {domain} 領域查無相關資料。"))
        return

    # 3. 生成回答與卡片
    ai_result = generate_rag_answer(user_query, domain, raw_data)
    
    if ai_result:
        flex_content = create_rag_flex(domain, ai_result)
        line_bot_api.reply_message(reply_token, FlexSendMessage(alt_text=f"{domain} 查詢結果", contents=flex_content))
    else:
        line_bot_api.reply_message(reply_token, TextSendMessage(text="⚠️ AI 生成回應失敗，請稍後再試。"))
