"""
Adobe (ADBE) discounted cash flow model.

Pulls reported financials from SEC EDGAR (XBRL companyfacts API) and market
data from Yahoo Finance, builds a 10-year unlevered FCF forecast, values the
equity with a Gordon-growth terminal value (exit-multiple cross-check), and
writes scenario, sensitivity and reverse-DCF tables.

Usage:
    python dcf_model.py                 # live pull, writes ./outputs
    python dcf_model.py --offline       # reuse cached ./data JSON
    python dcf_model.py --price 250 --rf 0.045 --erp 0.055

Units: USD millions unless noted; per-share figures in USD.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
OUT = HERE / "outputs"

TICKER = "ADBE"
CIK = "0000796343"
SEC_HEADERS = {"User-Agent": "DCF research essa_shak@hotmail.com"}
YEARS = 10


# --------------------------------------------------------------------------
# 1. Data pull
# --------------------------------------------------------------------------
def fetch_companyfacts(offline: bool) -> dict:
    path = DATA / f"companyfacts_{CIK}.json"
    if offline and path.exists():
        return json.loads(path.read_text())
    import requests

    r = requests.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json",
                     headers=SEC_HEADERS, timeout=30)
    r.raise_for_status()
    DATA.mkdir(exist_ok=True)
    path.write_text(r.text)
    return r.json()


def fetch_market(offline: bool) -> dict:
    path = DATA / "market.json"
    if offline and path.exists():
        return json.loads(path.read_text())
    import yfinance as yf

    info = yf.Ticker(TICKER).info
    tnx = yf.Ticker("^TNX").history(period="5d")["Close"].iloc[-1] / 100
    mkt = {
        "price": info.get("currentPrice") or info.get("previousClose"),
        "beta_raw": info.get("beta"),
        "rf": float(tnx),
        "high_52w": info.get("fiftyTwoWeekHigh"),
        "low_52w": info.get("fiftyTwoWeekLow"),
        "target_mean": info.get("targetMeanPrice"),
        "forward_eps": info.get("forwardEps"),
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    DATA.mkdir(exist_ok=True)
    path.write_text(json.dumps(mkt, indent=2))
    return mkt


def _facts(cf: dict, tag: str, unit: str = "USD") -> pd.DataFrame:
    rows = cf["facts"]["us-gaap"][tag]["units"][unit]
    df = pd.DataFrame(rows)
    df = df[df["form"].isin(["10-K", "10-Q", "10-K/A", "10-Q/A"])].copy()
    df["end"] = pd.to_datetime(df["end"])
    if "start" in df:
        df["start"] = pd.to_datetime(df["start"])
        df["days"] = (df["end"] - df["start"]).dt.days
    # keep the most recently filed value for each period
    keys = ["start", "end"] if "start" in df else ["end"]
    return df.sort_values("filed").drop_duplicates(keys, keep="last")


def flow_series(cf: dict, tags: list[str]) -> tuple[pd.Series, float]:
    """Annual fiscal-year values plus trailing-twelve-month value for a flow item."""
    for tag in tags:
        if tag in cf["facts"]["us-gaap"]:
            df = _facts(cf, tag)
            if "days" in df and not df.empty:
                break
    annual = df[df["days"].between(350, 380)].set_index("end")["val"].sort_index()
    latest_end = df["end"].max()
    ytd = df[(df["end"] == latest_end)].sort_values("days").iloc[-1]
    if ytd["days"] >= 350:  # latest filing is a 10-K
        return annual, float(ytd["val"])
    prior = df[(abs((df["end"] - (latest_end - pd.Timedelta(days=364))).dt.days) <= 7)
               & (abs(df["days"] - ytd["days"]) <= 7)].iloc[-1]
    last_fy = annual.iloc[-1]
    return annual, float(last_fy + ytd["val"] - prior["val"])


def instant(cf: dict, tag: str) -> tuple[float, pd.Timestamp]:
    df = _facts(cf, tag)
    row = df.sort_values("end").iloc[-1]
    return float(row["val"]), row["end"]


def load_financials(cf: dict) -> tuple[pd.DataFrame, dict]:
    m = 1e6
    items = {
        "Revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"],
        "EBIT": ["OperatingIncomeLoss"],
        "Pretax income": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"],
        "Tax expense": ["IncomeTaxExpenseBenefit"],
        "Net income": ["NetIncomeLoss"],
        "D&A": ["DepreciationDepletionAndAmortization"],
        "SBC": ["ShareBasedCompensation"],
        "CFO": ["NetCashProvidedByUsedInOperatingActivities"],
        "Capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
        "Buybacks": ["PaymentsForRepurchaseOfCommonStock"],
        "Interest expense": ["InterestExpenseNonoperating", "InterestExpense"],
    }
    hist, ttm = {}, {}
    for name, tags in items.items():
        a, t = flow_series(cf, tags)
        hist[name] = a / m
        ttm[name] = t / m
    hist = pd.DataFrame(hist)
    hist.index = [f"FY{d.year}" for d in hist.index]
    hist = hist.loc[[c for c in hist.index if int(c[2:]) >= 2019]]
    hist.loc["TTM"] = pd.Series(ttm)
    hist["FCF"] = hist["CFO"] - hist["Capex"]
    hist["FCF less SBC"] = hist["FCF"] - hist["SBC"]
    hist["Revenue growth"] = hist["Revenue"].pct_change()
    hist.loc["TTM", "Revenue growth"] = np.nan  # not comparable to prior FY
    hist["EBIT margin"] = hist["EBIT"] / hist["Revenue"]
    hist["Tax rate"] = hist["Tax expense"] / hist["Pretax income"]
    hist["D&A % rev"] = hist["D&A"] / hist["Revenue"]
    hist["Capex % rev"] = hist["Capex"] / hist["Revenue"]
    hist["SBC % rev"] = hist["SBC"] / hist["Revenue"]

    cash, bs_date = instant(cf, "CashAndCashEquivalentsAtCarryingValue")
    sti, _ = instant(cf, "ShortTermInvestments")
    ltd, _ = instant(cf, "LongTermDebt")
    std, _ = instant(cf, "DebtCurrent")
    shares = cf["facts"]["dei"]["EntityCommonStockSharesOutstanding"]["units"]["shares"][-1]
    bs = {
        "balance_sheet_date": bs_date.strftime("%Y-%m-%d"),
        "cash": (cash + sti) / m,
        "debt": (ltd + std) / m,
        "shares": shares["val"] / m,
        "shares_date": shares["end"],
    }
    return hist, bs


# --------------------------------------------------------------------------
# 2. Assumptions
# --------------------------------------------------------------------------
@dataclass
class Assumptions:
    name: str
    growth_start: float          # year-1 revenue growth
    growth_end: float            # year-10 revenue growth (linear fade)
    margin_start: float          # year-1 GAAP EBIT margin (SBC is a cost, not added back)
    margin_end: float            # year-10 / terminal EBIT margin
    terminal_growth: float
    tax_rate: float = 0.21
    capex_start: float = 0.010   # % revenue
    capex_end: float = 0.015
    da_end: float = 0.015        # D&A converges to capex by terminal year
    nwc_pct_delta_rev: float = -0.05  # deferred revenue funds growth (negative = cash inflow)
    exit_multiple: float = 12.0  # EV / EBITDA cross-check
    growth_shift: float = 0.0    # parallel shift used in sensitivities
    prob: float = 0.0


@dataclass
class Capital:
    rf: float
    beta: float
    erp: float = 0.050
    pretax_kd: float = 0.045
    tax_rate: float = 0.21
    price: float = 0.0
    shares: float = 0.0
    debt: float = 0.0
    cash: float = 0.0
    wacc_override: float | None = None

    @property
    def ke(self) -> float:
        return self.rf + self.beta * self.erp

    @property
    def wacc(self) -> float:
        if self.wacc_override is not None:
            return self.wacc_override
        e = self.price * self.shares
        d = self.debt
        return e / (e + d) * self.ke + d / (e + d) * self.pretax_kd * (1 - self.tax_rate)


def scenarios(base_tax: float) -> dict[str, Assumptions]:
    return {
        "Bear": Assumptions("Bear: GenAI erodes seats & pricing", 0.05, 0.00, 0.34, 0.27,
                            0.010, base_tax, exit_multiple=8.0, prob=0.25),
        "Base": Assumptions("Base: steady fade to mature growth", 0.10, 0.035, 0.36, 0.34,
                            0.025, base_tax, exit_multiple=12.0, prob=0.50),
        "Bull": Assumptions("Bull: Firefly/GenStudio monetise", 0.12, 0.05, 0.37, 0.39,
                            0.030, base_tax, exit_multiple=16.0, prob=0.25),
    }


# --------------------------------------------------------------------------
# 3. DCF engine
# --------------------------------------------------------------------------
def project(a: Assumptions, base: pd.Series) -> pd.DataFrame:
    t = np.arange(1, YEARS + 1)
    fade = (t - 1) / (YEARS - 1)
    growth = a.growth_start + (a.growth_end - a.growth_start) * fade + a.growth_shift
    margin = a.margin_start + (a.margin_end - a.margin_start) * fade
    capex_pct = a.capex_start + (a.capex_end - a.capex_start) * fade
    da_pct = base["D&A % rev"] + (a.da_end - base["D&A % rev"]) * fade

    rev = base["Revenue"] * np.cumprod(1 + growth)
    prev_rev = np.concatenate([[base["Revenue"]], rev[:-1]])
    ebit = rev * margin
    nopat = ebit * (1 - a.tax_rate)
    da = rev * da_pct
    capex = rev * capex_pct
    d_nwc = (rev - prev_rev) * a.nwc_pct_delta_rev
    fcf = nopat + da - capex - d_nwc
    return pd.DataFrame({
        "Revenue": rev, "Growth": growth, "EBIT": ebit, "EBIT margin": margin,
        "NOPAT": nopat, "D&A": da, "Capex": capex, "Change in NWC": d_nwc,
        "Unlevered FCF": fcf, "EBITDA": ebit + da,
    }, index=[f"Y{i}" for i in t])


def value(a: Assumptions, base: pd.Series, cap: Capital, method: str = "gordon") -> dict:
    proj = project(a, base)
    w, g = cap.wacc, a.terminal_growth
    t = np.arange(1, YEARS + 1)
    df_mid = (1 + w) ** -(t - 0.5)          # mid-year convention
    pv_fcf = float((proj["Unlevered FCF"] * df_mid).sum())

    last = proj.iloc[-1]
    if method == "gordon":
        # terminal FCF: reinvestment consistent with g (capex = D&A, NWC grows with revenue)
        rev_next = last["Revenue"] * (1 + g)
        fcf_next = (rev_next * last["EBIT margin"] * (1 - a.tax_rate)
                    - (rev_next - last["Revenue"]) * a.nwc_pct_delta_rev)
        tv = fcf_next / (w - g)
    else:
        tv = last["EBITDA"] * a.exit_multiple
    pv_tv = tv * (1 + w) ** -(YEARS - 0.5) if method == "gordon" else tv * (1 + w) ** -YEARS
    ev = pv_fcf + pv_tv
    equity = ev - cap.debt + cap.cash
    px = equity / cap.shares
    return {"proj": proj, "pv_fcf": pv_fcf, "tv": tv, "pv_tv": pv_tv, "ev": ev,
            "equity": equity, "price": px, "upside": px / cap.price - 1,
            "tv_share": pv_tv / ev, "wacc": w,
            "implied_exit": tv / last["EBITDA"] if method == "gordon" else a.exit_multiple}


# --------------------------------------------------------------------------
# 4. Sensitivities & reverse DCF
# --------------------------------------------------------------------------
def sens_wacc_g(a, base, cap):
    waccs = np.round(np.arange(0.090, 0.1301, 0.005), 3)
    gs = np.round(np.arange(0.010, 0.0401, 0.005), 3)
    tbl = pd.DataFrame(index=[f"{w:.1%}" for w in waccs], columns=[f"{g:.1%}" for g in gs], dtype=float)
    for w in waccs:
        for g in gs:
            tbl.loc[f"{w:.1%}", f"{g:.1%}"] = value(replace(a, terminal_growth=g),
                                                   base, replace(cap, wacc_override=w))["price"]
    tbl.index.name, tbl.columns.name = "WACC", "Terminal g"
    return tbl


def sens_growth_margin(a, base, cap):
    shifts = [-0.06, -0.04, -0.02, 0.0, 0.02, 0.04]
    margins = [0.26, 0.29, 0.32, 0.34, 0.36, 0.38, 0.40]
    tbl = pd.DataFrame(index=[f"{s:+.0%}" for s in shifts], columns=[f"{m:.0%}" for m in margins], dtype=float)
    for s in shifts:
        for mg in margins:
            tbl.loc[f"{s:+.0%}", f"{mg:.0%}"] = value(replace(a, growth_shift=s, margin_end=mg), base, cap)["price"]
    tbl.index.name, tbl.columns.name = "Rev growth shift (pp/yr)", "Terminal EBIT margin"
    return tbl


def sens_wacc_multiple(a, base, cap):
    waccs = np.round(np.arange(0.090, 0.1301, 0.01), 3)
    mults = [8, 10, 12, 14, 16, 18]
    tbl = pd.DataFrame(index=[f"{w:.1%}" for w in waccs], columns=[f"{m}x" for m in mults], dtype=float)
    for w in waccs:
        for mlt in mults:
            tbl.loc[f"{w:.1%}", f"{mlt}x"] = value(replace(a, exit_multiple=mlt), base,
                                                  replace(cap, wacc_override=w), method="exit")["price"]
    tbl.index.name, tbl.columns.name = "WACC", "Exit EV/EBITDA"
    return tbl


def reverse_dcf(a, base, cap) -> dict:
    """Solve for the flat 10-yr revenue growth (base margins) that justifies today's price."""
    def px(gr):
        return value(replace(a, growth_start=gr, growth_end=gr, terminal_growth=min(gr, a.terminal_growth)),
                     base, cap)["price"]
    lo, hi = -0.10, 0.20
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if px(mid) < cap.price else (lo, mid)
    flat = (lo + hi) / 2

    def px_m(mg):
        return value(replace(a, margin_start=mg, margin_end=mg), base, cap)["price"]
    lo, hi = 0.0, 0.6
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if px_m(mid) < cap.price else (lo, mid)
    return {"implied_flat_growth": flat, "implied_flat_margin_at_base_growth": (lo + hi) / 2}


