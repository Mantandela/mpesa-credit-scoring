# Model report

Seed 42. Split by vendor, balanced by persona. 52 features. Labels are simulated (see assumptions.md), so these numbers describe how well the models recover the synthetic outcome, not performance on real borrowers.

## Split

| split | vendors | applications | defaults | default_rate |
|---|---|---|---|---|
| train | 700 | 1579 | 292 | 0.185 |
| val | 149 | 332 | 58 | 0.175 |
| test | 151 | 350 | 63 | 0.180 |

## Tuning (train vendors only, 5-fold CV grouped by vendor)

| model | best_settings | cv_auc_mean | cv_auc_sd |
|---|---|---|---|
| logistic | {'C': 0.01} | 0.735 | 0.049 |
| random_forest | {'min_samples_leaf': 10} | 0.745 | 0.046 |
| xgboost | {'max_depth': 2, 'n_estimators': 200} | 0.738 | 0.033 |

## Results

| model | val AUC | test AUC | test AUC 95% low | test AUC 95% high | test PR-AUC | test KS | test Brier |
|---|---|---|---|---|---|---|---|
| logistic | 0.812 | 0.783 | 0.717 | 0.853 | 0.465 | 0.489 | 0.120 |
| random_forest | 0.790 | 0.798 | 0.732 | 0.862 | 0.543 | 0.520 | 0.116 |
| xgboost | 0.788 | 0.779 | 0.708 | 0.850 | 0.507 | 0.509 | 0.120 |
| rule_baseline | 0.792 | 0.800 | 0.733 | 0.862 | 0.511 | 0.501 | nan |
| scorecard_baseline | 0.810 | 0.804 | 0.740 | 0.864 | 0.502 | 0.513 | nan |

Intervals come from resampling test vendors 1,000 times. `rule_baseline` ranks vendors by share of near-zero-balance days with no fitting. `scorecard_baseline` is the visible cash-flow scorecard (features and weights only, no hidden terms), also with no fitting. A model should beat both clearly to justify its complexity.

## Lender view: default rate among approved applicants (test)

The cutoff is set on the validation set so that the target share is approved, then applied to the test set. Default rate with no scoring on test: 18.0%.

| model | approval target | actual approval on test | default rate among approved |
|---|---|---|---|
| logistic | 70% | 0.671 | 0.077 |
| logistic | 80% | 0.763 | 0.101 |
| logistic | 90% | 0.851 | 0.117 |
| random_forest | 70% | 0.646 | 0.062 |
| random_forest | 80% | 0.754 | 0.098 |
| random_forest | 90% | 0.851 | 0.128 |
| xgboost | 70% | 0.683 | 0.088 |
| xgboost | 80% | 0.746 | 0.100 |
| xgboost | 90% | 0.846 | 0.118 |
| rule_baseline | 70% | 0.691 | 0.087 |
| rule_baseline | 80% | 0.786 | 0.098 |
| rule_baseline | 90% | 0.883 | 0.126 |
| scorecard_baseline | 70% | 0.660 | 0.069 |
| scorecard_baseline | 80% | 0.780 | 0.103 |
| scorecard_baseline | 90% | 0.863 | 0.123 |

## Inside each persona (out-of-fold AUC on train + validation)

If the models only recognised which persona a vendor belongs to, these numbers would sit near 0.5. Overall out-of-fold AUC: logistic 0.744, random forest 0.746, xgboost 0.734.

| persona | applications | default_rate | logistic | random_forest | xgboost |
|---|---|---|---|---|---|
| growing | 309 | 0.084 | 0.542 | 0.590 | 0.610 |
| new | 142 | 0.232 | 0.579 | 0.632 | 0.546 |
| seasonal | 400 | 0.158 | 0.593 | 0.547 | 0.544 |
| stable | 599 | 0.065 | 0.527 | 0.538 | 0.533 |
| struggling | 461 | 0.410 | 0.617 | 0.622 | 0.579 |

## What the models use

XGBoost importance (gain, top 12):

- amount_to_avg_monthly_income_90: 0.094
- fuliza_funded_share_90: 0.083
- income_total_30: 0.078
- debt_service_ratio_90: 0.048
- near_zero_day_share_60: 0.030
- till_share_90: 0.029
- balance_median_eod_90: 0.026
- fuliza_draws_90: 0.024
- fee_share_of_income_90: 0.021
- income_total_60: 0.020
- income_total_90: 0.019
- balance_min_eod_90: 0.018

Logistic regression coefficients (inputs are rank-normalised, so sizes are comparable; positive = higher risk):

- weekly_income_cv_90: +0.12
- withdraw_share_of_income_60: +0.10
- fuliza_repay_lag_median_days_90: +0.10
- balance_median_eod_90: -0.09
- income_active_day_share_30: +0.08
- net_cash_flow_ratio_90: -0.08
- till_share_90: -0.07
- fuliza_draws_90: +0.07
- fuliza_repay_lag_median_days_90 (missing flag): +0.07
- supplier_spend_share_90: -0.06
- balance_cv_90: +0.06
- median_ticket_60: -0.06

Next: SHAP explanations, fairness check by gender, and the affordability simulation.
