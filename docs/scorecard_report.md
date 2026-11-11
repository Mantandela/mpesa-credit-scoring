# Scorecard and outcome report

2,244 applications, 1000 vendors. Weight set `author`, shock coefficient 0.5, scale 1.2, hidden risk coefficient 0.5. All outcomes are simulated.

## Outcome shares

| outcome | share |
|---|---|
| defaulted (class 2) | 17.2% |
| late, not defaulted (class 1) | 6.6% |
| on time (class 0) | 76.1% |

Applications with at least one Fuliza draw in the counting window: 48.6%. Applications with a complete 90-day window: 100.0%.

## By persona

| persona | applications | default | late | on time | mean p |
|---|---|---|---|---|---|
| growing | 406 | 7.1% | 5.7% | 87.2% | 0.078 |
| new | 152 | 16.4% | 12.5% | 71.1% | 0.154 |
| seasonal | 455 | 18.5% | 7.9% | 73.6% | 0.167 |
| stable | 701 | 7.4% | 4.1% | 88.4% | 0.056 |
| struggling | 530 | 37.2% | 7.9% | 54.9% | 0.381 |

## How predictable is default?

- Best possible AUC (the scorecard probability itself): 0.760
- Persona only: 0.714
- Inside a persona (average): 0.639
- Visible score only (features, no hidden terms) against default: 0.728

For scale: published cash-flow-only models reached AUCs of about 0.53 to 0.73 (CRA for FinRegLab, 2019).

## Do default and Fuliza lateness move together?

- Late share among defaulters: 14.5%
- Late share among non-defaulters: 8.0%
- AUC of `fuliza_late` as a predictor of default: 0.532

## Pillar scores against default (AUC, above 0.5 = higher score, more default)

- A_income_stability: 0.707
- B_cash_flow_buffer: 0.725
- C_borrowing_distress: 0.706
- D_affordability: 0.624
- E_obligations: 0.476
- F_history_growth: 0.621
- G_network: 0.700

## Single features with the strongest signal against default

- near_zero_day_share_60: 0.730
- near_zero_day_share_90: 0.730
- balance_median_eod_90: 0.277
- near_zero_day_share_30: 0.715
- income_total_60: 0.286
- income_total_90: 0.287
- income_total_30: 0.287
- income_count_60: 0.292
- income_count_90: 0.292
- fuliza_funded_share_90: 0.708

Single-feature AUCs above about 0.85 would suggest the label leaks into the features.

## Directions that disagree with the raw association

Directions were fixed from lending logic before any results (docs/scorecard_mapping.md) and are not tuned to the data. A disagreement means the feature's raw link to default is opposite to its assumed direction, usually because of persona structure in the simulated statements. It is a limitation to report, not something to fix by changing the direction.

- withdraw_share_of_income_90 (B, set to +1, raw AUC 0.462)
- failed_payment_share_90 (C, set to +1, raw AUC 0.480)
- requested_term_days (D, set to +1, raw AUC 0.499)
- paybill_months_paid_90 (E, set to -1, raw AUC 0.529)
- supplier_spend_share_90 (E, set to -1, raw AUC 0.575)
- supplier_count_90 (E, set to -1, raw AUC 0.526)
- essential_outflow_share_90 (E, set to -1, raw AUC 0.528)
