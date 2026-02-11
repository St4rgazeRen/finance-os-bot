import os
import requests
import json
import base64
import urllib3
from datetime import datetime, timedelta, timezone
from linebot.models import TextSendMessage, FlexSendMessage, QuickReply, QuickReplyButton, MessageAction

# --- 關閉 SSL 警告 ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 環境變數 ---
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DIET_DB_ID = os.getenv("DIET_DB_ID")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

user_sessions = {}

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# --- 台灣時區設定 (UTC+8) ---
TW_TZ = timezone(timedelta(hours=8))

# --- 使用者個人化目標 ---
DAILY_TARGET = {
    "calories": 2300, # kcal
    "protein": 100,   # g
    "carbs": 280,     # g
    "fat": 75         # g
}

def get_meal_type_tw():
    """取得台灣時間的餐別"""
    now_tw = datetime.now(TW_TZ)
    hour = now_tw.hour
    if 5 <= hour < 11: return "早餐"
    elif 11 <= hour < 14: return "午餐"
    elif 14 <= hour < 17: return "點心"
    elif 17 <= hour < 22: return "晚餐"
    else: return "點心"

def make_progress_bar(label, value, target, color):
    """Flex Message 進度條產生器"""
    percent = min(int((value / target) * 100), 100)
    return {
        "type": "box", "layout": "vertical", "margin": "md",
        "contents": [
            {
                "type": "box", "layout": "horizontal",
                "contents": [
                    {"type": "text", "text": label, "size": "xs", "color": "#aaaaaa", "flex": 2},
                    {"type": "text", "text": f"{value}g ({percent}%)", "size": "xs", "color": "#ffffff", "align": "end", "flex": 3}
                ]
            },
            {
                "type": "box", "layout": "vertical", "backgroundColor": "#333333", "height": "6px", "cornerRadius": "30px", "margin": "sm",
                "contents": [
                    {"type": "box", "layout": "vertical", "width": f"{percent}%", "backgroundColor": color, "height": "6px", "cornerRadius": "30px", "contents": []}
                ]
            }
        ]
    }

def create_diet_flex(data):
    """產生營養分析 Flex Message"""
    cal_pct = min(int((data['calories'] / DAILY_TARGET['calories']) * 100), 100)
    cal_color = "#ef5350" if cal_pct > 40 else "#27ae60" 

    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box", "layout": "vertical", "backgroundColor": "#1e1e1e",
            "contents": [
                {"type": "text", "text": "NUTRITION REPORT", "color": "#FFD700", "size": "xs", "weight": "bold"},
                {"type": "text", "text": data['food_name'], "weight": "bold", "size": "xl", "color": "#ffffff", "wrap": True}
            ]
        },
        "body": {
            "type": "box", "layout": "vertical", "backgroundColor": "#1e1e1e",
            "contents": [
                # 1. 總熱量顯示
                {
                    "type": "box", "layout": "vertical", "contents": [
                        {"type": "text", "text": f"{data['calories']} kcal", "size": "4xl", "weight": "bold", "color": cal_color, "align": "center"},
                        {"type": "text", "text": f"佔每日 {cal_pct}% (目標 {DAILY_TARGET['calories']})", "size": "xxs", "color": "#aaaaaa", "align": "center"}
                    ]
                },
                {"type": "separator", "margin": "lg", "color": "#333333"},
                
                # 2. 三大營養素進度條
                make_progress_bar("蛋白質", data.get('protein', 0), DAILY_TARGET['protein'], "#4fc3f7"),
                make_progress_bar("碳水", data.get('carbs', 0), DAILY_TARGET['carbs'], "#ffb74d"),
                make_progress_bar("脂肪", data.get('fat', 0), DAILY_TARGET['fat'], "#e57373"),

                {"type": "separator", "margin": "lg", "color": "#333333"},

                # 3. AI 建議
                {
                    "type": "box", "layout": "vertical", "margin": "lg", "backgroundColor": "#333333", "cornerRadius": "md", "paddingAll": "md",
                    "contents": [
                        {"type": "text", "text": "💡 AI 營養師建議：", "size": "xs", "color": "#cccccc", "weight": "bold"},
                        {"type": "text", "text": data['advice'], "size": "sm", "color": "#ffffff", "wrap": True, "margin": "sm"}
                    ]
                }
            ]
        }
    }

