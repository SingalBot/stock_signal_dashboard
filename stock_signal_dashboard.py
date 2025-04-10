import streamlit as st
import pandas as pd
import yfinance as yf
from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volatility import BollingerBands
import plotly.graph_objects as go
import time
import requests
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

# Validate environment variables
if not all([TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
    st.error("Telegram credentials are missing. Please set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in Streamlit secrets.")
if not all([EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER]):
    st.warning("Email credentials are incomplete. Email notifications will be disabled.")

# Cache stock data to reduce API calls
@st.cache_data(ttl=300)
def get_stock_data(symbol, period="1d", interval="5m"):
    try:
        df = yf.download(symbol, period=period, interval=interval, progress=False)
        if df.empty:
            st.error(f"No data found for {symbol}. Please check the symbol.")
            return pd.DataFrame()
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]
        if 'Date' in df.columns:
            df.rename(columns={'Date': 'Datetime'}, inplace=True)
        df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
        if df['Close'].isna().all():
            st.error(f"Invalid Close data for {symbol}.")
            return pd.DataFrame()
        return df
    except Exception as e:
        st.error(f"Error fetching data for {symbol}: {str(e)}")
        return pd.DataFrame()

def send_telegram_message(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        response = requests.post(url, data=payload, timeout=5)
        response.raise_for_status()
    except Exception as e:
        st.warning(f"Failed to send Telegram message: {str(e)}")

def send_email_notification(message):
    if not all([EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER]):
        return
    try:
        msg = MIMEText(message)
        msg['Subject'] = f"Stock Signal Alert for {symbol.upper()}"
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_RECEIVER
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        st.success("Email notification sent!")
    except Exception as e:
        st.warning(f"Failed to send email: {str(e)}")

def compute_signals(df, rsi_period=14, macd_fast=12, macd_slow=26, macd_signal=9):
    if "Close" not in df.columns or df["Close"].isna().all():
        st.error("Close column missing or invalid.")
        return df
    df = df.dropna(subset=["Close"])
    if df.empty:
        st.error("No valid data after dropping NaNs.")
        return df
    try:
        rsi = RSIIndicator(df["Close"], window=rsi_period)
        macd = MACD(df["Close"], window_fast=macd_fast, window_slow=macd_slow, window_sign=macd_signal)
        bb = BollingerBands(df["Close"])
        df["RSI"] = rsi.rsi()
        df["MACD"] = macd.macd()
        df["Signal"] = macd.macd_signal()
        df["BB_High"] = bb.bollinger_hband()
        df["BB_Low"] = bb.bollinger_lband()
        df["Buy_Signal"] = (df["MACD"] > df["Signal"]) & (df["RSI"] < 30) & (df["Close"] < df["BB_Low"])
        df["Sell_Signal"] = (df["MACD"] < df["Signal"]) & (df["RSI"] > 70) & (df["Close"] > df["BB_High"])
    except Exception as e:
        st.error(f"Error computing indicators: {str(e)}")
    return df

def plot_stock_data(data, symbol):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=data["Datetime"], y=data["Close"], mode="lines", name="Close", line=dict(color="blue")))
    fig.add_trace(go.Scatter(x=data["Datetime"], y=data["BB_High"], mode="lines", name="Bollinger High", line=dict(color="green", dash="dash")))
    fig.add_trace(go.Scatter(x=data["Datetime"], y=data["BB_Low"], mode="lines", name="Bollinger Low", line=dict(color="red", dash="dash")))
    fig.update_layout(
        title=f"Stock Price and Bollinger Bands for {symbol.upper()}",
        xaxis_title="Time",
        yaxis_title="Price",
        template="plotly_dark" if st.session_state.theme == "Dark" else "plotly_white",
        height=500
    )
    st.plotly_chart(fig, use_container_width=True)

# Streamlit configuration
st.set_page_config(page_title="Stock Signal Dashboard", layout="wide")
st.title("📈 Live Stock Signal Dashboard")

# Initialize session state
if "theme" not in st.session_state:
    st.session_state.theme = "Light"

# Sidebar settings
with st.sidebar:
    st.header("Settings")
    symbol = st.text_input("Stock Symbol (e.g., AAPL, RELIANCE.NS):", "AAPL").upper()
    refresh_interval = st.slider("Refresh Interval (seconds):", 10, 300, 60)
    rsi_period = st.slider("RSI Period:", 5, 50, 14)
    macd_fast = st.slider("MACD Fast Period:", 5, 50, 12)
    macd_slow = st.slider("MACD Slow Period:", 10, 100, 26)
    macd_signal = st.slider("MACD Signal Period:", 5, 50, 9)
    enable_email = st.checkbox("Enable Email Notifications", value=False)
    theme = st.selectbox("Theme", ["Light", "Dark"], index=0 if st.session_state.theme == "Light" else 1)
    st.session_state.theme = theme

# Main dashboard
placeholder = st.empty()

while True:
    with placeholder.container():
        data = get_stock_data(symbol)
        if not data.empty:
            data = compute_signals(data, rsi_period, macd_fast, macd_slow, macd_signal)
            if not data.empty and "Close" in data.columns:
                latest = data.iloc[-1]
                st.subheader(f"Live Signals for {symbol}")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Current Price", f"${latest['Close']:.2f}")
                with col2:
                    st.metric("RSI", f"{latest['RSI']:.2f}")
                with col3:
                    st.metric("MACD", f"{latest['MACD']:.2f}")
                plot_stock_data(data, symbol)
                if latest["Buy_Signal"]:
                    st.success("✅ Buy Signal Detected!")
                    send_telegram_message(f"📈 Buy Signal for {symbol} at {latest['Close']:.2f}")
                    if enable_email:
                        send_email_notification(f"Buy Signal for {symbol} at {latest['Close']:.2f}")
                elif latest["Sell_Signal"]:
                    st.error("🔻 Sell Signal Detected!")
                    send_telegram_message(f"📉 Sell Signal for {symbol} at {latest['Close']:.2f}")
                    if enable_email:
                        send_email_notification(f"Sell Signal for {symbol} at {latest['Close']:.2f}")
                else:
                    st.info("🔍 No strong signal currently.")
                with st.expander("📊 Recent Data"):
                    st.dataframe(data.tail(10).style.format({"Close": "{:.2f}", "RSI": "{:.2f}", "MACD": "{:.2f}", "Signal": "{:.2f}", "BB_High": "{:.2f}", "BB_Low": "{:.2f}"}))
        time.sleep(refresh_interval)
        st.rerun()