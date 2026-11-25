import random

import fetch as F


def mk(n=300, drift=0.002, seed=1, vol=1_000_000, start="2025-01-01"):
    import pandas as pd
    rnd = random.Random(seed)
    p, out = 100.0, []
    for i, d in enumerate(pd.bdate_range(start, periods=n)):
        p *= 1 + drift + rnd.uniform(-0.004, 0.004)
        out.append({"d": d.strftime("%Y-%m-%d"), "o": p, "h": p * 1.01, "l": p * 0.99, "c": p, "v": vol})
    return out


def test_close_on_or_before():
    rows = [{"d": "2026-01-02", "c": 1.0}, {"d": "2026-01-09", "c": 2.0}]
    assert F.close_on_or_before(rows, "2026-01-05") == 1.0
    assert F.close_on_or_before(rows, "2026-02-01") == 2.0
    assert F.close_on_or_before(rows, "2025-12-31") is None


def test_periods_and_anchors():
    rows = mk(n=300, drift=0.003)
    rec, ind = F.record(rows, {"y2": 50.0, "y3": None, "y5": 40.0, "max": 10.0})
    assert all(k in rec for k in F.PERIODS)
    assert rec["d1"] is not None and rec["d5"] is not None and rec["d1m"] is not None
    assert rec["y1"] is not None and rec["ytd"] is not None
    assert rec["y3"] is None                      # unknown anchor stays blank, not zero
    assert rec["max"] > rec["y5"] > rec["y2"]     # lower base, bigger gain
    assert F.record(mk(n=10), {}) is None


def test_build_signals_and_universes():
    unis = F.layout_of(F.universes_fallback())
    syms = sorted({s for u in unis for sec in u["sectors"] for s in sec["symbols"]} | set(F.INDICES))
    rows = {s: mk(drift=-0.004 if s == "SPY" else (0.004 if i % 2 else -0.004), seed=i) for i, s in enumerate(syms)}
    data = F.build(rows, {}, unis)
    assert data["regime"]["ok"] is False
    assert {u["id"] for u in data["universes"]} >= {"sp500", "dow", "etf"}
    sigs = {r["signal"] for r in data["symbols"].values()}
    assert F.BUY not in sigs                       # never a plain buy while SPY is below its 50-day
    assert {F.AVOID, F.WATCH} & sigs
    assert set(data["indices"]) == set(F.INDICES)
    for u in data["universes"]:
        for sec in u["sectors"]:
            assert all(s in data["symbols"] for s in sec["symbols"])


def test_parse_download_shape():
    import pandas as pd
    idx = pd.date_range("2026-01-01", periods=30, freq="B")
    cols = pd.MultiIndex.from_product([["BRK-B", "MSFT"], ["Open", "High", "Low", "Close", "Volume"]])
    df = pd.DataFrame(1.0, index=idx, columns=cols)
    df[("MSFT", "Volume")] = 1000
    df.loc[idx[-1], ("MSFT", "Close")] = float("nan")   # a half-empty latest row is dropped
    out = F.parse_download(df, ["BRK.B", "MSFT", "AAPL"])
    assert set(out) == {"BRK.B", "MSFT"}                  # AAPL missing is skipped, BRK.B maps to BRK-B
    assert len(out["MSFT"]) == 29


def test_group_and_layout():
    g = F.group([("A", "X"), ("B", "X"), ("C", "Y")], {"A": "Alpha", "B": "Alpha", "C": "Gamma"})
    assert g[0]["symbols"] == ["A", "B"] and g[0]["industries"] == [{"name": "Alpha", "symbols": ["A", "B"]}]
    assert F.group([("A", "X")])[0]["industries"] == [{"name": "", "symbols": ["A"]}]


def test_pick_table_flexible_columns():
    import pandas as pd
    big = pd.DataFrame({"Ticker": [f"T{i}" for i in range(100)], "Company": "x", "GICS Sector": "Energy"})
    small = pd.DataFrame({"Symbol": ["A"], "Industry": ["x"]})
    t, sym, sec = F._pick([small, big], 90)
    assert (sym, sec) == ("Ticker", "GICS Sector")
    dow = pd.DataFrame({"Company": "x", "Symbol": [f"D{i}" for i in range(30)], "Industry": "y"})
    t, sym, sec = F._pick([small, dow], 25, want_sector=False)
    assert sym == "Symbol"
    try:
        F._pick([small], 25)
        assert False
    except ValueError:
        pass


def test_pick_handles_footnote_marks_and_industry_column():
    import pandas as pd
    t = pd.DataFrame({"Ticker[2]": [f"T{i}" for i in range(100)], "ICB Industry[3]": "Energy"})
    _, sym, sec = F._pick([t], 90)
    assert sym == "Ticker[2]" and sec == "ICB Industry[3]"
    d = pd.DataFrame({"Symbol[1]": [f"D{i}" for i in range(30)]})
    assert F._pick([d], 25, want_sector=False)[1] == "Symbol[1]"


