"""Check the generated supplier and bill behaviour against the persona table (docs/personas.md).

The check reads only the statements, the vendors' personas and the features. It never reads an outcome (defaulted,
scorecard_p, repayment_status): the generator is judged against the written persona table, not against model results.

    python src/persona_check.py                     full data: data/synthetic, data/interim, data/processed
    python src/persona_check.py --generate 200      a fresh in-memory run of the generator (200 vendors, seed 42)

Persona table rows checked (personas.md, amounts per 90 days before an application unless noted):
    Supplier payments (buy goods): stable "regular, weekly"; growing "regular, growing"; seasonal "follow the season";
                                   new "small and irregular"; struggling "rare, shrinking"
    Bill payments (rent, electricity): stable "regular, on time"; growing "regular"; seasonal "irregular in off-peak";
                                   new "few or none"; struggling "often missed or late"
    Description, growing: "restocks with Fuliza"; Fuliza use, struggling: "frequent"
tests/test_personas.py runs the same rules on a small generated sample, so the table and the generator cannot drift
apart again without a failing test.
"""
import argparse
import datetime as dt
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clean  # noqa: E402
import config as C  # noqa: E402
import features as Fe  # noqa: E402
import generator as G  # noqa: E402

PERSONA_ORDER = ["stable", "growing", "seasonal", "new", "struggling"]
TX_COLUMNS = ["vendor_id", "completion_time", "txn_type", "is_failed", "fuliza_funded", "paid_in", "withdrawn"]


# ------------------------------------------------------------------ data
def generate(n_vendors: int, seed: int = C.SEED, max_months: int = 0):
    """An in-memory run of the generator: (vendors, applications, cleaned transactions, features)."""
    rng = np.random.default_rng(seed)
    end = dt.datetime.strptime(C.END_DATE, "%Y-%m-%d")
    rows, vendors, apps, counter = [], [], [], [0]
    for i in range(1, n_vendors + 1):
        v = G.make_vendor(rng, i, max_months)
        total = v["history_days"] + C.OBS_WINDOW_DAYS
        start = end - dt.timedelta(days=total - 1)
        va = G.make_applications(rng, v, start, counter)
        shocks = sorted(((dt.date.fromisoformat(x["application_date"]) - start.date()).days, x["hidden_shock"]) for x in va)
        G.simulate_vendor(rng, v, end, rows, total, shocks)
        apps.extend(va)
        vendors.append({"vendor_id": v["vendor_id"], "persona": v["persona"], "start_date": start.date().isoformat(),
                        "history_days": v["history_days"]})
    tx = clean.clean(G.to_frame(rows, 0), as_of="2099-12-31")
    ve, ap = pd.DataFrame(vendors), pd.DataFrame(apps)
    ap["application_date"] = pd.to_datetime(ap.application_date)
    feat = pd.concat([ap[["application_id", "vendor_id", "application_date"]].reset_index(drop=True),
                      Fe.build(tx, ap).reset_index(drop=True)], axis=1).merge(ve[["vendor_id", "persona"]], on="vendor_id")
    return ve, ap, tx[TX_COLUMNS], feat


def load_full(synthetic="data/synthetic", interim="data/interim", processed="data/processed"):
    """The full run from disk, reading the cleaned transactions one row group at a time (only the columns needed)."""
    import pyarrow.parquet as pq
    ve = pd.read_parquet(os.path.join(synthetic, "vendors.parquet"))
    ve["history_days"] = ve.statement_days - C.OBS_WINDOW_DAYS
    ap = pd.read_parquet(os.path.join(synthetic, "loan_applications.parquet"))
    ap["application_date"] = pd.to_datetime(ap.application_date)
    feat = pd.read_parquet(os.path.join(processed, "features.parquet"),
                           columns=["application_id", "vendor_id", "application_date", "persona", "supplier_count_90",
                                    "paybill_months_paid_90", "near_zero_day_share_90", "fuliza_draws_90", "history_days"])
    pf = pq.ParquetFile(os.path.join(interim, "transactions_clean.parquet"))
    seasonal = set(ve.vendor_id[ve.persona == "seasonal"])
    parts = []
    for i in range(pf.num_row_groups):
        t = pf.read_row_group(i, columns=TX_COLUMNS).to_pandas()
        t = t[~t.is_failed]
        keep = t.txn_type.isin(["BUY_GOODS_OUT", "PAYBILL_OUT"]) | (t.txn_type.isin(Fe.INCOME) & t.vendor_id.isin(seasonal))
        parts.append(t[keep])                                 # income rows only for the seasonal check (memory)
    tx = pd.concat(parts, ignore_index=True)
    return ve, ap, tx, feat


