# pages/40_financial_dashboard.py
# App Version: v5.0.0
# Description: Refactored to allow analysis even if some data modules are empty.

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
    
    # 讀取已儲存的全局假設
    plan = load_retirement_plan(user_id)
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        asset_return_rate = st.slider("預期總資產年化報酬率 (%)", 0.0, 15.0, plan.get('asset_return_rate', 7.0), 0.5)
    with c2:
        dividend_yield = st.slider("預期年化股息率 (%)", 0.0, 10.0, plan.get('dividend_yield', 2.5), 0.5)
    with c3:
        withdrawal_rate = st.slider("退休後資產提領率 (%)", 1.0, 10.0, plan.get('withdrawal_rate', 4.0), 0.5)
    with c4:
        inflation_rate = st.slider("預估長期平均通膨率 (%)", 0.0, 5.0, plan.get('inflation_rate', 2.0), 0.1)
    
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

# --- 顯示最終分析結果 ---
if 'final_analysis_results' in st.session_state:
    final_analysis = st.session_state['final_analysis_results']
    summary = final_analysis['summary']
    projection_df = pd.DataFrame(final_analysis['projection_timeseries'])

    st.markdown("---")
    col1, col2 = st.columns(2)
    col1.metric(
        "預計退休時總資產 (以今日購買力計算)",
        f"NT$ {summary['assets_at_retirement_real_value']:,.0f}"
    )
    col2.metric(
        "退休後第一年可支配所得 (以今日購買力計算)",
        f"NT$ {summary['first_year_disposable_income_real_value']:,.0f} /年"
    )

    st.markdown("---")
    st.subheader("資產與負債長期走勢 (實質購買力)")
    
    fig = px.line(
        projection_df,
        x="age",
        y=["year_end_assets_real_value", "year_end_liabilities_real_value"],
        title="資產與負債模擬曲線 (經通膨調整)",
        labels={"age": "年齡", "value": "金額 (TWD)", "variable": "項目"}
    )
    st.plotly_chart(fig, use_container_width=True)

