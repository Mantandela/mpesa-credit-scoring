# Model report

Seed 42. Split by vendor, balanced by persona. 52 features. Labels are simulated (see assumptions.md), so these numbers describe how well the models recover the synthetic outcome, not performance on real borrowers.

## Split

| split | vendors | applications | defaults | default_rate |
|---|---|---|---|---|
| train | 700 | 1561 | 273 | 0.175 |
| val | 151 | 336 | 52 | 0.155 |
| test | 149 | 347 | 62 | 0.179 |

## Tuning (train vendors only, 5-fold CV grouped by vendor)

| model | best_settings | cv_auc_mean | cv_auc_sd |
|---|---|---|---|
| logistic | {'C': 0.01} | 0.706 | 0.040 |
| random_forest | {'min_samples_leaf': 10} | 0.709 | 0.041 |
| xgboost | {'max_depth': 2, 'n_estimators': 200} | 0.699 | 0.048 |

## Results

| model | val AUC | test AUC | test AUC 95% low | test AUC 95% high | test PR-AUC | test KS | test Brier |
|---|---|---|---|---|---|---|---|
| logistic | 0.724 | 0.751 | 0.681 | 0.819 | 0.405 | 0.442 | 0.129 |
| random_forest | 0.700 | 0.716 | 0.650 | 0.788 | 0.301 | 0.444 | 0.136 |
| xgboost | 0.685 | 0.703 | 0.630 | 0.774 | 0.318 | 0.381 | 0.138 |
| rule_baseline | 0.720 | 0.759 | 0.690 | 0.826 | 0.371 | 0.408 | nan |
| scorecard_baseline | 0.728 | 0.756 | 0.681 | 0.826 | 0.400 | 0.450 | nan |

Intervals come from resampling test vendors 1,000 times. `rule_baseline` ranks vendors by share of near-zero-balance days with no fitting. `scorecard_baseline` is the visible cash-flow scorecard (features and weights only, no hidden terms), also with no fitting. A model should beat both clearly to justify its complexity.

## Lender view: default rate among approved applicants (test)

The cutoff is set on the validation set so that the target share is approved, then applied to the test set. Default rate with no scoring on test: 17.9%.

| model | approval target | actual approval on test | default rate among approved |
|---|---|---|---|
| logistic | 70% | 0.646 | 0.085 |
| logistic | 80% | 0.781 | 0.118 |
| logistic | 90% | 0.914 | 0.151 |
| random_forest | 70% | 0.683 | 0.093 |
| random_forest | 80% | 0.787 | 0.143 |
| random_forest | 90% | 0.870 | 0.152 |
| xgboost | 70% | 0.692 | 0.121 |
| xgboost | 80% | 0.775 | 0.152 |
| xgboost | 90% | 0.882 | 0.154 |
| rule_baseline | 70% | 0.657 | 0.092 |
| rule_baseline | 80% | 0.787 | 0.125 |
| rule_baseline | 90% | 0.905 | 0.146 |
| scorecard_baseline | 70% | 0.671 | 0.082 |
| scorecard_baseline | 80% | 0.787 | 0.114 |
| scorecard_baseline | 90% | 0.925 | 0.156 |

## Inside each persona (out-of-fold AUC on train + validation)

If the models only recognised which persona a vendor belongs to, these numbers would sit near 0.5. Overall out-of-fold AUC: logistic 0.703, random forest 0.702, xgboost 0.689.

| persona | applications | default_rate | logistic | random_forest | xgboost |
|---|---|---|---|---|---|
| growing | 344 | 0.073 | 0.517 | 0.534 | 0.567 |
| new | 129 | 0.163 | 0.441 | 0.459 | 0.489 |
| seasonal | 384 | 0.188 | 0.609 | 0.594 | 0.566 |
| stable | 591 | 0.076 | 0.523 | 0.528 | 0.527 |
| struggling | 449 | 0.361 | 0.515 | 0.515 | 0.489 |

## What the models use

XGBoost importance (gain, top 12):

- near_zero_day_share_90: 0.096
- near_zero_day_share_60: 0.065
- debt_service_ratio_90: 0.060
- income_total_90: 0.042
- income_total_60: 0.030
- near_zero_day_share_30: 0.030
- income_count_30: 0.020
- fuliza_draws_30: 0.019
- withdraw_share_of_income_60: 0.019
- balance_cv_90: 0.019
- balance_min_eod_90: 0.019
- median_ticket_60: 0.019

Logistic regression coefficients (inputs are rank-normalised, so sizes are comparable; positive = higher risk):

- withdraw_share_of_income_30: +0.12
- days_since_last_fuliza_draw: -0.11
- near_zero_day_share_60: +0.10
- income_active_day_share_30: -0.08
- weekly_income_cv_90: +0.07
- essential_outflow_share_90: -0.07
- withdraw_share_of_income_60: -0.06
- balance_cv_90: +0.06
- net_cash_flow_ratio_90: +0.06
- amount_to_income_30: -0.05
- balance_min_eod_90: -0.05
- income_active_day_share_90: -0.05

Next: SHAP explanations, fairness check by gender, and the affordability simulation.
