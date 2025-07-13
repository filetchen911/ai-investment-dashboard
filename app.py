# app.py

# ========================================================
#  個人 AI 投資決策儀表板 - Streamlit App
#  版本：v1.8.0 - AI 洞見呈現 + 健壯性修正版
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

APP_VERSION = "v1.8.0"

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
    """從 Firestore 讀取指定用戶最新的 AI 每日洞見。"""
    try:
        query = db.collection('users').document(user_id).collection('daily_insights').order_by('date', direction=firestore.Query.DESCENDING).limit(1)
        docs = list(query.stream())
        if docs:
            return docs[0].to_dict().get('insight_data')
        return None
    except Exception as e:
        st.error(f"讀取 AI 洞見時發生錯誤: {e}")
        return None

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
        assets_df,quotes_df=load_user_assets_from_firestore(user_id),load_quotes_from_firestore()
        if assets_df.empty:st.info("您目前沒有資產。")
        else:
            df=pd.merge(assets_df,quotes_df,left_on='代號',right_on='Symbol',how='left')
            for col in ['數量','成本價']:df[col]=pd.to_numeric(df[col],errors='coerce').fillna(0)
            
            # --- [健壯性修正] ---
            if 'Price' in df.columns and not df['Price'].isnull().all():
                df['Price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(0)
                df['市值'] = df['Price'] * df['數量']
            else:
                df['Price'] = df['成本價']
                df['市值'] = df['成本價'] * df['數量']
                if 'warning_shown' not in st.session_state:
                    st.warning("報價數據暫時無法獲取，目前「現價」與「市值」以您的成本價計算。")
                    st.session_state['warning_shown'] = True
            # --- 修正結束 ---
            
            df['成本']=df['成本價']*df['數量']
            df['損益']=df['市值']-df['成本']
            df['損益比']=df.apply(lambda r:(r['損益']/r['成本'])*100 if r['成本']!=0 else 0,axis=1)
            def classify_asset(r):
                t,s=r.get('類型','').lower(),r.get('代號','').upper()
                if t=='加密貨幣':return '加密貨幣'
                if '.TW' in s or '.TWO' in s:return '台股/ETF'
                if t in ['股票','etf']:return '美股/其他海外ETF'
                return '其他資產'
            df['分類']=df.apply(classify_asset,axis=1)
            total_value_usd=df.apply(lambda r:r['市值']/32 if r['幣別']=='TWD' else r['市值'],axis=1).sum()
            total_cost_usd=df.apply(lambda r:r['成本']/32 if r['幣別']=='TWD' else r['成本'],axis=1).sum()
            #total_pnl_usd,total_pnl_ratio=total_value_usd-total_cost_usd,(total_pnl_usd/total_cost_usd*100) if total_cost_usd!=0 else 0
            total_pnl_usd = total_value_usd - total_cost_usd
            total_pnl_ratio = (total_pnl_usd / total_cost_usd * 100) if total_cost_usd != 0 else 0
            last_updated=quotes_df['Timestamp'].max().strftime('%Y-%m-%d %H:%M:%S') if 'Timestamp' in quotes_df.columns and not quotes_df['Timestamp'].isnull().all() else "N/A"
            k1,k2,k3=st.columns(3)
            k1.metric("總資產價值 (約 USD)",f"${total_value_usd:,.2f}");k2.metric("總損益 (約 USD)",f"${total_pnl_usd:,.2f}",f"{total_pnl_ratio:.2f}%");k3.metric("報價更新時間 (UTC)",last_updated)
            st.markdown("---")
            if 'editing_asset_id' in st.session_state:
                asset_to_edit=df[df['doc_id']==st.session_state['editing_asset_id']].iloc[0]
                with st.form("edit_asset_form"):
                    st.subheader(f"✏️ 正在編輯資產: {asset_to_edit.get('名稱',asset_to_edit['代號'])}")
                    q,c,n=st.number_input("持有數量",0.0,format="%.4f",value=asset_to_edit['數量']),st.number_input("平均成本",0.0,format="%.4f",value=asset_to_edit['成本價']),st.text_input("自訂名稱(可選)",value=asset_to_edit.get('名稱',''))
                    if st.form_submit_button("儲存變更"):
                        db.collection('users').document(user_id).collection('assets').document(st.session_state['editing_asset_id']).update({"數量":float(q),"成本價":float(c),"名稱":n})
                        st.success("資產已成功更新！");del st.session_state['editing_asset_id'];st.cache_data.clear();st.rerun()
            st.subheader("我的投資組合")
            categories=df['分類'].unique().tolist()
            asset_tabs=st.tabs(categories)
            for i, category in enumerate(categories):
                with asset_tabs[i]:
                    category_df=df[df['分類']==category]
                    cat_value=category_df.apply(lambda r:r['市值']/32 if r['幣別']=='TWD' else r['市值'],axis=1).sum()
                    cat_cost=category_df.apply(lambda r:r['成本']/32 if r['幣別']=='TWD' else r['成本'],axis=1).sum()
                    #cat_pnl,cat_pnl_ratio=cat_value-cat_cost,(cat_pnl/cat_cost*100) if cat_cost!=0 else 0
                    cat_pnl = cat_value - cat_cost
                    cat_pnl_ratio = (cat_pnl / cat_cost * 100) if cat_cost != 0 else 0
                    c1,c2=st.columns(2);c1.metric(f"{category} 市值 (約 USD)",f"${cat_value:,.2f}");c2.metric(f"{category} 損益 (約 USD)",f"${cat_pnl:,.2f}",f"{cat_pnl_ratio:.2f}%")
                    st.markdown("---")
                    h_cols=st.columns([3,2,2,2,2,3,1,1])
                    for col,h in zip(h_cols,["資產","持有數量","平均成本","現價","市值","損益 (損益比)","",""]):col.markdown(f"**{h}**")
                    for _,row in category_df.iterrows():
                        doc_id,pnl,pnl_ratio=row['doc_id'],row['損益'],row['損益比']
                        cols=st.columns([3,2,2,2,2,3,1,1])
                        cols[0].markdown(f"**{row['代號']}**<br><small>{row.get('名稱')or row.get('類型','')}</small>",unsafe_allow_html=True)
                        cols[1].text(f"{row['數量']:.4f}");cols[2].text(f"{row['成本價']:.2f} {row['幣別']}");cols[3].text(f"{row['Price']:.2f} {row['幣別']}");cols[4].text(f"{row['市值']:,.2f} {row['幣別']}")
                        cols[5].metric(label="",value=f"{pnl:,.2f}",delta=f"{pnl_ratio:.2f}%",label_visibility="collapsed")
                        if cols[6].button("✏️",key=f"edit_{doc_id}",help="編輯"):st.session_state['editing_asset_id']=doc_id;st.rerun()
                        if cols[7].button("🗑️",key=f"delete_{doc_id}",help="刪除"):db.collection('users').document(user_id).collection('assets').document(doc_id).delete();st.success(f"資產 {row['代號']} 已刪除！");st.cache_data.clear();st.rerun()

    elif page == "AI 新聞精選":
        st.header("💡 AI 每日市場洞察")
        insights_data = load_latest_insights(user_id)
        if insights_data:
            st.caption(f"上次分析時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} (您的本地時間)")
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
            st.info("今日的 AI 分析尚未生成，或正在處理中。請稍後再回來查看。")

    elif page == "決策輔助指標":
        st.header("📈 決策輔助指標 (開發中)")
        st.info("此功能將在未來版本中，顯示由後端抓取的 CNN 恐慌貪婪指數等數據。")

else:
    st.info("👋 請從左側側邊欄登入或註冊，以開始使用您的 AI 投資儀表板。")