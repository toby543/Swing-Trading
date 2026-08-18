"""Loads a curated 'nearing breakout' watchlist (stocks close to their 52-week
high) bundled as a dated CSV snapshot, for the ticker-tape banner."""

import os

import pandas as pd

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
BREAKOUT_WATCHLIST_PATH = os.path.join(_DATA_DIR, "breakout_watchlist.csv")
BREAKOUT_WATCHLIST_DATE = "2026-08-18"

_COLUMNS = ["Name", "Ticker", "Sub-Sector", "Market Cap", "Close Price", "RSI (14D)", "% Away From 52W High"]


def load_breakout_watchlist() -> pd.DataFrame:
    """
    Returns the bundled breakout watchlist, sorted by proximity to the
    52-week high (closest first). Empty DataFrame if the file is missing,
    unreadable, or has an unexpected shape.
    """
    if not os.path.exists(BREAKOUT_WATCHLIST_PATH):
        return pd.DataFrame(columns=_COLUMNS)
    try:
        raw = pd.read_csv(BREAKOUT_WATCHLIST_PATH)
    except Exception:
        return pd.DataFrame(columns=_COLUMNS)

    raw = raw.dropna(axis=1, how="all")  # source file has trailing empty columns
    if raw.shape[1] < len(_COLUMNS):
        return pd.DataFrame(columns=_COLUMNS)

    df = raw.iloc[:, :len(_COLUMNS)].copy()
    df.columns = _COLUMNS
    for col in ["Market Cap", "Close Price", "RSI (14D)", "% Away From 52W High"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["Ticker", "Close Price", "% Away From 52W High"])
    return df.sort_values("% Away From 52W High").reset_index(drop=True)
