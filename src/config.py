"""All parameters for the synthetic M-Pesa vendor data generator.

Every number here comes from `docs/assumptions.md` (row numbers in the comments) or `docs/personas.md`.
Values marked "assumption" have no published source. Change them here and nowhere else.
Amounts are in KES.
"""

# ---------------------------------------------------------------- run settings
SEED = 42
N_VENDORS = 1000                 # full run. Use --n-vendors 50 for a quick check
CHUNK_VENDORS = 50               # vendors written per chunk (one parquet row group). Keeps memory small
END_DATE = "2026-06-30"          # every statement ends on this date
OUT_DIR = "data/synthetic"
PERSONA_OVERLAP = 0.10           # share of parameters a vendor takes from an adjacent persona (personas.md)

# ---------------------------------------------------------------- personas (personas.md v0.2)
# (low, high) ranges. Each vendor draws its own value inside the range.
# till_share: share of inflows that are till payments (rest is send money). Assumptions.md row 3 / O4.
# fuliza_prop: chance that a payment the balance cannot cover is funded by Fuliza (assumption).
# sweep_prob: chance per active day that the vendor withdraws cash at an agent (assumption).
# supplier_prob: chance per week of a supplier (buy goods) payment (assumption).
# bill_miss: chance a monthly bill is not paid on time (assumption).
PERSONAS = {
    "stable": dict(
        share=0.30, months=(12, 24), tx_per_day=(20, 40), ticket=(100, 200), active_days=(24, 28),
        trend=(-0.01, 0.02), weekly_cv=(0.10, 0.25), repeat=(0.50, 0.70), till_share=(0.35, 0.45),
        latent_risk=(0.02, 0.09), fuliza_prop=(0.02, 0.10), sweep_prob=(0.25, 0.45),
        supplier_prob=(0.90, 1.00), bill_miss=(0.00, 0.05), seasonal=False),
    "growing": dict(
        share=0.15, months=(12, 24), tx_per_day=(10, 25), ticket=(120, 250), active_days=(22, 27),
        trend=(0.03, 0.06), weekly_cv=(0.15, 0.30), repeat=(0.35, 0.55), till_share=(0.35, 0.45),
        latent_risk=(0.05, 0.14), fuliza_prop=(0.35, 0.60), sweep_prob=(0.50, 0.80),
        supplier_prob=(0.85, 1.00), bill_miss=(0.00, 0.08), seasonal=False),
    "seasonal": dict(
        share=0.20, months=(12, 24), tx_per_day=(5, 35), ticket=(100, 300), active_days=(10, 26),
        trend=(-0.005, 0.005), weekly_cv=(0.50, 0.90), repeat=(0.30, 0.50), till_share=(0.30, 0.40),
        latent_risk=(0.12, 0.26), fuliza_prop=(0.35, 0.65), sweep_prob=(0.50, 0.85),
        supplier_prob=(0.60, 0.90), bill_miss=(0.05, 0.25), seasonal=True, peak_ratio=(2.0, 3.0)),
    "new": dict(
        share=0.15, months=(1, 3), tx_per_day=(5, 20), ticket=(80, 200), active_days=(15, 25),
        trend=(0.05, 0.15), weekly_cv=(0.30, 0.60), repeat=(0.15, 0.35), till_share=(0.15, 0.25),
        latent_risk=(0.12, 0.23), fuliza_prop=(0.30, 0.55), sweep_prob=(0.55, 0.85),
        supplier_prob=(0.30, 0.50), bill_miss=(0.30, 0.70), seasonal=False),
    "struggling": dict(
        share=0.20, months=(6, 24), tx_per_day=(3, 12), ticket=(50, 150), active_days=(8, 20),
        trend=(-0.08, -0.03), weekly_cv=(0.40, 0.80), repeat=(0.10, 0.30), till_share=(0.20, 0.30),
        latent_risk=(0.24, 0.40), fuliza_prop=(0.60, 0.90), sweep_prob=(0.50, 0.85),
        supplier_prob=(0.10, 0.30), bill_miss=(0.30, 0.60), seasonal=False),
}
ADJACENT = {
    "stable": ["growing", "seasonal"],
    "growing": ["stable", "seasonal"],
    "seasonal": ["stable", "growing", "struggling"],
    "new": ["growing", "struggling"],
    "struggling": ["seasonal", "new"],
}

BUSINESS_TYPES = ["fresh_produce", "food_stall", "retail_kiosk", "services", "second_hand_clothes"]
TICKET_MULTIPLIER = {  # personas.md: business type can shift the ticket size (assumption)
    "fresh_produce": 0.8, "food_stall": 0.9, "retail_kiosk": 1.0, "services": 1.4, "second_hand_clothes": 1.2}

