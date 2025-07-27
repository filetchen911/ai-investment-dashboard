# pages/40_financial_dashboard.py
# App Version: v5.0.0
# Description: Final enhanced version with multiple charts, toggles, and detailed metrics.

import streamlit as st
import pandas as pd
import plotly.express as px
from utils import (
    render_sidebar,    
    init_firebase,
    load_user_assets_from_firestore,
    load_retirement_plan,
    load_user_liabilities,
    get_holistic_financial_projection # 引入我們的終極計算引擎
)

render_sidebar()

# --- 頁面配置 ---
st.set_page_config(layout="wide", page_title="財務自由儀表板")
st.title("🏁 財務自由儀表板")

# --- 身份驗證與初始化 ---
if 'user_id' not in st.session_state:
    st.info("請先從主頁面登入，以使用此功能。")
    st.stop()

user_id = st.session_state['user_id']
db, _ = init_firebase()

# --- [v5.0.0] 引導式檢查清單 ---
st.subheader("您的財務健康度檢查清單")
st.caption("請完成以下三大財務盤點，以解鎖您的整合性未來模擬報告。")

# 1. 檢查資產數據
assets_df = load_user_assets_from_firestore(user_id)
is_assets_done = not assets_df.empty

# 2. 檢查退休金規劃
pension_plan = load_retirement_plan(user_id)
is_pension_done = bool(pension_plan) # 檢查字典是否為空

# 3. 檢查債務數據
liabilities_df = load_user_liabilities(user_id)
is_liabilities_done = not liabilities_df.empty

# 顯示清單
col1, col2, col3 = st.columns(3)
with col1:
    with st.container(border=True):
        st.markdown(f"### {'✅' if is_assets_done else '❌'} 步驟一：資產盤點")
        st.write("記錄您所有的投資與現金資產。")
        st.page_link("pages/10_asset_overview.py", label="前往管理資產", icon="📊")

with col2:
    with st.container(border=True):
        st.markdown(f"### {'✅' if is_pension_done else '❌'} 步驟二：退休金規劃")
        st.write("設定您的退休目標與勞保/勞退參數。")
        st.page_link("pages/20_pension_overview.py", label="前往規劃退休金", icon="🏦")

with col3:
    with st.container(border=True):
        st.markdown(f"### {'✅' if is_liabilities_done else '❌'} 步驟三：債務盤點")
        st.write("記錄您所有的貸款與負債狀況。")
        st.page_link("pages/30_debt_management.py", label="前往管理債務", icon="💳")

st.markdown("---")


st.subheader("🚀 您的整合性財務分析報告")

# --- [v5.0.0] 全局財務假設輸入表單 ---
with st.form("global_assumptions_form"):
    st.markdown("#### 請輸入您的全局財務假設")
    plan = load_retirement_plan(user_id)
    
    c1, c2, c3, c4, c5 = st.columns(5)
    # [v5.0.0 新增]
    annual_investment = c1.number_input("退休前每年可增加的投資金額", min_value=0, value=plan.get('annual_investment', 0), step=10000)
    asset_return_rate = c2.slider("預期總資產年化報酬率 (%)", 0.0, 15.0, plan.get('asset_return_rate', 7.0), 0.5)
    dividend_yield = c3.slider("預期年化股息率 (%)", 0.0, 10.0, plan.get('dividend_yield', 2.5), 0.5)
    withdrawal_rate = c4.slider("退休後資產提領率 (%)", 1.0, 10.0, plan.get('withdrawal_rate', 4.0), 0.5)
    inflation_rate = c5.slider("預估長期平均通膨率 (%)", 0.0, 5.0, plan.get('inflation_rate', 2.0), 0.1)
    
    submitted = st.form_submit_button("開始最終模擬", use_container_width=True)

if submitted:
    # 將全局假設存回 retirement_plan
    updated_plan = {
        'asset_return_rate': asset_return_rate,
        'dividend_yield': dividend_yield,
        'withdrawal_rate': withdrawal_rate,
        'inflation_rate': inflation_rate
    }
    db.collection('users').document(user_id).set({'retirement_plan': updated_plan}, merge=True)
    
    # 呼叫終極計算引擎
    with st.spinner("正在執行整合性財務模擬..."):
        final_analysis = get_holistic_financial_projection(user_id)
        # 將結果存入 session_state 以便重新整理後也能顯示
        st.session_state['final_analysis_results'] = final_analysis
    
    st.success("模擬計算完成！")

    # --- [v5.0.0 偵錯] ---
    # 檢查是否有偵錯日誌，並將其顯示在螢幕上
    if 'debug_log' in final_analysis and final_analysis['debug_log']:
        st.subheader("🔍 後端偵錯日誌 (from utils.py)")
        with st.expander("點此查看詳細日誌"):
            for message in final_analysis['debug_log']:
                st.info(message)
    # --- [偵錯結束] ---
    
