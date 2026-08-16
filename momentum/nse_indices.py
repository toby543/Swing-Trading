"""Fetch current Nifty index constituent lists from NSE's public index archive.

Index membership is rebalanced periodically by NSE, so constituent lists are
fetched live (and cached) rather than hardcoded, to avoid silently screening
against a stale universe.
"""

import io
import logging

import pandas as pd
import requests
import streamlit as st

logger = logging.getLogger(__name__)

# NSE has served these archive CSVs from more than one hostname over time;
# try each in order and fall through on failure.
NSE_INDEX_CSV_URLS = {
    "Nifty 200": [
        "https://nsearchives.nseindia.com/content/indices/ind_nifty200list.csv",
        "https://archives.nseindia.com/content/indices/ind_nifty200list.csv",
    ],
    "Nifty 500": [
        "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
        "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
    ],
}

NSE_BENCHMARK_TICKER = "^NSEI"  # Nifty 50 index

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Referer": "https://www.nseindia.com/",
}


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_nifty_constituents(index_name: str) -> tuple:
    """
    Fetch current constituent tickers for a Nifty index, as yfinance-style
    symbols (NSE symbol + ".NS" suffix).

    Returns (tickers, error_message). `tickers` is [] on failure, in which
    case `error_message` describes the last failure across every mirror
    tried, so callers can surface something more useful than "it didn't
    work" — and so failures are visible in the deployed app's logs instead
    of being swallowed.
    """
    urls = NSE_INDEX_CSV_URLS.get(index_name, [])
    last_error = "No source URLs configured for this index."

    for url in urls:
        try:
            session = requests.Session()
            session.headers.update(_HEADERS)
            # NSE's WAF generally requires a warmed-up session cookie from
            # the main site before it will serve the archive CSVs.
            session.get("https://www.nseindia.com", timeout=10)
            response = session.get(url, timeout=15)
            response.raise_for_status()
            table = pd.read_csv(io.StringIO(response.text))
        except Exception as exc:
            last_error = f"{url} -> {type(exc).__name__}: {exc}"
            logger.warning("Nifty constituent fetch failed: %s", last_error)
            continue

        if "Symbol" not in table.columns:
            last_error = f"{url} -> unexpected response format (columns: {list(table.columns)[:5]})"
            logger.warning("Nifty constituent fetch failed: %s", last_error)
            continue

        symbols = table["Symbol"].dropna().astype(str).str.strip()
        tickers = sorted(f"{symbol}.NS" for symbol in symbols if symbol)
        if tickers:
            return tickers, ""

        last_error = f"{url} -> parsed response but found no symbols"
        logger.warning("Nifty constituent fetch failed: %s", last_error)

    return [], last_error
