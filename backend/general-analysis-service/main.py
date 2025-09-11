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

# --- 輔助函式 (新聞抓取 & 數據引擎) ---
def get_finance_news_from_rss(rss_urls, keywords):
    """
    [v5.5.4 優化] 從 RSS 抓取新聞，並根據關鍵字進行排序，提升相關性。
    """
    print("  > [News Engine v2.0] 開始抓取並過濾 RSS 新聞...")
    all_news = []
    seen_links = set()

    for rss_url in rss_urls:
        try:
            feed = feedparser.parse(rss_url)
            source_name = feed.feed.get('title', 'Unknown Source')
            for entry in feed.entries[:10]: # 稍微多抓一點作為篩選基數
                if entry.link not in seen_links:
                    all_news.append({
                        "title": entry.get('title', 'No Title'),
                        "link": entry.get('link'),
                        "source": source_name
                    })
                    seen_links.add(entry.link)
        except Exception as e:
            print(f"    - 錯誤：從 {rss_url} 獲取新聞時發生錯誤: {e}")

    # 根據關鍵字進行排序
    # 標題中包含關鍵字的新聞，其 'priority' 會是 0，否則為 1，排序時會被排在前面
    for news in all_news:
        news['priority'] = 1
        for keyword in keywords:
            if keyword.lower() in news['title'].lower():
                news['priority'] = 0
                break # 只要匹配到一個關鍵字就給予高優先級

    sorted_news = sorted(all_news, key=lambda x: x['priority'])
    
    print(f"  > [News Engine v2.0] 總共抓取 {len(all_news)} 條，篩選排序後回傳。")
    return sorted_news

def get_latest_model_data(db_client):
    # 此函式已有診斷日誌，保持不變，以便追蹤
    print("  > [Data Engine v2.1-Debug] 正在從 Firestore 獲取最新的模型數據...")
    try:
        # --- [診斷日誌 1] ---
        # 印出 Firestore client 物件，它包含了 project 和 database 的資訊
        print(f"  > [Debug Info] Firestore Client: {db_client}")

        taipei_tz = pytz.timezone('Asia/Taipei')
        doc_id = datetime.datetime.now(taipei_tz).strftime("%Y-%m-%d")
        
        # --- [診斷日誌 2] ---
        # 印出我們正在嘗試讀取的文件路徑
        print(f"  > [Debug Info] Attempting to fetch document from path: daily_model_data/{doc_id}")

        doc_ref = db_client.collection('daily_model_data').document(doc_id)
        doc = doc_ref.get()

        # --- [診斷日誌 3] ---
        # 印出 get() 操作的結果
        print(f"  > [Debug Info] doc.exists for today's document: {doc.exists}")

        if doc.exists:
            print(f"  > [Data Engine v2.1-Debug] 成功獲取到今日 ({doc_id}) 的模型數據。")
            return doc.to_dict()
        else:
            # 如果今天的不存在，繼續執行備用方案
            print(f"  > [Data Engine v2.1-Debug] 未找到今日數據，嘗試讀取最新一份...")
            query = db_client.collection('daily_model_data').order_by('updated_at', direction=firestore.Query.DESCENDING).limit(1)
            docs = list(query.stream())
            if docs:
                print(f"  > [Data Engine v2.1-Debug] 成功讀取到歷史最新數據: {docs[0].id}")
                return docs[0].to_dict()
            
            # --- [診斷日誌 4] ---
            # 如果連備用方案都找不到，也印出來
            print(f"  > [Debug Info] Fallback query also found no documents.")
            return None
    except Exception as e:
        print(f"  > [Data Engine v2.1-Debug] 獲取模型數據時發生嚴重錯誤: {e}")
        return None

