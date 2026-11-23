"""Company description and a five-axis fundamentals radar (Value, Future, Past, Health, Dividend, each 0 to 6).

Our own simple scoring from free Yahoo fundamentals, six yes/no checks per axis. It is not Simply Wall St's data or
model, so numbers will differ from theirs. Missing data counts as a fail, so banks and insurers (no current ratio or
debt/equity in Yahoo) tend to score low on Health.
"""
import json
import re
import time

AXES = ["Value", "Future", "Past", "Health", "Dividend"]


def _n(info, k):
    v = info.get(k)
    return float(v) if isinstance(v, (int, float)) and v == v else None


def _check(x, test):
    return 1 if x is not None and test(x) else 0


def scores(info):
    g = lambda k: _n(info, k)
    price = g("currentPrice") or g("regularMarketPrice") or g("previousClose")
    target = g("targetMeanPrice")
    upside = (target / price - 1) * 100 if price and target else None
    eps, feps = g("trailingEps"), g("forwardEps")
    eps_growth = (feps / eps - 1) * 100 if eps and eps > 0 and feps else None
    de = g("debtToEquity")
    cash, debt = g("totalCash"), g("totalDebt")
    rate = g("dividendRate")
    yld = rate / price * 100 if rate and price else None
    avg5 = g("fiveYearAvgDividendYield")
    pay = g("payoutRatio")
    value = [_check(g("trailingPE"), lambda x: 0 < x < 25), _check(g("forwardPE"), lambda x: 0 < x < 22),
             _check(g("priceToBook"), lambda x: 0 < x < 3), _check(g("trailingPegRatio") or g("pegRatio"), lambda x: 0 < x < 1.5),
             _check(g("enterpriseToEbitda"), lambda x: 0 < x < 15), _check(upside, lambda x: x >= 10)]
    future = [_check(eps_growth, lambda x: x >= 10), _check(eps_growth, lambda x: x >= 25), _check(upside, lambda x: x >= 10),
              _check(upside, lambda x: x >= 25), _check(g("recommendationMean"), lambda x: x <= 2.5),
              _check(g("revenueGrowth"), lambda x: x >= 0.10)]
    past = [_check(g("returnOnEquity"), lambda x: x >= 0.15), _check(g("returnOnEquity"), lambda x: x >= 0.25),
            _check(g("profitMargins"), lambda x: x >= 0.10), _check(g("profitMargins"), lambda x: x >= 0.20),
            _check(g("earningsGrowth"), lambda x: x > 0), _check(g("revenueGrowth"), lambda x: x >= 0.05)]
    health = [_check(g("currentRatio"), lambda x: x >= 1), _check(g("currentRatio"), lambda x: x >= 1.5),
              _check(de, lambda x: x < 100), _check(de, lambda x: x < 50), _check(g("freeCashflow"), lambda x: x > 0),
              1 if cash is not None and debt is not None and cash >= debt else 0]
    div = [_check(yld, lambda x: x > 0), _check(yld, lambda x: x >= 1), _check(yld, lambda x: x >= 2.5),
           _check(yld, lambda x: x >= 4), _check(pay, lambda x: 0 < x < 0.8),
           1 if yld and avg5 is not None and yld >= avg5 else 0]
    return [sum(a) for a in (value, future, past, health, div)]


def short(text, limit=330):
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("; "))
    return (cut[:end + 1] if end > 120 else cut.rsplit(" ", 1)[0] + "...")


def entry(info):
    desc = short(info.get("longBusinessSummary"))
    if not desc and not info.get("trailingPE") and not info.get("returnOnEquity"):
        return None
    return {"d": desc, "s": scores(info), "t": int(time.time())}


def refresh(symbols, cache, budget=240, max_age_days=7, ticker=None, pause=0.25):
    """Fill or renew cache entries for symbols (priority order) within a time budget. Stops early if Yahoo blocks us."""
    if ticker is None:
        import yfinance as yf
        ticker = lambda s: yf.Ticker(s.replace(".", "-")).info
    start, fails, done = time.time(), 0, 0
    old = time.time() - max_age_days * 86400
    for s in symbols:
        if time.time() - start > budget or fails >= 8:
            break
        if s in cache and cache[s].get("t", 0) > old:
            continue
        try:
            e = entry(ticker(s))
            if e:
                cache[s] = e
                done += 1
                fails = 0
            else:
                fails += 1
        except Exception:
            fails += 1
        time.sleep(pause)
    return done


def load(path="fund-cache.json"):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def save(cache, path="fund-cache.json"):
    with open(path, "w") as f:
        json.dump(cache, f, separators=(",", ":"))
