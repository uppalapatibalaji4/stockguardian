import streamlit as st
import pandas as pd
from datetime import datetime
import os

# === AUTO-CREATE utils.py IF MISSING ===
utils_path = "utils.py"
if not os.path.exists(utils_path):
    st.error("`utils.py` is missing! Creating it automatically...")
    utils_code = '''import streamlit as st
import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, time as dt_time
import matplotlib.pyplot as plt
import mplfinance as mpf
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from twilio.rest import Client

@st.cache_data(ttl=300)
def load_investments():
    try: return pd.read_csv('investments.csv')
    except FileNotFoundError: return pd.DataFrame(columns=['ticker','buy_price','qty','date','platform'])

def save_investments(df): df.to_csv('investments.csv', index=False)

def send_email_alert(ticker, price, typ):
    try:
        s, p, u = st.session_state.get("sender_email"), st.session_state.get("app_password"), st.session_state.get("user_email")
        if not all([s,p,u]): return False
        msg = MIMEMultipart(); msg['From']=s; msg['To']=u; msg['Subject']=f"Alert: {ticker}"
        msg.attach(MIMEText(f"{ticker} {typ} at ₹{price:.2f}", 'plain'))
        server = smtplib.SMTP('smtp.gmail.com',587); server.starttls(); server.login(s,p)
        server.sendmail(s,u,msg.as_string()); server.quit(); return True
    except: return False

def send_whatsapp_alert(ticker, price, typ):
    try:
        sid = st.secrets.get("TWILIO_SID"); token = st.secrets.get("TWILIO_TOKEN")
        fr = st.secrets.get("TWILIO_FROM"); to = st.session_state.get("whatsapp_number")
        if not all([sid,token,fr,to]): return False
        Client(sid,token).messages.create(body=f"{ticker} {typ} at ₹{price:.2f}", from_=f"whatsapp:{fr}", to=f"whatsapp:{to}")
        return True
    except: return False

def get_live_data(ticker):
    try:
        stock = yf.Ticker(ticker); info = stock.info; hist = stock.history(period="1d")
        if hist.empty: return None, "No data"
        cur = info.get('regularMarketPrice', hist['Close'].iloc[-1])
        return {'current':cur, 'high':info.get('regularMarketDayHigh',hist['High'].max()),
                'low':info.get('regularMarketDayLow',hist['Low'].min()),
                'volume':info.get('regularMarketVolume',hist['Volume'].sum()),
                'market_open': dt_time(9,15) <= datetime.now().time() <= dt_time(15,30)}, None
    except: return None, "Invalid ticker"

def get_pnl(ticker, buy): data, err = get_live_data(ticker); return (data['current'], ((data['current']-buy)/buy)*100) if not err else (None, err)

def get_sentiment_advice(ticker):
    try:
        news = yf.Ticker(ticker).news[:3]; analyzer = SentimentIntensityAnalyzer()
        avg = sum(analyzer.polarity_scores(n['title'])['compound'] for n in news)/len(news)
        return ("Positive","Buy") if avg>0.3 else (("Negative","Sell") if avg<-0.3 else ("Neutral","Hold"))
    except: return "Neutral","Hold"

def draw_trading_chart(ticker):
    try:
        hist = yf.download(ticker, period='5d', interval='5m', progress=False)
        if hist.empty or len(hist)<10:
            fig,ax=plt.subplots(); ax.text(0.5,0.5,'No data'); ax.axis('off'); return fig
        mpf.plot(hist, type='candle', style='charles', volume=True, title=f"{ticker} Chart", figsize=(10,6), returnfig=True)
        return plt.gcf()
    except:
        fig,ax=plt.subplots(); ax.text(0.5,0.5,'Error'); ax.axis('off'); return fig

def test_alert(ticker):
    data, err = get_live_data(ticker)
    if err: st.error(err); return
    send_email_alert(ticker, data['current'], "TEST")
    send_whatsapp_alert(ticker, data['current'], "TEST")
'''
    with open(utils_path, "w") as f:
        f.write(utils_code)
    st.success("`utils.py` created! Refreshing in 3 seconds...")
    import time; time.sleep(3); st.rerun()

# === NOW IMPORT SAFELY ===
from utils import (
    load_investments, save_investments, send_email_alert, send_whatsapp_alert,
    get_live_data, get_pnl, get_sentiment_advice, draw_trading_chart, test_alert
)

# === REST OF APP (UNCHANGED) ===
st.set_page_config(page_title="StockGuardian", layout="wide")
st.markdown("<style>.stApp{background:#0e1117;color:white}</style>", unsafe_allow_html=True)
st.title("StockGuardian: Upstox Clone")
st.warning("Market: 9:15 AM - 3:30 PM IST")

tab1, tab2, _ = st.tabs(["Dashboard", "Alerts", "Chat"])

with tab2:
    st.header("Alerts")
    c1,c2 = st.columns(2)
    with c1:
        with st.form("g"):
            e1=st.text_input("Your Email"); e2=st.text_input("Sender"); e3=st.text_input("App Pass",type="password")
            if st.form_submit_button("Save"): st.session_state.user_email=e1; st.session_state.sender_email=e2; st.session_state.app_password=e3; st.success("Saved")
    with c2:
        with st.form("w"):
            w=st.text_input("WhatsApp (+91...)")
            if st.form_submit_button("Save"): st.session_state.whatsapp_number=w; st.success("Saved")
    if st.button("Test Alert"): test_alert(st.text_input("Ticker", "TCS.NS"))

with tab1:
    st.header("Add Stock")
    df = load_investments()
    with st.form("a"):
        c1,c2=st.columns(2)
        with c1: t=st.text_input("Symbol","TCS.NS").upper(); b=st.number_input("Buy",0.01,step=0.01)
        with c2: q=st.number_input("Qty",1,step=1); p=st.selectbox("Platform",["Upstox","Zerodha"])
        if st.form_submit_button("Add"):
            new = pd.DataFrame([{'ticker':t,'buy_price':b,'qty':q,'date':datetime.now().strftime('%Y-%m-%d'),'platform':p}])
            df = pd.concat([df,new],ignore_index=True); save_investments(df); st.rerun()

    if not df.empty:
        sel = st.selectbox("Select",df['ticker'])
        r = df[df['ticker']==sel].iloc[0]
        data, err = get_live_data(r['ticker'])
        cur = r['buy_price'] if err else data['current']
        pnl = 0 if err else ((cur-r['buy_price'])/r['buy_price'])*100
        st.metric("Profit", f"{pnl:+.2f}%" if not err else "No Data")
        if not err:
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Current",f"₹{data['current']:.2f}")
            c2.metric("High",f"₹{data['high']:.2f}")
            c3.metric("Low",f"₹{data['low']:.2f}")
            c4.metric("Volume",f"{data['volume']:,.0f}")
        st.pyplot(draw_trading_chart(r['ticker']))