# Latent risk shapes behaviour, but only partly (personas.md: features reflect risk partly).
# z is the vendor's position inside its own persona's risk range: -1 at the low end, +1 at the high end.
# So within a persona, riskier vendors look somewhat worse. Persona differences still dominate. All are assumptions.
# Before v0.5 these effects were tied to the raw risk value and came to only about 1 to 2% within a persona.
RISK_INFLOW_EFFECT = 0.30        # inflow volume falls by this share at z = +1 (and rises at z = -1)
RISK_FULIZA_EFFECT = 0.25        # added to fuliza_prop per unit of z
RISK_BILL_MISS_EFFECT = 0.20     # added to bill_miss per unit of z
RISK_CV_EFFECT = 0.30            # weekly income variation rises by this share at z = +1
RISK_TREND_EFFECT = 0.015        # monthly income growth rate falls by this much per unit of z

# ---------------------------------------------------------------- transactions
TICKET_SIGMA = 0.8               # log-normal spread of sale sizes around the vendor's median (assumption)
MIN_TICKET = 10
WEEKDAY_FACTOR = [0.95, 0.95, 1.0, 1.0, 1.15, 1.20, 0.80]   # Mon..Sun (assumption)
HOUR_WEIGHTS = [0, 0, 0, 0, 0, 1, 3, 6, 8, 7, 6, 6, 7, 6, 5, 5, 6, 8, 7, 5, 3, 2, 1, 0]  # hours 0..23

PERSONAL_SEND_PER_MONTH = (1, 4)       # send-money-out events per month (assumption)
PERSONAL_SEND_AMOUNT = (100, 1500)
AIRTIME_PER_MONTH = (2, 8)
AIRTIME_AMOUNT = (20, 200)
SMALL_RESTOCK_PER_WEEK = 2.5           # small mid-week restock payments, scaled by fuliza_prop (assumption)
SMALL_RESTOCK_AMOUNT = (100, 800)
SUPPLIER_SHARE_OF_WEEK = (0.25, 0.45)  # supplier payment as share of last 7 days' inflow (assumption)
BILL_SHARE_OF_MONTH = (0.06, 0.12)     # monthly bill as share of last 30 days' inflow (assumption)
DEPOSIT_PROB_PER_DAY = 0.02            # cash deposited at an agent (assumption)
DEPOSIT_AMOUNT = (500, 5000)
SWEEP_FRACTION = (0.7, 1.0)            # share of balance withdrawn when a vendor sweeps (assumption)
MIN_WITHDRAWAL = 100
FAILED_PROB = 0.01                     # rare failed payments, added on purpose to test cleaning
REVERSAL_PROB = 0.003                  # rare reversals of a payment

# Fuliza (assumptions.md rows 7c, 9b, O8 to O11)
FULIZA_MAX_DRAW = 1000                 # single draw limit (row 9b: KES 50 to 1,000)
FULIZA_LIMIT = 3000                    # total outstanding limit (assumption)
FULIZA_MIN_DRAW = 50
FULIZA_DRAW_ROUND = 10
FULIZA_ACCESS_FEE = 0.03               # added to the amount owed. Repaid/drawn was 103% in the author's statement (O11)

# Approximate M-Pesa charges (illustrative, not the exact tariff): (upper bound, fee)
SEND_FEE = [(100, 0), (500, 7), (1000, 13), (1500, 23), (2500, 33), (3500, 53), (5000, 57), (7500, 78), (10**9, 90)]
WITHDRAW_FEE = [(100, 11), (2500, 29), (3500, 52), (5000, 69), (7500, 87), (10**9, 105)]
PAYBILL_FEE = [(100, 0), (500, 5), (1000, 10), (2500, 15), (5000, 25), (10**9, 30)]

