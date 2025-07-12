# app.py

# ========================================================
#  版本：v1.4.1 - Secrets 解析修正版
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
import ast # <--- [新增] 導入 ast 函式庫

APP_VERSION = "v1.4.1"

# --- [重大修改] 從 Streamlit Secrets 讀取並解析配置 ---
try:
    # firebase_config 是一個表格 (Table)，Streamlit 會正確解析為類字典物件
    firebase_config = st.secrets["firebase_config"]
    
    # 讀取服務帳戶金鑰 "字串"
    service_account_str = st.secrets["firebase_service_account_str"]
    
    # 使用 ast.literal_eval 將字串安全地轉換回字典
    service_account_info = ast.literal_eval(service_account_str)

except Exception as e:
    st.error("⚠️ Secrets 配置錯誤或遺失。請檢查 Streamlit Cloud 中的設定。")
    st.error(f"詳細錯誤: {e}")
    st.stop()
    
# --- Firebase Admin SDK 初始化 ---
if not firebase_admin._apps:
    try:
        # 現在 service_account_info 是一個正確的字典格式
        cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Firebase Admin SDK 初始化失敗: {e}")
        st.stop()

db = firestore.client()


# --- [升級版] 後端邏輯函數 ---
def get_price(symbol, asset_type, currency="USD"):
    """[升級版] 獲取單一資產的價格，統一使用 yfinance。"""
    price = None
    try:
        if asset_type.lower() in ["股票", "etf"]:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="2d", auto_adjust=True) # 使用 auto_adjust=True 獲取調整後價格
            if not data.empty and 'Close' in data and not data['Close'].empty:
                price = data['Close'].iloc[-1]
                
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
    users_ref = db_client.collection('users')
    users_list = list(users_ref.stream())
    for user_doc in users_list:
        assets_ref = user_doc.reference.collection('assets')
        for asset_doc in assets_ref.stream():
            asset_data = asset_doc.to_dict()
            symbol = asset_data.get('代號')
            asset_type = asset_data.get('類型')
            currency = asset_data.get('幣別')
            if symbol and asset_type and currency:
                all_symbols_to_fetch.add((symbol, asset_type, currency))
    return list(all_symbols_to_fetch)

def update_quotes_manually():
    db_client = firestore.client()
    symbols_to_fetch = get_all_symbols_from_firestore()
    if not symbols_to_fetch:
        st.toast("在所有用戶中未找到任何資產可供更新。")
        return 0

    quotes_batch = db_client.batch()
    quotes_ref = db_client.collection('general_quotes')
    updated_count = 0
    
    progress_bar = st.progress(0, text="正在開始更新報價...")
    
    for i, (symbol, asset_type, currency) in enumerate(symbols_to_fetch):
        current_price = get_price(symbol, asset_type, currency)
        if current_price is not None:
            quotes_batch.set(quotes_ref.document(symbol), {
                "Symbol": symbol,
                "Price": round(float(current_price), 4),
                "Timestamp": firestore.SERVER_TIMESTAMP
            })
            updated_count += 1
        progress_text = f"正在更新 {symbol}... ({i+1}/{len(symbols_to_fetch)})"
        progress_bar.progress((i + 1) / len(symbols_to_fetch), text=progress_text)

    quotes_batch.commit()
    progress_bar.empty()
    return updated_count

