"""Insider buying and selling summary from Yahoo's copy of SEC Form 4 filings (officers, directors, 10% owners).

Only open-market purchases and sales count. Grants, awards, gifts and option exercises are ignored, because they are
pay, not a view on the price. Filings arrive up to two business days after the trade, so this is never real time.
"""
import time
from datetime import date, datetime, timedelta


def _first(row, *names):
    for n in names:
        if n in row and row[n] == row[n] and row[n] is not None:
            return row[n]
    return None


def normalise(df):
    """DataFrame from yfinance Ticker.insider_transactions to plain rows: date, name, position, kind, value."""
    out = []
    if df is None or len(df) == 0:
        return out
    for _, r in df.iterrows():
        r = r.to_dict()
        text = str(_first(r, "Text", "Transaction") or "").lower()
        kind = "buy" if text.startswith(("purchase", "buy")) else "sell" if text.startswith("sale") else None
        if not kind:
            continue
        d = _first(r, "Start Date", "Date")
        try:
            d = d.date() if hasattr(d, "date") else datetime.fromisoformat(str(d)[:10]).date()
        except Exception:
            continue
        val = _first(r, "Value")
        shares = _first(r, "Shares")
        try:
            val = float(val) if val is not None else None
        except Exception:
            val = None
        out.append({"d": d, "name": str(_first(r, "Insider") or "").title(), "pos": str(_first(r, "Position") or ""),
                    "kind": kind, "value": val, "shares": shares})
    return out


def summarise(rows, today=None, days=90):
    today = today or date.today()
    since = today - timedelta(days=days)
    buys = [r for r in rows if r["kind"] == "buy" and r["d"] >= since]
    sells = [r for r in rows if r["kind"] == "sell" and r["d"] >= since]
    val = lambda xs: round(sum(x["value"] or 0 for x in xs))
    if not buys and not sells:
        return {}
    top = max(buys, key=lambda x: x["value"] or 0) if buys else None
    return {
        "b": len(buys), "n": len({r["name"] for r in buys}), "bv": val(buys), "sv": val(sells),
        "last": max((r["d"] for r in buys), default=None) and max(r["d"] for r in buys).isoformat(),
        "top": {"name": top["name"], "pos": top["pos"], "v": round(top["value"] or 0)} if top else None,
    }


def refresh(symbols, cache, budget=80, max_age_days=1, ticker=None, pause=0.25):
    """cache['_ins'][symbol] = {'t': time, 's': summary}. Time-boxed, stops early if Yahoo blocks us."""
    if ticker is None:
        import yfinance as yf
        ticker = lambda s: yf.Ticker(s.replace(".", "-")).insider_transactions
    store = cache.setdefault("_ins", {})
    start, fails, done = time.time(), 0, 0
    old = time.time() - max_age_days * 86400
    for s in symbols:
        if time.time() - start > budget or fails >= 8:
            break
        if s in store and store[s].get("t", 0) > old:
            continue
        try:
            store[s] = {"t": int(time.time()), "s": summarise(normalise(ticker(s)))}
            done += 1
            fails = 0
        except Exception:
            fails += 1
        time.sleep(pause)
    return done
