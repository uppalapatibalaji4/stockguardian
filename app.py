import streamlit as st
from utils import (
    load_investments, save_investments, send_alert_email, send_whatsapp_alert,
    draw_flow_chart, predict_with_sentiment, export_pdf
)
import pandas as pd
from datetime import datetime

# ========================================
# SESSION STATE
# ========================================
st.session_state.setdefault("user_email", "")
st.session_state.setdefault("user_phone", "")

# ========================================
# SIDEBAR
# ========================================
with st.sidebar:
    st.header("Settings")
    st.session_state.user_email = st.text_input("Email", value=st.session_state.user_email)
    st.session_state.user_phone = st.text_input("WhatsApp (+123...)", value=st.session_state.user_phone)

    if st.button("Test Email"):
        send_alert_email("TEST", 100.0, "Test Alert", st.session_state.user_email)
    if st.button("Test WhatsApp") and st.session_state.user_phone:
        send_whatsapp_alert("TEST", 100.0, "Test Alert", st.session_state.user_phone)

    st.divider()
    st.header("Add Stock")
    with st.form("add_stock"):
        ticker = st.text_input("Ticker").upper()
        buy_price = st.number_input("Buy Price", min_value=0.01)
        qty = st.number_input("Qty", min_value=1)
        target_price = st.number_input("Target Price", value=buy_price * 1.2)
        profit_pct = st.number_input("Profit %", value=20.0)
        drop_pct = st.number_input("Drop %", value=10.0)
        submitted = st.form_submit_button("Add")
        if submitted and ticker:
            df = load_investments()
            new = pd.DataFrame([{
                "ticker": ticker, "buy_price": buy_price, "qty": qty,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "target_price": target_price, "profit_pct": profit_pct, "drop_pct": drop_pct
            }])
            df = pd.concat([df, new], ignore_index=True)
            save_investments(df)
            st.success("Added!")
            st.rerun()

# ========================================
# MAIN
# ========================================
st.title("StockGuardian")
investments = load_investments()

col1, col2 = st.columns([2, 1])
with col1:
    st.subheader("Portfolio")
    if not investments.empty:
        st.dataframe(investments)
    else:
        st.info("Add a stock")

with col2:
    st.subheader("Flow")
    fig = draw_flow_chart(investments)
    if fig: st.pyplot(fig)

# Live P&L
if not investments.empty:
    st.subheader("Live P&L")
    for _, r in investments.iterrows():
        try:
            price = yf.Ticker(r["ticker"]).history(period="1d")["Close"].iloc[-1]
            pnl = (price - r["buy_price"]) * r["qty"]
            st.metric(r["ticker"], f"${price:.2f}", f"{pnl:+.0f}")

            # Alerts
            if price >= r["target_price"]:
                send_alert_email(r["ticker"], price, "Target Hit", st.session_state.user_email)
                send_whatsapp_alert(r["ticker"], price, "Target Hit", st.session_state.user_phone)
        except: pass

# AI
st.subheader("AI Forecast")
ticker = st.text_input("Ticker")
if ticker and st.button("Predict"):
    forecast, sent = predict_with_sentiment(ticker)
    if forecast is not None:
        fig = px.line(forecast, x="ds", y="yhat")
        st.plotly_chart(fig)
        st.write(f"Sentiment: {sent:.2f}")

# PDF
if not investments.empty:
    pdf = export_pdf(investments)
    if pdf:
        st.download_button("Download PDF", pdf, "portfolio.pdf", "application/pdf")
