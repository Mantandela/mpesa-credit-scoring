"""All parameters for the synthetic M-Pesa vendor data generator.

Every number here comes from `docs/assumptions.md` (row numbers in the comments) or `docs/personas.md`.
Values marked "assumption" have no published source. Change them here and nowhere else.
Amounts are in KES.
"""

# ---------------------------------------------------------------- run settings
SEED = 42
N_VENDORS = 300                  # full run. Use --n-vendors 50 for a quick check
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

# Latent risk nudges behaviour only partly (personas.md: features reflect risk partly)
RISK_INFLOW_EFFECT = 0.25        # inflow scale falls by up to this share as latent_risk rises
RISK_FULIZA_EFFECT = 0.60        # added to fuliza_prop per unit of latent_risk
RISK_BILL_MISS_EFFECT = 0.40     # added to bill_miss per unit of latent_risk

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
SHOCK_SD = 0.10                        # default probability = latent_risk + N(0, SHOCK_SD), clipped to 0..1
TARGET_DEFAULT_RATE = 0.166            # row 10a (checked after the run)
# Probability a non-defaulting borrower is late: LATE_BASE + LATE_SLOPE * latent_risk.
# Base run: small. Stress run (--stress): raised until late_or_default is near 61% (row 10b).
LATE_BASE, LATE_SLOPE = 0.15, 1.0
STRESS_LATE_BASE, STRESS_LATE_SLOPE = 0.37, 1.0
LATE_DAYS = (1, 30)
DEFAULT_DAYS_PAST_DUE = (31, 120)