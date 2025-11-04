# app.py: StockGuardian with Real-Time Predictor
import streamlit as st
import pandas as pd
import yfinance as yf
from sklearn.linear_model import LinearRegression
import numpy as np
import plotly.express as px
from utils import *  # Keep your existing utils

# ... (keep all your existing code for setup, tabs, etc. - insert this in Dashboard tab after investments table)

with tab1:
    st.subheader("Investment Query and Research")
    # ... (keep your existing investment input code)

    # NEW: Real-Time Stock Predictor (like the HF Space)
    st.subheader("Real-Time Stock Predictor")
    symbol = st.text_input("Enter Stock Symbol (e.g., TCS.NS):", placeholder="TCS.NS")
    if st.button("Predict Next 7 Days"):
        if symbol:
            try:
                # Fetch live data (like HF Space)
                stock = yf.Ticker(symbol)
                hist = stock.history(period="1y")
                if not hist.empty:
                    current_price = hist['Close'].iloc[-1]
                    st.metric("Current Price", f"₹{current_price:.2f}")

                    # Simple Linear Regression Prediction (like HF model)
                    X = np.arange(len(hist)).reshape(-1, 1)
                    y = hist['Close'].values
                    model = LinearRegression().fit(X, y)
                    future_days = np.arange(len(hist), len(hist) + 7).reshape(-1, 1)
                    predictions = model.predict(future_days)

                    # Create forecast DF
                    forecast_df = pd.DataFrame({
                        'Day': range(1, 8),
                        'Predicted Price': predictions
                    })

                    # Chart (like HF Space output)
                    fig = px.line(forecast_df, x='Day', y='Predicted Price', title=f"{symbol} 7-Day Forecast")
                    st.plotly_chart(fig, use_container_width=True)

                    # Recommendation
                    trend = "UP" if predictions[-1] > current_price else "DOWN"
                    st.success(f"Trend: {trend} | Next Day: ₹{predictions[0]:.2f}")
                else:
                    st.error("No data for symbol. Try AAPL or TCS.NS")
            except Exception as e:
                st.error(f"Error: {e}. Check symbol.")
