# utils.py
import streamlit as st
import os
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import timedelta
from twilio.rest import Client


# --------------------------------------------------------------
# 1. EMAIL ALERT
# --------------------------------------------------------------
def send_email(subject: str, body: str, to_email: str) -> bool:
    EMAIL_USER = os.getenv('EMAIL_USER')
    EMAIL_PASS = os.getenv('EMAIL_PASS')
    if not (EMAIL_USER and EMAIL_PASS):
        st.error("Email not configured in Secrets")
        return False

    from email.mime.text import MimeText
    import smtplib

    msg = MimeText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_USER
    msg['To'] = to_email

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()
        st.success("Email sent!")
        return True
    except Exception as e:
        st.error(f"Email failed: {e}")
        return False


# --------------------------------------------------------------
# 2. WHATSAPP ALERT
# --------------------------------------------------------------
def send_whatsapp(message: str) -> bool:
    sid = os.getenv('TWILIO_ACCOUNT_SID')
    token = os.getenv('TWILIO_AUTH_TOKEN')
    from_num = os.getenv('TWILIO_WHATSAPP_NUMBER')
    to_num = os.getenv('USER_PHONE')
    if not all([sid, token, from_num, to_num]):
        st.error("WhatsApp not configured")
        return False

    try:
        client = Client(sid, token)
        client.messages.create(body=message, from_=from_num, to=to_num)
        st.success("WhatsApp sent!")
        return True
    except Exception as e:
        st.error(f"WhatsApp failed: {e}")
        return False


# --------------------------------------------------------------
# 3. GET STOCK PRICE
# --------------------------------------------------------------
@st.cache_data(ttl=60)
def get_stock_price(symbol: str) -> float | None:
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period='1d')
        if not data.empty:
            return round(data['Close'].iloc[-1], 4)
        return None
    except:
        return None


# --------------------------------------------------------------
# 4. P&L CALCULATION
# --------------------------------------------------------------
def calculate_pnl(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    out = df.copy()
    out['current_price'] = out['symbol'].apply(get_stock_price)
    out['value'] = out['current_price'] * out['quantity']
    out['invested'] = out['buy_price'] * out['quantity']
    out['pnl'] = out['value'] - out['invested']
    out['pnl_pct'] = (out['pnl'] / out['invested']) * 100
    return out


# --------------------------------------------------------------
# 5. 30-DAY FORECAST (PURE MATH)
# --------------------------------------------------------------
@st.cache_data
def forecast_stock(symbol: str, days: int = 30):
    try:
        data = yf.download(symbol, period='3mo', progress=False)
        if data.empty or len(data) < 20:
            return None
        close = data['Close'].dropna()
        if len(close) < 20:
            return None

        x = np.arange(len(close))
        slope, intercept = np.polyfit(x, close, 1)
        future_x = np.arange(len(close), len(close) + days)
        base = slope * future_x + intercept
        noise = np.random.normal(1, 0.05, days)
        forecast = base * noise

        last_date = close.index[-1]
        dates = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=days)

        result = pd.DataFrame({'ds': dates, 'yhat': forecast})
        result['yhat_lower'] = result['yhat'] * 0.90
        result['yhat_upper'] = result['yhat'] * 1.10

        return result[['ds', 'yhat', 'yhat_lower', 'yhat_upper']]
    except:
        return None


# --------------------------------------------------------------
# 6. AI CHAT (RULE-BASED)
# --------------------------------------------------------------
def get_ai_response(user_input: str, context: str = "") -> str:
    user_input = user_input.lower().strip()

    if any(word in user_input for word in ["hi", "hello", "hey"]):
        return "Hello! I'm your stock assistant. Ask about prices, P&L, or forecasts."

    elif "price" in user_input:
        return "Check the **Dashboard** for live prices."

    elif "forecast" in user_input:
        return "See the **30-day forecast** in the Dashboard tab."

    elif "profit" in user_input or "loss" in user_input:
        return "Your total P&L and return % are shown in the **Dashboard**."

    elif "alert" in user_input:
        return "Set alerts in the **Alerts** tab. You'll get Email + WhatsApp!"

    else:
        return "I can help with:\n• Current prices\n• P&L\n• 30-day forecasts\n• Alerts\nAsk me anything!"
