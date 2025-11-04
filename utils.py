# utils.py - FIXED FOR .NS STOCKS
import yfinance as yf
import pandas as pd
from prophet import Prophet
import sqlite3
import streamlit as st
import smtplib
from email.mime.text import MIMEText
import hashlib

# DB Setup
def setup_db():
    conn = sqlite3.connect('investments.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS investments
                 (symbol TEXT, buy_price REAL, quantity INTEGER, purchase_date TEXT, platform TEXT, email TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS alerts
                 (symbol TEXT, alert_type TEXT, threshold REAL, email TEXT)''')
    conn.commit()
    return conn

# Fetch stock data - FIXED FOR .NS
def fetch_stock_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(period="60d")
        if history.empty:
            return {'history': pd.DataFrame(), 'info': {}}
        info = ticker.info
        return {'history': history, 'info': info}
    except:
        return {'history': pd.DataFrame(), 'info': {}}

# Calculate P&L
def calculate_profit_loss(investments):
    data = []
    for inv in investments:
        stock_data = fetch_stock_data(inv['symbol'])
        current = stock_data['info'].get('currentPrice') or stock_data['info'].get('regularMarketPrice')
        if not current or pd.isna(current):
            current = 'N/A'
            profit_abs = profit_pct = breakeven = 'N/A'
        else:
            cost = inv['buy_price'] * inv['quantity']
            value = current * inv['quantity']
            profit_abs = value - cost
            profit_pct = (profit_abs / cost) * 100 if cost > 0 else 0
            breakeven = inv['buy_price']
        data.append({
            'symbol': inv['symbol'],
            'current_price': current,
            'profit_loss_abs': profit_abs,
            'profit_loss_pct': profit_pct,
            'breakeven': breakeven
        })
    return pd.DataFrame(data)

# Forecast
def forecast_with_prophet(history):
    if history.empty or len(history) < 30:
        return pd.DataFrame()
    df = history[['Close']].reset_index().rename(columns={'Date': 'ds', 'Close': 'y'})
    m = Prophet(daily_seasonality=True)
    m.fit(df)
    future = m.make_future_dataframe(periods=30)
    forecast = m.predict(future)
    return forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']]

# Short term
def short_term_prediction(history):
    if history.empty:
        return "No data."
    recent = history['Close'].tail(5)
    trend = "up" if recent.iloc[-1] > recent.iloc[0] else "down"
    return f"Next day: likely {trend} (based on 5-day trend)."

# Check alerts
def check_alerts(conn, sender_email, sender_password):
    if not sender_email or not sender_password:
        return
    c = conn.cursor()
    alerts = c.execute("SELECT * FROM alerts").fetchall()
    for alert in alerts:
        symbol, alert_type, threshold, email = alert
        stock_data = fetch_stock_data(symbol)
        current = stock_data['info'].get('currentPrice') or stock_data['info'].get('regularMarketPrice')
        if not current:
            continue
        c.execute("SELECT buy_price, quantity FROM investments WHERE symbol=? AND email=?", (symbol, email))
        inv = c.fetchone()
        if not inv:
            continue
        buy_price, quantity = inv
        cost = buy_price * quantity
        value = current * quantity
        profit_abs = value - cost
        profit_pct = (profit_abs / cost) * 100

        trigger = False
        msg = ""
        if alert_type == 'price' and current >= threshold:
            trigger = True
            msg = f"{symbol} hit target ₹{threshold}! Current: ₹{current}"
        elif alert_type == 'profit_pct' and profit_pct >= threshold:
            trigger = True
            msg = f"{symbol} profit {profit_pct:.1f}% ≥ {threshold}%!"
        elif alert_type == 'drop_pct' and profit_pct <= -threshold:
            trigger = True
            msg = f"{symbol} dropped {abs(profit_pct):.1f}% ≥ {threshold}%!"

        if trigger:
            send_email(email, sender_email, sender_password, "Stock Alert", msg)
            c.execute("DELETE FROM alerts WHERE symbol=? AND alert_type=? AND email=?", (symbol, alert_type, email))
            conn.commit()

# Send email
def send_email(to_email, sender_email, sender_password, subject, body):
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = to_email
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
    except:
        pass
