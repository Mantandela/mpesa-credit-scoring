# Model report

Seed 42. Split by vendor, balanced by persona. 52 features. Labels are simulated (see assumptions.md), so these numbers describe how well the models recover the synthetic outcome, not performance on real borrowers.

## Split

| split | vendors | applications | defaults | default_rate |
|---|---|---|---|---|
| train | 700 | 1579 | 290 | 0.184 |
| val | 149 | 332 | 63 | 0.190 |
| test | 151 | 350 | 60 | 0.171 |

## Tuning (train vendors only, 5-fold CV grouped by vendor)

| model | best_settings | cv_auc_mean | cv_auc_sd |
|---|---|---|---|
| logistic | {'C': 0.01} | 0.719 | 0.028 |
| random_forest | {'min_samples_leaf': 10} | 0.731 | 0.042 |
| xgboost | {'max_depth': 3, 'n_estimators': 200} | 0.727 | 0.041 |

## Results

| model | val AUC | test AUC | test AUC 95% low | test AUC 95% high | test PR-AUC | test KS | test Brier |
|---|---|---|---|---|---|---|---|
| logistic | 0.796 | 0.742 | 0.669 | 0.818 | 0.403 | 0.450 | 0.124 |
| random_forest | 0.783 | 0.776 | 0.707 | 0.839 | 0.465 | 0.444 | 0.119 |
| xgboost | 0.779 | 0.763 | 0.691 | 0.833 | 0.456 | 0.447 | 0.121 |
| rule_baseline | 0.759 | 0.766 | 0.695 | 0.829 | 0.448 | 0.434 | nan |
| scorecard_baseline | 0.792 | 0.767 | 0.695 | 0.834 | 0.424 | 0.460 | nan |

Intervals come from resampling test vendors 1,000 times. `rule_baseline` ranks vendors by share of near-zero-balance days with no fitting. `scorecard_baseline` is the visible cash-flow scorecard (features and weights only, no hidden terms), also with no fitting. A model should beat both clearly to justify its complexity.

## Lender view: default rate among approved applicants (test)

The cutoff is set on the validation set so that the target share is approved, then applied to the test set. Default rate with no scoring on test: 17.1%.

| model | approval target | actual approval on test | default rate among approved |
|---|---|---|---|
| logistic | 70% | 0.666 | 0.082 |
| logistic | 80% | 0.777 | 0.107 |
| logistic | 90% | 0.857 | 0.130 |
| random_forest | 70% | 0.657 | 0.078 |
| random_forest | 80% | 0.769 | 0.108 |
| random_forest | 90% | 0.857 | 0.127 |
| xgboost | 70% | 0.660 | 0.087 |
| xgboost | 80% | 0.743 | 0.108 |
| xgboost | 90% | 0.866 | 0.122 |
| rule_baseline | 70% | 0.691 | 0.095 |
| rule_baseline | 80% | 0.786 | 0.105 |
| rule_baseline | 90% | 0.883 | 0.129 |
| scorecard_baseline | 70% | 0.680 | 0.080 |
| scorecard_baseline | 80% | 0.774 | 0.111 |
| scorecard_baseline | 90% | 0.846 | 0.122 |

## Inside each persona (out-of-fold AUC on train + validation)

If the models only recognised which persona a vendor belongs to, these numbers would sit near 0.5. Overall out-of-fold AUC: logistic 0.741, random forest 0.756, xgboost 0.749.

| persona | applications | default_rate | logistic | random_forest | xgboost |
|---|---|---|---|---|---|
| growing | 309 | 0.097 | 0.532 | 0.627 | 0.601 |
| new | 142 | 0.211 | 0.640 | 0.677 | 0.616 |
| seasonal | 400 | 0.155 | 0.596 | 0.602 | 0.623 |
| stable | 599 | 0.072 | 0.546 | 0.631 | 0.659 |
| struggling | 461 | 0.408 | 0.631 | 0.633 | 0.611 |

## What the models use

XGBoost importance (gain, top 12):

- amount_to_avg_monthly_income_90: 0.065
- income_total_30: 0.063
- fuliza_funded_share_90: 0.048
- debt_service_ratio_90: 0.045
- near_zero_day_share_60: 0.026
- fee_share_of_income_90: 0.025
- fuliza_draws_90: 0.025
- income_count_60: 0.023
- median_ticket_60: 0.023
- near_zero_day_share_30: 0.022
- reversal_count_90: 0.020
- income_total_60: 0.019

Logistic regression coefficients (inputs are rank-normalised, so sizes are comparable; positive = higher risk):

- weekly_income_cv_90: +0.11
- withdraw_share_of_income_60: +0.10
- fuliza_repay_lag_median_days_90: +0.08
- income_active_day_share_30: +0.08
- balance_median_eod_90: -0.08
- net_cash_flow_ratio_90: -0.07
- fuliza_repay_lag_median_days_90 (missing flag): +0.07
- fee_share_of_income_90: +0.07
- fuliza_draws_90: +0.06
- median_ticket_60: -0.06
- income_total_60: -0.06
- free_cash_flow_ratio_90: -0.05

Next: SHAP explanations, fairness check by gender, and the affordability simulation.

## Limits

This is sensitivity variant 2: cash-flow-heavy weights, shock 0.5, row 3 of the tables in [sensitivity_report.md](sensitivity_report.md).
Its outcomes are redrawn from a different simulated scorecard, so its numbers are not the deployed model's; those
are in [model_report.md](model_report.md). The outcomes are simulated and the test set is small, so the intervals
are wide ([calibration_report.md](calibration_report.md#limits)).

## See also

- [Project README](../README.md)
- [Sensitivity report](sensitivity_report.md)
- [Model report](model_report.md)
