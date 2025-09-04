# file: pages/70_cyclical_investing_model.py (v5.4.0)

import streamlit as st
import pandas as pd
import datetime
import pytz
from utils import render_sidebar, load_latest_model_data

st.set_page_config(layout="wide")
render_sidebar()

st.title("📈 週期投資策略模擬器")

# --- 身份驗證檢查 ---
if 'user_id' not in st.session_state:
    st.info("請先從主頁面登入，以使用此功能。")
    st.stop()

# --- 讀取數據 ---
model_data_doc = load_latest_model_data()
if not model_data_doc:
    st.info("模型數據正在生成中，或後端服務尚未執行成功。請稍後再試。")
    st.stop()

# --- 顯示數據更新時間 ---
updated_at = model_data_doc.get('updated_at')
if hasattr(updated_at, 'strftime'):
    taipei_tz = pytz.timezone('Asia/Taipei')
    taipei_time = updated_at.astimezone(taipei_tz)
    st.caption(f"上次數據更新時間: {taipei_time.strftime('%Y-%m-%d %H:%M')} (台北時間)")

# --- 提取各模組數據 ---
data = model_data_doc.get('data', {})
j_vix_model_data = data.get('j_vix_model', {})
tech_model_data = data.get('tech_model', {})
raw_data = data.get('raw_data', {})


# --- 頁面排版 ---
tab1, tab2 = st.tabs(["短中期擇時訊號 (J值+VIX)", "科技股總經儀表板 (V7.3模型)"])

# --- 頁籤一：短中期擇時訊號 (維持不變) ---
with tab1:
    st.header("市場進場訊號總覽")
    signals = j_vix_model_data.get('signals', {})
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
                    if mid_term_signal: st.write(" - 中期回檔訊號 (週J)")
                    if inventory_cycle_signal: st.write(" - 庫存週期訊號 (月J)")
                else:
                    st.markdown("🔴 <span style='color:red;'>未觸發訊號</span>", unsafe_allow_html=True)
    
    st.markdown("---")
    st.header("核心指標狀態")
    
    kdj_data = raw_data.get('kdj', {})
    latest_vix = j_vix_model_data.get('latest_vix', 'N/A')
    
    tabs_kdj = st.tabs(markets)
    for i, market_name in enumerate(markets):
        with tabs_kdj[i]:
            market_kdj = kdj_data.get(market_name, {})
            weekly_kdj = market_kdj.get('weekly', {})
            monthly_kdj = market_kdj.get('monthly', {})

            latest_weekly_date = sorted(weekly_kdj.keys())[-1] if weekly_kdj else 'N/A'
            latest_weekly_j = weekly_kdj.get(latest_weekly_date, {}).get('J', 'N/A')
            
            latest_monthly_date = sorted(monthly_kdj.keys())[-1] if monthly_kdj else 'N/A'
            latest_monthly_j = monthly_kdj.get(latest_monthly_date, {}).get('J', 'N/A')

            metric_cols = st.columns(3)
            metric_cols[0].metric(label=f"最新 週 J 值 ({latest_weekly_date})", value=f"{latest_weekly_j:.2f}" if isinstance(latest_weekly_j, (int, float)) else "N/A")
            metric_cols[1].metric(label=f"最新 月 J 值 ({latest_monthly_date})", value=f"{latest_monthly_j:.2f}" if isinstance(latest_monthly_j, (int, float)) else "N/A")
            metric_cols[2].metric(label=f"最新 VIX 值", value=f"{latest_vix:.2f}" if isinstance(latest_vix, (int, float)) else "N/A")

