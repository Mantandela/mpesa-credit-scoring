# Model report

Seed 42. Split by vendor, balanced by persona. 52 features. Labels are simulated (see assumptions.md), so these numbers describe how well the models recover the synthetic outcome, not performance on real borrowers.

## Split

| split | vendors | applications | defaults | default_rate |
|---|---|---|---|---|
| train | 700 | 1579 | 286 | 0.181 |
| val | 149 | 332 | 65 | 0.196 |
| test | 151 | 350 | 64 | 0.183 |

## Tuning (train vendors only, 5-fold CV grouped by vendor)

| model | best_settings | cv_auc_mean | cv_auc_sd |
|---|---|---|---|
| logistic | {'C': 0.01} | 0.717 | 0.016 |
| random_forest | {'min_samples_leaf': 5} | 0.735 | 0.034 |
| xgboost | {'max_depth': 2, 'n_estimators': 200} | 0.736 | 0.020 |

## Results

| model | val AUC | test AUC | test AUC 95% low | test AUC 95% high | test PR-AUC | test KS | test Brier |
|---|---|---|---|---|---|---|---|
| logistic | 0.776 | 0.726 | 0.646 | 0.807 | 0.398 | 0.412 | 0.132 |
| random_forest | 0.765 | 0.757 | 0.688 | 0.823 | 0.458 | 0.394 | 0.127 |
| xgboost | 0.760 | 0.752 | 0.681 | 0.821 | 0.439 | 0.402 | 0.128 |
| rule_baseline | 0.752 | 0.745 | 0.671 | 0.816 | 0.441 | 0.403 | nan |
| scorecard_baseline | 0.778 | 0.749 | 0.679 | 0.818 | 0.434 | 0.436 | nan |

Intervals come from resampling test vendors 1,000 times. `rule_baseline` ranks vendors by share of near-zero-balance days with no fitting. `scorecard_baseline` is the visible cash-flow scorecard (features and weights only, no hidden terms), also with no fitting. A model should beat both clearly to justify its complexity.

## Lender view: default rate among approved applicants (test)

The cutoff is set on the validation set so that the target share is approved, then applied to the test set. Default rate with no scoring on test: 18.3%.

| model | approval target | actual approval on test | default rate among approved |
|---|---|---|---|
| logistic | 70% | 0.669 | 0.098 |
| logistic | 80% | 0.766 | 0.112 |
| logistic | 90% | 0.846 | 0.135 |
| random_forest | 70% | 0.651 | 0.096 |
| random_forest | 80% | 0.726 | 0.110 |
| random_forest | 90% | 0.857 | 0.133 |
| xgboost | 70% | 0.654 | 0.100 |
| xgboost | 80% | 0.749 | 0.115 |
| xgboost | 90% | 0.863 | 0.129 |
| rule_baseline | 70% | 0.691 | 0.107 |
| rule_baseline | 80% | 0.786 | 0.116 |
| rule_baseline | 90% | 0.883 | 0.142 |
| scorecard_baseline | 70% | 0.654 | 0.092 |
| scorecard_baseline | 80% | 0.789 | 0.120 |
| scorecard_baseline | 90% | 0.860 | 0.133 |

## Inside each persona (out-of-fold AUC on train + validation)

If the models only recognised which persona a vendor belongs to, these numbers would sit near 0.5. Overall out-of-fold AUC: logistic 0.730, random forest 0.743, xgboost 0.740.

| persona | applications | default_rate | logistic | random_forest | xgboost |
|---|---|---|---|---|---|
| growing | 309 | 0.097 | 0.543 | 0.621 | 0.628 |
| new | 142 | 0.239 | 0.628 | 0.664 | 0.622 |
| seasonal | 400 | 0.140 | 0.576 | 0.556 | 0.562 |
| stable | 599 | 0.073 | 0.507 | 0.601 | 0.565 |
| struggling | 461 | 0.406 | 0.597 | 0.608 | 0.597 |

## What the models use

XGBoost importance (gain, top 12):

- fuliza_funded_share_90: 0.103
- amount_to_avg_monthly_income_90: 0.080
- income_total_30: 0.059
- debt_service_ratio_90: 0.032
- fuliza_draws_90: 0.031
- fee_share_of_income_90: 0.030
- till_share_90: 0.029
- income_total_90: 0.024
- near_zero_day_share_60: 0.024
- fuliza_draws_60: 0.021
- income_total_60: 0.020
- balance_median_eod_90: 0.019

Logistic regression coefficients (inputs are rank-normalised, so sizes are comparable; positive = higher risk):

- fuliza_repay_lag_median_days_90: +0.12
- weekly_income_cv_90: +0.11
- income_active_day_share_30: +0.09
- balance_median_eod_90: -0.09
- fuliza_repay_lag_median_days_90 (missing flag): +0.08
- withdraw_share_of_income_60: +0.07
- fee_share_of_income_90: +0.07
- till_share_90: -0.06
- income_active_day_share_60: +0.06
- net_cash_flow_ratio_90: -0.06
- fuliza_draws_90: +0.06
- fuliza_draws_60: +0.06

Next: SHAP explanations, fairness check by gender, and the affordability simulation.
