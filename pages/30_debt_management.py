# pages/30_💳_債務管理.py
# App Version: v5.0.0
# Description: Initial version of the Debt Management module.

import streamlit as st
import pandas as pd
from datetime import datetime
from firebase_admin import firestore
from utils import init_firebase, load_user_liabilities

# --- 頁面配置 ---
st.set_page_config(layout="wide", page_title="債務管理")
st.title("💳 債務管理")

# --- 身份驗證與初始化 ---
if 'user_id' not in st.session_state:
    st.info("請先從主頁面登入，以使用此功能。")
    st.stop()

user_id = st.session_state['user_id']
db, _ = init_firebase()


def get_default_date(date_obj):
    """處理日期預設值，避免 Streamlit 錯誤"""
    if pd.isna(date_obj):
        return datetime.now().date()
    return date_obj

# --- 主體邏輯 ---
liabilities_df = load_user_liabilities(user_id)

# --- 頂部指標 ---
if not liabilities_df.empty:
    total_outstanding = liabilities_df['outstanding_balance'].sum()
    total_monthly_payment = liabilities_df['monthly_payment'].sum()
    
    col1, col2 = st.columns(2)
    col1.metric("總剩餘負債 (TWD)", f"${total_outstanding:,.0f}")
    col2.metric("總月付金 (TWD)", f"${total_monthly_payment:,.0f}")
else:
    st.info("您目前沒有建立任何債務資料。")

# --- 新增/編輯表單 ---
with st.expander("➕ 新增債務資料"):
    with st.form("debt_form", clear_on_submit=True):
        st.subheader("新增一筆債務")
        
        debt_types = ["房屋貸款", "信用貸款", "汽車貸款", "就學貸款", "其他"]
        
        c1, c2, c3 = st.columns(3)
        with c1:
            debt_type = st.selectbox("債務類型", debt_types)
            custom_name = st.text_input("自訂名稱", help="例如：我的房子、國泰世華信貸")
            total_amount = st.number_input("總貸款金額", min_value=0, step=10000)
            outstanding_balance = st.number_input("剩餘未償還本金", min_value=0, step=10000)
        with c2:
            interest_rate = st.number_input("目前年利率 (%)", min_value=0.0, max_value=20.0, step=0.01, format="%.2f")
            monthly_payment = st.number_input("每月還款金額", min_value=0, step=1000)
            loan_period_years = st.number_input("總貸款年限", min_value=0, max_value=40)
        with c3:
            start_date = st.date_input("貸款起始日期", value=datetime.now())
            grace_period_years = st.number_input("寬限期年數 (無則填0)", min_value=0, max_value=10)

        if st.form_submit_button("儲存這筆債務"):
            form_data = {
                "debt_type": debt_type,
                "custom_name": custom_name,
                "total_amount": total_amount,
                "outstanding_balance": outstanding_balance,
                "interest_rate": interest_rate,
                "monthly_payment": monthly_payment,
                "loan_period_years": loan_period_years,
                "start_date": datetime.combine(start_date, datetime.min.time()),
                "grace_period_years": grace_period_years,
                "created_at": firestore.SERVER_TIMESTAMP
            }
            db.collection('users').document(user_id).collection('liabilities').add(form_data)
            st.success(f"債務「{custom_name or debt_type}」已成功新增！")
            st.cache_data.clear()
            st.rerun()

st.markdown("---")

