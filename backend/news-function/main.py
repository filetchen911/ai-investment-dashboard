# news-function/main.py (v2.2.1 - 修正版)

import os
import json
import re # <-- 引入正規表示式函式庫，用於清理 JSON
import datetime
import firebase_admin
from firebase_admin import firestore
import google.generativeai as genai # <-- 新的 import
from google.api_core import exceptions # <-- 用於捕捉額度錯誤
import feedparser
import functions_framework

# --- 初始化 ---
try:
    firebase_admin.initialize_app()
    print("✅ Firebase Admin SDK 初始化成功。")
except ValueError:
    print("ℹ️ Firebase App 已被初始化，跳過。")
except Exception as e:
    print(f"❌ 初始化失敗: {e}")


# --- 輔助函數 ---
def get_finance_news_from_rss(rss_urls):
    """從多個 RSS 源獲取最新財經新聞，並記錄來源。"""
    print("  > [News Engine] 開始抓取 RSS 新聞...")
    all_news = []
    for rss_url in rss_urls:
        try:
            feed = feedparser.parse(rss_url)
            source_name = feed.feed.title if hasattr(feed.feed, 'title') else 'Unknown Source'
            for entry in feed.entries[:7]: # 每個來源最多取 7 條
                if entry.title and entry.link and entry.link not in [n['link'] for n in all_news]:
                    all_news.append({
                        "title": entry.title,
                        "link": entry.link,
                        "source": source_name,
                    })
        except Exception as e:
            print(f"    - 錯誤：從 {rss_url} 獲取新聞時發生錯誤: {e}")
    print(f"  > [News Engine] 總共從 RSS 抓取到 {len(all_news)} 條新聞。")
    return all_news

def get_latest_economic_data(db_client):
    """從 Firestore 獲取最新一天的趨勢經濟數據。"""
    print("  > [Data Engine] 正在從 Firestore 獲取宏觀數據...")
    try:
        query = db_client.collection('daily_economic_data').order_by('date', direction=firestore.Query.DESCENDING).limit(1)
        docs = list(query.stream())
        if docs:
            print("  > [Data Engine] 成功獲取到宏觀經濟數據。")
            return docs[0].to_dict().get('data_series_items', [])
        else:
            print("  > [Data Engine] 在 Firestore 中未找到宏觀經濟數據。")
            return []
    except Exception as e:
        print(f"  > [Data Engine] 獲取經濟數據時發生錯誤: {e}")
        return []

