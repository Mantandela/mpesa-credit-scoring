# Model report

Seed 42. Split by vendor, balanced by persona. 52 features. Labels are simulated (see assumptions.md), so these numbers describe how well the models recover the synthetic outcome, not performance on real borrowers.

## Split

| split | vendors | applications | defaults | default_rate |
|---|---|---|---|---|
| train | 700 | 1561 | 275 | 0.176 |
| val | 151 | 336 | 48 | 0.143 |
| test | 149 | 347 | 64 | 0.184 |

## Tuning (train vendors only, 5-fold CV grouped by vendor)

| model | best_settings | cv_auc_mean | cv_auc_sd |
|---|---|---|---|
| logistic | {'C': 0.01} | 0.708 | 0.029 |
| random_forest | {'min_samples_leaf': 10} | 0.716 | 0.035 |
| xgboost | {'max_depth': 2, 'n_estimators': 200} | 0.703 | 0.034 |

## Results

| model | val AUC | test AUC | test AUC 95% low | test AUC 95% high | test PR-AUC | test KS | test Brier |
|---|---|---|---|---|---|---|---|
| logistic | 0.725 | 0.759 | 0.686 | 0.825 | 0.403 | 0.455 | 0.131 |
| random_forest | 0.695 | 0.732 | 0.658 | 0.798 | 0.340 | 0.492 | 0.137 |
| xgboost | 0.664 | 0.713 | 0.632 | 0.787 | 0.369 | 0.412 | 0.136 |
| rule_baseline | 0.728 | 0.772 | 0.699 | 0.835 | 0.410 | 0.441 | nan |
| scorecard_baseline | 0.731 | 0.770 | 0.696 | 0.836 | 0.440 | 0.483 | nan |

Intervals come from resampling test vendors 1,000 times. `rule_baseline` ranks vendors by share of near-zero-balance days with no fitting. `scorecard_baseline` is the visible cash-flow scorecard (features and weights only, no hidden terms), also with no fitting. A model should beat both clearly to justify its complexity.

## Lender view: default rate among approved applicants (test)

The cutoff is set on the validation set so that the target share is approved, then applied to the test set. Default rate with no scoring on test: 18.4%.

| model | approval target | actual approval on test | default rate among approved |
|---|---|---|---|
| logistic | 70% | 0.646 | 0.080 |
| logistic | 80% | 0.758 | 0.110 |
| logistic | 90% | 0.888 | 0.149 |
| random_forest | 70% | 0.663 | 0.078 |
| random_forest | 80% | 0.778 | 0.133 |
| random_forest | 90% | 0.885 | 0.160 |
| xgboost | 70% | 0.651 | 0.093 |
| xgboost | 80% | 0.772 | 0.134 |
| xgboost | 90% | 0.865 | 0.147 |
| rule_baseline | 70% | 0.657 | 0.088 |
| rule_baseline | 80% | 0.787 | 0.125 |
| rule_baseline | 90% | 0.905 | 0.146 |
| scorecard_baseline | 70% | 0.671 | 0.077 |
| scorecard_baseline | 80% | 0.787 | 0.114 |
| scorecard_baseline | 90% | 0.925 | 0.156 |

## Inside each persona (out-of-fold AUC on train + validation)

If the models only recognised which persona a vendor belongs to, these numbers would sit near 0.5. Overall out-of-fold AUC: logistic 0.710, random forest 0.708, xgboost 0.700.

| persona | applications | default_rate | logistic | random_forest | xgboost |
|---|---|---|---|---|---|
| growing | 344 | 0.070 | 0.455 | 0.513 | 0.542 |
| new | 129 | 0.171 | 0.434 | 0.531 | 0.560 |
| seasonal | 384 | 0.185 | 0.630 | 0.608 | 0.576 |
| stable | 591 | 0.078 | 0.539 | 0.506 | 0.524 |
| struggling | 449 | 0.356 | 0.584 | 0.579 | 0.555 |

## What the models use

XGBoost importance (gain, top 12):

- near_zero_day_share_30: 0.102
- near_zero_day_share_90: 0.094
- near_zero_day_share_60: 0.074
- debt_service_ratio_90: 0.048
- fuliza_funded_share_90: 0.033
- fuliza_draws_60: 0.027
- income_total_90: 0.025
- balance_cv_90: 0.024
- median_ticket_90: 0.022
- fuliza_draws_30: 0.021
- income_count_90: 0.018
- balance_median_eod_90: 0.017

Logistic regression coefficients (inputs are rank-normalised, so sizes are comparable; positive = higher risk):

- withdraw_share_of_income_30: +0.13
- balance_cv_90: +0.12
- withdraw_share_of_income_60: -0.10
- days_since_last_fuliza_draw: -0.09
- weekly_income_cv_90: +0.09
- near_zero_day_share_60: +0.08
- essential_outflow_share_90: -0.07
- fuliza_repay_lag_median_days_90 (missing flag): +0.07
- amount_to_income_30: -0.07
- withdraw_share_of_income_90: +0.06
- income_active_day_share_30: -0.06
- balance_min_eod_90: -0.06

Next: SHAP explanations, fairness check by gender, and the affordability simulation.
