"""Rule-based Strong Buy/Buy/Hold/Sell/Strong Sell signal classification and
MACD crossover markers, built from the same indicators used elsewhere in the app."""

import pandas as pd

from momentum import indicators as ind

STRONG_BUY = "🟢 Strong Buy"
BUY = "🟢 Buy"
HOLD = "🟡 Hold"
SELL = "🔴 Sell"
STRONG_SELL = "🔴 Strong Sell"

# RSI zone treated as "healthy" (bullish vote) vs. extended/weak (bearish vote).
_RSI_BULLISH_RANGE = (45.0, 75.0)
_RSI_BEARISH_LOW = 35.0
_RSI_BEARISH_HIGH = 80.0


def macd_state(close: pd.Series) -> bool:
    """True if MACD line is currently above its signal line (bullish state)."""
    macd_df = ind.macd(close)
    if macd_df.empty or pd.isna(macd_df["macd"].iloc[-1]) or pd.isna(macd_df["signal"].iloc[-1]):
        return False
    return bool(macd_df["macd"].iloc[-1] > macd_df["signal"].iloc[-1])


def classify_signal(
    momentum_score: float,
    vs_benchmark: float,
    rsi_val: float,
    above_trend: bool,
    macd_bullish: bool,
) -> str:
    """
    Combine momentum score, relative strength, RSI zone, trend, and MACD
    state into a Strong Buy / Buy / Hold / Sell / Strong Sell signal.

    Momentum direction is the primary signal (this is a momentum strategy):
    a stock with negative momentum is capped at Sell/Strong Sell regardless
    of the other votes, and positive momentum is required to reach Buy or
    Strong Buy. The other four factors act as a conviction score on top of
    that direction — more agreement pushes toward the "Strong" tier.
    """
    if pd.isna(momentum_score):
        return HOLD

    bullish_votes = 1 if momentum_score > 0 else 0
    bearish_votes = 1 if momentum_score <= 0 else 0

    if pd.notna(vs_benchmark):
        if vs_benchmark > 0:
            bullish_votes += 1
        else:
            bearish_votes += 1

    if pd.notna(rsi_val):
        if _RSI_BULLISH_RANGE[0] <= rsi_val <= _RSI_BULLISH_RANGE[1]:
            bullish_votes += 1
        elif rsi_val > _RSI_BEARISH_HIGH or rsi_val < _RSI_BEARISH_LOW:
            bearish_votes += 1

    if above_trend:
        bullish_votes += 1
    else:
        bearish_votes += 1

    if macd_bullish:
        bullish_votes += 1
    else:
        bearish_votes += 1

    net_score = bullish_votes - bearish_votes

    if momentum_score <= 0:
        return STRONG_SELL if net_score <= -3 else SELL

    if net_score >= 4:
        return STRONG_BUY
    if net_score >= 1:
        return BUY
    if net_score == 0:
        return HOLD
    return SELL


def macd_crossovers(close: pd.Series) -> pd.DataFrame:
    """
    Historical MACD bullish/bearish crossover points, for marking buy/sell
    signals on a price chart. Returns columns: Date, Price, Type ("Bullish"/"Bearish").
    """
    macd_df = ind.macd(close)
    diff = macd_df["macd"] - macd_df["signal"]
    sign = diff.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    sign_change = sign.diff()

    points = []
    for date, change in sign_change.items():
        if pd.isna(change) or change == 0 or date not in close.index:
            continue
        points.append({
            "Date": date,
            "Price": close.loc[date],
            "Type": "Bullish" if change > 0 else "Bearish",
        })
    return pd.DataFrame(points, columns=["Date", "Price", "Type"])
