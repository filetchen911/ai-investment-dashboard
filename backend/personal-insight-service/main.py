# file: personal-insight-service/main.py

import datetime
import pytz
import firebase_admin
from firebase_admin import firestore
import functions_framework
from _version import __version__

# --- 初始化 ---
try:
    firebase_admin.initialize_app()
    print(f"✅ Firebase Admin SDK 初始化成功 (版本: {__version__})")
except ValueError:
    print(f"ℹ️ Firebase App 已被初始化，跳過。")


def generate_simple_impact_text(market_summary, asset_types):
    """
    [v5.2.0 核心邏輯] 基於規則的輕量級個人影響分析。
    完全不使用 AI，僅根據市場總結的關鍵字和用戶持倉類型來產生建議。
    """
    impact_keywords = {
        "正面": ["樂觀", "強勁", "增長", "優於預期", "上漲", "擴張", "降溫", "放緩"],
        "負面": ["悲觀", "疲軟", "衰退", "低於預期", "下跌", "緊縮", "擔憂", "風險", "高於預期"],
    }
    
    summary_lower = market_summary.lower()
    sentiment = "中性" # 預設為中性

    if any(keyword in summary_lower for keyword in impact_keywords["正面"]):
        sentiment = "正面"
    elif any(keyword in summary_lower for keyword in impact_keywords["負面"]):
        sentiment = "負面"

    # 針對不同資產類別產生不同文字
    has_stock = any(cat in asset_types for cat in ["股票", "美股", "台股", "ETF"])
    has_bond = any(cat in asset_types for cat in ["債券"])
    has_crypto = any(cat in asset_types for cat in ["加密貨幣"])

    if has_stock and sentiment == "正面":
        return "市場普遍的樂觀情緒，或通膨降溫的訊號，可能對您持有的股票/ETF部位帶來正面助益。"
    if has_stock and sentiment == "負面":
        return "市場的擔憂情緒，或高於預期的通膨/就業數據，可能對您持有的股票/ETF部位帶來短期壓力，請留意風險。"
    
    # 您可以繼續添加針對債券、加密貨幣等的規則...

    return "綜合評估，今日的市場狀況對您的整體投資組合影響偏向中性，建議持續觀察。"


@functions_framework.http
def generate_personal_insight(request):
    """
    [v5.2.0] 由前端 HTTP 請求觸發，為單一用戶組合個人化分析報告。
    """
    print(f"--- 個人化分析組合服務 (v{__version__}) 開始執行 ---")
    
    # 1. 從請求中獲取 user_id
    request_json = request.get_json(silent=True)
    if not request_json or 'user_id' not in request_json:
        return {"status": "error", "version": __version__, "message": "請求中缺少 user_id"}, 400
    
    user_id = request_json['user_id']
    print(f"  > 正在為用戶 {user_id} 產生報告...")

    try:
        db = firestore.client()
        taipei_tz = pytz.timezone('Asia/Taipei')
        doc_id = datetime.datetime.now(taipei_tz).strftime("%Y-%m-%d")

        # 2. 讀取已存在的「通用市場分析」快取
        general_doc_ref = db.collection('general_analysis').document(doc_id)
        general_analysis_doc = general_doc_ref.get()
        if not general_analysis_doc.exists:
            return {"status": "error", "version": __version__, "message": f"找不到當日的通用市場分析，請先觸發通用分析。"}, 404
        
        general_data = general_analysis_doc.to_dict()

        # 3. 獲取用戶的資產類型
        assets_ref = db.collection('users').document(user_id).collection('assets')
        # 使用 set 來自動去除重複的類型
        asset_types = set(asset.to_dict().get('類型') for asset in assets_ref.stream() if asset.to_dict().get('類型'))
        
        # 4. 產生輕量級的個人化影響分析 (Rule-based)
        portfolio_impact_text = generate_simple_impact_text(general_data.get('market_summary', ''), asset_types)

        # 5. 組合最終報告
        final_insight_data = {
            "market_summary": general_data.get('market_summary', 'N/A'),
            "key_takeaways": general_data.get('key_takeaways', []),
            "portfolio_impact": portfolio_impact_text,
            "analysis_version": general_data.get('version', 'N/A'), # 記錄是基於哪個版本的通用分析
            "analysis_last_updated": general_data.get('last_updated') # 記錄通用分析的時間
        }

        # 6. 將結果寫入使用者的子集合
        insight_doc_ref = db.collection('users').document(user_id).collection('daily_insights').document(doc_id)
        insight_doc_ref.set({
            "date": firestore.SERVER_TIMESTAMP,
            "insight_data": final_insight_data
        })
        
        print(f"✅ 用戶 {user_id} 的個人化報告已成功寫入 Firestore。")
        
        # --- [v5.2.0-rc7 修正] ---
        # 準備回傳給前端的資料，不能包含 Timestamp 物件
        response_data = final_insight_data.copy()
        
        # 檢查 'analysis_last_updated' 欄位是否存在且可被轉換
        if 'analysis_last_updated' in response_data and hasattr(response_data['analysis_last_updated'], 'isoformat'):
            response_data['analysis_last_updated'] = response_data['analysis_last_updated'].isoformat()
            
        return {"status": "success", "version": __version__, "user_id": user_id, "data": response_data}, 200
        # --- [修正結束] ---

    except Exception as e:
        print(f"❌ 函式執行時發生嚴重錯誤: {e}")
        return {"status": "error", "version": __version__, "message": str(e)}, 500