# --------------------------------------------------------------------------
# 5. Run
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use cached data/ files")
    ap.add_argument("--price", type=float)
    ap.add_argument("--rf", type=float)
    ap.add_argument("--beta", type=float, help="override (default: Blume-adjusted Yahoo beta)")
    ap.add_argument("--erp", type=float, default=0.050)
    args = ap.parse_args()

    cf = fetch_companyfacts(args.offline)
    mkt = fetch_market(args.offline)
    hist, bs = load_financials(cf)
    ttm = hist.loc["TTM"]

    tax = float(np.clip(ttm["Tax rate"], 0.15, 0.25))
    beta = args.beta if args.beta else 0.67 * mkt["beta_raw"] + 0.33   # Blume adjustment
    kd = ttm["Interest expense"] / bs["debt"]
    cap = Capital(rf=args.rf or mkt["rf"], beta=beta, erp=args.erp, pretax_kd=kd, tax_rate=tax,
                  price=args.price or mkt["price"], shares=bs["shares"], debt=bs["debt"], cash=bs["cash"])

    sc = scenarios(tax)
    res = {k: value(a, ttm, cap) for k, a in sc.items()}
    res_exit = {k: value(a, ttm, cap, method="exit") for k, a in sc.items()}
    weighted = sum(sc[k].prob * res[k]["price"] for k in sc)
    base = sc["Base"]
    s1, s2, s3 = sens_wacc_g(base, ttm, cap), sens_growth_margin(base, ttm, cap), sens_wacc_multiple(base, ttm, cap)
    rev = reverse_dcf(base, ttm, cap)

    # ---- outputs ----
    OUT.mkdir(exist_ok=True)
    summary_rows = []
    for k, a in sc.items():
        r, rx = res[k], res_exit[k]
        summary_rows.append({
            "Scenario": a.name, "Prob": a.prob,
            "Rev growth Y1->Y10": f"{a.growth_start:.1%} -> {a.growth_end:.1%}",
            "EBIT margin Y1->Y10": f"{a.margin_start:.0%} -> {a.margin_end:.0%}",
            "Terminal g": a.terminal_growth,
            "Y10 revenue ($bn)": r["proj"]["Revenue"].iloc[-1] / 1e3,
            "EV ($bn)": r["ev"] / 1e3, "Value/share (Gordon)": r["price"],
            "Upside": r["upside"], "TV % of EV": r["tv_share"], "Implied exit EV/EBITDA": r["implied_exit"],
            "Value/share (exit multiple)": rx["price"], "Exit multiple": a.exit_multiple,
        })
    summary = pd.DataFrame(summary_rows)

    with pd.ExcelWriter(OUT / "ADBE_DCF.xlsx") as xw:
        summary.to_excel(xw, sheet_name="Summary", index=False)
        hist.T.to_excel(xw, sheet_name="Historicals")
        for k in sc:
            res[k]["proj"].T.to_excel(xw, sheet_name=f"Projection_{k}")
        s1.to_excel(xw, sheet_name="Sens_WACC_g")
        s2.to_excel(xw, sheet_name="Sens_Growth_Margin")
        s3.to_excel(xw, sheet_name="Sens_WACC_ExitMultiple")
        pd.DataFrame({
            "Input": ["Price", "Risk-free (10Y UST)", "Raw beta", "Adj. beta", "ERP", "Cost of equity",
                      "Pre-tax cost of debt", "Tax rate", "WACC", "Shares (m)", "Debt ($m)", "Cash+ST inv ($m)",
                      "Balance sheet date", "Market data as of"],
            "Value": [cap.price, cap.rf, mkt["beta_raw"], cap.beta, cap.erp, cap.ke, cap.pretax_kd, cap.tax_rate,
                      cap.wacc, cap.shares, cap.debt, cap.cash, bs["balance_sheet_date"], mkt["as_of"]],
        }).to_excel(xw, sheet_name="WACC_Inputs", index=False)
    s1.to_csv(OUT / "sens_wacc_g.csv", float_format="%.0f")
    s2.to_csv(OUT / "sens_growth_margin.csv", float_format="%.0f")
    s3.to_csv(OUT / "sens_wacc_exit_multiple.csv", float_format="%.0f")
    summary.to_csv(OUT / "scenario_summary.csv", index=False)

    key = {
        "price": cap.price, "wacc": cap.wacc, "ke": cap.ke, "beta_adj": cap.beta, "rf": cap.rf,
        "tax": tax, "kd": kd, "shares": cap.shares, "net_cash": cap.cash - cap.debt,
        "scenario_values": {k: res[k]["price"] for k in sc},
        "scenario_values_exit": {k: res_exit[k]["price"] for k in sc},
        "prob_weighted": weighted, "prob_weighted_upside": weighted / cap.price - 1,
        "base_tv_share": res["Base"]["tv_share"], "base_implied_exit": res["Base"]["implied_exit"],
        "reverse_dcf": rev, "market": mkt, "balance_sheet": bs,
    }
    (OUT / "summary.json").write_text(json.dumps(key, indent=2, default=str))
    make_charts(hist, res, s1, cap, weighted)

    # ---- console report ----
    pd.set_option("display.width", 200, "display.max_columns", 20)
    fmt = lambda x: f"{x:,.0f}"
    print(f"\n=== {TICKER} DCF  |  price ${cap.price:.2f}  |  market data {mkt['as_of']} ===")
    print("\nHistoricals ($m):")
    cols = ["Revenue", "Revenue growth", "EBIT", "EBIT margin", "CFO", "Capex", "FCF", "SBC", "FCF less SBC", "Tax rate", "D&A % rev"]
    print(hist[cols].to_string(formatters={c: (lambda x: f"{x:.1%}") if c in ("Revenue growth", "EBIT margin", "Tax rate", "D&A % rev") else fmt for c in cols}))
    print(f"\nWACC {cap.wacc:.2%}  (rf {cap.rf:.2%}, beta {mkt['beta_raw']:.2f} adj. {cap.beta:.2f}, ERP {cap.erp:.1%}, "
          f"Ke {cap.ke:.2%}, Kd {kd:.2%}, tax {tax:.1%})")
    print(f"Cash ${cap.cash:,.0f}m, debt ${cap.debt:,.0f}m (net debt ${cap.debt - cap.cash:,.0f}m)  |  "
          f"shares {cap.shares:.1f}m  |  BS date {bs['balance_sheet_date']}")
    print("\nBase projection ($m):")
    proj = res["Base"]["proj"].T.astype(object)
    for row in proj.index:
        pct = row in ("Growth", "EBIT margin")
        proj.loc[row] = [f"{v:.1%}" if pct else f"{v:,.0f}" for v in res["Base"]["proj"][row]]
    print(proj.to_string())
    print("\nScenarios:")
    pct_cols = {"Prob": "{:.0%}", "Terminal g": "{:.1%}", "Upside": "{:+.0%}", "TV % of EV": "{:.0%}"}
    usd_cols = ("Value/share (Gordon)", "Value/share (exit multiple)")
    print(summary.to_string(index=False, formatters={
        c: (lambda f: (lambda x: f.format(x)))(pct_cols[c]) if c in pct_cols
        else (lambda x: f"${x:,.0f}") if c in usd_cols
        else (lambda x: f"{x:,.1f}") for c in summary.columns if c not in
        ("Scenario", "Rev growth Y1->Y10", "EBIT margin Y1->Y10")}))
    print(f"\nProbability-weighted value: ${weighted:.0f}  ({weighted / cap.price - 1:+.0%})")
    print(f"Reverse DCF: price implies flat {rev['implied_flat_growth']:.1%} revenue growth for 10y at base margins, "
          f"or a flat {rev['implied_flat_margin_at_base_growth']:.1%} EBIT margin at base growth")
    for name, t in [("WACC x terminal g", s1), ("Growth shift x terminal margin", s2), ("WACC x exit multiple", s3)]:
        print(f"\nSensitivity: {name} ($/share)")
        print(t.to_string(float_format=lambda x: f"{x:,.0f}"))


