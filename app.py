import streamlit as st
import pandas as pd
from datetime import datetime
from utils import (
    load_investments, save_investments, get_live_data, get_pnl,
    get_sentiment_advice, send_email_alert, send_whatsapp_alert, test_alert
)

# Auto-create utils.py if missing
import os
if not os.path.exists("utils.py"):
    st.error("Creating utils.py...")
    with open("utils.py", "w") as f:
        f.write(open("utils.py").read())  # Will be replaced by GitHub
    st.rerun()

st.set_page_config(page_title="StockGuardian", layout="wide")
st.markdown("<style>.stApp{background:#0e1117;color:white}</style>", unsafe_allow_html=True)
st.title("StockGuardian: Live Stock Tracker")
st.warning("Live data every 60 sec. Market: 9:15 AM - 3:30 PM IST")

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
            if st.form_submit_button("Save Gmail"):
                st.session_state.user_email = e1
                st.session_state.sender_email = e2
                st.session_state.app_password = e3
                st.success("Saved")
    with c2:
        with st.form("wa"):
            w = st.text_input("WhatsApp (+91...)")
            if st.form_submit_button("Save WhatsApp"):
                st.session_state.whatsapp_number = w
                st.success("Saved")

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
            new = pd.DataFrame([{'ticker':t,'buy_price':b,'qty':q,'date':datetime.now().strftime('%Y-%m-%d'),'platform':p}])
            df = pd.concat([df, new], ignore_index=True)
            save_investments(df)
            st.rerun()

    if not df.empty:
        sel = st.selectbox("Select", df['ticker'])
        r = df[df['ticker']==sel].iloc[0]

        data, err = get_live_data(sel)
        if err:
            st.error(err)
            cur = r['buy_price']
            pnl = 0.0
        else:
            cur = data['current']
            pnl = ((cur - r['buy_price']) / r['buy_price']) * 100

        # FULL UPSTOX GRID
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Current", f"₹{cur}")
        c2.metric("High", f"₹{data['high'] if not err else '—'}")
        c3.metric("Low", f"₹{data['low'] if not err else '—'}")
        c4.metric("Volume", f"{data['volume']:,}" if not err else "—")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("P&L", f"{pnl:+.2f}%")
        c2.metric("Change", f"{data['change_pct']:+.2f}%" if not err else "—")
        sent, adv = get_sentiment_advice(sel)
        c3.metric("Sentiment", sent)
        c4.metric("Advice", adv)

        if not err:
            st.success(f"Market {'Open' if data['market_open'] else 'Closed'}")
        else:
            st.info("Try again in 1 min (rate limit)")

# ========================================
# CHAT
# ========================================
with tab3:
    st.header("AI Chat Bot")
    df = load_investments()
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    if prompt := st.chat_input("Ask about your stock..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)

        if df.empty:
            resp = "Add a stock first!"
        else:
            t = df.iloc[0]['ticker']
            d, e = get_live_data(t)
            if e:
                resp = e
            else:
                resp = f"{t}: ₹{d['current']} (High: ₹{d['high']}, Low: ₹{d['low']})\nP&L: {((d['current']-df.iloc[0]['buy_price'])/df.iloc[0]['buy_price'])*100:+.2f}%"

        st.session_state.messages.append({"role": "assistant", "content": resp})
        with st.chat_message("assistant"): st.markdown(resp)

# Auto 10% Alert
if not df.empty:
    for _, r in df.iterrows():
        cur, _ = get_pnl(r['ticker'], r['buy_price'])
        if cur and cur <= r['buy_price'] * 0.9:
            send_email_alert(r['ticker'], cur, "10% Drop")
            send_whatsapp_alert(r['ticker'], cur, "10% Drop")
