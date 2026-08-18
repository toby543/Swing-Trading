"""Manual paper-trading portfolio: buy/sell against a simulated cash balance,
tracked with weighted-average cost basis and persisted to disk between reruns."""

import json
import os
from datetime import date

import numpy as np
import pandas as pd

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
PORTFOLIO_PATH = os.path.join(_DATA_DIR, "paper_portfolio.json")

DEFAULT_STARTING_CAPITAL = 100_000.0


def _new_portfolio(starting_capital: float) -> dict:
    return {
        "starting_capital": starting_capital,
        "cash": starting_capital,
        "positions": {},  # ticker -> {"shares": float, "avg_price": float}
        "trades": [],  # {"date", "ticker", "action", "shares", "price", "value", "realized_pl"}
    }


def load_portfolio() -> dict:
    if not os.path.exists(PORTFOLIO_PATH):
        return _new_portfolio(DEFAULT_STARTING_CAPITAL)
    try:
        with open(PORTFOLIO_PATH) as f:
            portfolio = json.load(f)
    except (json.JSONDecodeError, OSError):
        return _new_portfolio(DEFAULT_STARTING_CAPITAL)
    portfolio.setdefault("positions", {})
    portfolio.setdefault("trades", [])
    return portfolio


def save_portfolio(portfolio: dict) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(PORTFOLIO_PATH, "w") as f:
        json.dump(portfolio, f, indent=2)


def reset_portfolio(starting_capital: float) -> dict:
    portfolio = _new_portfolio(starting_capital)
    save_portfolio(portfolio)
    return portfolio


def buy(portfolio: dict, ticker: str, price: float, amount: float) -> tuple:
    """Spend `amount` of cash buying `ticker` at `price`. Returns (success, message)."""
    if price is None or pd.isna(price) or price <= 0:
        return False, f"No valid price available for {ticker}."
    if amount <= 0:
        return False, "Enter a positive amount to invest."
    if amount > portfolio["cash"] + 1e-6:
        return False, f"Only ${portfolio['cash']:,.2f} cash available."

    shares_bought = amount / price
    position = portfolio["positions"].get(ticker, {"shares": 0.0, "avg_price": 0.0})
    total_shares = position["shares"] + shares_bought
    position["avg_price"] = (
        position["shares"] * position["avg_price"] + shares_bought * price
    ) / total_shares
    position["shares"] = total_shares
    portfolio["positions"][ticker] = position
    portfolio["cash"] -= amount

    portfolio["trades"].append({
        "date": str(date.today()), "ticker": ticker, "action": "BUY",
        "shares": round(shares_bought, 4), "price": round(price, 2), "value": round(amount, 2),
        "realized_pl": None,
    })
    save_portfolio(portfolio)
    return True, f"Bought {shares_bought:.4f} shares of {ticker} at {price:.2f}."


def sell(portfolio: dict, ticker: str, price: float, shares: float) -> tuple:
    """Sell `shares` of `ticker` at `price`. Returns (success, message)."""
    if price is None or pd.isna(price) or price <= 0:
        return False, f"No valid price available for {ticker}."
    position = portfolio["positions"].get(ticker)
    if not position or position["shares"] <= 0:
        return False, f"No open position in {ticker}."
    if shares <= 0:
        return False, "Enter a positive number of shares to sell."
    if shares > position["shares"] + 1e-6:
        return False, f"Only {position['shares']:.4f} shares of {ticker} held."

    proceeds = shares * price
    realized_pl = shares * (price - position["avg_price"])
    position["shares"] -= shares
    if position["shares"] <= 1e-9:
        del portfolio["positions"][ticker]
    else:
        portfolio["positions"][ticker] = position
    portfolio["cash"] += proceeds

    portfolio["trades"].append({
        "date": str(date.today()), "ticker": ticker, "action": "SELL",
        "shares": round(shares, 4), "price": round(price, 2), "value": round(proceeds, 2),
        "realized_pl": round(realized_pl, 2),
    })
    save_portfolio(portfolio)
    return True, f"Sold {shares:.4f} shares of {ticker} at {price:.2f} (realized P&L: {realized_pl:+.2f})."


def summary(portfolio: dict, price_lookup: dict) -> dict:
    """
    price_lookup: {ticker: last_price}. Returns cash/holdings/equity totals plus
    a holdings DataFrame (Ticker, Shares, Avg Cost, Last Price, Market Value, Unrealized P&L, P&L %).
    """
    rows = []
    holdings_value = 0.0
    for ticker, pos in portfolio["positions"].items():
        last_price = price_lookup.get(ticker)
        market_value = pos["shares"] * last_price if last_price else np.nan
        if pd.notna(market_value):
            holdings_value += market_value
        unrealized_pl = (last_price - pos["avg_price"]) * pos["shares"] if last_price else np.nan
        pl_pct = (last_price / pos["avg_price"] - 1) * 100 if last_price and pos["avg_price"] else np.nan
        rows.append({
            "Ticker": ticker,
            "Shares": round(pos["shares"], 4),
            "Avg Cost": round(pos["avg_price"], 2),
            "Last Price": round(last_price, 2) if last_price else np.nan,
            "Market Value": round(market_value, 2) if pd.notna(market_value) else np.nan,
            "Unrealized P&L": round(unrealized_pl, 2) if pd.notna(unrealized_pl) else np.nan,
            "P&L %": round(pl_pct, 2) if pd.notna(pl_pct) else np.nan,
        })

    holdings_df = pd.DataFrame(rows, columns=[
        "Ticker", "Shares", "Avg Cost", "Last Price", "Market Value", "Unrealized P&L", "P&L %",
    ])

    total_equity = portfolio["cash"] + holdings_value
    starting_capital = portfolio["starting_capital"]

    return {
        "cash": portfolio["cash"],
        "holdings_value": holdings_value,
        "total_equity": total_equity,
        "total_return_pct": (total_equity / starting_capital - 1) * 100 if starting_capital else np.nan,
        "holdings_df": holdings_df,
    }