def test_muka_index_equal_weight_and_membership():
    cfg = {"inception": "2025-01-02", "base": 100, "themes": {"T": ["A", "B"]}, "added": {"C": "2025-01-06"}, "removed": {}}
    mk2 = lambda cs: [{"d": d, "c": c} for d, c in zip(["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07"], cs)]
    rows = {"SPY": mk2([100, 100, 100, 100]), "A": mk2([10, 11, 11, 11]), "B": mk2([10, 10, 10, 10]), "C": mk2([5, 5, 5, 10])}
    m = F.muka_index(rows, cfg)
    # day2 +5% (A +10%, B 0); day3 0%; day4 C joined at the 01-06 close, so counts: A 0, B 0, C +100% => +33.3%
    assert m["level"][1] == 105.0 and m["level"][2] == 105.0
    assert abs(m["level"][3] - 105 * (1 + 1 / 3)) < 0.01
    assert m["spy_pct"] == 0.0


def test_muka_universe_is_equal_weight():
    u = F.muka_universe(F.load_muka())
    assert u["equal"] and len(F.muka_symbols(F.load_muka())) == 35


def test_ai_scores_and_defaults():
    import ai
    assert ai.score("NVDA") == 4 and ai.score("XOM") == 0
    assert ai.score("ZZZZ", "Information Technology") == 2
    assert ai.score("ZZZZ", "Information Technology", "Semiconductors") == 3
    assert ai.score("ZZZZ", "Energy") == 0
    assert all(0 <= v <= 4 for v in ai.EXPLICIT.values())


def test_fundamentals_scores_and_refresh():
    import fundamentals as FD
    strong = {"currentPrice": 100, "targetMeanPrice": 130, "trailingEps": 4, "forwardEps": 5.5, "trailingPE": 20, "forwardPE": 18,
              "priceToBook": 2, "pegRatio": 1.0, "enterpriseToEbitda": 12, "recommendationMean": 1.9, "revenueGrowth": 0.2,
              "returnOnEquity": 0.3, "profitMargins": 0.25, "earningsGrowth": 0.2, "currentRatio": 2, "debtToEquity": 30,
              "freeCashflow": 5, "totalCash": 10, "totalDebt": 5, "dividendRate": 3, "payoutRatio": 0.4, "fiveYearAvgDividendYield": 2.0,
              "longBusinessSummary": "A. " * 300}
    assert FD.scores(strong) == [6, 6, 6, 6, 5]      # 3% yield: not 4% or more
    assert FD.scores({}) == [0, 0, 0, 0, 0]
    assert len(FD.short(strong["longBusinessSummary"])) <= 335
    cache = {}
    n = FD.refresh(["A", "B", "C"], cache, ticker=lambda s: strong if s != "B" else {}, pause=0)
    assert n == 2 and set(cache) == {"A", "C"}
    assert FD.refresh(["A", "C"], cache, ticker=lambda s: 1 / 0, pause=0) == 0   # fresh entries are not refetched


def test_insider_summary_counts_only_open_market_buys_and_sells():
    import pandas as pd
    import insiders as I
    from datetime import date
    df = pd.DataFrame([
        {"Insider": "JANE DOE", "Position": "CEO", "Text": "Purchase at price 10.00 per share.", "Start Date": pd.Timestamp("2026-11-10"), "Value": 200000, "Shares": 20000},
        {"Insider": "JOHN ROE", "Position": "Director", "Text": "Purchase at price 10.50 per share.", "Start Date": pd.Timestamp("2026-10-20"), "Value": 50000, "Shares": 5000},
        {"Insider": "JANE DOE", "Position": "CEO", "Text": "Stock Award(Grant) at price 0.", "Start Date": pd.Timestamp("2026-11-01"), "Value": 900000, "Shares": 1},
        {"Insider": "SAM LEE", "Position": "CFO", "Text": "Sale at price 11.00 per share.", "Start Date": pd.Timestamp("2026-11-05"), "Value": 110000, "Shares": 10000},
        {"Insider": "OLD BUYER", "Position": "Director", "Text": "Purchase at price 9.", "Start Date": pd.Timestamp("2026-01-05"), "Value": 99999, "Shares": 1},
    ])
    s = I.summarise(I.normalise(df), today=date(2026, 11, 25))
    assert s["b"] == 2 and s["n"] == 2 and s["bv"] == 250000 and s["sv"] == 110000      # grant and old buy ignored
    assert s["last"] == "2026-11-10" and s["top"]["name"] == "Jane Doe" and s["top"]["pos"] == "CEO"
    assert I.summarise([], today=date(2026, 11, 25)) == {}
    cache = {}
    assert I.refresh(["A", "B"], cache, ticker=lambda s: df if s == "A" else (_ for _ in ()).throw(RuntimeError("x")), pause=0) == 1
    assert "A" in cache["_ins"] and "B" not in cache["_ins"]
