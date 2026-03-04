import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')

st.set_page_config(page_title="Risk-Averse Growth – Live Rebalance", layout="wide")

st.title("🚀 Risk-Averse Growth Strategy – Live Rebalance Tool")
st.markdown("**70% Growth + 30% Momentum | 10% permanent SGD buffer | RSI trim + trend filter**")

# ────────────────────────────────────────────────
# Sidebar – User inputs
# ────────────────────────────────────────────────
st.sidebar.header("Your Position & Settings")

total_capital = st.sidebar.number_input("My Current Total Capital (SGD)", value=20000.0, step=1000.0, min_value=0.0)
buffer_pct    = st.sidebar.slider("Permanent Cash Buffer %", 0.05, 0.20, 0.10, step=0.01)

st.sidebar.markdown("---")
st.sidebar.subheader("Current Holdings (approximate)")

current_qqq_shares  = st.sidebar.number_input("Current QQQ shares",  value=0.0, step=0.1)
current_spy_shares  = st.sidebar.number_input("Current SPY shares",  value=0.0, step=0.1)
current_mtum_shares = st.sidebar.number_input("Current MTUM shares", value=0.0, step=0.1)

# ────────────────────────────────────────────────
# Data fetch
# ────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner="Fetching latest prices (with retry)...")  # shorter TTL for faster retry
def get_latest_data():
    import time
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
    ]

    for attempt in range(3):
        try:
            tickers = ['QQQ', 'SPY', 'MTUM', 'SGD=X']
            session = yf.utils.get_session()
            session.headers.update({"User-Agent": user_agents[attempt % len(user_agents)]})

            df = yf.download(
                tickers,
                period="2y",
                interval="1d",
                progress=False,
                auto_adjust=True,
                ignore_tz=True,
                session=session
            )

            if isinstance(df.columns, pd.MultiIndex):
                closes = df['Close']
            else:
                closes = df

            closes = closes.rename(columns={'SGD=X': 'USDSGD'})
            closes = closes[['QQQ', 'SPY', 'MTUM', 'USDSGD']].dropna(how='all')

            if not closes.empty:
                return closes

            time.sleep(2)  # brief backoff

        except Exception as e:
            st.warning(f"Attempt {attempt+1}/3 failed: {str(e)}")
            time.sleep(3)

    # Ultimate fallback if all attempts fail
    st.warning("Yahoo Finance temporarily unavailable — using static demo prices (not real-time).")
    dates = pd.date_range(end=datetime.now(), periods=500, freq='B')  # business days ~2y
    fallback = pd.DataFrame(index=dates)
    fallback['QQQ']   = np.linspace(400, 520, len(dates))   # fake upward trend
    fallback['SPY']   = np.linspace(450, 580, len(dates))
    fallback['MTUM']  = np.linspace(160, 220, len(dates))
    fallback['USDSGD'] = 1.35
    return fallback

prices = get_latest_data()

if prices is None or prices.empty:
    st.error("Could not fetch market data right now. Please try again in a few minutes.")
    st.stop()

# ────────────────────────────────────────────────
# Blended index + weekly indicators
# ────────────────────────────────────────────────
base = prices.iloc[0]
prices['blended_usd'] = (
    0.5 * (prices['QQQ'] / base['QQQ']) +
    0.2 * (prices['SPY'] / base['SPY']) +
    0.3 * (prices['MTUM'] / base['MTUM'])
) * 100

prices['blended_sgd'] = prices['blended_usd'] * (prices['USDSGD'] / base['USDSGD'])

weekly = prices.resample('W-FRI').last()
weekly['sma20w'] = weekly['blended_usd'].rolling(20, min_periods=10).mean()

delta = weekly['blended_usd'].diff()
gain  = delta.where(delta > 0, 0).rolling(14, min_periods=7).mean()
loss  = (-delta.where(delta < 0, 0)).rolling(14, min_periods=7).mean()
rs    = gain / loss.replace(0, np.nan)
weekly['rsi14w'] = 100 - (100 / (1 + rs))

prices = prices.join(weekly[['sma20w', 'rsi14w']].ffill())

latest = prices.iloc[-1]
usdsgd = latest['USDSGD']

# ────────────────────────────────────────────────
# Signals
# ────────────────────────────────────────────────
above_trend   = latest['blended_usd'] > latest['sma20w'] if pd.notna(latest['sma20w']) else True
rsi_weekly    = latest['rsi14w'] if pd.notna(latest['rsi14w']) else 50.0
should_trim   = rsi_weekly > 75