def analyze_market_with_models(model_data_raw, news_list):
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("錯誤：找不到 GEMINI_API_KEY 環境變數。")

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash-latest')

        model_data = model_data_raw.get('data', {})
        if not model_data:
            # 如果連 'data' 這個主欄位都沒有，就拋出錯誤
            raise ValueError("Firestore 文件中缺少 'data' 主欄位，無法解析模型數據。")

        def safe_format(value, format_spec):
            """如果 value 是數字則格式化，否則直接回傳原始值(通常是'N/A')"""
            if isinstance(value, (int, float)):
                return f"{value:{format_spec}}"
            return value

        tech_model = model_data.get('tech_model', {})
        j_vix_model = model_data.get('j_vix_model', {})
        scores = tech_model.get('scores_breakdown', {})
        
        tech_model_score = tech_model.get('total_score', 'N/A')
        tech_model_scenario = tech_model.get('scenario', 'N/A')
        tech_model_scenario_details = tech_model.get('scenario_details', 'N/A')
        tech_model_action = tech_model.get('action', 'N/A')
        tech_model_position = tech_model.get('position', 'N/A')

        mag7_revenue = scores.get('Mag7營收年增率', {})
        capex_growth = scores.get('資本支出增長率', {})
        leading_indicators = scores.get('關鍵領先指標', {})
        gdp = scores.get('GDP季增率', {})
        ism_pmi = scores.get('ISM製造業PMI', {})
        consumption = scores.get('美國消費需求綜合', {})
        liquidity = scores.get('資金面與流動性', {})

        latest_vix = j_vix_model.get('latest_vix', 'N/A')
        sp500_signals = j_vix_model.get('signals', {}).get('標普500指數', {})
        sp500_mid_term_signal = sp500_signals.get('mid_term_pullback', False)
        sp500_inventory_cycle_signal = sp500_signals.get('inventory_cycle', False)

        news_text = "\n".join([f"- [{news.get('source', '未知來源')}] {news.get('title', '無標題新聞')}" for news in news_list[:15]]) or "..."
        # --- 步驟 2: 建立專家級 Prompt (使用 safe_format) ---
        prompt = f"""
        你的角色是一位頂尖的量化策略師與宏觀經濟學家，任職於一家專注於科技股的避險基金。你的任務是為內部投資委員會撰寫每日市場分析報告。

        你的分析**主要依據**必須是`[結構化模型數據]`，你可以使用`[輔助市場新聞]`來為你的數據洞見**提供額外的背景或佐證**，但新聞本身不應構成你核心結論的主要驅動力。禁止使用任何外部知識，所有論點必須源自下方提供的資料。

        [結構化模型數據]
        1.  **科技股總經模型 (Tech Model):**
            -   **綜合評分:** {safe_format(tech_model_score, '.1f')} / 100
            -   **當前情境:** "{tech_model_scenario}"
            -   **情境解讀:** "{tech_model_scenario_details}"
            -   **建議行動:** "{tech_model_action}"
            -   **建議倉位:** "{tech_model_position}"
        2.  **模型核心驅動因子 (細項分數):**
            -   **企業基本面 (滿分50):**
                -   Mag7 營收年增率: {mag7_revenue.get('score', 'N/A')} 分 ({mag7_revenue.get('value', 'N/A')})
                -   資本支出增長率: {capex_growth.get('score', 'N/A')} 分 ({capex_growth.get('value', 'N/A')})
            -   **總體經濟 (滿分20):**
                -   關鍵領先指標綜合: {leading_indicators.get('score', 'N/A')} 分
                -   GDP 季增率: {gdp.get('score', 'N/A')} 分 ({gdp.get('value', 'N/A')})
                -   ISM 製造業 PMI: {ism_pmi.get('score', 'N/A')} 分 ({ism_pmi.get('value', 'N/A')})
                -   美國消費需求綜合: {safe_format(consumption.get('score', 'N/A'), '.1f')} 分
            -   **資金流動性 (滿分10):**
                -   資金面綜合: {liquidity.get('score', 'N/A')} 分 ({liquidity.get('value', 'N/A')})
        3.  **逆勢擇時模型 (J-VIX Model):**
            -   **最新 VIX 指數:** {safe_format(latest_vix, '.2f')}
            -   **標普500指數 (S&P 500) 訊號:**
                -   中期回檔訊號 (週線級別): {'觸發' if sp500_mid_term_signal else '未觸發'}
                -   庫存週期訊號 (月線級別): {'觸發' if sp500_inventory_cycle_signal else '未觸發'}

        [輔助市場新聞]
        {news_text}

        請嚴格遵循以下 JSON 格式，生成今日的分析報告：
        {{
          "report_title": "一句話總結今天的市場核心主題",
          "overall_sentiment": "根據模型總分與情境，判斷整體市場情緒是「樂觀」、「謹慎樂觀」、「中性」、「謹慎悲觀」或「悲觀」",
          "analysis_summary": "一段約150字的摘要，闡述模型分數背後的意義。說明目前是基本面、總經還是資金面在主導市場，並點出最重要的趨勢。",
          "positive_factors": [
            {{
              "factor": "最強勁的支撐因子名稱 (例如：企業資本支出強勁)",
              "evidence": "從[結構化模型數據]中引用具體數據來支持此論點 (例如：資本支出增長率分數高達20分，對應的年增率為64.80%)",
              "implication": "這個數據對市場的正面影響是什麼 (例如：這表明科技巨頭對未來充滿信心，願意大舉投資，有利於產業鏈上游與長期增長)"
            }}
          ],
          "risk_factors": [
            {{
              "factor": "最主要的潛在風險因子名稱 (例如：製造業景氣疲軟)",
              "evidence": "從[結構化模型數據]中引用具體數據來支持此論點 (例如：ISM製造業PMI分數僅2分，指數值為48.7，連續處於收縮區間)",
              "implication": "這個數據對市場的潛在負面影響是什麼 (例如：這可能拖累實體經濟與企業的非科技部門，若趨勢惡化可能影響整體就業與消費信心)"
            }}
          ],
          "investment_conclusion": "綜合所有資訊，給出最終的投資策略結論。重申模型的建議行動與倉位，並提醒投資人應該關注的下一個關鍵數據或事件。"
        }}
        """

        # --- [偵錯] 新增日誌紀錄 ---
        print("-" * 50)
        print(">>> 即將傳送給 AI 的完整 Prompt 內容：")
        print(prompt)
        print("--- END OF PROMPT ---")
        print("-" * 50)
        # --- [偵錯] 新增結束 ---

        response = model.generate_content(prompt)
        raw_response = response.text
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', raw_response, re.DOTALL)
        cleaned_response = json_match.group(1) if json_match else raw_response
        return json.loads(cleaned_response)

    except Exception as e:
        print(f"❌ 在呼叫 Google AI 時發生錯誤: {e}")
        raise

