"""
Builds site/data.json for the market map. Free Yahoo Finance data through yfinance, no account or keys.
No trading. Yahoo prices can be delayed by up to about 15 minutes.

Universes: S&P 500, Nasdaq 100, Dow 30 (constituent lists from Wikipedia, with a built-in fallback list)
and a Markets view of index, sector, global, bond, commodity and crypto ETFs.
Periods: today, 5 days, 1 month, year to date, 1, 2, 3, 5 years and max.
"""

import io
import json
import os
import sys
from datetime import date, datetime, timezone

from dateutil.relativedelta import relativedelta

import ai as AI
import fundamentals as FD
import signals as S

BENCH = "SPY"
INDICES = ["SPY", "QQQ", "DIA", "IWM"]
PERIODS = ["d1", "d5", "d1m", "ytd", "y1", "y2", "y3", "y5", "max"]
LONG = {"y2": 24, "y3": 36, "y5": 60}  # months back, from the weekly history cached once a day

BUY, BUY_WEAK, WATCH, AVOID = "BUY SETUP", "SETUP (weak mkt)", "HOLD / WATCH", "AVOID"

# Used if Wikipedia cannot be read. Also the sector map is built from the S&P list when it can.
FALLBACK = {
    "Information Technology": ["MSFT", "AAPL", "NVDA", "AVGO", "ORCL", "CRM", "AMD", "ADBE", "CSCO", "INTC", "MU",
                               "QCOM", "TXN", "IBM", "PLTR", "NOW", "AMAT", "PANW"],
    "Communication Services": ["GOOGL", "META", "NFLX", "DIS", "T", "VZ", "TMUS"],
    "Consumer Discretionary": ["AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "LOW", "BKNG", "F", "GM", "UBER"],
    "Consumer Staples": ["WMT", "COST", "PG", "KO", "PEP", "PM", "MDLZ", "CL"],
    "Financials": ["JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "BRK.B", "AXP", "C", "SCHW"],
    "Health Care": ["LLY", "JNJ", "UNH", "ABBV", "MRK", "PFE", "TMO", "ABT", "AMGN"],
    "Industrials": ["GE", "CAT", "RTX", "BA", "HON", "UPS", "DE", "LMT"],
    "Energy": ["XOM", "CVX", "COP", "SLB"],
    "Utilities": ["NEE", "SO", "DUK"],
    "Real Estate": ["PLD", "AMT", "O"],
    "Materials": ["LIN", "NEM", "FCX"],
}
DOW_FALLBACK = ["AAPL", "AMGN", "AMZN", "AXP", "BA", "CAT", "CRM", "CSCO", "CVX", "DIS", "GS", "HD", "HON", "IBM",
                "JNJ", "JPM", "KO", "MCD", "MMM", "MRK", "MSFT", "NKE", "NVDA", "PG", "SHW", "TRV", "UNH", "V",
                "VZ", "WMT"]
ETF_NAMES = {
    "SPY": "SPDR S&P 500 ETF", "QQQ": "Invesco QQQ (Nasdaq 100)", "DIA": "SPDR Dow Jones Industrial Average ETF",
    "IWM": "iShares Russell 2000 ETF", "MDY": "SPDR S&P MidCap 400 ETF", "XLK": "Technology Select Sector SPDR",
    "XLF": "Financial Select Sector SPDR", "XLV": "Health Care Select Sector SPDR", "XLE": "Energy Select Sector SPDR",
    "XLY": "Consumer Discretionary Select Sector SPDR", "XLP": "Consumer Staples Select Sector SPDR",
    "XLI": "Industrial Select Sector SPDR", "XLU": "Utilities Select Sector SPDR", "XLB": "Materials Select Sector SPDR",
    "XLRE": "Real Estate Select Sector SPDR", "XLC": "Communication Services Select Sector SPDR",
    "SMH": "VanEck Semiconductor ETF", "EFA": "iShares MSCI EAFE (developed ex-US)", "EEM": "iShares MSCI Emerging Markets",
    "VGK": "Vanguard FTSE Europe", "EWJ": "iShares MSCI Japan", "FXI": "iShares China Large-Cap", "EWA": "iShares MSCI Australia",
    "INDA": "iShares MSCI India", "TLT": "iShares 20+ Year Treasury Bond", "IEF": "iShares 7-10 Year Treasury Bond",
    "HYG": "iShares High Yield Corporate Bond", "LQD": "iShares Investment Grade Corporate Bond", "GLD": "SPDR Gold Shares",
    "SLV": "iShares Silver Trust", "USO": "United States Oil Fund", "UNG": "United States Natural Gas Fund",
    "DBC": "Invesco DB Commodity Index", "CPER": "United States Copper Index Fund", "IBIT": "iShares Bitcoin Trust",
    "ETHA": "iShares Ethereum Trust",
}
ETFS = {
    "US indices": ["SPY", "QQQ", "DIA", "IWM", "MDY"],
    "US sectors": ["XLK", "XLF", "XLV", "XLE", "XLY", "XLP", "XLI", "XLU", "XLB", "XLRE", "XLC", "SMH"],
    "Global": ["EFA", "EEM", "VGK", "EWJ", "FXI", "EWA", "INDA"],
    "Bonds": ["TLT", "IEF", "HYG", "LQD"],
    "Commodities": ["GLD", "SLV", "USO", "UNG", "DBC", "CPER"],
    "Crypto": ["IBIT", "ETHA"],
}


# ---------------------------------------------------------------- universes
def _get_tables(url):
    import pandas as pd
    import requests
    r = requests.get(url, headers={"User-Agent": "market-map/1.0 (personal project)"}, timeout=30)
    r.raise_for_status()
    return pd.read_html(io.StringIO(r.text))


def _flat(c):
    return " ".join(str(x) for x in c) if isinstance(c, tuple) else str(c)


def _name(c):
    import re
    return re.sub(r"\[.*?\]", "", c).strip().lower()   # drop footnote marks like "Symbol[1]"


def _pick(tables, min_rows, want_sector=True):
    """First big table with a ticker column (Symbol or Ticker), and a sector or industry column when wanted."""
    seen = []
    for t in tables:
        cols = [_flat(c) for c in t.columns]
        seen.append(cols)
        sym = next((c for c in cols if _name(c) in ("symbol", "ticker")), None)
        sec = next((c for c in cols if _name(c).endswith("sector") or _name(c).endswith("industry")), None)
        if sym and (sec or not want_sector) and len(t) >= min_rows:
            t = t.copy()
            t.columns = cols
            return t, sym, sec
    raise ValueError(f"no suitable table, {len(seen)} tables, symbol-like columns: " +
                     str([[c for c in cols if "sym" in c.lower() or "tick" in c.lower()] for cols in seen][:30]))


def _first_table(base, pages, min_rows, want_sector):
    errs = []
    for p in pages:
        try:
            return _pick(_get_tables(base + p), min_rows, want_sector)
        except Exception as e:
            errs.append(f"{p}: {e}")
    raise ValueError("; ".join(errs))


def _clean(x):
    return str(x).strip()


def universes_from_wikipedia():
    base = "https://en.wikipedia.org/wiki/"
    out = {}
    sector_of = {}
    try:
        t, sym, sec = _pick(_get_tables(base + "List_of_S%26P_500_companies"), 400)
        sector_of = {_clean(r[sym]): _clean(r[sec]) for _, r in t.iterrows()}
        out["sp500"] = list(sector_of.items())
        ind_col = next((c for c in t.columns if _name(c) in ("gics sub-industry", "gics sub industry")), None)
        if ind_col:
            out["_industry"] = {_clean(r[sym]): _clean(r[ind_col]) for _, r in t.iterrows()}
        name_col = next((c for c in t.columns if _name(c) in ("security", "company")), None)
        if name_col:
            out["_names"] = {_clean(r[sym]): _clean(r[name_col]) for _, r in t.iterrows()}
    except Exception as e:
        print(f"S&P 500 list unavailable: {e}")
    try:
        t, sym, sec = _first_table(base, ["Nasdaq-100", "List_of_Nasdaq-100_companies"], 90, False)
        # the page uses a different industry scheme, so reuse the S&P sector where the company is in both
        out["ndx"] = [(_clean(r[sym]), sector_of.get(_clean(r[sym]), _clean(r[sec]) if sec else "Other"))
                      for _, r in t.iterrows()]
    except Exception as e:
        print(f"Nasdaq 100 list unavailable: {e}")
    try:
        t, sym, _ = _first_table(base, ["Dow_Jones_Industrial_Average", "Historical_components_of_the_Dow_Jones_Industrial_Average"], 25, False)
        t = t.head(30)
        out["dow"] = [(_clean(r[sym]), sector_of.get(_clean(r[sym]), "Other")) for _, r in t.iterrows()]
    except Exception as e:
        print(f"Dow 30 list unavailable: {e}")
    return out


def universes_fallback():
    sp = [(s, sec) for sec, syms in FALLBACK.items() for s in syms]
    sector_of = dict(sp)
    return {"sp500": sp, "dow": [(s, sector_of.get(s, "Other")) for s in DOW_FALLBACK]}


def get_universes():
    try:
        u = universes_from_wikipedia()
    except Exception as e:  # never let a changed web page stop the map
        print(f"Wikipedia lists unavailable ({e}).")
        u = {}
    fb = universes_fallback()
    for k, v in fb.items():       # anything that could not be read falls back to the built-in list
        u.setdefault(k, v)
    names = u.pop("_names", {})
    industry = u.pop("_industry", {})
    print("Constituent lists:", {k: len(v) for k, v in u.items()}, "names:", len(names), "industries:", len(industry))
    return u, names, industry


def group(pairs, industry=None):
    """pairs: (symbol, sector). Each sector lists its symbols and, when known, its industries."""
    out = {}
    for sym, sec in pairs:
        out.setdefault(sec, []).append(sym)
    result = []
    for sec, syms in out.items():
        inds = {}
        for s in syms:
            inds.setdefault((industry or {}).get(s, ""), []).append(s)
        result.append({"name": sec, "symbols": syms,
                       "industries": [{"name": k, "symbols": v} for k, v in inds.items()]})
    return result


def load_muka(path="muka.json"):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"Muka config unavailable ({e}).")
        return None


def muka_symbols(cfg):
    return [s for syms in cfg["themes"].values() for s in syms]


def muka_universe(cfg):
    sectors = [{"name": t, "symbols": list(s), "industries": [{"name": "", "symbols": list(s)}]}
               for t, s in cfg["themes"].items()]
    return {"id": "muka", "name": cfg.get("name", "Muka"), "sqrt": False, "equal": True, "sectors": sectors}


def muka_index(rows_by_sym, cfg, bench=BENCH):
    """Equal-weight index level since inception. Membership on a day is whatever the board held at the previous close."""
    inc = cfg["inception"]
    added, removed = cfg.get("added", {}), cfg.get("removed", {})
    closes = {s: {r["d"]: r["c"] for r in rows} for s, rows in rows_by_sym.items()}
    dates = [r["d"] for r in rows_by_sym.get(bench, []) if r["d"] >= inc]
    if not dates:
        return None
    syms = set(muka_symbols(cfg)) | set(added)

    def held(s, d):
        return added.get(s, inc) <= d and (s not in removed or removed[s] > d)

    level, spy = [cfg.get("base", 100.0)], [cfg.get("base", 100.0)]
    for prev, d in zip(dates, dates[1:]):
        rets = [closes[s][d] / closes[s][prev] - 1 for s in syms
                if held(s, prev) and s in closes and prev in closes[s] and d in closes[s]]
        r = sum(rets) / len(rets) if rets else 0.0
        level.append(level[-1] * (1 + r))
        b = closes[bench]
        spy.append(spy[-1] * b[d] / b[prev])
    base = cfg.get("base", 100.0)
    return {
        "name": cfg.get("name", "Muka"), "inception": inc, "method": cfg.get("method", ""),
        "rules": cfg.get("rules", []), "board": cfg.get("board", []), "bench": cfg.get("bench", []),
        "dates": dates, "level": [round(v, 3) for v in level], "spy": [round(v, 3) for v in spy],
        "pct": round((level[-1] / base - 1) * 100, 2), "spy_pct": round((spy[-1] / base - 1) * 100, 2),
    }


def ai_scope(unis):
    """Stocks (not ETFs) that get a description and radar."""
    return {s for u in unis if u["id"] != "etf" for sec in u["sectors"] for s in sec["symbols"]}


def layout_of(unis, industry=None):
    out = []
    names = {"sp500": "S&P 500", "ndx": "Nasdaq 100", "dow": "Dow 30"}
    for key in ("sp500", "ndx", "dow"):
        if key in unis:
            out.append({"id": key, "name": names[key], "sqrt": False, "sectors": group(unis[key], industry)})
    out.append({"id": "etf", "name": "Markets (ETFs)", "sqrt": True,
                "sectors": [{"name": k, "symbols": v, "industries": [{"name": "", "symbols": v}]}
                            for k, v in ETFS.items()]})
    return out


# ---------------------------------------------------------------- numbers
def close_on_or_before(rows, target):
    """Last close on or before the date string, or None when the history starts later."""
    best = None
    for r in rows:
        if r["d"] <= target:
            best = r["c"]
        else:
            break
    return best


def anchors_from_weekly(rows, today):
    """Cached once a day: closes 2, 3 and 5 years back and the first close on record."""
    out = {}
    for k, months in LONG.items():
        target = (today - relativedelta(months=months)).isoformat()
        out[k] = close_on_or_before(rows, target)
    out["max"] = rows[0]["c"] if rows else None
    return out


def record(rows, anchors):
    """rows: daily bars oldest first, the last one is the live or latest finished session."""
    if len(rows) < 23:
        return None
    last = rows[-1]
    price, last_date = last["c"], last["d"]
    done = rows[:-1]
    ind = S.compute_indicators(done, price, last["v"])
    today = date.fromisoformat(last_date)
    anchors = anchors or {}

    def chg(base):
        return S.pct(price, base) if base else None

    rec = {
        "price": round(price, 2),
        "size": max(price * sum(b["v"] for b in done[-20:]) / 20, 1.0),
        "d1": chg(done[-1]["c"]),
        "d5": chg(rows[-6]["c"]),
        "d1m": chg(close_on_or_before(rows, (today - relativedelta(months=1)).isoformat())),
        "ytd": chg(close_on_or_before(rows, f"{today.year - 1}-12-31")),
        "y1": chg(close_on_or_before(rows, (today - relativedelta(years=1)).isoformat())),
        "y2": chg(anchors.get("y2")), "y3": chg(anchors.get("y3")), "y5": chg(anchors.get("y5")),
        "max": chg(anchors.get("max")),
    }
    for k in PERIODS:
        if rec[k] is not None:
            rec[k] = round(rec[k], 2)
    return rec, ind


def signal(ind, regime_ok):
    res = S.classify(ind)
    if res["setup"]:
        return BUY if regime_ok else BUY_WEAK
    return AVOID if S._trend_failed(ind) else WATCH


def build(rows_by_sym, anchors_by_sym, universes, names=None):
    names = {**ETF_NAMES, **(names or {})}
    recs, inds = {}, {}
    for sym, rows in rows_by_sym.items():
        out = record(rows, anchors_by_sym.get(sym))
        if out:
            recs[sym], inds[sym] = out
    reg = S.regime(inds.get(BENCH))
    ok = bool(reg.get("ok"))
    for sym in recs:
        recs[sym]["signal"] = signal(inds[sym], ok)
        if names.get(sym):
            recs[sym]["n"] = names[sym]
    where = {}                      # symbol -> (sector, industry) from the first real index it appears in
    for u in universes:
        if u["id"] in ("sp500", "ndx", "dow"):
            for sec in u["sectors"]:
                for ind in sec.get("industries", []):
                    for s in ind["symbols"]:
                        where.setdefault(s, (sec["name"], ind["name"]))
                for s in sec["symbols"]:
                    where.setdefault(s, (sec["name"], ""))
    etfs = {s for u in universes if u["id"] == "etf" for sec in u["sectors"] for s in sec["symbols"]}
    for sym in recs:
        if sym not in etfs and sym not in INDICES:
            recs[sym]["ai"] = AI.score(sym, *where.get(sym, (None, None)))
    unis = []
    for u in universes:
        secs = []
        for sec in u["sectors"]:
            have = [s for s in sec["symbols"] if s in recs]
            if have:
                inds = []
                for ind in sec.get("industries", []):
                    keep = [s for s in ind["symbols"] if s in recs]
                    if keep:
                        inds.append({"name": ind["name"], "symbols": keep})
                secs.append({"name": sec["name"], "symbols": have, "industries": inds})
        if secs:
            unis.append({"id": u["id"], "name": u["name"], "sqrt": u["sqrt"], "equal": bool(u.get("equal")), "sectors": secs})
    return {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "regime": {"ok": reg.get("ok"), "why": reg.get("why")},
        "indices": [s for s in INDICES if s in recs],
        "symbols": recs,
        "universes": unis,
    }


# ---------------------------------------------------------------- yahoo
def _rows(sub):
    return [{"d": idx.strftime("%Y-%m-%d"), "o": float(r["Open"]), "h": float(r["High"]), "l": float(r["Low"]),
             "c": float(r["Close"]), "v": int(r["Volume"] or 0)} for idx, r in sub.iterrows()]


def parse_download(df, symbols):
    """df: yfinance frame grouped by ticker. Returns {symbol: rows}. Missing or empty symbols are skipped."""
    out = {}
    for sym in symbols:
        try:
            sub = df[sym.replace(".", "-")].dropna(subset=["Close"])
        except KeyError:
            continue
        rows = _rows(sub)
        if len(rows) >= 2:
            out[sym] = rows
    return out


def download(symbols, **kw):
    import yfinance as yf

    def get(syms, threads):
        df = yf.download([s.replace(".", "-") for s in syms], group_by="ticker", auto_adjust=True,
                         threads=threads, progress=False, **kw)
        return parse_download(df, syms)

    out = get(symbols, True)
    missing = [s for s in symbols if s not in out]
    if 0 < len(missing) <= 40:   # a few can fail on a busy cache ("database is locked"): retry them one by one
        out.update(get(missing, False))
    return out


def load_anchors(symbols, path="anchors.json"):
    """Weekly history back to the start, fetched once a day and cached by the workflow."""
    today = date.today().isoformat()
    try:
        with open(path) as f:
            cached = json.load(f)
        if cached.get("date") == today:
            return cached["anchors"]
    except Exception:
        pass
    weekly = download(symbols, period="max", interval="1wk")
    anchors = {s: anchors_from_weekly(rows, date.today()) for s, rows in weekly.items()}
    with open(path, "w") as f:
        json.dump({"date": today, "anchors": anchors}, f, separators=(",", ":"))
    return anchors


def main():
    lists, names, industry = get_universes()
    unis = layout_of(lists, industry)
    muka = load_muka()
    if muka:
        unis.insert(len(unis) - 1, muka_universe(muka))   # just before the ETF map
    symbols = sorted({s for u in unis for sec in u["sectors"] for s in sec["symbols"]} | set(INDICES))
    print(f"{len(symbols)} symbols")
    rows = download(symbols, period="13mo", interval="1d")
    try:
        anchors = load_anchors(list(rows))
    except Exception as e:
        print(f"Long-range history unavailable ({e}). Showing periods up to 1 year only.")
        anchors = {}
    data = build(rows, anchors, unis, names)
    if muka:
        try:
            data["muka"] = muka_index(rows, muka)
        except Exception as e:
            print(f"Muka index not calculated ({e}).")
    n = len(data["symbols"])
    if n < 30:
        sys.exit(f"Only {n} symbols had enough data, not publishing.")
    os.makedirs("site", exist_ok=True)
    with open("site/data.json", "w") as f:
        json.dump(data, f, separators=(",", ":"))
    # one year of closes per symbol for the hover chart, loaded by the page only when needed
    spark = {sym: [round(r["c"], 2) for r in rows[sym][-252:]] for sym in data["symbols"]}
    if data.get("muka"):
        spark["MUKA"] = data["muka"]["level"]
    with open("site/spark.json", "w") as f:
        json.dump(spark, f, separators=(",", ":"))
    print(f"Wrote site/data.json with {n} symbols. {data['regime']['why']}")
    try:   # descriptions and radar scores: slow to fetch, so a time-boxed top-up each run, cached between runs
        cache = FD.load()
        scope = ai_scope(unis)
        order = [s for s in (muka_symbols(muka) if muka else []) if s in data["symbols"]] + \
                [s for s in data["symbols"] if s in scope]
        done = FD.refresh(list(dict.fromkeys(order)), cache)
        FD.save(cache)
        with open("site/fund.json", "w") as f:
            json.dump({s: {"d": v["d"], "s": v["s"]} for s, v in cache.items() if s in data["symbols"]}, f, separators=(",", ":"))
        print(f"Fundamentals: {done} fetched this run, {len(cache)} cached.")
    except Exception as e:
        print(f"Fundamentals skipped ({e}).")


if __name__ == "__main__":
    main()
