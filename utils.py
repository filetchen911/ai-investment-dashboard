# utils.py (v5.0.0)

import streamlit as st
import pandas as pd
from datetime import datetime
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
import numpy_financial as npf
from typing import Dict, List, Tuple, Optional
from config import APP_VERSION # <--- 從 config.py 引用


# 設定日誌系統
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- Firebase 初始化 ---
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
                    coin_id = s.lower()
                    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies={currency.lower()}"
                    response = requests.get(url).json()
                    if coin_id in response and currency.lower() in response[coin_id]:
                        price = response[coin_id][currency.lower()]
                        price_data = {"price": price, "previous_close": price}
                        return price_data
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

# --- 側邊欄 ---
def render_sidebar():
    if 'user_id' not in st.session_state:
        st.sidebar.header("歡迎使用")
        
        # --- [v5.0.0 修正] ---
        # 在需要時，才初始化並取得 db 和 firebase_config
        db, firebase_config = init_firebase()

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
                            signup_user(db, firebase_config, email, password)
                            st.sidebar.success("✅ 註冊成功！請使用您的帳號登入。")
                        elif choice == "登入":
                            user = login_user(firebase_config, email, password)
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

        # --- [v5.0.0 修正] 手動建立側邊欄導覽 ---
        st.sidebar.markdown("---")
        st.sidebar.page_link("pages/10_asset_overview.py", label="資產總覽", icon="📊")
        st.sidebar.page_link("pages/20_pension_overview.py", label="退休金總覽", icon="🏦")
        st.sidebar.page_link("pages/30_debt_management.py", label="債務管理", icon="💳")
        st.sidebar.page_link("pages/40_financial_dashboard.py", label="財務自由儀表板", icon="🏁")
        st.sidebar.page_link("pages/50_ai_insights.py", label="AI 每日洞察", icon="💡")
        st.sidebar.page_link("pages/60_economic_indicators.py", label="關鍵經濟指標", icon="📈")
        st.sidebar.markdown("---")
        st.sidebar.caption(f"App Version: {APP_VERSION}")

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

# --- [v5.0.0 新增] ---
@st.cache_data(ttl=300)
def load_retirement_plan(uid):
    """讀取使用者已儲存的退休規劃參數"""
    db, _ = init_firebase()
    user_doc = db.collection('users').document(uid).get()
    if user_doc.exists and 'retirement_plan' in user_doc.to_dict():
        return user_doc.to_dict()['retirement_plan']
    return {}

@st.cache_data(ttl=300)
def load_user_liabilities(uid):
    """從 Firestore 讀取使用者的所有債務資料"""
    db, _ = init_firebase()
    docs = db.collection('users').document(uid).collection('liabilities').stream()
    data = []
    for doc in docs:
        doc_data = doc.to_dict()
        doc_data['doc_id'] = doc.id
        if 'start_date' in doc_data and isinstance(doc_data['start_date'], datetime):
            doc_data['start_date'] = doc_data['start_date'].date()
        data.append(doc_data)
    return pd.DataFrame(data)

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

