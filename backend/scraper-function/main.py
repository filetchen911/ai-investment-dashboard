# file: scraper-function/main.py (v5.3.0-rc2 - 最終數據整合版)

import os
import firebase_admin
from firebase_admin import firestore
from fredapi import Fred
import yfinance as yf
from dbnomics import fetch_series
import pandas as pd
import datetime
import functions_framework
import pytz # [時區修正] 新增 pytz 函式庫
from _version import __version__

# --- 初始化 ---
try:
    firebase_admin.initialize_app()
except ValueError: pass
FRED_API_KEY = os.environ.get('FRED_API_KEY')
pd.set_option('display.float_format', lambda x: '%.2f' % x)


# --- Helper Function 1: yfinance 數據抓取 ---
def get_yfinance_data(tickers, period="10y"):
    print(f"\n> 正在從 yfinance 抓取 {len(tickers)} 個市場的數據...")
    try:
        data = yf.download(tickers, period=period, auto_adjust=True)
        if data.empty: raise ValueError(f"未能抓取到任何 yfinance 數據 for tickers: {tickers}")
        print(f"  ✅ 成功抓取 yfinance 數據。")
        return data
    except Exception as e:
        print(f"  ❌ 抓取 yfinance 數據時發生錯誤: {e}"); return None

# --- Helper Function 2: KDJ 指標計算 ---
def calculate_kdj(price_data, time_period='W-FRI'):
    try:
        df = price_data.copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0].lower() for col in df.columns]
        else:
            df.columns = [col.lower() for col in df.columns]
        period_df = df.resample(time_period).agg({'high': 'max', 'low': 'min', 'close': 'last', 'open': 'first'})
        low_min = period_df['low'].rolling(window=9, min_periods=1).min()
        high_max = period_df['high'].rolling(window=9, min_periods=1).max()
        rsv = (period_df['close'] - low_min) / (high_max - low_min) * 100
        rsv.dropna(inplace=True)
        k = rsv.ewm(com=2, adjust=False).mean(); d = k.ewm(com=2, adjust=False).mean(); j = 3 * k - 2 * d
        return pd.DataFrame({'K': k, 'D': d, 'J': j}).dropna()
    except Exception as e:
        print(f"  - ❌ 計算 {time_period} KDJ 時發生錯誤: {e}"); return None

# --- Helper Function 3: DBnomics ISM 指標抓取 ---
# file: scraper-function/main.py

# --- Helper Function 4: DBnomics ISM 指標抓取 ---
def get_ism_pmi_from_dbnomics():
    """
    [v5.3.0-rc2 修正版] 從 DBnomics 抓取 ISM PMI 系列指標，並確保日期索引為 datetime 格式。
    """
    print("\n> 正在從 DBnomics 抓取 ISM PMI 系列指標...")
    series_map = {
        "製造業 PMI": "ISM/pmi/pm", "新訂單": "ISM/neword/in", "生產": "ISM/production/in",
        "就業": "ISM/employment/in", "庫存": "ISM/inventories/in", "非製造業 PMI": "ISM/nm-pmi/pm",
        "客戶端存貨": "ISM/cusinv/in"
    }
    all_series = []
    for name, series_id in series_map.items():
        try:
            df = fetch_series(series_id)
            series = df.set_index('original_period')['value'].rename(name)
            all_series.append(series)
        except Exception:
            print(f"  - 注意：抓取 {name} ({series_id}) 失敗，將跳過此項。")
            continue
    if not all_series: return None
    try:
        final_df = pd.concat(all_series, axis=1)
        
        # --- [v5.3.0-rc2 修正] ---
        # 將字串格式的索引，轉換為標準的 DatetimeIndex 格式
        final_df.index = pd.to_datetime(final_df.index)
        # --- [修正結束] ---

        final_df.index.name = "Date"
        final_df.sort_index(inplace=True)
        print(f"  ✅ 成功合併了 {len(all_series)} 個 ISM 指標的數據。")
        return final_df.tail(12)
    except Exception as e:
        print(f"  ❌ 合併 ISM 數據時失敗: {e}")
        return None
        
