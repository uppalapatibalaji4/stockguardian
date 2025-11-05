import streamlit as st
from utils import (
    load_investments, save_investments, send_alert_email,
    get_pnl, get_sentiment_advice, draw_forecast_chart, chat_bot_response
)
import pandas as pd
from datetime import datetime
from streamlit_chat import message

# Page config
st.set_page_config(page_title="StockGuardian", layout="wide")

# Dark theme
st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: white; }
    .stTextInput > div > div > input { background-color: #262730; color: white; }
    .stButton > button { background-color: #1e1e1e; color: white; }
    .stMetric { color: white; }
    h1, h2, h3 { color: white; }
</style>
""", unsafe_allow_html=True)

# Title + Warning
st.title("StockGuardian: Your Personal Stock Agent")
st.warning("API Limits: yfinance may throttle requests. Use sparingly. Emails hashed for security.")

# Tabs
tab_dashboard, tab_alerts, tab_chat = st.tabs(["Dashboard", "Alerts", "Chat Bot"])

with tab_alerts:
    st.header("Setup")
    with st.form("email_setup"):
        user_email = st.text_input("Enter your email for alerts:")
        sender_email = st.text_input("Sender Gmail (for SMTP):")
        app_password = st.text_input("Gmail App Password:", type="password")
        save = st.form_submit_button("Save Setup")
        if save:
            st.session_state.user_email = user_email
            st.session_state.sender_email = sender_email
            st.session_state.app_password = app_password
            st.success("Setup saved! Alerts active.")
            st.rerun()

with tab_dashboard:
    st.header("Dashboard")
    investments = load_investments()
    
    # Add Investment
    with st.form("add_investment"):
        col1, col2 = st.columns(2)
        with col1:
            ticker = st.text_input("Stock Symbol:", "TCS.NS").upper()
            buy_price = st.number_input("Buy Price:", 4000.00)
        with col2:
            qty = st.number_input("Quantity:", 1)
            date = st.date_input("Purchase Date:", datetime(2025, 11, 4))
            platform = st.selectbox("Platform:", ["Upstox", "Zerodha"])
        add = st.form_submit_button("Add Investment")
        if add:
            new = pd.DataFrame([{
                'ticker': ticker, 'buy_price': buy_price, 'qty': qty,
                'date': date.strftime('%Y-%m-%d'), 'platform': platform
            }])
            investments = pd.concat([investments, new], ignore_index=True)
            save_investments(investments)
            st.rerun()
    
    # Metrics
    if not investments.empty:
        row = investments.iloc[0]
        current, pnl_pct = get_pnl(row['ticker'], row['buy_price'], row['qty'])
        sentiment, advice = get_sentiment_advice(row['ticker'])
        
        cols = st.columns(5)
        cols[0].metric("Set", "0")
        cols[1].metric("Breakeven", f"₹{row['buy_price']:.2f}")
        cols[2].metric("Stage", f"Profit: {pnl_pct:+.1f}%")
        cols[3].metric("Sentiment", sentiment)
        cols[4].metric("Advice", advice)
        
        # Chart
        st.subheader(f"Chart & Forecast: {row['ticker']}")
        fig = draw_forecast_chart(row['ticker'])
        if fig:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No historical data.")
    else:
        st.info("Add your first investment!")

with tab_chat:
    st.header("AI Chat Bot")
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    for msg in st.session_state.messages:
        message(msg["content"], is_user=msg["role"] == "user", key=str(msg["id"]))
    
    if prompt := st.chat_input("Ask about your stocks (e.g., 'Should I buy?')"):
        st.session_state.messages.append({"role": "user", "content": prompt, "id": len(st.session_state.messages)})
        message(prompt, is_user=True)
        
        response = chat_bot_response(prompt, investments)
        st.session_state.messages.append({"role": "assistant", "content": response, "id": len(st.session_state.messages)})
        message(response)

# Auto-alerts (run on load)
if not investments.empty:
    for _, row in investments.iterrows():
        current, _ = get_pnl(row['ticker'], row['buy_price'], row['qty'])
        if current <= row['buy_price'] * 0.9:  # 10% drop
            send_alert_email(row['ticker'], current, "10% Drop")
