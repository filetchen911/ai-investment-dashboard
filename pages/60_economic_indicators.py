
# pages/3_📈_決策輔助指標.py

import streamlit as st
import pandas as pd
import datetime
from utils import (
    init_firebase, 
    load_latest_economic_data, 
    render_sidebar,
    trigger_scraper # [v5.2.0] 引入新的輔助函式
)

render_sidebar()

#st.set_page_config(layout="wide", page_title="關鍵經濟指標趨勢")
st.title("📈 關鍵經濟指標趨勢")

# --- [v5.2.0 修改] 手動更新按鈕的完整邏輯 ---
if st.button("🔄 手動更新經濟指標"):
    with st.spinner("正在從 FRED API 更新最新數據..."):
        success = trigger_scraper()
        if success:
            # 清除快取，確保下次讀取時能抓到最新數據
            st.cache_data.clear()
            st.success("數據更新成功！頁面將在2秒後自動刷新。")
            time.sleep(2)
            st.rerun()
# --- [修改結束] ---
    
# --- 身份驗證與初始化 ---
if 'user_id' not in st.session_state:
    st.info("請先從主頁面登入。")
    st.stop()
    
user_id = st.session_state['user_id']
db, _ = init_firebase()

# --- 頁面主要邏輯 ---
economic_data_report = load_latest_economic_data()

if economic_data_report:
    if 'date' in economic_data_report and isinstance(economic_data_report.get('date'), datetime.datetime):
        last_update_time = economic_data_report['date'].strftime('%Y-%m-%d %H:%M:%S')
    else:
        last_update_time = "N/A"
    st.caption(f"數據來源：{economic_data_report.get('source_name', '未知')} | 上次更新時間 (UTC): {last_update_time}")
    
    st.subheader("宏觀經濟數據趨勢")
    indicators = economic_data_report.get('data_series_items', [])
    
    if not indicators:
        st.write("暫無宏觀經濟數據。")
    else:
        col1, col2 = st.columns(2)
        for i, indicator in enumerate(indicators):
            target_col = col1 if i % 2 == 0 else col2
            with target_col:
                with st.container(border=True):
                    st.markdown(f"**{indicator.get('event', '未知指標')}**")
                    values = indicator.get('values', [])
                    if values:
                        chart_df = pd.DataFrame(values)
                        chart_df['date'] = pd.to_datetime(chart_df['date'])
                        chart_df = chart_df.set_index('date')
                        chart_df['value'] = pd.to_numeric(chart_df['value'])
                        latest_point = values[-1]
                        st.metric(label=f"最新數據 ({latest_point['date']})", value=f"{latest_point['value']}")
                        st.line_chart(chart_df)
                    else:
                        st.write("暫無趨勢數據。")
else:
    st.info("今日的宏觀經濟數據尚未生成，或正在處理中。")

