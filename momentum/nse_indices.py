"""Fetch current Nifty index constituent lists from NSE's public index archive.

Index membership is rebalanced periodically by NSE, so constituent lists are
fetched live (and cached) rather than hardcoded, to avoid silently screening
against a stale universe.
"""

import io

import pandas as pd
import requests
import streamlit as st

NSE_INDEX_CSV_URLS = {
    "Nifty 200": "https://nsearchives.nseindia.com/content/indices/ind_nifty200list.csv",
    "Nifty 500": "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
}

NSE_BENCHMARK_TICKER = "^NSEI"  # Nifty 50 index

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/json,text/plain,*/*",
    "Referer": "https://www.nseindia.com/",
}


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_nifty_constituents(index_name: str) -> list:
    """
    Fetch current constituent tickers for a Nifty index, as yfinance-style
    symbols (NSE symbol + ".NS" suffix). Returns [] if the live fetch fails
    (e.g. NSE blocking the request) so callers can fall back gracefully.
    """
    url = NSE_INDEX_CSV_URLS.get(index_name)
    if url is None:
        return []

    try:
        session = requests.Session()
        session.headers.update(_HEADERS)
        # NSE requires a warmed-up session cookie from the main site before
        # it will serve the archive CSVs to a fresh client.
        session.get("https://www.nseindia.com", timeout=10)
        response = session.get(url, timeout=10)
        response.raise_for_status()
        table = pd.read_csv(io.StringIO(response.text))
    except Exception:
        return []

    if "Symbol" not in table.columns:
        return []

    symbols = table["Symbol"].dropna().astype(str).str.strip()
    return sorted(f"{symbol}.NS" for symbol in symbols if symbol)