# --- 債務列表 ---
if not liabilities_df.empty:
    st.subheader("我的負債列表")
    st.info("ℹ️ 溫馨提醒：為確保「財務自由儀表板」的模擬結果準確，請在央行調整利率或每隔一段時間（例如：每年），點擊下方「✏️」按鈕，回來更新您各項貸款的「目前年利率」與「剩餘未償還本金」。")

    debt_categories = ["房屋貸款", "信用貸款", "汽車貸款", "就學貸款", "其他"]
    existing_categories = [cat for cat in debt_categories if cat in liabilities_df['debt_type'].unique()]

    debt_tabs = st.tabs(existing_categories)
    
    for i, category in enumerate(existing_categories):
        with debt_tabs[i]:
            category_df = liabilities_df[liabilities_df['debt_type'] == category]
            
            for _, row in category_df.iterrows():
                doc_id = row['doc_id']
                with st.container(border=True):
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.markdown(f"**{row['custom_name']}** (`{row['debt_type']}`)")
                        sub_cols = st.columns(3)
                        sub_cols[0].metric("剩餘本金", f"${row['outstanding_balance']:,.0f}")
                        sub_cols[1].metric("月付金", f"${row['monthly_payment']:,.0f}")
                        sub_cols[2].metric("目前年利率", f"{row['interest_rate']:.2f}%")

                    with col2:
                        if st.button("✏️ 編輯", key=f"edit_{doc_id}", use_container_width=True):
                            st.session_state['editing_debt_id'] = doc_id
                        if st.button("🗑️ 刪除", key=f"delete_{doc_id}", use_container_width=True):
                            db.collection('users').document(user_id).collection('liabilities').document(doc_id).delete()
                            st.success(f"債務 {row['custom_name']} 已刪除！")
                            st.cache_data.clear()
                            st.rerun()

                    if 'editing_debt_id' in st.session_state and st.session_state['editing_debt_id'] == doc_id:
                        with st.form(key=f"edit_form_{doc_id}"):
                            st.markdown("---")
                            st.subheader(f"正在編輯: {row['custom_name']}")
                            edit_c1, edit_c2, edit_c3 = st.columns(3)
                            
                            with edit_c1:
                                new_debt_type = st.selectbox("債務類型", debt_types, index=debt_types.index(row.get('debt_type', '其他')), key=f"type_{doc_id}")
                                new_custom_name = st.text_input("自訂名稱", value=row.get('custom_name', ''), key=f"name_{doc_id}")
                                new_total_amount = st.number_input("總貸款金額", min_value=0, value=row.get('total_amount', 0), step=10000, key=f"total_{doc_id}")
                                new_outstanding_balance = st.number_input("剩餘未償還本金", min_value=0, value=row.get('outstanding_balance', 0), step=10000, key=f"outstanding_{doc_id}")
                            
                            with edit_c2:
                                new_interest_rate = st.number_input("目前年利率 (%)", min_value=0.0, max_value=20.0, value=row.get('interest_rate', 0.0), step=0.01, format="%.2f", key=f"rate_{doc_id}")
                                new_monthly_payment = st.number_input("每月還款金額", min_value=0, value=row.get('monthly_payment', 0), step=1000, key=f"payment_{doc_id}")
                                new_loan_period_years = st.number_input("總貸款年限", min_value=0, max_value=40, value=row.get('loan_period_years', 0), key=f"period_{doc_id}")
                            
                            with edit_c3:
                                default_date = get_default_date(row.get('start_date'))
                                new_start_date = st.date_input("貸款起始日期", value=default_date, key=f"start_date_{doc_id}")
                                new_grace_period_years = st.number_input("寬限期年數 (無則填0)", min_value=0, max_value=10, value=row.get('grace_period_years', 0), key=f"grace_{doc_id}")

                            btn_c1, btn_c2 = st.columns(2)
                            if btn_c1.form_submit_button("儲存變更", use_container_width=True):
                                update_data = {
                                    "debt_type": new_debt_type, "custom_name": new_custom_name,
                                    "total_amount": new_total_amount, "outstanding_balance": new_outstanding_balance,
                                    "interest_rate": new_interest_rate, "monthly_payment": new_monthly_payment,
                                    "loan_period_years": new_loan_period_years,
                                    "start_date": datetime.combine(new_start_date, datetime.min.time()),
                                    "grace_period_years": new_grace_period_years
                                }
                                db.collection('users').document(user_id).collection('liabilities').document(doc_id).update(update_data)
                                st.success(f"債務「{new_custom_name}」已成功更新！")
                                del st.session_state['editing_debt_id']
                                st.cache_data.clear()
                                st.rerun()
                            
                            if btn_c2.form_submit_button("取消", type="secondary", use_container_width=True):
                                del st.session_state['editing_debt_id']
                                st.rerun()