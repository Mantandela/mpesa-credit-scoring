# Model report

Seed 42. Split by vendor, balanced by persona. 52 features. Labels are simulated (see assumptions.md), so these numbers describe how well the models recover the synthetic outcome, not performance on real borrowers.

## Split

| split | vendors | applications | defaults | default_rate |
|---|---|---|---|---|
| train | 700 | 1579 | 287 | 0.182 |
| val | 149 | 332 | 62 | 0.187 |
| test | 151 | 350 | 62 | 0.177 |

## Tuning (train vendors only, 5-fold CV grouped by vendor)

| model | best_settings | cv_auc_mean | cv_auc_sd |
|---|---|---|---|
| logistic | {'C': 0.01} | 0.723 | 0.025 |
| random_forest | {'min_samples_leaf': 10} | 0.728 | 0.027 |
| xgboost | {'max_depth': 2, 'n_estimators': 200} | 0.713 | 0.023 |

## Results

| model | val AUC | test AUC | test AUC 95% low | test AUC 95% high | test PR-AUC | test KS | test Brier |
|---|---|---|---|---|---|---|---|
| logistic | 0.785 | 0.726 | 0.644 | 0.807 | 0.392 | 0.440 | 0.130 |
| random_forest | 0.776 | 0.757 | 0.685 | 0.822 | 0.454 | 0.441 | 0.124 |
| xgboost | 0.765 | 0.753 | 0.677 | 0.827 | 0.433 | 0.417 | 0.125 |
| rule_baseline | 0.753 | 0.746 | 0.670 | 0.818 | 0.440 | 0.414 | nan |
| scorecard_baseline | 0.784 | 0.747 | 0.667 | 0.822 | 0.425 | 0.430 | nan |

Intervals come from resampling test vendors 1,000 times. `rule_baseline` ranks vendors by share of near-zero-balance days with no fitting. `scorecard_baseline` is the visible cash-flow scorecard (features and weights only, no hidden terms), also with no fitting. A model should beat both clearly to justify its complexity.

## Lender view: default rate among approved applicants (test)

The cutoff is set on the validation set so that the target share is approved, then applied to the test set. Default rate with no scoring on test: 17.7%.

| model | approval target | actual approval on test | default rate among approved |
|---|---|---|---|
| logistic | 70% | 0.666 | 0.090 |
| logistic | 80% | 0.769 | 0.112 |
| logistic | 90% | 0.851 | 0.134 |
| random_forest | 70% | 0.663 | 0.091 |
| random_forest | 80% | 0.754 | 0.106 |
| random_forest | 90% | 0.860 | 0.133 |
| xgboost | 70% | 0.657 | 0.091 |
| xgboost | 80% | 0.734 | 0.101 |
| xgboost | 90% | 0.860 | 0.123 |
| rule_baseline | 70% | 0.691 | 0.103 |
| rule_baseline | 80% | 0.786 | 0.113 |
| rule_baseline | 90% | 0.883 | 0.136 |
| scorecard_baseline | 70% | 0.660 | 0.087 |
| scorecard_baseline | 80% | 0.780 | 0.114 |
| scorecard_baseline | 90% | 0.863 | 0.132 |

## Inside each persona (out-of-fold AUC on train + validation)

If the models only recognised which persona a vendor belongs to, these numbers would sit near 0.5. Overall out-of-fold AUC: logistic 0.733, random forest 0.742, xgboost 0.734.

| persona | applications | default_rate | logistic | random_forest | xgboost |
|---|---|---|---|---|---|
| growing | 309 | 0.094 | 0.507 | 0.620 | 0.598 |
| new | 142 | 0.211 | 0.670 | 0.693 | 0.686 |
| seasonal | 400 | 0.150 | 0.559 | 0.533 | 0.529 |
| stable | 599 | 0.073 | 0.545 | 0.595 | 0.594 |
| struggling | 461 | 0.403 | 0.625 | 0.620 | 0.600 |

## What the models use

XGBoost importance (gain, top 12):

- amount_to_avg_monthly_income_90: 0.101
- income_total_30: 0.075
- fuliza_funded_share_90: 0.074
- debt_service_ratio_90: 0.044
- fee_share_of_income_90: 0.035
- income_active_day_share_60: 0.027
- fuliza_draws_90: 0.025
- fuliza_draws_60: 0.024
- income_total_60: 0.021
- income_total_90: 0.021
- median_ticket_90: 0.020
- balance_median_eod_90: 0.019

Logistic regression coefficients (inputs are rank-normalised, so sizes are comparable; positive = higher risk):

- weekly_income_cv_90: +0.11
- fuliza_repay_lag_median_days_90: +0.10
- withdraw_share_of_income_60: +0.09
- balance_median_eod_90: -0.08
- income_active_day_share_30: +0.08
- fuliza_repay_lag_median_days_90 (missing flag): +0.08
- fee_share_of_income_90: +0.07
- net_cash_flow_ratio_90: -0.06
- fuliza_draws_90: +0.06
- median_ticket_60: -0.06
- income_total_60: -0.05
- free_cash_flow_ratio_90: -0.05

Next: SHAP explanations, fairness check by gender, and the affordability simulation.
