import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from prophet import Prophet
from transformers import pipeline
import plotly.express as px
import matplotlib.pyplot as plt

# Load investments
@st.cache_data(ttl=300)
def load_investments():
    try:
        return pd.read_csv('investments.csv')
    except:
        return pd.DataFrame(columns=['ticker', 'buy_price', 'qty', 'date', 'platform'])

def save_investments(df):
    df.to_csv('investments.csv', index=False)

# Email setup & send
def setup_email():
    with st.form("email_setup"):
        user_email = st.text_input("Enter your email for alerts:")
        sender_email = st.text_input("Sender Gmail (SMTP):")
        app_password = st.text_input("Gmail App Password:", type="password")
        submitted = st.form_submit_button("Save Setup")
        if submitted:
            st.session_state.user_email = user_email
            st.secrets["GMAIL_USER"] = sender_email  # Save to secrets
            st.secrets["GMAIL_APP_PASSWORD"] = app_password
            st.success("Setup saved! Alerts enabled.")
            st.rerun()

def send_alert_email(ticker, price, alert_type):
    try:
        sender = st.secrets["GMAIL_USER"]
        password = st.secrets["GMAIL_APP_PASSWORD"]
        user_email = st.session_state.get("user_email", "")
        if not user_email:
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
    except:
        return False

# Dashboard metrics & chart
def get_pnl(ticker, buy_price, qty):
    try:
        data = yf.download(ticker, period='1d')
        current_price = data['Close'].iloc[-1]
        pnl = (current_price - buy_price) * qty
        pnl_pct = (pnl / (buy_price * qty)) * 100
        return current_price, pnl_pct
    except:
        return buy_price, 0

def get_sentiment_advice(ticker):
    sentiment_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert")
    try:
        news = yf.Ticker(ticker).news[:3]
        scores = [sentiment_pipeline(n['title'])[0] for n in news]
        avg_score = sum(s['score'] for s in scores if s['label'] == 'positive') / len(scores)
        if avg_score > 0.5:
            return "Positive", "Buy"
        elif avg_score < -0.5:
            return "Negative", "Sell"
        else:
            return "Neutral", "Hold"
    except:
        return "Neutral", "Hold"

def draw_forecast_chart(ticker):
    try:
        data = yf.download(ticker, period='1y')
        data = data.reset_index()
        data['ds'] = data['Date']
        data['y'] = data['Close']
        m = Prophet()
        m.fit(data[['ds', 'y']])
        future = m.make_future_dataframe(periods=30)
        forecast = m.predict(future)
        fig = px.line(forecast.tail(30), x='ds', y='yhat', title=f"{ticker} 30-Day Forecast")
        return fig
    except:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, 'No historical data.', ha='center')
        plt.title(f"Chart & Forecast: {ticker}")
        return fig

# Chat bot responses (simple AI)
def chat_bot_response(query, investments):
    if "tcs" in query.lower() or "tcs.ns" in query.lower():
        current, pct = get_pnl('TCS.NS', investments['buy_price'].iloc[0] if not investments.empty else 4000, 1)
        sentiment, advice = get_sentiment_advice('TCS.NS')
        return f"TCS.NS is at ₹{current:.2f} (Profit {pct:+.1f}%). Sentiment: {sentiment}. Advice: {advice}."
    elif "bye" in query.lower():
        return "Bye! Check back for updates."
    else:
        return "Ask about your stocks (e.g., 'How's TCS.NS?')."