# 🔥 修改重點：支援單圖 (img2_bytes=None)
def analyze_with_gemini_http(img1_bytes, img2_bytes=None):
    print("🤖 正在呼叫 Gemini 2.5 Flash (HTTP)...")
    b64_img1 = base64.b64encode(img1_bytes).decode('utf-8')
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GOOGLE_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    parts = [{"inline_data": {"mime_type": "image/jpeg", "data": b64_img1}}]
    
    if img2_bytes:
        # --- 雙圖模式 (比對完食率) ---
        b64_img2 = base64.b64encode(img2_bytes).decode('utf-8')
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64_img2}})
        
        prompt_text = """
        你是一位專業營養師。圖1是「餐前」、圖2是「餐後」。
        請分析：
        1. 食物名稱 (10字內)。
        2. 根據餐後照片，判斷使用者「實際吃了多少比例」(0.0 - 1.0)。空盤代表 1.0。
        3. 估算「實際攝取」的：總熱量(kcal)、蛋白質(g)、碳水化合物(g)、脂肪(g)。
        4. 給予營養建議 (30-50字)。
        """
    else:
        # --- 單圖模式 (假設完食) ---
        prompt_text = """
        你是一位專業營養師。這是一張食物照片。
        假設使用者 **全部吃完 (Percentage = 1.0)**。
        請分析：
        1. 食物名稱 (10字內)。
        2. percentage 固定回傳 1.0。
        3. 估算整份食物的：總熱量(kcal)、蛋白質(g)、碳水化合物(g)、脂肪(g)。
        4. 給予營養建議 (30-50字)。
        """

    # 共通的 JSON 格式要求
    prompt_text += """
    請回傳 JSON (純數字):
    {
        "food_name": "雞腿便當",
        "percentage": 0.9,
        "calories": 750,
        "protein": 35,
        "carbs": 80,
        "fat": 25,
        "advice": "建議..."
    }
    """
    
    # 將 Prompt 插入到最前面
    parts.insert(0, {"text": prompt_text})

    data = {"contents": [{"parts": parts}]}

    try:
        response = requests.post(url, headers=headers, json=data, verify=False)
        
        if response.status_code == 200:
            result = response.json()
            raw_text = result['candidates'][0]['content']['parts'][0]['text']
            clean_json = raw_text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_json)
        elif response.status_code == 429:
            print("❌ Diet Helper Quota Exceeded (429)")
            return {"error": "quota_exceeded"}
        else:
            print(f"❌ Gemini API Error ({response.status_code}): {response.text}")
            return None

    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def save_to_notion(user_id, data):
    """寫入 Notion 資料庫"""
    now_tw = datetime.now(TW_TZ)
    meal_type = get_meal_type_tw()
    
    # 計算百分比
    cal_pct = int((data['calories'] / DAILY_TARGET['calories']) * 100)
    p_pct = int((data['protein'] / DAILY_TARGET['protein']) * 100)
    c_pct = int((data['carbs'] / DAILY_TARGET['carbs']) * 100)
    f_pct = int((data['fat'] / DAILY_TARGET['fat']) * 100)

    # 詳細資訊字串
    info_text = (
        f"🔥 {data['calories']} kcal ({cal_pct}%) | "
        f"🥚 {data['protein']}g ({p_pct}%) | "
        f"🍚 {data['carbs']}g ({c_pct}%) | "
        f"🥑 {data['fat']}g ({f_pct}%)"
    )

    payload = {
        "parent": {"database_id": DIET_DB_ID},
        "properties": {
            "餐點名稱": {"title": [{"text": {"content": data['food_name']}}]},
            "USER ID": {"rich_text": [{"text": {"content": user_id}}]},
            "餐別": {"select": {"name": meal_type}},
            "用餐時間": {"date": {"start": now_tw.isoformat()}},
            "狀態": {"status": {"name": "分析完成"}},
        },
        "children": [
            {
                "object": "block", "type": "callout",
                "callout": {
                    "rich_text": [{"text": {"content": info_text}}],
                    "icon": {"emoji": "📊"}, "color": "gray_background"
                }
            },
            {
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": f"💡 {data['advice']}"}}]}
            }
        ]
    }
    
    try:
        requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json=payload, verify=False)
        print("✅ Notion 寫入成功")
    except Exception as e:
        print(f"❌ Notion 寫入失敗: {e}")

