# file: pages/70_cyclical_investing_model.py (v5.4.0)

import streamlit as st
import pandas as pd
import datetime
import pytz
import plotly.graph_objects as go
from utils import render_sidebar, load_latest_model_data

st.set_page_config(layout="wide")
render_sidebar()

st.title("📈 週期投資策略模擬器")

# --- 身份驗證檢查 ---
if 'user_id' not in st.session_state:
    st.info("請先從主頁面登入，以使用此功能。")
    st.stop()

# --- 讀取並解析數據 ---
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

            # --- [v5.4.0] 全新的三頁籤佈局 ---
            exp_tabs = st.tabs(["產業數據", "總經數據", "領先指標"])

            # 頁籤一：產業數據
            with exp_tabs[0]:
                st.markdown("#### **科技巨頭關鍵財務數據 (季)**")
                corporate_data = raw_data.get('corporate_financials', {})
                if not corporate_data:
                    st.write("產業數據正在收集中...")
                else:
                    companies = ['MSFT', 'AAPL', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META', 'TSM']
                    corp_cols = st.columns(4)
                    for i, symbol in enumerate(companies):
                        with corp_cols[i % 4]:
                            if symbol in corporate_data:
                                with st.container(border=True):
                                    st.markdown(f"**{symbol}**")
                                    # --- 營收 ---
                                    revenue_data = corporate_data[symbol].get('revenue', {})
                                    if revenue_data:
                                        rev_df = pd.DataFrame.from_dict(revenue_data, orient='index', columns=['Revenue']).sort_index()
                                        rev_df.index = pd.to_datetime(rev_df.index)
                                        rev_df['YoY'] = rev_df['Revenue'].pct_change(4) * 100
                                        latest_rev_yoy = rev_df['YoY'].iloc[-1] if len(rev_df) >= 5 else 'N/A'
                                        
                                        st.metric("最新季營收年增率", f"{latest_rev_yoy:.2f}%" if isinstance(latest_rev_yoy, (int, float)) else "N/A")

                                        # [修正] 建立單純的長條圖，並優化 Y 軸格式
                                        rev_df_display = rev_df.copy()
                                        rev_df_display['Revenue_B'] = rev_df_display['Revenue'] / 1_000_000_000
                                        fig = go.Figure()
                                        fig.add_trace(go.Bar(x=rev_df_display.index, y=rev_df_display['Revenue_B'], name='營收'))
                                        fig.update_layout(
                                            title_text='營收 (Billion)',
                                            height=200, margin=dict(l=0, r=0, t=30, b=0), 
                                            yaxis_title="十億 (B)",
                                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                                        )
                                        st.plotly_chart(fig, use_container_width=True)
                                    
                                    # --- 資本支出 ---
                                    capex_data = corporate_data[symbol].get('capex', {})
                                    if capex_data:
                                        capex_df = pd.DataFrame.from_dict(capex_data, orient='index', columns=['Capex']).sort_index()
                                        capex_df.index = pd.to_datetime(capex_df.index)
                                        capex_df['YoY'] = capex_df['Capex'].pct_change(4) * 100
                                        latest_capex_yoy = capex_df['YoY'].iloc[-1] if len(capex_df) >= 5 else 'N/A'
                                        
                                        st.metric("最新季資本支出年增率", f"{latest_capex_yoy:.2f}%" if isinstance(latest_capex_yoy, (int, float)) else "N/A")


            # 頁籤二：總經數據
            with exp_tabs[1]:
                st.markdown("#### **美國總經指標**")
                fred_data = raw_data.get('fred', {})
                ism_data = raw_data.get('dbnomics', {})
                
                macro_data_sources = {**fred_data, **ism_data}
                indicators_to_display = [
                    "實質GDP季增年率(SAAR)", "美國零售銷售年增率 (%)", "實質個人消費支出年增率 (%)", "密大消費者信心指數",
                    "ISM 製造業PMI", "ISM 製造業PMI-新訂單", "ISM 製造業PMI-客戶端存貨",
                    "聯邦基準利率", "FOMC利率點陣圖中位數", "失業率 (%)", "非農就業人數變化 (萬人)", "核心 PCE 物價指數年增率 (%)"
                ]
                
                macro_cols = st.columns(2)
                col_idx = 0
                for name in indicators_to_display:
                    # 為了簡化，我們只顯示存在於 FRED 或 DBnomics 的指標
                    # 注意：部分名稱需要從原始字典中對應
                    original_name = name 
                    if name == "聯邦基準利率": original_name = "聯邦基金利率"
                    elif name == "ISM 製造業PMI": original_name = "製造業 PMI"
                    elif name == "ISM 製造業PMI-新訂單": original_name = "新訂單"
                    elif name == "ISM 製造業PMI-客戶端存貨": original_name = "客戶端存貨"

                    if original_name in macro_data_sources and macro_data_sources.get(original_name):
                        with macro_cols[col_idx % 2]:
                             with st.container(border=True):
                                df = pd.DataFrame.from_dict(macro_data_sources[original_name], orient='index', columns=['Value'])
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
                dbnomics_data = raw_data.get('dbnomics', {})
                
                lead_indicators_to_display = ["OECD 美國領先指標"] # 只保留 OECD
                
                lead_cols = st.columns(2)
                col_idx_lead = 0
                for name in lead_indicators_to_display:
                    if name in dbnomics_data and dbnomics_data.get(name):
                        # 顯示絕對值卡片
                        with lead_cols[col_idx_lead % 2]:
                             with st.container(border=True):
                                df = pd.DataFrame.from_dict(dbnomics_data[name], orient='index', columns=['Value'])
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
                        col_idx_lead += 1
                
                        # 額外計算並顯示年增率卡片
                        with lead_cols[col_idx_lead % 2]:
                            with st.container(border=True):
                                oecd_yoy = df.pct_change(12) * 100
                                oecd_yoy.dropna(inplace=True)
                                
                                st.markdown(f"**{name} (年增率 %)**")
                                latest_yoy = oecd_yoy['Value'].iloc[-1]
                                previous_yoy = oecd_yoy['Value'].iloc[-2] if len(oecd_yoy) >= 2 else None
                                delta_yoy = (latest_yoy - previous_yoy) if previous_yoy is not None else None
                                
                                st.metric(
                                    label=f"最新 ({oecd_yoy.index[-1].strftime('%Y-%m')})",
                                    value=f"{latest_yoy:,.2f}%",
                                    delta=f"{delta_yoy:,.2f}" if delta_yoy is not None else None)
                                st.line_chart(oecd_yoy, height=150)