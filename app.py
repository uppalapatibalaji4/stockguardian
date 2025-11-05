import streamlit as st
from utils import (
    load_investments, save_investments, send_email_alert, send_whatsapp_alert,
    get_live_data, get_pnl, get_sentiment_advice, draw_trading_chart, chat_bot_response, test_alert
)
import pandas as pd
from datetime import datetime

# Page Config
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
st.warning("API Limits: yfinance may throttle requests. Use sparingly. Emails hashed for security.")

tab_dashboard, tab_alerts, tab_chat = st.tabs(["Dashboard", "Alerts", "Chat Bot"])

# ========================================
# ALERTS TAB
# ========================================
with tab_alerts:
    st.header("Alert Setup")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Gmail")
        with st.form("gmail_form"):
            user_email = st.text_input("Enter your email for alerts:")
            sender_email = st.text_input("Sender Gmail (SMTP):")
            app_password = st.text_input("Gmail App Password:", type="password")
            submitted = st.form_submit_button("Save Setup")
            if submitted:
                st.session_state.user_email = user_email
                st.session_state.sender_email = sender_email
                st.session_state.app_password = app_password
                st.success("Setup saved! Alerts enabled.")
    with col2:
        st.subheader("WhatsApp")
        with st.form("whatsapp_form"):
            user_phone = st.text_input("WhatsApp Number (+91...):")
            submitted = st.form_submit_button("Save WhatsApp")
            if submitted:
                st.session_state.whatsapp_number = user_phone
                st.success("WhatsApp saved!")

    st.divider()
    st.subheader("Test Alert")
    test_ticker = st.text_input("Test Ticker:", "TCS.NS")
    if st.button("Send Test Alert (Live Price)"):
        test_alert(test_ticker)

# ========================================
# DASHBOARD TAB
# ========================================
with tab_dashboard:
    st.header("Add Stock")
    investments = load_investments()

    with st.form("add_stock"):
        col1, col2 = st.columns(2)
        with col1:
            ticker = st.text_input("Symbol (e.g. TCS.NS):").upper()
            buy_price = st.number_input("Buy Price:", min_value=0.01, step=0.01)
        with col2:
            qty = st.number_input("Quantity:", min_value=1, step=1)
            platform = st.selectbox("Platform:", ["Upstox", "Zerodha", "Groww"])
        submitted = st.form_submit_button("Add Stock")
        if submitted and ticker:
            new_row = pd.DataFrame({
                'ticker': [ticker], 'buy_price': [buy_price], 'qty': [qty],
                'date': [datetime.now().strftime('%Y-%m-%d')], 'platform': [platform]
            })
            investments = pd.concat([investments, new_row], ignore_index=True)
            save_investments(investments)
            st.success(f"{ticker} added!")
            st.rerun()

    if not investments.empty:
        st.subheader("Select Stock to View")
        selected_ticker = st.selectbox("Choose:", investments['ticker'].tolist())

        row = investments[investments['ticker'] == selected_ticker].iloc[0]

        data, error = get_live_data(selected_ticker)
        if error:
            st.error(error)
            current_price = row['buy_price']
            pnl_pct = 0.0
            market_status = "Closed"
        else:
            current_price = data['current']
            pnl_pct = ((current_price - row['buy_price']) / row['buy_price']) * 100
            market_status = "Open" if data['market_open'] else "Closed"

        # Metrics Row 1
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Set", "0")
        col2.metric("Breakeven", f"₹{row['buy_price']:.2f}")
        col3.metric("Stage", f"Profit: {pnl_pct:+.1f}%")
        sentiment, advice = get_sentiment_advice(selected_ticker)
        col4.metric("Sentiment", sentiment)
        col5.metric("Advice", advice)

        # Metrics Row 2 (Upstox Style)
        if not error:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Current", f"₹{data['current']:.2f}")
            col2.metric("Open", f"₹{data['open']:.2f}")
            col3.metric("High", f"₹{data['high']:.2f}")
            col4.metric("Low", f"₹{data['low']:.2f}")

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Volume", f"{data['volume']:,.0f}")
            col2.metric("Change", f"{data['change_pct']:+.2f}%")
            col3.metric("Prev Close", f"₹{data['prev_close']:.2f}")
            col4.metric("Market", market_status)

        st.subheader(f"Chart & Forecast: {selected_ticker}")
        fig = draw_trading_chart(selected_ticker)
        st.pyplot(fig)
    else:
        st.info("Add your first stock to see live data!")

# ========================================
# CHAT BOT TAB
# ========================================
with tab_chat:
    st.header("AI Chat Bot")
    investments = load_investments()

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ask about your stocks (e.g., 'How's TCS.NS?')"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        response = chat_bot_response(prompt, investments)
        st.session_state.messages.append({"role": "assistant", "content": response})
        with st.chat_message("assistant"):
            st.markdown(response)

# ========================================
# AUTO ALERTS
# ========================================
if not investments.empty:
    for _, row in investments.iterrows():
        current, _ = get_pnl(row['ticker'], row['buy_price'])
        if current and current <= row['buy_price'] * 0.9:
            send_email_alert(row['ticker'], current, "10% Drop")
            send_whatsapp_alert(row['ticker'], current, "10% Drop")
