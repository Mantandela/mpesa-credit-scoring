# Scoring function

`src/predict.py` scores one M-Pesa statement with the trained logistic regression. The dashboard and the vendor
self-check will call it. **All outcomes the model learned from are simulated** (scorecard -> probability -> drawn
labels), so the score shows how the method works, not how a real borrower would repay.

## Input

```python
from predict import score_statement, warm_up

warm_up()                                   # optional, at start-up: importing shap takes about 4 seconds
result = score_statement(
    statement,                              # DataFrame of raw transactions, or a path to .pdf / .xlsx / .xls / .csv
    requested_amount=5000,                  # KES; default = training median (5,000); clipped to 1,300-10,000
    requested_term_days=14,                 # default = training median (19); clipped to 7-30
    application_date="2026-03-15",          # default = the day after the last transaction
    model_path="models/logistic.joblib",
    reference_path="models/reference.json",
    password=None,                          # for a password-protected PDF
)
```

CLI (prints JSON only, never transaction details):

```
python src/predict.py <statement file> --amount 5000 --term 14 [--date 2026-03-15] [--ask-password] [--full]
```

Steps: read the statement (`pdf_statement.read_statement`) -> `clean.clean` -> keep transactions before the
application date -> `features.build_row` -> logistic model -> probability of default -> `scoring.pd_to_score` and
`risk_tier`. Pillar ratings use `scorecard.pillar_scores` with the stored standardisation. Reasons are SHAP values
(`shap.LinearExplainer` on the final LogisticRegression, on the imputed and rank-normalised inputs).

## Output (example: a simulated vendor, 6-month statement, KES 5,000 for 14 days; pillar scores rounded)

```json
{
  "probability_of_default": 0.1248,
  "score": 624,
  "tier": "Moderate risk",
  "pillar_ratings": [
    {"pillar": "A_income_stability",   "rating": 69, "label": "Good",   "pillar_score": -0.450},
    {"pillar": "B_cash_flow_buffer",   "rating": 49, "label": "Fair",   "pillar_score":  0.006},
    {"pillar": "C_borrowing_distress", "rating": 56, "label": "Good",   "pillar_score": -0.011},
    {"pillar": "D_affordability",      "rating": 76, "label": "Strong", "pillar_score": -0.192},
    {"pillar": "E_obligations",        "rating": 13, "label": "Weak",   "pillar_score":  0.397},
    {"pillar": "F_history_growth",     "rating": 40, "label": "Fair",   "pillar_score":  0.265},
    {"pillar": "G_network",            "rating": 59, "label": "Good",   "pillar_score": -0.265}
  ],
  "top_reasons": [
    {"feature": "fuliza_repay_lag_median_days_90 (missing flag)", "label": "typical time taken to repay Fuliza (missing flag)",
     "value": 1.0, "direction": "raises risk", "shap_value": 0.349,
     "sentence": "Raises your risk: typical time taken to repay Fuliza (no data in your statement)"},
    {"feature": "withdraw_share_of_income_30", "label": "cash withdrawn at agents compared with customer income (last 30 days)",
     "value": 1.067, "direction": "raises risk", "shap_value": 0.197,
     "sentence": "Raises your risk: cash withdrawn at agents compared with customer income (last 30 days) (high: 107%)"},
    {"feature": "weekly_income_cv_90", "label": "how much your weekly income goes up and down",
     "value": 0.168, "direction": "lowers risk", "shap_value": -0.118,
     "sentence": "Lowers your risk: how much your weekly income goes up and down (low: 17%)"},
    {"feature": "fuliza_draws_90", "label": "number of times you used Fuliza",
     "value": 0.0, "direction": "lowers risk", "shap_value": -0.109,
     "sentence": "Lowers your risk: number of times you used Fuliza (low: 0)"},
    {"feature": "withdraw_share_of_income_60", "label": "cash withdrawn at agents compared with customer income (last 60 days)",
     "value": 0.962, "direction": "lowers risk", "shap_value": -0.108,
     "sentence": "Lowers your risk: cash withdrawn at agents compared with customer income (last 60 days) (high: 96%)"}
  ],
  "inputs_used": {"requested_amount": 5000.0, "requested_term_days": 14.0, "application_date": "2026-06-30",
                  "history_days": 183.0, "transactions_used": 3425, "transactions_after_date_ignored": 0},
  "warnings": [],
  "explanation": {"base_value": -1.867, "logit": -1.947},
  "model_info": {"model": "logistic", "seed": 42, "n_features": 52, "settings": {"C": 0.01}, "labels": "simulated"}
}
```