# --- 顯示最終分析結果 ---
if 'final_analysis_results' in st.session_state:
    final_analysis = st.session_state['final_analysis_results']
    summary = final_analysis['summary']
    projection_df = pd.DataFrame(final_analysis['projection_timeseries'])

    # --- [v5.0.0 偵錯] 將關鍵 DataFrame 打印在螢幕上 ---
    st.markdown("---")
    st.subheader("🔍 偵錯資訊")
    with st.expander("點此查看從後端回傳的原始數據"):
        st.write("`projection_df` 的前 10 筆資料：")
        # 我們只關心與「新增投資」相關的欄位
        debug_columns = ['age', 'phase', 'annual_investment_nominal', 'user_input_annual_investment']
        # 檢查欄位是否存在，避免出錯
        existing_debug_columns = [col for col in debug_columns if col in projection_df.columns]
        st.dataframe(projection_df[existing_debug_columns].head(10))
    st.markdown("---")
    # --- [偵錯結束] ---

    # 將使用者設定的退休年齡讀入一個變數
    user_retirement_age = plan.get('retirement_age', 65)

    st.markdown("---")
    # [v5.0.0 建議 1] 擴充為 2x2 指標矩陣
    st.subheader("退休關鍵指標")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("預計退休時總資產 (名目價值)", f"NT$ {summary['assets_at_retirement_nominal']:,.0f}")
        st.metric("預計退休時總資產 (今日購買力)", f"NT$ {summary['assets_at_retirement_real_value']:,.0f}")
    with col2:
        st.metric("退休後第一年可支配所得 (名目價值)", f"NT$ {summary['first_year_disposable_income_nominal']:,.0f} /年")
        st.metric("退休後第一年可支配所得 (今日購買力)", f"NT$ {summary['first_year_disposable_income_real_value']:,.0f} /年")

    # [v5.0.0 建議 3] 資產與負債圖表 (含切換)
    st.markdown("---")
    st.subheader("資產與負債長期走勢")
    chart_type_asset = st.radio("選擇顯示模式", ["實質購買力", "名目價值"], key="asset_chart_type", horizontal=True)

    if not projection_df.empty:
        asset_col = 'year_end_assets_real_value' if chart_type_asset == '實質購買力' else 'year_end_assets_nominal'
        liability_col = 'year_end_liabilities_real_value' if chart_type_asset == '實質購買力' else 'year_end_liabilities_nominal'

        df_to_plot_assets = projection_df.melt(
            id_vars=['age', 'investment_gain_nominal', 'annual_investment_nominal'], 
            value_vars=[asset_col, liability_col],
            var_name='項目',
            value_name='金額'
        )

        # --- [v5.0.0 偵錯] 打印用來繪圖的最終 DataFrame ---
        with st.expander("點此查看用於繪製「資產負債圖」的最終數據"):
            st.write("`df_to_plot_assets` 的前 10 筆資料：")
            st.dataframe(df_to_plot_assets.head(10))
        # --- [偵錯結束] ---

        label_mapping_assets = {asset_col: '總資產價值', liability_col: '總負債餘額'}
        df_to_plot_assets['項目'] = df_to_plot_assets['項目'].map(label_mapping_assets)

        fig_assets = px.line(
            df_to_plot_assets,
            x="age",
            y="金額",
            color="項目",
            title=f"資產與負債模擬曲線 ({chart_type_asset})",
            labels={"age": "年齡", "金額": f"金額 (TWD, {chart_type_asset})"},
            # [修正] custom_data 直接使用正確的欄位名稱
            custom_data=['investment_gain_nominal', 'annual_investment_nominal']
        )

        fig_assets.update_traces(
            hovertemplate="<b>年齡: %{x}</b><br>" +
                          "項目: %{data.name}<br>" +
                          "<b>年末價值: %{y:,.0f}</b><br><br>" +
                          "--- 當年度變化 (名目) ---<br>" +
                          "投資利得: %{customdata[0]:,.0f}<br>" + # <-- 現在能正確讀取
                          "新增投資: %{customdata[1]:,.0f}<br>" + # <-- 現在能正確讀取
                          "<extra></extra>"
        )

        st.plotly_chart(fig_assets, use_container_width=True)

    # [v5.0.0 建議 4 & 5] 新增現金流與可支配所得圖表
    st.markdown("---")
    st.subheader("退休後年度現金流分析")

    retirement_df = projection_df[projection_df['age'] >= user_retirement_age].copy()
    if not retirement_df.empty:
        # [修正] 圖表一：收入來源堆疊長條图 (含切換)
        chart_type_cashflow = st.radio("選擇顯示模式", ["實質購買力", "名目價值"], key="cashflow_chart_type", horizontal=True)
        
        income_source_vars = ['asset_income_real_value', 'pension_income_real_value'] if chart_type_cashflow == '實質購買力' else ['asset_income_nominal', 'pension_income_nominal']
        total_income_var = 'total_income_real_value' if chart_type_cashflow == '實質購買力' else 'total_income_nominal'

        cashflow_df = retirement_df.melt(
            id_vars=['age', total_income_var],
            value_vars=income_source_vars,
            var_name='收入來源',
            value_name='年度分項收入'
        )
        # ... (中文標籤映射不變) ...
        label_mapping_cashflow = {
            'asset_income_real_value': '資產被動收入', 'pension_income_real_value': '退休金收入',
            'asset_income_nominal': '資產被動收入', 'pension_income_nominal': '退休金收入'
        }
        cashflow_df['收入來源'] = cashflow_df['收入來源'].map(label_mapping_cashflow)

        fig_cashflow = px.bar(
            cashflow_df, x="age", y="年度分項收入", color="收入來源",
            title=f"退休後年度總收入來源分析 ({chart_type_cashflow})",
            labels={"age": "年齡", "年度分項收入": f"年度收入 ({chart_type_cashflow})", "收入來源": "收入來源"}, # <-- [修正] 新增圖例標籤
            custom_data=[total_income_var]
        )

        fig_cashflow.update_traces(
            hovertemplate="<b>年齡: %{x}</b><br><br>" +
                          "<b>年度總收入: %{customdata[0]:,.0f}</b><br>" +
                          "此來源收入: %{y:,.0f}<br>" +
                          "<extra></extra>"
        )
        st.plotly_chart(fig_cashflow, use_container_width=True)


        # 圖表二：可支配所得長條圖
        chart_type_income = st.radio("選擇顯示模式 ", ["實質購買力", "名目價值"], key="income_chart_type", horizontal=True) # 空格用於區別 key
        y_income_var = 'disposable_income_real_value' if chart_type_income == '實質購買力' else 'disposable_income_nominal'
        
        custom_data_income_cols = [
            'total_income_real_value', 'monthly_disposable_income_real_value',
            'asset_income_real_value', 'pension_income_real_value'
        ] if chart_type_income == '實質購買力' else [
            'total_income_nominal', 'monthly_disposable_income_nominal',
            'asset_income_nominal', 'pension_income_nominal'
        ]

        fig_disposable = px.bar(
            retirement_df, x="age", y=y_income_var,
            title=f"年度可支配所得趨勢 ({chart_type_income}, 已扣除負債支出)",
            labels={"age": "年齡", y_income_var: f"年度可支配所得 ({chart_type_income})"},
            custom_data=custom_data_income_cols
        )

        fig_disposable.update_traces(
            hovertemplate="<b>年齡: %{x}</b><br><br>" +
                          "<b>年度可支配所得: %{y:,.0f}</b><br>" +
                          "每月可支配所得約: %{customdata[1]:,.0f}<br>" +
                          "<br>--- 年度總收入 ---<br>" +
                          "總計: %{customdata[0]:,.0f}<br>" +
                          "來自資產: %{customdata[2]:,.0f}<br>" +
                          "來自退休金: %{customdata[3]:,.0f}<br>" +
                          "<extra></extra>"
        )

        st.plotly_chart(fig_disposable, use_container_width=True)
    else:
        st.info("無退休後數據可供分析。")