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
import plotly.express as px

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
        body = f"{ticker} {alert_type} at ₹{current_price:.2f}\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
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
def send_whatsapp_alert(ticker, current_price, alert_type):
    try:
        sid = st.secrets.get("TWILIO_SID", "")
        token = st.secrets.get("TWILIO_TOKEN", "")
        from_num = st.secrets.get("TWILIO_FROM", "")
        to_num = st.session_state.get("whatsapp_number", "")
        if not all([sid, token, from_num, to_num]):
            return False

        client = Client(sid, token)
        client.messages.create(
            body=f"{ticker} {alert_type} at ₹{current_price:.2f}",
            from_=f"whatsapp:{from_num}",
            to=f"whatsapp:{to_num}"
        )
        return True
    except:
        return False

# ========================================
# 4. LIVE DATA (FIXED TYPES + CACHE)
# ========================================
@st.cache_data(ttl=120)  # 2 min cache to avoid rate limit
def get_live_data(ticker):
    try:
        time.sleep(0.5)  # Small delay
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="1d")

        if hist.empty:
            return None, "No data (market closed)"

        # Force float
        current = float(info.get('regularMarketPrice') or hist['Close'].iloc[-1])
        open_p = float(info.get('regularMarketOpen') or hist['Open'].iloc[0])
        high = float(info.get('regularMarketDayHigh') or hist['High'].max())
        low = float(info.get('regularMarketDayLow') or hist['Low'].min())
        volume = int(info.get('regularMarketVolume') or hist['Volume'].sum())
        prev_close = float(info.get('regularMarketPreviousClose') or hist['Close'].iloc[-1])

        now = datetime.now().time()
        is_open = dt_time(9, 15) <= now <= dt_time(15, 30)

        return {
            'current': current,
            'open': open_p,
            'high': high,
            'low': low,
            'volume': volume,
            'prev_close': prev_close,
            'change_pct': ((current - prev_close) / prev_close) * 100,
            'market_open': is_open,
            'hist': hist
        }, None
    except Exception as e:
        return None, f"Error: {str(e)[:50]}"

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
    try:
        news = yf.Ticker(ticker).news[:3]
        analyzer = get_sentiment_analyzer()
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
# 7. SIMPLE LINE CHART (NO ERROR)
# ========================================
def draw_trading_chart(ticker):
    try:
        hist = yf.download(ticker, period='1mo', progress=False)
        if hist.empty:
            fig = px.line(title=f"Chart & Forecast: {ticker}", text="No data")
            return fig

        hist = hist.reset_index()
        fig = px.line(hist, x='Date', y='Close', title=f"{ticker} 1-Month Price")
        fig.add_scatter(x=hist['Date'], y=hist['High'], mode='lines', name='High', line=dict(color='green'))
        fig.add_scatter(x=hist['Date'], y=hist['Low'], mode='lines', name='Low', line=dict(color='red'))
        return fig
    except:
        fig = px.line(title=f"Chart & Forecast: {ticker}", text="No historical data.")
        return fig

# ========================================
# 8. CHAT BOT
# ========================================
def chat_bot_response(query, investments):
    if investments.empty:
        return "Add a stock first!"
    ticker = investments.iloc[0]['ticker']
    data, error = get_live_data(ticker)
    if error:
        return error
    current = data['current']
    sentiment, advice = get_sentiment_advice(ticker)
    return f"{ticker} current price: ₹{current:.2f}\nHigh: ₹{data['high']:.2f} | Low: ₹{data['low']:.2f} | Volume: {data['volume']:,}\nChange: {data['change_pct']:+.2f}%\nSentiment: {sentiment} | Advice: {advice}"

# ========================================
# 9. TEST ALERT
# ========================================
def test_alert(ticker):
    data, error = get_live_data(ticker)
    if error:
        st.error(error)
        return
    price = data['current']
    email_sent = send_email_alert(ticker, price, "TEST")
    wa_sent = send_whatsapp_alert(ticker, price, "TEST")
    st.success(f"Email: {'Sent' if email_sent else 'Failed'} | WhatsApp: {'Sent' if wa_sent else 'Failed'}")
