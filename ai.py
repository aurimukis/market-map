"""AI exposure score per stock: 4 core, 3 high, 2 medium, 1 low, 0 minimal.

A judgement call, not a measured number. It asks how much of the company's revenue, growth or cost base now depends on
AI spending: the chips, memory, networking, cloud, power and data centres behind it, then the software and services
selling it, then everything else. Anything not listed gets a default from its sector or industry.
"""

LABELS = ["Minimal", "Low", "Medium", "High", "Core"]

SCORES = {
    4: "NVDA AVGO AMD MU MSFT GOOGL GOOG AMZN META ORCL PLTR SMCI VRT ANET MRVL DELL TSM ASML",
    3: "AMAT LRCX KLAC TER QCOM INTC CSCO NOW CRM SNPS CDNS IBM EQIX DLR GEV CEG VST ETN PWR NRG APH GLW HPE NTAP WDC "
       "STX TSLA ADBE COHR CIEN JBL FIX TLN SAP LITE CRWV",
    2: "INTU WDAY ADSK PANW CRWD FTNT DDOG SNOW TXN ADI NXPI ON MCHP MPWR ACN IT CTSH UBER AAPL NFLX HON ROK EMR TT JCI "
       "CAT GE GEHC FSLR NVO TYL PTC ANSS EPAM GDDY AKAM FICO PAYX ADP SPOT ARM",
    1: "LLY ISRG V MA JPM AMT PLD UNH GS MS BLK SPGI MSCI MCO AZN NVS TMO DHR ABT MDT BSX SYK ZBH TMUS T VZ DIS WMT COST "
       "HD LOW DE UNP UPS FDX LMT RTX NOC GD BA",
    0: "XOM CVX COP SLB EOG OXY KO PEP PG MCD NKE SBUX NEM FCX LIN SHEL BRK.B JNJ PFE MRK ABBV AMGN",
}
EXPLICIT = {s: n for n, syms in SCORES.items() for s in syms.split()}

SECTOR_DEFAULT = {
    "Information Technology": 2, "Communication Services": 1, "Industrials": 1, "Utilities": 1,
    "Financials": 1, "Health Care": 1,
}
INDUSTRY_DEFAULT = [("semiconductor", 3), ("electronic manufacturing", 2), ("electrical", 2), ("construction & engineering", 2)]


def score(sym, sector=None, industry=None):
    if sym in EXPLICIT:
        return EXPLICIT[sym]
    ind = (industry or "").lower()
    for key, n in INDUSTRY_DEFAULT:
        if key in ind:
            return n
    return SECTOR_DEFAULT.get(sector, 0)