- `pillar_ratings.rating`: percentile of the vendor's pillar score among the 2,244 simulated applications, flipped so
  100 = best. Weak < 25 <= Fair < 50 <= Good < 75 <= Strong.
- `top_reasons`: the five largest SHAP values in absolute size. `explanation.base_value` + the sum of all SHAP values
  equals `explanation.logit` (the model's log-odds) exactly; `--full` / the Python result include every SHAP value.
- `warnings` (each has a `code`): `thin_history` (fewer than 90 days before the application date),
  `requested_amount_clipped` / `requested_term_days_clipped`, `integrity_flags` (counts of rows that broke a
  `clean.py` check, only rows actually used), `unparsed_rows` (rows whose time or balance could not be read; they
  are skipped but always counted), and reader notes (`skipped_non_transaction_rows` with a breakdown of repeated
  headers, blank rows and footers; `same_second_reordered`; `balance_breaks`; `duplicate_receipts`).
- Errors are `ValueError`s with a message safe to show: no transactions, no usable transactions before the date, a
  wrong or missing PDF password, a PDF without text, an unsupported file type.

## Rebuilding the reference files

The reference files live in `models/` next to the model. After retraining the model or rebuilding features or the
scorecard, run, from the repo root:

```
python src/train_models.py          # writes models/logistic.joblib
python src/build_reference.py       # writes models/reference.json and models/shap_background.parquet
```

`predict.py` refuses a reference whose feature list differs from the model's, but it cannot detect a reference built
from an older population, so always run both.

## Speed

On a 6-month statement (about 3,400 rows): about 0.2 to 0.9 seconds per call once loaded. The first call in a
process takes about 4 to 5 seconds, almost all of it importing `shap` (numba); call `warm_up()` when the app starts.

## Limitations

- **Simulated labels.** The model recovers a simulated scorecard; nothing here is validated on real repayment.
- **The models do not beat the visible scorecard baseline** (docs/model_report.md). The scoring function is a working
  pipeline with explanations, not evidence that machine learning adds value over the scorecard.
- **Thin history.** Below 90 days several features are missing and are filled with training medians (plus missing
  flags); the score leans on the population average. The `thin_history` warning says so.
- **Requested amount is not monotone in the trained model.** The coefficients of the affordability ratios
  (`amount_to_income_30`, `amount_to_avg_monthly_income_90`) and of `requested_term_days` are slightly negative,
  so asking for more can lower the predicted risk over part of the range (example vendor above: PD 13.3% at KES 1,300,
  12.3% at KES 7,500, 14.1% at KES 10,000). The self-check should not present the amount slider as "what you can
  afford" until this is addressed (e.g. sign constraints or a monotone model).
- **Reasons can look contradictory.** Correlated features (30/60/90-day versions, a feature and its missing flag) can
  receive SHAP values of opposite sign, e.g. agent withdrawals over 30 days raising risk while the 60-day version
  lowers it. The reasons explain the model faithfully, not causes.
- **Clipping hides large requests.** A request above KES 10,000 is scored as 10,000 (with a warning).
- **PDF statements.** The reader expects the original M-Pesa PDF layout and is tested on generated PDFs only. A PDF
  re-printed with "Microsoft Print to PDF" or scanned has no text and is rejected (OCR is not supported).
