# pages/1_📊_資產概覽.py (v4.0.2)

import streamlit as st
import pandas as pd
import numpy as np
import datetime
import plotly.express as px
from firebase_admin import firestore
from utils import (
    init_firebase, 
    update_quotes_manually, 
    load_user_assets_from_firestore, 
    load_quotes_from_firestore, 
    get_exchange_rate,
    load_historical_value
)

st.header("📊 資產概覽")

# --- 身份驗證與初始化 ---
if 'user_id' not in st.session_state:
    st.info("請先從主頁面登入，以查看您的資產。")
    st.stop()

user_id = st.session_state['user_id']
db, _ = init_firebase()

# --- 頁面主要邏輯 ---
col1_action, _ = st.columns([1, 3])
if col1_action.button("🔄 立即更新所有報價"):
    with st.spinner("正在執行報價更新..."):
        count = update_quotes_manually()
    st.success(f"報價更新完成！共處理 {count} 筆資產報價。")
    st.cache_data.clear()
    st.rerun()

with st.expander("➕ 新增資產"):
    with st.form("add_asset_form", clear_on_submit=True):
        c1,c2,c3=st.columns(3)
        asset_type = c1.selectbox("類型", ["美股", "台股", "債券", "加密貨幣", "現金", "其他"])
        symbol_input = c1.text_input("代號", help="台股或台灣上市債券ETF無需加後綴")
        quantity,cost_basis=c2.number_input("持有數量",0.0,format="%.4f"),c2.number_input("平均成本",0.0,format="%.4f")
        currency,name=c3.selectbox("幣別",["USD","TWD","USDT"]),c3.text_input("自訂名稱(可選)")
        if st.form_submit_button("確定新增"):
            if symbol_input and quantity>0 and cost_basis>0:
                final_symbol = symbol_input.strip().upper()
                if asset_type in ["台股", "債券"] and final_symbol.isdigit():
                    final_symbol = f"{final_symbol}.TW"
                
                db.collection('users').document(user_id).collection('assets').add({
                    "類型":asset_type, "代號":final_symbol, "名稱":name, 
                    "數量":float(quantity), "成本價":float(cost_basis), 
                    "幣別":currency, "建立時間":firestore.SERVER_TIMESTAMP
                })
                st.success("資產已成功新增！")
                st.cache_data.clear()
                st.rerun()
            else: st.error("代號、數量、成本價為必填欄位，且必須大於 0。")
st.markdown("---")

assets_df = load_user_assets_from_firestore(user_id)
quotes_df = load_quotes_from_firestore()
usd_to_twd_rate = get_exchange_rate("USD", "TWD")

if assets_df.empty:
    st.info("您目前沒有資產。")
