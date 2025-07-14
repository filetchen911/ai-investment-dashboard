# app.py

# ========================================================
#  個人 AI 投資決策儀表板 - Streamlit App
#  版本：v2.7.0 - 最終功能版
#  功能：
#  - 新增資產配置圓餅圖 (台幣計價)
#  - 重構數據處理邏輯，徹底修復 KeyError
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
import plotly.express as px
import numpy as np

APP_VERSION = "v2.7.0"

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

@st.cache_data(ttl=60)
def load_quotes_from_firestore():
    docs = db.collection('general_quotes').stream()
    df = pd.DataFrame([doc.to_dict() for doc in docs])
    if not df.empty:
        df['Symbol'] = df['Symbol'].astype(str)
        df['Price'] = pd.to_numeric(df['Price'], errors='coerce')
    return df

@st.cache_data(ttl=900)
def load_latest_insights(user_id):
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
    return 32.5

# --- APP 介面與主體邏輯 ---
st.set_page_config(layout="wide", page_title="AI 投資儀表板")
st.title("📈 AI 投資儀表板")

# 側邊欄
if 'user_id' not in st.session_state:
    st.sidebar.header("歡迎使用")
    choice = st.sidebar.radio("請選擇操作", ["登入", "註冊"], horizontal=True)
    with st.sidebar.form("auth_form"):
        email = st.text_input("電子郵件")
        password = st.text_input("密碼", type="password")
        if st.form_submit_button("執行"):
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
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()
    st.sidebar.markdown("---")
    st.sidebar.caption(f"App Version: {APP_VERSION}")

