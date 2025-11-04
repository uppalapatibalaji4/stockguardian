# utils.py: Helper functions for StockGuardian

import yfinance as yf
import pandas as pd
from datetime import datetime
from textblob import TextBlob
import hashlib
from prophet import Prophet
from sklearn.linear_model import LinearRegression
import numpy as np
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import streamlit as st

# Database setup
def setup_db():
    """Initialize SQLite DB for investments and alerts."""
    conn = sqlite3.connect('investments.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS investments
                 (symbol TEXT, buy_price REAL, quantity INTEGER, purchase_date TEXT, platform TEXT, email TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS alerts
                 (symbol TEXT, alert_type TEXT, threshold REAL, email TEXT)''')
    conn.commit()
    return conn

# Fetch stock data with fallback
def fetch_stock_data(symbol):
    """Fetch real-time/historical data using yfinance."""
    try:
        stock = yf.Ticker(symbol)
        hist = stock.history(period='1y')
        if hist.empty:
            return {'current_price': 0, 'history': pd.DataFrame(), 'volume': 0, 'news': []}
        current_price = hist['Close'].iloc[-1]
        news = stock.news[:5]  # Top 5 news
        return {
            'current_price': current_price,
            'history': hist,
            'volume': hist['Volume'].mean(),
            'news': news
        }
    except Exception as e:
        st.warning(f"Could not fetch {symbol}: {e}. Using fallback.")
        return {'current_price': 0, 'history': pd.DataFrame(), 'volume': 0, 'news': []}

# Simulate news sentiment
def get_news_sentiment(news):
    """Analyze headlines with TextBlob."""
    if not news:
        return "Neutral"
    sentiments = []
    for article in news:
        if 'title' in article:
            blob = TextBlob(article['title'])
            sentiments.append(blob.sentiment.polarity)
    if not sentiments:
        return "Neutral"
    avg = np.mean(sentiments)
    if avg > 0.1:
        return "Positive"
    elif avg < -0.1:
        return "Negative"
    return "Neutral"

# Calculate profit/loss - SAFE VERSION
def calculate_profit_loss(investments):
    """Compute P/L for each investment with error handling."""
    results = []
    for inv in investments:
        data = fetch_stock_data(inv['symbol'])
        current_price = data['current_price']
        buy_price = inv['buy_price']
        quantity = inv['quantity']

        # Handle invalid ticker
        if current_price == 0 or current_price is None:
            results.append({
                'symbol': inv['symbol'],
                'current_price': 'N/A',
                'profit_loss_abs': 'N/A',
                'profit_loss_pct': 'N/A',
                'breakeven': f"${buy_price:.2f}" if buy_price > 0 else "N/A",
                'stage': 'No Data',
                'sentiment': 'N/A',
                'advice': f"{inv['symbol']} not found or delisted."
            })
            continue

        # Handle zero or negative buy price
        if buy_price <= 0:
            results.append({
                'symbol': inv['symbol'],
                'current_price': f"${current_price:.2f}",
                'profit_loss_abs': 'N/A',
                'profit_loss_pct': 'N/A',
                'breakeven': 'Invalid',
                'stage': 'Error',
                'sentiment': get_news_sentiment(data['news']),
                'advice': 'Buy price must be > 0.'
            })
            continue

        current_value = current_price * quantity
        buy_value = buy_price * quantity
        profit_loss_abs = current_value - buy_value
        profit_loss_pct = (profit_loss_abs / buy_value) * 100
        breakeven = buy_price
        stage = f"In Profit: +{profit_loss_pct:.2f}%" if profit_loss_pct > 0 else f"At Loss: {profit_loss_pct:.2f}%"
        sentiment = get_news_sentiment(data['news'])
        advice = f"{inv['symbol']} {'bullish' if profit_loss_pct > 0 else 'bearish'} trend. Sentiment: {sentiment}."

        results.append({
            'symbol': inv['symbol'],
            'current_price': f"${current_price:.2f}",
            'profit_loss_abs': f"${profit_loss_abs:.2f}",
            'profit_loss_pct': f"{profit_loss_pct:.2f}%",
            'breakeven': f"${breakeven:.2f}",
            'stage': stage,
            'sentiment': sentiment,
            'advice': advice
        })
    return pd.DataFrame(results)

# Prophet forecast
def forecast_with_prophet(hist):
    """30-day forecast using Prophet."""
    if hist.empty or len(hist) < 10:
        return "Not enough data"
    df = hist.reset_index()[['Date', 'Close']].copy()
    df.columns = ['ds', 'y']
    df['ds'] = df['ds'].dt.tz_localize(None)
    m = Prophet(daily_seasonality=True)
    m.fit(df)
    future = m.make_future_dataframe(periods=30)
    forecast = m.predict(future)
    return forecast[['ds', 'yhat']].tail(30)

# Short-term prediction
def short_term_prediction(hist):
    """Next day prediction using Linear Regression."""
    if len(hist) < 5:
        return "Need more data"
    X = np.arange(len(hist)).reshape(-1, 1)
    y = hist['Close'].values
    model = LinearRegression()
    model.fit(X, y)
    next_day = model.predict([[len(hist)]])[0]
    return f"Next close: ${next_day:.2f}"

# Send email
def send_email(to_email, subject, body, sender_email, sender_password):
    """Send alert via Gmail SMTP."""
    if not sender_email or not sender_password:
        return
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_email, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"Email failed: {e}")

# Check alerts
def check_alerts(conn, sender_email, sender_password):
    """Background task to check and send alerts."""
    c = conn.cursor()
    alerts = c.execute("SELECT symbol, alert_type, threshold, email FROM alerts").fetchall()
    investments = c.execute("SELECT symbol, buy_price, quantity FROM investments").fetchall()
    
    for alert in alerts:
        symbol, alert_type, threshold, email = alert
        data = fetch_stock_data(symbol)
        current_price = data['current_price']
        if current_price == 0:
            continue

        inv = next((i for i in investments if i[0] == symbol), None)
        if not inv:
            continue
        buy_price = inv[1]

        profit_pct = ((current_price - buy_price) / buy_price) * 100
        drop_pct = ((buy_price - current_price) / buy_price) * 100

        triggered = False
        body = ""

        if alert_type == 'price' and current_price >= threshold:
            triggered = True
            body = f"{symbol} hit ${threshold:.2f}! Current: ${current_price:.2f}"
        elif alert_type == 'profit_pct' and profit_pct >= threshold:
            triggered = True
            body = f"{symbol} reached {threshold}% profit! Now: {profit_pct:.2f}%"
        elif alert_type == 'drop_pct' and drop_pct >= threshold:
            triggered = True
            body = f"{symbol} dropped {threshold}%! Current drop: {drop_pct:.2f}%"

        if triggered:
            send_email(email, f"StockGuardian Alert: {symbol}", body, sender_email, sender_password)
            c.execute("DELETE FROM alerts WHERE symbol=? AND alert_type=? AND threshold=?", (symbol, alert_type, threshold))
            conn.commit()
