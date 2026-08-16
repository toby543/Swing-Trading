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


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_many(tickers: tuple, period: str = "1y", interval: str = "1d") -> dict:
    """Fetch history for many tickers. Returns {ticker: DataFrame}, skipping empty results."""
    result = {}
    for ticker in tickers:
        df = fetch_history(ticker, period=period, interval=interval)
        if not df.empty:
            result[ticker] = df
    return result
