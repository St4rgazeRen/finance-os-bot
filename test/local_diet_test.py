import os
import requests
import json
import base64
import urllib3
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# --- 關閉 SSL 警告 ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 🔥 載入環境變數 ---
load_dotenv(override=True)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DIET_DB_ID = os.getenv("DIET_DB_ID")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID") 

TW_TZ = timezone(timedelta(hours=8))
DAILY_TARGET = {"calories": 2300, "protein": 100, "carbs": 280, "fat": 75}

def get_meal_type_tw():
    now_tw = datetime.now(TW_TZ)
    hour = now_tw.hour
    if 5 <= hour < 11: return "早餐"
    elif 11 <= hour < 14: return "午餐"
    elif 14 <= hour < 17: return "點心"
    elif 17 <= hour < 22: return "晚餐"
    else: return "點心"

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
                {
                    "type": "box", "layout": "vertical", "contents": [
                        {"type": "text", "text": f"{data['calories']} kcal", "size": "4xl", "weight": "bold", "color": cal_color, "align": "center"},
                        {"type": "text", "text": f"佔每日 {cal_pct}% (目標 {DAILY_TARGET['calories']})", "size": "xxs", "color": "#aaaaaa", "align": "center"}
                    ]
                },
                {"type": "separator", "margin": "lg", "color": "#333333"},
                make_progress_bar("蛋白質", data.get('protein', 0), DAILY_TARGET['protein'], "#4fc3f7"),
                make_progress_bar("碳水", data.get('carbs', 0), DAILY_TARGET['carbs'], "#ffb74d"),
                make_progress_bar("脂肪", data.get('fat', 0), DAILY_TARGET['fat'], "#e57373"),
                {"type": "separator", "margin": "lg", "color": "#333333"},
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

