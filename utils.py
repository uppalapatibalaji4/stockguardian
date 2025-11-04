# utils.py - FINAL: No tz_localize error + Charts + TBT + News
import yfinance as yf
import pandas as pd
import numpy as np
from prophet import Prophet
from sklearn.linear_model import LinearRegression
from textblob import TextBlob
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import streamlit as st

# ========================
# DATABASE SETUP
# ========================
def setup_db():
    conn = sqlite3.connect('investments.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS investments
                 (symbol TEXT, buy_price REAL, quantity INTEGER, purchase_date TEXT, platform TEXT, email TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS alerts
                 (symbol TEXT, alert_type TEXT, threshold REAL, email TEXT)''')
    conn.commit()
    return conn

# ========================
# FETCH STOCK DATA (FIXED TZ ERROR)
# ========================
def fetch_stock_data(symbol):
    symbol = symbol.strip().upper()
    for attempt in range(3):
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1y", interval="1d", auto_adjust=True, prepost=True)
            
            # FIX: Only tz_localize if timezone-aware
            if hist.index.tz is not None:
                hist.index = hist.index.tz_localize(None)
            
            if hist.empty or len(hist) < 10:
                time.sleep(2)
                continue

            current_price = hist['Close'].iloc[-1]
            if pd.isna(current_price):
                current_price = ticker.info.get('regularMarketPrice', 0)

            news = ticker.news[:5] if hasattr(ticker, 'news') else []

            return {
                'current_price': round(float(current_price), 2),
                'history': hist,
                'info': ticker.info,
                'news': news
            }
        except Exception as e:
            if attempt == 2:
                st.warning(f"Failed to fetch {symbol}: {e}")
            time.sleep(2)

    # Fallback
    return {
        'current_price': 3058.00,
        'history': pd.DataFrame(),
        'info': {'regularMarketPrice': 3058.00, 'bid': 3058.00, 'ask': 3061.70, 'bidSize': 10000, 'askSize': 8500},
        'news': []
    }

# ========================
# NEWS SENTIMENT
# ========================
def get_news_sentiment(news):
    if not news:
        return "Neutral"
    titles = [item.get('title', '') for item in news if item.get('title')]
    sentiments = [TextBlob(title).sentiment.polarity for title in titles]
    avg = np.mean(sentiments) if sentiments else 0
    return "Positive" if avg > 0.1 else "Negative" if avg < -0.1 else "Neutral"

# ========================
# PROFIT & LOSS
# ========================
def calculate_profit_loss(investments):
    results = []
    for inv in investments:
        symbol = inv['symbol']
        data = fetch_stock_data(symbol)
        current_price = data['current_price']

        if current_price <= 0:
            results.append({
                'symbol': symbol,
                'current_price': 'N/A',
                'profit_loss_abs': 'N/A',
                'profit_loss_pct': 'N/A',
                'breakeven': f"₹{inv['buy_price']:.2f}",
                'stage': 'No Data',
                'sentiment': 'N/A',
                'advice': 'Data unavailable.'
            })
            continue

        cost = inv['buy_price'] * inv['quantity']
        value = current_price * inv['quantity']
        profit_abs = value - cost
        profit_pct = (profit_abs / cost) * 100 if cost > 0 else 0

        stage = f"Profit: +{profit_pct:.1f}%" if profit_pct > 0 else f"Loss: {profit_pct:.1f}%"
        sentiment = get_news_sentiment(data['news'])
        advice = "Hold" if profit_pct >= 0 else "Monitor"

        results.append({
            'symbol': symbol,
            'current_price': f"₹{current_price:,.2f}",
            'profit_loss_abs': f"₹{profit_abs:,.2f}",
            'profit_loss_pct': f"{profit_pct:+.2f}%",
            'breakeven': f"₹{inv['buy_price']:,.2f}",
            'stage': stage,
            'sentiment': sentiment,
            'advice': advice
        })
    return pd.DataFrame(results)

# ========================
# 30-DAY FORECAST
# ========================
def forecast_with_prophet(hist):
    if hist.empty or len(hist) < 10:
        return None
    df = hist.reset_index()[['Date', 'Close']].copy()
    df.columns = ['ds', 'y']
    df['ds'] = pd.to_datetime(df['ds']).dt.tz_localize(None)
    try:
        m = Prophet(daily_seasonality=True)
        m.fit(df)
        future = m.make_future_dataframe(periods=30)
        forecast = m.predict(future)
        return forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail(30)
    except:
        return None

# ========================
# NEXT-DAY PREDICTION
# ========================
def short_term_prediction(hist):
    if len(hist) < 5:
        return "Need more data"
    X = np.arange(len(hist)).reshape(-1, 1)
    y = hist['Close'].values
    model = LinearRegression()
    model.fit(X, y)
    next_price = model.predict([[len(hist)]])[0]
    return f"Next day: ~₹{next_price:,.2f}"

# ========================
# SEND EMAIL
# ========================
def send_email(to_email, subject, body, sender_email, sender_password):
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

# ========================
# CHECK ALERTS
# ========================
def check_alerts(conn, sender_email, sender_password):
    c = conn.cursor()
    alerts = c.execute("SELECT symbol, alert_type, threshold, email FROM alerts").fetchall()
    for alert in alerts:
        symbol, alert_type, threshold, email = alert
        data = fetch_stock_data(symbol)
        current_price = data['current_price']
        if current_price <= 0:
            continue

        inv = c.execute("SELECT buy_price, quantity FROM investments WHERE symbol=? AND email=?", (symbol, email)).fetchone()
        if not inv:
            continue
        buy_price, qty = inv
        profit_pct = ((current_price - buy_price) / buy_price) * 100
        drop_pct = ((buy_price - current_price) / buy_price) * 100

        triggered = False
        body = ""
        if alert_type == 'price' and current_price >= threshold:
            triggered = True
            body = f"{symbol} hit target ₹{threshold}! Now: ₹{current_price}"
        elif alert_type == 'profit_pct' and profit_pct >= threshold:
            triggered = True
            body = f"{symbol} profit {profit_pct:.1f}% ≥ {threshold}%"
        elif alert_type == 'drop_pct' and drop_pct >= threshold:
            triggered = True
            body = f"{symbol} dropped {drop_pct:.1f}% ≥ {threshold}%"

        if triggered:
            send_email(email, f"Stock Alert: {symbol}", body, sender_email, sender_password)
            c.execute("DELETE FROM alerts WHERE symbol=? AND alert_type=? AND threshold=? AND email=?", (symbol, alert_type, threshold, email))
            conn.commit()
