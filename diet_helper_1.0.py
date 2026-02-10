import os
import requests
import json
import base64
from datetime import datetime
from linebot.models import TextSendMessage

# --- 環境變數 ---
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DIET_DB_ID = os.getenv("DIET_DB_ID")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# 使用者狀態暫存 (重啟後會清空，但不影響短時間操作)
user_sessions = {}

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def get_meal_type():
    """根據現在時間判斷餐別"""
    hour = datetime.now().hour
    if 5 <= hour < 11: return "早餐"
    elif 11 <= hour < 14: return "午餐"
    elif 14 <= hour < 17: return "點心"
    elif 17 <= hour < 22: return "晚餐"
    else: return "點心"

def analyze_with_gemini_http(img1_bytes, img2_bytes):
    """
    改用 Requests HTTP 呼叫 Gemini 2.5 Flash
    優點：相容性高，不易被 SSL/防火牆擋下
    """
    print("🤖 正在呼叫 Gemini 2.5 Flash (HTTP)...")

    # 1. 將 Bytes 轉為 Base64 字串
    b64_img1 = base64.b64encode(img1_bytes).decode('utf-8')
    b64_img2 = base64.b64encode(img2_bytes).decode('utf-8')

    # 2. 設定 API URL (使用 gemini-2.5-flash)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GOOGLE_API_KEY}"
    
    headers = {"Content-Type": "application/json"}
    
    prompt_text = """
    你是一位專業營養師。圖1是「餐前」、圖2是「餐後」。
    請分析：
    1. 食物名稱與內容物。
    2. 根據餐後照片，判斷使用者「實際吃了多少比例」(0.0 - 1.0)。空盤代表 1.0。
    3. 估算「實際攝取」的總熱量(大卡)。
    4. 給予簡短營養建議 (50字內)。
    
    請直接回傳純 JSON 格式，不要 markdown 標記，格式如下：
    {
        "food_name": "雞腿便當",
        "percentage": 0.9,
        "calories": 750,
        "advice": "蛋白質充足，但飯量稍多，建議下一餐減少澱粉。"
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
        # 在 Render (雲端) 其實不需要 verify=False，但為了保證跟你本地測試一樣穩，
        # 我們先保留它 (若 Render 報錯可改回 verify=True)
        response = requests.post(url, headers=headers, json=data, verify=False)
        
        if response.status_code != 200:
            print(f"❌ Gemini API Error ({response.status_code}): {response.text}")
            return None
            
        result = response.json()
        
        # 解析回傳結構
        try:
            raw_text = result['candidates'][0]['content']['parts'][0]['text']
            clean_json = raw_text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_json)
        except (KeyError, IndexError) as e:
            print(f"❌ JSON 解析失敗: {e} | Raw: {result}")
            return None

    except Exception as e:
        print(f"❌ Gemini 連線失敗: {e}")
        return None

def save_to_notion(user_id, data):
    """寫入 Notion 資料庫"""
    now = datetime.now()
    meal_type = get_meal_type()
    title = f"{now.strftime('%Y%m%d')}-{meal_type}"
    
    # 建立 Payload
    payload = {
        "parent": {"database_id": DIET_DB_ID},
        "properties": {
            "餐點名稱": {"title": [{"text": {"content": title}}]},
            "USER ID": {"rich_text": [{"text": {"content": user_id}}]},
            "餐別": {"select": {"name": meal_type}},
            "用餐時間": {"date": {"start": now.isoformat()}},
            "狀態": {"status": {"name": "分析完成"}},
            
            # 數值欄位 (對應你 Notion 的 Number 欄位，方便做統計)
            # 若你的資料庫還沒開這些欄位，Notion API 會自動忽略或報錯，建議先開好
            # "總熱量 (kcal)": {"number": data['calories']},
            # "攝取比例": {"number": data['percentage']}, 
        },
        # 頁面內文 (詳細報告)
        "children": [
            {
                "object": "block", "type": "callout",
                "callout": {
                    "rich_text": [{"text": {"content": f"熱量: {data['calories']} kcal | 完食率: {int(data['percentage']*100)}%"}}],
                    "icon": {"emoji": "🔥"}, "color": "orange_background"
                }
            },
            {
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": f"🍱 {data['food_name']}\n💡 {data['advice']}"}}]}
            }
        ]
    }
    
    # 寫入 Notion
    try:
        r = requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json=payload, verify=False)
        if r.status_code == 200:
            print(f"✅ Notion 寫入成功: {title}")
        else:
            print(f"❌ Notion 寫入失敗: {r.text}")
    except Exception as e:
        print(f"❌ Notion 連線錯誤: {e}")

def handle_diet_image(user_id, image_content, reply_token, line_bot_api):
    """
    主邏輯：處理 LINE 圖片訊息
    """
    
    if user_id not in user_sessions:
        # --- 步驟 1: 收到第一張圖 (餐前) ---
        print(f"📸 用戶 {user_id} 傳送了餐前照片")
        
        # 暫存狀態
        user_sessions[user_id] = {
            'step': 'waiting_after',
            'before_img': image_content, # 直接存 Bytes
            'timestamp': datetime.now()
        }
        
        reply = "✅ 收到「餐前照片」！\n請慢慢享用，吃完後請再傳一張「餐後照片」給我，我來幫你計算熱量。"
        line_bot_api.reply_message(reply_token, TextSendMessage(text=reply))
        
    else:
        # --- 步驟 2: 收到第二張圖 (餐後) ---
        print(f"📸 用戶 {user_id} 傳送了餐後照片，準備開始分析...")
        
        # 取出第一張圖，並清除狀態
        session = user_sessions.pop(user_id)
        before_img = session['before_img']
        after_img = image_content
        
        # 先回覆使用者，避免 LINE Timeout
        line_bot_api.reply_message(reply_token, TextSendMessage(text="🤖 AI 營養師正在分析前後差異與熱量... (Gemini 2.5)"))

        try:
            # A. 呼叫 Gemini 2.5 Flash
            result = analyze_with_gemini_http(before_img, after_img)
            
            if result:
                # B. 寫入 Notion
                save_to_notion(user_id, result)
                
                # C. 推播報告
                report = (
                    f"🍱 餐點：{result['food_name']}\n"
                    f"🔥 熱量：{result['calories']} kcal (完食率 {int(result['percentage']*100)}%)\n"
                    f"💡 建議：{result['advice']}"
                )
                line_bot_api.push_message(user_id, TextSendMessage(text=report))
            else:
                line_bot_api.push_message(user_id, TextSendMessage(text="⚠️ AI 分析失敗，請確認照片清晰度後再試一次。"))
                
        except Exception as e:
            print(f"❌ 處理流程錯誤: {e}")
            line_bot_api.push_message(user_id, TextSendMessage(text="⚠️ 系統發生未知錯誤"))