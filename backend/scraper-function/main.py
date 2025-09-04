# file: backend/scraper-function/main.py (v5.4.0-rc1 - 數據邏輯修正版)

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


# --- 數據抓取與計算函式庫 ---

def get_yfinance_data(tickers, period="10y"):
    print(f"\n> [yfinance] 正在抓取 {len(tickers)} 個市場的數據...")
    try:
        data = yf.download(tickers, period=period, auto_adjust=True, progress=False)
        if data.empty: raise ValueError("yfinance 未返回任何數據")
        print(f"  ✅ [yfinance] 成功抓取數據。")
        return data
    except Exception as e:
        print(f"  ❌ [yfinance] 抓取時發生錯誤: {e}"); return None

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

def get_fred_data(fred_instance):
    """
    [最終整合版] 從 FRED 統一抓取並計算所有模型需要的總經指標。
    """
    print("\n> [FRED] 正在抓取所有總經指標...")
    
    # [修正] 整合並去除了重複的 Ticker，只抓取原始數據
    fred_tickers = {
        "核心 PCE 物價指數": "PCEPILFE", "非農就業人數": "PAYEMS",
        "初領失業救濟金人數": "ICSA", "失業率": "UNRATE",
        "密大消費者信心指數": "UMCSENT", "零售銷售": "RSAFS",
        "實質GDP季增年率(SAAR)": "A191RL1Q225SBEA", "聯邦基金利率": "FEDFUNDS",
        "實質個人消費支出": "PCEC96", "FOMC利率點陣圖中位數": "FEDTARMD"
    }
    
    raw_results = {}
    start_date = pd.to_datetime('today') - pd.DateOffset(years=2)
    
    # 步驟 1: 先抓取所有原始數據
    for name, ticker_id in fred_tickers.items():
        try:
            raw_results[name] = fred_instance.get_series(ticker_id, observation_start=start_date).dropna()
        except Exception as e:
            print(f"  - ❌ 抓取 FRED 指標 {name} 失敗: {e}")
            
    # 步驟 2: 根據原始數據，計算我們需要的最終指標
    final_results = {}
    
    # 需要計算年增率的指標
    for name, raw_name in [("核心 PCE 物價指數年增率 (%)", "核心 PCE 物價指數"), 
                           ("美國零售銷售年增率 (%)", "零售銷售"),
                           ("實質個人消費支出年增率 (%)", "實質個人消費支出")]:
        if raw_name in raw_results:
            final_results[name] = (raw_results[raw_name].pct_change(periods=12) * 100).round(2)

    # 需要計算月變動的指標
    if "非農就業人數" in raw_results:
        final_results["非農就業人數變化 (萬人)"] = (raw_results["非農就業人數"].diff() / 10).round(2)

    # 需要轉換單位的指標
    if "初領失業救濟金人數" in raw_results:
        final_results["初領失業救濟金人數 (萬人)"] = (raw_results["初領失業救濟金人數"] / 10000).round(2)

    # 不需任何計算的指標，直接沿用
    for name in ["失業率", "密大消費者信心指數", "實質GDP季增年率(SAAR)", "聯邦基金利率", "FOMC利率點陣圖中位數"]:
         if name in raw_results:
             final_results[name] = raw_results[name]

    # 保留原始數據供 tech_model 使用
    final_results["零售銷售_原始"] = raw_results.get("零售銷售")
    final_results["實質個人消費支出_原始"] = raw_results.get("實質個人消費支出")

    print(f"  ✅ [FRED] 成功處理了 {len(final_results)} 個最終指標。")
    return final_results

def get_dbnomics_data():
    """
    [v5.4.0 修正版] 從 DBnomics 抓取 ISM & OECD 指標，並確保日期索引為 datetime 格式。
    """
    print("\n> [DBnomics] 正在抓取 ISM & OECD 指標...")
    series_map = {
        "ISM 製造業PMI": "ISM/pmi/pm", "新訂單": "ISM/neword/in", "客戶端存貨": "ISM/cusinv/in",
        "OECD 美國領先指標": "OECD/DSD_STES@DF_CLI/USA.M.LI.IX._Z.AA.IX._Z.H"
    }
    results = {}

    # 定義我們要抓取的起始日期 (兩年前)
    start_date = pd.to_datetime('today') - pd.DateOffset(years=2)

    for name, series_id in series_map.items():
        try:
            df = fetch_series(series_id)
            series = df.set_index('original_period')['value'].rename(name)        
            series.index = pd.to_datetime(series.index)

            # 在收到完整數據後，只選取在 start_date 之後的數據
            series = series[series.index >= start_date]

            results[name] = series
        except Exception:
            print(f"  - 注意：抓取 {name} ({series_id}) 失敗，跳過。")
    print(f"  ✅ [DBnomics] 成功處理了 {len(results)} 個指標。")
    return results    