# ------------------------------------------------------------------ measures
def measures(ve: pd.DataFrame, ap: pd.DataFrame, tx: pd.DataFrame, feat: pd.DataFrame) -> dict:
    """Per persona: supplier and bill measures (medians unless named otherwise). No outcome is read."""
    tx = tx[~tx.is_failed].copy()
    tx["completion_time"] = pd.to_datetime(tx.completion_time)
    ve = ve.set_index("vendor_id")
    sup = tx[tx.txn_type == "BUY_GOODS_OUT"]
    bills = tx[tx.txn_type == "PAYBILL_OUT"]
    inc = tx[tx.txn_type.isin(Fe.INCOME)]

    # Per application: share of the weeks before the application that have a supplier payment; Fuliza-funded restocks
    sup_by_v = {v: g.completion_time.to_numpy() for v, g in sup.groupby("vendor_id")}
    fz_by_v = {v: g.completion_time.to_numpy() for v, g in sup[sup.fuliza_funded].groupby("vendor_id")}
    app_rows = []
    for a in ap.merge(feat[["application_id", "history_days"]], on="application_id").itertuples(index=False):
        cut = np.datetime64(a.application_date, "ns")
        n_weeks = int(min(90, a.history_days) // 7)
        t = sup_by_v.get(a.vendor_id, np.array([], "datetime64[ns]"))
        age = (cut - t[(t < cut) & (t >= cut - np.timedelta64(n_weeks * 7, "D"))]) // np.timedelta64(7, "D")
        f = fz_by_v.get(a.vendor_id, np.array([], "datetime64[ns]"))
        app_rows.append({"application_id": a.application_id,
                         "weeks_with_supplier_share": len(np.unique(age)) / n_weeks if n_weeks else np.nan,
                         "fuliza_restock_90": int(((f < cut) & (f >= cut - np.timedelta64(90, "D"))).sum())})
    A = feat.merge(pd.DataFrame(app_rows), on="application_id")

    # Per vendor, over its history (statement start to the first possible application window end, i.e. before the
    # 90-day outcome window): supplier trend, seasonality of supplier spend and bills, Fuliza-funded restocks
    hist_end = {v: pd.Timestamp(r.start_date) + pd.Timedelta(days=int(r.history_days)) for v, r in ve.iterrows()}
    seasonal_ids = set(ve.index[ve.persona == "seasonal"])
    by_month = lambda d, col: d.groupby([d.vendor_id, d.completion_time.dt.to_period("M")])[col].sum()  # noqa: E731
    inc_m = by_month(inc[inc.vendor_id.isin(seasonal_ids)], "paid_in")
    sup_m = by_month(sup[sup.vendor_id.isin(seasonal_ids)], "withdrawn")
    bill_m = by_month(bills[bills.vendor_id.isin(seasonal_ids)], "withdrawn")
    sup_g = {v: g for v, g in sup.groupby("vendor_id")}
    bill_g = {v: g for v, g in bills.groupby("vendor_id")}
    vrows = []
    for v, r in ve.iterrows():
        end = hist_end[v]
        s = sup_g.get(v, sup.iloc[0:0])
        s = s[s.completion_time < end]
        start = pd.Timestamp(r.start_date)
        mid = start + (end - start) / 2
        first, second = s[s.completion_time < mid].withdrawn.sum(), s[s.completion_time >= mid].withdrawn.sum()
        row = {"vendor_id": v, "persona": r.persona, "spend_first_half": first, "spend_second_half": second,
               "supplier_trend": (second / first) if first > 0 else np.nan,
               "any_fuliza_restock": bool(len(s) and s.fuliza_funded.any())}
        # Bill punctuality over the full months of the history: on time = paid within a day of the vendor's usual bill
        # day (its most common day of the month); a late bill comes 5 to 12 days after it
        months = pd.period_range(start.to_period("M") + 1, end.to_period("M") - 1, freq="M")
        if len(months) >= 3:
            b = bill_g.get(v, bills.iloc[0:0])
            b = b[(b.completion_time >= months[0].start_time) & (b.completion_time <= months[-1].end_time)]
            day = b.completion_time.dt.day
            usual = int(day.mode().iloc[0]) if len(b) else 0
            on_time = set(b.completion_time[(day - usual).abs() <= 1].dt.to_period("M"))
            row["bill_on_time_share"] = len(on_time & set(months)) / len(months)
        if v in seasonal_ids and r.history_days >= 300 and v in inc_m.index.get_level_values(0):
            mi = inc_m.loc[v]
            mi = mi[(mi.index > start.to_period("M")) & (mi.index < end.to_period("M"))]   # full history months only
            if len(mi) >= 6:
                ms = (sup_m.loc[v] if v in sup_m.index.get_level_values(0) else pd.Series(dtype=float)).reindex(mi.index, fill_value=0.0)
                b = bill_m.loc[v] if v in bill_m.index.get_level_values(0) else pd.Series(dtype=float)
                paid = (b.reindex(mi.index, fill_value=0.0) > 0).astype(float)
                off = mi < mi.median()
                row.update({"supplier_income_corr": float(np.corrcoef(ms, mi)[0, 1]) if ms.std() > 0 else np.nan,
                            "bill_paid_share_peak": float(paid[~off].mean()), "bill_paid_share_offpeak": float(paid[off].mean())})
        vrows.append(row)
    V = pd.DataFrame(vrows)

    out = {}
    for p in PERSONA_ORDER:
        a, w = A[A.persona == p], V[V.persona == p]
        if a.empty:
            continue
        s_amt = sup[sup.vendor_id.isin(w.vendor_id)].withdrawn
        out[p] = {
            "applications": int(len(a)), "vendors": int(len(w)),
            "supplier_count_90_median": float(a.supplier_count_90.median()),
            "supplier_count_90_mean": float(a.supplier_count_90.mean()),
            "weeks_with_supplier_share_median": float(a.weeks_with_supplier_share.median()),
            "supplier_payment_median_kes": float(s_amt.median()) if len(s_amt) else np.nan,
            "supplier_trend_median": float(w.supplier_trend.median()),
            # all the persona's vendors together (information only: a few vendors with a trend borrowed from another
            # persona, the designed overlap, can dominate the sum, so the rules use the median vendor)
            "supplier_trend_pooled": float(w.spend_second_half.sum() / w.spend_first_half.sum()) if w.spend_first_half.sum() else np.nan,
            "paybill_months_paid_90_median": float(a.paybill_months_paid_90.median()),
            "paybill_months_paid_90_mean": float(a.paybill_months_paid_90.mean()),
            "bill_on_time_share_median": float(w.bill_on_time_share.median()) if "bill_on_time_share" in w and
            w.bill_on_time_share.notna().any() else np.nan,
            "share_vendors_with_fuliza_restock": float(w.any_fuliza_restock.mean()),
            "share_apps_with_fuliza_restock_90": float((a.fuliza_restock_90 > 0).mean()),
            "fuliza_draws_90_median": float(a.fuliza_draws_90.median()),
            "near_zero_days_per_month_median": float(a.near_zero_day_share_90.median() * 30),
        }
        if p == "seasonal" and "supplier_income_corr" in w:
            out[p].update({"supplier_income_corr_median": float(w.supplier_income_corr.median()),
                           "bill_paid_share_peak_mean": float(w.bill_paid_share_peak.mean()),
                           "bill_paid_share_offpeak_mean": float(w.bill_paid_share_offpeak.mean())})
    return out


# ------------------------------------------------------------------ the persona table as rules
def rules(m: dict) -> list:
    """(persona table cell, rule, holds?) for every supplier, bill and Fuliza-restock cell."""
    s, g, se, n, st = (m[p] for p in PERSONA_ORDER)
    R = [
        ("supplier, stable: regular, weekly", "weeks with a supplier payment >= 75%", s["weeks_with_supplier_share_median"] >= 0.75),
        ("supplier, growing: regular", "weeks with a supplier payment >= 75%", g["weeks_with_supplier_share_median"] >= 0.75),
        ("supplier, growing: growing", "supplier spend, 2nd half of history / 1st half > 1.1 (median vendor)", g["supplier_trend_median"] > 1.1),
        ("supplier, new: small and irregular", "weeks with a payment below stable and growing, and payments smaller than stable's",
         n["weeks_with_supplier_share_median"] < min(s["weeks_with_supplier_share_median"], g["weeks_with_supplier_share_median"])
         and n["supplier_payment_median_kes"] < s["supplier_payment_median_kes"]),
        ("supplier, struggling: rare", "at most half the supplier payments of stable, growing and seasonal, "
         "and weeks with a payment <= 40%",
         st["supplier_count_90_median"] <= 0.5 * min(x["supplier_count_90_median"] for x in (s, g, se))
         and st["weeks_with_supplier_share_median"] <= 0.40),
        ("supplier, struggling: shrinking", "supplier spend, 2nd half of history / 1st half < 0.9 (median vendor)", st["supplier_trend_median"] < 0.9),
        ("bills, stable: regular, on time", "median months with a bill paid in 90 days >= 3, and >= 85% of months paid on time",
         s["paybill_months_paid_90_median"] >= 3 and s["bill_on_time_share_median"] >= 0.85),
        ("bills, growing: regular", "median months with a bill paid in 90 days >= 3", g["paybill_months_paid_90_median"] >= 3),
        ("bills, new: few or none", "median months with a bill paid in 90 days <= 1", n["paybill_months_paid_90_median"] <= 1),
        ("bills, struggling: often missed or late", "share of months paid on time at least 20 points below stable and "
         "growing, and fewer months paid than both",
         st["bill_on_time_share_median"] <= min(s["bill_on_time_share_median"], g["bill_on_time_share_median"]) - 0.20
         and st["paybill_months_paid_90_mean"] < min(s["paybill_months_paid_90_mean"], g["paybill_months_paid_90_mean"])),
        ("growing: restocks with Fuliza", "share of vendors with a Fuliza-funded restock >= 50% and above stable",
         g["share_vendors_with_fuliza_restock"] >= 0.5 and g["share_vendors_with_fuliza_restock"] > s["share_vendors_with_fuliza_restock"]),
        ("Fuliza, struggling: frequent", "most Fuliza draws in 90 days of all personas",
         st["fuliza_draws_90_median"] >= max(x["fuliza_draws_90_median"] for x in (s, g, se, n))),
    ]
    if "supplier_income_corr_median" in se:
        R += [("supplier, seasonal: follow the season", "monthly supplier spend moves with monthly income (correlation > 0.3)",
               se["supplier_income_corr_median"] > 0.3),
              ("bills, seasonal: irregular in off-peak", "share of months with a bill paid lower off-peak than in peak months",
               se["bill_paid_share_offpeak_mean"] < se["bill_paid_share_peak_mean"])]
    return R


def table(m: dict) -> str:
    keys = ["applications", "supplier_count_90_median", "supplier_count_90_mean", "weeks_with_supplier_share_median",
            "supplier_payment_median_kes", "supplier_trend_median", "supplier_trend_pooled", "paybill_months_paid_90_median",
            "paybill_months_paid_90_mean", "bill_on_time_share_median",
            "share_vendors_with_fuliza_restock", "share_apps_with_fuliza_restock_90", "fuliza_draws_90_median",
            "near_zero_days_per_month_median"]
    L = ["| measure | " + " | ".join(p for p in PERSONA_ORDER if p in m) + " |", "|---|" + "---|" * len(m)]
    for k in keys:
        L.append(f"| {k} | " + " | ".join(f"{m[p][k]:.2f}" if isinstance(m[p][k], float) else str(m[p][k]) for p in PERSONA_ORDER if p in m) + " |")
    se = m.get("seasonal", {})
    if "supplier_income_corr_median" in se:
        L.append(f"\nseasonal: supplier spend vs income correlation (median) {se['supplier_income_corr_median']:.2f}; "
                 f"months with a bill paid: peak {se['bill_paid_share_peak_mean']:.0%}, off-peak {se['bill_paid_share_offpeak_mean']:.0%}")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--generate", type=int, default=0, help="check a fresh in-memory run of this many vendors instead")
    ap.add_argument("--seed", type=int, default=C.SEED)
    ap.add_argument("--max-months", type=int, default=0)
    ap.add_argument("--json", default=None, help="also write the measures to this file")
    a = ap.parse_args()
    data = generate(a.generate, a.seed, a.max_months) if a.generate else load_full()
    m = measures(*data)
    print(table(m), "\n")
    bad = 0
    for cell, rule, ok in rules(m):
        bad += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {cell}  ({rule})")
    if a.json:
        with open(a.json, "w") as f:
            json.dump(m, f, indent=1)
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
