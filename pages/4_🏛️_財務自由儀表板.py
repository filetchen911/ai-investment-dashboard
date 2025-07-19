# pages/4_🏛️_財務自由儀表板.py
# App Version: v4.3.1
# Depends on: utils.py v4.3.0
# Description: Fixed NameError for charts by correcting display block scope.

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
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

# --- [v4.2] 數據處理函數 ---
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

# --- [v4.2] 頁面模式切換與主體邏輯 ---

# 載入使用者資料
saved_plan, saved_results = load_user_data(user_id, db)

# 初始化/決定當前模式 (edit_mode)
if 'edit_mode' not in st.session_state:
    st.session_state.edit_mode = not bool(saved_plan)

# --- 顯示模式 ---
if not st.session_state.edit_mode and saved_results:
    # [v4.3] 數據時效性提醒
    last_updated_str = saved_plan.get('last_updated', "N/A")
    try:
        last_updated_date = datetime.strptime(last_updated_str, "%Y-%m-%d %H:%M:%S")
        if (datetime.now() - last_updated_date) > timedelta(days=180):
            st.warning(f"⚠️ 您的財務資料最後更新於 {last_updated_date.strftime('%Y-%m-%d')}，可能已過期，建議您更新以獲得最準確的分析。")
        else:
            st.success(f"✅ 財務資料最後更新於 {last_updated_date.strftime('%Y-%m-%d')}，分析結果具有高參考價值。")
    except (ValueError, TypeError):
        pass # 如果日期格式不對或不存在，則不顯示

    if st.button("✏️ 編輯我的財務參數"):
        st.session_state.edit_mode = True
        st.rerun()

    # --- [v4.3.1 修正] 將所有結果顯示區塊都放在這個 if 判斷式內 ---
    results = saved_results
    retirement_age = saved_plan.get('retirement_age', 65)
    legal_age = results.get('labor_insurance', {}).get('legal_age', 65)
    pension_monthly = results.get('labor_pension', {}).get('monthly_pension', 0)
    insurance_monthly = results.get('labor_insurance', {}).get('monthly_pension', 0)

    # 總覽區塊
    st.markdown("---")
    st.subheader("📊 您的退休金流總覽")

    retirement_age = saved_plan.get('retirement_age', 65)
    legal_age = saved_results.get('labor_insurance', {}).get('legal_age', 65)
    pension_monthly = saved_results.get('labor_pension', {}).get('monthly_pension', 0)
    insurance_monthly = saved_results.get('labor_insurance', {}).get('monthly_pension', 0)
    total_at_legal_age = pension_monthly + insurance_monthly
    
    if retirement_age < legal_age:
        # 使用 st.metric 來顯示，避免格式衝突
        col1, col2 = st.columns(2)
        with col1:
            st.metric(label=f"{retirement_age} ~ {legal_age - 1} 歲 (僅勞退)", value=f"NT$ {pension_monthly:,.0f} /月")
        with col2:
            st.metric(label=f"{legal_age} 歲起 (勞退+勞保)", value=f"NT$ {total_at_legal_age:,.0f} /月",
                      help=f"勞退 ${pension_monthly:,.0f} + 勞保 ${insurance_monthly:,.0f}")
    else:
        st.metric(
            label=f"預計 {retirement_age} 歲退休後，每月總退休金 (勞退+勞保)",
            value=f"NT$ {total_at_legal_age:,.0f}"
        )
    
    replacement_ratio = results.get('summary', {}).get('replacement_ratio', 0)
    analysis = results.get('summary', {}).get('analysis', {})
    st.metric(label="所得替代率", value=f"{replacement_ratio:.1f} %", help="退休後每月收入 / 退休前月薪")
    st.info(f"{analysis.get('color', '⚪️')} **綜合評估：{analysis.get('level', '未知')}**")

    # 詳細分析區塊
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


# --- 編輯模式 ---
else:
    st.info("請填寫以下參數，讓我們為您模擬未來的財務狀況。所有資料將會自動儲存。")
    defaults = {
        'current_age': saved_plan.get('current_age', 35),
        'birth_year': saved_plan.get('birth_year', 1990),
        'retirement_age': saved_plan.get('retirement_age', 65),
        'avg_monthly_salary': saved_plan.get('avg_monthly_salary', 50000),
        'current_pension_principal': saved_plan.get('current_pension_principal', 500000),
        'self_contribution_rate': saved_plan.get('self_contribution_rate', 6.0),
        'current_total_seniority': saved_plan.get('current_total_seniority', 10),
        'expected_return_rate': saved_plan.get('expected_return_rate', 5.0),
        'salary_growth_rate': saved_plan.get('salary_growth_rate', 2.0),
    }

    with st.form("retirement_form_v3"):
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

        submitted = st.form_submit_button("儲存並開始分析", use_container_width=True)

    if submitted:
        years_to_retirement = retirement_age - current_age
        final_seniority = current_total_seniority + years_to_retirement
        
        user_inputs = {
            'current_age': current_age,
            'birth_year': birth_year,
            'retirement_age': retirement_age,
            'avg_monthly_salary': avg_monthly_salary,
            'current_pension_principal': current_pension_principal,
            'self_contribution_rate': self_contribution_rate,
            'current_total_seniority': current_total_seniority,
            'insurance_seniority': max(0, final_seniority),
            'pension_contributed_years': max(0, final_seniority),
            'expected_return_rate': expected_return_rate,
            'salary_growth_rate': salary_growth_rate,
            'years_to_retirement': years_to_retirement,
            'last_updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        with st.spinner("正在為您進行深度計算..."):
            analysis_results = get_full_retirement_analysis(user_inputs)
            save_user_data(user_id, db, user_inputs, analysis_results)
            st.toast("您的財務規劃已更新！")
            st.session_state.edit_mode = False
            st.rerun()