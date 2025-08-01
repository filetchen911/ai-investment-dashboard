# file: pages/50_ai_insights.py

import streamlit as st
import datetime
import time

from utils import (
    init_firebase, 
    load_latest_insights, 
    render_sidebar,
    get_general_analysis_status,    # [v5.2.0] 引入新的輔助函式
    trigger_general_analysis,       # [v5.2.0] 引入新的輔助函式
    trigger_personal_insight        # [v5.2.0] 引入新的輔助函式
)

render_sidebar()

#st.set_page_config(layout="wide", page_title="AI 每日市場洞察")
st.title("💡 AI 每日市場洞察")

# --- 身份驗證與初始化 ---
if 'user_id' not in st.session_state:
    st.info("請先從主頁面登入，以查看您的個人化 AI 洞見。")
    st.stop()

user_id = st.session_state['user_id']
db, _ = init_firebase()


# --- [v5.2.0-rc3 修正] 按鈕移至登入檢查內部 ---
if st.button("🚀 產生今日 AI 洞察"):
    with st.spinner("正在檢查您的分析狀態..."):
        # 檢查點 1：使用者個人當日報告是否已存在？
        if load_latest_insights(user_id):
            # [v5.2.0-rc3 修正] 移除 st.stop()，讓頁面繼續渲染已存在的報告
            st.info("✅ 您今日的個人化分析報告已存在。")
        else:
            # 檢查點 2：通用的「市場分析」快取是否存在且夠新？
            st.write(" > 正在檢查通用市場分析快取...")
            status = get_general_analysis_status()

            if not status["exists"] or not status["is_fresh"]:
                st.write(" > 通用分析不存在或已過時，正在啟動深層分析（可能需要1-2分鐘）...")
                success_general = trigger_general_analysis()
                if not success_general:
                    st.error("通用市場分析失敗，請稍後再試。")
                    st.stop()
            else:
                st.write(" > 發現新鮮的通用市場分析，正在使用快取...")

            # 檢查點 3：產生個人化分析
            st.write(" > 正在為您產生個人化影響分析...")
            success_personal = trigger_personal_insight(user_id)
            if success_personal:
                st.success("分析報告已成功產生！頁面將在2秒後自動刷新。")
                time.sleep(2)
                st.rerun()
            else:
                st.error("產生個人化報告時失敗，請稍後再試。")


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
    st.info("今日的 AI 分析尚未生成。您可以點擊上方的按鈕來立即產生。")