# snapshot-function/main.py (v1.5.2 - 最終定案版)

import os
import datetime
import firebase_admin
from firebase_admin import firestore, credentials
import yfinance as yf
import pandas as pd
import functions_framework
import traceback
import pytz
from _version import __version__

# --- 初始化 Firebase App ---
try:
    firebase_admin.initialize_app()
except ValueError:
    pass

# --- 數據加載與匯率獲取函數 ---
def load_quotes_from_firestore(db_client):
    """從 general_quotes 集合讀取最新報價。"""
    docs = db_client.collection('general_quotes').stream()
    return {doc.id: doc.to_dict().get('Price') for doc in docs if doc.to_dict() and doc.to_dict().get('Price') is not None}

def get_all_user_assets(db_client):
    """獲取所有用戶的所有資產資料。"""
    all_users_assets = {}
    users_ref = db_client.collection('users')
    for user_doc in users_ref.stream():
        user_id = user_doc.id
        assets_ref = user_doc.reference.collection('assets')
        all_users_assets[user_id] = [asset.to_dict() for asset in assets_ref.stream()]
    return all_users_assets

def get_exchange_rate():
    """使用 yfinance 獲取即時匯率。"""
    try:
        ticker = yf.Ticker("USDTWD=X")
        data = ticker.history(period="1d")
        if not data.empty:
            rate = data['Close'].iloc[-1]
            return rate
    except Exception as e:
        print(f"  > [Snapshot] 獲取匯率失敗: {e}")
    return 32.5

# --- [v1.5.2 最終版] Cloud Function 主執行函數 ---
@functions_framework.cloud_event
def create_portfolio_snapshot(cloud_event):
    """[v1.5.2] 基於已有的報價數據和即時匯率，為所有用戶計算總資產並儲存或覆蓋當日快照。"""
    print("--- 每日資產快照服務 v1.5.2 (最終定案版) 開始執行 ---")
    
    try:
        db = firestore.client()
        
        all_users_assets = get_all_user_assets(db)
        live_quotes = load_quotes_from_firestore(db)
        usd_to_twd_rate = get_exchange_rate()

        # [修正] 文件 ID 只使用日期，確保每日唯一
        taipei_tz = pytz.timezone('Asia/Taipei')
        snapshot_doc_id = datetime.datetime.now(taipei_tz).strftime("%Y-%m-%d")
        
        for user_id, assets in all_users_assets.items():
            print(f"  > 正在為用戶 {user_id} 計算資產快照...")
            total_value_twd = 0.0
            
            for asset in assets:
                symbol = asset.get('代號')
                price = live_quotes.get(symbol)
                
                if price is not None:
                    quantity = float(asset.get('數量', 0))
                    currency = asset.get('幣別')
                    market_value = float(price) * quantity
                    
                    if currency in ['USD', 'USDT']:
                        total_value_twd += market_value * usd_to_twd_rate
                    else:
                        total_value_twd += market_value
                else:
                    print(f"    - 警告：找不到資產 {symbol} 的即時報價，本次快照將不計入此資產。")

            # [修正] 儲存路徑和數據內容
            snapshot_ref = db.collection('users').document(user_id).collection('historical_value').document(snapshot_doc_id)
            
            data_to_save = {
                "date": snapshot_doc_id,
                "snapshot_timestamp": firestore.SERVER_TIMESTAMP,
                "total_value_twd": float(round(total_value_twd, 2)) 
            }
            
            # 使用 set() 指令，如果文件已存在，它會自動覆蓋
            snapshot_ref.set(data_to_save)
            print(f"  > ✅ [成功] 用戶 {user_id} 的資產快照已寫入/覆蓋到文件: {snapshot_doc_id}")
        
        print("--- 所有用戶資產快照已建立完畢 ---")
        return "OK"

    except Exception as e:
        print(f"❌ [嚴重錯誤] 執行 create_portfolio_snapshot 時發生未預期錯誤！")
        print(traceback.format_exc())
        raise