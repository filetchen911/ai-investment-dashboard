# pages/30_debt_management.py
# App Version: v5.0.0
# Description: Fully refactored with a single, robust "debt_form" function for both add and edit modes.

import streamlit as st
import pandas as pd
from datetime import datetime
from firebase_admin import firestore
from utils import init_firebase, load_user_liabilities, calculate_mortgage_payments, render_sidebar

render_sidebar()

# --- 頁面配置 ---
st.set_page_config(layout="wide", page_title="債務管理")
st.title("💳 債務管理")

# --- 身份驗證與初始化 ---
if 'user_id' not in st.session_state:
    st.info("請先從主頁面登入，以使用此功能。")
    st.stop()
user_id = st.session_state['user_id']
db, _ = init_firebase()

# --- [v5.0.0 最終重構] 統一的、智慧的債務表單 ---
def debt_form(mode='add', existing_data=None):
    """
    一個統一的債務表單，可用於新增(add)或編輯(edit)模式。
    具備手動試算按鈕與統一的雙月付欄位。
    """
    form_key = f"{mode}_debt_form"
    
    # 使用 session state 來儲存表單的動態值，確保刷新後狀態不遺失
    state_key = f"form_state_{mode}_{existing_data.get('doc_id', 'new') if existing_data else 'new'}"
    if state_key not in st.session_state:
        if mode == 'edit' and existing_data is not None:
            st.session_state[state_key] = existing_data
        else:
            # 新增模式，預設值全部為 0 或空
            st.session_state[state_key] = {
                "debt_type": "房屋貸款", "total_amount": 0, "outstanding_balance": 0,
                "interest_rate": 0.0, "loan_period_years": 0, "grace_period_years": 0,
                "start_date": datetime.now().date(), "custom_name": "",
                "grace_period_payment": 0, "monthly_payment": 0
            }
    s = st.session_state[state_key]

    def _calculate_payments_callback():
        # 自動試算月付金的回呼函數
        payments = calculate_mortgage_payments(s['total_amount'], s['interest_rate'], s['loan_period_years'], s['grace_period_years'])
        s['grace_period_payment'] = payments['grace_period_payment']
        s['monthly_payment'] = payments['regular_payment']

    with st.form(key=form_key):
        if mode == 'add':
            st.subheader("新增一筆債務")
        else:
            st.subheader(f"正在編輯: {s.get('custom_name', '')}")

        debt_types = ["房屋貸款", "信用貸款", "汽車貸款", "就學貸款", "其他"]
        
        c1, c2 = st.columns(2)
        with c1:
            s['debt_type'] = st.selectbox("債務類型", debt_types, index=debt_types.index(s.get('debt_type', '房屋貸款')))
            s['custom_name'] = st.text_input("自訂名稱", value=s.get('custom_name', ''), help="例如：我的房子、國泰世華信貸")
            s['total_amount'] = st.number_input("總貸款金額", min_value=0, value=int(s.get('total_amount', 0)), step=10000)
            s['outstanding_balance'] = st.number_input("剩餘未償還本金", min_value=0, value=int(s.get('outstanding_balance', 0)), step=10000)
        
        with c2:
            s['interest_rate'] = st.number_input("目前年利率 (%)", 0.0, 20.0, value=float(s.get('interest_rate', 0.0)), step=0.01, format="%.2f")
            s['loan_period_years'] = st.number_input("總貸款年限", min_value=0, max_value=40, value=int(s.get('loan_period_years', 0)))
            s['grace_period_years'] = st.number_input("寬限期年數 (無則填0)", 0, 10, value=int(s.get('grace_period_years', 0)))
            s['start_date'] = st.date_input("貸款起始日期", value=pd.to_datetime(s.get('start_date')).date() if s.get('start_date') else datetime.now().date())

        st.markdown("---")
        
        # 智慧月付金區塊
        col_calc_btn, col_grace, col_regular = st.columns([1, 2, 2])

        col_calc_btn.form_submit_button("🔄 自動試算月付金", on_click=_calculate_payments_callback)
        
        s['grace_period_payment'] = col_grace.number_input("寬限期每月還款", min_value=0, value=int(s.get('grace_period_payment', 0)), step=1000)
        s['monthly_payment'] = col_regular.number_input("非寬限期每月還款", min_value=0, value=int(s.get('monthly_payment', 0)), step=1000)
        
        st.markdown("---")

        # 表單提交按鈕
        btn_save, btn_cancel = st.columns(2)
        if btn_save.form_submit_button("儲存這筆債務" if mode == 'add' else "儲存變更", use_container_width=True):
            form_data = st.session_state[state_key].copy()
            form_data['start_date'] = datetime.combine(form_data['start_date'], datetime.min.time())
            
            if mode == 'add':
                form_data["created_at"] = firestore.SERVER_TIMESTAMP
                db.collection('users').document(user_id).collection('liabilities').add(form_data)
                st.success(f"債務「{form_data['custom_name'] or form_data['debt_type']}」已成功新增！")
            else:
                db.collection('users').document(user_id).collection('liabilities').document(existing_data['doc_id']).update(form_data)
                st.success(f"債務「{form_data['custom_name']}」已成功更新！")
                st.session_state.editing_debt_id = None

            del st.session_state[state_key]
            st.cache_data.clear()
            st.rerun()

        if mode == 'edit' and btn_cancel.form_submit_button("取消", type="secondary", use_container_width=True):
            del st.session_state[state_key]
            st.session_state.editing_debt_id = None
            st.rerun()

