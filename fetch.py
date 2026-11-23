"""
Builds site/data.json for the market map. Free Yahoo Finance data through yfinance, no account or keys. No trading.
Yahoo prices can be delayed by up to about 15 minutes.
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


def parse_download(df, symbols):
    """
    df: yfinance download frame (columns grouped by ticker). Returns (bars, snaps) in the shape build() expects.
    Yahoo's last daily row is the live (or latest finished) session, so it supplies price, volume and date.
    """
    bars, snaps = {}, {}
    for sym in symbols:
        ysym = sym.replace(".", "-")
        try:
            sub = df[ysym].dropna(subset=["Close"])
        except KeyError:
            continue
        rows = [{"d": idx.strftime("%Y-%m-%d"), "o": float(r["Open"]), "h": float(r["High"]), "l": float(r["Low"]),
                 "c": float(r["Close"]), "v": int(r["Volume"] or 0)} for idx, r in sub.iterrows()]
        if len(rows) < 2:
            continue
        bars[sym] = rows
        snaps[sym] = {"price": rows[-1]["c"], "volume": rows[-1]["v"], "last_date": rows[-1]["d"],
                      "prev_close": rows[-2]["c"]}
    return bars, snaps


def fetch():
    import yfinance as yf

    symbols = sorted({s for syms in SECTORS.values() for s in syms} | set(INDICES))
    df = yf.download([s.replace(".", "-") for s in symbols], period="8mo", interval="1d", group_by="ticker",
                     auto_adjust=True, threads=True, progress=False)
    return parse_download(df, symbols)


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
