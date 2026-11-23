import random
import fetch as F


def mk(n=80, drift=0.002, seed=1, vol=1_000_000):
    rnd = random.Random(seed)
    p, out = 100.0, []
    for i in range(n):
        p *= 1 + drift + rnd.uniform(-0.004, 0.004)
        out.append({"d": f"2026-{1 + i // 28:02d}-{i % 28 + 1:02d}", "o": p, "h": p * 1.01, "l": p * 0.99, "c": p, "v": vol})
    return out


def test_build_signals_and_sectors():
    syms = {s for ss in F.SECTORS.values() for s in ss} | set(F.INDICES)
    bars, snaps = {}, {}
    for i, s in enumerate(sorted(syms)):
        b = mk(drift=-0.004 if s == "SPY" else (0.004 if i % 2 else -0.004), seed=i)
        bars[s] = b
        snaps[s] = {"price": b[-1]["c"] * 1.01, "volume": 900_000, "last_date": "2099-01-01", "prev_close": b[-1]["c"]}
    data = F.build(bars, snaps)
    assert data["regime"]["ok"] is False
    n = sum(len(s["items"]) for s in data["sectors"])
    assert n == len(syms) - len(F.INDICES) or n >= 60
    sigs = {i["signal"] for s in data["sectors"] for i in s["items"]}
    assert F.BUY not in sigs                      # never a plain buy while SPY is below its 50-day
    assert {F.AVOID, F.WATCH} & sigs
    assert set(data["indices"]) == set(F.INDICES)
    assert all(i["d1"] is not None for s in data["sectors"] for i in s["items"])


def test_short_history_skipped():
    bars = {"MSFT": mk(n=10)}
    snaps = {"MSFT": {"price": 100, "volume": 1, "last_date": "2099-01-01", "prev_close": 99}}
    assert F.build(bars, snaps)["sectors"] == []