# 🔥 修改重點：加入 QuickReply
def handle_diet_image(user_id, image_content, reply_token, line_bot_api):
    """處理使用者傳送的飲食圖片"""
    now_tw = datetime.now(TW_TZ)
    
    if user_id not in user_sessions:
        print(f"📸 用戶 {user_id} 傳送了餐前照片")
        # 記錄狀態與餐前照片
        user_sessions[user_id] = {'step': 'waiting_after', 'before_img': image_content, 'timestamp': now_tw}
        
        # 回覆並附帶「完食」按鈕
        text_msg = TextSendMessage(
            text="✅ 收到「餐前照片」！\n請享用美食，吃完後請拍一張「餐後照片」給我。\n\n或是直接點擊下方按鈕結算：",
            quick_reply=QuickReply(items=[
                QuickReplyButton(action=MessageAction(label="完食 (單圖分析)", text="完食"))
            ])
        )
        line_bot_api.reply_message(reply_token, text_msg)
    else:
        print(f"📸 用戶 {user_id} 傳送了餐後照片，開始分析 (雙圖)...")
        session = user_sessions.pop(user_id)
        before_img = session['before_img']
        
        line_bot_api.reply_message(reply_token, TextSendMessage(text="🤖 AI 營養師正在分析中 (雙圖比對)..."))

        perform_analysis(user_id, before_img, image_content, reply_token, line_bot_api)

# 🔥 抽離出來的分析邏輯，供雙圖/單圖共用
def perform_analysis(user_id, img1, img2, reply_token, line_bot_api):
    try:
        result = analyze_with_gemini_http(img1, img2)
        
        if result and result.get("error") == "quota_exceeded":
            line_bot_api.push_message(user_id, TextSendMessage(text="💸 今日 TOKEN 已用罄 QQ"))
            return

        if result:
            save_to_notion(user_id, result)
            flex_content = create_diet_flex(result)
            flex_message = FlexSendMessage(alt_text=f"營養分析：{result['food_name']}", contents=flex_content)
            line_bot_api.push_message(user_id, flex_message)
        else:
            line_bot_api.push_message(user_id, TextSendMessage(text="⚠️ AI 分析失敗，請重試。"))
    except Exception as e:
        print(f"❌ 系統錯誤: {e}")
        line_bot_api.push_message(user_id, TextSendMessage(text="⚠️ 系統發生錯誤"))

# 🔥 新增：供 app.py 呼叫的單圖觸發函式
def trigger_single_image_analysis(user_id, reply_token, line_bot_api):
    if user_id in user_sessions and user_sessions[user_id].get('step') == 'waiting_after':
        print(f"🚀 用戶 {user_id} 觸發單圖分析 (完食)")
        session = user_sessions.pop(user_id)
        before_img = session['before_img']
        
        line_bot_api.reply_message(reply_token, TextSendMessage(text="🤖 AI 營養師正在分析中 (單圖假設完食)..."))
        
        # 傳入 img2=None 觸發單圖模式
        perform_analysis(user_id, before_img, None, reply_token, line_bot_api)
        return True
    return False
