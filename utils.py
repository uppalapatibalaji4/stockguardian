import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, time as dt_time
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from twilio.rest import Client
import time

# ========================================
# 1. INVESTMENTS
# ========================================
@st.cache_data(ttl=3600)  # Cache 1 hour
def load_investments():
    try:
        return pd.read_csv('investments.csv')
    except FileNotFoundError:
        return pd.DataFrame(columns=['ticker', 'buy_price', 'qty', 'date', 'platform'])

def save_investments(df):
    df.to_csv('investments.csv', index=False)

# ========================================
# 2. LIVE DATA (SAFE + RATE LIMIT PROOF)
# ========================================
@st.cache_data(ttl=60)  # Update every 60 sec
def get_live_data(ticker):
    try:
        # Delay to avoid rate limit
        time.sleep(1)
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="1d")

        if hist.empty:
            return None, "No data (market closed or invalid ticker)"

        current = info.get('regularMarketPrice') or hist['Close'].iloc[-1]
        open_p = info.get('regularMarketOpen') or hist['Open'].iloc[0]
        high = info.get('regularMarketDayHigh') or hist['High'].max()
        low = info.get('regularMarketDayLow') or hist['Low'].min()
        volume = info.get('regularMarketVolume') or int(hist['Volume'].sum())
        prev_close = info.get('regularMarketPreviousClose') or hist['Close'].iloc[-1]

        now = datetime.now().time()
        is_open = dt_time(9, 15) <= now <= dt_time(15, 30)

        return {
            'current': round(current, 2),
            'open': round(open_p, 2),
            'high': round(high, 2),
            'low': round(low, 2),
            'volume': volume,
            'prev_close': round(prev_close, 2),
            'change_pct': round(((current - prev_close) / prev_close) * 100, 2) if prev_close else 0,
            'market_open': is_open
        }, None
    except Exception as e:
        return None, f"Error: {str(e)[:50]}"

# ========================================
# 3. P&L
# ========================================
def get_pnl(ticker, buy_price):
    data, error = get_live_data(ticker)
    if error:
        return None, error
    current = data['current']
    pnl_pct = ((current - buy_price) / buy_price) * 100
    return current, round(pnl_pct, 2)

# ========================================
# 4. SENTIMENT
# ========================================
@st.cache_resource
def get_sentiment_analyzer():
    return SentimentIntensityAnalyzer()

def get_sentiment_advice(ticker):
    try:
        news = yf.Ticker(ticker).news[:3]
        analyzer = get_sentiment_analyzer()
        scores = [analyzer.polarity_scores(n['title'])['compound'] for n in news]
        avg = sum(scores) / len(scores) if scores else 0
        if avg > 0.3: return "Positive", "Buy"
        elif avg < -0.3: return "Negative", "Sell"
        else: return "Neutral", "Hold"
    except:
        return "Neutral", "Hold"

# ========================================
# 5. EMAIL ALERT
# ========================================
def send_email_alert(ticker, price, typ):
    try:
        s = st.session_state.get("sender_email")
        p = st.session_state.get("app_password")
        u = st.session_state.get("user_email")
        if not all([s, p, u]): return False
        msg = MIMEMultipart()
        msg['From'] = s; msg['To'] = u; msg['Subject'] = f"Alert: {ticker}"
        msg.attach(MIMEText(f"{ticker} {typ} at ₹{price}\n{datetime.now().strftime('%Y-%m-%d %H:%M')}", 'plain'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls(); server.login(s, p)
        server.sendmail(s, u, msg.as_string()); server.quit()
        return True
    except: return False

# ========================================
# 6. WHATSAPP ALERT
# ========================================
def send_whatsapp_alert(ticker, price, typ):
    try:
        sid = st.secrets.get("TWILIO_SID")
        token = st.secrets.get("TWILIO_TOKEN")
        fr = st.secrets.get("TWILIO_FROM")
        to = st.session_state.get("whatsapp_number")
        if not all([sid, token, fr, to]): return False
        Client(sid, token).messages.create(
            body=f"{ticker} {typ} at ₹{price}",
            from_=f"whatsapp:{fr}", to=f"whatsapp:{to}"
        )
        return True
    except: return False

# ========================================
# 7. TEST ALERT
# ========================================
def test_alert(ticker):
    data, err = get_live_data(ticker)
    if err:
        st.error(err)
        return
    p = data['current']
    e = send_email_alert(ticker, p, "TEST")
    w = send_whatsapp_alert(ticker, p, "TEST")
    st.success(f"Email: {'Sent' if e else 'Failed'} | WhatsApp: {'Sent' if w else 'Failed'}")
