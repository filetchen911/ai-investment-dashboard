# file: frontend/app.py (診斷專用)

import streamlit as st
import sys
import os

# --- 診斷程式碼 ---
st.set_page_config(layout="wide")
st.title("路徑診斷腳本")

st.header("診斷資訊 from app.py")
st.write(f"**Current Working Directory (os.getcwd()):** `{os.getcwd()}`")
st.write(f"**app.py's Location (__file__):** `{os.path.abspath(__file__)}`")

st.subheader("Python 搜尋路徑 (sys.path) in app.py:")
st.json(sys.path)

st.header("正在嘗試導入 utils.py...")

try:
    from utils import print_diagnostics_from_utils
    st.success("成功從 app.py 導入 utils.py！")
    
    # 呼叫 utils.py 中的診斷函式
    print_diagnostics_from_utils()

except ImportError as e:
    st.error(f"從 app.py 導入 utils.py 失敗！")
    st.exception(e)

except Exception as e:
    st.error("發生未預期的錯誤！")
    st.exception(e)