import streamlit as st
from utils import (
    load_investments, save_investments, send_email_alert, send_whatsapp_alert,
    get_pnl, get_sentiment_advice, draw_forecast_chart, chat_bot_response
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
st.warning("API Limits: yfinance may throttle requests. Use sparingly.")

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
            user_email = st.text_input("Your Email:")
            sender_email = st.text_input("Sender Gmail:")
            app_password = st.text_input("App Password:", type="password")
            if st.form_submit_button("Save Gmail"):
                st.session_state.user_email = user_email
                st.session_state.sender_email = sender_email
                st.session_state.app_password = app_password
                st.success("Gmail saved!")

    with col2:
        st.subheader("WhatsApp")
        with st.form("whatsapp_form"):
            wa_number = st.text_input("Your WhatsApp (+91...):")
            if st.form_submit_button("Save WhatsApp"):
                st.session_state.whatsapp_number = wa_number
                st.success("WhatsApp saved!")

    st.markdown("---")
    st.subheader("Test Alerts")
    test_ticker = st.text_input("Test Ticker:", "RELIANCE.NS")
    if st.button("Send Test Alert"):
        price = 2500
        email_ok = send_email_alert(test_ticker, price, "TEST")
        wa_ok = send_whatsapp_alert(test_ticker, price, "TEST")
        st.write(f"Email: {'Sent' if email_ok else 'Failed'}")
        st.write(f"WhatsApp: {'Sent' if wa_ok else 'Failed'}")

# ========================================
# DASHBOARD TAB
# ========================================
with tab_dashboard:
    st.header("Add Stock")
    investments = load_investments()

    with st.form("add_stock"):
        c1, c2 = st.columns(2)
        with c1:
            ticker = st.text_input("Symbol (e.g. TCS.NS, AAPL):").upper()
            buy_price = st.number_input("Buy Price (₹):", min_value=0.01, step=0.01)
        with c2:
            qty = st.number_input("Quantity:", min_value=1, step=1)
            platform = st.selectbox("Platform:", ["Upstox", "Zerodha", "Groww"])
        if st.form_submit_button("Add Stock"):
            if ticker:
                new = pd.DataFrame([{
                    'ticker': ticker, 'buy_price': buy_price, 'qty': qty,
                    'date': datetime.now().strftime('%Y-%m-%d'), 'platform': platform
                }])
                investments = pd.concat([investments, new], ignore_index=True)
                save_investments(investments)
                st.success(f"{ticker} added!")
                st.rerun()

    if not investments.empty:
        st.markdown("---")
        st.subheader("Your Stocks")
        selected = st.selectbox("Select:", investments['ticker'].tolist())
        row = investments[investments['ticker'] == selected].iloc[0]

        current_price, pnl_info = get_pnl(row['ticker'], row['buy_price'], row['qty'])
        sentiment, advice = get_sentiment_advice(row['ticker'])

        if current_price is None:
            st.error(f"Market closed or {row['ticker']} not trading today.")
            current_price = row['buy_price']
            pnl_pct = 0.0
        else:
            pnl_pct = ((current_price - row['buy_price']) / row['buy_price']) * 100

        cols = st.columns(5)
        cols[0].metric("Set", "0")
        cols[1].metric("Breakeven", f"₹{row['buy_price']:.2f}")
        cols[2].metric("Stage", f"Profit: {pnl_pct:+.2f}%" if current_price else "No Data")
        cols[3].metric("Sentiment", sentiment)
        cols[4].metric("Advice", advice)

        st.subheader(f"Chart & Forecast: {row['ticker']}")
        fig = draw_forecast_chart(row['ticker'])
        if hasattr(fig, 'update_layout'):
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.pyplot(fig)

# ========================================
# CHAT BOT
# ========================================
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

# Auto 10% drop alert
if not investments.empty:
    for _, r in investments.iterrows():
        price, _ = get_pnl(r['ticker'], r['buy_price'], r['qty'])
        if price and price <= r['buy_price'] * 0.9:
            send_email_alert(r['ticker'], price, "10% Drop")
            send_whatsapp_alert(r['ticker'], price, "10% Drop")
