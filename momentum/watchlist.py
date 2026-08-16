"""Simple JSON-backed watchlist of tickers, persisted to disk between sessions."""

import json
import os

WATCHLIST_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "watchlist.json")


def _ensure_dir() -> None:
    os.makedirs(os.path.dirname(WATCHLIST_PATH), exist_ok=True)


def load_watchlist() -> list:
    if not os.path.exists(WATCHLIST_PATH):
        return []
    try:
        with open(WATCHLIST_PATH, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    return sorted(set(data))


def save_watchlist(tickers: list) -> None:
    _ensure_dir()
    with open(WATCHLIST_PATH, "w") as f:
        json.dump(sorted(set(t.upper() for t in tickers)), f, indent=2)


def add_ticker(ticker: str) -> list:
    tickers = load_watchlist()
    ticker = ticker.strip().upper()
    if ticker and ticker not in tickers:
        tickers.append(ticker)
        save_watchlist(tickers)
    return sorted(set(tickers))


def remove_ticker(ticker: str) -> list:
    tickers = load_watchlist()
    ticker = ticker.strip().upper()
    tickers = [t for t in tickers if t != ticker]
    save_watchlist(tickers)
    return tickers
