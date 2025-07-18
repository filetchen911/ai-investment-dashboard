# utils.py

import streamlit as st
import pandas as pd
import datetime
import os
import requests
import json
import yfinance as yf
import firebase_admin
from firebase_admin import credentials, auth, firestore
import plotly.express as px
import numpy as np
import logging
import sys

APP_VERSION = "v4.0.3 (PreviousClose 修正版)"

# 設定日誌系統
logging.basicConfig(
    stream=sys.stdout, 
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- Firebase 初始化 (使用 @st.cache_resource 確保只執行一次) ---
@st.cache_resource
def init_firebase():
    """初始化 Firebase Admin SDK，並返回 firestore client 和 firebase_config。"""
    try:
        firebase_config = st.secrets["firebase_config"]
        service_account_info = {
            "type": st.secrets.firebase_service_account.type,
            "project_id": st.secrets.firebase_service_account.project_id,
            "private_key_id": st.secrets.firebase_service_account.private_key_id,
            "private_key": st.secrets.firebase_service_account.private_key.replace('\\n', '\n'),
            "client_email": st.secrets.firebase_service_account.client_email,
            "client_id": st.secrets.firebase_service_account.client_id,
            "auth_uri": st.secrets.firebase_service_account.auth_uri,
            "token_uri": st.secrets.firebase_service_account.token_uri,
            "auth_provider_x509_cert_url": st.secrets.firebase_service_account.auth_provider_x509_cert_url,
            "client_x509_cert_url": st.secrets.firebase_service_account.client_x509_cert_url,
            "universe_domain": st.secrets.firebase_service_account.universe_domain
        }
        if not firebase_admin._apps:
            cred = credentials.Certificate(service_account_info)
            firebase_admin.initialize_app(cred)
        
        return firestore.client(), firebase_config
    except Exception as e:
        st.error("⚠️ Secrets 配置錯誤或 Firebase 初始化失敗。")
        st.error(f"詳細錯誤: {e}")
        st.stop()

# --- [v4.0.3 重大修改] 後端邏輯函數 ---
def get_price(symbol, asset_type, currency="USD"):
    price_data = {"price": None, "previous_close": None}
    try:
        asset_type_lower = asset_type.lower()
        
        symbols_to_try = [symbol.strip().upper()]
        if asset_type_lower in ["台股", "債券"]:
            clean_symbol = symbol.strip().upper()
            if not (clean_symbol.endswith(".TW") or clean_symbol.endswith(".TWO")):
                symbols_to_try = [f"{clean_symbol}.TW", f"{clean_symbol}.TWO"]
        
        logging.info(f"  [報價引擎] 準備為 '{symbol}' ({asset_type}) 嘗試的代號列表: {symbols_to_try}")

        for s in symbols_to_try:
            try:
                logging.info(f"    --- 正在嘗試代號: {s} ---")
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
                    # ... (加密貨幣邏輯不變)
            except Exception:
                logging.info(f"    嘗試 {s} 失敗，繼續...")
                continue

    except Exception as e:
        logging.error(f"獲取 {symbol} ({asset_type}) 報價時出錯: {e}")
        
    return price_data if price_data.get("price") is not None else None

def update_quotes_manually():
    db_client, _ = init_firebase()
    all_symbols_to_fetch = set()
    users_ref = db_client.collection('users')
    for user_doc in users_ref.stream():
        assets_ref = user_doc.reference.collection('assets')
        for asset_doc in assets_ref.stream():
            asset_data = asset_doc.to_dict()
            if asset_data.get('代號') and asset_data.get('類型') and asset_data.get('幣別'):
                all_symbols_to_fetch.add((asset_data['代號'], asset_data['類型'], asset_data['幣別']))
    symbols_to_fetch = list(all_symbols_to_fetch)
    if not symbols_to_fetch:
        st.toast("資料庫中無資產可更新。")
        return 0
    quotes_batch = db_client.batch()
    quotes_ref = db_client.collection('general_quotes')
    updated_count = 0
    progress_bar = st.progress(0, "開始更新報價...")
    for i, (symbol, asset_type, currency) in enumerate(symbols_to_fetch):
        price_data = get_price(symbol, asset_type, currency)
        if price_data and price_data.get("price") is not None:
            quotes_batch.set(quotes_ref.document(symbol), {
                "Symbol": symbol,
                "Price": round(float(price_data['price']), 4),
                "PreviousClose": round(float(price_data.get('previous_close', 0)), 4),
                "Timestamp": firestore.SERVER_TIMESTAMP
            })
            updated_count += 1
        progress_bar.progress((i + 1) / len(symbols_to_fetch), f"正在更新 {symbol}...")
    quotes_batch.commit()
    progress_bar.empty()
    return updated_count

# --- 用戶認證函式 ---
def signup_user(db, firebase_config, email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={firebase_config['apiKey']}"
    payload = json.dumps({"email": email, "password": password, "returnSecureToken": True})
    response_data = requests.post(url, headers={"Content-Type": "application/json"}, data=payload).json()
    if "idToken" in response_data:
        user_id = response_data["localId"]
        db.collection('users').document(user_id).set({
            'email': response_data["email"], 'created_at': firestore.SERVER_TIMESTAMP,
            'investment_profile': '通用市場趨勢，風險適中'
        })
        return response_data
    raise Exception(response_data.get("error", {}).get("message", "註冊失敗"))

def login_user(firebase_config, email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={firebase_config['apiKey']}"
    payload = json.dumps({"email": email, "password": password, "returnSecureToken": True})
    response = requests.post(url, headers={"Content-Type": "application/json"}, data=payload).json()
    if "idToken" in response:
        return response
    raise Exception(response.get("error", {}).get("message", "登入失敗"))

# --- Streamlit 數據加載函式 ---
@st.cache_data(ttl=300)
def load_user_assets_from_firestore(user_id):
    db, _ = init_firebase()
    docs = db.collection('users').document(user_id).collection('assets').stream()
    data = []
    for doc in docs:
        doc_data = doc.to_dict()
        doc_data['doc_id'] = doc.id
        data.append(doc_data)
    return pd.DataFrame(data)

@st.cache_data(ttl=60)
def load_quotes_from_firestore():
    db, _ = init_firebase()
    docs = db.collection('general_quotes').stream()
    df = pd.DataFrame([doc.to_dict() for doc in docs])
    if not df.empty:
        df['Symbol'] = df['Symbol'].astype(str)
        for col in ['Price', 'PreviousClose']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
    return df

@st.cache_data(ttl=900)
def load_latest_insights(user_id):
    db, _ = init_firebase()
    try:
        query = db.collection('users').document(user_id).collection('daily_insights').order_by('date', direction=firestore.Query.DESCENDING).limit(1)
        docs = list(query.stream())
        if docs:
            return docs[0].to_dict().get('insight_data')
        return None
    except Exception as e:
        st.error(f"讀取 AI 洞見時發生錯誤: {e}")
        return None

@st.cache_data(ttl=900)
def load_latest_economic_data():
    db, _ = init_firebase()
    try:
        query = db.collection('daily_economic_data').order_by('date', direction=firestore.Query.DESCENDING).limit(1)
        docs = list(query.stream())
        if docs:
            return docs[0].to_dict()
        return None
    except Exception as e:
        st.error(f"讀取宏觀經濟數據時發生錯誤: {e}")
        return None

@st.cache_data(ttl=1800)
def get_exchange_rate(from_currency="USD", to_currency="TWD"):
    try:
        ticker_str = f"{from_currency}{to_currency}=X"
        ticker = yf.Ticker(ticker_str)
        data = ticker.history(period="1d")
        if not data.empty:
            return data['Close'].iloc[-1]
    except Exception as e:
        print(f"獲取匯率 {ticker_str} 時出錯: {e}")
    return 30.0

@st.cache_data(ttl=900)
def load_historical_value(user_id):
    db, _ = init_firebase()
    try:
        query = db.collection('users').document(user_id).collection('historical_value').order_by('date', direction=firestore.Query.ASCENDING)
        docs = list(query.stream())
        if docs:
            data = [doc.to_dict() for doc in docs]
            df = pd.DataFrame(data)
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            return df
        return pd.DataFrame() 
    except Exception as e:
        st.error(f"讀取歷史淨值時發生錯誤: {e}")
        return pd.DataFrame()