@functions_framework.http
def generate_general_analysis(request):
    """由前端 HTTP 請求觸發的通用市場分析主函式"""
    print(f"--- 通用市場分析服務 (v{__version__}) 開始執行 ---")
    db = firestore.client()
    doc_id = datetime.datetime.now(pytz.timezone('Asia/Taipei')).strftime("%Y-%m-%d")
    doc_ref = db.collection('general_analysis').document(doc_id)

    # --- 智慧快取檢查 ---
    try:
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            last_updated_utc = data.get('last_updated').replace(tzinfo=pytz.UTC)
            now_utc = datetime.datetime.now(pytz.UTC)
            if (now_utc - last_updated_utc).total_seconds() / 3600 < FRESHNESS_THRESHOLD_HOURS:
                print(f"✅ 快取命中：找到 {FRESHNESS_THRESHOLD_HOURS} 小時內的新鮮報告。")
                return {"status": "success_from_cache", "version": data.get('version', __version__), "doc_id": doc_id, "data": data}, 200
            else:
                print(f"🟡 快取過時：找到今日報告，但已超過 {FRESHNESS_THRESHOLD_HOURS} 小時。")
        else:
            print(f"ℹ️ 快取未命中：今日尚無分析報告。")
    except Exception as e:
        print(f"⚠️ 讀取快取時發生錯誤: {e}。")
    # --- 新報告產生流程 ---
    try:
        print("  > [新報告產生流程] 開始抓取數據...")

        # [優化二] 定義新聞過濾關鍵字
        news_keywords = [
            "Fed", "聯準會", "FOMC", "利率", "通膨", "CPI", "PCE", "PMI", "GDP", "財報",
            "NVIDIA", "輝達", "AVGO", "博通", "蘋果", "台積電", "TSMC", "半導體", "AI", "晶片", "伺服器",
            "台股", "美股", "納斯達克", "NASDAQ"
        ]

        # 2. 取得上一個月份來產生動態關鍵字
        #    財政部通常在每月7-10號公布上個月的出口數據，因此我們總是關注上一個月的出口新聞。
        today = datetime.date.today()
        #    一個簡單可靠的回推月份方式是減去約15天，確保日期必定落在上一個月
        last_month_date = today - datetime.timedelta(days=15)
        last_month_number = last_month_date.month

        dynamic_keyword = f"台灣{last_month_number}月出口"

        # 3. 將動態關鍵字加入到列表中
        news_keywords.append(dynamic_keyword)
        
        # (可選) 在日誌中印出，方便我們驗證
        print(f"  > [News Engine v2.1] 動態加入新聞關鍵字: '{dynamic_keyword}'")

        rss_urls = [
            "https://feeds.bloomberg.com/technology/news.rss",  # 彭博科技（正常運作）
            "https://finance.yahoo.com/rss/topstories",        # Yahoo Finance 財經頭條
            "https://tw.news.yahoo.com/rss/finance", #Yahoo財經
            "https://news.google.com/rss/search?q=site:reuters.com+business&hl=en&gl=US&ceid=US:en",  # 路透商業（透過Google News）
            "https://news.google.com/rss/search?q=台股+OR+台灣股市&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",      # 透過Google News搜索台股相關新聞
            "https://news.google.com/rss/search?q=site:tw.stock.yahoo.com&hl=zh-TW&gl=TW&ceid=TW:zh-Hant", #Google News的方式來獲取Yahoo奇摩股市新聞
            "https://feeds.feedburner.com/rsscna/finance",  # 中央社產經證券
            "https://feeds.marketwatch.com/marketwatch/marketpulse/"  # MarketWatch美股新聞
        ]
        raw_news_list = get_finance_news_from_rss(rss_urls, news_keywords)
        
        latest_model_data = get_latest_model_data(db)
        if not latest_model_data:
            return {"status": "error", "message": "無法從 Firestore 獲取任何有效的模型數據，分析無法進行。"}, 500

        print("  > [新報告產生流程] 呼叫 Google AI 進行深度分析...")
        general_analysis_result = analyze_market_with_models(latest_model_data, raw_news_list)
        if not general_analysis_result:
             return {"status": "error", "message": "未能生成有效的 AI 分析結果。"}, 500

        print("  > [新報告產生流程] 準備將結果寫入 Firestore...")
        expire_at_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)
        data_for_firestore = {
            "last_updated": firestore.SERVER_TIMESTAMP,
            "expireAt": expire_at_time,
            "version": __version__,
            **general_analysis_result
        }
        doc_ref.set(data_for_firestore)
        print(f"✅ [新報告] 通用市場分析結果已成功寫入 Firestore: {doc_id}")

        response_data = data_for_firestore.copy()
        response_data['last_updated'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        response_data['expireAt'] = expire_at_time.isoformat()
        
        return {"status": "success_newly_generated", "version": __version__, "doc_id": doc_id, "data": response_data}, 200

    except Exception as e:
        print(f"❌ 函式執行時發生嚴重錯誤: {e}")
        return {"status": "error", "version": __version__, "message": str(e)}, 500