# Very approximate drawdown (using blended recent high)
recent_high = prices['blended_sgd'].rolling(63).max().iloc[-1]  # ~3 months
approx_dd   = (recent_high - latest['blended_sgd']) / recent_high if recent_high > 0 else 0
uncle_risk  = approx_dd > 0.12   # warning zone before 15%

# ────────────────────────────────────────────────
# Status box
# ────────────────────────────────────────────────
if not above_trend:
    st.error("🔴 BELOW 20-WEEK SMA → TREND BROKEN → Consider moving to cash / FD")
    invested_multiplier = 0.0
elif should_trim:
    st.warning("🔵 WEEKLY RSI OVERBOUGHT (%.1f) → **TRIM HALF POSITION** recommended" % rsi_weekly)
    invested_multiplier = 0.5
elif uncle_risk:
    st.warning("🟠 DRAW DOWN APPROACHING UNCLE POINT (≈%.1f%%) → monitor closely" % (approx_dd*100))
    invested_multiplier = 1.0
else:
    st.success("🟢 IN TREND – NO TRIM SIGNAL → **HOLD FULL POSITION** (or rebalance to target)")
    invested_multiplier = 1.0

st.caption(f"Weekly RSI(14): **{rsi_weekly:.1f}**  |  Above 20w SMA: **{above_trend}**  |  Approx drawdown: **{approx_dd*100:.1f}%**")

# ────────────────────────────────────────────────
# Calculations
# ────────────────────────────────────────────────
cash_buffer     = total_capital * buffer_pct
invested_target = total_capital * (1 - buffer_pct) * invested_multiplier

weights = {'QQQ': 0.50, 'SPY': 0.20, 'MTUM': 0.30}

# Targets
targets = {}
for etf, w in weights.items():
    price_usd = latest[etf]
    price_sgd = price_usd * usdsgd
    target_sgd = invested_target * w
    target_shares = target_sgd / price_sgd if price_sgd > 0 else 0

    if etf == 'QQQ':
        current_shares = current_qqq_shares
    elif etf == 'SPY':
        current_shares = current_spy_shares
    else:
        current_shares = current_mtum_shares

    delta_shares = target_shares - current_shares

    if abs(delta_shares) < 0.4:
        action = "HOLD"
        action_color = "gray"
    elif delta_shares > 0:
        action = f"BUY {abs(delta_shares):.2f}"
        action_color = "green"
    else:
        action = f"SELL {abs(delta_shares):.2f}"
        action_color = "red"

    targets[etf] = {
        'price_usd': round(price_usd, 2),
        'price_sgd': round(price_sgd, 2),
        'target_sgd': target_sgd,
        'target_shares': round(target_shares, 2),
        'current_shares': current_shares,
        'delta_shares': round(delta_shares, 2),
        'action': action,
        'action_color': action_color
    }

# ────────────────────────────────────────────────
# Display table
# ────────────────────────────────────────────────
st.subheader("Live Prices & Rebalance Targets")

data = []
for etf, info in targets.items():
    data.append({
        "ETF": etf,
        "Price USD": f"${info['price_usd']}",
        "Price SGD": f"S${info['price_sgd']}",
        "Current Shares": info['current_shares'],
        "Target Shares": info['target_shares'],
        "Delta Shares": info['delta_shares'],
        "Action": info['action']
    })

df_display = pd.DataFrame(data)

# Simple styling for Action column
def color_action(val):
    color = targets[val['ETF']]['action_color'] if val['ETF'] in targets else 'black'
    return f'color: {color}; font-weight: bold;'

styled = df_display.style.applymap(color_action, subset=['Action'])

st.dataframe(styled, use_container_width=True, hide_index=True)

# ────────────────────────────────────────────────
# Summary & instructions
# ────────────────────────────────────────────────
st.markdown("---")

col1, col2 = st.columns([3,2])
with col1:
    st.metric("Cash Buffer (always held)", f"S${cash_buffer:,.0f}", f"{buffer_pct*100:.0f}%")
with col2:
    st.metric("Invested Target Today", f"S${invested_target:,.0f}", f"× {invested_multiplier:.1f}")

if st.button("Show Rebalance Instructions"):
    st.info("**Suggested actions today** (after buffer):")
    for row in data:
        if row['Action'].startswith("BUY"):
            st.success(f"**{row['ETF']}**: BUY ≈ **{row['Delta Shares']:.2f}** shares")
        elif row['Action'].startswith("SELL"):
            st.warning(f"**{row['ETF']}**: SELL ≈ **{row['Delta Shares']:.2f}** shares")
        else:
            st.write(f"**{row['ETF']}**: HOLD")

st.caption("Educational tool only – not financial advice. Rebalance quarterly or on major signals. Past performance ≠ future results.")
