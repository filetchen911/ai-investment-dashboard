# quote-function/main.py (v2.5 - 修正前日報價)

import firebase_admin
from firebase_admin import firestore, credentials
import yfinance as yf
import requests
import functions_framework
import logging
import sys

# --- 初始化 ---
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

try:
    firebase_admin.initialize_app()
except ValueError:
    logging.info("Firebase App 已被初始化，跳過。")

db = firestore.client()


def get_price(symbol, asset_type, currency="USD"):
    price_data = {"price": None, "previous_close": None}  
    try:
        asset_type_lower = asset_type.lower()
        
        # 準備要嘗試的代號列表
        symbols_to_try = [symbol.strip().upper()]
        if asset_type_lower in ["台股", "債券"]:
            clean_symbol = symbol.strip().upper()
            # 只對純數字的代號嘗試後綴
            if not (clean_symbol.endswith(".TW") or clean_symbol.endswith(".TWO")):
                symbols_to_try = [f"{clean_symbol}.TW", f"{clean_symbol}.TWO"]

        
        logging.info(f"  > [報價引擎] 準備為 '{symbol}' ({asset_type}) 嘗試的代號列表: {symbols_to_try}")

        # 遍歷嘗試列表
        for s in symbols_to_try:
            try:
                if asset_type_lower == "現金":
                     return {"price": 1.0, "previous_close": 1.0}
                
                if asset_type_lower in ["美股", "台股", "債券", "其他", "股票", "etf"]:
                    ticker = yf.Ticker(s)
                    # 優先使用 .info 獲取數據，更穩定
                    info = ticker.info
                    
                    current_price = info.get('currentPrice', info.get('regularMarketPrice'))
                    previous_close = info.get('previousClose')

                    # 如果 .info 中沒有數據，則退回使用 .history
                    if current_price is None or previous_close is None:
                        logging.warning(f"    - .info 中找不到 {s} 的數據，退回使用 .history()")
                        hist = ticker.history(period="2d")
                        if not hist.empty:
                            current_price = hist['Close'].iloc[-1]
                            previous_close = hist['Close'].iloc[-2] if len(hist) >= 2 else current_price
                    
                    if current_price is not None and previous_close is not None:
                        price_data["price"] = current_price
                        price_data["previous_close"] = previous_close
                        logging.info(f"    - ✅ 使用 {s} 成功抓取到報價: 現價={current_price}, 前日收盤={previous_close}")
                        return price_data
                
                elif asset_type_lower == "加密貨幣":
                    coin_id = s.lower()
                    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies={currency.lower()}"
                    response = requests.get(url).json()
                    if coin_id in response and currency.lower() in response[coin_id]:
                        price = response[coin_id][currency.lower()]
                        price_data = {"price": price, "previous_close": price}
                        return price_data
            except Exception:
                logging.info(f"    - 嘗試 {s} 失敗，繼續...")
                continue
        
        logging.warning(f"  > [警告] 未能從任何代號 {symbols_to_try} 獲取到 {symbol} 的報價。")

    except Exception as e:
        logging.error(f"獲取 {symbol} 報價時發生未知錯誤: {e}")
        
    return price_data if price_data.get("price") is not None else None


def get_all_symbols_from_firestore(db_client):
    """從所有用戶的資產中收集所有獨一無二的資產代號、類型和幣別。"""
    all_symbols_to_fetch = set()
    users_ref = db_client.collection('users')
    for user_doc in users_ref.stream():
        assets_ref = user_doc.reference.collection('assets')
        for asset_doc in assets_ref.stream():
            asset_data = asset_doc.to_dict()
            symbol, asset_type, currency = asset_data.get('代號'), asset_data.get('類型'), asset_data.get('幣別')
            if all([symbol, asset_type, currency]):
                all_symbols_to_fetch.add((symbol, asset_type, currency))
    logging.info(f"總共收集到 {len(all_symbols_to_fetch)} 個獨特資產。")
    return list(all_symbols_to_fetch)


# --- Cloud Function 主執行函數 ---
@functions_framework.cloud_event
def update_all_quotes(cloud_event):
    """[v2.3] 由 Pub/Sub 觸發，更新所有資產的報價，包含前日收盤價。"""
    logging.info("--- 報價更新服務 v2.3 (智慧後綴版) 開始執行 ---")
    
    symbols_to_fetch = get_all_symbols_from_firestore(db)
    
    if not symbols_to_fetch:
        logging.info("沒有資產可供更新，函數執行完畢。")
        return "OK"

    quotes_batch = db.batch()
    quotes_ref = db.collection('general_quotes')
    updated_count = 0
    
    logging.info(f"準備更新 {len(symbols_to_fetch)} 筆資產報價...")
    for symbol, asset_type, currency in symbols_to_fetch:
        price_data = get_price(symbol, asset_type, currency)
        
        if price_data and price_data.get("price") is not None:
            logging.info(f"  > 獲取到報價: {symbol} = {price_data['price']:.2f}")
            
            # 寫入 Firestore 的 Symbol 欄位，依然是使用者輸入的、不含後綴的乾淨代號
            quotes_batch.set(quotes_ref.document(symbol), {
                "Symbol": symbol,
                "Price": round(float(price_data['price']), 4),
                "PreviousClose": round(float(price_data.get('previous_close', 0)), 4),
                "Timestamp": firestore.SERVER_TIMESTAMP
            })
            updated_count += 1

    try:
        quotes_batch.commit()
        success_message = f"成功將 {updated_count} 筆報價更新到 Firestore！"
        logging.info(success_message)
        return success_message
    except Exception as e:
        error_message = f"寫入 Firestore 時發生錯誤: {e}"
        logging.error(error_message)
        raise RuntimeError(error_message) from e