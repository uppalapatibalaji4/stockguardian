import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os  # Keep this
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import plotly.express as px
from prophet import Prophet
from twilio.rest import Client
from transformers import pipeline
import base64
from fpdf import FPDF
from io import BytesIO

# === Load Secrets ===
load_dotenv()
st.session_state.setdefault("user_email", "")
st.session_state.setdefault("user_phone", "")

# === Email Alert Function ===
def send_alert_email(ticker, current_price, alert_type):
    try:
        sender_email = os.getenv("GMAIL_USER")
        sender_password = os.getenv("GMAIL_APP_PASSWORD")
        user_email = st.session_state.user_email

        if not sender_email or not sender_password or not user_email:
            st.warning("Set email in sidebar first!")
            return False

        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = user_email
        msg['Subject'] = f"StockGuardian: {ticker} {alert_type}"
        body = f"{ticker} is at ${current_price:.2f} → {alert_type}\nCheck: {st.session_state.get('app_url', 'your app')}"
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, user_email, msg.as_string())
        server.quit()
        st.success(f"Email alert sent for {ticker}!")
        return True
    except Exception as e:
        st.error(f"Email failed: {str(e)}")
        return False

# === WhatsApp Alert ===
def send_whatsapp_alert(ticker, current_price, alert_type):
    try:
        client = Client(os.getenv("TWILIO_SID"), os.getenv("TWILIO_AUTH"))
        user_phone = st.session_state.user_phone
        if not user_phone: return False
        message = client.messages.create(
            body=f"StockGuardian: {ticker} {alert_type} at ${current_price:.2f}",
            from_=os.getenv("TWILIO_WHATSAPP_FROM"),
            to=f"whatsapp:{user_phone}"
        )
        st.success("WhatsApp sent!")
        return True
    except:
        return False

# === Load/Save Investments ===
@st.cache_data(ttl=300)
def load_investments():
    try:
        return pd.read_csv('investments.csv')
    except:
        return pd.DataFrame(columns=['ticker', 'buy_price', 'qty', 'date', 'target_price', 'profit_pct', 'drop_pct'])

def save_investments(df):
    df.to_csv('investments.csv', index=False)

# === Flow Chart ===
def draw_flow_chart(df):
    if df.empty: return None
    fig, ax = plt.subplots(figsize=(8, 4))
    invested = (df['buy_price'] * df['qty']).sum()
    current = 0
    for _, r in df.iterrows():
        try:
            price = yf.Ticker(r['ticker']).history(period='1d')['Close'].iloc[-1]
            current += price * r['qty']
        except: pass
    pnl = current - invested
    ax.text(0.1, 0.5, f"Invested\n${invested:,.0f}", ha='center', fontsize=10, bbox=dict(boxstyle="round", facecolor="lightblue"))
    ax.text(0.5, 0.5, f"Current\n${current:,.0f}", ha='center', fontsize=10, bbox=dict(boxstyle="round", facecolor="lightgreen"))
    ax.text(0.9, 0.5, f"P&L\n${pnl:,.0f}", ha='center', fontsize=10, bbox=dict(boxstyle="round", facecolor="lightcoral" if pnl < 0 else "lightgreen"))
    ax.arrow(0.25, 0.5, 0.1, 0, head_width=0.05, fc='gray')
    ax.arrow(0.65, 0.5, 0.1, 0, head_width=0.05, fc='gray')
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')
    plt.title("Portfolio Flow")
    return fig

# === AI Prediction with Sentiment ===
sentiment_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert", device=-1)

def predict_with_sentiment(ticker):
    try:
        data = yf.download(ticker, period="1y")
        data = data.reset_index()
        data['ds'] = data['Date']
        data['y'] = data['Close']

        # Sentiment
        news = yf.Ticker(ticker).news[:3]
        scores = []
        for item in news:
            result = sentiment_pipeline(item['title'])[0]
            scores.append(result['score'] if result['label'] == 'positive' else -result['score'])
        sentiment = sum(scores) / len(scores) if scores else 0
        data['sentiment'] = sentiment

        m = Prophet()
        m.add_regressor('sentiment')
        m.fit(data[['ds', 'y', 'sentiment']])
        future = m.make_future_dataframe(periods=30)
        future['sentiment'] = sentiment
        forecast = m.predict(future)
        return forecast[['ds', 'yhat']], sentiment
    except:
        return None, 0

