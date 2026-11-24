# Model report

Seed 42. Split by vendor, balanced by persona. 52 features. Labels are simulated (see assumptions.md), so these numbers describe how well the models recover the synthetic outcome, not performance on real borrowers.

## Split

| split | vendors | applications | defaults | default_rate |
|---|---|---|---|---|
| train | 700 | 1579 | 285 | 0.180 |
| val | 149 | 332 | 57 | 0.172 |
| test | 151 | 350 | 65 | 0.186 |

## Tuning (train vendors only, 5-fold CV grouped by vendor)

| model | best_settings | cv_auc_mean | cv_auc_sd |
|---|---|---|---|
| logistic | {'C': 0.01} | 0.713 | 0.010 |
| random_forest | {'min_samples_leaf': 5} | 0.719 | 0.023 |
| xgboost | {'max_depth': 2, 'n_estimators': 200} | 0.697 | 0.025 |

## Results

| model | val AUC | test AUC | test AUC 95% low | test AUC 95% high | test PR-AUC | test KS | test Brier |
|---|---|---|---|---|---|---|---|
| logistic | 0.757 | 0.730 | 0.650 | 0.807 | 0.400 | 0.400 | 0.134 |
| random_forest | 0.747 | 0.770 | 0.701 | 0.830 | 0.439 | 0.435 | 0.128 |
| xgboost | 0.756 | 0.743 | 0.672 | 0.814 | 0.441 | 0.384 | 0.130 |
| rule_baseline | 0.737 | 0.760 | 0.687 | 0.829 | 0.459 | 0.440 | nan |
| scorecard_baseline | 0.767 | 0.757 | 0.680 | 0.826 | 0.435 | 0.429 | nan |

Intervals come from resampling test vendors 1,000 times. `rule_baseline` ranks vendors by share of near-zero-balance days with no fitting. `scorecard_baseline` is the visible cash-flow scorecard (features and weights only, no hidden terms), also with no fitting. A model should beat both clearly to justify its complexity.

## Lender view: default rate among approved applicants (test)

The cutoff is set on the validation set so that the target share is approved, then applied to the test set. Default rate with no scoring on test: 18.6%.

| model | approval target | actual approval on test | default rate among approved |
|---|---|---|---|
| logistic | 70% | 0.689 | 0.104 |
| logistic | 80% | 0.760 | 0.113 |
| logistic | 90% | 0.866 | 0.145 |
| random_forest | 70% | 0.666 | 0.103 |
| random_forest | 80% | 0.777 | 0.110 |
| random_forest | 90% | 0.889 | 0.151 |
| xgboost | 70% | 0.671 | 0.106 |
| xgboost | 80% | 0.766 | 0.119 |
| xgboost | 90% | 0.883 | 0.139 |
| rule_baseline | 70% | 0.691 | 0.099 |
| rule_baseline | 80% | 0.786 | 0.120 |
| rule_baseline | 90% | 0.883 | 0.142 |
| scorecard_baseline | 70% | 0.660 | 0.091 |
| scorecard_baseline | 80% | 0.780 | 0.121 |
| scorecard_baseline | 90% | 0.863 | 0.142 |

## Inside each persona (out-of-fold AUC on train + validation)

If the models only recognised which persona a vendor belongs to, these numbers would sit near 0.5. Overall out-of-fold AUC: logistic 0.717, random forest 0.715, xgboost 0.707.

| persona | applications | default_rate | logistic | random_forest | xgboost |
|---|---|---|---|---|---|
| growing | 309 | 0.117 | 0.628 | 0.655 | 0.623 |
| new | 142 | 0.211 | 0.630 | 0.643 | 0.646 |
| seasonal | 400 | 0.145 | 0.552 | 0.556 | 0.507 |
| stable | 599 | 0.075 | 0.550 | 0.569 | 0.597 |
| struggling | 461 | 0.375 | 0.605 | 0.597 | 0.571 |

## What the models use

XGBoost importance (gain, top 12):

- near_zero_day_share_60: 0.068
- debt_service_ratio_90: 0.062
- amount_to_avg_monthly_income_90: 0.061
- near_zero_day_share_30: 0.052
- fuliza_funded_share_90: 0.040
- income_count_90: 0.024
- fuliza_draws_90: 0.023
- income_total_60: 0.021
- fee_share_of_income_90: 0.021
- income_total_30: 0.020
- unique_senders_90: 0.020
- balance_median_eod_90: 0.019

Logistic regression coefficients (inputs are rank-normalised, so sizes are comparable; positive = higher risk):

- fuliza_repay_lag_median_days_90: +0.12
- income_active_day_share_30: +0.10
- weekly_income_cv_90: +0.09
- fee_share_of_income_90: +0.08
- withdraw_share_of_income_60: +0.08
- balance_median_eod_90: -0.07
- history_days: -0.07
- free_cash_flow_ratio_90: -0.07
- net_cash_flow_ratio_90: -0.06
- median_ticket_30: -0.06
- fuliza_funded_share_90: +0.06
- fuliza_draws_90: +0.06

Next: SHAP explanations, fairness check by gender, and the affordability simulation.
