import os
import json
import re
import datetime
import pytz
import firebase_admin
from firebase_admin import firestore
import google.generativeai as genai
from google.api_core import exceptions
import feedparser
import functions_framework
from _version import __version__ # [版本號] 引入版本號

# --- 常數設定 ---
FRESHNESS_THRESHOLD_HOURS = 4 # 快取有效時長（小時）

# --- 初始化 ---
try:
    firebase_admin.initialize_app()
    print("✅ Firebase Admin SDK 初始化成功。")
except ValueError:
    print("ℹ️ Firebase App 已被初始化，跳過。")

def get_finance_news_from_rss(rss_urls):
    # ... (此輔助函數邏輯與先前版本相同) ...
    print("  > [News Engine] 開始抓取 RSS 新聞...")
    all_news = []
    for rss_url in rss_urls:
        try:
            feed = feedparser.parse(rss_url)
            source_name = feed.feed.title if hasattr(feed.feed, 'title') else 'Unknown Source'
            for entry in feed.entries[:7]:
                if entry.title and entry.link and entry.link not in [n['link'] for n in all_news]:
                    all_news.append({"title": entry.title, "link": entry.link, "source": source_name})
        except Exception as e:
            print(f"    - 錯誤：從 {rss_url} 獲取新聞時發生錯誤: {e}")
    print(f"  > [News Engine] 總共從 RSS 抓取到 {len(all_news)} 條新聞。")
    return all_news

def get_latest_economic_data(db_client):
    # ... (此輔助函數邏輯與先前版本相同) ...
    print("  > [Data Engine] 正在從 Firestore 獲取宏觀數據...")
    try:
        query = db_client.collection('daily_economic_data').order_by('date', direction=firestore.Query.DESCENDING).limit(1)
        docs = list(query.stream())
        if docs:
            print("  > [Data Engine] 成功獲取到宏觀經濟數據。")
            return docs[0].to_dict().get('data_series_items', [])
        print("  > [Data Engine] 在 Firestore 中未找到宏觀經濟數據。")
        return []
    except Exception as e:
        print(f"  > [Data Engine] 獲取經濟數據時發生錯誤: {e}")
        return []

def analyze_general_market_with_google_ai(economic_data, news_list):
    # ... (此輔助函數經改造，不再需要 user_assets) ...
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("錯誤：找不到 GEMINI_API_KEY 環境變數。")

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash-latest')

        # 將傳入的數據轉換為純文字
        economic_data_text = "\n".join([f"- {item.get('event', '未知指標')}: 最新數據為 {item['values'][-1]['value']} (日期: {item['values'][-1]['date']})" for item in economic_data if item.get('values')]) or "今日無關鍵宏觀數據。"
        news_text = "\n".join([f"{i}. {news.get('title', '無標題新聞')}" for i, news in enumerate(news_list[:15], 1)]) or "今日無相關市場新聞。"

        # [改造] Prompt 移除了所有個人化相關的區塊
        prompt = f"""
        你的角色是一位頂尖的宏觀經濟學家與投資策略師。請嚴格根據以下[主要客觀數據]的「趨勢變化」，並酌情參考[輔助市場新聞]，提供一份簡潔、客觀、數據驅動的今日市場洞察。

        [主要客觀數據]
        {economic_data_text}

        [輔助市場新聞]
        {news_text}

        請依據以上所有資訊，提供一份嚴格遵循以下格式的 JSON 報告：
        {{
          "market_summary": "基於今日數據「趨勢」的整體市場情緒總結。",
          "key_takeaways": [
            {{
              "type": "數據洞見",
              "content": "從今天最重要的1-2個數據的「趨勢」中，提煉出的核心洞見。",
              "source": "FRED API"
            }},
            {{
              "type": "新聞洞見",
              "content": "從今天最相關的1-2條新聞中，提煉出的核心洞見。",
              "source": "新聞來源網站名"
            }}
          ]
        }}
        """

        response = model.generate_content(prompt)
        raw_response = response.text
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', raw_response, re.DOTALL)
        cleaned_response = json_match.group(1) if json_match else raw_response
        return json.loads(cleaned_response)

    except Exception as e:
        print(f"❌ 在呼叫 Google AI 時發生錯誤: {e}")
        # 將錯誤回傳，以便 HTTP 響應能反映出來
        raise

