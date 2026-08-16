"""Rank a universe of tickers by momentum strength for swing trade candidates."""

import numpy as np
import pandas as pd

from momentum import indicators as ind

# (lookback in trading days, weight in the composite score)
MOMENTUM_LOOKBACKS = [(21, 0.15), (63, 0.35), (126, 0.30), (252, 0.20)]

MIN_HISTORY_DAYS = 60


def _momentum_score(close: pd.Series) -> float:
    """Weighted average ROC across multiple lookback windows; NaN if not enough history."""
    weighted_sum = 0.0
    weight_used = 0.0
    for lookback, weight in MOMENTUM_LOOKBACKS:
        if len(close) <= lookback:
            continue
        roc = (close.iloc[-1] / close.iloc[-1 - lookback] - 1) * 100
        weighted_sum += roc * weight
        weight_used += weight
    if weight_used == 0:
        return np.nan
    return weighted_sum / weight_used


def screen_universe(
    price_data: dict,
    benchmark_close: pd.Series,
    min_price: float = 5.0,
    min_avg_volume: float = 200_000,
    rsi_min: float = 40.0,
    rsi_max: float = 85.0,
    require_uptrend: bool = True,
) -> pd.DataFrame:
    """
    Build a ranked momentum table from raw OHLCV data.

    price_data: {ticker: DataFrame with Open/High/Low/Close/Volume}
    benchmark_close: Close series for the benchmark (e.g. SPY), used for relative strength.
    """
    rows = []

    bench_score = _momentum_score(benchmark_close) if benchmark_close is not None else np.nan

    for ticker, df in price_data.items():
        if len(df) < MIN_HISTORY_DAYS:
            continue

        close = df["Close"]
        volume = df["Volume"]
        last_price = close.iloc[-1]
        avg_volume = volume.tail(20).mean()

        if last_price < min_price or avg_volume < min_avg_volume:
            continue

        sma_50 = ind.sma(close, 50).iloc[-1]
        sma_200 = ind.sma(close, 200).iloc[-1] if len(close) >= 200 else np.nan
        uptrend = bool(last_price > sma_50) and (pd.isna(sma_200) or sma_50 > sma_200 or last_price > sma_200)

        if require_uptrend and not uptrend:
            continue

        rsi_val = ind.rsi(close, 14).iloc[-1]
        if pd.notna(rsi_val) and not (rsi_min <= rsi_val <= rsi_max):
            continue

        score = _momentum_score(close)
        if pd.isna(score):
            continue

        rel_strength = score - bench_score if pd.notna(bench_score) else np.nan
        off_high = ind.percent_off_high(close, 252).iloc[-1]
        vol_surge = ind.volume_surge_ratio(volume, 20).iloc[-1]

        rows.append({
            "Ticker": ticker,
            "Price": round(last_price, 2),
            "Momentum Score": round(score, 2),
            "Vs Benchmark": round(rel_strength, 2) if pd.notna(rel_strength) else np.nan,
            "RSI (14)": round(rsi_val, 1) if pd.notna(rsi_val) else np.nan,
            "% Off 52w High": round(off_high, 2),
            "Volume Surge": round(vol_surge, 2) if pd.notna(vol_surge) else np.nan,
            "Above 50/200 SMA": uptrend,
            "Avg Volume (20d)": int(avg_volume),
        })

    if not rows:
        return pd.DataFrame(columns=[
            "Ticker", "Price", "Momentum Score", "Vs Benchmark", "RSI (14)",
            "% Off 52w High", "Volume Surge", "Above 50/200 SMA", "Avg Volume (20d)",
        ])

    result = pd.DataFrame(rows).sort_values("Momentum Score", ascending=False).reset_index(drop=True)
    result.insert(0, "Rank", np.arange(1, len(result) + 1))
    return result


# Shortlist thresholds, applied on top of an already-screened table:
#   - genuinely outperforming the benchmark, not just riding a broad rally
#   - RSI in a "healthy" zone rather than already extended/overbought
#   - near its 52-week high (breakout-style setup, not a deep recovery)
#   - above-average recent volume, confirming the move is real
#   - confirmed uptrend (price above 50/200 SMA)
SHORTLIST_RSI_RANGE = (55.0, 70.0)
SHORTLIST_MIN_VS_BENCHMARK = 0.0
SHORTLIST_MAX_PCT_OFF_HIGH = -10.0
SHORTLIST_MIN_VOLUME_SURGE = 1.0


def shortlist_candidates(
    results: pd.DataFrame,
    rsi_range: tuple = SHORTLIST_RSI_RANGE,
    min_vs_benchmark: float = SHORTLIST_MIN_VS_BENCHMARK,
    max_pct_off_high: float = SHORTLIST_MAX_PCT_OFF_HIGH,
    min_volume_surge: float = SHORTLIST_MIN_VOLUME_SURGE,
) -> pd.DataFrame:
    """
    Apply a stricter secondary filter to already-screened results, keeping
    only the strongest, healthiest-looking setups rather than everything
    that merely passed the base screener filters. Rows missing a required
    metric (e.g. no benchmark data) are excluded rather than let through.
    """
    if results.empty:
        return results

    mask = (
        (results["Vs Benchmark"].fillna(-np.inf) >= min_vs_benchmark)
        & results["RSI (14)"].between(rsi_range[0], rsi_range[1])
        & (results["% Off 52w High"] >= max_pct_off_high)
        & (results["Volume Surge"].fillna(0) >= min_volume_surge)
        & (results["Above 50/200 SMA"])
    )
    return results[mask].reset_index(drop=True)
