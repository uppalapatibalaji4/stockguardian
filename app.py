# app.py: Main Streamlit app for StockGuardian
import streamlit as st
import pandas as pd
from utils import *
import threading
import schedule
import time
import requests  # FOR GEMINI
import os

# Initialize DB and session state
conn = setup_db()
if 'investments' not in st.session_state:
    st.session_state.investments = []
if 'email' not in st.session_state:
    st.session_state.email = ""
if 'sender_email' not in st.session_state:
    st.session_state.sender_email = os.getenv('EMAIL_SENDER', '')
if 'sender_password' not in st.session_state:
    st.session_state.sender_password = os.getenv('EMAIL_PASSWORD', '')

# FREE GEMINI AI (NO distilgpt2!)
def gemini_chat(query, context=""):
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={st.secrets['GEMINI_API_KEY']}"
        data = {
            "contents": [{
                "parts": [{
                    "text": f"You are a stock expert. User holds: {context}. Question: {query}. Reply in 2-3 sentences, be sharp and confident."
                }]
            }]
        }
        r = requests.post(url, json=data, timeout=15)
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return "Gemini is thinking... Try again."

# Background scheduler
def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

schedule.every(10).minutes.do(check_alerts, conn, st.session_state.sender_email, st.session_state.sender_password)
if not hasattr(st, "scheduler_started"):
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    st.scheduler_started = True

# UI
st.title("StockGuardian: Your Personal Stock Agent")
st.warning("API Limits: yfinance may throttle requests. Use sparingly. Emails hashed for security.")

# Setup
if not st.session_state.email:
    st.subheader("Setup")
    email = st.text_input("Enter your email for alerts:")
    sender_email = st.text_input("Sender Gmail (for SMTP):", value=st.session_state.sender_email)
    sender_password = st.text_input("Gmail App Password:", type="password", value=st.session_state.sender_password)
    if st.button("Save Setup"):
        if "@" in email and sender_email and sender_password:
            st.session_state.email = email
            st.session_state.sender_email = sender_email
            st.session_state.sender_password = sender_password
            st.success("Setup saved! Proceed to tabs.")
        else:
            st.error("Please fill all fields correctly.")
else:
    tab1, tab2, tab3 = st.tabs(["Dashboard", "Alerts", "Chat Bot"])

    with tab1:
        st.subheader("Investment Query and Research")
        st.write("Agent: Please provide details from your trading platform: stock symbols (e.g., AAPL, WEBSOL), buy prices, quantities, purchase dates, and platform (e.g., Zerodha).")

        col1, col2 = st.columns(2)
        with col1:
            symbol = st.text_input("Stock Symbol:", key="sym")
            buy_price = st.number_input("Buy Price:", min_value=0.0, key="price")
            quantity = st.number_input("Quantity:", min_value=1, key="qty")
        with col2:
            purchase_date = st.date_input("Purchase Date:", key="date")
            platform = st.text_input("Platform:", key="plat")

        if st.button("Add Investment"):
            if symbol and buy_price > 0 and quantity > 0:
                c = conn.cursor()
                c.execute("INSERT INTO investments VALUES (?, ?, ?, ?, ?, ?)",
                          (symbol.upper(), buy_price, quantity, str(purchase_date), platform, st.session_state.email))
                conn.commit()
                st.success(f"Added {symbol.upper()}!")
                st.rerun()
            else:
                st.error("Fill all fields.")

        # Load from DB
        c = conn.cursor()
        db_investments = c.execute("SELECT symbol, buy_price, quantity, purchase_date, platform FROM investments WHERE email=?", (st.session_state.email,)).fetchall()
        st.session_state.investments = [{'symbol': row[0], 'buy_price': row[1], 'quantity': row[2], 'purchase_date': row[3], 'platform': row[4]} for row in db_investments]

        if st.session_state.investments:
            df = calculate_profit_loss(st.session_state.investments)

            # SAFE FORMATTING
            def safe_format(val, fmt):
                try:
                    if pd.isna(val) or val in ['N/A', 'Invalid', 'No Data', 'Error']:
                        return str(val)
                    return fmt.format(float(val))
                except:
                    return str(val)

            display_df = df.copy()
            for col, fmt in [
                ('current_price', '${:.2f}'),
                ('profit_loss_abs', '${:.2f}'),
                ('profit_loss_pct', '{:.2f}%'),
                ('breakeven', '${:.2f}')
            ]:
                if col in display_df.columns:
                    display_df[col] = display_df[col].apply(lambda x: safe_format(x, fmt))

            st.dataframe(display_df, use_container_width=True)

            for inv in st.session_state.investments:
                with st.expander(f"Chart & Forecast: {inv['symbol']}"):
                    data = fetch_stock_data(inv['symbol'])
                    if not data['history'].empty:
                        st.line_chart(data['history']['Close'].tail(60), use_container_width=True)
                        forecast = forecast_with_prophet(data['history'])
                        if isinstance(forecast, pd.DataFrame):
                            st.write("30-Day Forecast:")
                            st.line_chart(forecast.set_index('ds')['yhat'])
                        st.write(short_term_prediction(data['history']))
                    else:
                        st.write("No historical data.")
        else:
            st.info("No investments yet. Add one above!")

    with tab2:
        st.subheader("Notification Setup")
        if st.session_state.investments:
            symbol = st.selectbox("Select Stock:", [inv['symbol'] for inv in st.session_state.investments])
            alert_type = st.selectbox("Alert Type:", ['Target Price', 'Profit %', 'Drop %'])
            threshold = st.number_input("Threshold (e.g., 50 for price, 20 for %):", min_value=0.0)
            if st.button("Set Alert"):
                db_type = 'price' if alert_type == 'Target Price' else 'profit_pct' if alert_type == 'Profit %' else 'drop_pct'
                c = conn.cursor()
                c.execute("INSERT INTO alerts VALUES (?, ?, ?, ?)",
                          (symbol, db_type, threshold, st.session_state.email))
                conn.commit()
                st.success(f"Alert set: {alert_type} = {threshold}")
                st.rerun()

            alerts = c.execute("SELECT symbol, alert_type, threshold FROM alerts WHERE email=?", (st.session_state.email,)).fetchall()
            if alerts:
                st.write("Active Alerts:")
                alert_df = pd.DataFrame(alerts, columns=['Stock', 'Type', 'Threshold'])
                alert_df['Type'] = alert_df['Type'].map({'price': 'Target Price', 'profit_pct': 'Profit %', 'drop_pct': 'Drop %'})
                st.table(alert_df)
            else:
                st.info("No alerts set.")
        else:
            st.write("Add investments first.")

    with tab3:
        st.subheader("AI Chat Bot (Gemini 1.5 Flash - FREE)")
        context = ", ".join([f"{inv['symbol']} @ ₹{inv['buy_price']} × {inv['quantity']}" for inv in st.session_state.investments])
        user_query = st.chat_input("Ask anything (e.g., 'Buy TCS.NS now?')")
        if user_query:
            with st.chat_message("user"):
                st.write(user_query)
            with st.chat_message("assistant"):
                with st.spinner("Gemini thinking..."):
                    response = gemini_chat(user_query, context)
                st.write(response)
