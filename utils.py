# utils.py
import streamlit as st
import os
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from twilio.rest import Client


# --------------------------------------------------------------
# 1. Email Alert
# --------------------------------------------------------------
def send_email(subject: str, body: str, to_email: str) -> bool:
    EMAIL_USER = os.getenv('EMAIL_USER')
    EMAIL_PASS = os.getenv('EMAIL_PASS')
    if not (EMAIL_USER and EMAIL_PASS):
        st.error("Email not configured in .env")
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
# 2. WhatsApp Alert
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
# 3. Stock Price (cached)
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
        st.warning(f"Failed to fetch {symbol}")
        return None


# --------------------------------------------------------------
# 4. P&L Calculation
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
# 5. 30-Day Forecast — PURE MATH (NO ML)
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

        # Linear trend
        x = np.arange(len(close))
        slope, intercept = np.polyfit(x, close, 1)
        last_price = close.iloc[-1]

        # Generate future
        future_x = np.arange(len(close), len(close) + days)
        base_forecast = slope * future_x + intercept

        # Add ±5% noise
        noise = np.random.normal(1, 0.05, days)
        forecast = base_forecast * noise

        # Dates
        last_date = close.index[-1]
        future_dates = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=days)

        result = pd.DataFrame({
            'ds': future_dates,
            'yhat': forecast
        })
        result['yhat_lower'] = result['yhat'] * 0.90
        result['yhat_upper'] = result['yhat'] * 1.10

        return result[['ds', 'yhat', 'yhat_lower', 'yhat_upper']]

    except:
        return None


# --------------------------------------------------------------
# 6. AI Chat — RULE-BASED (NO TRANSFORMERS)
# --------------------------------------------------------------
def get_ai_response(user_input: str, context: str = "") -> str:
    user_input = user_input.lower().strip()

    # Simple keyword responses
    if any(word in user_input for word in ["hello", "hi", "hey"]):
        return "Hello! I'm your stock assistant. Ask me about your portfolio, prices, or forecasts."

    elif "price" in user_input or "worth" in user_input:
        symbols = [s for s in context.split() if s.replace(',', '').isupper()]
        if symbols:
            prices = []
            for sym in symbols[:3]:
                p = get_stock_price(sym)
                if p:
                    prices.append(f"{sym}: ${p:.2f}")
            return "Current prices:\n" + "\n".join(prices) if prices else "No price data."

    elif "forecast" in user_input or "predict" in user_input:
        return "I can show a 30-day trend in the Dashboard. Try adding a stock and checking the forecast tab!"

    elif "profit" in user_input or "loss" in user_input:
        return "Check the Dashboard for your total P&L and percentage return."

    elif "alert" in user_input:
        return "Set price, profit %, or drop % alerts in the Alerts tab. You'll get email + WhatsApp!"

    else:
        return "I can help with:\n• Current prices\n• Portfolio P&L\n• 30-day forecasts\n• Setting alerts\nAsk me anything!"
