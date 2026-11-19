"""Plain-English labels for every model feature, and the sentences shown as reasons for a score.

Convention: the standard look-back is 90 days, so 90-day features carry no window in their label; 30- and 60-day
versions say "(last 30 days)" or "(last 60 days)". The dashboard should say once that figures cover the last 90 days.

    reason_sentence("near_zero_day_share_90", 0.42, 0.31, reference_median=0.12)
    -> "Raises your risk: days with almost no money left in your wallet (high: 31% of days)"

select_reasons picks the reasons shown for a score: missing data is neutral and never a reason, one reason per family
(FEATURE_FAMILIES: the 30/60/90-day versions of a measure and its missing flag), and one reason per measure group
(MEASURE_GROUPS), so reasons never contradict each other or repeat a theme.
"""
import math

MISSING_FLAG_SUFFIX = " (missing flag)"

# kind controls how a value is written: kes, count, days, months, pct, pct_days, ratio
_WINDOWED = {
    "income_total": ("money received from customers", "kes"),
    "income_count": ("number of customer payments", "count"),
    "income_active_day_share": ("days with at least one customer payment", "pct_days"),
    "median_ticket": ("typical customer payment size", "kes"),
    "unique_senders": ("number of different customers who paid you", "count"),
    "near_zero_day_share": ("days with almost no money left in your wallet", "pct_days"),
    "fuliza_draws": ("number of times you used Fuliza", "count"),
    "withdraw_share_of_income": ("cash withdrawn at agents compared with customer income", "pct"),
}
_SINGLE = {
    "requested_amount": ("the loan amount you asked for", "kes"),
    "requested_term_days": ("the loan term you asked for", "days"),
    "history_days": ("how long your M-Pesa history is", "days"),
    "weekly_income_cv_90": ("how much your weekly income goes up and down", "pct"),
    "repeat_sender_share_90": ("customer payments from returning customers", "pct"),
    "till_share_90": ("customer payments made to your till (Lipa na M-Pesa)", "pct"),
    "supplier_count_90": ("number of payments to suppliers (Buy Goods)", "count"),
    "supplier_spend_share_90": ("spending on suppliers compared with income", "pct"),
    "paybill_months_paid_90": ("months in which you paid a bill (Paybill)", "months"),
    "fuliza_funded_share_90": ("payments you could only make with Fuliza", "pct"),
    "failed_payment_share_90": ("payments that failed", "pct"),
    "fee_share_of_income_90": ("M-Pesa charges compared with income", "pct"),
    "cash_deposit_share_90": ("cash you deposited at agents compared with money received", "pct"),
    "reversal_count_90": ("number of reversed transactions", "count"),
    "fuliza_amount_90": ("total amount borrowed through Fuliza", "kes"),
    "fuliza_repay_lag_median_days_90": ("typical time taken to repay Fuliza", "days1"),
    "days_since_last_fuliza_draw": ("days since you last used Fuliza", "days"),
    "income_trend_30_vs_prior": ("income in the last 30 days compared with the 60 days before", "ratio"),
    "balance_median_eod_90": ("typical end-of-day wallet balance", "kes"),
    "balance_min_eod_90": ("lowest end-of-day wallet balance", "kes"),
    "balance_cv_90": ("how much your end-of-day balance goes up and down", "pct"),
    "balance_trend_90": ("wallet balance in the last 30 days compared with the 60 days before", "ratio"),
    "net_cash_flow_ratio_90": ("income left after payments and charges", "pct"),
    "essential_outflow_share_90": ("bills and airtime as a share of your payments", "pct"),
    "free_cash_flow_ratio_90": ("income left after bills and airtime", "pct"),
    "debt_service_ratio_90": ("Fuliza repayments compared with income", "pct"),
    "amount_to_income_30": ("loan amount compared with your income in the last 30 days", "ratio"),
    "amount_to_avg_monthly_income_90": ("loan amount compared with your average monthly income", "ratio"),
}


