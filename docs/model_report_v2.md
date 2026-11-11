# Model report

Seed 42. Split by vendor, balanced by persona. 52 features. Labels are simulated (see assumptions.md), so these numbers describe how well the models recover the synthetic outcome, not performance on real borrowers.

## Split

| split | vendors | applications | defaults | default_rate |
|---|---|---|---|---|
| train | 700 | 1561 | 273 | 0.175 |
| val | 151 | 336 | 50 | 0.149 |
| test | 149 | 347 | 65 | 0.187 |

## Tuning (train vendors only, 5-fold CV grouped by vendor)

| model | best_settings | cv_auc_mean | cv_auc_sd |
|---|---|---|---|
| logistic | {'C': 0.01} | 0.722 | 0.026 |
| random_forest | {'min_samples_leaf': 10} | 0.731 | 0.032 |
| xgboost | {'max_depth': 2, 'n_estimators': 200} | 0.723 | 0.028 |

## Results

| model | val AUC | test AUC | test AUC 95% low | test AUC 95% high | test PR-AUC | test KS | test Brier |
|---|---|---|---|---|---|---|---|
| logistic | 0.762 | 0.778 | 0.708 | 0.839 | 0.437 | 0.478 | 0.129 |
| random_forest | 0.727 | 0.751 | 0.676 | 0.814 | 0.371 | 0.469 | 0.135 |
| xgboost | 0.701 | 0.724 | 0.646 | 0.792 | 0.365 | 0.429 | 0.137 |
| rule_baseline | 0.757 | 0.786 | 0.717 | 0.844 | 0.428 | 0.467 | nan |
| scorecard_baseline | 0.760 | 0.784 | 0.710 | 0.843 | 0.464 | 0.520 | nan |

Intervals come from resampling test vendors 1,000 times. `rule_baseline` ranks vendors by share of near-zero-balance days with no fitting. `scorecard_baseline` is the visible cash-flow scorecard (features and weights only, no hidden terms), also with no fitting. A model should beat both clearly to justify its complexity.

## Lender view: default rate among approved applicants (test)

The cutoff is set on the validation set so that the target share is approved, then applied to the test set. Default rate with no scoring on test: 18.7%.

| model | approval target | actual approval on test | default rate among approved |
|---|---|---|---|
| logistic | 70% | 0.657 | 0.079 |
| logistic | 80% | 0.772 | 0.104 |
| logistic | 90% | 0.899 | 0.147 |
| random_forest | 70% | 0.666 | 0.082 |
| random_forest | 80% | 0.778 | 0.137 |
| random_forest | 90% | 0.865 | 0.150 |
| xgboost | 70% | 0.657 | 0.096 |
| xgboost | 80% | 0.769 | 0.139 |
| xgboost | 90% | 0.888 | 0.153 |
| rule_baseline | 70% | 0.657 | 0.083 |
| rule_baseline | 80% | 0.787 | 0.121 |
| rule_baseline | 90% | 0.905 | 0.150 |
| scorecard_baseline | 70% | 0.680 | 0.081 |
| scorecard_baseline | 80% | 0.787 | 0.117 |
| scorecard_baseline | 90% | 0.916 | 0.148 |

## Inside each persona (out-of-fold AUC on train + validation)

If the models only recognised which persona a vendor belongs to, these numbers would sit near 0.5. Overall out-of-fold AUC: logistic 0.734, random forest 0.725, xgboost 0.721.

| persona | applications | default_rate | logistic | random_forest | xgboost |
|---|---|---|---|---|---|
| growing | 344 | 0.067 | 0.472 | 0.483 | 0.461 |
| new | 129 | 0.155 | 0.437 | 0.546 | 0.541 |
| seasonal | 384 | 0.193 | 0.664 | 0.612 | 0.606 |
| stable | 591 | 0.068 | 0.546 | 0.529 | 0.547 |
| struggling | 449 | 0.370 | 0.585 | 0.577 | 0.559 |

## What the models use

XGBoost importance (gain, top 12):

- near_zero_day_share_30: 0.155
- near_zero_day_share_60: 0.105
- near_zero_day_share_90: 0.095
- debt_service_ratio_90: 0.041
- income_total_90: 0.027
- fuliza_amount_90: 0.023
- income_active_day_share_60: 0.019
- fuliza_draws_30: 0.018
- balance_cv_90: 0.018
- income_total_60: 0.017
- till_share_90: 0.016
- supplier_spend_share_90: 0.015

Logistic regression coefficients (inputs are rank-normalised, so sizes are comparable; positive = higher risk):

- withdraw_share_of_income_30: +0.14
- withdraw_share_of_income_60: -0.11
- weekly_income_cv_90: +0.10
- balance_cv_90: +0.10
- days_since_last_fuliza_draw: -0.09
- near_zero_day_share_60: +0.08
- withdraw_share_of_income_90: +0.07
- supplier_spend_share_90: -0.07
- essential_outflow_share_90: -0.07
- fuliza_repay_lag_median_days_90 (missing flag): +0.06
- till_share_90: -0.06
- balance_min_eod_90: -0.06

Next: SHAP explanations, fairness check by gender, and the affordability simulation.