# --- 頁籤二：科技股總經儀表板 ---
with tab2:
    if not tech_model_data or not tech_model_data.get('total_score'):
        st.warning("科技股總經模型數據正在收集中...")
    else:
        st.header("🎯 當前市場總評")
        
        total_score = tech_model_data.get('total_score', 0)
        scenario = tech_model_data.get('scenario', 'N/A')
        position = tech_model_data.get('position', 'N/A')
        
        score_cols = st.columns(3)
        score_cols[0].metric("總分", f"{total_score:.1f} / 100.0")
        score_cols[1].metric("市場情境", scenario)
        score_cols[2].metric("建議倉位", position)
        
        st.markdown("---")
        st.header("📊 模型評分細項")
        
        scores_breakdown = tech_model_data.get('scores_breakdown', {})
        
        col1, col2 = st.columns(2)
        with col1:
            with st.container(border=True):
                st.markdown("##### 💼 微觀基本面")
                micro_score = scores_breakdown.get('Mag7營收年增率', 0) + scores_breakdown.get('資本支出增長率', 0) + scores_breakdown.get('關鍵領先指標', 0)
                st.progress(int(micro_score / 65 * 100), text=f"總分: {micro_score:.1f} / 65.0")
                st.markdown(f"- Mag7營收年增率: **{scores_breakdown.get('Mag7營收年增率', 0):.1f} / 30.0**")
                st.markdown(f"- 資本支出增長率: **{scores_breakdown.get('資本支出增長率', 0):.1f} / 20.0**")
                st.markdown(f"- 關鍵領先指標: **{scores_breakdown.get('關鍵領先指標', 0):.1f} / 15.0**")

        with col2:
            with st.container(border=True):
                st.markdown("##### 🌍 總經環境")
                macro_score = scores_breakdown.get('資金面與流動性', 0) + scores_breakdown.get('GDP季增率', 0) + scores_breakdown.get('ISM製造業PMI', 0) + scores_breakdown.get('美國消費需求綜合', 0)
                st.progress(int(macro_score / 35 * 100), text=f"總分: {macro_score:.1f} / 35.0")
                st.markdown(f"- 資金面與流動性: **{scores_breakdown.get('資金面與流動性', 0):.1f} / 12.0**")
                st.markdown(f"- GDP季增率: **{scores_breakdown.get('GDP季增率', 0):.1f} / 9.0**")
                st.markdown(f"- ISM製造業PMI: **{scores_breakdown.get('ISM製造業PMI', 0):.1f} / 8.0**")
                st.markdown(f"- 美國消費需求綜合: **{scores_breakdown.get('美國消費需求綜合', 0):.1f} / 6.0**")

        with st.expander("🔍 展開以查看所有指標原始數據", expanded=True):
            
            # --- [v5.4.0] 新增的三頁籤佈局 ---
            exp_tabs = st.tabs(["產業數據", "總經數據", "領先指標"])

            # 頁籤一：產業數據
            with exp_tabs[0]:
                st.markdown("#### **科技巨頭關鍵財務數據 (季)**")
                corporate_data = raw_data.get('corporate_financials', {})
                if not corporate_data:
                    st.write("產業數據正在收集中...")
                else:
                    corp_cols = st.columns(4)
                    companies = ['MSFT', 'AAPL', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META', 'TSM']
                    for i, symbol in enumerate(companies):
                        with corp_cols[i % 4]:
                            if symbol in corporate_data:
                                with st.container(border=True):
                                    st.markdown(f"**{symbol}**")
                                    # 營收
                                    revenue_data = corporate_data[symbol].get('revenue', {})
                                    if revenue_data:
                                        rev_df = pd.DataFrame.from_dict(revenue_data, orient='index', columns=['Revenue']).sort_index()
                                        rev_yoy = (rev_df['Revenue'].iloc[-1] / rev_df['Revenue'].iloc[0] - 1) if len(rev_df) >= 4 else 0
                                        st.metric("最新季營收年增率", f"{rev_yoy:.2%}")
                                        st.bar_chart(rev_df, height=150)
                                    # 資本支出
                                    capex_data = corporate_data[symbol].get('capex', {})
                                    if capex_data:
                                        capex_df = pd.DataFrame.from_dict(capex_data, orient='index', columns=['Capex']).sort_index()
                                        capex_df['Capex'] = capex_df['Capex'].abs()
                                        st.bar_chart(capex_df, height=150)


            # 頁籤二：總經數據
            with exp_tabs[1]:
                st.markdown("#### **美國總經指標 (FRED & ISM)**")
                fred_data = raw_data.get('fred', {})
                ism_data = raw_data.get('dbnomics', {})
                
                # 合併 FRED 和部分 ISM 數據
                macro_data_sources = {**fred_data, **ism_data}
                indicators_to_display = ["美國零售銷售年增率 (%)", "核心 PCE 物價指數年增率 (%)", "非農就業人數變化 (萬人)", "失業率 (%)", "密大消費者信心指數", "製造業 PMI", "非製造業 PMI"]
                
                macro_cols = st.columns(2)
                col_idx = 0
                for name in indicators_to_display:
                    if name in macro_data_sources and macro_data_sources[name]:
                        with macro_cols[col_idx % 2]:
                             with st.container(border=True):
                                df = pd.DataFrame.from_dict(macro_data_sources[name], orient='index', columns=['Value'])
                                df.index = pd.to_datetime(df.index)
                                df.sort_index(inplace=True)
                                
                                st.markdown(f"**{name}**")
                                latest_value = df['Value'].iloc[-1]
                                previous_value = df['Value'].iloc[-2] if len(df) >= 2 else None
                                delta = (latest_value - previous_value) if previous_value is not None else None
                                
                                st.metric(
                                    label=f"最新 ({df.index[-1].strftime('%Y-%m')})", 
                                    value=f"{latest_value:,.2f}",
                                    delta=f"{delta:,.2f}" if delta is not None else None)
                                st.line_chart(df, height=150)
                        col_idx += 1


            # 頁籤三：領先指標
            with exp_tabs[2]:
                st.markdown("#### **領先指標 (OECD)**")
                oecd_data = raw_data.get('dbnomics', {}).get('OECD 美國領先指標', {})
                
                if not oecd_data:
                    st.write("OECD 領先指標數據正在收集中...")
                else:
                    lead_cols = st.columns(2)
                    with lead_cols[0]:
                        with st.container(border=True):
                            df = pd.DataFrame.from_dict(oecd_data, orient='index', columns=['Value'])
                            df.index = pd.to_datetime(df.index)
                            df.sort_index(inplace=True)
                            
                            st.markdown("**OECD 美國領先指標 (絕對值)**")
                            latest_value = df['Value'].iloc[-1]
                            previous_value = df['Value'].iloc[-2] if len(df) >= 2 else None
                            delta = latest_value - previous_value if previous_value is not None else None
                            st.metric(
                                label=f"最新 ({df.index[-1].strftime('%Y-%m')})", 
                                value=f"{latest_value:,.2f}",
                                delta=f"{delta:,.2f}" if delta is not None else None)
                            st.line_chart(df, height=150)
                            
                    with lead_cols[1]:
                        with st.container(border=True):
                            df_yoy = df.pct_change(12) * 100
                            df_yoy.dropna(inplace=True)
                            
                            st.markdown("**OECD 美國領先指標 (年增率 %)**")
                            latest_yoy = df_yoy['Value'].iloc[-1]
                            previous_yoy = df_yoy['Value'].iloc[-2] if len(df_yoy) >= 2 else None
                            delta_yoy = latest_yoy - previous_yoy if previous_yoy is not None else None
                            st.metric(
                                label=f"最新 ({df_yoy.index[-1].strftime('%Y-%m')})", 
                                value=f"{latest_yoy:,.2f}%",
                                delta=f"{delta_yoy:,.2f}" if delta_yoy is not None else None)
                            st.line_chart(df_yoy, height=150)