@functions_framework.http
def generate_general_analysis(request):
    """
    [v5.2.0] 由前端 HTTP 請求觸發，內含智慧快取檢查。
    """
    print(f"--- 通用市場分析服務 (v{__version__}) 開始執行 ---")
    db = firestore.client()
    doc_id = datetime.datetime.now(pytz.timezone('Asia/Taipei')).strftime("%Y-%m-%d")
    doc_ref = db.collection('general_analysis').document(doc_id)

    # --- [v5.2.0 智慧快取檢查] ---
    try:
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            last_updated_utc = data.get('last_updated').replace(tzinfo=pytz.UTC) # 確保時間是 UTC aware
            now_utc = datetime.datetime.now(pytz.UTC)
            time_difference = now_utc - last_updated_utc
            
            if time_difference.total_seconds() / 3600 < FRESHNESS_THRESHOLD_HOURS:
                print(f"✅ 快取命中：找到 {FRESHNESS_THRESHOLD_HOURS} 小時內的新鮮報告。直接回傳快取內容。")
                return {"status": "success_from_cache", "version": __version__, "doc_id": doc_id, "data": data}, 200
            else:
                print(f"🟡 快取過時：找到今日報告，但已超過 {FRESHNESS_THRESHOLD_HOURS} 小時。繼續執行以產生新報告。")
        else:
            print(f"ℹ️ 快取未命中：今日尚無分析報告。繼續執行以產生新報告。")
            
    except Exception as e:
        print(f"⚠️ 讀取快取時發生錯誤: {e}。繼續執行以產生新報告。")
    # --- [檢查結束] ---

    try:
        # 1. 抓取通用數據 (新聞 & 經濟指標)
        # [修正] 採用您指定的完整新聞來源列表
        print("  > [新報告產生流程] 開始抓取通用數據...")
        rss_urls = [
            "https://www.macromicro.me/rss/cn/research", "https://technews.tw/feed/",
            "https://feeds.bloomberg.com/bview/rss.xml",
            "https://news.google.com/rss/search?q=when:1d+台股&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
            "https://news.google.com/rss/search?q=when:1d+美股&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        ]

        raw_news_list = get_finance_news_from_rss(rss_urls)
        latest_economic_data = get_latest_economic_data(db)

        # 2. 呼叫 AI 進行一次性的通用分析
        print("  > [新報告產生流程] 呼叫 Google AI 進行分析...")
        general_analysis_result = analyze_general_market_with_google_ai(latest_economic_data, raw_news_list)

        if not general_analysis_result:
             return {"status": "error", "message": "未能生成有效的 AI 分析結果。"}, 500

        # 3. 為產生的結果加上 TTL 到期時間與版本號
        print("  > [新報告產生流程] 準備將結果寫入 Firestore...")
        # 準備寫入 Firestore 的資料
        expire_at_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)
        data_for_firestore = {
            "last_updated": firestore.SERVER_TIMESTAMP, # <-- 包含 Sentinel
            "expireAt": expire_at_time, # <-- 包含 datetime 物件
            "version": __version__,
            **general_analysis_result # 解構 AI 分析結果
        }

        # 將包含特殊物件的資料寫入 Firestore
        doc_ref.set(data_for_firestore)

        
        print(f"✅ [新報告] 通用市場分析結果已成功寫入 Firestore: {doc_id}")

        # --- [v5.2.0-rc6 修正] ---
        # 準備一個「乾淨」的版本回傳給前端
        response_data = data_for_firestore.copy()
        
        # 將 Firestore Sentinel 和 datetime 物件轉換為 JSON 相容的 ISO 格式字串
        response_data['last_updated'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        response_data['expireAt'] = expire_at_time.isoformat()
        
        return {"status": "success_newly_generated", "version": __version__, "doc_id": doc_id, "data": response_data}, 200
        # --- [修正結束] ---

    except Exception as e:
        print(f"❌ 函式執行時發生嚴重錯誤: {e}")
        return {"status": "error", "version": __version__, "message": str(e)}, 500