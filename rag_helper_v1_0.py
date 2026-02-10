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

MODEL_NAME = "gemini-2.0-flash"

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
        else:
            # 🔥 新增這段：把錯誤印出來，不要默默 return None
            print(f"❌ Gemini API Error ({r.status_code}): {r.text}")
    except Exception as e:
        print(f"❌ Request Failed: {e}")
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
    
    # 🔥 針對流水帳特化：撈更多資料以覆蓋「上個月」
    if db_env_key == "TRANSACTIONS_DB_ID":
        limit = 60
    
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

def generate_rag_response(user_query, domain, raw_data):
    # 限制 Context 長度
    context = json.dumps(raw_data, ensure_ascii=False, indent=2)
    if len(context) > 60000: context = context[:60000] + "...(略)"

    # 🔥 Prompt 升級：要求同時產生 JSON 卡片數據 AND 詳細文字分析
    prompt = f"""
    你是 AI 財務與生活助理。使用者問："{user_query}"
    資料庫 ({domain}) 紀錄：
    {context}
    
    請回傳一個 JSON 物件，包含兩部分：
    1. "card_data": 用於生成 UI 的精簡數據
       - title: 標題
       - main_stat: 核心數據 (如 "$1,200", "2100 kcal")
       - details: list [{{ "label": "項目", "value": "數值" }}]
    
    2. "detailed_analysis": 針對使用者問題的詳細回答與建議 (字串)。
       - 請像是專業顧問一樣，針對數據給出具體分析。
       - 如果資料不足 (例如問上個月但只有本月資料)，請誠實說明「目前資料只包含近期紀錄」，不要瞎掰數字。
       - 內容要言之有物，可以包含條列式建議。
    
    格式範例:
    {{
        "card_data": {{
            "title": "飲品消費查詢",
            "main_stat": "$500",
            "details": [
                {{ "label": "50嵐", "value": "$120" }},
                {{ "label": "星巴克", "value": "$380" }}
            ]
        }},
        "detailed_analysis": "您上個月在飲料上的花費主要集中在...建議可以..."
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
    colors = {
        "INVESTMENT": "#ef5350", "FINANCE": "#42a5f5", 
        "HEALTH": "#66bb6a", "KNOWLEDGE": "#ffa726"
    }
    theme_color = colors.get(domain, "#999999")
    
    detail_boxes = []
    for item in data.get('details', [])[:5]: 
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
                *([{"type": "text", "text": data['main_stat'], "size": "3xl", "weight": "bold", "color": theme_color, "align": "center", "margin": "md"}] if data.get('main_stat') else []),
                {"type": "separator", "margin": "lg", "color": "#333333"},
                {"type": "box", "layout": "vertical", "margin": "lg", "spacing": "sm", "contents": detail_boxes}
            ]
        }
    }

def handle_rag_query(user_query, reply_token, line_bot_api):
    intent = determine_intent(user_query)
    domain = intent.get("domain") if intent else "OTHER"
    
    if domain == "OTHER":
        line_bot_api.reply_message(reply_token, TextSendMessage(text="🤖 請輸入投資、記帳或健康相關問題。"))
        return

    target_dbs = list(set(DOMAIN_MAP.get(domain, []) + GLOBAL_DBS))
    raw_data = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_db = {executor.submit(fetch_notion_data, db, 15): db for db in target_dbs}
        for future in concurrent.futures.as_completed(future_to_db):
            db_name = future_to_db[future]
            res = future.result()
            if res: raw_data[db_name] = res

    if not raw_data:
        line_bot_api.reply_message(reply_token, TextSendMessage(text=f"⚠️ 在 {domain} 領域查無資料。"))
        return

    # 生成完整回應 (含卡片與分析)
    ai_result = generate_rag_response(user_query, domain, raw_data)
    
    if ai_result:
        # 1. 製作 Flex 卡片 (只放重點數據)
        card_data = ai_result.get("card_data", {})
        flex_msg = FlexSendMessage(alt_text=f"{domain} 查詢結果", contents=create_rag_flex(domain, card_data))
        
        # 2. 製作詳細文字訊息
        text_msg = TextSendMessage(text=ai_result.get("detailed_analysis", "無詳細分析"))
        
        # 🔥 重點：一次回傳兩個訊息 (Flex + Text)
        line_bot_api.reply_message(reply_token, [flex_msg, text_msg])
    else:
        line_bot_api.reply_message(reply_token, TextSendMessage(text="⚠️ AI 生成回應失敗。"))
