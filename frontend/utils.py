# file: frontend/utils.py (診斷專用)

import streamlit as st
import sys
import os

def print_diagnostics_from_utils():
    """
    這個函式被 app.py 呼叫，用來打印出 utils.py 內部的路徑資訊。
    """
    st.header("診斷資訊 from utils.py")
    st.write(f"**Current Working Directory (os.getcwd()):** `{os.getcwd()}`")
    st.write(f"**utils.py's Location (__file__):** `{os.path.abspath(__file__)}`")

    st.subheader("Python 搜尋路徑 (sys.path) in utils.py:")
    st.json(sys.path)
    
    st.header("正在嘗試導入 config.py...")
    
    try:
        from config import APP_VERSION
        st.success("成功從 utils.py 導入 config.py！")
        st.info(f"讀取到的 APP_VERSION: {APP_VERSION}")
    except ImportError as e:
        st.error(f"從 utils.py 導入 config.py 失敗！")
        st.exception(e)