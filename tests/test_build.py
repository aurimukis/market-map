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
    g = F.group([("A", "X"), ("B", "X"), ("C", "Y")])
    assert g == [{"name": "X", "symbols": ["A", "B"]}, {"name": "Y", "symbols": ["C"]}]


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
