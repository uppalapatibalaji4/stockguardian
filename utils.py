import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import plotly.express as px
from prophet import Prophet
from twilio.rest import Client
from transformers import pipeline
import base64
from fpdf import FPDF
from io import BytesIO
import streamlit as st

# ========================================
# 1. EMAIL ALERT
# ========================================
def send_alert_email(ticker: str, current_price: float, alert_type: str, user_email: str):
    try:
        sender_email = st.secrets["GMAIL_USER"]
        sender_password = st.secrets["GMAIL_APP_PASSWORD"]

        if not user_email:
            return False

        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = user_email
        msg["Subject"] = f"StockGuardian: {ticker} {alert_type}"
        body = f"{ticker} is at ${current_price:.2f} → {alert_type}\nCheck the app!"
        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, user_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False


# ========================================
# 2. WHATSAPP ALERT
# ========================================
def send_whatsapp_alert(ticker: str, current_price: float, alert_type: str, user_phone: str):
    try:
        client = Client(st.secrets.get("TWILIO_SID"), st.secrets.get("TWILIO_AUTH"))
        if not user_phone or not st.secrets.get("TWILIO_WHATSAPP_FROM"):
            return False
        client.messages.create(
            body=f"StockGuardian: {ticker} {alert_type} @ ${current_price:.2f}",
            from_=st.secrets["TWILIO_WHATSAPP_FROM"],
            to=f"whatsapp:{user_phone}",
        )
        return True
    except Exception:
        return False


# ========================================
# 3. LOAD / SAVE INVESTMENTS
# ========================================
def load_investments() -> pd.DataFrame:
    try:
        return pd.read_csv("investments.csv")
    except FileNotFoundError:
        return pd.DataFrame(
            columns=[
                "ticker",
                "buy_price",
                "qty",
                "date",
                "target_price",
                "profit_pct",
                "drop_pct",
            ]
        )

def save_investments(df: pd.DataFrame):
    df.to_csv("investments.csv", index=False)


# ========================================
# 4. FLOW CHART
# ========================================
def draw_flow_chart(df: pd.DataFrame):
    if df.empty:
        return None
    fig, ax = plt.subplots(figsize=(8, 4))
    invested = (df["buy_price"] * df["qty"]).sum()
    current = 0.0
    for _, r in df.iterrows():
        try:
            price = yf.Ticker(r["ticker"]).history(period="1d")["Close"].iloc[-1]
            current += price * r["qty"]
        except Exception:
            pass
    pnl = current - invested

    ax.text(0.1, 0.5, f"Invested\n${invested:,.0f}", ha="center", fontsize=10,
            bbox=dict(boxstyle="round", facecolor="lightblue"))
    ax.text(0.5, 0.5, f"Current\n${current:,.0f}", ha="center", fontsize=10,
            bbox=dict(boxstyle="round", facecolor="lightgreen"))
    ax.text(0.9, 0.5, f"P&L\n${pnl:,.0f}", ha="center", fontsize=10,
            bbox=dict(boxstyle="round", facecolor="lightcoral" if pnl < 0 else "lightgreen"))
    ax.arrow(0.25, 0.5, 0.1, 0, head_width=0.05, fc="gray")
    ax.arrow(0.65, 0.5, 0.1, 0, head_width=0.05, fc="gray")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    plt.title("Portfolio Flow")
    return fig


# ========================================
# 5. AI PREDICTION WITH SENTIMENT
# ========================================
sentiment_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert", device=-1)

def predict_with_sentiment(ticker: str):
    try:
        data = yf.download(ticker, period="1y")
        data = data.reset_index()
        data["ds"] = data["Date"]
        data["y"] = data["Close"]

        news = yf.Ticker(ticker).news[:3]
        scores = []
        for item in news:
            res = sentiment_pipeline(item["title"])[0]
            scores.append(res["score"] if res["label"] == "positive" else -res["score"])
        sentiment = sum(scores) / len(scores) if scores else 0
        data["sentiment"] = sentiment

        m = Prophet()
        m.add_regressor("sentiment")
        m.fit(data[["ds", "y", "sentiment"]])
        future = m.make_future_dataframe(periods=30)
        future["sentiment"] = sentiment
        forecast = m.predict(future)
        return forecast[["ds", "yhat"]], sentiment
    except Exception as e:
        print(f"Prediction error: {e}")
        return None, 0


# ========================================
# 6. PDF EXPORT
# ========================================
def export_pdf(df: pd.DataFrame):
    if df.empty:
        return None
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="StockGuardian Portfolio", ln=1, align="C")
    for _, r in df.iterrows():
        pdf.cell(200, 10, txt=f"{r['ticker']}: {r['qty']} @ ${r['buy_price']} (Target ${r['target_price']})", ln=1)
    buffer = BytesIO()
    pdf.output(buffer)
    buffer.seek(0)
    return buffer.getvalue()