# --- Helper Function 4: [整合版] FRED 所有指標抓取 ---
def get_all_fred_data(fred_instance):
    print("\n> 正在從 FRED 抓取所有總經指標...")
    # 合併了舊指標與新指標
    fred_tickers = {
        "核心 PCE 物價指數年增率 (%)": "PCEPILFE", "非農就業人數變化 (萬人)": "PAYEMS",
        "初領失業救濟金人數 (萬人)": "ICSA", "失業率 (%)": "UNRATE",
        "密大消費者信心指數": "UMCSENT", "美國零售銷售年增率 (%)": "RSAFS"
    }
    economic_data_series = []
    start_date = (datetime.date.today() - pd.DateOffset(months=25)).strftime('%Y-%m-%d')
    for name, ticker_id in fred_tickers.items():
        try:
            series = fred_instance.get_series(ticker_id, observation_start=start_date)
            # --- 針對不同指標進行客製化計算 ---
            if ticker_id in ['PCEPILFE', 'RSAFS']:
                series = series.pct_change(periods=12) * 100
            elif ticker_id == 'PAYEMS':
                series = series.diff()
            series.dropna(inplace=True)
            if ticker_id == 'ICSA': series = series.tail(26) 
            else: series = series.tail(6)
            if not series.empty:
                values_list = [{'date': date.strftime("%Y-%m-%d"), 'value': round(float(value) / 10 if "(萬人)" in name else float(value), 2)} for date, value in series.items()]
                economic_data_series.append({"source": "FRED API", "event": name, "values": values_list})
        except Exception as e:
            print(f"  - ❌ 處理 FRED 指標 {name} 失敗: {e}")
    print(f"  ✅ 成功處理了 {len(economic_data_series)} 個 FRED 指標。")
    return economic_data_series


@functions_framework.http
def run_scraper(request):
    """
    [v5.3.0] 作為總指揮，抓取並計算所有指標，並統一存入 Firestore。
    """
    print(f"--- 投資模型數據抓取器 (v{__version__}) 開始執行 ---")
    final_data_to_store = {}
    
    # 1. 抓取 yfinance 數據 (市場價格 & 美國 VIX)
    market_tickers = {"台股加權指數": "^TWII", "標普500指數": "^GSPC", "納斯達克100指數": "^IXIC", "費城半導體指數": "^SOX"}
    all_price_data = get_yfinance_data(list(market_tickers.values()) + ['^VIX'])

    # 2. 計算 J 值 & 處理 VIX
    if all_price_data is not None:
        final_data_to_store['kdj_indicators'] = {}
        for name, ticker in market_tickers.items():
            market_price_df = all_price_data.loc[:, (slice(None), ticker)]
            market_price_df.dropna(how='all', inplace=True)
            kdj_weekly = calculate_kdj(market_price_df, 'W-FRI')
            kdj_monthly = calculate_kdj(market_price_df, 'ME')
            final_data_to_store['kdj_indicators'][name] = {
                "weekly": {d.strftime('%Y-%m-%d'): v for d, v in kdj_weekly.tail(3).to_dict('index').items()} if kdj_weekly is not None else None,
                "monthly": {d.strftime('%Y-%m-%d'): v for d, v in kdj_monthly.tail(3).to_dict('index').items()} if kdj_monthly is not None else None,
            }
        vix_df = all_price_data['Close'][['^VIX']].dropna().tail()
        final_data_to_store['sentiment_vix_us'] = {d.strftime('%Y-%m-%d'): v for d, v in vix_df.to_dict()['^VIX'].items()}

    # 3. 抓取所有 FRED 數據 (包含舊指標)
    try:
        fred = Fred(api_key=FRED_API_KEY)
        # 將舊指標與新指標的結果合併
        final_data_to_store['macro_fred_indicators'] = get_all_fred_data(fred)
    except Exception as e:
        print(f"  ❌ FRED 初始化或處理失敗: {e}")

    # 4. 抓取 DBnomics 數據
    ism_data = get_ism_pmi_from_dbnomics()
    if ism_data is not None:
        final_data_to_store['macro_ism_pmi'] = {d.strftime('%Y-%m-%d'): v for d, v in ism_data.to_dict('index').items()}

    # 5. 統一寫入 Firestore
    db = firestore.client()
    # --- [時區修正] ---
    # 使用台北時區來產生當日的文件 ID，以解決 UTC 日期問題
    taipei_tz = pytz.timezone('Asia/Taipei')
    doc_id = datetime.datetime.now(taipei_tz).strftime("%Y-%m-%d")
    # --- [修正結束] ---
    doc_ref = db.collection('daily_model_data').document(doc_id)
    expire_at_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)
    
    firestore_document = { "updated_at": firestore.SERVER_TIMESTAMP, "expireAt": expire_at_time, "version": __version__, "data": final_data_to_store }
    doc_ref.set(firestore_document)
    
    success_message = f"成功抓取並整合所有模型數據到 Firestore！"
    print(f"--- {success_message} ---")
    return {"status": "success", "message": success_message, "version": __version__}, 200