# utils.py
import streamlit as st
import os
import yfinance as yf
import pandas as pd
from prophet import Prophet
from twilio.rest import Client
from transformers import pipeline, Conversation

# --------------------------------------------------------------
# 1. Email Alert — MimeText imported INSIDE function
# --------------------------------------------------------------
def send_email(subject: str, body: str, to_email: str) -> bool:
    EMAIL_USER = os.getenv('EMAIL_USER')
    EMAIL_PASS = os.getenv('EMAIL_PASS')
    if not (EMAIL_USER and EMAIL_PASS):
        st.error("Email not configured (check .env)")
        return False

    # Import here to avoid top-level import issues
    from email.mime.text import MimeText

    msg = MimeText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_USER
    msg['To'] = to_email

    try:
        import smtplib
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
        st.warning(f"Price error for {symbol}: {e}")
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
# 5. Forecast
# --------------------------------------------------------------
@st.cache_data
def forecast_stock(symbol: str, days: int = 30):
    try:
        data = yf.download(symbol, period='2y', progress=False)
        if data.empty:
            st.error(f"No data for {symbol}")
            return None
        df = data.reset_index()[['Date', 'Close']].rename(columns={'Date': 'ds', 'Close': 'y'})
        m = Prophet(daily_seasonality=True)
        m.fit(df)
        future = m.make_future_dataframe(periods=days)
        forecast = m.predict(future)
        return forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail(days + 1)
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