# 主頁面
if 'user_id' in st.session_state:
    user_id = st.session_state['user_id']
    st.sidebar.header("導覽")
    page = st.sidebar.radio("選擇頁面", ["資產概覽", "AI 新聞精選", "決策輔助指標"], horizontal=True)

    if page == "資產概覽":
        st.header("📊 資產概覽")
        col1_action, _ = st.columns([1, 3])
        if col1_action.button("🔄 立即更新所有報價"):
            with st.spinner("正在執行報價更新..."):
                count = update_quotes_manually()
            st.success(f"報價更新完成！共處理 {count} 筆資產報價。")
            st.cache_data.clear()
            st.rerun()
        with st.expander("➕ 新增資產"):
            with st.form("add_asset_form", clear_on_submit=True):
                c1,c2,c3=st.columns(3)
                asset_type,symbol=c1.selectbox("類型",["股票","ETF","加密貨幣","其他"]),c1.text_input("代號")
                quantity,cost_basis=c2.number_input("持有數量",0.0,format="%.4f"),c2.number_input("平均成本",0.0,format="%.4f")
                currency,name=c3.selectbox("幣別",["USD","TWD","USDT"]),c3.text_input("自訂名稱(可選)")
                if st.form_submit_button("確定新增"):
                    if symbol and quantity>0 and cost_basis>0:
                        db.collection('users').document(user_id).collection('assets').add({"類型":asset_type,"代號":symbol,"名稱":name,"數量":float(quantity),"成本價":float(cost_basis),"幣別":currency,"建立時間":firestore.SERVER_TIMESTAMP})
                        st.success("資產已成功新增！");st.cache_data.clear();st.rerun()
                    else: st.error("代號、數量、成本價為必填欄位，且必須大於 0。")
        st.markdown("---")
        
        assets_df = load_user_assets_from_firestore(user_id)
        quotes_df = load_quotes_from_firestore()
        usd_to_twd_rate = get_exchange_rate("USD", "TWD")

        if assets_df.empty:
            st.info("您目前沒有資產。")
        else:
            # --- [v2.7.0] 最終數據處理邏輯 ---
            df = pd.merge(assets_df, quotes_df, left_on='代號', right_on='Symbol', how='left')
            
            for col in ['數量', '成本價']:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            if 'Price' not in df.columns or df['Price'].isnull().all():
                df['Price'] = df['成本價']
            else:
                df['Price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(df['成本價'])

            # 1. 優先計算原幣別指標，確保欄位存在
            df['市值'] = df['Price'] * df['數量']
            df['成本'] = df['成本價'] * df['數量']
            df['損益'] = df['市值'] - df['成本']
            df['損益比'] = np.divide(df['損益'], df['成本'], out=np.zeros_like(df['損益']), where=df['成本']!=0) * 100

            # 2. 建立台幣市值欄位，用於總計與圖表
            df['市值_TWD'] = df['市值']
            usd_mask = (df['幣別'] == 'USD') | (df['幣別'] == 'USDT')
            df.loc[usd_mask, '市值_TWD'] = df.loc[usd_mask, '市值'] * usd_to_twd_rate
            
            # 3. 資產分類
            def classify_asset(r):
                t,s=r.get('類型','').lower(),r.get('代號','').upper()
                if t=='加密貨幣':return '加密貨幣'
                if '.TW' in s or '.TWO' in s:return '台股/ETF'
                if t in ['股票','etf']:return '美股/其他海外ETF'
                return '其他資產'
            df['分類'] = df.apply(classify_asset, axis=1)
            
            # 4. 計算台幣總計
            total_value_twd = df['市值_TWD'].sum()
            total_cost_twd = df.apply(lambda r: r['成本'] * usd_to_twd_rate if r['幣別'] in ['USD', 'USDT'] else r['成本'], axis=1).sum()
            total_pnl_twd = total_value_twd - total_cost_twd
            total_pnl_ratio = (total_pnl_twd / total_cost_twd * 100) if total_cost_twd != 0 else 0
            
            k1, k2, k3 = st.columns(3)
            k1.metric("總資產價值 (約 TWD)", f"${total_value_twd:,.0f}")
            k2.metric("總損益 (約 TWD)", f"${total_pnl_twd:,.0f}", f"{total_pnl_ratio:.2f}%")
            k3.metric("美金匯率 (USD/TWD)", f"{usd_to_twd_rate:.2f}")
            st.markdown("---")

            # 5. 資產配置圓餅圖
            if total_value_twd > 0:
                st.subheader("資產配置比例")
                allocation_by_class = df.groupby('分類')['市值_TWD'].sum().reset_index()
                allocation_by_currency = df.groupby('幣別')['市值_TWD'].sum().reset_index()
                chart_col1, chart_col2 = st.columns(2)
                with chart_col1:
                    fig_class = px.pie(allocation_by_class, names='分類', values='市值_TWD', title='依資產類別 (台幣計價)', hole=.3)
                    st.plotly_chart(fig_class, use_container_width=True)
                with chart_col2:
                    fig_currency = px.pie(allocation_by_currency, names='幣別', values='市值_TWD', title='依計價幣別 (台幣計價)', hole=.3)
                    st.plotly_chart(fig_currency, use_container_width=True)
            st.markdown("---")
            
            if 'editing_asset_id' in st.session_state:
                asset_to_edit=df[df['doc_id']==st.session_state['editing_asset_id']].iloc[0]
                with st.form("edit_asset_form"):
                    st.subheader(f"✏️ 正在編輯資產: {asset_to_edit.get('名稱',asset_to_edit['代號'])}")
                    q,c,n=st.number_input("持有數量",0.0,format="%.4f",value=asset_to_edit['數量']),st.number_input("平均成本",0.0,format="%.4f",value=asset_to_edit['成本價']),st.text_input("自訂名稱(可選)",value=asset_to_edit.get('名稱',''))
                    if st.form_submit_button("儲存變更"):
                        db.collection('users').document(user_id).collection('assets').document(st.session_state['editing_asset_id']).update({"數量":float(q),"成本價":float(c),"名稱":n})
                        st.success("資產已成功更新！");del st.session_state['editing_asset_id'];st.cache_data.clear();st.rerun()

            col_title, col_time = st.columns([3, 1])
            with col_title:
                st.subheader("我的投資組合")
            with col_time:
                if 'Timestamp' in quotes_df.columns and not quotes_df['Timestamp'].isnull().all():
                    last_updated_utc = quotes_df['Timestamp'].max()
                    taipei_tz = datetime.timezone(datetime.timedelta(hours=8))
                    last_updated_taipei = last_updated_utc.astimezone(taipei_tz)
                    formatted_time = last_updated_taipei.strftime('%y-%m-%d %H:%M')
                    st.markdown(f"<p style='text-align: right; color: #888; font-size: 0.9em;'>更新於: {formatted_time}</p>", unsafe_allow_html=True)
            
            categories=df['分類'].unique().tolist()
            asset_tabs=st.tabs(categories)
            
            for i, category in enumerate(categories):
                with asset_tabs[i]:
                    category_df=df[df['分類']==category]
                    cat_value_twd = category_df['市值_TWD'].sum()
                    cat_cost_twd = category_df.apply(lambda r: r['成本'] * usd_to_twd_rate if r['幣別'] in ['USD', 'USDT'] else r['成本'], axis=1).sum()
                    cat_pnl_twd = cat_value_twd - cat_cost_twd
                    cat_pnl_ratio = (cat_pnl_twd / cat_cost_twd * 100) if cat_cost_twd != 0 else 0
                    c1,c2=st.columns(2)
                    c1.metric(f"{category} 市值 (約 TWD)",f"${cat_value_twd:,.0f}")
                    c2.metric(f"{category} 損益 (約 TWD)",f"${cat_pnl_twd:,.0f}",f"{cat_pnl_ratio:.2f}%")
                    st.markdown("---")

                    header_cols = st.columns([3, 2, 2, 2, 2, 2])
                    headers = ["持倉", "數量", "現價", "成本", "總市值", ""]
                    for col, header in zip(header_cols, headers):
                        col.markdown(f"**{header}**")
                    st.markdown('<hr style="margin-top:0; margin-bottom:0.5rem; opacity: 0.3;">', unsafe_allow_html=True)

                    for _, row in category_df.iterrows():
                        doc_id = row['doc_id']
                        cols = st.columns([3, 2, 2, 2, 2, 2])
                        with cols[0]:
                            st.markdown(f"<h5>{row.get('代號', '')}</h5>", unsafe_allow_html=True)
                            st.caption(row.get('名稱') or row.get('類型', ''))
                        with cols[1]:
                            st.markdown(f"<h5>{row.get('數量', 0):.4f}</h5>", unsafe_allow_html=True)
                        with cols[2]:
                            st.markdown(f"<h5>{row.get('Price', 0):,.2f}</h5>", unsafe_allow_html=True)
                        with cols[3]:
                            st.markdown(f"<h5>{row.get('成本價', 0):,.2f}</h5>", unsafe_allow_html=True)
                        with cols[4]:
                            st.markdown(f"<h5>{row.get('市值', 0):,.2f}</h5>", unsafe_allow_html=True)
                        with cols[5]:
                            btn_cols = st.columns([1,1])
                            if btn_cols[0].button("✏️", key=f"edit_{doc_id}", help="編輯此資產", use_container_width=True):
                                st.session_state['editing_asset_id'] = doc_id
                                st.rerun()
                            if btn_cols[1].button("🗑️", key=f"delete_{doc_id}", help="刪除此資產", use_container_width=True):
                                db.collection('users').document(user_id).collection('assets').document(doc_id).delete()
                                st.success(f"資產 {row['代號']} 已刪除！"); st.cache_data.clear(); st.rerun()
                        
                        with st.expander("查看損益"):
                            pnl = row.get('損益', 0)
                            pnl_ratio = row.get('損益比', 0)
                            st.metric(label=f"總損益 ({row.get('幣別','')})", value=f"{pnl:,.2f}", delta=f"{pnl_ratio:.2f}%")
                        st.divider()

    elif page == "AI 新聞精選":
        st.header("💡 AI 每日市場洞察")
        insights_data = load_latest_insights(user_id)
        if insights_data:
            st.caption(f"上次分析時間: {datetime.datetime.now(datetime.timezone.utc).astimezone(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')} (台北時間)")
            st.subheader("今日市場總結")
            st.info(insights_data.get('market_summary', '暫無總結。'))
            st.subheader("對您投資組合的潛在影響")
            st.warning(insights_data.get('portfolio_impact', '暫無影響分析。'))
            st.markdown("---")
            st.subheader("核心洞見摘要")
            key_takeaways = insights_data.get('key_takeaways', [])
            if not key_takeaways:
                st.write("今日無核心洞見。")
            else:
                for item in key_takeaways:
                    icon = "📊" if item.get('type') == '數據洞見' else "📰"
                    with st.container(border=True):
                        st.markdown(f"**{icon} {item.get('type', '洞見')}** | 來源：{item.get('source', '未知')}")
                        st.write(item.get('content', ''))
                        if item.get('type') == '新聞洞見' and item.get('link'):
                            st.link_button("查看原文", item['link'])
        else:
            st.info("今日的 AI 分析尚未生成，或正在處理中。")

    elif page == "決策輔助指標":
        st.header("📈 關鍵經濟指標趨勢")
        economic_data_report = load_latest_economic_data()
        if economic_data_report:
            if 'date' in economic_data_report and isinstance(economic_data_report.get('date'), datetime.datetime):
                last_update_time = economic_data_report['date'].strftime('%Y-%m-%d %H:%M:%S')
            else:
                last_update_time = "N/A"
            st.caption(f"數據來源：{economic_data_report.get('source_name', '未知')} | 上次更新時間 (UTC): {last_update_time}")
            
            st.subheader("宏觀經濟數據趨勢")
            indicators = economic_data_report.get('data_series_items', [])
            if not indicators:
                st.write("暫無宏觀經濟數據。")
            else:
                col1, col2 = st.columns(2)
                for i, indicator in enumerate(indicators):
                    target_col = col1 if i % 2 == 0 else col2
                    with target_col:
                        with st.container(border=True):
                            st.markdown(f"**{indicator.get('event', '未知指標')}**")
                            values = indicator.get('values', [])
                            if values:
                                chart_df = pd.DataFrame(values)
                                chart_df['date'] = pd.to_datetime(chart_df['date'])
                                chart_df = chart_df.set_index('date')
                                chart_df['value'] = pd.to_numeric(chart_df['value'])
                                latest_point = values[-1]
                                st.metric(label=f"最新數據 ({latest_point['date']})", value=f"{latest_point['value']}")
                                st.line_chart(chart_df)
                            else:
                                st.write("暫無趨勢數據。")
        else:
            st.info("今日的宏觀經濟數據尚未生成，或正在處理中。")
else:
    st.info("👋 請從左側側邊欄登入或註冊，以開始使用您的 AI 投資儀表板。")