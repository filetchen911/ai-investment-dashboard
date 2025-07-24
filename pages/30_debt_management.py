# pages/30_debt_management.py
# App Version: v5.0.0
# Description: Final refactored version with a state-driven smart form and generalized loan calculator.

import streamlit as st
import pandas as pd
from datetime import datetime
from firebase_admin import firestore
from utils import init_firebase, load_user_liabilities, calculate_loan_payments, render_sidebar

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

# --- [v5.0.0 最終重構] 統一的、狀態驅動的智慧債務表單 ---
def debt_form(mode='add', existing_data=None):
    """
    一個統一的債務表單，其所有狀態都由 session_state 驅動。
    """
    # 為每個表單實例建立唯一的 state key
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

    def _update_and_calculate():
        """回呼函數：先從介面更新 state，再用 state 進行計算"""
        # 1. 從 widget 的 key 更新 session state
        for key in ['debt_type', 'custom_name', 'total_amount', 'outstanding_balance', 'interest_rate', 'loan_period_years', 'grace_period_years', 'start_date', 'grace_period_payment', 'monthly_payment']:
            widget_key = f"widget_{mode}_{key}"
            if widget_key in st.session_state:
                s[key] = st.session_state[widget_key]
        
        # 2. 執行計算
        payments = calculate_loan_payments(s['total_amount'], s['interest_rate'], s['loan_period_years'], s['grace_period_years'])
        s['grace_period_payment'] = payments['grace_period_payment']
        s['monthly_payment'] = payments['regular_payment']

    with st.form(key=f"{mode}_debt_form"):
        st.subheader("新增一筆債務" if mode == 'add' else f"正在編輯: {s.get('custom_name', '')}")

        debt_types = ["房屋貸款", "信用貸款", "汽車貸款", "就學貸款", "其他"]
        
        c1, c2 = st.columns(2)
        with c1:
            st.selectbox("債務類型", debt_types, index=debt_types.index(s.get('debt_type', '房屋貸款')), key=f"widget_{mode}_debt_type")
            st.text_input("自訂名稱", value=s.get('custom_name', ''), help="例如：我的房子、國泰世華信貸", key=f"widget_{mode}_custom_name")
            st.number_input("總貸款金額", min_value=0, value=int(s.get('total_amount', 0)), step=10000, key=f"widget_{mode}_total_amount")
            st.number_input("剩餘未償還本金", min_value=0, value=int(s.get('outstanding_balance', 0)), step=10000, key=f"widget_{mode}_outstanding_balance")
        
        with c2:
            st.number_input("目前年利率 (%)", 0.0, 20.0, value=float(s.get('interest_rate', 0.0)), step=0.01, format="%.2f", key=f"widget_{mode}_interest_rate")
            st.number_input("總貸款年限", min_value=0, max_value=40, value=int(s.get('loan_period_years', 0)), key=f"widget_{mode}_loan_period_years")
            st.number_input("寬限期年數 (無則填0)", 0, 10, value=int(s.get('grace_period_years', 0)), key=f"widget_{mode}_grace_period_years")
            st.date_input("貸款起始日期", value=pd.to_datetime(s.get('start_date')).date() if s.get('start_date') else datetime.now().date(), key=f"widget_{mode}_start_date")

        st.markdown("---")
        
        col_calc_btn, col_grace, col_regular = st.columns([1, 2, 2])
        col_calc_btn.form_submit_button("🔄 自動試算月付金", on_click=_update_and_calculate)
        
        col_grace.number_input("寬限期每月還款", min_value=0, value=int(s.get('grace_period_payment', 0)), step=1000, key=f"widget_{mode}_grace_period_payment")
        col_regular.number_input("非寬限期每月還款", min_value=0, value=int(s.get('monthly_payment', 0)), step=1000, key=f"widget_{mode}_monthly_payment")
        
        st.markdown("---")

        btn_save, btn_cancel = st.columns(2)
        if btn_save.form_submit_button("儲存這筆債務" if mode == 'add' else "儲存變更", use_container_width=True):
            # 提交時，再次從 widget 更新 state，確保萬無一失
            for key in ['debt_type', 'custom_name', 'total_amount', 'outstanding_balance', 'interest_rate', 'loan_period_years', 'grace_period_years', 'start_date', 'grace_period_payment', 'monthly_payment']:
                widget_key = f"widget_{mode}_{key}"
                if widget_key in st.session_state:
                    s[key] = st.session_state[widget_key]

            form_data = st.session_state[state_key].copy()
            form_data['start_date'] = datetime.combine(form_data['start_date'], datetime.min.time())
            
            if mode == 'add':
                form_data["created_at"] = firestore.SERVER_TIMESTAMP
                db.collection('users').document(user_id).collection('liabilities').add(form_data)
                st.success(f"債務「{form_data['custom_name'] or form_data['debt_type']}」已成功新增！")
                st.session_state.show_add_form = False
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
    
# --- [重構] 使用獨立的 session_state 來控制新增表單的顯示 ---
if 'show_add_form' not in st.session_state:
    st.session_state.show_add_form = False

def toggle_add_form():
    st.session_state.show_add_form = not st.session_state.show_add_form

st.button("➕ 新增債務資料", on_click=toggle_add_form)

if st.session_state.show_add_form:
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