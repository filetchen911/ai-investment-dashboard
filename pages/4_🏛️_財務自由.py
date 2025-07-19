# pages/4_🏛️_財務自由.py
# App Version: v4.2.0
# Depends on: utils.py v4.1.0
# Description: Implemented Display/Edit modes, cached results in Firestore, and optimized input fields for better UX.

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from utils import init_firebase, get_full_retirement_analysis

# --- 頁面配置 ---
st.set_page_config(layout="wide", page_title="財務自由儀表板")
st.title("🏛️ 財務自由儀表板")

# --- 身份驗證與初始化 ---
if 'user_id' not in st.session_state:
    st.info("請先從主頁面登入，以使用此功能。")
    st.stop()

user_id = st.session_state['user_id']
db, _ = init_firebase()

# --- [v4.2 優化] 數據處理函數 ---
def load_user_data(uid, db_client):
    """讀取使用者的規劃參數與上次的分析結果"""
    user_ref = db_client.collection('users').document(uid)
    user_doc = user_ref.get()
    if user_doc.exists:
        data = user_doc.to_dict()
        plan = data.get('retirement_plan', {})
        results = data.get('analysis_results', {})
        return plan, results
    return {}, {}

def save_user_data(uid, db_client, plan, results):
    """儲存使用者的規劃參數與分析結果"""
    user_ref = db_client.collection('users').document(uid)
    user_ref.update({
        'retirement_plan': plan,
        'analysis_results': results
    })

# --- [v4.2 優化] 頁面模式切換與主體邏輯 ---

# 載入使用者資料
saved_plan, saved_results = load_user_data(user_id, db)

# 初始化/決定當前模式 (edit_mode)
if 'edit_mode' not in st.session_state:
    # 如果從未儲存過計畫，強制進入編輯模式
    st.session_state.edit_mode = not bool(saved_plan)

# 顯示模式 (如果已有儲存結果且非編輯模式)
if not st.session_state.edit_mode and saved_results:
    st.caption(f"上次計算時間：{saved_plan.get('last_calculated', 'N/A')}")
    if st.button("✏️ 編輯或重新計算我的財務參數"):
        st.session_state.edit_mode = True
        st.rerun()

    # --- 直接顯示已儲存的結果 ---
    results = saved_results
    retirement_age = saved_plan.get('retirement_age', 65)
    st.markdown("---")
    st.subheader("📊 您的退休金流總覽")

    summary = results.get('summary', {})
    analysis = summary.get('analysis', {})
    total_monthly_pension = summary.get('total_monthly_pension', 0)
    replacement_ratio = summary.get('replacement_ratio', 0)

    kpi_col1, kpi_col2 = st.columns(2)
    kpi_col1.metric(
        label=f"預計 {retirement_age} 歲退休後，每月總退休金",
        value=f"NT$ {total_monthly_pension:,.0f}"
    )
    kpi_col2.metric(
        label="所得替代率",
        value=f"{replacement_ratio:.1f} %",
        help="退休後每月收入 / 退休前月薪"
    )
    st.progress(int(min(replacement_ratio, 100)))
    st.info(f"{analysis.get('color', '⚪️')} **綜合評估：{analysis.get('level', '未知')}**")
    
    st.markdown("---")
    st.subheader("詳細分析")
    
    col1, col2 = st.columns(2)
    
    # 勞退個人專戶
    with col1:
        with st.container(border=True):
            pension = results['labor_pension']
            st.markdown("#### **勞工退休金 (個人專戶)**")
            st.metric("退休時帳戶總額", f"NT$ {pension['final_amount']:,.0f}")
            st.metric("預估月領金額", f"NT$ {pension['monthly_pension']:,.0f}" if pension['can_monthly_payment'] else "N/A (僅可一次領)")
            if not pension['can_monthly_payment']:
                st.warning("提醒：因退休時總提繳年資未滿15年，僅可一次領取。")

    # 勞保老年年金
    with col2:
        with st.container(border=True):
            insurance = results['labor_insurance']
            st.markdown("#### **勞工保險 (老年年金)**")
            st.metric("擇優公式", insurance['formula'] if insurance['eligible'] else "N/A")
            st.metric("預估月領金額", f"NT$ {insurance['monthly_pension']:,.0f}" if insurance['eligible'] else "N/A (資格不符)")
            if not insurance['eligible']:
                st.warning(f"提醒：{insurance.get('remark', '請領資格不符')}")

    # --- 敏感度分析圖表 ---
    st.markdown("---")
    st.subheader("報酬率敏感度分析")
    sensitivity_data = results['sensitivity_analysis']
    df = pd.DataFrame.from_dict(sensitivity_data, orient='index')
    df.index.name = '年化報酬率'
    df.reset_index(inplace=True)

    fig = px.bar(
        df, x='年化報酬率', y='final_amount',
        text='final_amount',
        title='不同「勞退自提專戶報酬率」對「退休時總額」的影響',
        labels={'final_amount': '退休時帳戶總額 (NT$)', '年化報酬率': '預估年化報酬率 (%)'}
    )
    fig.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
    st.plotly_chart(fig, use_container_width=True)

    # --- 逐年提繳明細 ---
    with st.expander("查看勞退個人專戶 - 逐年累積模擬"):
        details_df = pd.DataFrame(pension['contribution_details'])
        if not details_df.empty:
            # 重新命名欄位以利閱讀
            display_df = details_df.rename(columns={
                'year': '年度',
                'monthly_salary': '當年度月薪',
                'capped_salary': '提繳工資',
                'annual_contribution': '年度總提繳',
                'investment_return': '年度投資收益',
                'account_balance_before': '年初帳戶餘額'
            })
            display_df['年末總餘額'] = display_df['年初帳戶餘額'] + display_df['年度投資收益'] + display_df['年度總提繳']
            
            # 格式化顯示
            for col in ['當年度月薪', '提繳工資', '年度總提繳', '年度投資收益', '年初帳戶餘額', '年末總餘額']:
                display_df[col] = display_df[col].apply(lambda x: f"{x:,.0f}")

            st.dataframe(display_df[['年度', '當年度月薪', '年度總提繳', '年度投資收益', '年末總餘額']], use_container_width=True)

