"""Technical indicators used for momentum swing trading analysis."""

import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    result = result.where(avg_loss != 0, 100)  # no losses in window -> RSI 100
    return result.mask(avg_gain.isna())  # not enough history yet -> NaN


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "histogram": histogram})


def rate_of_change(series: pd.Series, periods: int) -> pd.Series:
    """Percentage change over `periods` bars."""
    return series.pct_change(periods=periods) * 100


def average_true_range(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def percent_off_high(series: pd.Series, window: int) -> pd.Series:
    """How far (in %, negative = below) the latest close is from the rolling high."""
    rolling_high = series.rolling(window=window, min_periods=1).max()
    return (series / rolling_high - 1) * 100


def relative_strength_line(series: pd.Series, benchmark: pd.Series) -> pd.Series:
    """Simple price ratio of a stock to a benchmark, aligned by index."""
    aligned = pd.concat([series, benchmark], axis=1, join="inner")
    aligned.columns = ["series", "benchmark"]
    return aligned["series"] / aligned["benchmark"]


def volume_surge_ratio(volume: pd.Series, window: int = 20) -> pd.Series:
    """Latest volume relative to its trailing average (>1 means above-average activity)."""
    avg_vol = volume.rolling(window=window, min_periods=window).mean()
    return volume / avg_vol
