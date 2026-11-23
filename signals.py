"""Indicators and rule signals, copied from the trader bot so the map labels match it. No trading code."""

def sma(values, n):
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def atr(highs, lows, closes, n=14):
    if len(closes) < n + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    return sum(trs[-n:]) / n


def rsi(closes, n=14):
    if len(closes) < n + 1:
        return None
    gains, losses = [], []
    for i in range(len(closes) - n, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain, avg_loss = sum(gains) / n, sum(losses) / n
    if avg_loss == 0:
        return 100.0
    return 100 - 100 / (1 + avg_gain / avg_loss)


def pct(a, b):
    if a is None or b in (None, 0):
        return None
    return round((a / b - 1) * 100, 2)


def compute_indicators(bars, live_price, today_volume=None):
    """bars: list of dicts with o,h,l,c,v (completed days, oldest first)."""
    closes = [b["c"] for b in bars]
    highs = [b["h"] for b in bars]
    lows = [b["l"] for b in bars]
    vols = [b["v"] for b in bars]
    last_close = closes[-1] if closes else None
    avg_vol = sma(vols, 20)
    out = {
        "price": round(live_price, 2) if live_price else None,
        "prev_close": last_close,
        "chg_today_pct": pct(live_price, last_close),
        "chg_5d_pct": pct(live_price, closes[-5]) if len(closes) >= 5 else None,
        "chg_20d_pct": pct(live_price, closes[-20]) if len(closes) >= 20 else None,
        "sma20": round(sma(closes, 20), 2) if sma(closes, 20) else None,
        "sma50": round(sma(closes, 50), 2) if sma(closes, 50) else None,
        "atr14": round(atr(highs, lows, closes), 2) if atr(highs, lows, closes) else None,
        "rsi14": round(rsi(closes), 1) if rsi(closes) else None,
        "high_20d": max(highs[-20:]) if len(highs) >= 20 else None,
        "low_20d": min(lows[-20:]) if len(lows) >= 20 else None,
        "rel_volume_today": round(today_volume / avg_vol, 2) if (today_volume and avg_vol) else None,
    }
    if out["atr14"] and live_price:
        out["atr_pct"] = round(out["atr14"] / live_price * 100, 2)
    if out["sma50"] and live_price:
        out["above_sma50"] = live_price > out["sma50"]
    return out


PULLBACK_MAX_ABOVE_SMA20 = 1.02   # price no more than 2% above the 20-day average
PULLBACK_MAX_RSI = 55
BREAKOUT_NEAR_HIGH = 0.995        # within 0.5% of (or above) the 20-day high
BREAKOUT_MIN_REL_VOLUME = 1.2


def regime(bench):
    """Is the benchmark in a state where the strategy notes allow new longs?"""
    if not bench or bench.get("sma50") is None or bench.get("price") is None:
        return {"known": False, "ok": None, "why": "benchmark data missing"}
    above = bench["price"] > bench["sma50"]
    return {
        "known": True,
        "ok": above,
        "price": bench["price"],
        "sma50": bench["sma50"],
        "why": "benchmark above its 50-day average" if above else "benchmark below its 50-day average",
    }


def _checks(ind):
    """Every condition as (name, passed). A missing value counts as a fail."""
    p, s20, s50 = ind.get("price"), ind.get("sma20"), ind.get("sma50")
    hi20, rsi, rv = ind.get("high_20d"), ind.get("rsi14"), ind.get("rel_volume_today")
    have_trend = None not in (p, s20, s50)
    uptrend_price = bool(have_trend and p > s50)
    uptrend_avgs = bool(have_trend and s20 > s50)
    return {
        "uptrend": [("price above 50-day", uptrend_price), ("20-day above 50-day", uptrend_avgs)],
        "pullback": [
            ("near or below 20-day", bool(have_trend and p <= s20 * PULLBACK_MAX_ABOVE_SMA20)),
            (f"RSI at or below {PULLBACK_MAX_RSI}", bool(rsi is not None and rsi <= PULLBACK_MAX_RSI)),
        ],
        "breakout": [
            ("within 0.5% of 20-day high", bool(p is not None and hi20 is not None and p >= hi20 * BREAKOUT_NEAR_HIGH)),
            (f"volume at least {BREAKOUT_MIN_REL_VOLUME}x average", bool(rv is not None and rv >= BREAKOUT_MIN_REL_VOLUME)),
        ],
    }


def classify(ind):
    """
    One symbol. Returns {"setup": "pullback" | "breakout" | None, "score", "failed"}.
    A setup needs the uptrend checks plus all of that setup's own checks.
    "score" is the share of checks passed for the best-fitting setup (1.0 = a setup).
    """
    if not ind:
        return {"setup": None, "score": 0.0, "failed": ["no indicators"]}
    c = _checks(ind)
    trend = c["uptrend"]
    best = None
    for name in ("pullback", "breakout"):
        checks = trend + c[name]
        passed = sum(1 for _, ok in checks if ok)
        score = passed / len(checks)
        failed = [label for label, ok in checks if not ok]
        if best is None or score > best["score"]:
            best = {"setup": name if not failed else None, "closest": name, "score": round(score, 2), "failed": failed}
    return best


def scan(indicators, bench, top_n=3):
    """
    indicators: {symbol: indicator dict} for the symbols Claude may consider today.
    Returns a small, loggable summary.
    """
    results = {s: classify(i) for s, i in indicators.items()}
    setups = sorted(s for s, r in results.items() if r["setup"])
    near = sorted(((s, r) for s, r in results.items() if not r["setup"]), key=lambda x: -x[1]["score"])[:top_n]
    return {
        "regime": regime(bench),
        "scanned": len(results),
        "in_uptrend": sum(1 for s, i in indicators.items() if not _trend_failed(i)),
        "setups": [{"symbol": s, "setup": results[s]["setup"]} for s in setups],
        "near_misses": [
            {"symbol": s, "closest": r["closest"], "score": r["score"], "failed": r["failed"]} for s, r in near
        ],
    }


def _trend_failed(ind):
    return any(not ok for _, ok in _checks(ind)["uptrend"])


def summary_line(result):
    """One short block for the Telegram message and the weekly review."""
    if not result:
        return ""
    reg = result["regime"]
    lines = [f"Scanner: {reg['why']}."]
    if result["scanned"]:
        lines.append(f"{result['in_uptrend']} of {result['scanned']} symbols in an uptrend, "
                     f"{len(result['setups'])} with a setup.")
    for n in result["near_misses"]:
        lines.append(f"Near miss {n['symbol']} ({n['closest']}, {int(n['score'] * 100)}%): missing "
                     + ", ".join(n["failed"][:2]))
    return "\n".join(lines)