# 編輯模式 (首次進入或點擊編輯按鈕)
else:
    st.info("請填寫以下參數，讓我們為您模擬未來的財務狀況。所有資料將會自動儲存。")
    defaults = {
        'current_age': saved_plan.get('current_age', 35),
        'birth_year': saved_plan.get('birth_year', 1990),
        'retirement_age': saved_plan.get('retirement_age', 65),
        'avg_monthly_salary': saved_plan.get('avg_monthly_salary', 50000),
        'current_pension_principal': saved_plan.get('current_pension_principal', 500000),
        'self_contribution_rate': saved_plan.get('self_contribution_rate', 6.0),
        # [v4.2 優化] 新增的欄位
        'labor_insurance_start_year': saved_plan.get('labor_insurance_start_year', datetime.now().year - 10),
        'uninsured_years': saved_plan.get('uninsured_years', 0),
        'pension_contributed_years': saved_plan.get('pension_contributed_years', 10),
        'expected_return_rate': saved_plan.get('expected_return_rate', 5.0),
        'salary_growth_rate': saved_plan.get('salary_growth_rate', 2.0),
    }

    with st.form("retirement_form_v2"):
        st.subheader("1. 基本資料")
        col1, col2, col3 = st.columns(3)
        current_age = col1.number_input("目前年齡", 18, 99, defaults['current_age'])
        birth_year = col2.number_input("出生年份 (西元)", 1920, datetime.now().year, defaults['birth_year'])
        retirement_age = col3.number_input("預計退休年齡", 55, 80, defaults['retirement_age'])

        st.subheader("2. 薪資與資產")
        col1, col2, col3 = st.columns(3)
        avg_monthly_salary = col1.number_input("目前平均月薪 (請填寫稅前薪資)", 0, 200000, defaults['avg_monthly_salary'], 1000)
        current_pension_principal = col2.number_input("目前勞退個人專戶累積本金", 0, 10000000, defaults['current_pension_principal'], 10000)
        col2.caption("可登入 [勞保局e化服務系統](https://mes.bli.gov.tw/) 查詢。")
        self_contribution_rate = col3.slider("勞退個人自願提繳率 (%)", 0.0, 6.0, defaults['self_contribution_rate'], 0.5)

        st.subheader("3. 年資與成長性")
        col1, col2, col3 = st.columns(3)
        # [v4.2 優化] 改用更直覺的輸入方式
        labor_insurance_start_year = col1.number_input("勞保首次投保年份 (西元)", 1950, datetime.now().year, defaults['labor_insurance_start_year'])
        uninsured_years = col1.number_input("預計中斷投保年數", 0, 40, defaults['uninsured_years'], help="例如育嬰假、待業等沒有勞保的年資")
        pension_contributed_years = col2.number_input("目前勞退已提繳年資", 0, 50, defaults['pension_contributed_years'])
        expected_return_rate = col3.slider("預估勞退投資年化報酬率 (%)", 1.0, 12.0, defaults['expected_return_rate'], 0.5)
        salary_growth_rate = col3.slider("預估未來薪資年成長率 (%)", 0.0, 10.0, defaults['salary_growth_rate'], 0.5)

        submitted = st.form_submit_button("儲存並開始分析", use_container_width=True)

    if submitted:
        # [v4.2 優化] 前端自動計算總勞保年資
        calculated_seniority = (retirement_age - (labor_insurance_start_year - birth_year)) - uninsured_years
        
        user_inputs = {
            'current_age': current_age,
            'birth_year': birth_year,
            'retirement_age': retirement_age,
            'avg_monthly_salary': avg_monthly_salary,
            'current_pension_principal': current_pension_principal,
            'self_contribution_rate': self_contribution_rate,
            'insurance_seniority': max(0, calculated_seniority), # 確保不為負
            'labor_insurance_start_year': labor_insurance_start_year, # 一併儲存
            'uninsured_years': uninsured_years, # 一併儲存
            'pension_contributed_years': pension_contributed_years,
            'expected_return_rate': expected_return_rate,
            'salary_growth_rate': salary_growth_rate,
            'years_to_retirement': retirement_age - current_age,
            'last_calculated': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        with st.spinner("正在為您進行深度計算..."):
            analysis_results = get_full_retirement_analysis(user_inputs)
            # [v4.2 優化] 儲存輸入與結果
            save_user_data(user_id, db, user_inputs, analysis_results)
            st.toast("您的財務規劃已更新！")
            st.session_state.edit_mode = False
            st.rerun()