# pages/2_💡_AI_新聞精選.py
import streamlit as st
import datetime
from utils import init_firebase, load_latest_insights, render_sidebar

render_sidebar()

st.set_page_config(layout="wide", page_title="AI 每日市場洞察")
st.title("💡 AI 每日市場洞察")

# --- 身份驗證與初始化 ---
if 'user_id' not in st.session_state:
    st.info("請先從主頁面登入，以查看您的個人化 AI 洞見。")
    st.stop()

user_id = st.session_state['user_id']
db, _ = init_firebase()

# --- 頁面主要邏輯 ---
insights_data = load_latest_insights(user_id)

if insights_data:
    st.caption(f"上次分析時間: {datetime.datetime.now(datetime.timezone.utc).astimezone(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')} (台北時間)")
    
    st.subheader("今日市場總結")
    st.info(insights_data.get('market_summary', '暫無總結。'))
    
    st.subheader("對您投資組合的潛在影響")
    st.warning(insights_data.get('portfolio_impact', '暫無影響分析。'))
    
    st.markdown("---")
    
    st.subheader("核心洞見摘要")
    key_takeaways = insights_data.get('key_takeaways', [])
    
    if not key_takeaways:
        st.write("今日無核心洞見。")
    else:
        for item in key_takeaways:
            icon = "📊" if item.get('type') == '數據洞見' else "📰"
            with st.container(border=True):
                st.markdown(f"**{icon} {item.get('type', '洞見')}** | 來源：{item.get('source', '未知')}")
                st.write(item.get('content', ''))
                if item.get('type') == '新聞洞見' and item.get('link'):
                    st.link_button("查看原文", item['link'])
                    
else:
    st.info("今日的 AI 分析尚未生成，或正在處理中。請稍後再回來查看。")