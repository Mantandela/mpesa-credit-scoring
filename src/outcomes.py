"""Fuliza lateness outcomes read from the transactions, and the three-class repayment label."""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402

TX_COLUMNS = ["vendor_id", "completion_time", "txn_type", "is_failed", "paid_in", "withdrawn"]


def _vendor_draw_table(g: pd.DataFrame):
    """Per draw: draw time and repaid time (NaT if never), matched first-in first-out."""
    g = g.sort_values("completion_time", kind="stable")
    ok = g[~g.is_failed.astype(bool)]
    dr = ok[ok.txn_type == "FULIZA_DRAW"]
    rp = ok[ok.txn_type == "FULIZA_REPAY"]
    if dr.empty:
        return np.array([], dtype="datetime64[ns]"), np.array([], dtype="datetime64[ns]")
    owed = np.cumsum(dr.paid_in.to_numpy(float) * (1.0 + C.FULIZA_ACCESS_FEE))
    paid_total = np.cumsum(rp.withdrawn.to_numpy(float))
    rp_t = rp.completion_time.to_numpy("datetime64[ns]")
    j = np.searchsorted(paid_total, owed - 1e-6, side="left")
    if len(rp_t):
        t1 = np.where(j < len(rp_t), rp_t[np.minimum(j, len(rp_t) - 1)], np.datetime64("NaT")).astype("datetime64[ns]")
    else:
        t1 = np.full(len(owed), np.datetime64("NaT"), dtype="datetime64[ns]")
    return dr.completion_time.to_numpy("datetime64[ns]"), t1


def fuliza_outcomes(tx: pd.DataFrame, apps: pd.DataFrame, window=C.OBS_WINDOW_DAYS, count_days=C.FULIZA_COUNT_DAYS,
                    late_days=C.LATE_THRESHOLD_DAYS) -> pd.DataFrame:
    """A draw in the first `count_days` after the application is late if unpaid after `late_days`."""
    rows = []
    last_seen = tx.groupby("vendor_id").completion_time.max()
    by_vendor = {v: g for v, g in tx[tx.txn_type.isin(["FULIZA_DRAW", "FULIZA_REPAY"])].groupby("vendor_id")}
    for app in apps.itertuples(index=False):
        a0 = np.datetime64(pd.Timestamp(app.application_date).normalize(), "ns")
        end = a0 + np.timedelta64(window, "D")
        t0, t1 = _vendor_draw_table(by_vendor[app.vendor_id]) if app.vendor_id in by_vendor else (np.array([], "datetime64[ns]"),) * 2
        counted = (t0 >= a0) & (t0 < a0 + np.timedelta64(count_days, "D"))
        t0c, t1c = t0[counted], t1[counted]
        lag = (t1c - t0c) / np.timedelta64(1, "D")                    # NaN where never repaid
        late = np.isnan(lag) | (lag > late_days)
        rows.append({"application_id": app.application_id, "fuliza_n_draws": int(counted.sum()),
                     "fuliza_late": int(late.any()) if len(late) else 0,
                     "fuliza_max_lag_days": float(np.nanmax(lag)) if len(lag) and not np.isnan(lag).all() else np.nan,
                     "window_complete": bool(app.vendor_id in last_seen.index and
                                             np.datetime64(last_seen[app.vendor_id], "ns") >= end - np.timedelta64(1, "D"))})
    return pd.DataFrame(rows)


def repayment_status(defaulted, fuliza_late) -> np.ndarray:
    """2 default, 1 late (not defaulted, Fuliza draw unpaid past the threshold), 0 on time."""
    d, l = np.asarray(defaulted).astype(int), np.asarray(fuliza_late).astype(int)
    return np.where(d == 1, 2, np.where(l == 1, 1, 0)).astype(int)


def best_possible_auc(df: pd.DataFrame) -> dict:
    """AUC ceiling: scorecard_p itself, persona alone, and scorecard_p within personas."""
    from sklearn.metrics import roc_auc_score
    rank = {"stable": 0, "growing": 1, "seasonal": 2, "new": 2, "struggling": 3}
    inside = [roc_auc_score(g.defaulted, g.scorecard_p) for _, g in df.groupby("persona") if 0 < g.defaulted.sum() < len(g)]
    return {"oracle_auc": float(roc_auc_score(df.defaulted, df.scorecard_p)),
            "persona_only_auc": float(roc_auc_score(df.defaulted, df.persona.map(rank))),
            "within_persona_oracle_auc": float(np.mean(inside)) if inside else float("nan")}