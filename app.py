import streamlit as st
import pandas as pd
import time
import re
from datetime import datetime
from tvDatafeed import TvDatafeed, Interval
from io import BytesIO

# --- LOGIN SECTION ---
username = st.text_input("Enter TradingView Username/Email")
password = st.text_input("Enter TradingView Password", type="password")

if st.button("Login"):
    try:
        st.session_state.tv = TvDatafeed(username, password)
        st.success("✅ Logged in successfully!")
    except Exception as e:
        st.error(f"❌ Login failed: {e}")

# --- STREAMLIT UI ---
st.title("📊 Stock Stochastic Trade Analyzer")
st.markdown("Analyze stocks with stochastic, RSI, and weighted scoring.")

symbols_input = st.text_area("Enter stock symbols (comma separated):", "AVALON, BLISSGVS, GALLANTT")
symbols = [s.strip() for s in symbols_input.split(",") if s.strip()]
exchange = st.selectbox("Select Exchange", ["NSE", "BSE"], index=0)

if st.button("Run Analysis"):
    if "tv" not in st.session_state:
        st.error("⚠️ Please login first!")
    else:
        tv = st.session_state.tv
        summary = []
        today = datetime.today().strftime('%Y-%m-%d')

        def sanitize_filename(name):
            return re.sub(r'[^A-Za-z0-9_-]', '_', name)

        def evaluate_targets(df, entries):
            results = {"<=5_days": 0, "5_to_10_days": 0, "10_to_20_days": 0,
                       "20_to_30_days": 0, ">30_days": 0, "Never Hit": 0, "Overlapping": 0}
            open_trade_pending = None
            for _, row in entries.iterrows():
                entry_date = row['datetime']
                entry_close = row['close']
                target_price = round(1.05 * entry_close, 2)
                future_data = df[df['datetime'] > entry_date]
                hit_target = future_data[future_data['high'] >= target_price]

                overlapping = open_trade_pending is not None and entry_date > open_trade_pending
                if overlapping:
                    results["Overlapping"] += 1

                if not hit_target.empty:
                    first_hit_date = hit_target.iloc[0]['datetime']
                    holding_days = (first_hit_date - entry_date).days
                    if holding_days <= 5:
                        results["<=5_days"] += 1
                    elif holding_days <= 10:
                        results["5_to_10_days"] += 1
                    elif holding_days <= 20:
                        results["10_to_20_days"] += 1
                    elif holding_days <= 30:
                        results["20_to_30_days"] += 1
                    else:
                        results[">30_days"] += 1
                else:
                    if open_trade_pending is None:
                        open_trade_pending = entry_date
                    results["Never Hit"] += 1
            return results

        def calculate_weighted_score(results, total_trades):
            if total_trades == 0:
                return 0.0
            def pct(x): return (x / total_trades) * 100
            score = (
                pct(results["<=5_days"]) * 0.50 +
                pct(results["5_to_10_days"]) * 0.25 +
                pct(results["10_to_20_days"]) * 0.125 +
                pct(results["20_to_30_days"]) * 0.075 +
                pct(results[">30_days"]) * 0.05 -
                pct(results["Never Hit"]) * 0.075 -
                pct(results["Overlapping"]) * 0.10
            )
            return round(score, 2)

        progress = st.progress(0)
        for i, symbol in enumerate(symbols, start=1):
            try:
                df = tv.get_hist(symbol=symbol, exchange=exchange,
                                 interval=Interval.in_daily, n_bars=1500)
                if df is None or df.empty:
                    continue

                df['datetime'] = pd.to_datetime(df.index)
                df['low'] = pd.to_numeric(df['low'], errors='coerce')
                df['high'] = pd.to_numeric(df['high'], errors='coerce')
                df['close'] = pd.to_numeric(df['close'], errors='coerce')

                # Indicators
                low_min = df['low'].rolling(window=4).min()
                high_max = df['high'].rolling(window=4).max()
                raw_k = 100 * (df['close'] - low_min) / (high_max - low_min)
                df['%K'] = raw_k.rolling(window=3).mean()
                df['%D'] = df['%K'].rolling(window=3).mean()

                delta = df['close'].diff()
                gain = delta.where(delta > 0, 0)
                loss = -delta.where(delta < 0, 0)
                avg_gain = gain.rolling(window=2).mean()
                avg_loss = loss.rolling(window=2).mean()
                rs = avg_gain / avg_loss
                df['RSI_2'] = 100 - (100 / (1 + rs))
                df['200DMA'] = df['close'].rolling(window=200).mean()

                # Entry condition
                entries = df[(df['%K'] < 20) & (df['%D'] < 20) &
                             (df['RSI_2'] < 15) & (df['close'] > df['200DMA'])].copy()
                total_trades = len(entries)
                results = evaluate_targets(df, entries)

                def pct(x): return (x / total_trades * 100) if total_trades > 0 else 0

                score = calculate_weighted_score(results, total_trades)

                summary.append({
                    "Stock": symbol,
                    "Total Trades": total_trades,
                    "<=5 days %": round(pct(results["<=5_days"]), 2),
                    "5-10 days %": round(pct(results["5_to_10_days"]), 2),
                    "10-20 days %": round(pct(results["10_to_20_days"]), 2),
                    "20-30 days %": round(pct(results["20_to_30_days"]), 2),
                    ">30 days %": round(pct(results[">30_days"]), 2),
                    "Never Hit %": round(pct(results["Never Hit"]), 2),
                    "Overlapping %": round(pct(results["Overlapping"]), 2),
                    "Weighted Score": score
                })

            except Exception as e:
                st.error(f"Error fetching {symbol}: {e}")
            progress.progress(i / len(symbols))

        if summary:
            summary_df = pd.DataFrame(summary).sort_values(by="Weighted Score", ascending=False)
            st.success("✅ Analysis Complete")
            st.dataframe(summary_df, use_container_width=True)

            # ✅ Fix Excel export (BytesIO instead of direct to_excel)
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                summary_df.to_excel(writer, index=False)
            buffer.seek(0)

            st.download_button(
                label="📥 Download Results as Excel",
                data=buffer,
                file_name=f"stock_summary_{today}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
