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
# 2. EMAIL ALERT (REAL LIVE PRICE)
# ========================================
def send_email_alert(ticker, current_price, alert_type):
    try:
        sender = st.session_state.get("sender_email", "")
        password = st.session_state.get("app_password", "")
        user_email = st.session_state.get("user_email", "")
        if not all([sender, password, user_email]):
            st.warning("Setup Gmail first!")
            return False

        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = user_email
        msg['Subject'] = f"StockGuardian Alert: {ticker}"
        body = f"{ticker} {alert_type} at ₹{current_price:.2f}\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M')}\nCheck app!"
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, user_email, msg.as_string())
        server.quit()
        st.success(f"Email sent for {ticker}!")
        return True
    except Exception as e:
        st.error(f"Email failed: {e}")
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
            st.warning("Setup WhatsApp first!")
            return False

        client = Client(sid, token)
        client.messages.create(
            body=f"🚨 StockGuardian: {ticker} {alert_type} at ₹{current_price:.2f}",
            from_=f"whatsapp:{from_num}",
            to=f"whatsapp:{to_num}"
        )
        st.success(f"WhatsApp sent for {ticker}!")
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
            return None, "No data available"

        current_price = info.get('regularMarketPrice', hist['Close'].iloc[-1])
        open_price = info.get('regularMarketOpen', hist['Open'].iloc[0])
        high_price = info.get('regularMarketDayHigh', hist['High'].max())
        low_price = info.get('regularMarketDayLow', hist['Low'].min())
        volume = info.get('regularMarketVolume', hist['Volume'].sum())
        prev_close = info.get('regularMarketPreviousClose', hist['Close'].iloc[-1])

        # Market status (IST)
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
            'change_pct': ((current_price - prev_close) / prev_close) * 100 if prev_close else 0,
            'market_open': is_open,
            'hist': hist
        }, None
    except Exception as e:
        return None, f"Error: {e}"

# ========================================
# 5. P&L CALC
# ========================================
def get_pnl(ticker, buy_price):
    data, error = get_live_data(ticker)
    if error:
        return None, error
    current = data['current']
    pnl_pct = ((current - buy_price) / buy_price) * 100
    return current, pnl_pct

# ========================================
# 6. SENTIMENT & ADVICE
# ========================================
@st.cache_resource
def get_sentiment_analyzer():
    return SentimentIntensityAnalyzer()

def get_sentiment_advice(ticker):
    analyzer = get_sentiment_analyzer()
    try:
        stock = yf.Ticker(ticker)
        news = stock.news[:3]
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
# 7. FULL TRADING CHART (CANDLESTICK + VOLUME)
# ========================================
def draw_trading_chart(ticker):
    try:
        hist = yf.download(ticker, period='5d', interval='5m', progress=False)
        if hist.empty or len(hist) < 10:
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.text(0.5, 0.5, 'No historical data. Try adding more time.', ha='center', va='center', fontsize=14)
            ax.set_title(f"Chart & Forecast: {ticker}")
            ax.axis('off')
            return fig

        # Candlestick chart with volume
        mpf.plot(hist, type='candle', style='charles', volume=True, figsize=(12, 8),
                 title=f"{ticker} Live Trading Chart", returnfig=True)
        return plt.gcf()
    except Exception as e:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, f'Chart error: {e}', ha='center', va='center', fontsize=12)
        ax.set_title(f"Chart & Forecast: {ticker}")
        ax.axis('off')
        return fig

# ========================================
# 8. CHAT BOT RESPONSE
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
    return f"{ticker} is at ₹{current:.2f} (Change: {data['change_pct']:+.2f}%). Sentiment: {sentiment}. Advice: {advice}."

# ========================================
# 9. TEST ALERT (REAL LIVE PRICE)
# ========================================
def test_alert(ticker):
    data, error = get_live_data(ticker)
    if error:
        st.error(error)
        return
    price = data['current']
    email_sent = send_email_alert(ticker, price, "TEST - Live Price")
    wa_sent = send_whatsapp_alert(ticker, price, "TEST - Live Price")
    st.success(f"Email: {'Sent' if email_sent else 'Failed'} | WhatsApp: {'Sent' if wa_sent else 'Failed'}")
