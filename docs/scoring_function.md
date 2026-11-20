# Scoring function

`src/predict.py` scores one M-Pesa statement with the trained logistic regression. The dashboard and the vendor
self-check will call it. **All outcomes the model learned from are simulated** (scorecard -> probability -> drawn
labels), so the score shows how the method works, not how a real borrower would repay.

## Supported inputs

- **Excel (.xlsx, .xls) and CSV** M-Pesa statements: the supported inputs.
- **PDF only when it has a text layer.** Real M-Pesa PDF statements are scanned images with no text layer (checked on
  two statements), so they **cannot** be read. Reading them would need OCR, which is out of scope (future work). For
  an image-only PDF the error tells the user to ask for the Excel or CSV version of the statement.
- A DataFrame of raw transactions (generator schema), for the pipeline and the tests.

## Input

```python
from predict import score_statement, score_uploaded_file, warm_up

warm_up()                                   # optional, at start-up: importing shap takes about 4 seconds
result = score_statement(
    statement,                              # DataFrame of raw transactions, or a path to .xlsx / .xls / .csv
    requested_amount=5000,                  # KES; used ONLY for the affordability block, as typed (no clipping); default = median (5,000); must be > 0
    requested_term_days=14,                 # used ONLY for the affordability block, as typed; default = median (19); must be > 0
    application_date="2026-03-15",          # default = the day after the last transaction
    model_path="models/logistic.joblib",
    reference_path="models/reference.json",
    password=None,                          # only for a password-protected text PDF
)

# a web upload (bytes or a file object); only the extension of the filename is used
result = score_uploaded_file(uploaded_bytes, "statement.xlsx", requested_amount=5000, requested_term_days=14)
```

`score_uploaded_file` holds the upload in memory and writes it to one temporary file with a random name in the
system temp folder, because the readers work from a path. The temporary file is deleted in a `finally` block, after
success and after any error. The upload is never written anywhere else, logged or cached. Files over 20 MB, empty files
and other file types are refused before anything is written.

CLI (prints JSON only, never transaction details):

```
python src/predict.py <statement file> --amount 5000 --term 14 [--date 2026-03-15] [--full]
```

Steps: read the statement (`pdf_statement.read_statement`) -> `clean.clean` -> keep transactions before the
application date -> `features.build_row` **at the median request** -> logistic model -> probability of default ->
`scoring.pd_to_score` and `risk_tier`. Pillar ratings use `scorecard.pillar_scores` with the stored standardisation.
Reasons are SHAP values (`shap.LinearExplainer` on the final LogisticRegression, on the imputed and rank-normalised
inputs). The requested amount and term feed only the `affordability` block.

## The score does not depend on the requested loan

The trained model's coefficients on the request fields are not monotone. `requested_term_days` and the two
amount-to-income ratios have small negative coefficients, so scoring the caller's request could show a larger loan as
less risky. For the example vendor below, the PD was 13.3% at KES 1,300, 12.3% at KES 7,500 and 14.1% at KES 10,000.
Retraining is out of scope, so:

- the probability of default, score, tier, pillar ratings and reasons are always worked out at the **median request**
  in `reference.json` (KES 5,000 for 19 days), whatever the caller passes. They describe the vendor, not the slider.
  `inputs_used.scored_at` shows the request used and the warning `score_at_median_request` says so.
- the requested amount and term, **exactly as typed** (no clipping, since the model never sees them; only values
  <= 0 are rejected with a `ValueError`), feed the separate **`affordability`** block. It holds the same
  ratios as the features (`amount_to_income_30`, `amount_to_avg_monthly_income_90`) and an estimated repayment (the
  amount only; fees and interest are not modelled). It also gives a band on `amount_to_avg_monthly_income_90`, with
  cutoffs at the 50th and 85th percentile of the 2,244 simulated applications. The bands are **comfortable** (at or
  below the 50th), **stretched** (50th to 85th) and **heavy** (above the 85th). A vendor with no customer income in the
  last 90 days gets **unknown**. With income fixed, the ratio grows with the amount and the cutoffs are fixed, so a
  larger amount never gives a better band.

## Estimated eligibility (PROTOTYPE POLICY)

The web app adds an estimated loan limit to every score (`src/eligibility.py`; `score_statement` itself is unchanged):

```
max_amount         = tier_factor[tier] x stretched_cutoff x monthly_income      rounded DOWN to KES 100
comfortable_amount = min(comfortable_cutoff x monthly_income, max_amount)       rounded DOWN to KES 100
status             = "eligible" if max_amount > 0 else "not_eligible";  "unknown" if monthly income is missing or <= 0
```

- `tier_factor` (in `ELIGIBILITY_POLICY`): Low 0.50, Moderate 0.35, High 0.15, Very high 0 (never eligible).
- The cutoffs are the affordability band cutoffs of `models/reference.json` (comfortable = 50th percentile, about
  0.056; stretched = 85th percentile, about 0.419). They are read from the file, never hard-coded.
