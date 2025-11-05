import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from prophet import Prophet
import plotly.express as px
import matplotlib.pyplot as plt
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from twilio.rest import Client
import time

# ========================================
# 1. INVESTMENTS
# ========================================
@st.cache_data(ttl=300)
def load_investments():
    try:
        return pd.read_csv('investments.csv')
    except FileNotFoundError:
        return pd.DataFrame(columns=['ticker', 'buy_price', 'qty', 'date', 'platform'])

def save_investments(df):
    df.to_csv('investments.csv', index=False)

# ========================================
# 2. EMAIL ALERT
# ========================================
def send_email_alert(ticker, price, alert_type):
    try:
        sender = st.session_state.get("sender_email", "")
        password = st.session_state.get("app_password", "")
        user_email = st.session_state.get("user_email", "")
        if not all([sender, password, user_email]):
            return False

        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = user_email
        msg['Subject'] = f"StockGuardian Alert: {ticker}"
        body = f"{ticker} {alert_type} at ₹{price:.2f} on {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, user_email, msg.as_string())
        server.quit()
        return True
    except:
        return False

# ========================================
# 3. WHATSAPP ALERT
# ========================================
def send_whatsapp_alert(ticker, price, alert_type):
    try:
        account_sid = st.secrets.get("TWILIO_SID", "")
        auth_token = st.secrets.get("TWILIO_TOKEN", "")
        from_number = st.secrets.get("TWILIO_FROM", "")
        to_number = st.session_state.get("whatsapp_number", "")
        if not all([account_sid, auth_token, from_number, to_number]):
            return False

        client = Client(account_sid, auth_token)
        message = client.messages.create(
            body=f"StockGuardian Alert: {ticker} {alert_type} at ₹{price:.2f}",
            from_=f"whatsapp:{from_number}",
            to=f"whatsapp:{to_number}"
        )
        return True
    except:
        return False

# ========================================
# 4. P&L & LIVE PRICE
# ========================================
def get_pnl(ticker, buy_price, qty):
    try:
        data = yf.download(ticker, period='2d', progress=False)
        if data.empty:
            return None, "No data"
        current_price = data['Close'].iloc[-1]
        pnl_pct = ((current_price - buy_price) / buy_price) * 100
        return current_price, pnl_pct
    except:
        return None, "Invalid ticker"

# ========================================
# 5. SENTIMENT
# ========================================
@st.cache_resource
def get_sentiment_analyzer():
    return SentimentIntensityAnalyzer()

def get_sentiment_advice(ticker):
    analyzer = get_sentiment_analyzer()
    try:
        news = yf.Ticker(ticker).news[:3]
        scores = [analyzer.polarity_scores(n['title'])['compound'] for n in news]
        avg = sum(scores) / len(scores) if scores else 0
        if avg > 0.3:
            return "Positive", "Buy"
        elif avg < -0.3:
            return "Negative", "Sell"
        else:
            return "Neutral", "Hold"
    except:
        return "Neutral", "Hold"

# ========================================
# 6. FORECAST CHART
# ========================================
def draw_forecast_chart(ticker):
    try:
        data = yf.download(ticker, period='1y', progress=False)
        if len(data) < 100:
            raise ValueError("Not enough data")
        data = data.reset_index()
        data['ds'] = data['Date']
        data['y'] = data['Close']
        m = Prophet()
        m.fit(data[['ds', 'y']])
        future = m.make_future_dataframe(periods=30)
        forecast = m.predict(future)
        fig = px.line(forecast.tail(60), x='ds', y='yhat', title=f"{ticker} 30-Day Forecast")
        fig.add_scatter(x=data['ds'], y=data['y'], mode='lines', name='Actual', line=dict(color='blue'))
        return fig
    except:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, 'No historical data.', ha='center', va='center', fontsize=14)
        ax.set_title(f"Chart: {ticker}")
        ax.axis('off')
        return fig

# ========================================
# 7. CHAT BOT
# ========================================
def chat_bot_response(query, investments):
    query = query.lower()
    if "bye" in query:
        return "Goodbye! Stay profitable"
    if investments.empty:
        return "Add a stock first!"
    ticker = investments.iloc[0]['ticker']
    current, _ = get_pnl(ticker, 0, 0)
    if current is None:
        return "Market closed or invalid ticker."
    sentiment, advice = get_sentiment_advice(ticker)
    return f"{ticker}: ₹{current:.2f} | Sentiment: {sentiment} | Advice: {advice}"
