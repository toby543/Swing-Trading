# Momentum Swing Trading

A Streamlit app for finding, tracking, and backtesting momentum-based swing trade candidates.

## Features

- **Screener** — ranks a ticker universe by a composite momentum score (weighted 1/3/6/12-month
  rate of change), with filters for price, average volume, RSI range, and trend (price above
  50/200-day SMA).
- **Watchlist** — save candidates from the screener and track their latest momentum stats;
  persisted locally to `data/watchlist.json`.
- **Stock Detail** — candlestick chart with 50/200-day SMAs, RSI(14), and MACD for any ticker.
- **Backtest** — simulates an equal-weight, top-N momentum rotation strategy rebalanced on a
  fixed schedule, plotted against a buy-and-hold benchmark, with CAGR / volatility / Sharpe /
  max drawdown stats.

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploying to Streamlit Community Cloud

1. Push this repo to GitHub.
2. On [share.streamlit.io](https://share.streamlit.io), create a new app pointing at this repo,
   branch `main`, and entrypoint `app.py`.
3. No secrets are required — price data comes from the public Yahoo Finance API via `yfinance`.

## Project structure

```
app.py                  Streamlit UI (tabs: Screener, Watchlist, Stock Detail, Backtest)
momentum/
  data.py               Price data fetching (yfinance, cached)
  indicators.py         SMA/EMA/RSI/MACD/ROC/ATR/relative strength helpers
  screener.py            Momentum scoring and universe screening
  watchlist.py           JSON-backed watchlist persistence
  backtest.py             Top-N momentum rotation backtest engine
```

## Disclaimer

This tool is for research and educational purposes only. It is not investment advice. Momentum
strategies can experience sharp drawdowns; past performance (backtested or otherwise) does not
guarantee future results.
