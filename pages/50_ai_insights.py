# file: pages/50_ai_insights.py
# version: v5.5.0 (與現有應用框架完全相容)

import streamlit as st
import pytz
from datetime import datetime
from utils import (
    render_sidebar,
    init_firebase,
    get_general_analysis_status,
    trigger_general_analysis
)

# 遵循現有頁面模式：首先渲染側邊欄
render_sidebar()

# 遵循現有頁面模式：設定頁面標題
st.set_page_config(layout="wide")
st.title("💡 AI 每日市場洞察")
st.caption("此頁面提供由大型語言模型(LLM)生成的每日通用市場分析，整合了宏觀數據與量化模型，以提供客觀的市場洞察。")

# 遵循現有頁面模式：進行身份驗證檢查
if 'user_id' not in st.session_state:
    st.info("請先從主頁面登入，以使用此功能。")
    st.stop()

# 遵循現有頁面模式：初始化必要的變數
user_id = st.session_state['user_id']
db, _ = init_firebase()

# --------------------------------------------------------------------------------
# 顯示報告專用的函式 (這是一個獨立的輔助函式，可以安全地放在檔案頂部)
# --------------------------------------------------------------------------------
def display_analysis_report(data: dict):
    """
    專門用來渲染新版 AI 分析報告的函式
    """
    # --- 區塊 1: 報告標題與整體情緒 ---
    st.subheader(data.get("report_title", "今日市場分析"))

    sentiment_map = {
        "樂觀": "🔥", "謹慎樂觀": "🟢", "中性": "⚪",
        "謹慎悲觀": "🟠", "悲觀": "🥶"
    }
    sentiment_icon = sentiment_map.get(data.get("overall_sentiment"), "❓")
    st.metric(label="市場整體情緒", value=f"{sentiment_icon} {data.get('overall_sentiment', '未知')}")

    st.divider()

    # --- 區塊 2: 分析摘要 ---
    st.markdown("##### 📈 分析摘要")
    st.write(data.get("analysis_summary", "摘要內容缺失。"))

    st.divider()

    # --- 區塊 3: 正反方因子 (使用雙欄佈局) ---
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### ✅ 正面支撐因子")
        positive_factors = data.get("positive_factors", [])
        if not positive_factors:
            st.info("報告中未提及主要的正面因子。")
        else:
            for factor in positive_factors:
                with st.expander(f"**{factor.get('factor', '未知因子')}**", expanded=True):
                    st.markdown(f"**- 證據:** {factor.get('evidence', '無')}")
                    st.markdown(f"**- 影響:** {factor.get('implication', '無')}")

    with col2:
        st.markdown("##### ⚠️ 潛在風險因子")
        risk_factors = data.get("risk_factors", [])
        if not risk_factors:
            st.info("報告中未提及主要的風險因子。")
        else:
            for factor in risk_factors:
                with st.expander(f"**{factor.get('factor', '未知因子')}**", expanded=True):
                    st.markdown(f"**- 證據:** {factor.get('evidence', '無')}")
                    st.markdown(f"**- 影響:** {factor.get('implication', '無')}")

    st.divider()

    # --- 區塊 4: 投資結論 ---
    st.markdown("##### 🧭 投資結論")
    st.info(data.get("investment_conclusion", "結論內容缺失。"), icon="💡")

# --------------------------------------------------------------------------------
# 頁面主體邏輯 (直接在頂層執行，不使用 main() 函式)
# --------------------------------------------------------------------------------

# 使用 utils 中的函式檢查快取狀態
with st.spinner("正在檢查最新的 AI 洞察報告..."):
    analysis_status = get_general_analysis_status()

# 情況一: 報告已存在
if analysis_status.get("exists") and analysis_status.get("data"):
    report_data = analysis_status["data"]

    # 顯示報告更新時間
    try:
        last_updated_raw = report_data.get('last_updated')
        if isinstance(last_updated_raw, str):
            last_updated_utc = datetime.fromisoformat(last_updated_raw.replace('Z', '+00:00'))
        else:
            last_updated_utc = last_updated_raw.replace(tzinfo=pytz.UTC)
        
        taipei_tz = pytz.timezone("Asia/Taipei")
        last_updated_taipei = last_updated_utc.astimezone(taipei_tz)
        st.caption(f"上次分析時間: {last_updated_taipei.strftime('%Y-%m-%d %H:%M:%S')} (台北時間)")
    except Exception:
        # 如果時間解析失敗，優雅地跳過
        pass

    # 呼叫專用函式來顯示報告
    display_analysis_report(report_data)

    st.divider()

    # 提供一個手動刷新的按鈕
    if st.button("🔄 強制刷新分析報告"):
        with st.spinner("正在強制觸發後端分析服務，請稍候..."):
            success = trigger_general_analysis()
            if success:
                st.success("刷新請求已送出！頁面將在幾秒後自動重載以獲取最新報告。")
                st.cache_data.clear() # 清除前端快取
                st.rerun()
            else:
                st.error("刷新失敗，請檢查後端服務日誌。")

# 情況二: 報告不存在
else:
    st.info("今日尚無通用市場分析報告。您可以點擊下方按鈕立即產生。")
    if st.button("🚀 產生今日市場洞察報告"):
        with st.spinner("首次產生報告需要約 1-2 分鐘，請耐心等候..."):
            success = trigger_general_analysis()
            if success:
                st.success("報告已成功生成！頁面將自動刷新。")
                st.cache_data.clear() # 清除前端快取
                st.rerun()
            else:
                st.error("報告生成失敗，請稍後再試或聯繫管理員。")