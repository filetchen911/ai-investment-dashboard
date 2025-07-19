
# pages/3_📈_決策輔助指標.py

import streamlit as st
import pandas as pd
import datetime
from utils import init_firebase, load_latest_economic_data

st.set_page_config(layout="wide", page_title="關鍵經濟指標趨勢")
st.title("📈 關鍵經濟指標趨勢")

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
<<<<<<< HEAD
    st.info("今日的宏觀經濟數據尚未生成，或正在處理中。")
=======
    st.info("今日的宏觀經濟數據尚未生成，或正在處理中。")
>>>>>>> 2b574fdea3656ebfc0e70ff2d6e0ceecc5a07f1e
