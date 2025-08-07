# App Version: v5.3.0-rc1

# --- [v5.3.0 最終修正] 解決 Monorepo 在 Streamlit Cloud 上的路徑問題 ---
import sys
import os

# 獲取當前 app.py 檔案所在的目錄 (也就是 'frontend/' 目錄)
app_dir = os.path.dirname(os.path.abspath(__file__))

# 將這個目錄強制加入到 Python 的搜尋路徑列表的最前面
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)
# --- [修正結束] ---

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
        # --- [v5.0.0] 更新頁面連結與結構 ---
        st.subheader("核心功能")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.page_link("pages/10_asset_overview.py", label="資產總覽", icon="📊")
        with c2:
            st.page_link("pages/20_pension_overview.py", label="退休金總覽", icon="🏦")
        with c3:
            st.page_link("pages/30_debt_management.py", label="債務管理", icon="💳")
        with c4:
            st.page_link("pages/40_financial_dashboard.py", label="財務自由儀表板", icon="🏁")
        st.markdown("---")
        st.subheader("智慧洞察")
        c1, c2 = st.columns(2)
        with c1:
            st.page_link("pages/50_ai_insights.py", label="AI 每日洞察", icon="💡")
        with c2:
            st.page_link("pages/60_economic_indicators.py", label="關鍵經濟指標", icon="📈")         
    else:
        st.info("👋 請從左側側邊欄登入或註冊，以開始使用。")

if __name__ == "__main__":
    main()