"""Backtest a simple top-N momentum rotation strategy over a universe of tickers."""

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def _build_close_matrix(price_data: dict) -> pd.DataFrame:
    """Combine {ticker: OHLCV df} into one wide Close-price DataFrame aligned on date."""
    series = {ticker: df["Close"] for ticker, df in price_data.items() if not df.empty}
    matrix = pd.DataFrame(series).sort_index()
    return matrix.ffill(limit=5)


def run_backtest(
    price_data: dict,
    benchmark_close: pd.Series,
    top_n: int = 5,
    lookback: int = 63,
    rebalance_days: int = 21,
    starting_capital: float = 100_000.0,
) -> dict:
    """
    Simulate an equal-weight, top-N momentum rotation strategy rebalanced every
    `rebalance_days` trading days, ranking by trailing `lookback`-day return.

    Returns a dict with an equity_curve DataFrame (Strategy vs Benchmark),
    summary stats, and the rebalance history (dates + holdings picked).
    """
    prices = _build_close_matrix(price_data)
    if prices.empty or len(prices) <= lookback + rebalance_days:
        return {"equity_curve": pd.DataFrame(), "stats": {}, "history": []}

    dates = prices.index
    daily_returns = prices.pct_change().fillna(0)

    portfolio_value = starting_capital
    equity = []
    history = []
    current_holdings = []

    rebalance_points = list(range(lookback, len(dates), rebalance_days))

    for i, day_idx in enumerate(range(lookback, len(dates))):
        date = dates[day_idx]

        if day_idx in rebalance_points:
            window = prices.iloc[day_idx - lookback: day_idx + 1]
            valid = window.dropna(axis=1)
            if not valid.empty:
                momentum = (valid.iloc[-1] / valid.iloc[0] - 1)
                momentum = momentum[momentum > 0].sort_values(ascending=False)
                current_holdings = list(momentum.head(top_n).index)
            else:
                current_holdings = []
            history.append({"date": date, "holdings": list(current_holdings)})

        if current_holdings:
            day_return = daily_returns.loc[date, current_holdings].mean()
        else:
            day_return = 0.0

        portfolio_value *= (1 + day_return)
        equity.append({"Date": date, "Strategy": portfolio_value})

    equity_df = pd.DataFrame(equity).set_index("Date")

    bench_aligned = benchmark_close.reindex(equity_df.index).ffill()
    bench_returns = bench_aligned.pct_change().fillna(0)
    equity_df["Benchmark"] = starting_capital * (1 + bench_returns).cumprod()

    stats = _compute_stats(equity_df, starting_capital)

    return {"equity_curve": equity_df, "stats": stats, "history": history}


def _compute_stats(equity_df: pd.DataFrame, starting_capital: float) -> dict:
    stats = {}
    n_days = len(equity_df)
    years = n_days / TRADING_DAYS_PER_YEAR if n_days else np.nan

    for col in ["Strategy", "Benchmark"]:
        if col not in equity_df or equity_df[col].empty:
            continue
        final_value = equity_df[col].iloc[-1]
        total_return = final_value / starting_capital - 1
        cagr = (final_value / starting_capital) ** (1 / years) - 1 if years and years > 0 else np.nan

        daily_ret = equity_df[col].pct_change().dropna()
        volatility = daily_ret.std() * np.sqrt(TRADING_DAYS_PER_YEAR)
        sharpe = (daily_ret.mean() * TRADING_DAYS_PER_YEAR) / volatility if volatility else np.nan

        running_max = equity_df[col].cummax()
        drawdown = equity_df[col] / running_max - 1
        max_drawdown = drawdown.min()

        stats[col] = {
            "Total Return %": round(total_return * 100, 2),
            "CAGR %": round(cagr * 100, 2) if pd.notna(cagr) else np.nan,
            "Volatility %": round(volatility * 100, 2),
            "Sharpe": round(sharpe, 2) if pd.notna(sharpe) else np.nan,
            "Max Drawdown %": round(max_drawdown * 100, 2),
        }

    return stats
