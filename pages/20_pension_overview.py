# pages/20_🏦_退休金總覽.py
# App Version: v5.0.0
# Description: A self-contained module for pension planning, including data entry, calculation, and results display.

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from firebase_admin import firestore
# --- [v5.0.0 修正] 從 utils 引用所有核心函數 ---
from utils import init_firebase, get_full_retirement_analysis, load_retirement_plan, load_pension_data, render_sidebar

render_sidebar()

# --- 頁面配置 ---
st.set_page_config(layout="wide", page_title="退休金總覽")
st.title("🏦 退休金總覽與模擬")

# --- 身份驗證與初始化 ---
if 'user_id' not in st.session_state:
    st.info("請先從主頁面登入，以使用此功能。")
    st.stop()

user_id = st.session_state['user_id']
db, _ = init_firebase()


# --- 主體邏輯 ---
st.info("在此頁面模擬您的勞保與勞退狀況。儲存後的結果，將被用於「財務自由儀表板」的最終整合分析。")

# --- [v5.0.0 修正] ---
# 載入使用者已儲存的計畫與上次的結果
saved_plan, saved_results = load_pension_data(user_id)

# 如果有從 Firestore 讀取到已儲存的結果，且 session_state 是空的，就將結果載入
if saved_results and 'pension_plan_results' not in st.session_state:
    st.session_state['pension_plan_inputs'] = saved_plan
    st.session_state['pension_plan_results'] = saved_results
# --- [修正結束] ---

# 載入使用者已儲存的計畫
saved_plan = load_retirement_plan(user_id)
defaults = {
    'current_age': saved_plan.get('current_age', 35),
    'birth_year': saved_plan.get('birth_year', 1990),
    'retirement_age': saved_plan.get('retirement_age', 65),
    'avg_monthly_salary': saved_plan.get('avg_monthly_salary', 50000),
    'current_pension_principal': saved_plan.get('current_pension_principal', 500000),
    'self_contribution_rate': saved_plan.get('self_contribution_rate', 6.0),
    'current_total_seniority': saved_plan.get('current_total_seniority', 10),
    'expected_return_rate': saved_plan.get('expected_return_rate', 5.0), # 這裡的報酬率僅用於勞退帳戶
    'salary_growth_rate': saved_plan.get('salary_growth_rate', 2.0),
    'last_updated': saved_plan.get('last_updated', "尚未儲存")
}

# --- 輸入表單 (使用 expander) ---
with st.expander("✏️ 編輯或輸入您的退休金規劃參數", expanded=not bool(saved_plan)):
    with st.form("retirement_plan_form"):
        st.subheader("1. 基本資料")
        col1, col2, col3 = st.columns(3)
        current_age = col1.number_input("目前年齡", 18, 99, defaults['current_age'])
        birth_year = col2.number_input("出生年份 (西元)", 1920, datetime.now().year, defaults['birth_year'])
        retirement_age = col3.number_input("預計退休年齡", 55, 80, defaults['retirement_age'])

        st.subheader("2. 薪資與資產")
        col1, col2 = st.columns(2)
        avg_monthly_salary = col1.number_input("目前平均月薪 (請填寫稅前薪資)", 0, 200000, defaults['avg_monthly_salary'], 1000)
        current_pension_principal = col2.number_input("目前勞退個人專戶累積本金", 0, 10000000, defaults['current_pension_principal'], 10000)
        col2.caption("可登入 [勞保局e化服務系統](https://edesk.bli.gov.tw/aa/) 查詢您的本金與目前總年資。")

        st.subheader("3. 年資與成長性")
        col1, col2, col3 = st.columns(3)
        current_total_seniority = col1.number_input("目前累計總年資 (勞保與勞退年資可擇一)", 0, 50, defaults['current_total_seniority'], help="請至勞保局e化服務系統查詢，此處年資將同時用於估算勞保與勞退。")
        self_contribution_rate = col2.slider("勞退個人自願提繳率 (%)", 0.0, 6.0, defaults['self_contribution_rate'], 0.5)
        expected_return_rate = col3.slider("預估勞退投資年化報酬率 (%)", 1.0, 12.0, defaults['expected_return_rate'], 0.5)
        salary_growth_rate = col3.slider("預估未來薪資年成長率 (%)", 0.0, 10.0, defaults['salary_growth_rate'], 0.5)
    

        if st.form_submit_button("儲存並進行分析", use_container_width=True):
            # 1. 收集所有使用者輸入
            years_to_retirement = retirement_age - current_age
            final_seniority = current_total_seniority + years_to_retirement
            plan_data = {
                'current_age': current_age,
                'birth_year': birth_year,
                'retirement_age': retirement_age,
                'avg_monthly_salary': avg_monthly_salary,
                'current_pension_principal': current_pension_principal,
                'self_contribution_rate': self_contribution_rate,
                'current_total_seniority': current_total_seniority,
                'expected_return_rate': expected_return_rate,
                'salary_growth_rate': salary_growth_rate,
                'years_to_retirement': retirement_age - current_age,
                'last_updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                # --- [v5.0.0 修正] ---
                # 將後端需要的 `insurance_seniority` 和 `pension_contributed_years` 一併傳入
                'insurance_seniority': max(0, final_seniority),
                'pension_contributed_years': max(0, final_seniority)                
            }
            
            # 2. 呼叫計算引擎進行分析
            with st.spinner("正在為您計算退休金流..."):
                # 注意：直接將收集到的 plan_data 傳遞給計算函數
                analysis_results = get_full_retirement_analysis(plan_data) 
            
            # 3. 將輸入與結果都存入 session state，以便立即顯示
            st.session_state['pension_plan_inputs'] = plan_data
            st.session_state['pension_plan_results'] = analysis_results

            # 4. 將使用者輸入的規劃參數存入 Firestore
            # --- [v5.0.0 修正] 將分析結果也一併存入 Firestore ---
            db.collection('users').document(user_id).set({
                'retirement_plan': plan_data,
                'pension_analysis_results': analysis_results # <-- 新增這一行
            }, merge=True)
            # --- [修正結束] ---

            st.success("您的退休金規劃已更新並完成分析！")            
            # 5. 清除數據快取
            st.cache_data.clear()

            # (選擇性) 如果您希望點擊按鈕後表單能收合，可以在所有操作的最後一步加上 rerun
            st.rerun() 

