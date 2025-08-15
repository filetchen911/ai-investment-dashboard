# file: scraper-function/main.py (v5.3.0 - 模型整合版)

import os
import firebase_admin
from firebase_admin import firestore
from fredapi import Fred
import yfinance as yf
from dbnomics import fetch_series
import pandas as pd
import datetime
import pytz
import functions_framework
from _version import __version__

# --- 初始化 ---
try:
    if not firebase_admin._apps:
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
        print(f"  ❌ 抓取 yfinance 數據時發生錯誤: {e}")
        return None

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


# --- Helper Function 3: [最終修正版] FRED 所有指標抓取 ---
def get_fred_indicators(fred_instance):
    """
    [最終版] 從 FRED 抓取並正確計算所有需要的總經指標。
    """
    print("\n> 正在從 FRED 抓取所有總經指標...")
    
    # [修正] 合併了舊指標與新指標，共六項
    fred_tickers = {
        "核心 PCE 物價指數年增率 (%)": "PCEPILFE",
        "非農就業人數變化 (萬人)": "PAYEMS",
        "初領失業救濟金人數 (萬人)": "ICSA",
        "失業率 (%)": "UNRATE",
        "密大消費者信心指數": "UMCSENT",
        "美國零售銷售年增率 (%)": "RSAFS"
    }
    
    results = {}
    # 擴大抓取時間範圍到25個月前，以確保有足夠數據計算
    start_date = pd.to_datetime('today') - pd.DateOffset(months=25)
    
    for name, ticker_id in fred_tickers.items():
        try:
            series = fred_instance.get_series(ticker_id, observation_start=start_date)

            # --- 針對不同指標進行客製化計算 ---
            if ticker_id in ['PCEPILFE', 'RSAFS']:
                # 計算年增率
                series = series.pct_change(periods=12) * 100
                series = series.round(2) # [修正 3] 四捨五入到小數點後兩位
            elif ticker_id == 'PAYEMS':
                # 計算月變動
                series = series.diff()
            
            series.dropna(inplace=True)

            # 單位換算 (僅針對非農和初領失業金)
            if ticker_id == 'PAYEMS': # 單位: 千人 -> 萬人
                series = series / 10
            elif ticker_id == 'ICSA': # 單位: 人 -> 萬人
                series = series / 10000 # [修正 2] 使用正確的換算單位

            results[name] = series
            print(f"  ✅ 成功處理 FRED 指標: {name}")
        except Exception as e:
            print(f"  ❌ 處理 FRED 指標失敗: {name} - {e}")
            results[name] = None
    return results

# --- Helper Function 4: DBnomics ISM 指標抓取 ---
def get_ism_pmi_from_dbnomics():
    print("\n> 正在從 DBnomics 抓取 ISM PMI 系列指標...")
    series_map = {"製造業 PMI": "ISM/pmi/pm", "新訂單": "ISM/neword/in", "生產": "ISM/production/in", "就業": "ISM/employment/in", "庫存": "ISM/inventories/in", "非製造業 PMI": "ISM/nm-pmi/pm", "客戶端存貨": "ISM/cusinv/in"}
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
        final_df = pd.concat(all_series, axis=1); 
        final_df.index = pd.to_datetime(final_df.index)
        final_df.index.name = "Date"
        final_df.sort_index(inplace=True)
        print(f"  ✅ 成功合併了 {len(all_series)} 個 ISM 指標的數據。")
        return final_df.tail(12)
        
    except Exception as e:
        print(f"  ❌ 合併 ISM 數據時失敗: {e}"); return None

