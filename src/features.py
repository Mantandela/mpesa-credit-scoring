"""Stage 3: features (docs/data_dictionary.md section 4).

One row per loan application. Every feature is built ONLY from cleaned transactions completed before the
application date (strictly earlier than midnight at the start of `application_date`). No outcome is used here.

Run from the repo root:
    python src/features.py                      reads data/interim/transactions_clean and data/synthetic/{vendors,loan_applications}
    python src/features.py --skip-check         skip the leakage test (faster)

Writes:
    data/processed/features.parquet          one row per application: meta columns + feature columns
    data/processed/feature_columns.json      which columns are features and which are meta (ids, labels, slicing columns)
    docs/feature_report.md                   missing values per feature and a quick signal check

Never features: persona, latent_risk, hidden_shock, txn_type_true, gender (fairness check only), business_type and every
outcome column. They are kept in the meta columns for slicing and checking only.
Missing values are left as NaN on purpose (for example a ratio with no income). Impute inside the model pipeline.
"""
import argparse
import json
import os
import numpy as np
import pandas as pd

WINDOWS = (30, 60, 90)
INCOME = ("TILL_PAYMENT_IN", "SEND_MONEY_IN")
PAYMENT_OUT = ("SEND_MONEY_OUT", "BUY_GOODS_OUT", "PAYBILL_OUT", "AIRTIME_OUT")
NEAR_ZERO = 100                       # KES. End-of-day balance below this counts as near zero
META = ["application_id", "vendor_id", "application_date", "business_type", "gender", "persona"]
# Outcome and hidden columns (defaulted, repayment_status, hidden_shock, latent_risk, ...) are added by src/scorecard.py.


def load(d, name):
    for ext, fn in ((".parquet", pd.read_parquet), (".csv", pd.read_csv)):
        p = os.path.join(d, name + ext)
        if os.path.exists(p):
            return fn(p)
    raise SystemExit(f"{name} not found in {d}")


def save(df, folder, name):
    os.makedirs(folder, exist_ok=True)
    try:
        p = os.path.join(folder, name + ".parquet")
        df.to_parquet(p, index=False)
    except Exception:
        p = os.path.join(folder, name + ".csv")
        df.to_csv(p, index=False)
    return p


def _div(a, b):
    return float(a) / float(b) if b and not pd.isna(b) and b != 0 else np.nan


def daily_end_balance(past: pd.DataFrame, cut: pd.Timestamp) -> pd.Series:
    """End-of-day balance for every calendar day from the first transaction to the day before `cut`.
    Days without transactions carry the last balance forward."""
    eod = past.groupby(past.completion_time.dt.normalize())["balance"].last()
    days = pd.date_range(eod.index.min(), cut - pd.Timedelta(days=1), freq="D")
    return eod.reindex(days).ffill()