def make_charts(hist, res, s1, cap, weighted):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    ax = axes[0]
    labels = ["Bear", "Base", "Bull", "Prob-wtd"]
    vals = [res["Bear"]["price"], res["Base"]["price"], res["Bull"]["price"], weighted]
    colors = ["#b85450", "#4a6fa5", "#5b8c5a", "#555555"]
    ax.barh(labels, vals, color=colors)
    ax.axvline(cap.price, color="black", ls="--", lw=1)
    ax.text(cap.price, 3.45, f" price ${cap.price:.0f}", va="center", fontsize=9)
    for i, v in enumerate(vals):
        ax.text(v, i, f" ${v:.0f}", va="center", fontsize=9)
    ax.set_title("ADBE value per share by scenario")
    ax.invert_yaxis()
    ax.spines[["top", "right"]].set_visible(False)

    ax = axes[1]
    im = ax.imshow(s1.values.astype(float) / cap.price - 1, cmap="RdYlGn", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(s1.columns)), s1.columns)
    ax.set_yticks(range(len(s1.index)), s1.index)
    ax.set_xlabel("Terminal growth"); ax.set_ylabel("WACC")
    for i in range(s1.shape[0]):
        for j in range(s1.shape[1]):
            ax.text(j, i, f"{s1.values[i, j]:.0f}", ha="center", va="center", fontsize=8)
    ax.set_title("Base case: $/share, WACC x terminal g")
    fig.colorbar(im, ax=ax, label="Upside vs price", format=matplotlib.ticker.PercentFormatter(1.0))
    fig.tight_layout()
    fig.savefig(OUT / "adbe_dcf_charts.png", dpi=150)


if __name__ == "__main__":
    main()