def _build():
    labels, kinds = {}, {}
    for stem, (text, kind) in _WINDOWED.items():
        for w in (30, 60, 90):
            labels[f"{stem}_{w}"] = text if w == 90 else f"{text} (last {w} days)"
            kinds[f"{stem}_{w}"] = kind
    for name, (text, kind) in _SINGLE.items():
        labels[name], kinds[name] = text, kind
    return labels, kinds


FEATURE_LABELS, FEATURE_KINDS = _build()

# Families: the 30/60/90-day versions of one measure (and, through base_feature, a feature's missing flag) are one
# family, so they give at most one reason between them. The loan request fields form one family that is never used
# as a reason: the score is worked out at the median request (see predict.py), so they say nothing about the vendor.
REQUEST_FAMILY = "loan_request"
_REQUEST = ("requested_amount", "requested_term_days", "amount_to_income_30", "amount_to_avg_monthly_income_90")
FEATURE_FAMILIES = {stem: [f"{stem}_{w}" for w in (30, 60, 90)] for stem in _WINDOWED}
FEATURE_FAMILIES.update({name: [name] for name in _SINGLE if name not in _REQUEST})
FEATURE_FAMILIES[REQUEST_FAMILY] = list(_REQUEST)
EXCLUDED_FROM_REASONS = frozenset({REQUEST_FAMILY})
_FAMILY_OF = {f: fam for fam, members in FEATURE_FAMILIES.items() for f in members}

# Families that measure the same thing (a high value means the same in each). Reasons from one group that point in
# opposite directions would contradict each other ("more Fuliza lowers your risk" next to "more Fuliza raises it"), and
# two in the same direction repeat one theme, so only the one with the larger SHAP value is kept.
MEASURE_GROUPS = {
    "income_size": ("income_total", "income_count"),
    "fuliza_use": ("fuliza_draws", "fuliza_amount_90", "fuliza_funded_share_90", "debt_service_ratio_90"),
    "wallet_balance": ("balance_median_eod_90", "balance_min_eod_90"),
    "money_left_over": ("net_cash_flow_ratio_90", "free_cash_flow_ratio_90"),
}
_GROUP_OF = {fam: g for g, fams in MEASURE_GROUPS.items() for fam in fams}


def base_feature(name: str) -> str:
    return name[:-len(MISSING_FLAG_SUFFIX)] if name.endswith(MISSING_FLAG_SUFFIX) else name


def is_missing_flag(name: str) -> bool:
    return name.endswith(MISSING_FLAG_SUFFIX)


def family(name: str) -> str:
    """Family of a feature or a missing flag. KeyError for an unknown feature."""
    return _FAMILY_OF[base_feature(name)]


def family_label(fam: str) -> str:
    """Label of a family: the 90-day (or only) member's label, which carries no window."""
    return FEATURE_LABELS[FEATURE_FAMILIES[fam][-1]]


def label(name: str) -> str:
    """Label for a feature or a missing-value flag ("<feature> (missing flag)"). KeyError for an unknown feature."""
    if is_missing_flag(name):
        return f"{FEATURE_LABELS[base_feature(name)]}{MISSING_FLAG_SUFFIX}"
    return FEATURE_LABELS[name]


def format_value(name: str, value) -> str:
    """The value in words a vendor understands, e.g. "31% of days", "KES 4,200", "1.4 times"."""
    if is_missing_flag(name):
        return "no data" if value and value >= 0.5 else "data available"
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "no data"
    v = float(value)
    kind = FEATURE_KINDS.get(name, "ratio")
    if kind == "kes":
        return f"KES {v:,.0f}"
    if kind == "count":
        return f"{v:,.0f}"
    if kind == "days":
        return f"{v:,.0f} day" + ("" if round(v) == 1 else "s")
    if kind == "days1":
        return f"{v:.1f} days"
    if kind == "months":
        return f"{v:.0f} month" + ("" if round(v) == 1 else "s")
    if kind == "pct_days":
        return f"{v:.0%} of days"
    if kind == "pct":
        return f"{v:.0%}"
    return f"{v:.2f} times"


