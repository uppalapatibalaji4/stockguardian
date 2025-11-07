# utils.py
import os
import smtplib
from email.mime.text import MimeText
import yfinance as yf
import pandas as pd
from prophet import Prophet
from twilio.rest import Client
from transformers import pipeline, Conversation


# ----------------------------------------------------------------------
# 1. Email (no st calls)
# ----------------------------------------------------------------------
def send_email(subject: str, body: str, to_email: str) -> bool:
    EMAIL_USER = os.getenv('EMAIL_USER')
    EMAIL_PASS = os.getenv('EMAIL_PASS')
    if not (EMAIL_USER and EMAIL_PASS):
        return False

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
        return True
    except:
        return False


# ----------------------------------------------------------------------
# 2. WhatsApp
# ----------------------------------------------------------------------
def send_whatsapp(message: str) -> bool:
    sid = os.getenv('TWILIO_ACCOUNT_SID')
    token = os.getenv('TWILIO_AUTH_TOKEN')
    from_num = os.getenv('TWILIO_WHATSAPP_NUMBER')
    to_num = os.getenv('USER_PHONE')
    if not all([sid, token, from_num, to_num]):
        return False

    try:
        client = Client(sid, token)
        client.messages.create(body=message, from_=from_num, to=to_num)
        return True
    except:
        return False


# ----------------------------------------------------------------------
# 3. Stock Price (raw — caching done in app.py)
# ----------------------------------------------------------------------
def get_stock_price_raw(symbol: str) -> float | None:
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period='1d')
        if not data.empty:
            return round(data['Close'].iloc[-1], 4)
        return None
    except:
        return None


# ----------------------------------------------------------------------
# 4. P&L
# ----------------------------------------------------------------------
def calculate_pnl(df: pd.DataFrame, price_getter) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    out = df.copy()
    out['current_price'] = out['symbol'].apply(price_getter)
    out['value'] = out['current_price'] * out['quantity']
    out['invested'] = out['buy_price'] * out['quantity']
    out['pnl'] = out['value'] - out['invested']
    out['pnl_pct'] = (out['pnl'] / out['invested']) * 100
    return out


# ----------------------------------------------------------------------
# 5. Forecast
# ----------------------------------------------------------------------
def forecast_stock(symbol: str, days: int = 30):
    try:
        data = yf.download(symbol, period='2y', progress=False)
        if data.empty:
            return None
        df = data.reset_index()[['Date', 'Close']].rename(columns={'Date': 'ds', 'Close': 'y'})
        m = Prophet(daily_seasonality=True)
        m.fit(df)
        future = m.make_future_dataframe(periods=days)
        forecast = m.predict(future)
        return forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail(days + 1)
    except:
        return None


# ----------------------------------------------------------------------
# 6. AI Chat
# ----------------------------------------------------------------------
def load_chat_model():
    model_name = os.getenv('HUGGINGFACE_MODEL', 'distilgpt2')
    try:
        pipe = pipeline('conversational', model=model_name)
        return Conversation(pipe)
    except:
        return None


def get_ai_response(user_input: str, context: str = "") -> str:
    model = load_chat_model()
    if not model:
        return "AI is currently unavailable."

    full = f"{context} {user_input}"
    model.add_user_input(full)
    model = model.generate()
    model.mark_processed(model.last_exchange_id)
    return model.generated_responses[-1]
