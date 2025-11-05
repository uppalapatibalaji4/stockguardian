import streamlit as st
import pandas as pd
from datetime import datetime

# === SAFE IMPORT FROM utils.py ===
try:
    from utils import (
        load_investments, save_investments, send_email_alert, send_whatsapp_alert,
        get_live_data, get_pnl, get_sentiment_advice, draw_trading_chart, test_alert
    )
except ImportError as e:
    st.error("utils.py file missing or misnamed. Rename to `utils.py` and retry.")
    st.stop()

# Page Setup
st.set_page_config(page_title="StockGuardian", layout="wide")
st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: white; }
    .stTextInput > div > div > input { background-color: #262730; color: white; }
    .stButton > button { background-color: #1f1f1f; color: white; border: 1px solid #444; }
    h1, h2, h3 { color: white; }
    .stTabs [data-baseweb="tab"] { color: white; }
    .stTabs [data-baseweb="tab"][aria-selected="true"] { color: #ff4b4b; }
</style>
""", unsafe_allow_html=True)

st.title("StockGuardian: Your Upstox Clone")
st.warning("Live NSE/BSE data via yfinance. Market: 9:15 AM - 3:30 PM IST")

tab1, tab2, tab3 = st.tabs(["Dashboard", "Alerts", "Chat"])

# ========================================
# ALERTS
# ========================================
with tab2:
    st.header("Alert Setup")
    c1, c2 = st.columns(2)
    with c1:
        with st.form("gmail"):
            e1 = st.text_input("Your Email")
            e2 = st.text_input("Sender Gmail")
            e3 = st.text_input("App Password", type="password")
            if st.form_submit_button("Save"):
                st.session_state.user_email = e1
                st.session_state.sender_email = e2
                st.session_state.app_password = e3
                st.success("Gmail Saved")
    with c2:
        with st.form("wa"):
            wa = st.text_input("WhatsApp (+91...)")
            if st.form_submit_button("Save"):
                st.session_state.whatsapp_number = wa
                st.success("WhatsApp Saved")

    st.markdown("---")
    test_t = st.text_input("Test Ticker", "TCS.NS")
    if st.button("Send Test Alert"):
        test_alert(test_t)

# ========================================
# DASHBOARD
# ========================================
with tab1:
    st.header("Add Stock")
    df = load_investments()

    with st.form("add"):
        c1, c2 = st.columns(2)
        with c1:
            t = st.text_input("Symbol", "TCS.NS").upper()
            b = st.number_input("Buy Price", 0.01, step=0.01)
        with c2:
            q = st.number_input("Qty", 1, step=1)
            p = st.selectbox("Platform", ["Upstox", "Zerodha"])
        if st.form_submit_button("Add"):
            new = pd.DataFrame([{
                'ticker': t, 'buy_price': b, 'qty': q,
                'date': datetime.now().strftime('%Y-%m-%d'), 'platform': p
            }])
            df = pd.concat([df, new], ignore_index=True)
            save_investments(df)
            st.success(f"{t} added!")
            st.rerun()

    if not df.empty:
        st.markdown("---")
        sel = st.selectbox("Select", df['ticker'].tolist())
        row = df[df['ticker'] == sel].iloc[0]

        data, err = get_live_data(row['ticker'])
        if err:
            st.error(err)
            cur = row['buy_price']
            pnl = 0.0
            status = "Closed"
        else:
            cur = data['current']
            pnl = ((cur - row['buy_price']) / row['buy_price']) * 100
            status = "Open" if data['market_open'] else "Closed"

        # Metrics
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Set", "0")
        c2.metric("Breakeven", f"₹{row['buy_price']:.2f}")
        c3.metric("Stage", f"Profit: {pnl:+.2f}%" if not err else "No Data")
        sent, adv = get_sentiment_advice(row['ticker'])
        c4.metric("Sentiment", sent)
        c5.metric("Advice", adv)

        if not err:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Current", f"₹{data['current']:.2f}")
            c2.metric("High", f"₹{data['high']:.2f}")
            c3.metric("Low", f"₹{data['low']:.2f}")
            c4.metric("Volume", f"{data['volume']:,.0f}")
            c1, c2 = st.columns(2)
            c1.metric("Change", f"{data['change_pct']:+.2f}%")
            c2.metric("Market", status)

        st.subheader(f"{row['ticker']} Live Chart")
        fig = draw_trading_chart(row['ticker'])
        st.pyplot(fig)

# Auto 10% Alert
if not df.empty:
    for _, r in df.iterrows():
        cur, _ = get_pnl(r['ticker'], r['buy_price'])
        if cur and cur <= r['buy_price'] * 0.9:
            send_email_alert(r['ticker'], cur, "10% Drop")
            send_whatsapp_alert(r['ticker'], cur, "10% Drop")