# --- 用戶認證函式 ---
def signup_user(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={firebase_config['apiKey']}"
    payload = json.dumps({"email": email, "password": password, "returnSecureToken": True})
    headers = {"Content-Type": "application/json"}
    response_data = requests.post(url, data=payload, headers=headers).json()
    if "idToken" not in response_data:
        raise Exception(response_data.get("error", {}).get("message", "註冊失敗，未知錯誤。"))
    user_id = response_data["localId"]
    try:
        db.collection('users').document(user_id).set({
            'email': response_data["email"], 'created_at': firestore.SERVER_TIMESTAMP,
            'investment_profile': '通用市場趨勢，風險適中'
        })
    except Exception as e:
        raise Exception(f"註冊成功，但建立用戶資料時發生錯誤: {e}")
    return response_data

def login_user(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={firebase_config['apiKey']}"
    payload = json.dumps({"email": email, "password": password, "returnSecureToken": True})
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, data=payload, headers=headers).json()
    if "idToken" in response:
        return response
    else:
        raise Exception(response.get("error", {}).get("message", "登入失敗"))

# --- Streamlit 數據加載函式 ---
@st.cache_data(ttl=300)
def load_user_assets_from_firestore(user_id):
    assets_docs = db.collection('users').document(user_id).collection('assets').stream()
    assets_list = []
    for doc in assets_docs:
        asset_data = doc.to_dict()
        asset_data['doc_id'] = doc.id
        assets_list.append(asset_data)
    return pd.DataFrame(assets_list)

@st.cache_data(ttl=60)
def load_quotes_from_firestore():
    quotes_docs = db.collection('general_quotes').stream()
    quotes_list = [doc.to_dict() for doc in quotes_docs]
    df = pd.DataFrame(quotes_list)
    if not df.empty:
        df['Symbol'] = df['Symbol'].astype(str)
        df['Price'] = pd.to_numeric(df['Price'], errors='coerce')
    return df

# --- APP 介面與主體邏輯 ---
st.set_page_config(layout="wide", page_title="AI 投資儀表板")
st.title("📈 AI 投資儀表板")

# 側邊欄用戶認證區
if 'user_id' not in st.session_state:
    st.sidebar.header("歡迎使用")
    # ... (此處省略認證表單的詳細程式碼，與前版相同) ...
    choice = st.sidebar.radio("請選擇操作", ["登入", "註冊"], horizontal=True)
    with st.sidebar.form("auth_form"):
        email = st.text_input("電子郵件")
        password = st.text_input("密碼", type="password")
        submitted = st.form_submit_button("執行")
        if submitted:
            if not email or not password:
                st.sidebar.warning("請輸入電子郵件和密碼。")
            else:
                try:
                    if choice == "註冊":
                        signup_user(email, password)
                        st.sidebar.success("✅ 註冊成功！請使用您的帳號登入。")
                    elif choice == "登入":
                        user = login_user(email, password)
                        st.session_state['user_id'] = user['localId']
                        st.session_state['user_email'] = user['email']
                        st.rerun()
                except Exception as e:
                    st.sidebar.error(f"操作失敗: {e}")
else:
    st.sidebar.success(f"已登入: {st.session_state['user_email']}")
    if st.sidebar.button("登出"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    # --- [新增] 在此處顯示版本號 ---
    st.sidebar.markdown("---") # 畫一條分隔線
    st.sidebar.caption(f"App Version: {APP_VERSION}") # 使用 caption 或 info 來顯示
    
# 主頁面內容 (僅在登入後顯示)
if 'user_id' in st.session_state:
    st.sidebar.header("導覽")
    page = st.sidebar.radio("選擇頁面", ["資產概覽", "AI 新聞精選", "決策輔助指標"], horizontal=True)

    if page == "資產概覽":
        st.header("📊 資產概覽")
        user_id = st.session_state['user_id']

        col1_action, col2_action = st.columns([1,3])
        with col1_action:
            if st.button("🔄 立即更新所有報價"):
                with st.spinner("正在執行報價更新，請稍候...此過程可能需要一點時間。"):
                    count = update_quotes_manually()
                st.success(f"報價更新完成！共更新 {count} 筆資產報價。")
                st.cache_data.clear()
                st.rerun()

        with st.expander("➕ 新增資產"):
            with st.form("add_asset_form", clear_on_submit=True):
                # ... (新增資產表單) ...
                c1, c2, c3 = st.columns(3)
                with c1:
                    asset_type = st.selectbox("類型", ["股票", "ETF", "加密貨幣", "其他"])
                    symbol = st.text_input("代號", placeholder="例如: TSLA, 0050.TW, bitcoin, Gold")
                with c2:
                    quantity = st.number_input("持有數量", min_value=0.0, format="%.4f")
                    cost_basis = st.number_input("平均成本", min_value=0.0, format="%.4f")
                with c3:
                    currency = st.selectbox("幣別", ["USD", "TWD", "USDT"])
                    name = st.text_input("自訂名稱(可選)", placeholder="例如: 特斯拉, 元大台灣50")
                submitted = st.form_submit_button("確定新增")
                if submitted:
                    if not all([symbol, quantity > 0, cost_basis > 0]):
                        st.error("代號、數量、成本價為必填欄位，且必須大於 0。")
                    else:
                        db.collection('users').document(user_id).collection('assets').add({
                            "類型": asset_type, "代號": symbol, "名稱": name,
                            "數量": float(quantity), "成本價": float(cost_basis),
                            "幣別": currency, "建立時間": firestore.SERVER_TIMESTAMP
                        })
                        st.success("資產已成功新增！")
                        st.cache_data.clear()
                        st.rerun()
        st.markdown("---")

        assets_df = load_user_assets_from_firestore(user_id)
        quotes_df = load_quotes_from_firestore()

        if assets_df.empty:
            st.info("您目前沒有資產。請使用上方「新增資產」區塊添加您的第一筆資產。")
        else:
            # --- 數據處理與分類 ---
            df = pd.merge(assets_df, quotes_df, left_on='代號', right_on='Symbol', how='left')
            for col in ['Price', '數量', '成本價']: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            df['市值'] = df['Price'] * df['數量']
            df['成本'] = df['成本價'] * df['數量']
            df['損益'] = df['市值'] - df['成本']
            df['損益比'] = df.apply(lambda row: (row['損益'] / row['成本']) * 100 if row['成本'] != 0 else 0, axis=1)

            def classify_asset(row):
                asset_type, symbol = row.get('類型', '').lower(), row.get('代號', '').upper()
                if asset_type == '加密貨幣': return '加密貨幣'
                elif '.TW' in symbol or '.TWO' in symbol: return '台股/ETF'
                elif asset_type in ['股票', 'etf']: return '美股/其他海外ETF'
                else: return '其他資產'
            df['分類'] = df.apply(classify_asset, axis=1)
            
            # --- 總覽指標顯示 ---
            # ... (總覽指標計算與顯示) ...
            total_value_usd = df.apply(lambda r: r['市值'] / 32 if r['幣別'] == 'TWD' else r['市值'], axis=1).sum()
            total_cost_usd = df.apply(lambda r: r['成本'] / 32 if r['幣別'] == 'TWD' else r['成本'], axis=1).sum()
            total_pnl_usd = total_value_usd - total_cost_usd
            total_pnl_ratio = (total_pnl_usd / total_cost_usd * 100) if total_cost_usd != 0 else 0
            last_updated = quotes_df['Timestamp'].max().strftime('%Y-%m-%d %H:%M:%S') if 'Timestamp' in quotes_df.columns and not quotes_df['Timestamp'].isnull().all() else "N/A"
            kpi1, kpi2, kpi3 = st.columns(3)
            kpi1.metric("總資產價值 (約 USD)", f"${total_value_usd:,.2f}")
            kpi2.metric("總損益 (約 USD)", f"${total_pnl_usd:,.2f}", f"{total_pnl_ratio:.2f}%")
            kpi3.metric("報價更新時間 (UTC)", last_updated)
            st.markdown("---")

            # --- 編輯表單邏輯 ---
            if 'editing_asset_id' in st.session_state:
                # ... (編輯表單的詳細程式碼) ...
                asset_id_to_edit = st.session_state['editing_asset_id']
                asset_to_edit = df[df['doc_id'] == asset_id_to_edit].iloc[0]
                st.subheader(f"✏️ 正在編輯資產: {asset_to_edit.get('名稱', asset_to_edit['代號'])}")
                with st.form("edit_asset_form"):
                    new_quantity = st.number_input("持有數量", min_value=0.0, format="%.4f", value=asset_to_edit['數量'])
                    new_cost_basis = st.number_input("平均成本", min_value=0.0, format="%.4f", value=asset_to_edit['成本價'])
                    new_name = st.text_input("自訂名稱(可選)", value=asset_to_edit.get('名稱', ''))
                    submitted_edit = st.form_submit_button("儲存變更")
                    if submitted_edit:
                        update_data = {"數量": float(new_quantity), "成本價": float(new_cost_basis), "名稱": new_name}
                        db.collection('users').document(user_id).collection('assets').document(asset_id_to_edit).update(update_data)
                        st.success("資產已成功更新！")
                        del st.session_state['editing_asset_id']
                        st.cache_data.clear()
                        st.rerun()

            # --- 分類頁籤 (Tabs) 顯示 ---
            st.subheader("我的投資組合")
            categories = df['分類'].unique().tolist()
            asset_tabs = st.tabs(categories)

            for i, category in enumerate(categories):
                with asset_tabs[i]:
                    category_df = df[df['分類'] == category]
                    # ... (分類小計與列表渲染) ...
                    cat_value = category_df['市值'].sum()
                    cat_cost = category_df['成本'].sum()
                    cat_pnl = cat_value - cat_cost
                    cat_pnl_ratio = (cat_pnl / cat_cost * 100) if cat_cost != 0 else 0
                    c1, c2 = st.columns(2)
                    c1.metric(f"{category} 市值 (當地幣別加總)", f"{cat_value:,.2f}")
                    c2.metric(f"{category} 損益", f"{cat_pnl:,.2f}", f"{cat_pnl_ratio:.2f}%")
                    st.markdown("---")
                    
                    header_cols = st.columns([3, 2, 2, 2, 2, 3, 1, 1])
                    headers = ["資產", "持有數量", "平均成本", "現價", "市值", "損益 (損益比)", "", ""]
                    for col, header in zip(header_cols, headers): col.markdown(f"**{header}**")
                    
                    for index, row in category_df.iterrows():
                        doc_id, pnl, pnl_ratio = row['doc_id'], row['損益'], row['損益比']
                        cols = st.columns([3, 2, 2, 2, 2, 3, 1, 1])
                        cols[0].markdown(f"**{row['代號']}**<br><small>{row.get('名稱') or row.get('類型', '')}</small>", unsafe_allow_html=True)
                        cols[1].text(f"{row['數量']:.4f}")
                        cols[2].text(f"{row['成本價']:.2f} {row['幣別']}")
                        cols[3].text(f"{row['Price']:.2f} {row['幣別']}")
                        cols[4].text(f"{row['市值']:,.2f} {row['幣別']}")
                        cols[5].metric(label="", value=f"{pnl:,.2f}", delta=f"{pnl_ratio:.2f}%", label_visibility="collapsed")
                        if cols[6].button("✏️", key=f"edit_{doc_id}", help="編輯此資產"):
                            st.session_state['editing_asset_id'] = doc_id
                            st.rerun()
                        if cols[7].button("🗑️", key=f"delete_{doc_id}", help="刪除此資產"):
                            db.collection('users').document(user_id).collection('assets').document(doc_id).delete()
                            st.success(f"資產 {row['代號']} 已刪除！")
                            st.cache_data.clear()
                            st.rerun()

    # 其他頁面的 Placeholder
    elif page == "AI 新聞精選":
        st.header("📰 AI 新聞精選 (開發中)")
    elif page == "決策輔助指標":
        st.header("📈 決策輔助指標 (開發中)")

# 用戶未登入時的提示
else:
    st.info("👋 請從左側側邊欄登入或註冊，以開始使用您的 AI 投資儀表板。")