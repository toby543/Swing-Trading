"""Fetch current Nifty index constituent lists from NSE's public index archive.

Index membership is rebalanced periodically by NSE, so constituent lists are
fetched live (and cached) rather than hardcoded, to avoid silently screening
against a stale universe.
"""

import io
import json
import logging
import os

import pandas as pd
import requests
import streamlit as st

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def _uploaded_cache_path(index_name: str) -> str:
    safe_name = index_name.lower().replace(" ", "_")
    return os.path.join(_DATA_DIR, f"uploaded_{safe_name}.json")

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


def _symbols_from_table(table: pd.DataFrame) -> list:
    """Extract yfinance-style (.NS-suffixed) tickers from an NSE constituent CSV's 'Symbol' column."""
    if "Symbol" not in table.columns:
        return []
    symbols = table["Symbol"].dropna().astype(str).str.strip()
    return sorted(f"{symbol}.NS" for symbol in symbols if symbol)


def parse_constituent_csv(file_obj) -> list:
    """Parse a user-uploaded NSE index constituent CSV (e.g. downloaded from NSE's own site,
    where it isn't blocked) into yfinance-style tickers. Returns [] if the format is unrecognized."""
    try:
        table = pd.read_csv(file_obj)
    except Exception:
        return []
    return _symbols_from_table(table)


def save_uploaded_constituents(index_name: str, tickers: list) -> None:
    """
    Persist an uploaded constituent list to disk, keyed by index name, so it
    survives page refreshes / new browser tabs / the app going idle and
    reconnecting — st.session_state alone does not survive any of those,
    only a live rerun within the same browser connection.
    """
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_uploaded_cache_path(index_name), "w") as f:
        json.dump(tickers, f)


def load_uploaded_constituents(index_name: str) -> list:
    """Load a previously uploaded constituent list from disk, if one was saved."""
    path = _uploaded_cache_path(index_name)
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_nifty_constituents(index_name: str) -> tuple:
    """
    Fetch current constituent tickers for a Nifty index, as yfinance-style
    symbols (NSE symbol + ".NS" suffix), directly from NSE's archive.

    Returns (tickers, error_message). `tickers` is [] on failure, in which
    case `error_message` describes the last failure across every mirror
    tried, so callers can surface something more useful than "it didn't
    work" — and so failures are visible in the deployed app's logs instead
    of being swallowed.

    Note: NSE's WAF blocks requests from most cloud/datacenter IP ranges
    (including Streamlit Community Cloud), regardless of headers or cookies.
    When this fails for that reason, the caller should offer a manual
    upload path (see parse_constituent_csv) rather than retrying.
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

        tickers = _symbols_from_table(table)
        if tickers:
            return tickers, ""

        last_error = f"{url} -> parsed response but found no usable 'Symbol' column"
        logger.warning("Nifty constituent fetch failed: %s", last_error)

    return [], last_error
