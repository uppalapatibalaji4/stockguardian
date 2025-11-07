# app.py
import streamlit as st
import pandas as pd
import os
from datetime import date
import plotly.express as px
from utils import (
    send_email, send_whatsapp, get_stock_price,
    calculate_pnl, forecast_stock, get_ai_response
)

# ----------------------------------------------------------------------
# Session state init
# ----------------------------------------------------------------------
if 'investments' not in st.session_state:
    st.session_state.investments = pd.DataFrame(
        columns=['symbol', 'buy_price', 'quantity', 'buy_date']
    )
if 'user_email' not in st.session_state:
    st.session_state.user_email = ''
if 'alerts' not in st.session_state:
    st.session_state.alerts = pd.DataFrame(
        columns=['symbol', 'target_price', 'profit_pct', 'drop_pct', 'type']
    )
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

# ----------------------------------------------------------------------
# Helper: check all alerts
# ----------------------------------------------------------------------
def check_alerts(df_pnl: pd.DataFrame):
    for _, row in st.session_state.alerts.iterrows():
        sym = row['symbol']
        cur = get_stock_price(sym)
        if not cur:
            continue

        msg = None
        if row['type'] == 'price' and cur >= row['target_price']:
            msg = f"{sym} hit target ${row['target_price']} (now ${cur:.2f})"
        elif row['type'] == 'profit':
            pnl_pct = df_pnl.loc[df_pnl['symbol'] == sym, 'pnl_pct'].iloc[0]
            if pnl_pct >= row['profit_pct']:
                msg = f"{sym} profit reached {row['profit_pct']}% (now {pnl_pct:.1f}%)"
        elif row['type'] == 'drop':
            pnl_pct = df_pnl.loc[df_pnl['symbol'] == sym, 'pnl_pct'].iloc[0]
            if pnl_pct <= -abs(row['drop_pct']):
                msg = f"{sym} dropped {row['drop_pct']}% (now {pnl_pct:.1f}%)"

        if msg:
            send_email(f"StockGuardian Alert – {sym}", msg,
                       st.session_state.user_email)
            send_whatsapp(msg)

# ----------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------
st.set_page_config(page_title="StockGuardian", layout="wide")
st.title("StockGuardian – Your AI-Powered Stock Agent")

# ---------- Sidebar ----------
with st.sidebar:
    st.header("Setup")
    email = st.text_input("Your Email", value=st.session_state.user_email)
    if st.button("Save Email"):
        st.session_state.user_email = email
        st.success("Email saved!")

    if st.button("Run Alert Check Now"):
        if st.session_state.investments.empty:
            st.warning("No stocks yet.")
        else:
            df = calculate_pnl(st.session_state.investments)
            check_alerts(df)
            st.success("Alert check complete.")

# ---------- Tabs ----------
tab_dash, tab_add, tab_alert, tab_chat = st.tabs(
    ["Dashboard", "Add Stock", "Alerts", "AI Chat"]
)

# ------------------- Dashboard -------------------
with tab_dash:
    st.header("Dashboard")
    if st.session_state.investments.empty:
        st.info("Add your first investment to see the dashboard.")
    else:
        df = calculate_pnl(st.session_state.investments)
        st.dataframe(df[['symbol', 'current_price', 'pnl', 'pnl_pct']],
                     use_container_width=True)

        total_pnl = df['pnl'].sum()
        total_invested = df['invested'].sum()
        total_pct = (total_pnl / total_invested) * 100 if total_invested else 0
        c1, c2 = st.columns(2)
        c1.metric("Total P&L", f"${total_pnl:,.2f}")
        c2.metric("Portfolio %", f"{total_pct:.2f}%")

        # Pie chart
        fig_pie = px.pie(df, values='value', names='symbol',
                         title="Portfolio Allocation")
        st.plotly_chart(fig_pie, use_container_width=True)

        # Forecast selector
        sel = st.selectbox("30-day forecast for:", df['symbol'].tolist())
        fc = forecast_stock(sel, 30)
        if fc is not None:
            fig_fc = px.line(fc, x='ds', y='yhat',
                             title=f"30-Day Forecast – {sel}")
            fig_fc.add_scatter(x=fc['ds'], y=fc['yhat_upper'],
                               mode='lines', name='Upper')
            fig_fc.add_scatter(x=fc['ds'], y=fc['yhat_lower'],
                               mode='lines', name='Lower')
            st.plotly_chart(fig_fc, use_container_width=True)
        else:
            st.error("Forecast unavailable for this ticker.")

# ------------------- Add Stock -------------------
with tab_add:
    st.header("Add Investment")
    with st.form("add_stock_form"):
        sym = st.text_input("Symbol (e.g. AAPL)").strip().upper()
        price = st.number_input("Buy price", min_value=0.01, step=0.01)
        qty = st.number_input("Quantity", min_value=0.01, step=0.01)
        bdate = st.date_input("Buy date", value=date.today())
        submitted = st.form_submit_button("Add")
        if submitted:
            new = pd.DataFrame({
                'symbol': [sym],
                'buy_price': [price],
                'quantity': [qty],
                'buy_date': [bdate]
            })
            st.session_state.investments = pd.concat(
                [st.session_state.investments, new], ignore_index=True)
            st.success(f"{sym} added!")
            st.rerun()

# ------------------- Alerts -------------------
with tab_alert:
    st.header("Set Alerts")
    if st.session_state.investments.empty:
        st.warning("Add stocks first.")
    else:
        sym = st.selectbox("Stock", st.session_state.investments['symbol'].tolist())
        atype = st.selectbox("Alert type", ['price', 'profit', 'drop'])

        if atype == 'price':
            target = st.number_input("Target price", min_value=0.01)
            col = 'target_price'
        else:
            target = st.number_input(f"{atype.title()} %", min_value=0.01)
            col = 'profit_pct' if atype == 'profit' else 'drop_pct'

        if st.button("Create Alert"):
            new_alert = pd.DataFrame({
                'symbol': [sym],
                col: [target],
                'type': [atype]
            })
            # fill missing columns with NaN
            for c in st.session_state.alerts.columns:
                if c not in new_alert.columns:
                    new_alert[c] = pd.NA
            st.session_state.alerts = pd.concat(
                [st.session_state.alerts, new_alert], ignore_index=True)
            st.success("Alert created!")

    if not st.session_state.alerts.empty:
        st.subheader("Active Alerts")
        st.dataframe(st.session_state.alerts)

# ------------------- AI Chat -------------------
with tab_chat:
    st.header("AI Chat Bot")

    # Show history
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ask anything about your portfolio…"):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Build context
        symbols = ", ".join(st.session_state.investments['symbol'].tolist())
        context = f"User owns: {symbols}. "
        # Try to detect a ticker in the prompt
        mentioned = next((s for s in st.session_state.investments['symbol']
                          if s in prompt.upper()), None)
        if mentioned:
            price = get_stock_price(mentioned)
            context += f"{mentioned} current price: ${price:.2f}. "

        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                answer = get_ai_response(prompt, context)
                st.markdown(answer)
                st.session_state.chat_history.append(
                    {"role": "assistant", "content": answer})
        st.rerun()

# ----------------------------------------------------------------------
# Auto-alert on every dashboard load (lightweight)
# ----------------------------------------------------------------------
if st.session_state.user_email and not st.session_state.investments.empty:
    df = calculate_pnl(st.session_state.investments)
    check_alerts(df)

# ----------------------------------------------------------------------
st.caption("StockGuardian – Streamlit • yfinance • Prophet • HuggingFace – Updated Nov 2025")
