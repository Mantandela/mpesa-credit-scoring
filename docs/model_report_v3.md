# Model report

Seed 42. Split by vendor, balanced by persona. 52 features. Labels are simulated (see assumptions.md), so these numbers describe how well the models recover the synthetic outcome, not performance on real borrowers.

## Split

| split | vendors | applications | defaults | default_rate |
|---|---|---|---|---|
| train | 700 | 1561 | 283 | 0.181 |
| val | 151 | 336 | 48 | 0.143 |
| test | 149 | 347 | 62 | 0.179 |

## Tuning (train vendors only, 5-fold CV grouped by vendor)

| model | best_settings | cv_auc_mean | cv_auc_sd |
|---|---|---|---|
| logistic | {'C': 0.01} | 0.686 | 0.017 |
| random_forest | {'min_samples_leaf': 10} | 0.684 | 0.015 |
| xgboost | {'max_depth': 2, 'n_estimators': 200} | 0.681 | 0.016 |

## Results

| model | val AUC | test AUC | test AUC 95% low | test AUC 95% high | test PR-AUC | test KS | test Brier |
|---|---|---|---|---|---|---|---|
| logistic | 0.705 | 0.733 | 0.660 | 0.799 | 0.385 | 0.410 | 0.132 |
| random_forest | 0.651 | 0.727 | 0.652 | 0.794 | 0.323 | 0.424 | 0.136 |
| xgboost | 0.627 | 0.716 | 0.634 | 0.791 | 0.346 | 0.335 | 0.134 |
| rule_baseline | 0.709 | 0.746 | 0.676 | 0.810 | 0.371 | 0.408 | nan |
| scorecard_baseline | 0.708 | 0.746 | 0.672 | 0.811 | 0.406 | 0.416 | nan |

Intervals come from resampling test vendors 1,000 times. `rule_baseline` ranks vendors by share of near-zero-balance days with no fitting. `scorecard_baseline` is the visible cash-flow scorecard (features and weights only, no hidden terms), also with no fitting. A model should beat both clearly to justify its complexity.

## Lender view: default rate among approved applicants (test)

The cutoff is set on the validation set so that the target share is approved, then applied to the test set. Default rate with no scoring on test: 17.9%.

| model | approval target | actual approval on test | default rate among approved |
|---|---|---|---|
| logistic | 70% | 0.671 | 0.090 |
| logistic | 80% | 0.767 | 0.124 |
| logistic | 90% | 0.899 | 0.147 |
| random_forest | 70% | 0.683 | 0.097 |
| random_forest | 80% | 0.778 | 0.126 |
| random_forest | 90% | 0.856 | 0.148 |
| xgboost | 70% | 0.640 | 0.113 |
| xgboost | 80% | 0.758 | 0.122 |
| xgboost | 90% | 0.876 | 0.141 |
| rule_baseline | 70% | 0.657 | 0.092 |
| rule_baseline | 80% | 0.787 | 0.125 |
| rule_baseline | 90% | 0.905 | 0.146 |
| scorecard_baseline | 70% | 0.683 | 0.093 |
| scorecard_baseline | 80% | 0.807 | 0.118 |
| scorecard_baseline | 90% | 0.919 | 0.150 |

## Inside each persona (out-of-fold AUC on train + validation)

If the models only recognised which persona a vendor belongs to, these numbers would sit near 0.5. Overall out-of-fold AUC: logistic 0.686, random forest 0.673, xgboost 0.663.

| persona | applications | default_rate | logistic | random_forest | xgboost |
|---|---|---|---|---|---|
| growing | 344 | 0.087 | 0.504 | 0.497 | 0.500 |
| new | 129 | 0.178 | 0.438 | 0.475 | 0.505 |
| seasonal | 384 | 0.180 | 0.633 | 0.595 | 0.563 |
| stable | 591 | 0.093 | 0.512 | 0.466 | 0.515 |
| struggling | 449 | 0.343 | 0.595 | 0.591 | 0.563 |

## What the models use

XGBoost importance (gain, top 12):

- near_zero_day_share_30: 0.084
- near_zero_day_share_90: 0.066
- near_zero_day_share_60: 0.063
- debt_service_ratio_90: 0.053
- fuliza_funded_share_90: 0.046
- balance_cv_90: 0.028
- income_count_90: 0.023
- fuliza_draws_30: 0.023
- income_count_60: 0.022
- income_total_90: 0.022
- net_cash_flow_ratio_90: 0.021
- free_cash_flow_ratio_90: 0.019

Logistic regression coefficients (inputs are rank-normalised, so sizes are comparable; positive = higher risk):

- withdraw_share_of_income_30: +0.10
- balance_cv_90: +0.10
- days_since_last_fuliza_draw: -0.10
- withdraw_share_of_income_60: -0.09
- essential_outflow_share_90: -0.09
- near_zero_day_share_60: +0.08
- fuliza_repay_lag_median_days_90 (missing flag): +0.07
- income_active_day_share_30: -0.07
- weekly_income_cv_90: +0.06
- amount_to_income_30: -0.06
- withdraw_share_of_income_90: +0.06
- requested_amount: +0.05

Next: SHAP explanations, fairness check by gender, and the affordability simulation.
