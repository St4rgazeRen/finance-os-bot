import os
import requests
import json
import base64
from datetime import datetime
# 🔥 記得引入 FlexSendMessage
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

def get_meal_type():
    hour = datetime.now().hour
    if 5 <= hour < 11: return "早餐"
    elif 11 <= hour < 14: return "午餐"
    elif 14 <= hour < 17: return "點心"
    elif 17 <= hour < 22: return "晚餐"
    else: return "點心"

def analyze_with_gemini_http(img1_bytes, img2_bytes):
    print("🤖 正在呼叫 Gemini 2.5 Flash (HTTP)...")
    b64_img1 = base64.b64encode(img1_bytes).decode('utf-8')
    b64_img2 = base64.b64encode(img2_bytes).decode('utf-8')
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GOOGLE_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    prompt_text = """
    你是一位專業營養師。圖1是「餐前」、圖2是「餐後」。
    請分析：
    1. 食物名稱(10字內)。
    2. 根據餐後照片，判斷使用者「實際吃了多少比例」(0.0 - 1.0)。空盤代表 1.0。
    3. 估算「實際攝取」的總熱量(大卡)。
    4. 給予簡短營養建議 (30字內)。
    
    回傳 JSON:
    {
        "food_name": "雞腿便當",
        "percentage": 0.9,
        "calories": 750,
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
                    "rich_text": [{"text": {"content": f"熱量: {data['calories']} kcal | 完食: {int(data['percentage']*100)}%"}}],
                    "icon": {"emoji": "🔥"}, "color": "orange_background"
                }
            },
            {
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": f"🍱 {data['food_name']}\n💡 {data['advice']}"}}]}
            }
        ]
    }
    requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json=payload, verify=False)

# 🔥 新增：製作 Flex Message 卡片
def create_diet_flex(data):
    pct = int(data['percentage'] * 100)
    # 根據熱量決定顏色 (大於800紅，小於800綠)
    color = "#ef5350" if data['calories'] > 800 else "#27ae60"
    
    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#1e1e1e",
            "contents": [
                {"type": "text", "text": "NUTRITION REPORT", "color": "#FFD700", "size": "xs", "weight": "bold"},
                {"type": "text", "text": data['food_name'], "weight": "bold", "size": "xl", "color": "#ffffff", "wrap": True}
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#1e1e1e",
            "contents": [
                # 熱量大數字
                {
                    "type": "text",
                    "text": f"{data['calories']} kcal",
                    "size": "4xl",
                    "weight": "bold",
                    "color": color,
                    "align": "center"
                },
                {"type": "text", "text": "ESTIMATED INTAKE", "size": "xxs", "color": "#aaaaaa", "align": "center", "margin": "none"},
                
                {"type": "separator", "margin": "lg", "color": "#333333"},
                
                # 完食率進度條
                {
                    "type": "box", "layout": "vertical", "margin": "lg",
                    "contents": [
                        {"type": "text", "text": f"完食率 {pct}%", "size": "xs", "color": "#FFD700", "align": "end"},
                        {
                            "type": "box", "layout": "vertical", "backgroundColor": "#333333", "height": "6px", "cornerRadius": "30px",
                            "contents": [
                                {"type": "box", "layout": "vertical", "width": f"{pct}%", "backgroundColor": "#FFD700", "height": "6px", "cornerRadius": "30px", "contents": []}
                            ]
                        }
                    ]
                },
                
                # AI 建議區塊
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
        
        line_bot_api.reply_message(reply_token, TextSendMessage(text="🤖 AI 營養師正在分析熱量 (Gemini 2.5)..."))

        try:
            result = analyze_with_gemini_http(before_img, image_content)
            if result:
                save_to_notion(user_id, result)
                
                # 🔥 改用 Flex Message 推播
                flex_content = create_diet_flex(result)
                line_bot_api.push_message(user_id, FlexSendMessage(alt_text="營養分析報告", contents=flex_content))
            else:
                line_bot_api.push_message(user_id, TextSendMessage(text="⚠️ AI 分析失敗，請重試。"))
        except Exception as e:
            print(f"❌ 錯誤: {e}")
            line_bot_api.push_message(user_id, TextSendMessage(text="⚠️ 系統錯誤"))