def calculate_asset_metrics(assets_df: pd.DataFrame) -> pd.DataFrame:
    """
    接收原始資產 DataFrame，回傳一個包含所有計算指標（市值、損益、佔比等）的新 DataFrame。
    這是專案中唯一負責計算資產指標的地方。
    """
    if assets_df.empty:
        return assets_df

    # 1. 獲取報價與匯率
    quotes_df = load_quotes_from_firestore()
    usd_to_twd_rate = get_exchange_rate("USD", "TWD")

    # 2. 合併與計算
    df = pd.merge(assets_df, quotes_df, left_on='代號', right_on='Symbol', how='left')
    
    # 確保數值格式正確
    for col in ['數量', '成本價']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    df['Price'] = pd.to_numeric(df.get('Price'), errors='coerce').fillna(df['成本價'])
    df['PreviousClose'] = pd.to_numeric(df.get('PreviousClose'), errors='coerce').fillna(df['Price'])

    # 3. 計算所有指標
    df['市值'] = df['Price'] * df['數量']
    df['成本'] = df['成本價'] * df['數量']
    df['損益'] = df['市值'] - df['成本']
    df['損益比'] = np.divide(df['損益'], df['成本'], out=np.zeros_like(df['損益'], dtype=float), where=df['成本']!=0) * 100
    df['今日漲跌'] = df['Price'] - df['PreviousClose']
    df['今日總損益'] = (df['Price'] - df['PreviousClose']) * df['數量']            
    df['今日漲跌幅'] = np.divide(df['今日漲跌'], df['PreviousClose'], out=np.zeros_like(df['Price'], dtype=float), where=df['PreviousClose']!=0) * 100
    df['市值_TWD'] = df.apply(lambda r: r['市值'] * usd_to_twd_rate if r['幣別'] in ['USD', 'USDT'] else r['市值'], axis=1)
    
    total_value_twd = df['市值_TWD'].sum()
    if total_value_twd > 0:
        df['佔比'] = (df['市值_TWD'] / total_value_twd) * 100
    else:
        df['佔比'] = 0
    
    df['分類'] = df['類型']

    return df

# [v5.0.0 最終修正] 重新命名函數，使其更通用
def calculate_loan_payments(principal, annual_rate, years, grace_period_years=0):
    """
    計算定期貸款在寬限期與本息攤還期的月付金。
    """
    if annual_rate <= 0 or years <= 0 or principal <= 0:
        return {"grace_period_payment": 0, "regular_payment": 0}

    monthly_rate = annual_rate / 100 / 12
    total_months = years * 12
    
    grace_payment = 0
    if grace_period_years > 0:
        grace_payment = principal * monthly_rate
    
    repayment_months = total_months if grace_period_years == 0 else total_months - (grace_period_years * 12)
    
    if repayment_months <= 0:
        return {"grace_period_payment": round(grace_payment), "regular_payment": 0}

    regular_payment = -npf.pmt(monthly_rate, repayment_months, principal)
    
    return {
        "grace_period_payment": round(grace_payment),
        "regular_payment": round(regular_payment)
    }

# --- [v4.1] 退休金計算引擎的包裝函數 ---
def get_full_retirement_analysis(user_inputs: Dict) -> Dict:

    calculator = RetirementCalculator()

    # 從 user_inputs 解構參數
    # 勞退參數
    pension_params = {
        'current_principal': user_inputs.get('current_pension_principal', 0),
        'monthly_salary': user_inputs.get('avg_monthly_salary', 0),
        'employer_rate': 6.0,  # 法定雇主提撥率
        'employee_rate': user_inputs.get('self_contribution_rate', 0),
        'years_to_retirement': user_inputs.get('years_to_retirement', 0),
        'annual_return_rate': user_inputs.get('expected_return_rate', 4.0),
        'retirement_age': user_inputs.get('retirement_age', 60),
        'current_contributed_years': user_inputs.get('pension_contributed_years', 0),
        'salary_growth_rate': user_inputs.get('salary_growth_rate', 2.0)
    }

    # 勞保參數
    insurance_params = {
        'avg_salary': user_inputs.get('avg_monthly_salary', 0),
        'insurance_years': user_inputs.get('insurance_seniority', 0),
        'claim_age': user_inputs.get('retirement_age', 60),
        'birth_year': user_inputs.get('birth_year', 1990)
    }

    # 執行計算
    labor_pension_result = calculator.calculate_labor_pension_accurate(**pension_params, verbose=False)
    labor_insurance_result = calculator.calculate_labor_insurance_pension(**insurance_params, verbose=False)

    # 整合結果用於替代率分析
    total_monthly_pension = labor_pension_result.get('monthly_pension', 0) + labor_insurance_result.get('monthly_pension', 0)
    replacement_ratio = (total_monthly_pension / user_inputs.get('avg_monthly_salary', 1)) * 100

    replacement_ratio_result = calculator.calculate_replacement_ratio_suggestions(
        replacement_ratio,
        user_inputs.get('avg_monthly_salary', 0),
        user_inputs.get('years_to_retirement', 0)
    )

    # 執行敏感度分析
    sensitivity_result = calculator.sensitivity_analysis(base_params=pension_params, verbose=False)

    # 將所有結果打包成一個清晰的字典
    final_results = {
        "labor_pension": labor_pension_result,
        "labor_insurance": labor_insurance_result,
        "summary": {
            "total_monthly_pension": total_monthly_pension,
            "replacement_ratio": replacement_ratio,
            "analysis": replacement_ratio_result
        },
        "sensitivity_analysis": sensitivity_result,
        "validation_errors": labor_pension_result.get('validation_errors', [])
    }

    return final_results