def level(name: str, value, reference_median=None) -> str:
    """'high', 'low' or 'typical' against the reference median; flags and missing values get their own wording."""
    if is_missing_flag(name):
        return "missing" if value and value >= 0.5 else "present"
    if value is None or (isinstance(value, float) and math.isnan(value)) or reference_median is None:
        return "not available" if value is None or (isinstance(value, float) and math.isnan(value)) else "value"
    if math.isclose(float(value), float(reference_median), rel_tol=1e-9, abs_tol=1e-12):
        return "typical"
    return "high" if float(value) > float(reference_median) else "low"


def no_data_sentence(text: str) -> str:
    """Neutral note for a measure the statement has no data on. It never says whether this raises or lowers risk."""
    return f"No data in this statement on: {text}"


def reason_sentence(name: str, shap_value: float, value, reference_median=None) -> str:
    """'Raises your risk: <label> (<level>: <value>)' or 'Lowers your risk: ...'. Missing flags and features without
    data get a neutral sentence instead ("No data in this statement on: ..."): missing data is never a reason."""
    lv = level(name, value, reference_median)
    if is_missing_flag(name):
        base = FEATURE_LABELS[base_feature(name)]
        return no_data_sentence(base) if lv == "missing" else f"Data available in this statement on: {base}"
    if lv == "not available":
        return no_data_sentence(label(name))
    verb = "Raises your risk" if shap_value > 0 else "Lowers your risk"
    shown = format_value(name, value)
    return f"{verb}: {label(name)} ({shown})" if lv == "value" else f"{verb}: {label(name)} ({lv}: {shown})"


def neutral_sentence(fam: str) -> str:
    """Neutral note for a family with no data in the statement."""
    return no_data_sentence(family_label(fam))


def _is_missing(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def select_reasons(shap_values: dict, values: dict, medians: dict | None = None, n: int = 5) -> tuple:
    """Pick the reasons shown for a score. Returns (reasons, data_notes).

    shap_values: {feature or missing-flag name: SHAP value}; values: {name: value} (a missing flag's value is 1.0 when
    the feature is missing). Rules:
    1. Missing flags and features without data are neutral. They never count as reasons; a family that has no data at
       all gets a neutral note in data_notes instead ("No data in this statement on: ...").
    2. One reason per family (30/60/90-day versions and the missing flag): the member with the largest |SHAP|.
    3. One reason per measure group, the larger |SHAP|. Two reasons from one group that point in opposite directions
       would contradict each other; two in the same direction would repeat one theme.
    4. The loan request family is never a reason; a zero SHAP value has no direction and is skipped.
    Reasons come in order of |SHAP|, largest first; ties keep the order of shap_values (deterministic).
    """
    medians = medians or {}
    best, no_data = {}, {}
    for name, s in shap_values.items():
        fam = family(name)
        if fam in EXCLUDED_FROM_REASONS:
            continue
        v = values.get(name)
        if is_missing_flag(name) or _is_missing(v):
            if (is_missing_flag(name) and v is not None and v >= 0.5) or (not is_missing_flag(name) and _is_missing(v)):
                no_data[fam] = max(no_data.get(fam, 0.0), abs(s))
            continue
        if s != 0 and (fam not in best or abs(s) > abs(best[fam][1])):
            best[fam] = (name, s)
    reasons = []
    for fam, (name, s) in sorted(best.items(), key=lambda kv: -abs(kv[1][1])):
        g = _GROUP_OF.get(fam)
        if g and any(_GROUP_OF.get(r["family"]) == g for r in reasons):
            continue                          # one reason per measure group: no contradiction, no repeated theme
        v = values.get(name)
        reasons.append({"feature": name, "family": fam, "label": label(name), "value": float(v),
                        "direction": "raises risk" if s > 0 else "lowers risk", "shap_value": float(s),
                        "sentence": reason_sentence(name, s, v, medians.get(name))})
        if len(reasons) == n:
            break
    notes = [{"family": fam, "label": family_label(fam), "sentence": neutral_sentence(fam)}
             for fam, _ in sorted(no_data.items(), key=lambda kv: -kv[1]) if fam not in best]
    return reasons, notes