def build_row(g: pd.DataFrame, app) -> dict:
    """Features for one application. `g` is one vendor's cleaned transactions. Only rows before the date are used."""
    cut = pd.Timestamp(app.application_date).normalize()
    past = g[g.completion_time < cut]                       # <- the only place data is selected by time
    row = {"requested_amount": float(app.requested_amount), "requested_term_days": float(app.requested_term_days)}
    if past.empty:
        return {**row, "history_days": 0.0}
    first = past.completion_time.min().normalize()
    history = float((cut - first).days)
    row["history_days"] = history
    ok = past[~past.is_failed]
    bal = daily_end_balance(past, cut)

    def win(df, w):
        return df[df.completion_time >= cut - pd.Timedelta(days=w)]

    inc_all = ok[ok.txn_type.isin(INCOME)]
    income = {}
    for w in WINDOWS:
        obs = min(w, history)
        inc = win(inc_all, w)
        income[w] = inc.paid_in.sum()
        wk = win(ok, w)
        b = bal.iloc[-int(obs):] if obs >= 1 else bal.iloc[0:0]
        row[f"income_total_{w}"] = float(inc.paid_in.sum())
        row[f"income_count_{w}"] = float(len(inc))
        row[f"income_active_day_share_{w}"] = _div(inc.completion_time.dt.normalize().nunique(), obs)
        row[f"median_ticket_{w}"] = float(inc.paid_in.median()) if len(inc) else np.nan
        row[f"unique_senders_{w}"] = float(inc.counterparty_id.nunique())
        row[f"near_zero_day_share_{w}"] = float((b < NEAR_ZERO).mean()) if len(b) else np.nan
        row[f"fuliza_draws_{w}"] = float((wk.txn_type == "FULIZA_DRAW").sum())
        row[f"withdraw_share_of_income_{w}"] = _div(wk.loc[wk.txn_type == "WITHDRAW_AGENT", "withdrawn"].sum(), inc.paid_in.sum())

    # ---- 90-day detail
    w90 = win(ok, 90)
    inc90 = win(inc_all, 90)
    obs90 = min(90.0, history)
    # weekly stability: 7-day blocks counted back from the application date, only blocks inside the history
    age = (cut - inc90.completion_time).dt.days // 7
    n_blocks = int(min(12, history // 7))
    if n_blocks >= 3:
        wk_tot = inc90.assign(k=age)[lambda d: d.k < n_blocks].groupby("k").paid_in.sum().reindex(range(n_blocks), fill_value=0.0)
        row["weekly_income_cv_90"] = _div(wk_tot.std(ddof=0), wk_tot.mean())
    else:
        row["weekly_income_cv_90"] = np.nan
    if len(inc90):
        cnt = inc90.counterparty_id.map(inc90.counterparty_id.value_counts())
        row["repeat_sender_share_90"] = float((cnt >= 2).mean())
        row["till_share_90"] = float((inc90.txn_type == "TILL_PAYMENT_IN").mean())
    else:
        row["repeat_sender_share_90"] = row["till_share_90"] = np.nan
    sup = w90[w90.txn_type == "BUY_GOODS_OUT"]
    row["supplier_count_90"] = float(len(sup))
    row["supplier_spend_share_90"] = _div(sup.withdrawn.sum(), income[90])
    pb = w90[w90.txn_type == "PAYBILL_OUT"]
    row["paybill_months_paid_90"] = float(pb.completion_time.dt.to_period("M").nunique())
    pays = w90[w90.txn_type.isin(PAYMENT_OUT)]
    row["fuliza_funded_share_90"] = _div(pays.fuliza_funded.sum(), len(pays))
    all_pay_rows = win(past, 90)
    all_pay_rows = all_pay_rows[all_pay_rows.txn_type.isin(PAYMENT_OUT)]
    row["failed_payment_share_90"] = _div(all_pay_rows.is_failed.sum(), len(all_pay_rows))
    row["fee_share_of_income_90"] = _div(w90.loc[w90.txn_type == "FEE", "withdrawn"].sum(), income[90])
    dep = w90.loc[w90.txn_type == "DEPOSIT_AGENT", "paid_in"].sum()
    row["cash_deposit_share_90"] = _div(dep, dep + income[90])
    row["reversal_count_90"] = float((w90.txn_type == "REVERSAL").sum())
    # Fuliza history
    draws = ok[ok.txn_type == "FULIZA_DRAW"]
    repays = ok[ok.txn_type == "FULIZA_REPAY"].completion_time.values
    d90 = win(draws, 90)
    row["fuliza_amount_90"] = float(d90.paid_in.sum())
    if len(d90) and len(repays):
        d = d90.completion_time.values
        i = np.searchsorted(repays, d)
        good = i < len(repays)
        lag = (repays[i[good]] - d[good]) / np.timedelta64(1, "D")
        row["fuliza_repay_lag_median_days_90"] = float(np.median(lag)) if len(lag) else np.nan
    else:
        row["fuliza_repay_lag_median_days_90"] = np.nan
    row["days_since_last_fuliza_draw"] = float((cut - draws.completion_time.max()).days) if len(draws) else history
    # trend: last 30 days against the average 30 days of the 60 days before
    prior_days = min(60.0, history - 30)
    if prior_days >= 14:
        prior = inc_all[(inc_all.completion_time >= cut - pd.Timedelta(days=90)) & (inc_all.completion_time < cut - pd.Timedelta(days=30))]
        row["income_trend_30_vs_prior"] = _div(income[30], prior.paid_in.sum() * 30.0 / prior_days)
    else:
        row["income_trend_30_vs_prior"] = np.nan
    b90 = bal.iloc[-int(obs90):] if obs90 >= 1 else bal.iloc[0:0]
    row["balance_median_eod_90"] = float(b90.median()) if len(b90) else np.nan
    row["balance_min_eod_90"] = float(b90.min()) if len(b90) else np.nan
    row["balance_cv_90"] = _div(b90.std(ddof=0), b90.mean()) if len(b90) >= 14 and b90.mean() > 0 else np.nan
    if len(bal) >= 45:                          # balance trend: last 30 days against the 60 days before
        last, prev = bal.iloc[-30:], bal.iloc[-90:-30]
        row["balance_trend_90"] = _div(last.median(), prev.median()) if prev.median() > 0 else np.nan
    else:
        row["balance_trend_90"] = np.nan
    # cash-flow ratios (docs/scorecard_mapping.md). Spending = payments out and fees; cash taken out at an agent is not spending.
    spend = w90[w90.txn_type.isin(PAYMENT_OUT + ("FEE",))].withdrawn.sum()
    essential = w90[w90.txn_type.isin(("PAYBILL_OUT", "AIRTIME_OUT"))].withdrawn.sum()
    row["net_cash_flow_ratio_90"] = _div(income[90] - spend, income[90])
    row["essential_outflow_share_90"] = _div(essential, w90[w90.txn_type.isin(PAYMENT_OUT)].withdrawn.sum())
    row["free_cash_flow_ratio_90"] = _div(income[90] - essential, income[90])
    row["debt_service_ratio_90"] = _div(w90.loc[w90.txn_type == "FULIZA_REPAY", "withdrawn"].sum(), income[90])
    # affordability: the loan against what the vendor takes in
    row["amount_to_income_30"] = _div(app.requested_amount, income[30])
    row["amount_to_avg_monthly_income_90"] = _div(app.requested_amount, income[90] * 30.0 / obs90 if obs90 else np.nan)
    return row


def build(tx: pd.DataFrame, apps: pd.DataFrame) -> pd.DataFrame:
    tx = tx.sort_values(["vendor_id", "completion_time"], kind="stable")
    groups = {v: g for v, g in tx.groupby("vendor_id")}
    rows = []
    for app in apps.itertuples(index=False):
        rows.append(build_row(groups[app.vendor_id], app))
    return pd.DataFrame(rows, index=apps.index)


def leakage_test(tx: pd.DataFrame, apps: pd.DataFrame, n=25, seed=1):
    """Recompute features after deleting every transaction on or after the application date. They must not change."""
    tx = tx.sort_values(["vendor_id", "completion_time"], kind="stable")
    groups = {v: g for v, g in tx.groupby("vendor_id")}
    bad = 0
    for app in apps.sample(min(n, len(apps)), random_state=seed).itertuples(index=False):
        g = groups[app.vendor_id]
        cut = pd.Timestamp(app.application_date).normalize()
        a = build_row(g, app)
        b = build_row(g[g.completion_time < cut], app)
        for k in a:
            if not (np.isclose(a[k], b[k], equal_nan=True)):
                bad += 1
                print("  LEAK?", app.application_id, k, a[k], b[k])
    return bad


TX_COLUMNS = ["vendor_id", "completion_time", "txn_type", "is_failed", "fuliza_funded", "paid_in", "withdrawn",
              "balance", "counterparty_id"]


def build_in_chunks(path: str, apps: pd.DataFrame):
    """Same result as build(), reading the cleaned file one parquet row group (a block of whole vendors) at a time.
    Returns the features and a map vendor -> row group, which the leakage test needs."""
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(path)
    parts, rg_of = [], {}
    for i in range(pf.num_row_groups):
        tx = pf.read_row_group(i, columns=TX_COLUMNS).to_pandas()
        tx["completion_time"] = pd.to_datetime(tx["completion_time"])
        vids = tx.vendor_id.unique()
        split = [v for v in vids if v in rg_of]
        if split:
            raise SystemExit(f"Vendor {split[0]} appears in more than one row group of {path}. The cleaned file must keep whole "
                             "vendors together. Re-run the current src/clean.py (it writes one row group per 50 vendors) and try again.")
        rg_of.update({v: i for v in vids})
        sub = apps[apps.vendor_id.isin(vids)]
        if len(sub):
            parts.append(build(tx, sub))
        print(f"  features: chunk {i + 1}/{pf.num_row_groups}", flush=True)
    return pd.concat(parts).reindex(apps.index), rg_of, pf


def leakage_test_chunked(pf, rg_of, apps: pd.DataFrame, n=25, seed=1) -> int:
    """Leakage test for a chunked file: loads only the row groups that hold the sampled applications."""
    sample = apps.sample(min(n, len(apps)), random_state=seed)
    bad = 0
    for i, sub in sample.groupby(sample.vendor_id.map(rg_of)):
        tx = pf.read_row_group(int(i), columns=TX_COLUMNS).to_pandas()
        tx["completion_time"] = pd.to_datetime(tx["completion_time"])
        bad += leakage_test(tx, sub, n=len(sub))
    return bad


def auc(x: pd.Series, y: pd.Series) -> float:
    """Rank-based AUC of one feature against a 0/1 label. 0.5 means no signal. NaN rows are skipped."""
    d = pd.DataFrame({"x": x, "y": y}).dropna()
    n1, n0 = int(d.y.sum()), int((1 - d.y).sum())
    if n1 == 0 or n0 == 0 or d.x.nunique() < 2:
        return np.nan
    r = d.x.rank()
    return float((r[d.y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def report(df, feats, leaks):
    n = len(df)
    L = ["# Feature report", "", f"{n:,} applications, {len(feats)} features. Outcomes are made later by src/scorecard.py; "
         "the signal check against them is in docs/scorecard_report.md.", ""]
    L += [f"Leakage test: {'PASS, no feature changed when later transactions were deleted' if leaks == 0 else f'FAIL, {leaks} values changed'}"
          if leaks is not None else "Leakage test: skipped", ""]
    miss = df[feats].isna().mean().sort_values(ascending=False)
    L += ["## Missing values (share of applications)", "", "| feature | missing |", "|---|---|"]
    L += [f"| {k} | {v:.1%} |" for k, v in miss[miss > 0].items()] or ["| none | 0% |"]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", default="data/interim")
    ap.add_argument("--dir", default="data/synthetic")
    ap.add_argument("--out", default="data/processed")
    ap.add_argument("--report", default="docs/feature_report.md")
    ap.add_argument("--skip-check", action="store_true")
    a = ap.parse_args()

    apps = load(a.dir, "loan_applications")
    apps["application_date"] = pd.to_datetime(apps["application_date"])
    ve = load(a.dir, "vendors")

    src = os.path.join(a.clean, "transactions_clean.parquet")
    chunked = False
    if os.path.exists(src):
        try:
            import pyarrow.parquet as pq
            chunked = pq.ParquetFile(src).num_row_groups > 1
        except ImportError:
            pass
    if chunked:                                       # big file: one block of vendors in memory at a time
        feat, rg_of, pf = build_in_chunks(src, apps)
    else:
        tx = load(a.clean, "transactions_clean")
        tx["completion_time"] = pd.to_datetime(tx["completion_time"])
        feat = build(tx, apps)
    out = pd.concat([apps[["application_id", "vendor_id", "application_date"]].reset_index(drop=True),
                     feat.reset_index(drop=True)], axis=1)
    out = out.merge(ve[["vendor_id", "business_type", "gender", "persona"]], on="vendor_id", how="left")
    feats = [c for c in out.columns if c not in META]
    out = out[META + feats]

    leaks = None
    if not a.skip_check:
        leaks = leakage_test_chunked(pf, rg_of, apps) if chunked else leakage_test(tx, apps)
        print("Leakage test:", "PASS" if leaks == 0 else f"FAIL ({leaks} values changed)")

    p = save(out, a.out, "features")
    with open(os.path.join(a.out, "feature_columns.json"), "w") as f:
        json.dump({"features": feats, "meta": META}, f, indent=2)
    txt = report(out, feats, leaks)
    os.makedirs(os.path.dirname(a.report) or ".", exist_ok=True)
    with open(a.report, "w", encoding="utf-8") as f:
        f.write(txt)
    print(f"{len(out)} applications, {len(feats)} features")
    print(txt)
    print(f"wrote {p}\nwrote {os.path.join(a.out, 'feature_columns.json')}\nwrote {a.report}")


if __name__ == "__main__":
    main()