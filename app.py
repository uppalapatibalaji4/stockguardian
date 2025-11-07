# app.py
import streamlit as st
import pandas as pd
from datetime import date
import plotly.express as px

from utils import (
    send_email, send_whatsapp, get_stock_price,
    calculate_pnl, forecast_stock, get_ai_response
)

# --------------------------------------------------------------
# SESSION STATE
# --------------------------------------------------------------
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


# --------------------------------------------------------------
# CHECK ALERTS
# --------------------------------------------------------------
def check_alerts(df_pnl: pd.DataFrame):
    if not st.session_state.user_email:
        return
    for _, row in st.session_state.alerts.iterrows():
        sym = row['symbol']
        cur = get_stock_price(sym)
        if not cur:
            continue
        msg = None
        if row['type'] == 'price' and cur >= row['target_price']:
            msg = f"{sym} hit ${row['target_price']} → ${cur:.2f}"
        elif row['type'] == 'profit':
            pnl = df_pnl.loc[df_pnl['symbol'] == sym, 'pnl_pct'].iloc[0]
            if pnl >= row['profit_pct']:
                msg = f"{sym} profit ≥ {row['profit_pct']}% (now {pnl:.1f}%)"
        elif row['type'] == 'drop':
            pnl = df_pnl.loc[df_pnl['symbol'] == sym, 'pnl_pct'].iloc[0]
            if pnl <= -abs(row['drop_pct']):
                msg = f"{sym} dropped ≥ {row['drop_pct']}% (now {pnl:.1f}%)"
        if msg:
            send_email(f"Alert: {sym}", msg, st.session_state.user_email)
            send_whatsapp(msg)


# --------------------------------------------------------------
# UI
# --------------------------------------------------------------
st.set_page_config(page_title="StockGuardian", layout="wide")
st.title("StockGuardian – Your Stock Agent")

with st.sidebar:
    st.header("Setup")
    email = st.text_input("Your Email", value=st.session_state.user_email)
    if st.button("Save Email"):
        st.session_state.user_email = email
        st.success("Email saved!")

    if st.button("Check Alerts Now"):
        if not st.session_state.investments.empty:
            df = calculate_pnl(st.session_state.investments)
            check_alerts(df)
            st.success("Alerts checked!")

tab1, tab2, tab3, tab4 = st.tabs(["Dashboard", "Add Stock", "Alerts", "AI Chat"])

# === DASHBOARD ===
with tab1:
    st.header("Portfolio")
    if st.session_state.investments.empty:
        st.info("Add your first stock to see the dashboard.")
    else:
        df = calculate_pnl(st.session_state.investments)
        st.dataframe(df[['symbol', 'current_price', 'pnl', 'pnl_pct']], use_container_width=True)

        total_pnl = df['pnl'].sum()
        total_inv = df['invested'].sum()
        total_pct = (total_pnl / total_inv) * 100 if total_inv else 0

        c1, c2 = st.columns(2)
        c1.metric("Total P&L", f"${total_pnl:,.2f}")
        c2.metric("Return", f"{total_pct:.2f}%")

        fig = px.pie(df, values='value', names='symbol', title="Portfolio Allocation")
        st.plotly_chart(fig, use_container_width=True)

        sel = st.selectbox("30-Day Forecast", df['symbol'])
        fc = forecast_stock(sel)
        if fc is not None:
            fig_fc = px.line(fc, x='ds', y='yhat', title=f"30-Day Forecast: {sel}")
            fig_fc.add_scatter(x=fc['ds'], y='yhat_upper', mode='lines', name='Upper Bound')
            fig_fc.add_scatter(x=fc['ds'], y='yhat_lower', mode='lines', name='Lower Bound')
            st.plotly_chart(fig_fc, use_container_width=True)
        else:
            st.warning("Not enough data for forecast.")

# === ADD STOCK ===
with tab2:
    st.header("Add Investment")
    with st.form("add_form"):
        sym = st.text_input("Symbol (e.g. AAPL)").strip().upper()
        price = st.number_input("Buy Price", min_value=0.01, step=0.01)
        qty = st.number_input("Quantity", min_value=0.01, step=0.01)
        bdate = st.date_input("Buy Date", value=date.today())
        submitted = st.form_submit_button("Add Stock")
        if submitted:
            if not sym:
                st.error("Symbol is required.")
            else:
                new = pd.DataFrame([{
                    'symbol': sym,
                    'buy_price': price,
                    'quantity': qty,
                    'buy_date': bdate
                }])
                st.session_state.investments = pd.concat([st.session_state.investments, new], ignore_index=True)
                st.success(f"{sym} added!")
                st.rerun()

# === ALERTS ===
with tab3:
    st.header("Set Alerts")
    if st.session_state.investments.empty:
        st.warning("Add stocks first.")
    else:
        sym = st.selectbox("Stock", st.session_state.investments['symbol'])
        atype = st.selectbox("Alert Type", ['price', 'profit', 'drop'])
        val = st.number_input("Target Value", min_value=0.01)

        if st.button("Create Alert"):
            col = 'target_price' if atype == 'price' else 'profit_pct' if atype == 'profit' else 'drop_pct'
            new = pd.DataFrame([{'symbol': sym, col: val, 'type': atype}])
            for c in st.session_state.alerts.columns:
                if c not in new.columns:
                    new[c] = pd.NA
            st.session_state.alerts = pd.concat([st.session_state.alerts, new], ignore_index=True)
            st.success("Alert created!")

    if not st.session_state.alerts.empty:
        st.subheader("Active Alerts")
        st.dataframe(st.session_state.alerts)

# === AI CHAT ===
with tab4:
    st.header("AI Chat Bot")
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ask about your portfolio..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        context = " ".join(st.session_state.investments['symbol'].tolist())
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                ans = get_ai_response(prompt, context)
                st.markdown(ans)
                st.session_state.chat_history.append({"role": "assistant", "content": ans})
        st.rerun()


# --------------------------------------------------------------
# AUTO ALERT CHECK
# --------------------------------------------------------------
if st.session_state.user_email and not st.session_state.investments.empty:
    df = calculate_pnl(st.session_state.investments)
    check_alerts(df)

st.caption("StockGuardian © 2025 | Fast • Reliable • No AI Models")