def get_holistic_financial_projection(user_id: str) -> Dict:
    # 1. 初始化
    plan = load_retirement_plan(user_id)
    raw_assets_df = load_user_assets_from_firestore(user_id) # 讀取原始數據
    liabilities_df = load_user_liabilities(user_id)

    # 2. 呼叫中心函數計算初始總資產
    enriched_assets_df = calculate_asset_metrics(raw_assets_df)
    current_assets = enriched_assets_df['市值_TWD'].sum() if not enriched_assets_df.empty else 0


    # 提取使用者假設
    return_rate = plan.get('expected_asset_return_rate', 7.0) / 100
    dividend_yield = plan.get('expected_dividend_yield', 2.5) / 100
    withdrawal_rate = plan.get('retirement_withdrawal_rate', 4.0) / 100
    inflation_rate = plan.get('inflation_rate', 2.0) / 100
    
    # 提取核心參數
    current_age = plan.get('current_age', 35)
    retirement_age = plan.get('retirement_age', 65)

    # 初始負債狀態
    current_liabilities = liabilities_df['outstanding_balance'].sum() if not liabilities_df.empty else 0
    
    # 取得退休金預估
    pension_results = get_full_retirement_analysis(plan)
    legal_age = pension_results.get('labor_insurance', {}).get('legal_age', 65)
    
    projection_timeseries = []
    
    # 2. 模擬迴圈
    for age in range(current_age, 101):
        year_data = {"age": age}
        
        # 3. 資產累積期
        if age < retirement_age:
            year_data["phase"] = "accumulation"
            current_assets *= (1 + return_rate)
            # 此模型簡化後的債務償還
            if not liabilities_df.empty:
                annual_payment = liabilities_df['monthly_payment'].sum() * 12
                current_liabilities -= annual_payment
                current_liabilities = max(0, current_liabilities)
            
            year_data["disposable_income"] = 0 # 尚無退休收入
        
        # 4. 資產提領期
        else:
            year_data["phase"] = "decumulation"
            
            # 計算收入流
            asset_income = (current_assets * dividend_yield) + (current_assets * withdrawal_rate)
            
            pension_income = 0
            if age >= legal_age:
                pension_income = pension_results['summary']['total_monthly_pension'] * 12
            elif age >= 60:
                pension_income = pension_results['labor_pension']['monthly_pension'] * 12

            total_income = asset_income + pension_income
            
            # 計算支出
            annual_debt_payment = 0
            if not liabilities_df.empty and current_liabilities > 0:
                annual_debt_payment = liabilities_df['monthly_payment'].sum() * 12
                current_liabilities -= annual_debt_payment
                current_liabilities = max(0, current_liabilities)

            disposable_income = total_income - annual_debt_payment
            year_data["disposable_income"] = disposable_income
            
            # 更新資產價值
            net_withdrawal = (disposable_income + annual_debt_payment) - (pension_income) # 從資產中提出的金額
            current_assets -= net_withdrawal
            current_assets *= (1 + return_rate)

        # --- [v5.0.0 修正] 確保輸出的欄位名稱與前端一致 ---
        # 5. 通膨調整
        # 儲存名目價值
        year_data["year_end_assets"] = current_assets
        year_data["year_end_liabilities"] = current_liabilities
        
        # 計算並儲存經通膨調整後的實質價值
        years_from_now = age - current_age
        # 使用 n+1 作為次方，以更精確地反映期末價值的貼現
        inflation_divisor = (1 + inflation_rate) ** (years_from_now + 1)
        
        # 使用前端 melt 函數所需要的、完全一致的欄位名稱
        year_data["year_end_assets_real_value"] = current_assets / inflation_divisor
        year_data["year_end_liabilities_real_value"] = current_liabilities / inflation_divisor
        year_data["disposable_income_real_value"] = year_data.get("disposable_income", 0) / inflation_divisor
        # --- [修正結束] ---        
        

        projection_timeseries.append(year_data)

    # 6. 最終輸出模型
    summary = {
        "assets_at_retirement_real_value": next((y["year_end_assets_real_value"] for y in projection_timeseries if y["age"] == retirement_age), 0),
        "first_year_disposable_income_real_value": next((y["disposable_income_real_value"] for y in projection_timeseries if y["age"] == retirement_age), 0)
    }
    
    return {"summary": summary, "projection_timeseries": projection_timeseries}
    