- `monthly_income` is `affordability.amount_to_avg_monthly_income_90` turned back into KES: the vendor's average
  monthly customer income over the last 90 days.
- Example (the simulated vendor above: Moderate risk, about KES 164,300 a month): up to KES 24,100
  (0.35 x 0.4194 x 164,304 = 24,118, rounded down), comfortable up to KES 9,200 (0.0564 x 164,304 = 9,261).

**This is a placeholder policy for the prototype.** The tier factors are not taken from any lender's policy; monthly
income is statement **turnover** (money received from customers), not profit; the cutoffs describe simulated
applicants; and nothing here is validated on real repayment outcomes. The app says "The lender makes the final
decision."

In the app, Check score shows the estimate. Apply asks for the statement again, scores it fresh with the requested
amount and term, and sends the application only if the fresh estimate is "eligible" and the amount is within
`max_amount`. Otherwise it says why (above the limit, with the limit; not eligible; not enough income data).

## Output (example: a simulated vendor, 6-month statement, KES 5,000 for 14 days; numbers rounded)

```json
{
  "probability_of_default": 0.1244,
  "score": 625,
  "tier": "Moderate risk",
  "pillar_ratings": [
    {"pillar": "A_income_stability",   "rating": 69, "label": "Good",  "pillar_score": -0.450},
    {"pillar": "B_cash_flow_buffer",   "rating": 49, "label": "Fair",  "pillar_score":  0.006},
    {"pillar": "C_borrowing_distress", "rating": 56, "label": "Good",  "pillar_score": -0.011},
    {"pillar": "D_affordability",      "rating": 58, "label": "Good",  "pillar_score": -0.013},
    {"pillar": "E_obligations",        "rating": 13, "label": "Weak",  "pillar_score":  0.397},
    {"pillar": "F_history_growth",     "rating": 40, "label": "Fair",  "pillar_score":  0.265},
    {"pillar": "G_network",            "rating": 59, "label": "Good",  "pillar_score": -0.265}
  ],
  "top_reasons": [
    {"feature": "withdraw_share_of_income_30", "family": "withdraw_share_of_income",
     "label": "cash withdrawn at agents compared with customer income (last 30 days)", "value": 1.067,
     "direction": "raises risk", "shap_value": 0.197,
     "sentence": "Raises your risk: cash withdrawn at agents compared with customer income (last 30 days) (high: 107%)"},
    {"feature": "weekly_income_cv_90", "family": "weekly_income_cv_90", "label": "how much your weekly income goes up and down",
     "value": 0.168, "direction": "lowers risk", "shap_value": -0.118,
     "sentence": "Lowers your risk: how much your weekly income goes up and down (low: 17%)"},
    {"feature": "fuliza_draws_90", "family": "fuliza_draws", "label": "number of times you used Fuliza",
     "value": 0.0, "direction": "lowers risk", "shap_value": -0.109,
     "sentence": "Lowers your risk: number of times you used Fuliza (low: 0)"},
    {"feature": "net_cash_flow_ratio_90", "family": "net_cash_flow_ratio_90", "label": "income left after payments and charges",
     "value": 0.968, "direction": "raises risk", "shap_value": 0.081,
     "sentence": "Raises your risk: income left after payments and charges (high: 97%)"},
    {"feature": "balance_min_eod_90", "family": "balance_min_eod_90", "label": "lowest end-of-day wallet balance",
     "value": 2.0, "direction": "lowers risk", "shap_value": -0.075,
     "sentence": "Lowers your risk: lowest end-of-day wallet balance (typical: KES 2)"}
  ],
  "data_notes": [
    {"family": "fuliza_repay_lag_median_days_90", "label": "typical time taken to repay Fuliza",
     "sentence": "No data in this statement on: typical time taken to repay Fuliza"}
  ],
  "affordability": {"requested_amount": 5000.0, "requested_term_days": 14.0, "estimated_repayment": 5000.0,
                    "amount_to_income_30": 0.0319, "amount_to_avg_monthly_income_90": 0.0304, "band": "comfortable",
                    "band_cutoffs": {"comfortable_up_to": 0.0564, "stretched_up_to": 0.4194},
                    "note": "Compared with your income, this loan is no larger than for a typical applicant."},
  "inputs_used": {"requested_amount": 5000.0, "requested_term_days": 14.0,
                  "scored_at": {"requested_amount": 5000.0, "requested_term_days": 19.0},
                  "application_date": "2026-06-30", "history_days": 183.0, "transactions_used": 3425,
                  "transactions_after_date_ignored": 0},
  "warnings": [{"code": "score_at_median_request", "message": "The score is worked out for a typical loan (KES 5,000 for 19 days), so it does not depend on the loan you ask for. See 'affordability' for your request."}],
  "explanation": {"base_value": -1.867, "logit": -1.951},
  "model_info": {"model": "logistic", "seed": 42, "n_features": 52, "settings": {"C": 0.01}, "labels": "simulated"}
}
```

