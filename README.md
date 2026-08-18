# Momentum Swing Trading

A Streamlit app for finding, tracking, and backtesting momentum-based swing trade candidates.

## Features

- **Screener** — ranks a ticker universe by a composite momentum score (weighted 1/3/6/12-month
  rate of change), with filters for price, average volume, RSI range, and trend (price above
  50/200-day SMA). Universe options: a default 40-stock US watchlist, live-fetched **Nifty 200**
  or **Nifty 500** constituents (via NSE's public index archive), or a custom ticker list.
- **Watchlist** — save candidates from the screener and track their latest momentum stats;
  persisted locally to `data/watchlist.json`.
- **Signals** — every screened stock gets a rule-based **Strong Buy / Buy / Hold / Sell / Strong
  Sell** label, combining momentum direction, relative strength, RSI zone, trend, and MACD state
  (see `momentum/signals.py`). The Stock Detail chart also marks historical MACD bullish/bearish
  crossover points.
- **Stock Detail** — candlestick chart with 50/200-day SMAs, RSI(14), MACD, and crossover markers
  for any ticker, plus its current Signal/Momentum Score/Vs Benchmark badge.
- **Backtest** — simulates an equal-weight, top-N momentum rotation strategy across the whole
  universe, rebalanced on a fixed schedule, plotted against a buy-and-hold benchmark, with CAGR /
  volatility / Sharpe / max drawdown stats.
- **Trade Simulator** — manual paper trading: click Buy/Sell yourself on any ticker against a
  simulated cash balance, at its latest price, buying either by dollar amount or by exact share
  quantity, with weighted-average cost basis. Shows the current Buy/Sell signal next to each
  ticker as a decision aid, an equity curve across your trades, realized P&L/win-rate stats, an
  open-positions table, a trade log with CSV export, and a confirm-before-erasing portfolio reset.
  Persisted to `data/paper_portfolio.json`.

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
app.py                  Streamlit UI (tabs: Screener, Watchlist, Stock Detail, Backtest, Trade Simulator)
momentum/
  data.py               Price data fetching (yfinance, cached, batched for large universes)
  nse_indices.py        Live Nifty 200 / Nifty 500 constituent list fetching (NSE archive)
  indicators.py         SMA/EMA/RSI/MACD/ROC/ATR/relative strength helpers
  signals.py             Strong Buy/Buy/Hold/Sell/Strong Sell signal rules and MACD crossover detection
  screener.py            Momentum scoring and universe screening
  watchlist.py           JSON-backed watchlist persistence
  backtest.py             Top-N momentum rotation backtest engine (universe-wide rotation)
  paper_trading.py         Manual buy/sell paper-trading portfolio (weighted-avg cost basis)
```

## Note on Signals

The Strong Buy/Buy/Hold/Sell/Strong Sell label is a simple, transparent vote across five
already-visible metrics — it is not a machine-learned or optimized signal, and it is not
investment advice. Momentum direction always caps the signal (negative momentum can never show
as Buy/Strong Buy); the other four factors determine conviction within that direction. Treat it
as a faster way to scan the screener table, not a substitute for looking at the chart yourself.

## Note on the Nifty 200 / Nifty 500 universes

Index constituents are fetched live from NSE on each cache refresh (once per day) rather than
hardcoded, since NSE rebalances these indices periodically. NSE commonly blocks cloud/datacenter
IPs (including Streamlit Community Cloud's) at the network level, so the live fetch is expected to
fail most of the time when deployed. Three layers of fallback, in priority order:

1. **Live fetch** from NSE — freshest, used whenever NSE doesn't block the request.
2. **Uploaded list** (`data/uploaded_*.json`) — download the CSV from NSE in your own browser
   (unaffected by the block) and upload it via the "Upload a fresher list" expander. Survives page
   refreshes and reconnects, but is wiped on the next app redeploy (Streamlit Cloud resets the
   filesystem on every push).
3. **Bundled snapshot** (`data/nifty200_fallback.csv`, `data/nifty500_fallback.csv`) — committed
   to the repo, as of `nse_indices.BUNDLED_FALLBACK_DATE`. Ships with the code, so it survives
   every redeploy without any action needed; refresh it periodically by replacing those files
   (and updating `BUNDLED_FALLBACK_DATE`) with a freshly downloaded CSV.

Only if all three fail does the screener fall back to the default watchlist universe and show an
error — it will not silently use a stale or partial list without telling you.

## Disclaimer

This tool is for research and educational purposes only. It is not investment advice. Momentum
strategies can experience sharp drawdowns; past performance (backtested or otherwise) does not
guarantee future results.