# --- 結果顯示區塊 ---
# 檢查 session_state 中是否有計算結果可以顯示
if 'pension_plan_results' in st.session_state:
    results = st.session_state['pension_plan_results']
    plan = st.session_state['pension_plan_inputs']
    
    retirement_age = plan.get('retirement_age', 65)
    legal_age = results.get('labor_insurance', {}).get('legal_age', 65)
    pension_monthly = results.get('labor_pension', {}).get('monthly_pension', 0)
    insurance_monthly = results.get('labor_insurance', {}).get('monthly_pension', 0)
    total_at_legal_age = pension_monthly + insurance_monthly

    st.markdown("---")
    st.subheader("📊 您的退休金流總覽 (預估值)")
    
    if retirement_age < legal_age:
        col1, col2 = st.columns(2)
        col1.metric(label=f"{retirement_age} ~ {legal_age - 1} 歲 (僅勞退)", value=f"NT$ {pension_monthly:,.0f} /月")
        col2.metric(label=f"{legal_age} 歲起 (勞退+勞保)", value=f"NT$ {total_at_legal_age:,.0f} /月",
                      help=f"勞退 ${pension_monthly:,.0f} + 勞保 ${insurance_monthly:,.0f}")
    else:
        st.metric(label=f"預計 {retirement_age} 歲退休後，每月總退休金 (勞退+勞保)", value=f"NT$ {total_at_legal_age:,.0f}")

    st.markdown("---")
    st.subheader("詳細分析")
    col1, col2 = st.columns(2)
    with col1:
        with st.container(border=True):
            pension = results['labor_pension']
            st.markdown("#### **勞工退休金 (個人專戶)**")
            st.metric("退休時帳戶總額", f"NT$ {pension['final_amount']:,.0f}")
            st.metric("預估月領金額", f"NT$ {pension['monthly_pension']:,.0f}" if pension['can_monthly_payment'] else "N/A (僅可一次領)")
            if not pension['can_monthly_payment']:
                st.warning("提醒：因退休時總提繳年資未滿15年，僅可一次領取。")
    with col2:
        with st.container(border=True):
            insurance = results['labor_insurance']
            st.markdown("#### **勞工保險 (老年年金)**")
            st.metric("擇優公式", insurance['formula'])
            st.metric("預估月領金額", f"NT$ {insurance['monthly_pension']:,.0f}")
            if insurance.get('is_projected_at_legal_age'):
                st.info(f"ℹ️ 您選擇在 {retirement_age} 歲退休，勞保年金依法需至 {insurance['legal_age']} 歲才能開始請領。上列金額為模擬您於 {insurance['legal_age']} 歲時可領取的月退俸。")
            elif not insurance.get('eligible'):
                 st.warning(f"提醒：{insurance.get('remark', '請領資格不符')}")


    # 敏感度分析圖表
    st.markdown("---")
    st.subheader("報酬率敏感度分析")
    sensitivity_data = results['sensitivity_analysis']
    df = pd.DataFrame.from_dict(sensitivity_data, orient='index')
    df.index.name = '年化報酬率'
    df.reset_index(inplace=True)
    fig = px.bar(
        df, x='年化報酬率', y='final_amount', text='final_amount',
        title='不同「勞退自提專戶報酬率」對「退休時總額」的影響',
        labels={'final_amount': '退休時帳戶總額 (NT$)', '年化報酬率': '預估年化報酬率 (%)'}
    )
    fig.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
    st.plotly_chart(fig, use_container_width=True)

    # 逐年提繳明細
    with st.expander("查看勞退個人專戶 - 逐年累積模擬"):
        pension_details = results.get('labor_pension', {})
        details_df = pd.DataFrame(pension_details.get('contribution_details', []))
        if not details_df.empty:
            display_df = details_df.rename(columns={
                'year': '年度', 'monthly_salary': '當年度月薪', 'capped_salary': '提繳工資',
                'annual_contribution': '年度總提繳', 'investment_return': '年度投資收益',
                'account_balance_before': '年初帳戶餘額'
            })
            display_df['年末總餘額'] = display_df['年初帳戶餘額'] + display_df['年度投資收益'] + display_df['年度總提繳']
            for col in ['當年度月薪', '提繳工資', '年度總提繳', '年度投資收益', '年初帳戶餘額', '年末總餘額']:
                display_df[col] = display_df[col].apply(lambda x: f"{x:,.0f}")
            st.dataframe(display_df[['年度', '當年度月薪', '年度總提繳', '年度投資收益', '年末總餘額']], use_container_width=True)