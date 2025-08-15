# file: pages/70_cyclical_investing_model.py

import streamlit as st
import pandas as pd
from utils import render_sidebar, load_latest_model_data

st.set_page_config(layout="wide")
render_sidebar()

st.title("📈 週期投資策略模擬器")

if 'user_id' not in st.session_state:
    st.info("請先從主頁面登入，以使用此功能。")
    st.stop()
    
# --- 讀取數據 ---
model_data_doc = load_latest_model_data()

if not model_data_doc:
    st.info("模型數據正在生成中，請稍後再試。")
    st.stop()

# --- 顯示數據更新時間 ---
updated_at = model_data_doc.get('updated_at', 'N/A')
if hasattr(updated_at, 'strftime'):
    st.caption(f"上次數據更新時間: {updated_at.strftime('%Y-%m-%d %H:%M')} (UTC)")

# --- 1. 市場進場訊號總覽 ---
st.subheader("一、市場進場訊號總覽")

signals = model_data_doc.get('data', {}).get('signals', {})
markets = ["標普500指數", "納斯達克100指數", "費城半導體指數", "台股加權指數"]

cols = st.columns(len(markets))

for i, market_name in enumerate(markets):
    with cols[i]:
        with st.container(border=True):
            st.markdown(f"**{market_name}**")
            market_signals = signals.get(market_name, {})
            
            mid_term_signal = market_signals.get('mid_term_pullback', False)
            inventory_cycle_signal = market_signals.get('inventory_cycle', False)

            if mid_term_signal or inventory_cycle_signal:
                st.markdown("🟢 <span style='color:green; font-weight:bold;'>觸發進場訊號</span>", unsafe_allow_html=True)
                if mid_term_signal:
                    st.write(" - 中期回檔訊號")
                if inventory_cycle_signal:
                    st.write(" - 庫存週期訊號")
            else:
                st.markdown("🔴 <span style='color:red;'>未觸發訊號</span>", unsafe_allow_html=True)

# --- 2. 核心指標狀態 ---
st.subheader("二、核心指標狀態")

kdj_data = model_data_doc.get('data', {}).get('kdj_indicators', {})
vix_data = model_data_doc.get('data', {}).get('sentiment_vix_us', {})
latest_vix_date = sorted(vix_data.keys())[-1] if vix_data else 'N/A'
latest_vix_value = vix_data.get(latest_vix_date, 'N/A')

tabs = st.tabs(markets)

for i, market_name in enumerate(markets):
    with tabs[i]:
        market_kdj = kdj_data.get(market_name, {})
        weekly_kdj = market_kdj.get('weekly', {})
        monthly_kdj = market_kdj.get('monthly', {})

        latest_weekly_date = sorted(weekly_kdj.keys())[-1] if weekly_kdj else 'N/A'
        latest_weekly_j = weekly_kdj.get(latest_weekly_date, {}).get('J', 'N/A')
        
        latest_monthly_date = sorted(monthly_kdj.keys())[-1] if monthly_kdj else 'N/A'
        latest_monthly_j = monthly_kdj.get(latest_monthly_date, {}).get('J', 'N/A')

        metric_cols = st.columns(3)
        with metric_cols[0]:
            st.metric(label=f"最新 週 J 值 ({latest_weekly_date})", value=f"{latest_weekly_j:.2f}" if isinstance(latest_weekly_j, float) else "N/A")
        with metric_cols[1]:
            st.metric(label=f"最新 月 J 值 ({latest_monthly_date})", value=f"{latest_monthly_j:.2f}" if isinstance(latest_monthly_j, float) else "N/A")
        with metric_cols[2]:
            st.metric(label=f"最新 VIX 值 ({latest_vix_date})", value=f"{latest_vix_value:.2f}" if isinstance(latest_vix_value, float) else "N/A")


# --- 3. 總經環境儀表板 ---
st.subheader("三、總經環境儀表板")

macro_fred = model_data_doc.get('data', {}).get('macro_fred', {})
macro_ism = model_data_doc.get('data', {}).get('macro_ism_pmi', {})

with st.expander("展開以查看詳細總經數據"):
    macro_tabs = st.tabs(["美國總經指標 (FRED)", "美國 ISM PMI 指標"])
    
    with macro_tabs[0]:
        if not macro_fred:
            st.write("FRED 總經數據正在收集中...")
        else:
            fred_cols = st.columns(2)
            # 將字典轉換為 DataFrame 以便繪圖
            for i, (name, data_dict) in enumerate(macro_fred.items()):
                with fred_cols[i % 2]:
                    if data_dict:
                        df = pd.DataFrame.from_dict(data_dict, orient='index', columns=['Value'])
                        df.index = pd.to_datetime(df.index)
                        df.sort_index(inplace=True)
                        st.markdown(f"**{name}**")
                        st.line_chart(df)

    with macro_tabs[1]:
        if not macro_ism:
            st.write("ISM PMI 數據正在收集中...")
        else:
            df_ism = pd.DataFrame.from_dict(macro_ism, orient='index').sort_index(ascending=False)
            
            # 重新命名
            df_ism.rename(columns={'就業': '僱傭指數', '庫存': '存貨'}, inplace=True)
            
            # 定義新的欄位順序
            new_order = [
                "非製造業 PMI", "製造業 PMI", "新訂單", "生產", 
                "僱傭指數", "存貨", "客戶端存貨"
            ]
            # 過濾掉可能不存在的欄位，以避免錯誤
            display_order = [col for col in new_order if col in df_ism.columns]
            
            st.dataframe(df_ism[display_order].head(12)) # 顯示最近12個月