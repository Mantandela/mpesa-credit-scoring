# Model report

Seed 42. Split by vendor, balanced by persona. 52 features. Labels are simulated (see assumptions.md), so these numbers describe how well the models recover the synthetic outcome, not performance on real borrowers.

## Split

| split | vendors | applications | defaults | default_rate |
|---|---|---|---|---|
| train | 700 | 1561 | 275 | 0.176 |
| val | 151 | 336 | 49 | 0.146 |
| test | 149 | 347 | 61 | 0.176 |

## Tuning (train vendors only, 5-fold CV grouped by vendor)

| model | best_settings | cv_auc_mean | cv_auc_sd |
|---|---|---|---|
| logistic | {'C': 0.01} | 0.702 | 0.034 |
| random_forest | {'min_samples_leaf': 10} | 0.694 | 0.033 |
| xgboost | {'max_depth': 2, 'n_estimators': 200} | 0.671 | 0.042 |

## Results

| model | val AUC | test AUC | test AUC 95% low | test AUC 95% high | test PR-AUC | test KS | test Brier |
|---|---|---|---|---|---|---|---|
| logistic | 0.711 | 0.753 | 0.684 | 0.815 | 0.393 | 0.427 | 0.128 |
| random_forest | 0.666 | 0.737 | 0.665 | 0.804 | 0.331 | 0.467 | 0.132 |
| xgboost | 0.635 | 0.728 | 0.653 | 0.798 | 0.346 | 0.443 | 0.132 |
| rule_baseline | 0.710 | 0.760 | 0.687 | 0.823 | 0.379 | 0.441 | nan |
| scorecard_baseline | 0.710 | 0.762 | 0.689 | 0.824 | 0.424 | 0.467 | nan |

Intervals come from resampling test vendors 1,000 times. `rule_baseline` ranks vendors by share of near-zero-balance days with no fitting. `scorecard_baseline` is the visible cash-flow scorecard (features and weights only, no hidden terms), also with no fitting. A model should beat both clearly to justify its complexity.

## Lender view: default rate among approved applicants (test)

The cutoff is set on the validation set so that the target share is approved, then applied to the test set. Default rate with no scoring on test: 17.6%.

| model | approval target | actual approval on test | default rate among approved |
|---|---|---|---|
| logistic | 70% | 0.657 | 0.088 |
| logistic | 80% | 0.769 | 0.109 |
| logistic | 90% | 0.905 | 0.146 |
| random_forest | 70% | 0.660 | 0.079 |
| random_forest | 80% | 0.787 | 0.128 |
| random_forest | 90% | 0.867 | 0.146 |
| xgboost | 70% | 0.628 | 0.078 |
| xgboost | 80% | 0.772 | 0.123 |
| xgboost | 90% | 0.862 | 0.140 |
| rule_baseline | 70% | 0.657 | 0.083 |
| rule_baseline | 80% | 0.787 | 0.117 |
| rule_baseline | 90% | 0.905 | 0.143 |
| scorecard_baseline | 70% | 0.692 | 0.083 |
| scorecard_baseline | 80% | 0.813 | 0.124 |
| scorecard_baseline | 90% | 0.925 | 0.150 |

## Inside each persona (out-of-fold AUC on train + validation)

If the models only recognised which persona a vendor belongs to, these numbers would sit near 0.5. Overall out-of-fold AUC: logistic 0.700, random forest 0.689, xgboost 0.683.

| persona | applications | default_rate | logistic | random_forest | xgboost |
|---|---|---|---|---|---|
| growing | 344 | 0.073 | 0.478 | 0.468 | 0.494 |
| new | 129 | 0.186 | 0.432 | 0.428 | 0.473 |
| seasonal | 384 | 0.180 | 0.628 | 0.580 | 0.578 |
| stable | 591 | 0.081 | 0.522 | 0.502 | 0.516 |
| struggling | 449 | 0.352 | 0.574 | 0.569 | 0.544 |

## What the models use

XGBoost importance (gain, top 12):

- near_zero_day_share_30: 0.162
- near_zero_day_share_60: 0.091
- near_zero_day_share_90: 0.051
- fuliza_funded_share_90: 0.035
- debt_service_ratio_90: 0.033
- income_total_90: 0.023
- fuliza_draws_30: 0.023
- income_count_90: 0.022
- balance_cv_90: 0.022
- unique_senders_30: 0.020
- income_active_day_share_90: 0.018
- unique_senders_60: 0.018

Logistic regression coefficients (inputs are rank-normalised, so sizes are comparable; positive = higher risk):

- withdraw_share_of_income_30: +0.12
- withdraw_share_of_income_60: -0.11
- essential_outflow_share_90: -0.09
- days_since_last_fuliza_draw: -0.09
- near_zero_day_share_60: +0.09
- balance_cv_90: +0.09
- weekly_income_cv_90: +0.08
- amount_to_income_30: -0.06
- income_active_day_share_30: -0.06
- fuliza_repay_lag_median_days_90 (missing flag): +0.06
- withdraw_share_of_income_90: +0.06
- till_share_90: -0.06

Next: SHAP explanations, fairness check by gender, and the affordability simulation.
