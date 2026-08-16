"""Simulate individual signal-driven trades on a single ticker, by walking the
same Buy/Sell signal logic used in the screener across its full price history
(rather than only the latest snapshot, as the screener table does)."""

import numpy as np
import pandas as pd

from momentum import indicators as ind
from momentum import screener
from momentum import signals as sig

BUY_SIGNALS = (sig.STRONG_BUY, sig.BUY)
SELL_SIGNALS = (sig.SELL, sig.STRONG_SELL)


def _rolling_momentum_score(close: pd.Series) -> pd.Series:
    """Vectorized version of screener.momentum_score, computed at every bar."""
    weighted_sum = pd.Series(0.0, index=close.index)
    weight_used = pd.Series(0.0, index=close.index)
    for lookback, weight in screener.MOMENTUM_LOOKBACKS:
        roc = close.pct_change(periods=lookback) * 100
        valid = roc.notna()
        weighted_sum = weighted_sum.add(roc.where(valid, 0.0) * weight, fill_value=0.0)
        weight_used = weight_used.add(valid.astype(float) * weight, fill_value=0.0)
    return weighted_sum / weight_used.replace(0.0, np.nan)


def rolling_signals(close: pd.Series, benchmark_close: pd.Series = None) -> pd.Series:
    """Compute the Strong Buy/Buy/Hold/Sell/Strong Sell signal at every bar in `close`'s history."""
    momentum = _rolling_momentum_score(close)

    if benchmark_close is not None and not benchmark_close.empty:
        bench_momentum = _rolling_momentum_score(benchmark_close).reindex(close.index).ffill()
        vs_benchmark = momentum - bench_momentum
    else:
        vs_benchmark = pd.Series(np.nan, index=close.index)

    rsi_series = ind.rsi(close, 14)
    sma_50 = ind.sma(close, 50)
    sma_200 = ind.sma(close, 200)
    uptrend = (close > sma_50) & (sma_200.isna() | (sma_50 > sma_200) | (close > sma_200))

    macd_df = ind.macd(close)
    macd_bullish = macd_df["macd"] > macd_df["signal"]

    signal_values = [
        sig.classify_signal(
            momentum.iloc[i], vs_benchmark.iloc[i], rsi_series.iloc[i],
            bool(uptrend.iloc[i]), bool(macd_bullish.iloc[i]) if pd.notna(macd_bullish.iloc[i]) else False,
        )
        for i in range(len(close))
    ]
    return pd.Series(signal_values, index=close.index)


def simulate_trades(
    df: pd.DataFrame,
    benchmark_close: pd.Series = None,
    starting_capital: float = 100_000.0,
) -> dict:
    """
    Walk a ticker's price history day by day: enter (with all available capital)
    the session after a Buy/Strong Buy signal fires while flat, exit the session
    after a Sell/Strong Sell signal fires while holding. One position at a time.

    Entries/exits execute at the *next* bar's open (not the signal bar's close)
    to avoid look-ahead bias. Returns {"trades": DataFrame, "equity_curve": DataFrame, "stats": dict}.
    """
    close = df["Close"]
    open_ = df["Open"]
    signal_series = rolling_signals(close, benchmark_close)

    trades = []
    capital = starting_capital
    equity_points = []

    in_position = False
    entry_date = entry_price = shares = None

    dates = df.index
    n = len(dates)

    for i in range(n):
        # Mark-to-market at today's close, using the position held coming
        # into today (i.e. before today's signal is evaluated below) — an
        # entry/exit decided on day i only executes at day i+1's open, so it
        # must not affect today's equity value.
        equity_points.append({
            "Date": dates[i],
            "Equity": shares * close.iloc[i] if in_position else capital,
        })

        if i == n - 1:
            break  # no next bar left to execute a new signal at

        signal = signal_series.iloc[i]
        next_day = dates[i + 1]

        if not in_position and signal in BUY_SIGNALS:
            entry_date = next_day
            entry_price = open_.iloc[i + 1]
            shares = capital / entry_price
            in_position = True
        elif in_position and signal in SELL_SIGNALS:
            exit_date = next_day
            exit_price = open_.iloc[i + 1]
            capital = shares * exit_price
            trades.append({
                "Entry Date": entry_date, "Entry Price": round(entry_price, 2),
                "Exit Date": exit_date, "Exit Price": round(exit_price, 2),
                "P&L %": round((exit_price / entry_price - 1) * 100, 2),
                "Holding Days": (exit_date - entry_date).days,
                "Status": "Closed",
            })
            in_position = False
            entry_date = entry_price = shares = None

    # Mark-to-market a still-open position at the last available close.
    last_date, last_close = dates[-1], close.iloc[-1]
    if in_position:
        trades.append({
            "Entry Date": entry_date, "Entry Price": round(entry_price, 2),
            "Exit Date": None, "Exit Price": None,
            "P&L %": round((last_close / entry_price - 1) * 100, 2),
            "Holding Days": (last_date - entry_date).days,
            "Status": "Open",
        })
        final_capital = shares * last_close
    else:
        final_capital = capital

    trades_df = pd.DataFrame(trades, columns=[
        "Entry Date", "Entry Price", "Exit Date", "Exit Price", "P&L %", "Holding Days", "Status",
    ])
    equity_curve = pd.DataFrame(equity_points).set_index("Date")

    stats = _compute_stats(trades_df, starting_capital, final_capital)
    return {"trades": trades_df, "equity_curve": equity_curve, "stats": stats}


def _compute_stats(trades_df: pd.DataFrame, starting_capital: float, final_capital: float) -> dict:
    closed = trades_df[trades_df["Status"] == "Closed"]
    wins = closed[closed["P&L %"] > 0]

    return {
        "Total Trades": len(trades_df),
        "Closed Trades": len(closed),
        "Win Rate %": round(len(wins) / len(closed) * 100, 1) if len(closed) else np.nan,
        "Avg P&L % (closed)": round(closed["P&L %"].mean(), 2) if len(closed) else np.nan,
        "Avg Holding Days": round(trades_df["Holding Days"].mean(), 1) if len(trades_df) else np.nan,
        "Total Return %": round((final_capital / starting_capital - 1) * 100, 2),
        "Final Capital": round(final_capital, 2),
    }
