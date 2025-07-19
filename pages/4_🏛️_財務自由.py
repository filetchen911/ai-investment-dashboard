# pages/4_🏛️_財務自由.py
# App Version: v4.1.0
# Depends on: utils.py v4.1.0

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from utils import init_firebase, get_full_retirement_analysis

# --- 頁面配置 ---
st.set_page_config(layout="wide", page_title="財務自由儀表板")
st.title("🏛️ 財務自由儀表板")
st.caption("輸入您的財務參數，模擬未來的退休金流，規劃您的財務自由之路。")

# --- 身份驗證與初始化 ---
if 'user_id' not in st.session_state:
    st.info("請先從主頁面登入，以使用此功能。")
    st.stop()

user_id = st.session_state['user_id']
db, _ = init_firebase()

# --- 函數：讀取與儲存使用者的退休規劃 ---
def load_retirement_plan(uid, db_client):
    user_doc = db_client.collection('users').document(uid).get()
    if user_doc.exists and 'retirement_plan' in user_doc.to_dict():
        return user_doc.to_dict()['retirement_plan']
    return {}

# --- 主體邏輯 ---
# 載入使用者儲存的計畫，如果沒有則使用預設值
saved_plan = load_retirement_plan(user_id, db)
defaults = {
    'current_age': saved_plan.get('current_age', 35),
    'birth_year': saved_plan.get('birth_year', 1990),
    'retirement_age': saved_plan.get('retirement_age', 65),
    'avg_monthly_salary': saved_plan.get('avg_monthly_salary', 50000),
    'current_pension_principal': saved_plan.get('current_pension_principal', 500000),
    'self_contribution_rate': saved_plan.get('self_contribution_rate', 6.0),
    'insurance_seniority': saved_plan.get('insurance_seniority', 10),
    'pension_contributed_years': saved_plan.get('pension_contributed_years', 10),
    'expected_return_rate': saved_plan.get('expected_return_rate', 5.0),
    'salary_growth_rate': saved_plan.get('salary_growth_rate', 2.0),
}

# --- 輸入表單 ---
with st.form("retirement_form"):
    st.subheader("1. 基本資料")
    col1, col2, col3 = st.columns(3)
    with col1:
        current_age = st.number_input("目前年齡", min_value=18, max_value=99, value=defaults['current_age'])
    with col2:
        birth_year = st.number_input("出生年份 (西元)", min_value=1920, max_value=datetime.now().year, value=defaults['birth_year'])
    with col3:
        retirement_age = st.number_input("預計退休年齡", min_value=55, max_value=80, value=defaults['retirement_age'])

    st.subheader("2. 薪資與資產")
    col1, col2, col3 = st.columns(3)
    with col1:
        avg_monthly_salary = st.number_input("目前平均月薪 (用於計算勞保/勞退)", min_value=0, value=defaults['avg_monthly_salary'], step=1000)
    with col2:
        current_pension_principal = st.number_input("目前勞退個人專戶累積本金", min_value=0, value=defaults['current_pension_principal'], step=10000)
    with col3:
        self_contribution_rate = st.slider("勞退個人自願提繳率 (%)", min_value=0.0, max_value=6.0, value=defaults['self_contribution_rate'], step=0.5)

    st.subheader("3. 年資與成長性")
    col1, col2, col3 = st.columns(3)
    with col1:
        insurance_seniority = st.number_input("預計退休時總勞保年資", min_value=0, max_value=50, value=defaults['insurance_seniority'])
    with col2:
        pension_contributed_years = st.number_input("目前勞退已提繳年資", min_value=0, max_value=50, value=defaults['pension_contributed_years'])
    with col3:
        expected_return_rate = st.slider("預估勞退投資年化報酬率 (%)", min_value=1.0, max_value=12.0, value=defaults['expected_return_rate'], step=0.5)
        salary_growth_rate = st.slider("預估未來薪資年成長率 (%)", min_value=0.0, max_value=10.0, value=defaults['salary_growth_rate'], step=0.5)

    # 提交按鈕
    submitted = st.form_submit_button("開始計算分析", use_container_width=True)


# --- 計算與顯示結果 ---
if submitted:
    # 收集使用者輸入
    user_inputs = {
        'current_age': current_age,
        'birth_year': birth_year,
        'retirement_age': retirement_age,
        'avg_monthly_salary': avg_monthly_salary,
        'current_pension_principal': current_pension_principal,
        'self_contribution_rate': self_contribution_rate,
        'insurance_seniority': insurance_seniority,
        'pension_contributed_years': pension_contributed_years,
        'expected_return_rate': expected_return_rate,
        'salary_growth_rate': salary_growth_rate,
        'years_to_retirement': retirement_age - current_age
    }
    # 儲存使用者輸入
    db.collection('users').document(user_id).update({'retirement_plan': user_inputs})
    st.toast("您的規劃已儲存！")

    # 呼叫後端計算引擎
    with st.spinner("正在為您進行深度計算..."):
        analysis_results = get_full_retirement_analysis(user_inputs)
        st.session_state['analysis_results'] = analysis_results

# 顯示結果 (如果存在)
if 'analysis_results' in st.session_state:
    results = st.session_state['analysis_results']

    # 檢查是否有驗證錯誤
    if results['validation_errors']:
        for error in results['validation_errors']:
            st.error(f"輸入錯誤: {error}")
    else:
        st.markdown("---")
        st.subheader("📊 您的退休金流總覽")

        summary = results['summary']
        analysis = summary['analysis']
        total_monthly_pension = summary['total_monthly_pension']
        replacement_ratio = summary['replacement_ratio']

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
        st.info(f"{analysis['color']} **綜合評估：{analysis['level']}**")

        # --- 詳細分析區塊 ---
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