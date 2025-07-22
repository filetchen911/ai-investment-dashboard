# app.py (v5.0.0)

import streamlit as st
from utils import signup_user, login_user, init_firebase
from config import APP_VERSION

# --- 初始化 ---
# st.cache_resource 確保 Firebase 只被初始化一次
@st.cache_resource
def initialize_app():
    return init_firebase()

db, firebase_config = initialize_app()

# --- 頁面配置 ---
st.set_page_config(
    page_title="AI 投資儀表板",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 側邊欄 ---
def show_sidebar():
    if 'user_id' not in st.session_state:
        st.sidebar.header("歡迎使用")
        choice = st.sidebar.radio("請選擇操作", ["登入", "註冊"], horizontal=True)
        with st.sidebar.form("auth_form"):
            email = st.text_input("電子郵件")
            password = st.text_input("密碼", type="password")
            if st.form_submit_button("執行"):
                if not email or not password:
                    st.sidebar.warning("請輸入電子郵件和密碼。")
                else:
                    try:
                        if choice == "註冊":
                            signup_user(db, firebase_config, email, password)
                            st.sidebar.success("✅ 註冊成功！請使用您的帳號登入。")
                        elif choice == "登入":
                            user = login_user(firebase_config, email, password)
                            st.session_state['user_id'] = user['localId']
                            st.session_state['user_email'] = user['email']
                            st.rerun()
                    except Exception as e:
                        st.sidebar.error(f"操作失敗: {e}")
    else:
        st.sidebar.success(f"已登入: {st.session_state['user_email']}")
        if st.sidebar.button("登出"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

        # --- [v5.0.0 修正] 手動建立側邊欄導覽 ---
        st.sidebar.markdown("---")
        st.sidebar.page_link("pages/10_asset_overview.py", label="資產總覽", icon="📊")
        st.sidebar.page_link("pages/20_pension_overview.py", label="退休金總覽", icon="🏦")
        st.sidebar.page_link("pages/30_debt_management.py", label="債務管理", icon="💳")
        st.sidebar.page_link("pages/40_financial_dashboard.py", label="財務自由儀表板", icon="🏁")
        st.sidebar.page_link("pages/50_ai_insights.py", label="AI 每日洞察", icon="💡")
        st.sidebar.page_link("pages/60_economic_indicators.py", label="關鍵經濟指標", icon="📈")
        st.sidebar.markdown("---")
        st.sidebar.caption(f"App Version: {APP_VERSION}")

# --- 主函數 ---
def main():
    show_sidebar()
    
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