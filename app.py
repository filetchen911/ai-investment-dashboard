# app.py (v4.3.1)

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
        st.sidebar.markdown("---")
        st.sidebar.caption(f"App Version: {APP_VERSION}")

# --- 主函數 ---
def main():
    show_sidebar()
    
    if 'user_id' in st.session_state:
        st.title("📈 歡迎來到您的 AI 投資儀表板")
        st.info("👈 請從左側側邊欄選擇您要查看的頁面。")
        st.markdown("---")
        st.page_link("pages/1_📊_資產概覽.py", label="前往資產概覽", icon="📊")
        st.page_link("pages/2_💡_AI_新聞精選.py", label="查看 AI 每日洞察", icon="💡")
        st.page_link("pages/3_📈_決策輔助指標.py", label="分析關鍵經濟指標", icon="📈")
        st.page_link("pages/4_🏛️_財務自由.py", label="財務自由儀表板", icon="🏛️") 
    else:
        st.info("👋 請從左側側邊欄登入或註冊，以開始使用。")

if __name__ == "__main__":
    main()