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

# Sidebar
st.sidebar.header("Your Settings")
initial_sgd = st.sidebar.number_input("Initial Capital (SGD)", value=20000.0, step=1000.0)
my_current_capital = st.sidebar.number_input("My Actual Current Capital (SGD)", value=41350.0, step=100.0)
buffer_pct = st.sidebar.slider("Permanent Cash Buffer %", 0.05, 0.20, 0.10, step=0.01)
fd_rate = st.sidebar.slider("FD Rate %", 0.02, 0.06, 0.035)
show_details = st.sidebar.checkbox("Show Full Backtest", value=False)

# Fetch data
@st.cache_data(ttl=1800)
def fetch_data():
    tickers = ['QQQ', 'SPY', 'MTUM', 'SGD=X']
    df = yf.download(tickers, start='2022-10-01', progress=False, group_by='ticker')
    closes = pd.DataFrame({t: df[t]['Close'] for t in ['QQQ', 'SPY', 'MTUM']})
    closes['USDSGD'] = df['SGD=X']['Close']
    return closes.dropna()

prices = fetch_data()

# Blended & indicators
prices['blended_usd'] = (0.5 * prices['QQQ']/prices['QQQ'].iloc[0] +
                         0.2 * prices['SPY']/prices['SPY'].iloc[0] +
                         0.3 * prices['MTUM']/prices['MTUM'].iloc[0]) * 100
prices['blended_sgd'] = prices['blended_usd'] * (prices['USDSGD'] / prices['USDSGD'].iloc[0])

weekly = prices.resample('W-FRI').last()
weekly['sma20w'] = weekly['blended_usd'].rolling(20).mean()
delta = weekly['blended_usd'].diff()
gain = delta.where(delta > 0, 0).rolling(14).mean()
loss = abs(delta.where(delta < 0, 0)).rolling(14).mean()
weekly['rsi14w'] = 100 - (100 / (1 + gain / loss))
prices = prices.join(weekly[['sma20w', 'rsi14w']].ffill())

# Backtest simulation with buffer
equity_curve = pd.Series(dtype=float)
equity_curve.iloc[0] = initial_sgd
cash = initial_sgd * buffer_pct
invested = initial_sgd * (1 - buffer_pct)
position = 0

for i in range(1, len(prices)):
    row = prices.iloc[i]
    blended = row['blended_usd']
    sma = row['sma20w']
    rsi = row['rsi14w']
    usdsgd = row['USDSGD']
    
    # Entry signal
    if position == 0 and sma > 0 and blended > sma and rsi < 70:
        position = invested / (blended * usdsgd / 100)
    
    # Exit signal
    if position > 0 and (blended < sma or rsi > 85):
        invested = position * (blended * usdsgd / 100)
        position = 0
    
    # Update equity
    position_value = position * (blended * usdsgd / 100) if position > 0 else 0
    fd_interest = cash * (fd_rate / 365)
    cash += fd_interest
    equity = position_value + cash
    equity_curve[prices.index[i]] = equity

final_value = equity_curve.iloc[-1]

# === LIVE PORTFOLIO EXECUTION PANEL ===
st.subheader("📋 Live Portfolio Execution – " + datetime.now().strftime("%d %b %Y"))

latest = prices.iloc[-1]
usdsgd = latest['USDSGD']
current_value = my_current_capital

cash_buffer = current_value * buffer_pct
invested_target = current_value - cash_buffer

# Live prices
qqq_price = latest['QQQ']
spy_price = latest['SPY']
mtum_price = latest['MTUM']

qqq_sgd = qqq_price * usdsgd
spy_sgd = spy_price * usdsgd
mtum_sgd = mtum_price * usdsgd

# Target SGD & Shares
targets = {
    'QQQ': {'weight': 0.50, 'price_usd': qqq_price, 'price_sgd': qqq_sgd},
    'SPY': {'weight': 0.20, 'price_usd': spy_price, 'price_sgd': spy_sgd},
    'MTUM': {'weight': 0.30, 'price_usd': mtum_price, 'price_sgd': mtum_sgd}
}

st.write("**Current Live Prices**")
price_table = pd.DataFrame({
    'ETF': ['QQQ', 'SPY', 'MTUM'],
    'Price USD': [qqq_price, spy_price, mtum_price],
    'Price SGD': [qqq_sgd, spy_sgd, mtum_sgd]
}).round(2)
st.dataframe(price_table, use_container_width=True)

# Target Holdings Table
data = []
for etf, info in targets.items():
    target_sgd = invested_target * info['weight']
    shares = target_sgd / info['price_sgd']
    data.append({
        'ETF': etf,
        'Target % (of invested)': f"{info['weight']*100}-%",
        'Target SGD': f"S${target_sgd:,.0f}",
        'Shares to Hold': round(shares, 2),
        'Cost SGD': f"S${target_sgd:,.0f}"
    })

st.write("**Target Holdings (rebalance to these)**")
holdings_df = pd.DataFrame(data)
st.dataframe(holdings_df, use_container_width=True, hide_index=True)

# Rebalance Calculator
st.subheader("🔄 One-Click Rebalance Calculator")
if st.button("Calculate Exact Buy/Sell Orders Now"):
    st.success("Rebalance Instructions:")
    for row in data:
        st.write(f"**{row['ETF']}**: Buy **{row['Shares to Hold']} shares** for **{row['Cost SGD']}**")
    st.info("Total to invest from buffer/cash: S$" + f"{invested_target:,.0f}")

# Status & Action
col1, col2 = st.columns(2)
with col1:
    st.metric("Portfolio Value", f"S${current_value:,.0f}", f"+{((current_value/initial_sgd - 1)*100):.1f}%")
with col2:
    st.metric("Cash Buffer", f"S${cash_buffer:,.0f}", f"{buffer_pct*100:.0f}%")

# Equity Curve
fig = go.Figure()
fig.add_trace(go.Scatter(x=equity_curve.index, y=equity_curve.values, mode='lines', name='Equity'))
fig.update_layout(title="Backtest Equity Curve", xaxis_title="Date", yaxis_title="Value (SGD)", hovermode='x unified')
st.plotly_chart(fig, use_container_width=True)

if st.button("🔄 Refresh All Live Data & Signals"):
    st.cache_data.clear()
    st.rerun()

st.caption("Max 3 holdings ever. Rebalance quarterly or on entry/trim signals. Educational only – not advice.")