def analyze_with_gemini_local(img1_path, img2_path=None):
    if not GOOGLE_API_KEY: return None

    print(f"🤖 [Gemini] 讀取餐前: {img1_path}")
    with open(img1_path, "rb") as f1:
        b64_img1 = base64.b64encode(f1.read()).decode('utf-8')

    parts = [{"inline_data": {"mime_type": "image/jpeg", "data": b64_img1}}]
    
    # 判斷是單圖還是雙圖
    if img2_path:
        print(f"🤖 [Gemini] 讀取餐後: {img2_path} (雙圖模式)")
        with open(img2_path, "rb") as f2:
            b64_img2 = base64.b64encode(f2.read()).decode('utf-8')
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64_img2}})
        
        # 雙圖 Prompt
        prompt_text = """
        你是一位專業營養師。圖1是「餐前」、圖2是「餐後」。
        請分析：
        1. 食物名稱 (10字內)。
        2. 根據餐後照片，判斷「實際吃了多少比例」(0.0 - 1.0)。
        3. 估算「實際攝取」的：總熱量(kcal)、蛋白質(g)、碳水(g)、脂肪(g)。
        4. 給予營養建議 (30-50字)。
        """
    else:
        print(f"🤖 [Gemini] 無餐後照片 (單圖模式 - 假設完食)")
        # 單圖 Prompt
        prompt_text = """
        你是一位專業營養師。這是一張食物照片。
        假設使用者 **全部吃完 (Percentage = 1.0)**。
        請分析：
        1. 食物名稱 (10字內)。
        2. percentage 固定回傳 1.0。
        3. 估算整份食物的：總熱量(kcal)、蛋白質(g)、碳水(g)、脂肪(g)。
        4. 給予營養建議 (30-50字)。
        """

    # 加上共通的 JSON 格式要求
    prompt_text += """
    回傳 JSON (純數字):
    {
        "food_name": "雞腿便當",
        "percentage": 1.0,
        "calories": 750,
        "protein": 35,
        "carbs": 80,
        "fat": 25,
        "advice": "建議..."
    }
    """
    
    parts.insert(0, {"text": prompt_text})

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GOOGLE_API_KEY}"
    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": parts}]}

    try:
        response = requests.post(url, headers=headers, json=data, verify=False)
        if response.status_code == 200:
            result = response.json()
            raw_text = result['candidates'][0]['content']['parts'][0]['text']
            clean_json = raw_text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_json)
        else:
            print(f"❌ Gemini API Error: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

# 🔥 核心修改：將數值寫入 Notion Number 欄位
def generate_notion_payload(data, user_id="TEST_USER_LOCAL"):
    now_tw = datetime.now(TW_TZ)
    meal_type = get_meal_type_tw()
    p_pct = int((data['protein'] / DAILY_TARGET['protein']) * 100)
    c_pct = int((data['carbs'] / DAILY_TARGET['carbs']) * 100)
    f_pct = int((data['fat'] / DAILY_TARGET['fat']) * 100)
    cal_pct = int((data['calories'] / DAILY_TARGET['calories']) * 100)

    # Callout 顯示文字
    info_text = (
        f"🔥 {data['calories']} kcal ({cal_pct}%) | "
        f"🥚 {data['protein']}g ({p_pct}%) | "
        f"🍚 {data['carbs']}g ({c_pct}%) | "
        f"🥑 {data['fat']}g ({f_pct}%)"
    )

    return {
        "parent": {"database_id": DIET_DB_ID},
        "properties": {
            # 1. 既有欄位
            "餐點名稱": {"title": [{"text": {"content": data['food_name']}}]}, 
            "USER ID": {"rich_text": [{"text": {"content": user_id}}]},
            "餐別": {"select": {"name": meal_type}},
            "用餐時間": {"date": {"start": now_tw.isoformat()}}, 
            "狀態": {"status": {"name": "分析完成"}},
            
            # 🔥 2. 新增數值欄位 (Number)
            "熱量": {"number": data['calories']},
            "蛋白質": {"number": data['protein']},
            "碳水化合物": {"number": data['carbs']},
            "脂肪": {"number": data['fat']}
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

def push_line_flex_message(user_id, flex_content, alt_text):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    payload = {"to": user_id, "messages": [{"type": "flex", "altText": alt_text, "contents": flex_content}]}
    try:
        requests.post(url, headers=headers, json=payload, verify=False)
        print("✅ [LINE] 訊息傳送成功！")
    except Exception as e:
        print(f"❌ [LINE] 傳送失敗: {e}")

if __name__ == "__main__":
    # --- 模擬測試 ---
    print("請選擇測試模式：")
    print("1. 單圖模式 (模擬輸入『完食』)")
    print("2. 雙圖模式 (模擬傳兩張圖)")
    choice = input("請輸入 (1/2): ")

    img1 = "test_before.jpg" 
    
    if choice == "1":
        if os.path.exists(img1):
            print("\n🚀 執行單圖分析 (假設完食)...")
            result = analyze_with_gemini_local(img1, None)
        else:
            print(f"❌ 找不到 {img1}")
            exit()
    
    elif choice == "2":
        img2 = "test_after.jpg" 
        if os.path.exists(img1) and os.path.exists(img2):
            print("\n🚀 執行雙圖比對分析...")
            result = analyze_with_gemini_local(img1, img2)
        else:
            print(f"❌ 找不到圖片")
            exit()
    else:
        print("無效輸入")
        exit()

    # --- 後續處理 (Notion & LINE) ---
    if result:
        print(f"\n✅ 分析結果: {result['food_name']} ({result['calories']} kcal)")
        
        # 寫入 Notion
        if NOTION_TOKEN and DIET_DB_ID:
            print("🚀 寫入 Notion...")
            payload = generate_notion_payload(result)
            try:
                headers = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}
                # 🔥 Verify False
                r = requests.post("https://api.notion.com/v1/pages", headers=headers, json=payload, verify=False)
                if r.status_code == 200:
                    print("✅ Notion 寫入成功")
                else:
                    print(f"❌ Notion 寫入失敗: {r.status_code} - {r.text}")
            except Exception as e: print(e)

        # 推送 LINE
        if LINE_CHANNEL_ACCESS_TOKEN and LINE_USER_ID:
            print("🚀 推送 LINE Flex...")
            flex_content = create_diet_flex(result)
            push_line_flex_message(LINE_USER_ID, flex_content, f"營養分析：{result['food_name']}")
    else:
        print("❌ 分析失敗")