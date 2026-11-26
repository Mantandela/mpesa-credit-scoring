# Scoring function

`src/predict.py` scores one M-Pesa statement with the trained logistic regression. The web app calls it from Check
score and Apply ([app_overview.md](app_overview.md)). **All outcomes the model learned from are simulated** (scorecard -> probability -> drawn
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
    requested_amount=5000,                  # KES; used ONLY for the affordability block, as typed (no clipping); default = median (4,900); must be > 0
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
and other file types are refused before anything is written. The web app sets a lower limit of 10 MB and checks it
before it calls `predict`.

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
less risky. For the example vendor below (term 14 days), the PD would be 9.3% at KES 1,300, 10.0% at KES 5,000, 10.2%
at KES 7,500 and 9.4% at KES 10,000. Retraining with sign constraints is out of scope, so:

- the probability of default, score, tier, pillar ratings and reasons are always worked out at the **median request**
  in `reference.json` (KES 4,900 for 19 days), whatever the caller passes. They describe the vendor, not the slider.
  `inputs_used.scored_at` shows the request used and the warning `score_at_median_request` says so.
- the requested amount and term, **exactly as typed** (no clipping, since the model never sees them; only values
  <= 0 are rejected with a `ValueError`), feed the separate **`affordability`** block. It holds the same
  ratios as the features (`amount_to_income_30`, `amount_to_avg_monthly_income_90`) and an estimated repayment (the
  amount only; fees and interest are not modelled). It also gives a band on `amount_to_avg_monthly_income_90`, with
  cutoffs at the 50th and 85th percentile of the 2,261 simulated applications. The bands are **comfortable** (at or
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
  0.058; stretched = 85th percentile, about 0.411). They are read from the file, never hard-coded.
- `monthly_income` is `affordability.amount_to_avg_monthly_income_90` turned back into KES: the vendor's average
  monthly customer income over the last 90 days.
- Example (the simulated vendor below: Moderate risk, about KES 206,300 a month): up to KES 29,600
  (0.35 x 0.4108 x 206,297 = 29,658, rounded down), comfortable up to KES 11,900 (0.0579 x 206,297 = 11,952).
- A typical vendor of each tier (median PD and median monthly income of the simulated applications in the tier, at
  the median request): Low risk (PD 6.2%, score 679, KES 222,000 a month) up to KES 45,500, comfortable 12,800;
  Moderate (PD 11.2%, score 633, KES 114,600) up to KES 16,400, comfortable 6,600; High (PD 23.0%, score 571,
  KES 35,100) up to KES 2,100, comfortable 2,000; Very high (PD 40.8%, score 511, KES 8,200) not eligible.

**This is a placeholder policy for the prototype.** The tier factors are not taken from any lender's policy; monthly
income is statement **turnover** (money received from customers), not profit; the cutoffs describe simulated
applicants; and nothing here is validated on real repayment outcomes. The app says "The lender makes the final
decision."

In the app, Check score shows the estimate and saves it with the check. Apply uses that saved check (at most 30
days old) with no second upload and nothing re-scored, and sends the application only if the check's estimate is
"eligible" and the amount is within its `max_amount`. Otherwise it says why (above the limit, with the limit; not
eligible; not enough income data). See [app_overview.md](app_overview.md#privacy-and-security-rules).

## Output (example: a simulated vendor, 6-month statement, KES 5,000 for 14 days; numbers rounded)

The example statement is kept fixed across retrains so that results can be compared: vendor V00514 of the v0.6
seed-42 run ("new" persona, 183 days, 4,469 rows), saved before the v0.7 regeneration as
`data/test/example_statement_V00514_v06.parquet` (git-ignored, synthetic). The regenerated V00514 is a different vendor.

```json
{
  "probability_of_default": 0.1009,
  "score": 642,
  "tier": "Moderate risk",
  "pillar_ratings": [
    {"pillar": "A_income_stability",   "rating": 82, "label": "Strong", "pillar_score": -0.663},
    {"pillar": "B_cash_flow_buffer",   "rating": 91, "label": "Strong", "pillar_score": -0.540},
    {"pillar": "C_borrowing_distress", "rating": 62, "label": "Good",   "pillar_score": -0.083},
    {"pillar": "D_affordability",      "rating": 61, "label": "Good",   "pillar_score": -0.024},
    {"pillar": "E_obligations",        "rating": 51, "label": "Good",   "pillar_score":  0.091},
    {"pillar": "F_history_growth",     "rating": 44, "label": "Fair",   "pillar_score":  0.229},
    {"pillar": "G_network",            "rating": 41, "label": "Fair",   "pillar_score":  0.156}
  ],
  "top_reasons": [
    {"feature": "fuliza_draws_90", "family": "fuliza_draws", "label": "number of times you used Fuliza",
     "value": 0.0, "direction": "lowers risk", "shap_value": -0.223,
     "sentence": "Lowers your risk: number of times you used Fuliza (low: 0)"},
    {"feature": "net_cash_flow_ratio_90", "family": "net_cash_flow_ratio_90", "label": "income left after payments and charges",
     "value": 0.959, "direction": "lowers risk", "shap_value": -0.184,
     "sentence": "Lowers your risk: income left after payments and charges (high: 96%)"},
    {"feature": "withdraw_share_of_income_60", "family": "withdraw_share_of_income",
     "label": "cash withdrawn at agents compared with customer income (last 60 days)", "value": 0.975,
     "direction": "raises risk", "shap_value": 0.115,
     "sentence": "Raises your risk: cash withdrawn at agents compared with customer income (last 60 days) (high: 97%)"},
    {"feature": "failed_payment_share_90", "family": "failed_payment_share_90", "label": "payments that failed",
     "value": 0.045, "direction": "lowers risk", "shap_value": -0.084,
     "sentence": "Lowers your risk: payments that failed (high: 5%)"},
    {"feature": "income_active_day_share_30", "family": "income_active_day_share",
     "label": "days with at least one customer payment (last 30 days)", "value": 0.9,
     "direction": "raises risk", "shap_value": 0.080,
     "sentence": "Raises your risk: days with at least one customer payment (last 30 days) (high: 90% of days)"}
  ],
  "data_notes": [
    {"family": "fuliza_repay_lag_median_days_90", "label": "typical time taken to repay Fuliza",
     "sentence": "No data in this statement on: typical time taken to repay Fuliza"}
  ],
  "affordability": {"requested_amount": 5000.0, "requested_term_days": 14.0, "estimated_repayment": 5000.0,
                    "amount_to_income_30": 0.0244, "amount_to_avg_monthly_income_90": 0.0242, "band": "comfortable",
                    "band_cutoffs": {"comfortable_up_to": 0.0579, "stretched_up_to": 0.4108},
                    "note": "Compared with your income, this loan is no larger than for a typical applicant."},
  "inputs_used": {"requested_amount": 5000.0, "requested_term_days": 14.0,
                  "scored_at": {"requested_amount": 4900.0, "requested_term_days": 19.0},
                  "application_date": "2026-07-01", "history_days": 183.0, "transactions_used": 4469,
                  "transactions_after_date_ignored": 0},
  "warnings": [{"code": "score_at_median_request", "message": "The score is worked out for a typical loan (KES 4,900 for 19 days), so it does not depend on the loan you ask for. See 'affordability' for your request."}],
  "explanation": {"base_value": -1.688, "logit": -2.188},
  "model_info": {"model": "logistic", "seed": 42, "n_features": 52, "settings": {"C": 0.01}, "labels": "simulated"}
}
```

For this vendor (about KES 206,300 of customer income a month), KES 1,000 to 10,000 is "comfortable", KES 20,000 is
"stretched" and KES 200,000 is "heavy" (0.97 times monthly income). The PD is 0.1009 at every amount.

Risk tiers (`scoring.TIER_BANDS`): Low below PD 8%, Moderate 8% to 17%, High 17% to 30%, Very high 30% and above. At
the median request they hold 22.2%, 40.2%, 19.5% and 18.1% of the 2,261 simulated applications (mean PD 18.4%).

The score formula (`scoring.pd_to_score`) is `600 + 50 x log2(((1 - PD) / PD) / 5)`, rounded and clipped to 300-850:
PD 16.7% (odds 5 to 1) scores exactly 600, and PD 2% scores 765 (764.6 before rounding). On the score scale the tier
boundaries fall at **660.08** (PD 8%), **598.28** (PD 17%) and **545.02** (PD 30%). The tier is assigned from the
PD, not from the rounded score, so the rounded scores **660, 598 and 545 can belong to either tier** next to them;
661, 599 and 546 are the first scores always in the lower-risk tier. The overlap is at most one point and does not
change any tier. The check is in [calibration_report.md](calibration_report.md#score-formula).

- `pillar_ratings.rating`: percentile of the vendor's pillar score among the 2,261 simulated applications, flipped so
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

- **Simulated labels.** The model recovers a simulated scorecard; nothing here is validated on real repayment, and
  the test set is small, so every interval is wide ([calibration_report.md](calibration_report.md#limits)).
- **No model clearly beats the visible scorecard baseline.** On the test vendors the random forest and XGBoost are
  level with the scorecard baseline within wide, overlapping 95% intervals, and the logistic regression used here is
  a little below them; every paired difference includes zero ([model_report.md](model_report.md#results),
  [calibration_report.md](calibration_report.md#discrimination-test-set)). The scoring function is a working
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
  contradictions, but a reason can still look odd. In the example above, a higher share of failed payments lowers
  risk and selling on more days raises it, because each coefficient carries the effect of correlated features.
- **Requests outside the simulated range.** The simulated loans run from KES 1,300 to 10,000 (1st to 99th
  percentile). A larger request is assessed as typed in the affordability block (so it can reach "heavy"), with the
  information warning `request_outside_training_range`; the band then compares it with simulated requests it is far
  from, and the score itself never reflects the request.
- **PDF input.** The PDF reader is validated only on generated text PDFs. Real M-Pesa PDF statements are scanned
  images and are rejected with a message asking for the Excel or CSV version; OCR is future work.

## See also

- [Project README](../README.md)
- [Scorecard mapping](scorecard_mapping.md)
- [Model report](model_report.md)
- [Calibration report](calibration_report.md)
