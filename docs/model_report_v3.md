# Model report

Seed 42. Split by vendor, balanced by persona. 52 features. Labels are simulated (see assumptions.md), so these numbers describe how well the models recover the synthetic outcome, not performance on real borrowers.

## Split

| split | vendors | applications | defaults | default_rate |
|---|---|---|---|---|
| train | 700 | 1579 | 289 | 0.183 |
| val | 149 | 332 | 63 | 0.190 |
| test | 151 | 350 | 63 | 0.180 |

## Tuning (train vendors only, 5-fold CV grouped by vendor)

| model | best_settings | cv_auc_mean | cv_auc_sd |
|---|---|---|---|
| logistic | {'C': 0.01} | 0.707 | 0.024 |
| random_forest | {'min_samples_leaf': 10} | 0.708 | 0.027 |
| xgboost | {'max_depth': 2, 'n_estimators': 200} | 0.699 | 0.034 |

## Results

| model | val AUC | test AUC | test AUC 95% low | test AUC 95% high | test PR-AUC | test KS | test Brier |
|---|---|---|---|---|---|---|---|
| logistic | 0.768 | 0.712 | 0.629 | 0.795 | 0.376 | 0.386 | 0.133 |
| random_forest | 0.771 | 0.749 | 0.678 | 0.816 | 0.442 | 0.405 | 0.126 |
| xgboost | 0.753 | 0.737 | 0.665 | 0.809 | 0.428 | 0.386 | 0.128 |
| rule_baseline | 0.750 | 0.735 | 0.659 | 0.807 | 0.433 | 0.385 | nan |
| scorecard_baseline | 0.763 | 0.734 | 0.659 | 0.808 | 0.430 | 0.393 | nan |

Intervals come from resampling test vendors 1,000 times. `rule_baseline` ranks vendors by share of near-zero-balance days with no fitting. `scorecard_baseline` is the visible cash-flow scorecard (features and weights only, no hidden terms), also with no fitting. A model should beat both clearly to justify its complexity.

## Lender view: default rate among approved applicants (test)

The cutoff is set on the validation set so that the target share is approved, then applied to the test set. Default rate with no scoring on test: 18.0%.

| model | approval target | actual approval on test | default rate among approved |
|---|---|---|---|
| logistic | 70% | 0.677 | 0.101 |
| logistic | 80% | 0.760 | 0.117 |
| logistic | 90% | 0.849 | 0.138 |
| random_forest | 70% | 0.654 | 0.096 |
| random_forest | 80% | 0.749 | 0.115 |
| random_forest | 90% | 0.849 | 0.135 |
| xgboost | 70% | 0.649 | 0.097 |
| xgboost | 80% | 0.737 | 0.112 |
| xgboost | 90% | 0.860 | 0.123 |
| rule_baseline | 70% | 0.691 | 0.112 |
| rule_baseline | 80% | 0.786 | 0.116 |
| rule_baseline | 90% | 0.883 | 0.139 |
| scorecard_baseline | 70% | 0.660 | 0.095 |
| scorecard_baseline | 80% | 0.780 | 0.121 |
| scorecard_baseline | 90% | 0.863 | 0.136 |

## Inside each persona (out-of-fold AUC on train + validation)

If the models only recognised which persona a vendor belongs to, these numbers would sit near 0.5. Overall out-of-fold AUC: logistic 0.723, random forest 0.735, xgboost 0.730.

| persona | applications | default_rate | logistic | random_forest | xgboost |
|---|---|---|---|---|---|
| growing | 309 | 0.097 | 0.539 | 0.616 | 0.609 |
| new | 142 | 0.225 | 0.680 | 0.686 | 0.658 |
| seasonal | 400 | 0.145 | 0.557 | 0.580 | 0.567 |
| stable | 599 | 0.083 | 0.547 | 0.601 | 0.616 |
| struggling | 461 | 0.395 | 0.619 | 0.638 | 0.618 |

## What the models use

XGBoost importance (gain, top 12):

- fuliza_funded_share_90: 0.089
- income_total_30: 0.072
- debt_service_ratio_90: 0.064
- amount_to_avg_monthly_income_90: 0.062
- fee_share_of_income_90: 0.036
- near_zero_day_share_60: 0.025
- fuliza_draws_60: 0.024
- fuliza_draws_90: 0.022
- median_ticket_90: 0.021
- income_total_60: 0.020
- balance_median_eod_90: 0.018
- reversal_count_90: 0.018

Logistic regression coefficients (inputs are rank-normalised, so sizes are comparable; positive = higher risk):

- fuliza_repay_lag_median_days_90: +0.13
- income_active_day_share_30: +0.11
- weekly_income_cv_90: +0.10
- fuliza_repay_lag_median_days_90 (missing flag): +0.09
- balance_median_eod_90: -0.08
- free_cash_flow_ratio_90: -0.08
- withdraw_share_of_income_60: +0.08
- net_cash_flow_ratio_90: -0.07
- near_zero_day_share_60: -0.07
- fuliza_draws_90: +0.06
- fuliza_funded_share_90: +0.06
- fee_share_of_income_90: +0.06

Next: SHAP explanations, fairness check by gender, and the affordability simulation.

## Limits

This is sensitivity variant 3: FICO-like weights, shock 0.5, row 4 of the tables in [sensitivity_report.md](sensitivity_report.md).
Its outcomes are redrawn from a different simulated scorecard, so its numbers are not the deployed model's; those
are in [model_report.md](model_report.md). The outcomes are simulated and the test set is small, so the intervals
are wide ([calibration_report.md](calibration_report.md#limits)).

## See also

- [Project README](../README.md)
- [Sensitivity report](sensitivity_report.md)
- [Model report](model_report.md)
