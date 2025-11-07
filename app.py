import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, date
import smtplib
from email.mime.text import MimeText
from prophet import Prophet
from transformers import pipeline, Conversation
import torch
from twilio.rest import Client
from dotenv import load_dotenv
import os
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Load env vars
load_dotenv()

# Config
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASS = os.getenv('EMAIL_PASS')
TWILIO_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP = os.getenv('TWILIO_WHATSAPP_NUMBER')
USER_PHONE = os.getenv('USER_PHONE')
HF_MODEL = os.getenv('HUGGINGFACE_MODEL', 'distilgpt2')

# Initialize session state
if 'investments' not in st.session_state:
    st.session_state.investments = pd.DataFrame(columns=['symbol', 'buy_price', 'quantity', 'buy_date'])
if 'user_email' not in st.session_state:
    st.session_state.user_email = ''
if 'alerts' not in st.session_state:
    st.session_state.alerts = pd.DataFrame(columns=['symbol', 'target_price', 'profit_pct', 'drop_pct', 'type'])
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

# Email alert function
def send_email(subject, body):
    if not EMAIL_USER or not EMAIL_PASS:
        st.error("Email config missing. Check .env file.")
        return
    msg = MimeText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_USER
    msg['To'] = st.session_state.user_email
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()
        st.success("Email sent!")
    except Exception as e:
        st.error(f"Email failed: {e}")

# WhatsApp alert function (new/updated)
def send_whatsapp(message):
    if not all([TWILIO_SID, TWILIO_TOKEN, TWILIO_WHATSAPP, USER_PHONE]):
        st.error("WhatsApp config missing. Check .env for Twilio creds.")
        return
    client = Client(TWILIO_SID, TWILIO_TOKEN)
    try:
        client.messages.create(
            body=message,
            from_=TWILIO_WHATSAPP,
            to=USER_PHONE
        )
        st.success("WhatsApp sent!")
    except Exception as e:
        st.error(f"WhatsApp failed: {e}")

# Get real-time stock price (cached for speed)
@st.cache_data(ttl=60)  # Cache for 1 min
def get_stock_price(symbol):
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period='1d')
        if not data.empty:
            return data['Close'].iloc[-1]
        return None
    except:
        return None

# Calculate P/L
def calculate_pnl(df):
    if df.empty:
        return pd.DataFrame()
    df_current = df.copy()
    df_current['current_price'] = df_current['symbol'].apply(get_stock_price)
    df_current['value'] = df_current['current_price'] * df_current['quantity']
    df_current['invested'] = df_current['buy_price'] * df_current['quantity']
    df_current['pnl'] = df_current['value'] - df_current['invested']
    df_current['pnl_pct'] = (df_current['pnl'] / df_current['invested']) * 100
    return df_current

# Check alerts
def check_alerts(df_pnl):
    for _, alert in st.session_state.alerts.iterrows():
        symbol = alert['symbol']
        current = get_stock_price(symbol)
        if current:
            if alert['type'] == 'price' and current >= alert['target_price']:
                msg = f"Alert: {symbol} hit target ${alert['target_price']} (now ${current:.2f})"
                send_email("Stock Alert: Price Target", msg)
                send_whatsapp(msg)
            elif alert['type'] == 'profit' and df_pnl[df_pnl['symbol'] == symbol]['pnl_pct'].iloc[0] >= alert['profit_pct']:
                msg = f"Alert: {symbol} profit reached {alert['profit_pct']}%"
                send_email("Stock Alert: Profit Target", msg)
                send_whatsapp(msg)
            elif alert['type'] == 'drop' and df_pnl[df_pnl['symbol'] == symbol]['pnl_pct'].iloc[0] <= -abs(alert['drop_pct']):
                msg = f"Alert: {symbol} dropped {alert['drop_pct']}%"
                send_email("Stock Alert: Drop Alert", msg)
                send_whatsapp(msg)

# Prophet forecast (cached)
@st.cache_data
def forecast_stock(symbol, days=30):
    try:
        data = yf.download(symbol, period='2y')
        if data.empty:
            return None
        df_prophet = data.reset_index()[['Date', 'Close']].rename(columns={'Date': 'ds', 'Close': 'y'})
        m = Prophet()
        m.fit(df_prophet)
        future = m.make_future_dataframe(periods=days)
        forecast = m.predict(future)
        return forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail(days+1)
    except:
        return None

# AI Chat (updated with Transformers)
@st.cache_resource
def load_chat_model():
    try:
        return Conversation(pipeline('conversational', model=HF_MODEL))
    except:
        st.warning("Falling back to simple responses.")
        return None

def get_ai_response(user_input, symbol=None):
    model = load_chat_model()
    if model:
        # Add stock context
        context = f"User has stocks: {', '.join(st.session_state.investments['symbol'].tolist())}. "
        if symbol:
            price = get_stock_price(symbol)
            context += f"{symbol} current price: ${price:.2f}. "
        full_input = context + user_input
        model.add_user_input(full_input)
        response = model.generate()
        model.mark_processed(model.last_exchange_id)
        return response.generated_responses[-1]
    else:
        # Fallback
        return "I'm having trouble with the AI right now. Try asking about your stocks directly!"