# --- Helper Function 5: [新增] 策略訊號判斷 ---
def check_signals(kdj_weekly, kdj_monthly, vix, ism_pmi):
    signals = {"mid_term_pullback": False, "inventory_cycle": False}
    J_OVERSOLD = 20; VIX_FEAR = 25; PMI_CONTRACTION = 48

    try:
        latest_j_weekly = kdj_weekly['J'].iloc[-1]
        latest_j_monthly = kdj_monthly['J'].iloc[-1]
        latest_vix = vix.iloc[-1]
        latest_pmi = ism_pmi['製造業 PMI'].iloc[-1]

        # 判斷中期回檔訊號
        if latest_j_weekly < J_OVERSOLD and latest_vix > VIX_FEAR:
            signals["mid_term_pullback"] = True

        # 判斷庫存週期訊號
        if latest_j_monthly < J_OVERSOLD and latest_vix > VIX_FEAR and latest_pmi < PMI_CONTRACTION:
            signals["inventory_cycle"] = True

    except (IndexError, TypeError) as e:
        print(f"  - 訊號判斷時數據不足或出錯: {e}")
    
    return signals

# --- 主函式 (總指揮) ---
@functions_framework.http
def run_scraper(request):
    print(f"--- 投資模型數據抓取器 (v{__version__}) 開始執行 ---")
    
    final_data_to_store = {"signals": {}}
    
    # 1. 抓取 yfinance 數據 (市場價格 & 美國 VIX)
    market_tickers = {"台股加權指數": "^TWII", "標普500指數": "^GSPC", "納斯達克100指數": "^IXIC", "費城半導體指數": "^SOX"}
    all_price_data = get_yfinance_data(list(market_tickers.values()) + ['^VIX'])

    # 2. 抓取 FRED & DBnomics 數據
    try:
        fred = Fred(api_key=FRED_API_KEY)
        fred_data = get_fred_indicators(fred)
    except Exception as e:
        print(f"  ❌ FRED 初始化失敗: {e}"); fred_data = {}
    ism_data = get_ism_pmi_from_dbnomics()

    # 3. 為每個市場計算指標與訊號
    if all_price_data is not None:
        final_data_to_store['kdj_indicators'] = {}
        us_vix_series = all_price_data['Close']['^VIX'].dropna()
        
        for name, ticker in market_tickers.items():
            market_price_df = all_price_data.loc[:, (slice(None), ticker)]
            market_price_df.dropna(how='all', inplace=True)
            kdj_weekly = calculate_kdj(market_price_df, 'W-FRI')
            kdj_monthly = calculate_kdj(market_price_df, 'ME')
            final_data_to_store['kdj_indicators'][name] = {
                "weekly": {d.strftime('%Y-%m-%d'): v for d, v in kdj_weekly.tail(3).to_dict('index').items()} if kdj_weekly is not None else None,
                "monthly": {d.strftime('%Y-%m-%d'): v for d, v in kdj_monthly.tail(3).to_dict('index').items()} if kdj_monthly is not None else None,
            }
            
            # [新增] 執行訊號判斷
            if kdj_weekly is not None and kdj_monthly is not None and ism_data is not None:
                final_data_to_store['signals'][name] = check_signals(kdj_weekly, kdj_monthly, us_vix_series, ism_data)

        final_data_to_store['sentiment_vix_us'] = {d.strftime('%Y-%m-%d'): v for d, v in us_vix_series.tail().to_dict().items()}

    # 4. 整理總經數據
    final_data_to_store['macro_fred'] = {k: {d.strftime('%Y-%m-%d'): val for d, val in v.to_dict().items()} for k, v in fred_data.items() if v is not None}
    if ism_data is not None:
        final_data_to_store['macro_ism_pmi'] = {d.strftime('%Y-%m-%d'): v for d, v in ism_data.to_dict('index').items()}

    # 5. 統一寫入 Firestore
    db = firestore.client()
    taipei_tz = pytz.timezone('Asia/Taipei')
    doc_id = datetime.datetime.now(taipei_tz).strftime("%Y-%m-%d")
    doc_ref = db.collection('daily_model_data').document(doc_id)
    expire_at_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)
    
    firestore_document = { "updated_at": firestore.SERVER_TIMESTAMP, "expireAt": expire_at_time, "version": __version__, "data": final_data_to_store }
    doc_ref.set(firestore_document)
    
    success_message = f"成功抓取、計算並儲存所有模型數據到 Firestore 的文件 '{doc_id}' 中！"
    print(f"--- {success_message} ---")
    return {"status": "success", "message": success_message, "version": __version__}, 200