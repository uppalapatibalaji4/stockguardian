import streamlit as st
from utils import (
    load_investments, save_investments, send_alert_email,
    get_pnl, get_sentiment_advice, draw_forecast_chart, chat_bot_response
)
import pandas as pd
from datetime import datetime

# Page + Style
st.set_page_config(page_title="StockGuardian", layout="wide")
st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: white; }
    .stTextInput > div > div > input { background-color: #262730; color: white; }
    .stButton > button { background-color: #1f1f1f; color: white; }
    .stMetric { color: white; }
    h1, h2, h3 { color: white; }
    .stTabs [data-baseweb="tab"] { color: white; }
    .stTabs [data-baseweb="tab"][aria-selected="true"] { color: #ff4b4b; }
</style>
""", unsafe_allow_html=True)

st.title("StockGuardian: Your Personal Stock Agent")
st.warning("API Limits: yfinance may throttle requests. Use sparingly.")

tab_dashboard, tab_alerts, tab_chat = st.tabs(["Dashboard", "Alerts", "Chat Bot"])

# === ALERTS ===
with tab_alerts:
    st.header("Setup")
    with st.form("email_setup"):
        user_email = st.text_input("Your email:")
        sender_email = st.text_input("Sender Gmail:")
        app_password = st.text_input("App Password:", type="password")
        if st.form_submit_button("Save Setup"):
            st.session_state.user_email = user_email
            st.session_state.sender_email = sender_email
            st.session_state.app_password = app_password
            st.success("Saved!")

# === DASHBOARD ===
with tab_dashboard:
    st.header("Dashboard")
    investments = load_investments()

    # ADD NEW STOCK
    with st.form("add_investment"):
        c1, c2 = st.columns(2)
        with c1:
            new_ticker = st.text_input("Symbol:", "TCS.NS").upper()
            buy_price = st.number_input("Buy Price:", 4000.00, step=0.01)
        with c2:
            qty = st.number_input("Qty:", 1, step=1)
            date = st.date_input("Date:", datetime(2025, 11, 4))
            platform = st.selectbox("Platform:", ["Upstox", "Zerodha", "Groww"])
        if st.form_submit_button("Add"):
            new = pd.DataFrame([{
                'ticker': new_ticker, 'buy_price': buy_price, 'qty': qty,
                'date': date.strftime('%Y-%m-%d'), 'platform': platform
            }])
            investments = pd.concat([investments, new], ignore_index=True)
            save_investments(investments)
            st.success(f"{new_ticker} added!")
            st.rerun()

    # SELECT STOCK TO VIEW
    if not investments.empty:
        st.subheader("Select Stock to View")
        selected_ticker = st.selectbox("Choose:", investments['ticker'].tolist())

        # GET SELECTED ROW
        row = investments[investments['ticker'] == selected_ticker].iloc[0]

        current, pnl_pct = get_pnl(row['ticker'], row['buy_price'], row['qty'])
        sentiment, advice = get_sentiment_advice(row['ticker'])

        cols = st.columns(5)
        cols[0].metric("Set", "0")
        cols[1].metric("Breakeven", f"₹{row['buy_price']:.2f}")
        cols[2].metric("Stage", f"Profit: {pnl_pct:+.1f}%")
        cols[3].metric("Sentiment", sentiment)
        cols[4].metric("Advice", advice)

        st.subheader(f"Chart & Forecast: {row['ticker']}")
        fig = draw_forecast_chart(row['ticker'])
        if hasattr(fig, 'update_layout'):
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.pyplot(fig)
    else:
        st.info("Add your first stock!")

# === CHAT ===
with tab_chat:
    st.header("AI Chat Bot")
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ask about your stocks..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        response = chat_bot_response(prompt, investments)
        st.session_state.messages.append({"role": "assistant", "content": response})
        with st.chat_message("assistant"):
            st.markdown(response)

# Auto alerts
if not investments.empty:
    for _, r in investments.iterrows():
        current, _ = get_pnl(r['ticker'], r['buy_price'], r['qty'])
        if current <= r['buy_price'] * 0.9:
            send_alert_email(r['ticker'], current, "10% Drop")