# Streamlit App
st.set_page_config(page_title="StockGuardian", layout="wide")
st.title("🛡️ StockGuardian - Your AI Stock Agent")

# Sidebar for setup
with st.sidebar:
    st.header("Setup")
    user_email = st.text_input("Your Email", value=st.session_state.user_email)
    if st.button("Save Email"):
        st.session_state.user_email = user_email
        st.success("Email saved!")
    
    if st.button("Check Alerts Now"):
        df_pnl = calculate_pnl(st.session_state.investments)
        check_alerts(df_pnl)
        st.rerun()

# Tabs
tab1, tab2, tab3, tab4 = st.tabs(["📈 Dashboard", "➕ Add Stock", "🚨 Alerts", "💬 AI Chat"])

with tab1:
    st.header("Dashboard")
    if st.session_state.investments.empty:
        st.info("Add your first investment!")
    else:
        df_pnl = calculate_pnl(st.session_state.investments)
        st.dataframe(df_pnl[['symbol', 'current_price', 'pnl', 'pnl_pct']], use_container_width=True)
        
        # Total P/L
        total_pnl = df_pnl['pnl'].sum()
        total_pct = (total_pnl / df_pnl['invested'].sum()) * 100 if not df_pnl['invested'].sum() == 0 else 0
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total P&L", f"${total_pnl:.2f}", delta=f"{total_pct:.1f}%")
        
        # Portfolio chart
        fig = px.pie(df_pnl, values='value', names='symbol', title='Portfolio Allocation')
        st.plotly_chart(fig, use_container_width=True)
        
        # Select stock for forecast
        selected = st.selectbox("Forecast for:", df_pnl['symbol'].tolist())
        forecast = forecast_stock(selected, 30)
        if forecast is not None:
            fig_forecast = px.line(forecast, x='ds', y='yhat', title=f"30-Day Forecast for {selected}")
            fig_forecast.add_scatter(x=forecast['ds'], y=forecast['yhat_upper'], mode='lines', name='Upper')
            fig_forecast.add_scatter(x=forecast['ds'], y=forecast['yhat_lower'], mode='lines', name='Lower')
            st.plotly_chart(fig_forecast, use_container_width=True)
        else:
            st.error("Forecast unavailable.")

with tab2:
    st.header("Add Stock")
    with st.form("add_stock"):
        symbol = st.text_input("Symbol (e.g., AAPL)")
        buy_price = st.number_input("Buy Price", min_value=0.01)
        quantity = st.number_input("Quantity", min_value=0.01)
        buy_date = st.date_input("Buy Date", value=date.today())
        if st.form_submit_button("Add"):
            new_row = pd.DataFrame({
                'symbol': [symbol.upper()], 'buy_price': [buy_price], 'quantity': [quantity], 'buy_date': [buy_date]
            })
            st.session_state.investments = pd.concat([st.session_state.investments, new_row], ignore_index=True)
            st.success("Stock added!")
            st.rerun()

with tab3:
    st.header("Set Alerts")
    if st.session_state.investments.empty:
        st.warning("Add stocks first!")
    else:
        symbol = st.selectbox("For Stock:", st.session_state.investments['symbol'].tolist())
        alert_type = st.selectbox("Alert Type:", ['price', 'profit', 'drop'])
        if alert_type == 'price':
            target = st.number_input("Target Price", min_value=0.01)
        else:
            target = st.number_input(f"{alert_type.title()} %", min_value=0.01)
        
        if st.button("Set Alert"):
            new_alert = pd.DataFrame({
                {'symbol': [symbol], 'target_price' if alert_type == 'price' else 'profit_pct' if alert_type == 'profit' else 'drop_pct': [target], 'type': [alert_type]}
            })
            st.session_state.alerts = pd.concat([st.session_state.alerts, new_alert], ignore_index=True)
            st.success("Alert set!")

    if not st.session_state.alerts.empty:
        st.subheader("Active Alerts")
        st.dataframe(st.session_state.alerts)

with tab4:
    st.header("AI Chat Bot")
    # Chat interface
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    if prompt := st.chat_input("Ask about stocks, predictions, or anything!"):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Generate response
        symbol = None  # Auto-detect if prompt mentions a symbol
        if any(sym in prompt.upper() for sym in st.session_state.investments['symbol'].tolist()):
            symbol = next((sym for sym in st.session_state.investments['symbol'].tolist() if sym in prompt.upper()), None)
        
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                response = get_ai_response(prompt, symbol)
                st.markdown(response)
                st.session_state.chat_history.append({"role": "assistant", "content": response})
        st.rerun()

# Auto-check alerts on dashboard load (but not too often)
if st.session_state.user_email and not st.session_state.investments.empty:
    df_pnl = calculate_pnl(st.session_state.investments)
    check_alerts(df_pnl)

# Footer
st.markdown("---")
st.caption("Built with ❤️ using Streamlit, yfinance, Prophet & Hugging Face. Updated Nov 2025.")