def analyze_with_google_ai(economic_data, news_list, user_assets):
    """使用 Google AI Studio (Gemini) 進行分析，並處理額度用盡的狀況。"""
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("❌ 錯誤：找不到 GEMINI_API_KEY 環境變數。")
            return None

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash-latest')

        # --- [v2.2.1 錯誤修正] ---
        # 建立 prompt 前，先將傳入的結構化數據，轉換為 prompt 所需的純文字格式。
        
        # 1. 處理宏觀經濟數據
        economic_data_text = ""
        if economic_data:
            lines = []
            for item in economic_data:
                # 確保 values 存在且不為空
                if item.get('values'):
                    latest_point = item['values'][-1]
                    lines.append(f"- {item.get('event', '未知指標')}: 最新數據為 {latest_point.get('value', 'N/A')} (日期: {latest_point.get('date', 'N/A')})")
            economic_data_text = "\n".join(lines)
        
        if not economic_data_text:
            economic_data_text = "今日無關鍵宏觀數據。"

        # 2. 處理市場新聞
        news_text = ""
        if news_list:
            # 使用 list comprehension 和 str.join 提高效率，最多處理15條新聞
            lines = [f"{i}. {news.get('title', '無標題新聞')}" for i, news in enumerate(news_list[:15], 1)]
            news_text = "\n".join(lines)
            
        if not news_text:
            news_text = "今日無相關市場新聞。"
        
        # 3. 處理用戶持倉 (將傳入的參數賦值給 prompt 中使用的變數)
        asset_symbols = user_assets
        # --- [修正結束] ---

        prompt = f"""
        你的角色是一位頂尖的宏觀經濟學家與投資策略師。請嚴格根據以下[主要客觀數據]的「趨勢變化」，並酌情參考[輔助市場新聞]，為用戶的投資組合提供一份簡潔、客觀、數據驅動的今日市場洞察。

        [主要客觀數據]
        {economic_data_text}

        [輔助市場新聞]
        {news_text}

        [用戶持倉]
        {', '.join(asset_symbols) if asset_symbols else '無特定持倉'}

        請依據以上所有資訊，提供一份嚴格遵循以下格式的 JSON 報告：
        {{
          "market_summary": "基於今日數據「趨勢」的整體市場情緒總結（例如：PMI數據趨勢向上，顯示擴張動能增強，但初領失業金人數趨勢向下，顯示就業市場依然強勁，可能限制降息預期，市場情緒複雜）。",
          "key_takeaways": [
            {{
              "type": "數據洞見",
              "content": "從今天最重要的1-2個數據的「趨勢」中，提煉出的核心洞見。例如：核心PCE年增率連續三個月放緩，通膨壓力趨勢性下降。",
              "source": "FRED API"
            }},
            {{
              "type": "新聞洞見",
              "content": "從今天最相關的1-2條新聞中，提煉出的核心洞見。",
              "source": "新聞來源網站名"
            }}
          ],
          "portfolio_impact": "綜合所有資訊，對用戶的整體投資組合（特別是提到的持倉）的潛在影響分析（正面/負面/中性）。"
        }}
        """

        response = model.generate_content(prompt)
        raw_response = response.text
        
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', raw_response, re.DOTALL)
        if json_match:
            cleaned_response = json_match.group(1)
        else:
            cleaned_response = raw_response

        return json.loads(cleaned_response)

    except exceptions.ResourceExhausted as e:
        print(f"🟡 警告：Google AI Studio 免費額度可能已用盡。錯誤訊息: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失敗：模型回傳的格式不正確。原始回傳內容: {raw_response}")
        return None
    except Exception as e:
        print(f"❌ 在呼叫 Google AI 時發生未預期錯誤: {e}")
        return None

# --- Cloud Function 主執行函數 ---
@functions_framework.cloud_event
def analyze_and_update_news(cloud_event):
    """[v2.2.1] 由 Pub/Sub 觸發，整合宏觀數據與新聞，為所有用戶生成洞見。"""
    print("--- AI 智慧引擎 v2.2.1 (Gemini 修正版) 開始執行 ---")
    db = firestore.client()
    
    # 1. 抓取新聞來源
    finance_rss_urls = [
        "https://www.macromicro.me/rss/cn/research",
        "https://technews.tw/feed/",
        "https://feeds.bloomberg.com/bview/rss.xml",
        "https://news.google.com/rss/search?q=when:1d+台股&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=when:1d+美股&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    ]
    raw_news_list = get_finance_news_from_rss(finance_rss_urls)
    
    # 2. 抓取最新的宏觀經濟數據
    latest_economic_data = get_latest_economic_data(db)

    # 3. 遍歷所有用戶
    users_ref = db.collection('users')
    for user_doc in users_ref.stream():
        user_id = user_doc.id
        print(f"  > 正在為用戶 {user_id} 進行綜合分析...")
        assets_ref = user_doc.reference.collection('assets')
        asset_symbols = [asset.to_dict().get('代號') for asset in assets_ref.stream() if asset.to_dict().get('代號')]
        print(f"  > 用戶持倉: {asset_symbols}")
        
        # 4. 呼叫 AI 進行綜合分析
        ai_result = analyze_with_google_ai(latest_economic_data, raw_news_list, asset_symbols)
        
        # 5. 將結果寫入 Firestore
        if ai_result:
            doc_id = datetime.datetime.now().strftime("%Y-%m-%d")
            insight_doc_ref = db.collection('users').document(user_id).collection('daily_insights').document(doc_id)
            insight_doc_ref.set({
                "date": firestore.SERVER_TIMESTAMP,
                "insight_data": ai_result 
            })
            print(f"  > ✅ 用戶 {user_id} 的每日洞見已成功更新。")
        else:
            print(f"  > ⚠️ 未能為用戶 {user_id} 生成有效的 AI 分析結果。")
            
    print("--- 所有用戶每日洞見分析完畢 ---")
    return "OK"