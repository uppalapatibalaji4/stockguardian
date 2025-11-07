# utils.py
import streamlit as st
import os
import yfinance as yf
import pandas as pd
import numpy as np
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from twilio.rest import Client
from transformers import pipeline, Conversation


# --------------------------------------------------------------
# 1. Email Alert (MimeText inside function)
# --------------------------------------------------------------
def send_email(subject: str, body: str, to_email: str) -> bool:
    EMAIL_USER = os.getenv('EMAIL_USER')
    EMAIL_PASS = os.getenv('EMAIL_PASS')
    if not (EMAIL_USER and EMAIL_PASS):
        st.error("Email not configured")
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
# 2. WhatsApp
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
    except Exception as e:
        st.warning(f"Price error: {e}")
        return None


# --------------------------------------------------------------
# 4. P&L
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
# 5. 30-Day Forecast (using Exponential Smoothing)
# --------------------------------------------------------------
@st.cache_data
def forecast_stock(symbol: str, days: int = 30):
    try:
        data = yf.download(symbol, period='1y', progress=False)
        if data.empty or len(data) < 50:
            st.error(f"Not enough data for {symbol}")
            return None

        close = data['Close'].dropna()
        if len(close) < 50:
            return None

        # Use Exponential Smoothing
        model = ExponentialSmoothing(close, trend='add', seasonal=None)
        fit = model.fit()
        forecast = fit.forecast(days)

        # Create future dates
        last_date = close.index[-1]
        future_dates = pd.date_range(start=last_date + pd.Timedelta(days=1), periods=days, freq='B')

        result = pd.DataFrame({
            'ds': future_dates,
            'yhat': forecast.values
        })
        # Simple confidence: ±10%
        result['yhat_lower'] = result['yhat'] * 0.9
        result['yhat_upper'] = result['yhat'] * 1.1

        return result[['ds', 'yhat', 'yhat_lower', 'yhat_upper']]

    except Exception as e:
        st.error(f"Forecast failed: {e}")
        return None


# --------------------------------------------------------------
# 6. AI Chat
# --------------------------------------------------------------
@st.cache_resource
def _load_chat_model():
    model_name = os.getenv('HUGGINGFACE_MODEL', 'distilgpt2')
    try:
        pipe = pipeline('conversational', model=model_name)
        return Conversation(pipe)
    except Exception as e:
        st.warning(f"AI model failed: {e}")
        return None

def get_ai_response(user_input: str, context: str = "") -> str:
    model = _load_chat_model()
    if not model:
        return "AI is offline."

    full = f"{context} {user_input}"
    model.add_user_input(full)
    model = model.generate()
    model.mark_processed(model.last_exchange_id)
    return model.generated_responses[-1]
