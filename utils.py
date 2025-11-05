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
# 2. EMAIL
# ========================================
def send_alert_email(ticker, price, alert_type):
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
        body = f"{ticker} {alert_type} at ₹{price:.2f}"
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, user_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        st.error(f"Email failed: {e}")
        return False

# ========================================
# 3. P&L
# ========================================
def get_pnl(ticker, buy_price, qty):
    try:
        data = yf.download(ticker, period='1d', progress=False)
        current_price = data['Close'].iloc[-1]
        pnl_pct = ((current_price - buy_price) / buy_price) * 100
        return current_price, pnl_pct
    except:
        return buy_price, 0.0

# ========================================
# 4. SENTIMENT (VADER - NO TORCH)
# ========================================
@st.cache_resource
def get_sentiment_analyzer():
    return SentimentIntensityAnalyzer()

def get_sentiment_advice(ticker):
    analyzer = get_sentiment_analyzer()
    try:
        news = yf.Ticker(ticker).news[:3]
        scores = []
        for item in news:
            score = analyzer.polarity_scores(item['title'])['compound']
            scores.append(score)
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
# 5. FORECAST
# ========================================
def draw_forecast_chart(ticker):
    try:
        data = yf.download(ticker, period='1y', progress=False)
        if data.empty or len(data) < 100:
            raise ValueError("Not enough data")
        data = data.reset_index()
        data['ds'] = data['Date']
        data['y'] = data['Close']
        m = Prophet()
        m.fit(data[['ds', 'y']])
        future = m.make_future_dataframe(periods=30)
        forecast = m.predict(future)
        fig = px.line(forecast.tail(60), x='ds', y='yhat', title=f"{ticker} 30-Day Forecast")
        fig.add_scatter(x=data['ds'], y=data['y'], mode='lines', name='Actual')
        return fig
    except:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, 'No historical data.', ha='center', va='center')
        ax.set_title(f"Chart & Forecast: {ticker}")
        ax.axis('off')
        return fig

# ========================================
# 6. CHAT BOT
# ========================================
def chat_bot_response(query, investments):
    query = query.lower()
    if "bye" in query:
        return "Bye! Stay profitable"
    if "tcs" in query or "tcs.ns" in query:
        current, pct = get_pnl("TCS.NS", 4000, 1)
        sentiment, advice = get_sentiment_advice("TCS.NS")
        return f"TCS.NS: ₹{current:.2f} | Profit: {pct:+.1f}% | Sentiment: {sentiment} | Advice: {advice}"
    if "forecast" in query:
        return "Check the Dashboard tab for 30-day forecast!"
    return "Try: 'How is TCS.NS?' or 'Bye'"
