"""Momentum Swing Trading — a Streamlit app for screening, tracking, and backtesting
momentum-based swing trade candidates."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from momentum import backtest as bt
from momentum import data
from momentum import indicators as ind
from momentum import nse_indices
from momentum import screener
from momentum import watchlist as wl

st.set_page_config(page_title="Momentum Swing Trading", page_icon="📈", layout="wide")


@st.cache_data(ttl=3600, show_spinner=False)
def _load_universe_prices(tickers: tuple, period: str):
    return data.fetch_many(tickers, period=period)


def _parse_tickers(raw: str) -> list:
    return [t.strip().upper() for t in raw.replace("\n", ",").split(",") if t.strip()]


def render_chart(ticker: str, df: pd.DataFrame) -> go.Figure:
    close = df["Close"]
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        row_heights=[0.55, 0.2, 0.25],
        subplot_titles=(f"{ticker} — Price", "RSI (14)", "MACD"),
    )

    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        name="Price", showlegend=False,
    ), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=ind.sma(close, 50), name="SMA 50",
                              line=dict(width=1.3)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=ind.sma(close, 200), name="SMA 200",
                              line=dict(width=1.3)), row=1, col=1)

    rsi_series = ind.rsi(close, 14)
    fig.add_trace(go.Scatter(x=df.index, y=rsi_series, name="RSI", showlegend=False,
                              line=dict(color="#c98a2c")), row=2, col=1)
    fig.add_hline(y=70, line_dash="dot", line_color="gray", row=2, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="gray", row=2, col=1)

    macd_df = ind.macd(close)
    fig.add_trace(go.Scatter(x=df.index, y=macd_df["macd"], name="MACD",
                              line=dict(color="#2c6fc9")), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=macd_df["signal"], name="Signal",
                              line=dict(color="#c92c4f")), row=3, col=1)
    fig.add_trace(go.Bar(x=df.index, y=macd_df["histogram"], name="Histogram",
                          marker_color="lightgray", showlegend=False), row=3, col=1)

    fig.update_layout(height=750, xaxis_rangeslider_visible=False,
                       margin=dict(t=40, b=20, l=10, r=10), legend=dict(orientation="h"))
    return fig


def main():
    st.title("📈 Momentum Swing Trading")
    st.caption("Screen for momentum leaders, track a watchlist, inspect charts, and backtest a rotation strategy.")

    with st.sidebar:
        st.header("Universe")
        universe_source = st.radio(
            "Ticker universe",
            ["Default watchlist universe", "Nifty 200", "Nifty 500", "Custom list"],
            index=0,
        )

        is_nse_universe = universe_source in ("Nifty 200", "Nifty 500")

        if universe_source == "Custom list":
            raw = st.text_area("Tickers (comma or newline separated)", value=", ".join(data.DEFAULT_UNIVERSE))
            universe = _parse_tickers(raw)
        elif is_nse_universe:
            with st.spinner(f"Fetching current {universe_source} constituents from NSE..."):
                universe = nse_indices.fetch_nifty_constituents(universe_source)
            if not universe:
                st.error(
                    f"Couldn't fetch the {universe_source} constituent list from NSE right now "
                    "(the live feed may be unreachable or temporarily blocking requests). "
                    "Falling back to the default watchlist universe."
                )
                universe = data.DEFAULT_UNIVERSE
            else:
                st.caption(f"{len(universe)} {universe_source} constituents loaded.")
        else:
            universe = data.DEFAULT_UNIVERSE

        period = st.selectbox("History window", ["6mo", "1y", "2y"], index=1)
        default_benchmark = nse_indices.NSE_BENCHMARK_TICKER if is_nse_universe else data.BENCHMARK_TICKER
        benchmark_ticker = st.text_input("Benchmark", value=default_benchmark)

        st.divider()
        st.header("Screener filters")
        price_currency = "₹" if is_nse_universe else "$"
        min_price = st.number_input(f"Min price ({price_currency})", value=5.0, min_value=0.0, step=1.0)
        min_avg_volume = st.number_input("Min avg volume (20d)", value=200_000, min_value=0, step=50_000)
        rsi_range = st.slider("RSI (14) range", 0, 100, (40, 85))
        require_uptrend = st.checkbox("Require price above 50/200 SMA uptrend", value=True)

    tab_screener, tab_watchlist, tab_detail, tab_backtest = st.tabs(
        ["🔍 Screener", "⭐ Watchlist", "📊 Stock Detail", "🧪 Backtest"]
    )

    with st.spinner("Loading price data..."):
        price_data = _load_universe_prices(tuple(sorted(set(universe))), period)
        benchmark_df = data.fetch_history(benchmark_ticker, period=period)

    benchmark_close = benchmark_df["Close"] if not benchmark_df.empty else None

    with tab_screener:
        st.subheader("Momentum Screener")
        if not price_data:
            st.warning("No price data loaded — check your ticker list or try again.")
        else:
            results = screener.screen_universe(
                price_data, benchmark_close,
                min_price=min_price, min_avg_volume=min_avg_volume,
                rsi_min=rsi_range[0], rsi_max=rsi_range[1],
                require_uptrend=require_uptrend,
            )
            st.write(f"{len(results)} candidates ranked by momentum score (weighted 1/3/6/12-month rate of change).")
            st.dataframe(results, use_container_width=True, hide_index=True)

            if not results.empty:
                add_col1, add_col2 = st.columns([3, 1])
                pick = add_col1.selectbox("Add a candidate to your watchlist", results["Ticker"].tolist())
                if add_col2.button("➕ Add to watchlist", use_container_width=True):
                    wl.add_ticker(pick)
                    st.success(f"Added {pick} to watchlist.")

    with tab_watchlist:
        st.subheader("Watchlist")
        current = wl.load_watchlist()
        if not current:
            st.info("Your watchlist is empty. Add tickers from the Screener tab, or below.")
        else:
            watch_prices = {t: p for t, p in price_data.items() if t in current}
            missing = [t for t in current if t not in watch_prices]
            if missing:
                watch_prices.update(data.fetch_many(tuple(missing), period=period))

            if watch_prices:
                watch_table = screener.screen_universe(
                    watch_prices, benchmark_close,
                    min_price=0, min_avg_volume=0, rsi_min=0, rsi_max=100, require_uptrend=False,
                )
                st.dataframe(watch_table, use_container_width=True, hide_index=True)

            remove_col1, remove_col2 = st.columns([3, 1])
            remove_pick = remove_col1.selectbox("Remove a ticker", current)
            if remove_col2.button("🗑️ Remove", use_container_width=True):
                wl.remove_ticker(remove_pick)
                st.rerun()

        st.divider()
        manual = st.text_input("Add a ticker manually")
        if st.button("Add") and manual:
            wl.add_ticker(manual)
            st.rerun()

    with tab_detail:
        st.subheader("Stock Detail")
        all_tickers = sorted(set(list(price_data.keys()) + wl.load_watchlist()))
        if not all_tickers:
            st.info("No tickers available yet.")
        else:
            chosen = st.selectbox("Ticker", all_tickers)
            df = price_data.get(chosen)
            if df is None:
                df = data.fetch_history(chosen, period=period)
            if df is None or df.empty:
                st.warning(f"No data for {chosen}.")
            else:
                st.plotly_chart(render_chart(chosen, df), use_container_width=True)

    with tab_backtest:
        st.subheader("Momentum Rotation Backtest")
        st.caption("Equal-weight top-N momentum rotation, rebalanced periodically, vs. buy-and-hold benchmark.")

        c1, c2, c3, c4 = st.columns(4)
        top_n = c1.number_input("Top N holdings", value=5, min_value=1, max_value=20)
        lookback = c2.number_input("Momentum lookback (days)", value=63, min_value=10, max_value=252)
        rebalance_days = c3.number_input("Rebalance every (days)", value=21, min_value=5, max_value=126)
        starting_capital = c4.number_input("Starting capital ($)", value=100_000, min_value=1_000, step=1_000)

        if st.button("Run backtest", type="primary"):
            if not price_data or benchmark_close is None:
                st.warning("Need price data and a benchmark to backtest.")
            else:
                with st.spinner("Running backtest..."):
                    result = bt.run_backtest(
                        price_data, benchmark_close,
                        top_n=int(top_n), lookback=int(lookback),
                        rebalance_days=int(rebalance_days), starting_capital=float(starting_capital),
                    )

                equity_curve = result["equity_curve"]
                if equity_curve.empty:
                    st.warning("Not enough history to run this backtest — try a longer history window.")
                else:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=equity_curve.index, y=equity_curve["Strategy"], name="Strategy"))
                    fig.add_trace(go.Scatter(x=equity_curve.index, y=equity_curve["Benchmark"], name="Benchmark"))
                    fig.update_layout(height=450, margin=dict(t=20, b=20, l=10, r=10),
                                       legend=dict(orientation="h"))
                    st.plotly_chart(fig, use_container_width=True)

                    stats_df = pd.DataFrame(result["stats"]).T
                    st.dataframe(stats_df, use_container_width=True)

                    with st.expander("Rebalance history"):
                        for entry in result["history"]:
                            st.write(f"**{entry['date'].date()}**: {', '.join(entry['holdings']) or '(cash)'}")


if __name__ == "__main__":
    main()
