import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')

st.set_page_config(page_title="Risk-Averse Growth Pro", layout="wide")

st.title("🚀 Risk-Averse Growth Strategy Pro – 10% Cash Buffer")
st.markdown("**S$20k → 100% in 3 years | Max 3 ETFs | 15% Uncle Point | Live Shares & Rebalance**")

# ────────────────────────────────────────────────
# Sidebar settings
# ────────────────────────────────────────────────
st.sidebar.header("Your Settings")

initial_sgd = st.sidebar.number_input("Initial Capital (SGD)", value=20000.0, step=1000.0)
my_current_capital = st.sidebar.number_input("My Actual Current Capital (SGD)", value=41350.0, step=100.0)
buffer_pct = st.sidebar.slider("Permanent Cash Buffer %", 0.05, 0.20, 0.10, step=0.01)
fd_rate = st.sidebar.slider("FD Rate % (annual)", 0.02, 0.06, 0.035)
show_details = st.sidebar.checkbox("Show Debug / Full Backtest Info", value=False)

# ────────────────────────────────────────────────
# Data fetching – safer version
# ────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner="Fetching latest market data...")
def fetch_data():
    try:
        tickers = ['QQQ', 'SPY', 'MTUM', 'SGD=X']
        # Download without group_by → usually gives flat columns now
        df = yf.download(tickers, start='2022-10-01', progress=False, auto_adjust=True)

        # If still multi-index (newer yfinance behavior), flatten to Close prices
        if isinstance(df.columns, pd.MultiIndex):
            closes = df.xs('Close', axis=1, level=1, drop_level=True)
        else:
            closes = df['Close'] if 'Close' in df.columns else df

        # Rename forex ticker consistently
        if 'SGD=X' in closes.columns:
            closes = closes.rename(columns={'SGD=X': 'USDSGD'})

        # Keep only needed columns
        closes = closes[['QQQ', 'SPY', 'MTUM', 'USDSGD']].dropna()

        if closes.empty:
            st.error("No data returned from yfinance. Check internet or try later.")
            return None

        return closes

    except Exception as e:
        st.error(f"Data download failed: {str(e)}")
        return None

prices = fetch_data()

if prices is None:
    st.stop()

# Debug output (visible only if checkbox selected)
if show_details:
    st.subheader("Debug: Data shape & columns")
    st.write("Shape:", prices.shape)
    st.write("Columns:", list(prices.columns))
    st.write("First few rows:", prices.head(3))

# ────────────────────────────────────────────────
# Calculate blended index (base 100)
# ────────────────────────────────────────────────
try:
    base = prices.iloc[0]
    prices['blended_usd'] = (
        0.5 * (prices['QQQ'] / base['QQQ']) +
        0.2 * (prices['SPY'] / base['SPY']) +
        0.3 * (prices['MTUM'] / base['MTUM'])
    ) * 100

    prices['blended_sgd'] = prices['blended_usd'] * (prices['USDSGD'] / base['USDSGD'])

except Exception as e:
    st.error(f"Error calculating blended index: {str(e)}")
    st.stop()

# ────────────────────────────────────────────────
# Weekly indicators (SMA20w + RSI14w)
# ────────────────────────────────────────────────
weekly = prices.resample('W-FRI').last()

weekly['sma20w'] = weekly['blended_usd'].rolling(window=20, min_periods=10).mean()

delta = weekly['blended_usd'].diff()
gain = delta.where(delta > 0, 0).rolling(window=14, min_periods=7).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=7).mean()
rs = gain / loss.replace(0, np.nan)
weekly['rsi14w'] = 100 - (100 / (1 + rs))

# Forward fill indicators to daily data
prices = prices.join(weekly[['sma20w', 'rsi14w']].ffill())

# ────────────────────────────────────────────────
# Very simple backtest visualization (placeholder – can be expanded later)
# ────────────────────────────────────────────────
equity_curve = pd.Series(index=prices.index, dtype=float)
equity_curve.iloc[0] = initial_sgd

