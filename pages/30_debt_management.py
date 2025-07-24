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
    """
    # 根據模式，決定表單的 key 和預設值
    form_key = f"{mode}_debt_form"
    if mode == 'edit':
        if existing_data is None:
            st.error("編輯模式需要提供現有資料。")
            return
        # 編輯模式，使用傳入的資料作為預設值
        defaults = existing_data
    else:
        # 新增模式，使用通用預設值
        defaults = {
            "debt_type": "房屋貸款", "total_amount": 10000000, "outstanding_balance": 8000000,
            "interest_rate": 2.15, "loan_period_years": 30, "grace_period_years": 0,
            "start_date": datetime.now().date(), "custom_name": ""
        }

    with st.form(key=form_key, clear_on_submit=(mode == 'add')):
        if mode == 'add':
            st.subheader("新增一筆債務")
        else:
            st.subheader(f"正在編輯: {defaults.get('custom_name', '')}")

        debt_types = ["房屋貸款", "信用貸款", "汽車貸款", "就學貸款", "其他"]
        
        c1, c2, c3 = st.columns(3)
        with c1:
            debt_type = st.selectbox("債務類型", debt_types, index=debt_types.index(defaults.get('debt_type', '其他')))
            custom_name = st.text_input("自訂名稱", value=defaults.get('custom_name', ''), help="例如：我的房子、國泰世華信貸")
            total_amount = st.number_input("總貸款金額", min_value=0, value=int(defaults.get('total_amount', 0)), step=10000)
            outstanding_balance = st.number_input("剩餘未償還本金", min_value=0, value=int(defaults.get('outstanding_balance', 0)), step=10000)
        
        with c2:
            interest_rate = st.number_input("目前年利率 (%)", 0.0, 20.0, value=float(defaults.get('interest_rate', 0.0)), step=0.01, format="%.2f")
            loan_period_years = st.number_input("總貸款年限", min_value=1, max_value=40, value=int(defaults.get('loan_period_years', 30)))
            grace_period_years = st.number_input("寬限期年數 (無則填0)", 0, 10, value=int(defaults.get('grace_period_years', 0)))
            
        with c3:
            start_date_val = pd.to_datetime(defaults.get('start_date')).date() if defaults.get('start_date') else datetime.now().date()
            start_date = st.date_input("貸款起始日期", value=start_date_val)
            
            # 智慧月付金輸入框
            monthly_payment_value = int(defaults.get('monthly_payment', 0))
            help_text = "請根據您的貸款合約，輸入實際的月付金額。"
            if debt_type == "房屋貸款":
                payments = calculate_mortgage_payments(total_amount, interest_rate, loan_period_years, grace_period_years)
                if monthly_payment_value == 0: # 只在沒有預設值時才自動填入
                    monthly_payment_value = payments.get('regular_payment', 0)
                help_text = f"自動試算結果約為 ${payments['regular_payment']:,.0f} (寬限期 ${payments['grace_period_payment']:,.0f})，可自行調整。"
            
            monthly_payment = st.number_input("每月還款金額", min_value=0, value=monthly_payment_value, step=1000, help=help_text)

        # 提交按鈕
        if st.form_submit_button("儲存這筆債務" if mode == 'add' else "儲存變更", use_container_width=True):
            form_data = {
                "debt_type": debt_type, "custom_name": custom_name,
                "total_amount": total_amount, "outstanding_balance": outstanding_balance,
                "interest_rate": interest_rate, "monthly_payment": monthly_payment,
                "loan_period_years": loan_period_years,
                "start_date": datetime.combine(start_date, datetime.min.time()),
                "grace_period_years": grace_period_years,
            }
            if mode == 'add':
                form_data["created_at"] = firestore.SERVER_TIMESTAMP
                db.collection('users').document(user_id).collection('liabilities').add(form_data)
                st.success(f"債務「{custom_name or debt_type}」已成功新增！")
            else:
                db.collection('users').document(user_id).collection('liabilities').document(existing_data['doc_id']).update(form_data)
                st.success(f"債務「{custom_name}」已成功更新！")
                st.session_state.editing_debt_id = None

            st.cache_data.clear()
            st.rerun()
        
        # 編輯模式下的取消按鈕
        if mode == 'edit':
            if st.form_submit_button("取消", type="secondary", use_container_width=True):
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

    debt_tabs = st.tabs(existing_categories)
    
    for i, category in enumerate(existing_categories):
        with debt_tabs[i]:
            category_df = liabilities_df[liabilities_df['debt_type'] == category]
            
            for _, row in category_df.iterrows():
                doc_id = row['doc_id']
                with st.container(border=True):
                    # 如果當前項目正在被編輯，則顯示編輯表單
                    if st.session_state.editing_debt_id == doc_id:
                        debt_form(mode='edit', existing_data=row.to_dict())
                    # 否則，正常顯示列表項目
                    else:
                        col1, col2 = st.columns([4, 1])
                        with col1:
                            st.markdown(f"**{row['custom_name']}** (`{row['debt_type']}`)")
                            sub_cols = st.columns(3)
                            sub_cols[0].metric("剩餘本金", f"${row['outstanding_balance']:,.0f}")
                            sub_cols[1].metric("月付金", f"${row['monthly_payment']:,.0f}")
                            sub_cols[2].metric("目前年利率", f"{row['interest_rate']:.2f}%")
                        with col2:
                            if st.button("✏️ 編輯", key=f"edit_{doc_id}", use_container_width=True):
                                st.session_state.editing_debt_id = doc_id
                                st.rerun()
                            if st.button("🗑️ 刪除", key=f"delete_{doc_id}", use_container_width=True):
                                db.collection('users').document(user_id).collection('liabilities').document(doc_id).delete()
                                st.success(f"債務 {row['custom_name']} 已刪除！")
                                st.cache_data.clear()
                                st.rerun()