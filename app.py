# App Version: v5.3.0-rc3

import streamlit as st
from utils import signup_user, login_user, init_firebase, render_sidebar
from config import APP_VERSION # <--- 從 config.py 引用

# --- 初始化 ---
# st.cache_resource 確保 Firebase 只被初始化一次
@st.cache_resource
def initialize_app():
    return init_firebase()

#db, firebase_config = initialize_app()

# --- 頁面配置 ---
st.set_page_config(
    page_title="AI 投資儀表板",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)



# --- 主函數 ---
def main():
    render_sidebar()
    
    if 'user_id' in st.session_state:
        st.title("📈 歡迎來到您的 AI 投資儀表板")
        st.info("👈 請從左側側邊欄選擇您要查看的頁面。")
        st.markdown("---")
        
        # [v5.3.0-rc3 修正] 更新主頁連結以匹配新的頁面結構
        
        # 區塊 1: 財務自由儀表板
        st.subheader("財務自由儀表板")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.page_link("pages/10_asset_overview.py", label="資產總覽", icon="📊")
        with c2:
            st.page_link("pages/20_pension_overview.py", label="退休金總覽", icon="🏦")
        with c3:
            st.page_link("pages/30_debt_management.py", label="債務管理", icon="💳")
        with c4:
            # 更新連結與標籤
            st.page_link("pages/40_cashflow_simulator.py", label="現金流模擬器", icon="🌊")

        st.markdown("---")
        
        # 區塊 2: 週期投資儀表板
        st.subheader("週期投資儀表板")
        c1, c2 = st.columns(2)
        with c1:
            st.page_link("pages/50_ai_insights.py", label="AI 每日洞察", icon="💡")
        with c2:
            # 新增指向新頁面的連結
            st.page_link("pages/70_cyclical_investing_model.py", label="週期投資策略模擬器", icon="📈")      
    else:
        st.info("👋 請從左側側邊欄登入或註冊，以開始使用。")

if __name__ == "__main__":
    main()