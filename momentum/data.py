"""Price data fetching, backed by yfinance and cached for the Streamlit session."""

import pandas as pd
import streamlit as st
import yfinance as yf

DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "TSLA", "AMD", "NFLX",
    "CRM", "ADBE", "COST", "PEP", "LIN", "TMO", "UNH", "V", "MA", "JPM",
    "XOM", "CVX", "CAT", "DE", "BA", "LMT", "HD", "LOW", "NKE", "SBUX",
    "PANW", "CRWD", "SNOW", "NOW", "INTU", "ISRG", "REGN", "VRTX", "LLY", "ABBV",
]

BENCHMARK_TICKER = "SPY"


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_history(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """Fetch OHLCV history for a single ticker. Returns an empty DataFrame on failure."""
    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
    except Exception:
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.rename(columns=str.title)
    df.index.name = "Date"
    return df[["Open", "High", "Low", "Close", "Volume"]]


_BATCH_SIZE = 150  # tickers per yf.download call, to keep request URLs/responses reasonably sized


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_many(tickers: tuple, period: str = "1y", interval: str = "1d") -> dict:
    """
    Bulk-fetch history for many tickers using yfinance's batched, multi-threaded
    downloader (far faster than one request per ticker for large universes like
    the Nifty 500). Returns {ticker: DataFrame}, skipping tickers with no data.
    """
    result = {}
    unique_tickers = list(dict.fromkeys(tickers))

    for i in range(0, len(unique_tickers), _BATCH_SIZE):
        batch = unique_tickers[i:i + _BATCH_SIZE]
        try:
            raw = yf.download(
                tickers=batch, period=period, interval=interval,
                auto_adjust=True, group_by="ticker", threads=True, progress=False,
            )
        except Exception:
            continue

        if raw is None or raw.empty:
            continue

        for ticker in batch:
            try:
                df = raw[ticker] if len(batch) > 1 else raw
            except KeyError:
                continue

            df = df.dropna(how="all")
            if df.empty:
                continue

            df = df.rename(columns=str.title)
            df.index.name = "Date"
            cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
            if "Close" not in cols:
                continue
            result[ticker] = df[cols]

    return result
