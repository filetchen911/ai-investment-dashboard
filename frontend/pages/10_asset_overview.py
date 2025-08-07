# pages/10_asset_overview.py
# App Version: v5.2.0
# Description: Refactored to use the central calculate_asset_metrics function from utils.


import streamlit as st
import pandas as pd
import numpy as np
import datetime
import plotly.express as px
from firebase_admin import firestore
from ..utils import (
    render_sidebar,
    init_firebase, 
    update_quotes_manually, 
    load_user_assets_from_firestore, 
    load_quotes_from_firestore, 
    get_exchange_rate,
    load_historical_value,
    calculate_asset_metrics # <-- [v5.0.0] 引入新的指標計算中心
)

render_sidebar()

st.set_page_config(layout="wide")
st.title("📊 資產概覽")

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

# --- [v5.0.0 重構核心] ---
# 1. 讀取最原始的資產數據
assets_df = load_user_assets_from_firestore(user_id)

# 2. 呼叫唯一的「指標計算中心」來處理數據
#    所有複雜的 merge 和計算都已封裝在 calculate_asset_metrics 函數中
df = calculate_asset_metrics(assets_df)
# --- [重構結束] ---
quotes_df = load_quotes_from_firestore()
usd_to_twd_rate = get_exchange_rate("USD", "TWD")

if assets_df.empty:
    st.info("您目前沒有資產。")
