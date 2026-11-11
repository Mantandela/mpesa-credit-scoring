# Model report

Seed 42. Split by vendor, balanced by persona. 52 features. Labels are simulated (see assumptions.md), so these numbers describe how well the models recover the synthetic outcome, not performance on real borrowers.

## Split

| split | vendors | applications | defaults | default_rate |
|---|---|---|---|---|
| train | 700 | 1561 | 282 | 0.181 |
| val | 151 | 336 | 52 | 0.155 |
| test | 149 | 347 | 67 | 0.193 |

## Tuning (train vendors only, 5-fold CV grouped by vendor)

| model | best_settings | cv_auc_mean | cv_auc_sd |
|---|---|---|---|
| logistic | {'C': 0.01} | 0.722 | 0.027 |
| random_forest | {'min_samples_leaf': 10} | 0.717 | 0.031 |
| xgboost | {'max_depth': 2, 'n_estimators': 200} | 0.714 | 0.029 |

## Results

| model | val AUC | test AUC | test AUC 95% low | test AUC 95% high | test PR-AUC | test KS | test Brier |
|---|---|---|---|---|---|---|---|
| logistic | 0.751 | 0.768 | 0.696 | 0.829 | 0.449 | 0.484 | 0.132 |
| random_forest | 0.723 | 0.753 | 0.684 | 0.815 | 0.391 | 0.493 | 0.135 |
| xgboost | 0.695 | 0.722 | 0.640 | 0.790 | 0.375 | 0.462 | 0.140 |
| rule_baseline | 0.760 | 0.771 | 0.704 | 0.828 | 0.426 | 0.461 | nan |
| scorecard_baseline | 0.759 | 0.773 | 0.701 | 0.833 | 0.462 | 0.503 | nan |

Intervals come from resampling test vendors 1,000 times. `rule_baseline` ranks vendors by share of near-zero-balance days with no fitting. `scorecard_baseline` is the visible cash-flow scorecard (features and weights only, no hidden terms), also with no fitting. A model should beat both clearly to justify its complexity.

## Lender view: default rate among approved applicants (test)

The cutoff is set on the validation set so that the target share is approved, then applied to the test set. Default rate with no scoring on test: 19.3%.

| model | approval target | actual approval on test | default rate among approved |
|---|---|---|---|
| logistic | 70% | 0.654 | 0.084 |
| logistic | 80% | 0.775 | 0.108 |
| logistic | 90% | 0.896 | 0.154 |
| random_forest | 70% | 0.660 | 0.079 |
| random_forest | 80% | 0.801 | 0.137 |
| random_forest | 90% | 0.879 | 0.154 |
| xgboost | 70% | 0.637 | 0.090 |
| xgboost | 80% | 0.801 | 0.144 |
| xgboost | 90% | 0.885 | 0.163 |
| rule_baseline | 70% | 0.657 | 0.088 |
| rule_baseline | 80% | 0.787 | 0.125 |
| rule_baseline | 90% | 0.905 | 0.156 |
| scorecard_baseline | 70% | 0.671 | 0.077 |
| scorecard_baseline | 80% | 0.787 | 0.114 |
| scorecard_baseline | 90% | 0.925 | 0.162 |

## Inside each persona (out-of-fold AUC on train + validation)

If the models only recognised which persona a vendor belongs to, these numbers would sit near 0.5. Overall out-of-fold AUC: logistic 0.732, random forest 0.715, xgboost 0.708.

| persona | applications | default_rate | logistic | random_forest | xgboost |
|---|---|---|---|---|---|
| growing | 344 | 0.058 | 0.511 | 0.508 | 0.497 |
| new | 129 | 0.178 | 0.406 | 0.444 | 0.444 |
| seasonal | 384 | 0.190 | 0.642 | 0.583 | 0.588 |
| stable | 591 | 0.076 | 0.560 | 0.478 | 0.468 |
| struggling | 449 | 0.385 | 0.577 | 0.555 | 0.533 |

## What the models use

XGBoost importance (gain, top 12):

- near_zero_day_share_90: 0.118
- near_zero_day_share_60: 0.106
- near_zero_day_share_30: 0.096
- fuliza_funded_share_90: 0.050
- debt_service_ratio_90: 0.036
- income_total_90: 0.021
- balance_cv_90: 0.020
- balance_median_eod_90: 0.019
- withdraw_share_of_income_60: 0.017
- till_share_90: 0.016
- income_total_30: 0.016
- amount_to_avg_monthly_income_90: 0.015

Logistic regression coefficients (inputs are rank-normalised, so sizes are comparable; positive = higher risk):

- balance_cv_90: +0.11
- essential_outflow_share_90: -0.10
- withdraw_share_of_income_30: +0.10
- days_since_last_fuliza_draw: -0.10
- weekly_income_cv_90: +0.09
- withdraw_share_of_income_60: -0.08
- near_zero_day_share_60: +0.08
- balance_min_eod_90: -0.07
- income_active_day_share_30: -0.06
- amount_to_income_30: -0.06
- near_zero_day_share_90: -0.06
- cash_deposit_share_90: +0.06

Next: SHAP explanations, fairness check by gender, and the affordability simulation.