# --- [v4.1] 台灣退休金計算引擎 ---
class RetirementCalculator:
    def __init__(self):
        self.max_labor_insurance_salary = 45800  # 2025年勞保投保薪資最高級距
        self.max_labor_pension_salary = 150000  # 勞退提繳工資上限（月薪資）
        self.min_guaranteed_return = 1.07  # 勞退保證收益下限（政府保證）
        self.default_inflation_rate = 2.0  # 預設通膨率

        # 完整的平均餘命表（用於年金現值因子計算）
        self.life_expectancy_table = {
            60: 23.5, 61: 22.6, 62: 21.7, 63: 20.8, 64: 19.9,
            65: 19.1, 66: 18.2, 67: 17.4, 68: 16.6, 69: 15.8, 
            70: 15.0, 71: 14.2, 72: 13.5, 73: 12.8, 74: 12.1, 75: 11.4
        }

        # 擴充年金現值因子表（依勞動部公告）
        self.annuity_factor_table = {
            60: 21.39, 61: 20.53, 62: 19.67, 63: 18.82, 64: 17.98, 
            65: 17.15, 66: 16.33, 67: 15.52, 68: 14.73, 69: 13.95, 
            70: 13.18, 71: 12.43, 72: 11.70, 73: 10.98, 74: 10.28, 75: 9.60
        }
    
    def validate_inputs(self, **kwargs) -> List[str]:
        """
        輸入參數驗證
        
        Returns:
            List[str]: 錯誤訊息列表，空列表表示無錯誤
        """
        errors = []
        
        # 基本數值驗證
        if kwargs.get('monthly_salary', 0) <= 0:
            errors.append("月薪必須大於0")
        if kwargs.get('years_to_retirement', 0) < 0:
            errors.append("距離退休年數不能為負數")
        if kwargs.get('insurance_years', 0) < 0:
            errors.append("勞保年資不能為負數")
        if kwargs.get('current_contributed_years', 0) < 0:
            errors.append("已提繳年資不能為負數")
        
        # 比例驗證
        employer_rate = kwargs.get('employer_rate', 6.0)
        employee_rate = kwargs.get('employee_rate', 0.0)
        if employer_rate < 6.0 or employer_rate > 6.0:
            errors.append("雇主提繳率應為6%")
        if employee_rate < 0 or employee_rate > 6.0:
            errors.append("自願提繳率應介於0%~6%")
        
        # 年齡邏輯驗證
        current_age = kwargs.get('current_age', 0)
        retirement_age = kwargs.get('retirement_age', 60)
        if retirement_age < 60:
            errors.append("勞退請領年齡不得低於60歲")
        if current_age > 0 and retirement_age <= current_age:
            errors.append("退休年齡必須大於目前年齡")
            
        return errors

    def legal_retirement_age(self, birth_year: int) -> int:
        """
        根據出生年計算法定可請領勞保年金的年齡
        1956年以前為60歲，之後每年遞增1歲，至1961年後皆為65歲
        """
        if birth_year <= 1956:
            return 60
        elif birth_year == 1957:
            return 61
        elif birth_year == 1958:
            return 62
        elif birth_year == 1959:
            return 63
        elif birth_year == 1960:
            return 64
        else:
            return 65

    def get_annuity_factor(self, retirement_age: int) -> float:
        """
        取得年金現值因子，支援插值計算
        """
        if retirement_age in self.annuity_factor_table:
            return self.annuity_factor_table[retirement_age]
        
        # 如果年齡超出表格範圍，使用邊界值
        if retirement_age < min(self.annuity_factor_table.keys()):
            return self.annuity_factor_table[min(self.annuity_factor_table.keys())]
        if retirement_age > max(self.annuity_factor_table.keys()):
            return self.annuity_factor_table[max(self.annuity_factor_table.keys())]
        
        # 線性插值計算
        ages = sorted(self.annuity_factor_table.keys())
        for i in range(len(ages) - 1):
            if ages[i] < retirement_age < ages[i + 1]:
                age1, age2 = ages[i], ages[i + 1]
                factor1, factor2 = self.annuity_factor_table[age1], self.annuity_factor_table[age2]
                # 線性插值
                factor = factor1 + (factor2 - factor1) * (retirement_age - age1) / (age2 - age1)
                print(f"📊 使用插值計算年金現值因子：{factor:.2f}（介於{age1}歲:{factor1:.2f}與{age2}歲:{factor2:.2f}之間）")
                return factor
        
        # 備用方案：使用最接近的年齡
        closest = min(self.annuity_factor_table.keys(), key=lambda x: abs(x - retirement_age))
        print(f"⚠️ 使用最接近年齡 {closest} 的年金現值因子：{self.annuity_factor_table[closest]:.2f}")
        return self.annuity_factor_table[closest]

    def adjust_for_inflation(self, amount: float, years: int, inflation_rate: Optional[float] = None) -> float:
        """
        計算考慮通膨後的實質購買力
        
        Args:
            amount: 名目金額
            years: 年數
            inflation_rate: 通膨率（%），預設使用class預設值
            
        Returns:
            float: 實質購買力金額
        """
        if inflation_rate is None:
            inflation_rate = self.default_inflation_rate
        return amount / ((1 + inflation_rate / 100) ** years)

    def calculate_labor_pension_accurate(self, current_principal: float, monthly_salary: float,
                                         employer_rate: float, employee_rate: float,
                                         years_to_retirement: int, annual_return_rate: float,
                                         retirement_age: int, current_contributed_years: int,
                                         salary_growth_rate: float = 0.0, verbose: bool = True) -> Dict:
        """
        精確計算勞退個人專戶退休金累積與預估月領金額

        Args:
            current_principal (float): 現在勞退帳戶已累積本金
            monthly_salary (float): 目前月薪（每年會依薪資年成長率成長）
            employer_rate (float): 雇主提繳率（%）
            employee_rate (float): 自願提繳率（%）
            years_to_retirement (int): 距離退休還有幾年
            annual_return_rate (float): 投資年報酬率（%）
            retirement_age (int): 預計退休年齡
            current_contributed_years (int): 已提繳年數（過去）
            salary_growth_rate (float): 薪資年成長率（%），預設為 0
            verbose (bool): 是否輸出詳細說明

        Returns:
            dict: 包含是否可月領、預估總額與月領金額等資訊
        """
        
        # 輸入驗證
        validation_errors = self.validate_inputs(
            monthly_salary=monthly_salary,
            years_to_retirement=years_to_retirement,
            employer_rate=employer_rate,
            employee_rate=employee_rate,
            current_contributed_years=current_contributed_years,
            retirement_age=retirement_age
        )
        
        result = {
            'eligible_age': 60,
            'can_monthly_payment': False,
            'final_amount': 0,
            'lump_sum': 0,
            'monthly_pension': 0,
            'monthly_years': 0,
            'real_value': 0,  # 考慮通膨的實質價值
            'validation_errors': validation_errors,
            'contribution_details': []  # 提繳明細
        }

        if validation_errors:
            if verbose:
                for error in validation_errors:
                    print(f"❌ {error}")
            return result

        if years_to_retirement < 0 or monthly_salary <= 0:
            return result

        # 使用政府保證最低收益率
        actual_rate = max(annual_return_rate, self.min_guaranteed_return)
        total_contribution_rate = (employer_rate + employee_rate) / 100
        future_value = current_principal

        # 逐年計算，考慮薪資成長和提繳工資上限
        contribution_details = []
        for year in range(1, years_to_retirement + 1):
            future_salary = monthly_salary * ((1 + salary_growth_rate / 100) ** (year - 1))
            # 套用勞退提繳工資上限
            capped_salary = min(future_salary, self.max_labor_pension_salary)
            annual_contribution = capped_salary * total_contribution_rate * 12
            
            # 記錄每年提繳詳情
            contribution_details.append({
                'year': year,
                'monthly_salary': future_salary,
                'capped_salary': capped_salary,
                'annual_contribution': annual_contribution,
                'account_balance_before': future_value,
                'investment_return': future_value * (actual_rate / 100)
            })
            
            future_value = future_value * (1 + actual_rate / 100) + annual_contribution

        result['final_amount'] = result['lump_sum'] = future_value
        result['contribution_details'] = contribution_details
        
        # 計算實質購買力
        result['real_value'] = self.adjust_for_inflation(future_value, years_to_retirement)

        # 判斷月領資格：年資≥15年 且 年滿60歲
        total_years = current_contributed_years + years_to_retirement
        if total_years >= 15 and retirement_age >= 60:
            result['can_monthly_payment'] = True
            factor = self.get_annuity_factor(retirement_age)
            monthly_pension = future_value / factor / 12
            result['monthly_pension'] = monthly_pension
            result['monthly_years'] = factor

        if verbose:
            print("\n📘【勞退個人專戶計算結果】")
            print(f"目前本金: ${current_principal:,.0f}，月薪: ${monthly_salary:,.0f}")
            print(f"薪資年成長率: {salary_growth_rate:.1f}%，實際報酬率: {actual_rate:.2f}%")
            if monthly_salary > self.max_labor_pension_salary:
                print(f"⚠️ 月薪超過提繳工資上限 ${self.max_labor_pension_salary:,.0f}，以上限計算")
            print(f"退休時帳戶預估金額: ${future_value:,.0f}")
            print(f"考慮通膨後實質價值: ${result['real_value']:,.0f}")
            
            if result['can_monthly_payment']:
                print(f"✅ 符合月領資格（年資 {total_years} 年 ≥ 15年，年齡 {retirement_age} 歲 ≥ 60歲）")
                print(f"👉 預估月領金額: ${result['monthly_pension']:,.0f}（約可支應 {factor:.1f} 年的退休期間）")
            else:
                reasons = []
                if total_years < 15:
                    reasons.append(f"年資不足（{total_years} < 15年）")
                if retirement_age < 60:
                    reasons.append(f"未滿60歲")
                print(f"⚠️ 未達月領資格：{', '.join(reasons)}，僅可一次領取")

        return result

    def calculate_labor_insurance_pension(self, avg_salary: float, insurance_years: int, 
                                          claim_age: int, birth_year: int, verbose: bool = True) -> Dict:
        """
        勞保老年年金試算（v4.3 - 未來模擬版）
        如果申請年齡不足，會自動以法定請領年齡為基準進行模擬計算。
        """
        legal_age = self.legal_retirement_age(birth_year)
        result = {
            'legal_age': legal_age,
            'eligible': False,
            'monthly_pension': 0,
            'formula': '',
            'formula_a': 0,
            'formula_b': 0,
            'remark': '',
            'is_projected_at_legal_age': False, # [v4.3] 標記是否為模擬計算
            'early_retirement_penalty': 0,
            'delay_retirement_bonus': 0
        }

        if avg_salary <= 0 or insurance_years < 0:
            result['remark'] = "❌ 輸入參數錯誤"
            return result
        
        if insurance_years < 15:
            result['remark'] = f"❌ 年資不足：勞保年資為 {insurance_years} 年，需滿15年才可請領"
            return result

        # [v4.3 核心邏輯] 使用法定年齡作為計算基準，而非使用者當下選擇的退休年齡
        effective_claim_age = max(claim_age, legal_age)
        if claim_age < legal_age:
            result['is_projected_at_legal_age'] = True

        avg_salary = min(avg_salary, self.max_labor_insurance_salary)
        
        # A式
        if insurance_years <= 15:
            formula_a = avg_salary * insurance_years * 0.00775 + 3000
        else:
            formula_a = (avg_salary * 15 * 0.00775 + 
                         avg_salary * (insurance_years - 15) * 0.0155 + 3000)
        # B式
        formula_b = avg_salary * insurance_years * 0.0155
        
        base_pension = max(formula_a, formula_b)
        
        # [v4.3 修正] 以 effective_claim_age 計算延後加給
        delay_years = max(0, effective_claim_age - legal_age)
        if delay_years > 0:
            delay_rate = min(delay_years * 0.04, 0.20)
            delay_bonus = base_pension * delay_rate
            result['delay_retirement_bonus'] = delay_bonus
            base_pension += delay_bonus

        result['monthly_pension'] = base_pension
        result['eligible'] = True # 因為已滿足年資條件，在法定年齡時必定符合資格
        result['formula'] = 'A式' if formula_a >= formula_b else 'B式'
        result['formula_a'] = formula_a
        result['formula_b'] = formula_b
                
        return result


    def calculate_replacement_ratio_suggestions(self, replacement_ratio: float, 
                                              current_salary: float, years_to_retirement: int) -> Dict:
        """
        替代率分析與建議
        """
        suggestions = []
        target_ratios = [60, 70, 80]
        
        for target in target_ratios:
            if replacement_ratio < target:
                gap = target - replacement_ratio
                needed_monthly = current_salary * gap / 100
                total_gap = needed_monthly * 12 * 20  # 假設退休後20年
                suggestions.append({
                    'target_ratio': target,
                    'gap_percentage': gap,
                    'needed_monthly_saving': needed_monthly,
                    'total_retirement_asset_needed': total_gap,
                    'description': f"達到{target}%替代率需每月增加儲蓄 ${needed_monthly:,.0f}"
                })
                break

        # 評估建議
        if replacement_ratio < 50:
            level = "不足"
            color = "🔴"
        elif replacement_ratio < 70:
            level = "普通"
            color = "🟡"
        elif replacement_ratio < 80:
            level = "良好"
            color = "🟢"
        else:
            level = "優秀"
            color = "🟢"

        return {
            'replacement_ratio': replacement_ratio,
            'level': level,
            'color': color,
            'suggestions': suggestions
        }

    def sensitivity_analysis(self, base_params: Dict, verbose: bool = True) -> Dict:
        """
        敏感度分析：不同報酬率下的退休金變化
        """
        return_rates = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        results = {}
        
        for rate in return_rates:
            params = base_params.copy()
            params['annual_return_rate'] = rate
            result = self.calculate_labor_pension_accurate(**params, verbose=False)
            results[f"{rate}%"] = {
                'final_amount': result['final_amount'],
                'monthly_pension': result['monthly_pension'] if result['can_monthly_payment'] else 0,
                'real_value': result['real_value']
            }
        
        if verbose:
            print("\n📊【敏感度分析】報酬率對退休金的影響")
            print("年報酬率 | 帳戶總額 | 月領金額 | 實質價值")
            print("-" * 50)
            for rate_str, data in results.items():
                print(f"{rate_str:>8} | ${data['final_amount']:>8,.0f} | ${data['monthly_pension']:>8,.0f} | ${data['real_value']:>8,.0f}")
        
        return results

# --- [v4.1] 計算引擎結束 ---