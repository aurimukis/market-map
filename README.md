# Market map

A read-only spectator page: a market-style heat map with simple rule-based trend signals.
It places no orders and has no link to the trading bots. Data is free Yahoo Finance data via yfinance (no keys, can be delayed about 15 minutes).

- `fetch.py` builds `site/data.json` (no keys needed).
- `site/index.html` is the page. It reloads the data every minute and flashes tiles that moved.
- `.github/workflows/update.yml` refreshes and publishes it every 5 minutes in US market hours.

Signals are a picture of one set of trend rules, not advice or a forecast.
