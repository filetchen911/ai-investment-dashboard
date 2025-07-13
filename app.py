# app.py

# ========================================================
#  個人 AI 投資決策儀表板 - Streamlit App
#  版本：v2.0.0 - 手機優先版
#  功能：
#  - 重構「資產概覽」頁面為卡片式佈局，優化手機瀏覽體驗
# ========================================================

# --- 核心導入 ---
import streamlit as st
import pandas as pd
import datetime
import os
import requests
import json
import yfinance as yf
import firebase_admin
from firebase_admin import credentials, auth, firestore

APP_VERSION = "v2.0.0"

# --- 從 Streamlit Secrets 讀取並重組金鑰 ---
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
    db = firestore.client()
except Exception as e:
    st.error("⚠️ Secrets 配置錯誤或 Firebase 初始化失敗。")
    st.error(f"詳細錯誤: {e}")
    st.stop()


# --- 後端邏輯函數 ---
def get_price(symbol, asset_type, currency="USD"):
    price = None
    try:
        if asset_type.lower() in ["股票", "etf"]:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="1d")
            if not data.empty: price = data['Close'].iloc[-1]
        elif asset_type.lower() == "加密貨幣":
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={symbol.lower()}&vs_currencies={currency.lower()}"
            response = requests.get(url).json()
            if symbol.lower() in response and currency.lower() in response[symbol.lower()]:
                price = response[symbol.lower()][currency.lower()]
    except Exception as e:
        print(f"獲取 {symbol} 報價時出錯: {e}")
    return price

def get_all_symbols_from_firestore():
    db_client = firestore.client()
    all_symbols_to_fetch = set()
    for user_doc in db_client.collection('users').stream():
        for asset_doc in user_doc.reference.collection('assets').stream():
            asset_data = asset_doc.to_dict()
            if asset_data.get('代號') and asset_data.get('類型') and asset_data.get('幣別'):
                all_symbols_to_fetch.add((asset_data['代號'], asset_data['類型'], asset_data['幣別']))
    return list(all_symbols_to_fetch)

def update_quotes_manually():
    symbols_to_fetch = get_all_symbols_from_firestore()
    if not symbols_to_fetch:
        st.toast("資料庫中無資產可更新。")
        return 0
    quotes_batch = firestore.client().batch()
    quotes_ref = firestore.client().collection('general_quotes')
    updated_count = 0
    progress_bar = st.progress(0, "開始更新報價...")
    for i, (symbol, asset_type, currency) in enumerate(symbols_to_fetch):
        price = get_price(symbol, asset_type, currency)
        if price is not None:
            quotes_batch.set(quotes_ref.document(symbol), {"Symbol": symbol, "Price": round(float(price), 4), "Timestamp": firestore.SERVER_TIMESTAMP})
            updated_count += 1
        progress_bar.progress((i + 1) / len(symbols_to_fetch), f"正在更新 {symbol}...")
    quotes_batch.commit()
    progress_bar.empty()
    return updated_count

# --- 用戶認證函式 ---
def signup_user(email, password):
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

def login_user(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={firebase_config['apiKey']}"
    payload = json.dumps({"email": email, "password": password, "returnSecureToken": True})
    response = requests.post(url, headers={"Content-Type": "application/json"}, data=payload).json()
    if "idToken" in response:
        return response
    raise Exception(response.get("error", {}).get("message", "登入失敗"))

# --- Streamlit 數據加載函式 ---
@st.cache_data(ttl=300)
def load_user_assets_from_firestore(user_id):
    docs = db.collection('users').document(user_id).collection('assets').stream()
    data = []
    for doc in docs:
        doc_data = doc.to_dict()
        doc_data['doc_id'] = doc.id
        data.append(doc_data)
    return pd.DataFrame(data)

@st.cache_data(ttl=