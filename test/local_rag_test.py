import os
import requests
import json
import base64
import urllib3
import re
import concurrent.futures
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# --- 關閉 SSL 警告 ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 🔥 載入環境變數 ---
load_dotenv(override=True)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")

# 資料庫 IDs
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# --- 領域與資料庫設定 ---
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
        # Timeout 設為 90 秒，因為 200 筆資料處理需要時間
        r = requests.post(url, headers=headers, json=data, verify=False, timeout=90)
        if r.status_code == 200:
            raw = r.json()['candidates'][0]['content']['parts'][0]['text']
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            else:
                match_list = re.search(r'\[.*\]', raw, re.DOTALL)
                return json.loads(match_list.group(0)) if match_list else None
    except Exception as e:
        print(f"❌ Gemini Error: {e}")
    return None

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

def extract_notion_value(prop):
    p_type = prop.get("type")
    if p_type == "title": return prop["title"][0]["plain_text"] if prop["title"] else ""
    elif p_type == "rich_text": return prop["rich_text"][0]["plain_text"] if prop["rich_text"] else ""
    elif p_type == "number": return prop["number"]
    elif p_type == "select": return prop["select"]["name"] if prop["select"] else ""
    elif p_type == "status": return prop["status"]["name"] if prop["status"] else ""
    elif p_type == "date": return prop["date"]["start"] if prop["date"] else ""
    elif p_type == "formula":
        f = prop["formula"]
        if f["type"] == "number": return f["number"]
        if f["type"] == "string": return f["string"]
    elif p_type == "rollup":
        if prop["rollup"]["type"] == "number": return prop["rollup"]["number"]
    return None

def fetch_page_content(page_id):
    url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=30" # 稍微減少 block 讀取量以提升效能
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

    # 🔥 優化 2：如果有日期過濾，上限提升到 200 筆；否則 30 筆
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
             payload["filter"] = {"timestamp": "created_time", "created_time": {"on_or_after": date_filter["start"]}}
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
            simple = {} # 不存 ID 了，除非要抓內文，節省記憶體
            if fetch_content_flag: simple["id"] = page["id"]

            for k, v in page["properties"].items():
                val = extract_notion_value(v)
                # 🔥 優化 3：只保留有值的欄位，且過濾掉一些系統欄位如果不需要
                if val is not None and val != "": 
                    simple[k] = val
            
            if fetch_content_flag:
                content = fetch_page_content(page["id"])
                if content:
                    simple["content_body"] = content[:500] # 限制內文長度
                del simple["id"] # 用完就丟
            
            results.append(simple)
        return results
    except Exception as e:
        print(f"Fetch Error ({db_env_key}): {e}")
        return []

def generate_rag_response(user_query, domain, raw_data):
    context = json.dumps(raw_data, ensure_ascii=False, indent=2)
    # 🔥 優化 3：限制 Context 長度為 60000 字元，防止 Memory Error
    if len(context) > 60000: 
        print(f"⚠️ Context 過長 ({len(context)} chars)，進行截斷...")
        context = context[:60000] + "...(略)"

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
       - list [{{ "title": "重點", "content": "內容" }}]
    """
    return ask_gemini_json(prompt)

# --- 🔥 Flex Message UI 優化 ---

def create_summary_flex(domain, data):
    """第一張卡：數據儀表板 (UI 修復版)"""
    colors = {"INVESTMENT": "#ef5350", "FINANCE": "#42a5f5", "HEALTH": "#66bb6a", "KNOWLEDGE": "#ffa726"}
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
                {"type": "text", "text": label, "size": "sm", "color": "#aaaaaa", "flex": 2, "wrap": True}, # Label也要wrap
                {"type": "text", "text": value, "size": "sm", "color": "#ffffff", "align": "end", "flex": 4, "wrap": True} # Value維持wrap
            ]
        })

    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box", "layout": "vertical", "backgroundColor": theme_color,
            "contents": [
                {"type": "text", "text": f"{domain} INTELLIGENCE", "color": "#ffffff", "weight": "bold", "size": "xxs"},
                # 🔥 優化 1：標題自動換行 (wrap=True)，避免被切掉
                {"type": "text", "text": str(data.get('title', '查詢結果')), "weight": "bold", "size": "xl", "color": "#ffffff", "wrap": True}
            ]
        },
        "body": {
            "type": "box", "layout": "vertical", "backgroundColor": "#1e1e1e",
            "contents": [
                # 🔥 優化 1：核心數據縮小適應 (shrink-to-fit)，避免 $52,000... 這種情況
                *([{"type": "text", "text": str(data['main_stat']), "size": "4xl", "weight": "bold", "color": theme_color, "align": "center", "margin": "md", "adjustMode": "shrink-to-fit"}] if data.get('main_stat') else []),
                {"type": "separator", "margin": "lg", "color": "#333333"},
                {"type": "box", "layout": "vertical", "margin": "lg", "spacing": "sm", "contents": detail_boxes}
            ]
        }
    }

def create_analysis_flex(analysis_data):
    """第二張卡：詳細分析"""
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

def push_flex(user_id, alt_text, flex_content):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    payload = {"to": user_id, "messages": [{"type": "flex", "altText": alt_text, "contents": flex_content}]}
    try:
        requests.post(url, headers=headers, json=payload, verify=False)
        print("✅ Flex Message 傳送成功")
    except Exception as e:
        print(f"❌ 傳送失敗: {e}")

if __name__ == "__main__":
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        print("❌ 請先設定 .env 中的 LINE_CHANNEL_ACCESS_TOKEN 與 LINE_USER_ID")
        exit()

    while True:
        print("\n" + "="*40)
        user_query = input("請輸入測試問題 (輸入 exit 離開): ")
        if user_query.lower() in ["exit", "quit"]: break
        if not user_query.strip(): continue

        print(f"🚀 開始分析: {user_query}")
        
        # 1. 意圖
        intent = analyze_query_intent(user_query)
        if not intent:
            print("❌ 意圖分析失敗")
            continue
        domain = intent.get("domain", "OTHER")
        date_filter = intent.get("date_filter")
        print(f"🧠 意圖: {domain} | 日期: {date_filter}")

        # 2. 撈資料
        target_dbs = list(set(DOMAIN_MAP.get(domain, []) + GLOBAL_DBS)) if domain != "KNOWLEDGE" else GLOBAL_DBS
        raw_data = {}
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_db = {executor.submit(fetch_notion_data, db, domain, date_filter): db for db in target_dbs}
            for future in concurrent.futures.as_completed(future_to_db):
                db_name = future_to_db[future]
                res = future.result()
                if res:
                    raw_data[db_name] = res
                    print(f"  -> {db_name}: {len(res)} 筆")

        if not raw_data:
            print("❌ 查無資料")
            continue

        # 3. 生成與發送
        print("🤖 Gemini 生成中...")
        ai_result = generate_rag_response(user_query, domain, raw_data)
        
        if ai_result:
            print("📱 發送 LINE 訊息...")
            flex1 = create_summary_flex(domain, ai_result.get("card_data", {}))
            push_flex(LINE_USER_ID, "查詢摘要", flex1)
            
            flex2 = create_analysis_flex(ai_result.get("detailed_analysis", []))
            push_flex(LINE_USER_ID, "詳細分析", flex2)
        else:
            print("❌ 生成失敗")