def get_mag7_financials():
    print("\n> [yfinance] 正在抓取 Mag7 & TSM 財報數據...")
    mag7_symbols = ['MSFT', 'AAPL', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META', 'TSM']
    financial_data = {}
    for symbol in mag7_symbols:
        try:
            ticker = yf.Ticker(symbol)
            financial_data[symbol] = {
                'quarterly_financials': ticker.quarterly_financials,
                'quarterly_cashflow': ticker.quarterly_cashflow
            }
        except Exception:
            print(f"  - 注意：抓取 {symbol} 財報失敗，跳過。")
    print(f"  ✅ [yfinance] 成功抓取了 {len(financial_data)} 家公司的財報。")
    return financial_data

# --- 模型計算函式 ---

def run_j_vix_model(kdj_data, vix_data):
    print("\n> [模型一] 正在執行 J值+VIX 擇時模型...")
    signals = {}
    J_OVERSOLD = 20; VIX_FEAR = 25
    for market_name, kdj in kdj_data.items():
        try:
            latest_j_weekly = kdj['weekly']['J'].iloc[-1]
            latest_j_monthly = kdj['monthly']['J'].iloc[-1]
            latest_vix = vix_data['^VIX'].iloc[-1]
            signals[market_name] = {
                "mid_term_pullback": bool(latest_j_weekly < J_OVERSOLD and latest_vix > VIX_FEAR),
                "inventory_cycle": bool(latest_j_monthly < J_OVERSOLD and latest_vix > VIX_FEAR)
            }
        except Exception:
            signals[market_name] = {"mid_term_pullback": False, "inventory_cycle": False}
    print("  ✅ [模型一] 執行完畢。")
    return signals

def run_tech_model(financials, fred_data, dbnomics_data):
    print("\n> [模型二] 正在執行美股科技股總經模型 (V7.3)...")
    data = {}
    scores = {"Mag7營收年增率": 0, "資本支出增長率": 0, "關鍵領先指標": 0, "資金面與流動性": 0, "GDP季增率": 0, "ISM製造業PMI": 0, "美國消費需求綜合": 0}
    
    try:
        # 微觀-Mag7營收
        total_curr_rev, total_prev_rev = 0, 0
        for s in ['MSFT', 'AAPL', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META']:
            if s in financials and "Total Revenue" in financials[s]['quarterly_financials'].index:
                rev = financials[s]['quarterly_financials'].loc["Total Revenue"]
                if len(rev) >= 5: total_curr_rev += rev.iloc[0]; total_prev_rev += rev.iloc[4]
        data['mag7_agg_revenue_growth'] = (total_curr_rev - total_prev_rev) / total_prev_rev if total_prev_rev > 0 else 0
        if data['mag7_agg_revenue_growth'] >= 0.15: scores['Mag7營收年增率'] = 30
        elif data['mag7_agg_revenue_growth'] >= 0.10: scores['Mag7營收年增率'] = 25
        elif data['mag7_agg_revenue_growth'] >= 0.05: scores['Mag7營收年增率'] = 15
        elif data['mag7_agg_revenue_growth'] >= 0: scores['Mag7營收年增率'] = 8

        # 微觀-資本支出
        total_curr_capex, total_prev_capex = 0, 0
        for s in ['MSFT', 'AAPL', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META']:
             if s in financials and "Capital Expenditure" in financials[s]['quarterly_cashflow'].index:
                capex = financials[s]['quarterly_cashflow'].loc["Capital Expenditure"]
                if len(capex) >= 5: total_curr_capex += abs(capex.iloc[0]); total_prev_capex += abs(capex.iloc[4])
        data['mag7_agg_capex_growth'] = (total_curr_capex - total_prev_capex) / total_prev_capex if total_prev_capex > 0 else 0
        if data['mag7_agg_capex_growth'] >= 0.25: scores['資本支出增長率'] = 20
        elif data['mag7_agg_capex_growth'] >= 0.15: scores['資本支出增長率'] = 16
        elif data['mag7_agg_capex_growth'] >= 0.05: scores['資本支出增長率'] = 10
        elif data['mag7_agg_capex_growth'] >= 0: scores['資本支出增長率'] = 5

        # 微觀-關鍵領先指標
        tsm_score = 0
        if 'TSM' in financials and "Total Revenue" in financials['TSM']['quarterly_financials'].index:
            rev = financials['TSM']['quarterly_financials'].loc["Total Revenue"]
            data['tsm_growth'] = (rev.iloc[0] - rev.iloc[4]) / rev.iloc[4] if len(rev) >= 5 else 0
            if data['tsm_growth'] >= 0.20: tsm_score = 6
            elif data['tsm_growth'] >= 0.10: tsm_score = 4
            elif data['tsm_growth'] >= 0: tsm_score = 2
        oecd_cli = dbnomics_data.get("OECD 美國領先指標")
        oecd_score = 0
        if oecd_cli is not None:
            data['oecd_cli_latest'] = oecd_cli.iloc[-1]
            if data['oecd_cli_latest'] >= 101: oecd_score += 4
            elif data['oecd_cli_latest'] >= 100.5: oecd_score += 3
            elif data['oecd_cli_latest'] >= 100: oecd_score += 2
            elif data['oecd_cli_latest'] >= 99.5: oecd_score += 1
            if len(oecd_cli) >= 3 and oecd_cli.iloc[-1] > oecd_cli.iloc[-2] and oecd_cli.iloc[-2] > oecd_cli.iloc[-3]: oecd_score += 2
            elif len(oecd_cli) >= 2 and oecd_cli.iloc[-1] > oecd_cli.iloc[-2]: oecd_score += 1
        ism_diff = dbnomics_data.get("新訂單", pd.Series([0])).iloc[-1] - dbnomics_data.get("客戶端存貨", pd.Series([0])).iloc[-1]
        data['ism_diff'] = ism_diff
        ism_diff_score = 0
        if ism_diff >= 10: ism_diff_score = 3
        elif ism_diff >= 5: ism_diff_score = 2.5
        elif ism_diff >= 0: ism_diff_score = 2
        elif ism_diff >= -5: ism_diff_score = 1
        scores['關鍵領先指標'] = tsm_score + oecd_score + ism_diff_score

        # 總經-資金面
        rate = fred_data.get('聯邦基金利率').iloc[-1]
        data['current_fed_rate'] = rate
        rate_level_score = 0
        if rate < 3: rate_level_score = 6
        elif rate < 4: rate_level_score = 5
        elif rate < 5: rate_level_score = 3
        elif rate < 6: rate_level_score = 2
        dot_plot = fred_data.get('FOMC利率點陣圖中位數')
        fomc_score = 0
        if dot_plot is not None and len(dot_plot) >= 3:
            change_bp = (dot_plot.iloc[-2] - rate) * 100
            data['fomc_change_bp'] = change_bp
            if change_bp < -200: fomc_score = 6
            elif -200 <= change_bp <= -100: fomc_score = 5
            elif -100 < change_bp < 0: fomc_score = 3
            elif 0 <= change_bp <= 25: fomc_score = 2
        scores['資金面與流動性'] = rate_level_score + fomc_score

        # 總經-GDP
        gdp = fred_data.get('實質GDP季增年率(SAAR)').iloc[-1]
        data['gdp_growth'] = gdp
        if gdp >= 3: scores['GDP季增率'] = 9
        elif gdp >= 2: scores['GDP季增率'] = 7
        elif gdp >= 1: scores['GDP季增率'] = 4
        elif gdp >= 0: scores['GDP季增率'] = 2

        # 總經-PMI
        pmi = dbnomics_data.get("ISM 製造業PMI").iloc[-1]
        data['ism_pmi'] = pmi
        if pmi >= 55: scores['ISM製造業PMI'] = 8
        elif pmi >= 52: scores['ISM製造業PMI'] = 6
        elif pmi >= 50: scores['ISM製造業PMI'] = 4
        elif pmi >= 47: scores['ISM製造業PMI'] = 2
        
        # 總經-消費
        # [修正] 直接使用已計算好的年增率數據
        retail_yoy = fred_data.get('美國零售銷售年增率 (%)').iloc[-1] / 100 # 轉為小數
        pce_yoy = fred_data.get('實質個人消費支出年增率 (%)').iloc[-1] / 100
        data['retail_yoy'] = retail_yoy
        data['pce_yoy'] = pce_yoy
        retail_score, pce_score = 0, 0
        if retail_yoy > 0.05: retail_score = 3.6
        elif retail_yoy > 0.02: retail_score = 2.5
        elif retail_yoy >= 0: retail_score = 1.0
        if pce_yoy > 0.03: pce_score = 2.4
        elif pce_yoy > 0.02: pce_score = 1.8
        elif pce_yoy >= 0: pce_score = 0.8
        scores['美國消費需求綜合'] = retail_score + pce_score

    except Exception as e:
        print(f"  - ❌ [模型二] 計算時發生錯誤: {e}")

    total_score = sum(scores.values())
    if total_score >= 80: scenario = "情境1: 主升段"; position = "70-80%";
    elif total_score >= 65: scenario = "情境2: 末升段"; position = "50-70%";
    elif total_score >= 45: scenario = "情境3: 初跌段"; position = "40-60%";
    elif total_score >= 25: scenario = "情境4: 主跌段"; position = "60-75%";
    else: scenario = "情境5: 觸底/初升段"; position = "75-80%";
    
    print("  ✅ [模型二] 執行完畢。")
    return {"total_score": total_score, "scenario": scenario, "position": position, "scores_breakdown": scores, "underlying_data": data}


@functions_framework.http
def run_scraper(request):
    print(f"--- 數據與模型引擎 (v{__version__}) 開始執行 ---")
    
    # 1. 數據抓取
    market_tickers = {"台股加權指數": "^TWII", "標普500指數": "^GSPC", "納斯達克100指數": "^IXIC", "費城半導體指數": "^SOX"}
    yfinance_data = get_yfinance_data(list(market_tickers.values()) + ['^VIX'])
    financial_data = get_mag7_financials()
    fred = Fred(api_key=FRED_API_KEY)
    fred_data = get_fred_data(fred)
    dbnomics_data = get_dbnomics_data()

    # 2. 指標計算
    kdj_indicators = {}
    if yfinance_data is not None:
        for name, ticker in market_tickers.items():
            market_price_df = yfinance_data.loc[:, (slice(None), ticker)]
            market_price_df.dropna(how='all', inplace=True)
            kdj_indicators[name] = {
                "weekly": calculate_kdj(market_price_df, 'W-FRI'),
                "monthly": calculate_kdj(market_price_df, 'ME')
            }

    # 3. 模型運算
    signals_j_vix = run_j_vix_model(kdj_indicators, yfinance_data['Close'])
    signals_tech_model = run_tech_model(financial_data, fred_data, dbnomics_data)

    # 4. 組合最終數據包

    corporate_financials = {}
    if financial_data:
        for symbol, data in financial_data.items():
            try:
                revenue = data['quarterly_financials'].loc['Total Revenue'].head(4) # 取最近4季
                capex = data['quarterly_cashflow'].loc['Capital Expenditure'].head(4)
                corporate_financials[symbol] = {
                    "revenue": {d.strftime('%Y-%m'): v for d, v in revenue.to_dict().items()},
                    "capex": {d.strftime('%Y-%m'): v for d, v in capex.to_dict().items()}
                }
            except KeyError:
                print(f"  - 注意：{symbol} 的財報數據不完整，跳過。")
                    
    final_data_to_store = {
        "j_vix_model": {"signals": signals_j_vix, "latest_vix": yfinance_data['Close']['^VIX'].dropna().iloc[-1] if '^VIX' in yfinance_data['Close'].columns else None},
        "tech_model": signals_tech_model,
        "raw_data": {
            "kdj": {m: {"weekly": {d.strftime('%Y-%m-%d'): v for d, v in k['weekly'].tail(3).to_dict('index').items()}, "monthly": {d.strftime('%Y-%m-%d'): v for d, v in k['monthly'].tail(3).to_dict('index').items()}} for m, k in kdj_indicators.items() if k.get('weekly') is not None and k.get('monthly') is not None},
            "fred": {k: {d.strftime('%Y-%m-%d'): val for d, val in v.to_dict().items()} for k, v in fred_data.items() if v is not None},
            "dbnomics": {k: {d.strftime('%Y-%m-%d'): val for d, val in v.to_dict().items()} for k, v in dbnomics_data.items() if v is not None},
            "corporate_financials": corporate_financials # <-- [v5.4.0-rc4 新增]
        }
    }
    
    # 5. 統一寫入 Firestore
    db = firestore.client()
    taipei_tz = pytz.timezone('Asia/Taipei')
    doc_id = datetime.datetime.now(taipei_tz).strftime("%Y-%m-%d")
    doc_ref = db.collection('daily_model_data').document(doc_id)
    expire_at_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)
    firestore_document = { "updated_at": firestore.SERVER_TIMESTAMP, "expireAt": expire_at_time, "version": __version__, "data": final_data_to_store }
    doc_ref.set(firestore_document)
    
    print(f"--- 成功將所有模型數據寫入 Firestore 文件 '{doc_id}' ---")
    return {"status": "success", "version": __version__}