For this vendor (about KES 164,000 of customer income a month), KES 1,000 to 7,500 is "comfortable", KES 10,000 is
"stretched" and KES 200,000 is "heavy" (1.22 times monthly income). The PD is 0.1244 at every amount.

- `pillar_ratings.rating`: percentile of the vendor's pillar score among the 2,244 simulated applications, flipped so
  100 = best. Weak < 25 <= Fair < 50 <= Good < 75 <= Strong. Worked out at the median request.
- `top_reasons`: up to five reasons, chosen by `feature_labels.select_reasons` as follows.
  1. **Missing data is neutral.** A missing-data flag, or a feature with no data, is never a reason and never says
     "raises/lowers your risk". If a whole family has no data, it gets a note in `data_notes` ("No data in this
     statement on: ..."), and the five reasons are filled from the next real ones.
  2. **One reason per family.** A family is the 30/60/90-day versions of a measure plus its missing flag
     (`FEATURE_FAMILIES`). The member with the largest absolute SHAP value is used.
  3. **One reason per measure group** (`MEASURE_GROUPS`: income size, Fuliza use, wallet balance, money left over).
     Two reasons from one group would contradict each other or repeat a theme, so the larger SHAP is kept.
  4. **The loan request fields are never reasons**, because the score is worked out at the median request.

  `explanation.base_value` + the sum of all (unmerged) SHAP values equals `explanation.logit` (the model's log-odds)
  exactly. `--full` and the Python result include every SHAP value.
- `warnings` (each has a `code`):
  - `score_at_median_request` (always present);
  - `thin_history` (fewer than 90 days before the application date);
  - `request_outside_training_range` (information only: the amount or term is outside the 1st to 99th percentile of
    the simulated requests, KES 1,300 to 10,000 and 7 to 30 days; it is used as typed and the band is relative to
    simulated requests; `fields` holds the entered value and the range);
  - `integrity_flags` (counts of rows that broke a `clean.py` check, only rows actually used);
  - `unparsed_rows` (rows whose time or balance could not be read; they are skipped but always counted);
  - reader notes: `skipped_non_transaction_rows` (with a breakdown of repeated headers, blank rows and footers),
    `same_second_reordered`, `balance_breaks` and `duplicate_receipts`.
- Errors are `ValueError`s with a message safe to show: no transactions, no usable transactions before the date, an
  unsupported or empty file, a PDF without a text layer ("Please ask for the Excel (.xlsx) or CSV version of your M-Pesa
  statement ..."), and a wrong or missing PDF password.

## Rebuilding the reference files

The reference files live in `models/` next to the model. After retraining the model or rebuilding features or the
scorecard, run, from the repo root:

```
python src/train_models.py          # writes models/logistic.joblib
python src/build_reference.py       # writes models/reference.json and models/shap_background.parquet
```

`predict.py` refuses a reference whose feature list differs from the model's, or that has no `affordability_bands`.
It cannot detect a reference built from an older population, so always run both.

## Speed

On a 6-month statement (about 3,400 rows): about 0.2 to 0.9 seconds per call once loaded. The first call in a
process takes about 4 to 5 seconds, almost all of it importing `shap` (numba); call `warm_up()` when the app starts.

## Limitations

- **Simulated labels.** The model recovers a simulated scorecard; nothing here is validated on real repayment.
- **The models do not beat the visible scorecard baseline** (docs/model_report.md). The scoring function is a working
  pipeline with explanations, not evidence that machine learning adds value over the scorecard.
- **The score is evaluated at the median request.** The trained model's coefficients on the request fields are not
  monotone, so the score ignores the requested amount and term and affordability is reported separately. A
  larger loan therefore does not change the score; it shows only in the affordability band. Fixing this properly
  needs a retrained model with sign constraints or a monotone model.
- **Affordability bands are relative to simulated applicants.** The cutoffs are percentiles of simulated requests
  against simulated incomes (the typical applicant asks for about 6% of their monthly income), so "stretched" can mean a loan that is
  small in absolute terms. Repayment is the amount only; fees, interest and the term are not modelled.
- **Estimated eligibility is a prototype policy.** Placeholder tier factors, turnover instead of profit, cutoffs from
  simulated applicants, no validation on repayment outcomes (see the section above).
- **Thin history.** Below 90 days several features are missing and are filled with training medians (plus missing
  flags); the score leans on the population average. The `thin_history` warning says so.
- **Reasons explain the model, not causes.** Grouping families and measure groups removes the obvious
  contradictions, but a reason can still look odd. In the example above, having most income left after payments
  raises risk, because the coefficient carries the effect of correlated features.
- **Requests outside the simulated range.** The simulated loans run from KES 1,300 to 10,000 (1st to 99th
  percentile). A larger request is assessed as typed in the affordability block (so it can reach "heavy"), with the
  information warning `request_outside_training_range`; the band then compares it with simulated requests it is far
  from, and the score itself never reflects the request.
- **PDF input.** The PDF reader is validated only on generated text PDFs. Real M-Pesa PDF statements are scanned
  images and are rejected with a message asking for the Excel or CSV version; OCR is future work.
