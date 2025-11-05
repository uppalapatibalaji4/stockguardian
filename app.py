import streamlit as st
from utils import (
    load_investments, save_investments, send_email_alert, send_whatsapp_alert,
    get_live_data, get_pnl, get_sentiment_advice, draw_trading_chart, test_alert
)
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="StockGuardian", layout="wide")
st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: white; }
    .stTextInput > div > div > input { background-color: #262730; color: white; }
    .stButton > button { background-color: #1f1f1f; color: white; border: 1px solid #444; }
    .stMetric { color: white; }
    h1, h2, h3 { color: white; }
    .stTabs [data-baseweb="tab"] { color: white; }
    .stTabs [data-baseweb="tab"][aria-selected="true"] { color: #ff4b4b; }
</style>
""", unsafe_allow_html=True)

st.title("StockGuardian: Your Personal Stock Agent")
st.warning("Live data from yfinance. Market hours: 9:15 AM - 3:30 PM IST.")

tab_dashboard, tab_alerts, tab_chat = st.tabs(["Dashboard", "Alerts", "Chat Bot"])

# ========================================
# ALERTS
# ========================================
with tab_alerts:
    st.header("Alert Setup")
    c1, c2 = st.columns(2)
    with c1:
        with st.form("gmail"):
            user_email = st.text_input("Your Email")
            sender = st.text_input("Sender Gmail")
            pwd = st.text_input("App Password", type="password")
            if st.form_submit_button("Save Gmail"):
                st.session_state.user_email = user_email
                st.session_state.sender_email = sender
                st.session_state.app_password = pwd
                st.success("Saved")
    with c2:
        with st.form("wa"):
            wa = st.text_input("WhatsApp (+91...)")
            if st.form_submit_button("Save WhatsApp"):
                st.session_state.whatsapp_number = wa
                st.success("Saved")

    st.markdown("---")
    test_ticker = st.text_input("Test Ticker", "TCS.NS")
    if st.button("Send Test Alert (Live Price)"):
        test_alert(test_ticker)

# ========================================
# DASHBOARD
# ========================================
with tab_dashboard:
    st.header("Add Stock")
    investments = load_investments()

    with st.form("add"):
        c1, c2 = st.columns(2)
        with c1:
            ticker = st.text_input("Symbol", "TCS.NS").upper()
            buy = st.number_input("Buy Price", 0.01, step=0.01)
        with c2:
            qty = st.number_input("Qty", 1, step=1)
            platform = st.selectbox("Platform", ["Upstox", "Zerodha"])
        if st.form_submit_button("Add"):
            new = pd.DataFrame([{'ticker': ticker, 'buy_price': buy, 'qty': qty,
                                'date': datetime.now().strftime('%Y-%m-%d'), 'platform': platform}])
            investments = pd.concat([investments, new], ignore_index=True)
            save_investments(investments)
            st.rerun()

    if not investments.empty:
        st.markdown("---")
        selected = st.selectbox("Select", investments['ticker'].tolist())
        row = investments[investments['ticker'] == selected].iloc[0]

        data, error = get_live_data(row['ticker'])
        if error:
            st.error(error)
            current_price = row['buy_price']
            pnl_pct = 0.0
            market_status = "Closed"
        else:
            current_price = data['current']
            pnl_pct = ((current_price - row['buy_price']) / row['buy_price']) * 100
            market_status = "Open" if data['market_open'] else "Closed"

        # SAFE METRICS
        cols = st.columns(5)
        cols[0].metric("Set", "0")
        cols[1].metric("Breakeven", f"₹{row['buy_price']:.2f}")
        cols[2].metric("Stage", f"Profit: {pnl_pct:+.2f}%" if not error else "No Data")
        sentiment, advice = get_sentiment_advice(row['ticker'])
        cols[3].metric("Sentiment", sentiment)
        cols[4].metric("Advice", advice)

        # UPSTOX GRID
        if not error:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Current", f"₹{data['current']:.2f}")
            c2.metric("High", f"₹{data['high']:.2f}")
            c3.metric("Low", f"₹{data['low']:.2f}")
            c4.metric("Volume", f"{data['volume']:,.0f}")

            c1, c2 = st.columns(2)
            c1.metric("Change %", f"{data['change_pct']:+.2f}%")
            c2.metric("Market", market_status)

        st.subheader(f"{row['ticker']} Live Chart")
        fig = draw_trading_chart(row['ticker'])
        st.pyplot(fig)

# ========================================
# CHAT
# ========================================
with tab_chat:
    st.header("AI Chat Bot")
    if "messages" not in st.session_state:
        st.session_state.messages = []
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    if prompt := st.chat_input("Ask..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        response = "Ask: 'How is TCS?'"
        st.session_state.messages.append({"role": "assistant", "content": response})
        with st.chat_message("assistant"):
            st.markdown(response)

# Auto Alerts
if not investments.empty:
    for _, r in investments.iterrows():
        current, _ = get_pnl(r['ticker'], r['buy_price'])
        if current and current <= r['buy_price'] * 0.9:
            send_email_alert(r['ticker'], current, "10% Drop")
            send_whatsapp_alert(r['ticker'], current, "10% Drop")