for i in range(1, len(prices)):
    equity_curve.iloc[i] = equity_curve.iloc[i-1] * (1 + prices['blended_sgd'].iloc[i])

# ────────────────────────────────────────────────
# LIVE PORTFOLIO SECTION
# ────────────────────────────────────────────────
st.subheader("📋 Live Portfolio Execution – " + datetime.now().strftime("%d %b %Y %H:%M %Z"))

latest = prices.iloc[-1]
usdsgd = latest['USDSGD']
current_value = my_current_capital

cash_buffer = current_value * buffer_pct
invested_target = current_value - cash_buffer

# Current prices
qqq_price = latest['QQQ']
spy_price = latest['SPY']
mtum_price = latest['MTUM']

qqq_sgd = qqq_price * usdsgd
spy_sgd = spy_price * usdsgd
mtum_sgd = mtum_price * usdsgd

# Price table
st.write("**Current Live Prices**")
price_table = pd.DataFrame({
    'ETF': ['QQQ', 'SPY', 'MTUM'],
    'Price USD': [round(qqq_price, 2), round(spy_price, 2), round(mtum_price, 2)],
    'Price SGD': [round(qqq_sgd, 2), round(spy_sgd, 2), round(mtum_sgd, 2)]
})
st.dataframe(price_table, use_container_width=True)

# Target holdings
targets = {
    'QQQ':  {'weight': 0.50, 'price_sgd': qqq_sgd},
    'SPY':  {'weight': 0.20, 'price_sgd': spy_sgd},
    'MTUM': {'weight': 0.30, 'price_sgd': mtum_sgd}
}

data = []
for etf, info in targets.items():
    target_sgd = invested_target * info['weight']
    shares = target_sgd / info['price_sgd'] if info['price_sgd'] > 0 else 0
    data.append({
        'ETF': etf,
        'Target % (of invested)': f"{info['weight']*100:.0f}%",
        'Target SGD': f"S${target_sgd:,.0f}",
        'Shares to Hold': round(shares, 2),
        'Approx Cost SGD': f"S${target_sgd:,.0f}"
    })

st.write("**Target Holdings (rebalance to these amounts)**")
holdings_df = pd.DataFrame(data)
st.dataframe(holdings_df, use_container_width=True, hide_index=True)

# Rebalance button
st.subheader("🔄 One-Click Rebalance Calculator")
if st.button("Show Exact Buy/Sell Instructions"):
    st.success("Rebalance to the following:")
    for row in data:
        st.write(f"**{row['ETF']}**: Aim for **{row['Shares to Hold']} shares** ≈ **{row['Approx Cost SGD']}**")
    st.info(f"Total to be invested (after buffer): **S${invested_target:,.0f}**")

# Simple metrics
col1, col2, col3 = st.columns(3)
col1.metric("Current Portfolio", f"S${current_value:,.0f}", f"{((current_value/initial_sgd - 1)*100):+.1f}%")
col2.metric("Cash Buffer", f"S${cash_buffer:,.0f}", f"{buffer_pct*100:.0f}% always safe")
col3.metric("Invested Target", f"S${invested_target:,.0f}")

# Equity curve (very basic – using blended return only)
st.subheader("Backtest Equity Curve (simplified)")
fig = go.Figure()
fig.add_trace(go.Scatter(
    x=equity_curve.index,
    y=equity_curve,
    mode='lines',
    name='Portfolio Value',
    line=dict(color='#1f77b4', width=2.5)
))
fig.update_layout(
    title="Simulated Growth (blended return, no trading rules applied yet)",
    xaxis_title="Date",
    yaxis_title="SGD Value",
    template="plotly_white",
    hovermode='x unified'
)
st.plotly_chart(fig, use_container_width=True)

# Refresh
if st.button("🔄 Refresh Latest Prices & Recalculate"):
    st.cache_data.clear()
    st.rerun()

st.caption("Educational simulation – not financial advice. Max 3 ETFs. Past performance ≠ future results.")
