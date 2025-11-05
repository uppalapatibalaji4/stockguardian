import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, time as dt_time
from prophet import Prophet
import plotly.express as px
import matplotlib.pyplot as plt
import mplfinance as mpf
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from twilio.rest import Client

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
# 2. EMAIL ALERT (REAL PRICE)
# ========================================
def send_email_alert(ticker, current_price, alert_type):
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
        body = f"{ticker} {alert_type} at ₹{current_price:.2f} on {datetime.now().strftime('%Y-%m-%d %H:%M')}"
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
# 3. WHATSAPP ALERT
# ========================================
def send_whatsapp_alert(ticker, current_price, alert_type):
    try:
        account_sid = st.secrets.get("TWILIO_SID", "")
        auth_token = st.secrets.get("TWILIO_TOKEN", "")
        from_number = st.secrets.get("TWILIO_FROM", "")
        to_number = st.session_state.get("whatsapp_number", "")
        if not all([account_sid, auth_token, from_number, to_number]):
            return False

        client = Client(account_sid, auth_token)
        message = client.messages.create(
            body=f"{ticker} {alert_type} at ₹{current_price:.2f}",
            from_=f"whatsapp:{from_number}",
            to=f"whatsapp:{to_number}"
        )
        return True
    except Exception as e:
        st.error(f"WhatsApp failed: {e}")
        return False

# ========================================
# 4. LIVE DATA (UPSTOX STYLE)
# ========================================
def get_live_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="1d")

        if hist.empty:
            return None, "No data"

        current_price = info.get('regularMarketPrice') or hist['Close'].iloc[-1]
        open_price = info.get('regularMarketOpen', hist['Open'].iloc[0])
        high_price = info.get('regularMarketDayHigh', hist['High'].max())
        low_price = info.get('regularMarketDayLow', hist['Low'].min())
        volume = info.get('regularMarketVolume', hist['Volume'].sum())
        prev_close = info.get('regularMarketPreviousClose', hist['Close'].iloc[0])

        now = datetime.now().time()
        market_open = dt_time(9, 15)
        market_close = dt_time(15, 30)
        is_open = market_open <= now <= market_close

        return {
            'current': current_price,
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'volume': volume,
            'prev_close': prev_close,
            'change_pct': ((current_price - prev_close) / prev_close) * 100,
            'market_open': is_open,
            'hist': hist
        }, None
    except Exception as e:
        return None, "Invalid ticker or market closed"

# ========================================
# 5. P&L
# ========================================
def get_pnl(ticker, buy_price):
    data, error = get_live_data(ticker)
    if error:
        return None, error
    current = data['current']
    pnl_pct = ((current - buy_price) / buy_price) * 100
    return current, pnl_pct

# ========================================
# 6. SENTIMENT
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
# 7. CANDLESTICK CHART
# ========================================
def draw_trading_chart(ticker):
    try:
        hist = yf.download(ticker, period='5d', interval='5m', progress=False)
        if hist.empty or len(hist) < 10:
            fig, ax = plt.subplots()
            ax.text(0.5, 0.5, 'No trading data', ha='center')
            ax.axis('off')
            return fig

        mpf.plot(hist, type='candle', style='charles', volume=True,
                 title=f"{ticker} Live Chart", figsize=(10, 6), returnfig=True)
        return plt.gcf()
    except:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, 'Chart unavailable', ha='center')
        ax.axis('off')
        return fig

# ========================================
# 8. TEST ALERT
# ========================================
def test_alert(ticker):
    data, error = get_live_data(ticker)
    if error:
        st.error(error)
        return
    price = data['current']
    send_email_alert(ticker, price, "TEST")
    send_whatsapp_alert(ticker, price, "TEST")
