"""
Builds site/data.json for the market map. Read-only market data from Alpaca (IEX feed). No trading.
Needs ALPACA_KEY and ALPACA_SECRET in the environment (paper keys are fine).
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import signals as S

SECTORS = {
    "Technology": ["MSFT", "AAPL", "NVDA", "AVGO", "ORCL", "CRM", "AMD", "ADBE", "CSCO", "INTC", "MU",
                   "QCOM", "TXN", "IBM", "PLTR", "NOW", "AMAT", "PANW"],
    "Communication": ["GOOGL", "META", "NFLX", "DIS", "T", "VZ", "TMUS"],
    "Consumer Cyclical": ["AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "LOW", "BKNG", "F", "GM", "UBER"],
    "Consumer Defensive": ["WMT", "COST", "PG", "KO", "PEP", "PM", "MDLZ", "CL"],
    "Financial": ["JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "BRK.B", "AXP", "C", "SCHW"],
    "Healthcare": ["LLY", "JNJ", "UNH", "ABBV", "MRK", "PFE", "TMO", "ABT", "AMGN"],
    "Industrials": ["GE", "CAT", "RTX", "BA", "HON", "UPS", "DE", "LMT"],
    "Energy": ["XOM", "CVX", "COP", "SLB"],
    "Utilities": ["NEE", "SO", "DUK"],
    "Real Estate": ["PLD", "AMT", "O"],
    "Materials": ["LIN", "NEM", "FCX"],
}
INDICES = ["SPY", "QQQ", "DIA", "IWM"]
BENCH = "SPY"

BUY, BUY_WEAK, WATCH, AVOID = "BUY SETUP", "SETUP (weak mkt)", "HOLD / WATCH", "AVOID"


def signal(ind, regime_ok):
    if not ind:
        return AVOID
    res = S.classify(ind)
    if res["setup"]:
        return BUY if regime_ok else BUY_WEAK
    return AVOID if S._trend_failed(ind) else WATCH


def build(bars, snaps):
    """bars: {sym: [{d,o,h,l,c,v}]} completed days oldest first. snaps: {sym: {price, volume, last_date, prev_close}}."""
    inds, extra = {}, {}
    for sym, snap in snaps.items():
        rows = [b for b in bars.get(sym, []) if b["d"] < snap["last_date"]]
        if len(rows) < 22 or not snap.get("price"):
            continue
        ind = S.compute_indicators(rows, snap["price"], snap.get("volume"))
        inds[sym] = ind
        avg_vol = sum(b["v"] for b in rows[-20:]) / 20
        d1 = S.pct(snap["price"], snap["prev_close"]) if snap.get("prev_close") else None
        extra[sym] = {"price": round(snap["price"], 2), "size": max(snap["price"] * avg_vol, 1.0),
                      "d1": d1, "d5": ind.get("chg_5d_pct"), "d20": ind.get("chg_20d_pct")}
    reg = S.regime(inds.get(BENCH))
    ok = bool(reg.get("ok"))
    sectors = []
    for name, syms in SECTORS.items():
        items = []
        for s in syms:
            if s in extra:
                items.append({"s": s, **extra[s], "signal": signal(inds[s], ok)})
        if items:
            sectors.append({"name": name, "items": sorted(items, key=lambda i: -i["size"])})
    indices = {s: {"price": extra[s]["price"], "d1": extra[s]["d1"], "d5": extra[s]["d5"], "d20": extra[s]["d20"]}
               for s in INDICES if s in extra}
    return {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "regime": {"ok": reg.get("ok"), "why": reg.get("why")},
        "indices": indices,
        "sectors": sectors,
    }


def fetch():
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest, StockSnapshotRequest
    from alpaca.data.timeframe import TimeFrame

    client = StockHistoricalDataClient(os.environ["ALPACA_KEY"], os.environ["ALPACA_SECRET"])
    symbols = sorted({s for syms in SECTORS.values() for s in syms} | set(INDICES))
    req = StockBarsRequest(symbol_or_symbols=symbols, timeframe=TimeFrame.Day,
                           start=datetime.now(timezone.utc) - timedelta(days=130),
                           adjustment=Adjustment.SPLIT, feed=DataFeed.IEX)
    bars = {}
    for sym, rows in client.get_stock_bars(req).data.items():
        bars[sym] = [{"d": r.timestamp.strftime("%Y-%m-%d"), "o": r.open, "h": r.high, "l": r.low,
                      "c": r.close, "v": int(r.volume)} for r in rows]
    raw = client.get_stock_snapshot(StockSnapshotRequest(symbol_or_symbols=symbols, feed=DataFeed.IEX))
    snaps = {}
    for sym, s in raw.items():
        if not s.daily_bar:
            continue
        price = float(s.latest_trade.price) if s.latest_trade else float(s.daily_bar.close)
        snaps[sym] = {"price": price, "volume": int(s.daily_bar.volume),
                      "last_date": s.daily_bar.timestamp.strftime("%Y-%m-%d"),
                      "prev_close": float(s.previous_daily_bar.close) if s.previous_daily_bar else None}
    return bars, snaps


def main():
    bars, snaps = fetch()
    data = build(bars, snaps)
    n = sum(len(s["items"]) for s in data["sectors"])
    if n < 30:
        sys.exit(f"Only {n} symbols had enough data, not publishing.")
    os.makedirs("site", exist_ok=True)
    with open("site/data.json", "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"Wrote site/data.json with {n} symbols. {data['regime']['why']}")


if __name__ == "__main__":
    main()
