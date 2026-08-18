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
from momentum import paper_trading as pt
from momentum import screener
from momentum import signals as sig
from momentum import watchlist as wl

st.set_page_config(page_title="Momentum Swing Trading", page_icon="📈", layout="wide")


@st.cache_data(ttl=3600, show_spinner=False)
def _load_universe_prices(tickers: tuple, period: str):
    return data.fetch_many(tickers, period=period)


def _parse_tickers(raw: str) -> list:
    return [t.strip().upper() for t in raw.replace("\n", ",").split(",") if t.strip()]


def compute_current_signal(df: pd.DataFrame, benchmark_close: pd.Series):
    """Returns (signal_label, momentum_score, vs_benchmark) for a ticker's latest bar."""
    close = df["Close"]
    score = screener.momentum_score(close)
    bench_score = screener.momentum_score(benchmark_close) if benchmark_close is not None else float("nan")
    rel_strength = score - bench_score if pd.notna(bench_score) else float("nan")
    rsi_val = ind.rsi(close, 14).iloc[-1]
    sma_50 = ind.sma(close, 50).iloc[-1]
    sma_200 = ind.sma(close, 200).iloc[-1] if len(close) >= 200 else float("nan")
    last_price = close.iloc[-1]
    uptrend = bool(last_price > sma_50) and (pd.isna(sma_200) or sma_50 > sma_200 or last_price > sma_200)
    macd_bullish = sig.macd_state(close)
    signal = sig.classify_signal(score, rel_strength, rsi_val, uptrend, macd_bullish)
    return signal, score, rel_strength


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

    crossovers = sig.macd_crossovers(close)
    bullish_pts = crossovers[crossovers["Type"] == "Bullish"]
    bearish_pts = crossovers[crossovers["Type"] == "Bearish"]
    if not bullish_pts.empty:
        fig.add_trace(go.Scatter(
            x=bullish_pts["Date"], y=bullish_pts["Price"] * 0.97, mode="markers", name="Bullish crossover",
            marker=dict(symbol="triangle-up", size=10, color="#1a9850"),
        ), row=1, col=1)
    if not bearish_pts.empty:
        fig.add_trace(go.Scatter(
            x=bearish_pts["Date"], y=bearish_pts["Price"] * 1.03, mode="markers", name="Bearish crossover",
            marker=dict(symbol="triangle-down", size=10, color="#d73027"),
        ), row=1, col=1)

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
            # Priority: live NSE fetch (freshest) -> a list the user uploaded
            # this app instance's lifetime (data/uploaded_*.json — wiped by
            # every redeploy, since Streamlit Cloud resets the filesystem on
            # each push) -> the snapshot committed into the repo itself
            # (data/*_fallback.csv — always available, but goes stale between
            # updates) -> only if ALL THREE fail, the full error + upload ask.
            uploaded_cached = nse_indices.load_uploaded_constituents(universe_source)
            bundled_fallback = nse_indices.load_bundled_fallback(universe_source)

            with st.spinner(f"Fetching current {universe_source} constituents from NSE..."):
                universe, fetch_error = nse_indices.fetch_nifty_constituents(universe_source)

            if universe:
                st.caption(f"{len(universe)} {universe_source} constituents loaded live from NSE.")
            elif uploaded_cached:
                universe = uploaded_cached
                st.caption(
                    f"NSE's live feed is blocked from this server; using {len(universe)} previously "
                    f"uploaded {universe_source} tickers."
                )
            elif bundled_fallback:
                universe = bundled_fallback
                st.caption(
                    f"NSE's live feed is blocked from this server; using the {len(universe)}-ticker "
                    f"{universe_source} snapshot bundled with the app (as of {nse_indices.BUNDLED_FALLBACK_DATE})."
                )
            else:
                st.error(f"Couldn't fetch the {universe_source} constituent list, and no fallback is available.")
                st.caption(f"Details: {fetch_error}")

            with st.expander("Upload a fresher list" if universe else "Upload a list (required — no fallback found)"):
                st.caption(
                    "NSE blocks requests from cloud servers (including this app's), but works fine "
                    "from a regular browser. Download the CSV yourself and upload it here to refresh the list."
                )
                for url in nse_indices.NSE_INDEX_CSV_URLS.get(universe_source, []):
                    st.caption(f"→ {url}")

                # Persisted to disk (data/uploaded_*.json), not st.session_state
                # — session_state doesn't survive a page refresh, a new
                # browser tab, or the app reconnecting after going idle.
                uploaded = st.file_uploader(
                    f"Upload {universe_source} constituent CSV", type="csv", key=f"uploader::{universe_source}",
                )
                if uploaded is not None:
                    parsed = nse_indices.parse_constituent_csv(uploaded)
                    if parsed:
                        nse_indices.save_uploaded_constituents(universe_source, parsed)
                        universe = parsed
                        st.success(f"Loaded {len(parsed)} tickers from the uploaded file — saved for future sessions.")
                    else:
                        st.error("Couldn't parse that file — expected an NSE index CSV with a 'Symbol' column.")

                if uploaded_cached and st.button(
                    f"Clear uploaded {universe_source} list", key=f"clear_upload::{universe_source}",
                ):
                    nse_indices.save_uploaded_constituents(universe_source, [])
                    st.rerun()

            if not universe:
                universe = data.DEFAULT_UNIVERSE
                st.caption("Using the default watchlist universe until a valid list is provided.")
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

    tab_screener, tab_watchlist, tab_detail, tab_backtest, tab_simulator = st.tabs(
        ["🔍 Screener", "⭐ Watchlist", "📊 Stock Detail", "🧪 Backtest", "🧾 Trade Simulator"]
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

                st.divider()
                st.caption(
                    "**Shortlist** keeps only the strongest, healthiest-looking setups: outperforming "
                    "the benchmark, RSI in a non-overbought 55–70 zone, within 10% of the 52-week high, "
                    "above-average volume, and a confirmed 50/200 SMA uptrend."
                )
                if st.button("🎯 Shortlist strongest setups"):
                    st.session_state["shortlist_df"] = screener.shortlist_candidates(results)

                shortlist_df = st.session_state.get("shortlist_df")
                if shortlist_df is not None:
                    if shortlist_df.empty:
                        st.info("No candidates currently meet all the shortlist criteria.")
                    else:
                        st.write(f"{len(shortlist_df)} shortlisted.")
                        st.dataframe(shortlist_df, use_container_width=True, hide_index=True)
                        if st.button("➕ Add all shortlisted to watchlist"):
                            for ticker in shortlist_df["Ticker"]:
                                wl.add_ticker(ticker)
                            st.success(f"Added {len(shortlist_df)} tickers to your watchlist.")

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
                current_signal, score, rel_strength = compute_current_signal(df, benchmark_close)

                badge_col1, badge_col2, badge_col3 = st.columns(3)
                badge_col1.metric("Signal", current_signal)
                badge_col2.metric("Momentum Score", f"{score:.2f}" if pd.notna(score) else "—")
                badge_col3.metric("Vs Benchmark", f"{rel_strength:.2f}" if pd.notna(rel_strength) else "—")

                st.plotly_chart(render_chart(chosen, df), use_container_width=True)
                st.caption(
                    "Chart markers show historical MACD bullish (▲) / bearish (▼) crossovers — "
                    "not investment advice, just where this rule-based signal would have flipped."
                )

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

    with tab_simulator:
        st.subheader("🖐️ Manual Paper Trading")
        st.caption(
            "Buy and sell any ticker yourself against a simulated cash balance, at its latest "
            "available price. Weighted-average cost basis; persisted to disk so it survives page "
            "refreshes (not a full app redeploy, same as the watchlist)."
        )

        portfolio = pt.load_portfolio()

        with st.expander("Reset portfolio (erases all trade history)"):
            new_capital = st.number_input(
                "Starting capital", value=float(portfolio["starting_capital"]),
                min_value=1_000.0, step=1_000.0, key="pt_new_capital",
            )
            confirm_reset = st.checkbox(
                "I understand this permanently erases the current trade log and equity history.",
                key="pt_confirm_reset",
            )
            if st.button("🔄 Reset portfolio", disabled=not confirm_reset):
                portfolio = pt.reset_portfolio(float(new_capital))
                st.success(f"Portfolio reset with {new_capital:,.2f} starting capital.")
                st.rerun()

        # Price lookup for mark-to-market: the currently loaded universe,
        # plus a fetch for any held ticker that falls outside it (e.g. the
        # universe selection changed since the position was opened).
        price_lookup = {t: df["Close"].iloc[-1] for t, df in price_data.items() if not df.empty}
        held_tickers = list(portfolio["positions"].keys())
        missing_price_tickers = [t for t in held_tickers if t not in price_lookup]
        if missing_price_tickers:
            fetched = data.fetch_many(tuple(missing_price_tickers), period=period)
            price_lookup.update({t: df["Close"].iloc[-1] for t, df in fetched.items() if not df.empty})

        pt_summary = pt.summary(portfolio, price_lookup)
        pl_stats = pt.realized_pl_stats(portfolio)

        pm1, pm2, pm3, pm4 = st.columns(4)
        pm1.metric("Cash", f"{pt_summary['cash']:,.2f}")
        pm2.metric("Holdings Value", f"{pt_summary['holdings_value']:,.2f}")
        pm3.metric("Total Equity", f"{pt_summary['total_equity']:,.2f}")
        pm4.metric(
            "Total Return",
            f"{pt_summary['total_return_pct']:.2f}%" if pd.notna(pt_summary["total_return_pct"]) else "—",
        )
        pm5, pm6, pm7 = st.columns(3)
        pm5.metric("Realized P&L", f"{pl_stats['total_realized_pl']:+,.2f}")
        pm6.metric("Closed Trades", pl_stats["num_closed"])
        pm7.metric("Win Rate", f"{pl_stats['win_rate_pct']}%" if pd.notna(pl_stats["win_rate_pct"]) else "—")

        equity_history = portfolio["equity_history"]
        if len(equity_history) >= 2:
            eq_df = pd.DataFrame(equity_history)
            pt_eq_fig = go.Figure()
            pt_eq_fig.add_trace(go.Scatter(
                x=list(range(len(eq_df))), y=eq_df["equity"], mode="lines+markers", name="Equity",
            ))
            pt_eq_fig.update_layout(
                height=250, margin=dict(t=20, b=20, l=10, r=10),
                xaxis_title="Trade #", yaxis_title="Total Equity",
            )
            st.plotly_chart(pt_eq_fig, use_container_width=True)

        def _ticker_signal_caption(ticker: str) -> str:
            df = price_data.get(ticker)
            if df is None:
                df = data.fetch_history(ticker, period=period)
            if df is None or df.empty or len(df) < screener.MIN_HISTORY_DAYS:
                return ""
            signal_label, _, _ = compute_current_signal(df, benchmark_close)
            return f"Current signal: {signal_label}"

        trade_tickers = sorted(set(list(price_data.keys()) + wl.load_watchlist() + held_tickers))
        if not trade_tickers:
            st.info("No tickers available to trade yet.")
        else:
            buy_col, sell_col = st.columns(2)

            with buy_col:
                st.markdown("**Buy**")
                buy_ticker = st.selectbox("Ticker to buy", trade_tickers, key="pt_buy_ticker")
                buy_price = price_lookup.get(buy_ticker)
                st.caption(f"Last price: {buy_price:,.2f}" if buy_price else "Price unavailable for this ticker.")
                buy_signal_caption = _ticker_signal_caption(buy_ticker)
                if buy_signal_caption:
                    st.caption(buy_signal_caption)

                buy_mode = st.radio(
                    "Buy by", ["Amount ($)", "Quantity (shares)"], key="pt_buy_mode", horizontal=True,
                )
                if buy_mode == "Amount ($)":
                    buy_amount = st.number_input(
                        "Amount to invest", min_value=0.0, step=100.0,
                        value=float(min(1000.0, portfolio["cash"])), key="pt_buy_amount",
                    )
                    if buy_price:
                        st.caption(f"≈ {buy_amount / buy_price:.4f} shares")
                else:
                    buy_qty = st.number_input(
                        "Shares to buy", min_value=0.0, step=1.0, value=1.0, key="pt_buy_qty",
                    )
                    if buy_price:
                        st.caption(f"≈ {buy_qty * buy_price:,.2f} cost")

                if st.button("🟢 Buy", key="pt_buy_button", use_container_width=True):
                    if buy_mode == "Amount ($)":
                        ok, msg = pt.buy(portfolio, buy_ticker, buy_price, float(buy_amount))
                    else:
                        ok, msg = pt.buy_shares(portfolio, buy_ticker, buy_price, float(buy_qty))
                    (st.success if ok else st.error)(msg)
                    if ok:
                        pt.record_equity_snapshot(portfolio, price_lookup)
                        st.rerun()

            with sell_col:
                st.markdown("**Sell**")
                if not held_tickers:
                    st.caption("No open positions to sell.")
                else:
                    sell_ticker = st.selectbox("Ticker to sell", held_tickers, key="pt_sell_ticker")
                    sell_price = price_lookup.get(sell_ticker)
                    shares_held = portfolio["positions"][sell_ticker]["shares"]
                    st.caption(
                        f"Last price: {sell_price:,.2f} · Held: {shares_held:.4f} shares"
                        if sell_price else f"Held: {shares_held:.4f} shares (no live price)"
                    )
                    sell_signal_caption = _ticker_signal_caption(sell_ticker)
                    if sell_signal_caption:
                        st.caption(sell_signal_caption)
                    sell_shares = st.number_input(
                        "Shares to sell (defaults to your full position)", min_value=0.0,
                        max_value=float(shares_held), value=float(shares_held), key="pt_sell_shares",
                    )
                    if st.button("🔴 Sell", key="pt_sell_button", use_container_width=True):
                        ok, msg = pt.sell(portfolio, sell_ticker, sell_price, float(sell_shares))
                        (st.success if ok else st.error)(msg)
                        if ok:
                            pt.record_equity_snapshot(portfolio, price_lookup)
                            st.rerun()

        if not pt_summary["holdings_df"].empty:
            st.write("**Open Positions**")
            st.dataframe(pt_summary["holdings_df"], use_container_width=True, hide_index=True)

        if portfolio["trades"]:
            st.write("**Trade Log**")
            trades_log_df = pd.DataFrame(portfolio["trades"]).iloc[::-1]
            st.dataframe(trades_log_df, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Download trade log (CSV)",
                data=trades_log_df.to_csv(index=False),
                file_name="paper_trading_log.csv",
                mime="text/csv",
            )


if __name__ == "__main__":
    main()
