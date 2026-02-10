import os
import requests
import json
import base64
from datetime import datetime
from linebot.models import TextSendMessage, FlexSendMessage

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

# --- 🔥 使用者個人化目標 (1989年, 77kg) ---
DAILY_TARGET = {
    "calories": 2300, # kcal
    "protein": 100,   # g
    "carbs": 280,     # g
    "fat": 75         # g
}

def get_meal_type():
    hour = datetime.now().hour
    if 5 <= hour < 11: return "早餐"
    elif 11 <= hour < 14: return "午餐"
    elif 14 <= hour < 17: return "點心"
    elif 17 <= hour < 22: return "晚餐"
    else: return "點心"

def analyze_with_gemini_http(img1_bytes, img2_bytes):
    print("🤖 正在呼叫 Gemini 2.0 Flash (HTTP)...")
    b64_img1 = base64.b64encode(img1_bytes).decode('utf-8')
    b64_img2 = base64.b64encode(img2_bytes).decode('utf-8')
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GOOGLE_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    # 🔥 修改 Prompt: 增加營養素欄位
    prompt_text = """
    你是一位專業營養師。圖1是「餐前」、圖2是「餐後」。
    請分析：
    1. 食物名稱(10字內)。
    2. 根據餐後照片，判斷使用者「實際吃了多少比例」(0.0 - 1.0)。空盤代表 1.0。
    3. 估算「實際攝取」的：總熱量(kcal)、蛋白質(g)、碳水化合物(g)、脂肪(g)。
    4. 給予簡短營養建議 (30字內)。
    
    回傳 JSON (純數字，不要單位):
    {
        "food_name": "雞腿便當",
        "percentage": 0.9,
        "calories": 750,
        "protein": 35,
        "carbs": 80,
        "fat": 25,
        "advice": "建議下一餐多吃蔬菜。"
    }
    """

    data = {
        "contents": [{
            "parts": [
                {"text": prompt_text},
                {"inline_data": {"mime_type": "image/jpeg", "data": b64_img1}},
                {"inline_data": {"mime_type": "image/jpeg", "data": b64_img2}}
            ]
        }]
    }

    try:
        response = requests.post(url, headers=headers, json=data, verify=False)
        if response.status_code != 200: return None
        result = response.json()
        raw_text = result['candidates'][0]['content']['parts'][0]['text']
        clean_json = raw_text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def save_to_notion(user_id, data):
    now = datetime.now()
    meal_type = get_meal_type()
    title = f"{now.strftime('%Y%m%d')}-{meal_type}"
    payload = {
        "parent": {"database_id": DIET_DB_ID},
        "properties": {
            "餐點名稱": {"title": [{"text": {"content": title}}]},
            "USER ID": {"rich_text": [{"text": {"content": user_id}}]},
            "餐別": {"select": {"name": meal_type}},
            "用餐時間": {"date": {"start": now.isoformat()}},
            "狀態": {"status": {"name": "分析完成"}},
        },
        "children": [
            {
                "object": "block", "type": "callout",
                "callout": {
                    "rich_text": [{"text": {"content": f"🔥 {data['calories']} kcal | 🥚 {data['protein']}g | 🍚 {data['carbs']}g | 🥑 {data['fat']}g"}}],
                    "icon": {"emoji": "📊"}, "color": "gray_background"
                }
            },
            {
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": f"🍱 {data['food_name']}\n💡 {data['advice']}"}}]}
            }
        ]
    }
    requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json=payload, verify=False)

# --- 🔥 新增小工具：產生進度條 ---
def make_progress_bar(label, value, target, color):
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
    # 計算熱量佔比
    cal_pct = min(int((data['calories'] / DAILY_TARGET['calories']) * 100), 100)
    cal_color = "#ef5350" if cal_pct > 40 else "#27ae60" # 如果一餐吃超過日需40%顯示紅字

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
                make_progress_bar("蛋白質", data.get('protein', 0), DAILY_TARGET['protein'], "#4fc3f7"), # 藍色
                make_progress_bar("碳水", data.get('carbs', 0), DAILY_TARGET['carbs'], "#ffb74d"),   # 橘色
                make_progress_bar("脂肪", data.get('fat', 0), DAILY_TARGET['fat'], "#e57373"),      # 紅色

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

def handle_diet_image(user_id, image_content, reply_token, line_bot_api):
    if user_id not in user_sessions:
        print(f"📸 用戶 {user_id} 傳送了餐前照片")
        user_sessions[user_id] = {'step': 'waiting_after', 'before_img': image_content, 'timestamp': datetime.now()}
        line_bot_api.reply_message(reply_token, TextSendMessage(text="✅ 收到「餐前照片」！\n請享用美食，吃完後請拍一張「餐後照片」給我。"))
    else:
        print(f"📸 用戶 {user_id} 傳送了餐後照片，開始分析...")
        session = user_sessions.pop(user_id)
        before_img = session['before_img']
        
        line_bot_api.reply_message(reply_token, TextSendMessage(text="🤖 AI 營養師正在詳細分析營養成分..."))

        try:
            result = analyze_with_gemini_http(before_img, image_content)
            if result:
                save_to_notion(user_id, result)
                # 產生新的詳細版 Flex Message
                flex_content = create_diet_flex(result)
                line_bot_api.push_message(user_id, FlexSendMessage(alt_text="營養分析報告", contents=flex_content))
            else:
                line_bot_api.push_message(user_id, TextSendMessage(text="⚠️ AI 分析失敗，請重試。"))
        except Exception as e:
            print(f"❌ 錯誤: {e}")
            line_bot_api.push_message(user_id, TextSendMessage(text="⚠️ 系統錯誤"))

