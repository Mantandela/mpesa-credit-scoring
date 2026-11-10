# Feature report

710 applications, 46 features, default rate 16.8%

Leakage test: PASS, no feature changed when later transactions were deleted

## Missing values (share of applications)

| feature | missing |
|---|---|
| fuliza_repay_lag_median_days_90 | 50.4% |
| income_trend_30_vs_prior | 4.8% |

## Single-feature signal (AUC against `defaulted`; 0.5 = none, above 0.5 = higher value, more default)

| feature | AUC |
|---|---|
| income_count_60 | 0.300 |
| till_share_90 | 0.302 |
| income_count_30 | 0.302 |
| income_total_30 | 0.303 |
| income_count_90 | 0.303 |
| balance_median_eod_90 | 0.304 |
| income_total_60 | 0.305 |
| near_zero_day_share_90 | 0.694 |
| income_total_90 | 0.308 |
| fee_share_of_income_90 | 0.691 |
| unique_senders_30 | 0.309 |
| near_zero_day_share_60 | 0.688 |
| unique_senders_60 | 0.314 |
| weekly_income_cv_90 | 0.680 |
| unique_senders_90 | 0.323 |

Strongest single feature: income_count_60, strength 0.700 (an AUC of 0.300 means the same as 0.700 read the other way round). Strengths above about 0.85 would suggest the label leaks into the features and should be investigated.