# --- 主體邏輯 ---
liabilities_df = load_user_liabilities(user_id)

# 頂部指標...
if not liabilities_df.empty:
    total_outstanding = liabilities_df['outstanding_balance'].sum()
    total_monthly_payment = liabilities_df['monthly_payment'].sum()
    col1, col2 = st.columns(2)
    col1.metric("總剩餘負債 (TWD)", f"${total_outstanding:,.0f}")
    col2.metric("總月付金 (TWD)", f"${total_monthly_payment:,.0f}")
else:
    st.info("您目前沒有建立任何債務資料。")

# 新增表單
with st.expander("➕ 新增債務資料", expanded=not bool(st.session_state.get('editing_debt_id'))):
    debt_form(mode='add')

st.markdown("---")

# 債務列表
if not liabilities_df.empty:
    st.subheader("我的負債列表")
    st.info("ℹ️ 溫馨提醒：為確保「財務自由儀表板」的模擬結果準確，請在央行調整利率或每隔一段時間（例如：每年），點擊下方「✏️」按鈕，回來更新您各項貸款的「目前年利率」與「剩餘未償還本金」。")

    debt_categories = ["房屋貸款", "信用貸款", "汽車貸款", "就學貸款", "其他"]
    existing_categories = [cat for cat in debt_categories if cat in liabilities_df['debt_type'].unique()]
    
    if 'editing_debt_id' not in st.session_state:
        st.session_state.editing_debt_id = None

    for _, row in liabilities_df.iterrows():
        doc_id = row['doc_id']
        with st.container(border=True):
            if st.session_state.editing_debt_id == doc_id:
                debt_form(mode='edit', existing_data=row.to_dict())
            else:
                # ... (列表項目的顯示邏輯維持不變，但可以顯示更詳細的月付金)
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"**{row['custom_name']}** (`{row['debt_type']}`)")
                    sub_cols = st.columns(3)
                    sub_cols[0].metric("剩餘本金", f"${row.get('outstanding_balance', 0):,.0f}")
                    # 根據是否有寬限期月付來決定顯示方式
                    if row.get('grace_period_payment', 0) > 0:
                         sub_cols[1].metric("月付金(本息)", f"${row.get('monthly_payment', 0):,.0f}", delta=f"寬限期 ${row.get('grace_period_payment', 0):,.0f}", delta_color="off")
                    else:
                        sub_cols[1].metric("月付金", f"${row.get('monthly_payment', 0):,.0f}")
                    sub_cols[2].metric("目前年利率", f"{row.get('interest_rate', 0.0):.2f}%")
                with col2:
                    if st.button("✏️ 編輯", key=f"edit_{doc_id}", use_container_width=True):
                        st.session_state.editing_debt_id = doc_id
                        st.rerun()
                    if st.button("🗑️ 刪除", key=f"delete_{doc_id}", use_container_width=True):
                        db.collection('users').document(user_id).collection('liabilities').document(doc_id).delete()
                        st.success(f"債務 {row['custom_name']} 已刪除！")
                        st.cache_data.clear()
                        st.rerun()                