# ---------------------------------------------------------------- loans and labels (personas.md, assumptions.md rows 9a, 10a, 10b)
LOAN_MEDIAN = 5000                     # row 9a
LOAN_SIGMA = 0.6
LOAN_MIN, LOAN_MAX = 500, 10000
TERM_RANGE = (7, 30)
APPLICATION_MIN_DAY = 25               # earliest application day after the vendor's first transaction
APPLICATION_FRACTION = (0.55, 0.90)    # application falls this far through the statement
# ---------------------------------------------------------------- outcomes (v0.6)
# 1. `defaulted` comes from the cash-flow scorecard (src/scorecard.py): a probability p per application, then a coin flip.
# 2. Fuliza lateness is READ from the transactions after the application date (src/outcomes.py).
# 3. repayment_status combines them: 2 default, 1 late (not defaulted, but a Fuliza draw stayed unpaid past
#    LATE_THRESHOLD_DAYS), 0 on time.
TARGET_DEFAULT_RATE = 0.166            # row 10a (FinAccess 2024). The scorecard intercept is set so the average p matches it
OBS_WINDOW_DAYS = 90                   # statements run this many days past the last possible application date
FULIZA_COUNT_DAYS = 60                 # only Fuliza draws in the first 60 days count, so each has 30 days to be repaid
LATE_THRESHOLD_DAYS = 30               # a draw unpaid after 30 days is late (Fuliza term; IFRS 9 30-day presumption)
# Hidden shock: one standard-normal draw per application (illness, market closing). It lowers the vendor's inflows after
# the application date and also raises default risk in the scorecard, so the two outcomes share a hidden cause.
SHOCK_INFLOW_EFFECT = 0.25             # inflows are multiplied by exp(-effect * shock), clipped to SHOCK_CLIP (assumption)
SHOCK_CLIP = (0.4, 1.5)

# ---------------------------------------------------------------- scorecard (docs/scorecard_mapping.md)
# Pillar -> {feature: direction}. +1 means a higher value raises risk, -1 lowers it. Directions are author assumptions
# supported by cash-flow underwriting practice; see docs/scorecard_mapping.md for the reasoning.
SCORECARD_PILLARS = {
    "A_income_stability": {
        "weekly_income_cv_90": +1, "income_active_day_share_90": -1, "repeat_sender_share_90": -1,
        "income_count_90": -1, "median_ticket_90": -1},
    "B_cash_flow_buffer": {
        "near_zero_day_share_90": +1, "balance_median_eod_90": -1, "balance_min_eod_90": -1,
        "net_cash_flow_ratio_90": -1, "balance_trend_90": -1, "balance_cv_90": +1,
        "withdraw_share_of_income_90": +1, "fee_share_of_income_90": +1},
    # cash_deposit_share_90 is deliberately NOT in the scorecard: its direction is ambiguous and unsupported (own capital added,
    # or weak mobile-money sales). It stays a model input.
    "C_borrowing_distress": {
        "fuliza_draws_90": +1, "fuliza_funded_share_90": +1, "fuliza_repay_lag_median_days_90": +1,
        "days_since_last_fuliza_draw": -1, "failed_payment_share_90": +1, "fuliza_amount_90": +1,
        "reversal_count_90": +1},
    "D_affordability": {
        "amount_to_avg_monthly_income_90": +1, "amount_to_income_30": +1, "debt_service_ratio_90": +1,
        "requested_term_days": +1},
    "E_obligations": {
        "paybill_months_paid_90": -1, "supplier_spend_share_90": -1, "supplier_count_90": -1,
        "essential_outflow_share_90": -1, "free_cash_flow_ratio_90": -1},
    "F_history_growth": {
        "history_days": -1, "income_trend_30_vs_prior": -1, "fuliza_draws_30": +1},
    "G_network": {"unique_senders_90": -1, "till_share_90": -1},
}
# Pillar weights (sum to 1). "author" is the main set (docs/scorecard_mapping.md section 1). All are assumptions.
WEIGHT_SETS = {
    "author":         {"A_income_stability": 0.30, "B_cash_flow_buffer": 0.25, "C_borrowing_distress": 0.15,
                       "D_affordability": 0.10, "E_obligations": 0.10, "F_history_growth": 0.05, "G_network": 0.05},
    "equal":          {k: 1 / 7 for k in ("A_income_stability", "B_cash_flow_buffer", "C_borrowing_distress",
                                          "D_affordability", "E_obligations", "F_history_growth", "G_network")},
    "cashflow_heavy": {"A_income_stability": 0.35, "B_cash_flow_buffer": 0.30, "C_borrowing_distress": 0.15,
                       "D_affordability": 0.05, "E_obligations": 0.05, "F_history_growth": 0.05, "G_network": 0.05},
    "fico_like":      {"A_income_stability": 0.10, "B_cash_flow_buffer": 0.10, "C_borrowing_distress": 0.20,
                       "D_affordability": 0.25, "E_obligations": 0.20, "F_history_growth": 0.10, "G_network": 0.05},
}
MAIN_WEIGHTS = "author"
SCORECARD_SCALE = 1.2                  # logit units per unit of the pillar-weighted score (assumption)
HIDDEN_RISK_COEF = 0.5                 # logit units per standard deviation of latent_risk (assumption)
SHOCK_COEF = 0.5                       # logit units per unit of hidden shock (assumption)
SHOCK_COEF_LEVELS = (0.25, 0.5, 0.9)   # sensitivity run
SCORE_CLIP = 3.0                       # feature z-scores are clipped to +/- this before scoring