else:
    df = pd.merge(assets_df, quotes_df, left_on='代號', right_on='Symbol', how='left')
    
    for col in ['數量', '成本價']: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    if 'Price' not in df.columns or df['Price'].isnull().all(): df['Price'] = df['成本價']
    else: df['Price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(df['成本價'])

    if 'PreviousClose' not in df.columns or df['PreviousClose'].isnull().all(): df['PreviousClose'] = df['Price']
    else: df['PreviousClose'] = pd.to_numeric(df['PreviousClose'], errors='coerce').fillna(df['Price'])

    df['市值'] = df['Price'] * df['數量']
    df['成本'] = df['成本價'] * df['數量']
    df['損益'] = df['市值'] - df['成本']
    df['損益比'] = np.divide(df['損益'], df['成本'], out=np.zeros_like(df['損益'], dtype=float), where=df['成本']!=0) * 100
    df['今日漲跌'] = df['Price'] - df['PreviousClose']
    df['今日總損益'] = (df['Price'] - df['PreviousClose']) * df['數量']            
    df['今日漲跌幅'] = np.divide(df['今日漲跌'], df['PreviousClose'], out=np.zeros_like(df['Price'], dtype=float), where=df['PreviousClose']!=0) * 100

    df['市值_TWD'] = df.apply(lambda r: r['市值'] * usd_to_twd_rate if r['幣別'] in ['USD', 'USDT'] else r['市值'], axis=1)
    
    df['分類'] = df['類型']
    
    total_value_twd = df['市值_TWD'].sum()
    total_cost_twd = df.apply(lambda r: r['成本'] * usd_to_twd_rate if r['幣別'] in ['USD', 'USDT'] else r['成本'], axis=1).sum()
    total_pnl_twd = total_value_twd - total_cost_twd
    total_pnl_ratio = (total_pnl_twd / total_cost_twd * 100) if total_cost_twd != 0 else 0

    if total_value_twd > 0: df['佔比'] = (df['市值_TWD'] / total_value_twd) * 100
    else: df['佔比'] = 0
                    
    k1, k2, k3 = st.columns(3)
    k1.metric("總資產價值 (約 TWD)", f"${total_value_twd:,.0f}")
    k2.metric("總損益 (約 TWD)", f"${total_pnl_twd:,.0f}", f"{total_pnl_ratio:.2f}%")
    k3.metric("美金匯率 (USD/TWD)", f"{usd_to_twd_rate:.2f}")            
    st.markdown("---")

    if total_value_twd > 0:
        st.subheader("資產配置比例")
        allocation_by_class = df.groupby('分類')['市值_TWD'].sum().reset_index()
        allocation_by_currency = df.groupby('幣別')['市值_TWD'].sum().reset_index()
        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            fig_class = px.pie(allocation_by_class, names='分類', values='市值_TWD', title='依資產類別 (台幣計價)', hole=.3)
            st.plotly_chart(fig_class, use_container_width=True)
        with chart_col2:
            fig_currency = px.pie(allocation_by_currency, names='幣別', values='市值_TWD', title='依計價幣別 (台幣計價)', hole=.3)
            st.plotly_chart(fig_currency, use_container_width=True)
    st.markdown("---")
    
    st.subheader("歷史淨值趨勢 (TWD)")
    historical_df = load_historical_value(user_id)
    
    if not historical_df.empty:
        time_range_options = ["最近30天", "最近90天", "今年以來", "所有時間"]
        time_range = st.radio("選擇時間範圍", time_range_options, horizontal=True)

        today = pd.to_datetime(datetime.date.today())
        if time_range == "最近30天":
            chart_data = historical_df[historical_df.index >= (today - pd.DateOffset(days=30))]
        elif time_range == "最近90天":
            chart_data = historical_df[historical_df.index >= (today - pd.DateOffset(days=90))]
        elif time_range == "今年以來":
            chart_data = historical_df[historical_df.index.year == today.year]
        else:
            chart_data = historical_df

        if not chart_data.empty:
            # --- [v4.0.2 修正] ---
            fig = px.line(
                chart_data, 
                x=chart_data.index, 
                y='total_value_twd', 
                title="淨值走勢",
                labels={
                    "total_value_twd": "資產總值 (TWD)", # <-- 修改 Y 軸標籤
                    "date": "日期"                       # <-- 修改 X 軸標籤
                }
            )
            
            fig.update_xaxes(dtick="W1", tickformat="%Y-%m-%d", tickangle=0)
            fig.update_layout(dragmode=False, xaxis=dict(fixedrange=True), yaxis=dict(fixedrange=True))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("所選時間範圍內沒有歷史數據。")
    else:
        st.info("歷史淨值數據正在收集中，請於明日後查看。") 
    st.markdown("---")

    if 'editing_asset_id' in st.session_state:
        asset_to_edit = df[df['doc_id'] == st.session_state['editing_asset_id']].iloc[0]
        with st.form("edit_asset_form"):
            # ... (編輯資產的表單程式碼省略，與前版相同)
    
    col_title, col_time = st.columns([3, 1])
    # ... (我的投資組合標題與更新時間省略，與前版相同)

    defined_categories = ["美股", "台股", "債券", "加密貨幣", "現金", "其他"]
    existing_categories_in_order = [cat for cat in defined_categories if cat in df['分類'].unique()]
    
    if existing_categories_in_order:
        asset_tabs = st.tabs(existing_categories_in_order)
        for i, category in enumerate(existing_categories_in_order):
            with asset_tabs[i]:
                # ... (資產列表渲染省略，與前版相同)