# === PDF Export ===
def export_pdf(df):
    if df.empty: return
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="StockGuardian Portfolio", ln=1, align='C')
    for _, r in df.iterrows():
        pdf.cell(200, 10, txt=f"{r['ticker']}: {r['qty']} @ ${r['buy_price']} (Alert: {r['target_price']})", ln=1)
    buffer = BytesIO()
    pdf.output(buffer)
    b64 = base64.b64encode(buffer.getvalue()).decode()
    st.download_button("Download PDF", data=buffer.getvalue(), file_name="portfolio.pdf", mime="application/pdf")

# === Sidebar ===
with st.sidebar:
    st.header("Settings")
    st.session_state.user_email = st.text_input("Email for Alerts", st.session_state.user_email)
    st.session_state.user_phone = st.text_input("WhatsApp (+123...)", st.session_state.user_phone)
    if st.button("Test Email"):
        send_alert_email("TEST", 100, "Test Alert")
    if st.button("Test WhatsApp") and st.session_state.user_phone:
        send_whatsapp_alert("TEST", 100, "Test Alert")

    st.divider()
    st.header("Add Stock")
    with st.form("add_stock"):
        ticker = st.text_input("Ticker").upper()
        buy_price = st.number_input("Buy Price")
        qty = st.number_input("Quantity", min_value=1)
        target_price = st.number_input("Target Price (Alert)", value=buy_price*1.2)
        profit_pct = st.number_input("Profit % Alert", value=20.0)
        drop_pct = st.number_input("Drop % Alert", value=10.0)
        submitted = st.form_submit_button("Add")
        if submitted and ticker:
            new = pd.DataFrame([{
                'ticker': ticker, 'buy_price': buy_price, 'qty': qty,
                'date': datetime.now().strftime('%Y-%m-%d'),
                'target_price': target_price, 'profit_pct': profit_pct, 'drop_pct': drop_pct
            }])
            df = load_investments()
            df = pd.concat([df, new], ignore_index=True)
            save_investments(df)
            st.success(f"{ticker} added!")
            st.rerun()

# === Main App ===
st.title("StockGuardian")
st.caption("Your AI Stock Agent")

investments = load_investments()

col1, col2 = st.columns([2, 1])
with col1:
    if not investments.empty:
        st.subheader("Portfolio")
        st.dataframe(investments)
    else:
        st.info("Add your first stock in the sidebar!")

with col2:
    st.subheader("Flow Chart")
    fig = draw_flow_chart(investments)
    if fig: st.pyplot(fig)

# === Real-time P&L + Alerts ===
if not investments.empty:
    st.subheader("Live P&L")
    total_invest = (investments['buy_price'] * investments['qty']).sum()
    total_current = 0
    for _, r in investments.iterrows():
        try:
            price = yf.Ticker(r['ticker']).history(period='1d')['Close'].iloc[-1]
            value = price * r['qty']
            total_current += value
            pnl = value - (r['buy_price'] * r['qty'])
            st.metric(r['ticker'], f"${price:.2f}", f"{pnl:+.0f}")

            # Alerts
            if price >= r['target_price']:
                send_alert_email(r['ticker'], price, "Target Hit")
                send_whatsapp_alert(r['ticker'], price, "Target Hit")
            if (price - r['buy_price']) / r['buy_price'] * 100 >= r['profit_pct']:
                send_alert_email(r['ticker'], price, f"{r['profit_pct']}% Profit")
            if (r['buy_price'] - price) / r['buy_price'] * 100 >= r['drop_pct']:
                send_alert_email(r['ticker'], price, f"{r['drop_pct']}% Drop")
        except: pass

    st.metric("Total P&L", f"${total_current - total_invest:+,.0f}")

# === AI Chat ===
st.subheader("AI Forecast")
ai_ticker = st.text_input("Ask AI about a stock")
if ai_ticker and st.button("Predict 30 Days"):
    with st.spinner("Analyzing news & predicting..."):
        forecast, sentiment = predict_with_sentiment(ai_ticker)
        if forecast is not None:
            fig = px.line(forecast, x='ds', y='yhat', title=f"{ai_ticker} Forecast")
            st.plotly_chart(fig, use_container_width=True)
            st.write(f"News Sentiment: {'Positive' if sentiment > 0 else 'Negative'} ({sentiment:.2f})")

# === Export ===
if not investments.empty:
    st.download_button("Export to PDF", data=export_pdf(investments), file_name="portfolio.pdf")