else:
    # 1. 直接從 utils 獲取最準確的即時匯率
    usd_to_twd_rate = get_exchange_rate("USD", "TWD")    
    # 從重構後的 df 中，直接提取需要顯示的總覽數據
    # 這些計算現在由 calculate_asset_metrics 保證與其他模組一致
    total_value_twd = df['市值_TWD'].sum()

    # 為了計算總損益，我們需要先計算台幣計價的總成本
    # (這部分邏輯也由 calculate_asset_metrics 處理，但總計需要在頁面完成)
    total_cost_twd = df.apply(lambda r: r['成本'] * usd_to_twd_rate if r['幣別'] in ['USD', 'USDT'] else r['成本'], axis=1).sum()
    total_pnl_twd = total_value_twd - total_cost_twd
    total_pnl_ratio = (total_pnl_twd / total_cost_twd * 100) if total_cost_twd != 0 else 0
                    
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
            st.subheader(f"✏️ 正在編輯資產: {asset_to_edit.get('名稱', asset_to_edit['代號'])}")
            
            asset_types = ["美股", "台股", "債券", "加密貨幣", "現金", "其他"]
            try:
                current_type_index = asset_types.index(asset_to_edit.get('類型', '其他'))
            except ValueError:
                current_type_index = 5
            
            new_type = st.selectbox("類型", asset_types, index=current_type_index)
            new_symbol = st.text_input("代號", value=asset_to_edit.get('代號', ''), help="台股或台灣上市債券ETF無需加後綴")
            new_quantity = st.number_input("持有數量", 0.0, format="%.4f", value=asset_to_edit['數量'])
            new_cost_basis = st.number_input("平均成本", 0.0, format="%.4f", value=asset_to_edit['成本價'])
            new_name = st.text_input("自訂名稱(可選)", value=asset_to_edit.get('名稱', ''))
            
            if st.form_submit_button("儲存變更"):
                # [v3.1.6] 直接儲存用戶輸入的乾淨代號
                update_data = {
                    "類型": new_type,
                    "代號": new_symbol.strip().upper(),
                    "數量": float(new_quantity),
                    "成本價": float(new_cost_basis),
                    "名稱": new_name
                }
                db.collection('users').document(user_id).collection('assets').document(st.session_state['editing_asset_id']).update(update_data)
                st.success("資產已成功更新！")
                del st.session_state['editing_asset_id']
                st.cache_data.clear()
                st.rerun()
    
    col_title, col_time = st.columns([3, 1])
    with col_title:
        st.subheader("我的投資組合")
    with col_time:
        if 'Timestamp' in quotes_df.columns and not quotes_df['Timestamp'].isnull().all():
            last_updated_utc = quotes_df['Timestamp'].max()
            taipei_tz = datetime.timezone(datetime.timedelta(hours=8))
            last_updated_taipei = last_updated_utc.astimezone(taipei_tz)
            formatted_time = last_updated_taipei.strftime('%y-%m-%d %H:%M')
            st.markdown(f"<p style='text-align: right; color: #888; font-size: 0.9em;'>更新於: {formatted_time}</p>", unsafe_allow_html=True)

    defined_categories = ["美股", "台股", "債券", "加密貨幣", "現金", "其他"]
    existing_categories_in_order = [cat for cat in defined_categories if cat in df['分類'].unique()]
    
    if existing_categories_in_order:
        asset_tabs=st.tabs(existing_categories_in_order)
        for i, category in enumerate(existing_categories_in_order):
            with asset_tabs[i]:
                category_df=df[df['分類']==category]                  
                cat_value_twd = category_df['市值_TWD'].sum()
                cat_cost_twd = category_df.apply(lambda r: r['成本'] * usd_to_twd_rate if r['幣別'] in ['USD', 'USDT'] else r['成本'], axis=1).sum()
                cat_pnl_twd = cat_value_twd - cat_cost_twd
                cat_pnl_ratio = (cat_pnl_twd / cat_cost_twd * 100) if cat_cost_twd != 0 else 0
                c1,c2=st.columns(2)
                c1.metric(f"{category} 市值 (約 TWD)",f"${cat_value_twd:,.0f}")
                c2.metric(f"{category} 損益 (約 TWD)",f"${cat_pnl_twd:,.0f}",f"{cat_pnl_ratio:.2f}%")
                st.markdown("---")

                header_cols = st.columns([2, 1.5, 1.8, 2, 1.5, 1.5, 1.5])
                headers = ["持倉", "數量", "現價", "今日漲跌", "成本", "市值", ""]
                for col, header in zip(header_cols, headers):
                    col.markdown(f"**{header}**")
                st.markdown('<hr style="margin-top:0; margin-bottom:0.5rem; opacity: 0.3;">', unsafe_allow_html=True)                        

                for _, row in category_df.iterrows():
                    doc_id = row.get('doc_id')
                    cols = st.columns([2, 1.5, 1.8, 2, 1.5, 1.5, 1.5])
                    with cols[0]:
                        # 顯示時，移除台股的 .TW 或 .TWO 後綴
                        display_symbol = row.get('代號', '')
                        if row.get('類型') == '台股' and (display_symbol.upper().endswith('.TW') or display_symbol.upper().endswith('.TWO')):
                            display_symbol = display_symbol.split('.')[0]
                        st.markdown(f"**{display_symbol}**") # <-- 使用處理過的變數
                        st.caption(row.get('名稱') or row.get('類型', ''))


                    with cols[1]:
                        st.write(f"{row.get('數量', 0):.4f}")
                    
                    with cols[2]:
                        st.write(f"{row.get('Price', 0):,.2f}")

                    with cols[3]:
                        st.metric(label="", value="", 
                                  delta=f"{row.get('今日漲跌', 0):,.2f} ({row.get('今日漲跌幅', 0):.2f}%)",
                                  label_visibility="collapsed")

                    with cols[4]:
                        st.write(f"{row.get('成本價', 0):,.2f}")
                    
                    with cols[5]:
                        st.write(f"{row.get('市值', 0):,.2f}")
                    
                    # [v3.1.4 修正] 操作按鈕
                    with cols[6]:
                        btn_cols = st.columns([1,1])
                        if btn_cols[0].button("✏️", key=f"edit_{doc_id}", help="編輯"):
                            st.session_state['editing_asset_id'] = doc_id
                            st.rerun()
                        if btn_cols[1].button("🗑️", key=f"delete_{doc_id}", help="刪除"):
                            db.collection('users').document(user_id).collection('assets').document(doc_id).delete()
                            st.success(f"資產 {row['代號']} 已刪除！")
                            # 強制清除所有數據快取
                            st.cache_data.clear()
                            st.rerun()
                    
                    with st.expander("查看詳細分析"):
                        pnl = row.get('損益', 0)
                        pnl_ratio = row.get('損益比', 0)
                        today_pnl = row.get('今日總損益', 0)
                        asset_weight = (row.get('市值_TWD', 0) / total_value_twd * 100) if total_value_twd > 0 else 0
                        
                        expander_cols = st.columns(3)
                        expander_cols[0].metric(label="今日總損益", value=f"{today_pnl:,.2f} {row.get('幣別','')}")
                        expander_cols[1].metric(label="累計總損益", value=f"{pnl:,.2f}", delta=f"{pnl_ratio:.2f}%")
                        expander_cols[2].metric(label="佔總資產比例", value=f"{asset_weight:.2f}%")
                    st.divider()