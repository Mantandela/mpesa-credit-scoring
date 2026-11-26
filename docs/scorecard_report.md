# Scorecard and outcome report

2,261 applications, 1000 vendors. Weight set `author`, shock coefficient 0.5, scale 1.2, hidden risk coefficient 0.5. All outcomes are simulated.

## Outcome shares

| outcome | share |
|---|---|
| defaulted (class 2) | 18.2% |
| late, not defaulted (class 1) | 10.3% |
| on time (class 0) | 71.6% |

Applications with at least one Fuliza draw in the counting window: 57.3%. Applications with a complete 90-day window: 100.0%.

## By persona

| persona | applications | default | late | on time | mean p |
|---|---|---|---|---|---|
| growing | 365 | 8.8% | 18.1% | 73.2% | 0.079 |
| new | 167 | 18.6% | 19.2% | 62.3% | 0.156 |
| seasonal | 465 | 15.3% | 15.5% | 69.2% | 0.160 |
| stable | 717 | 7.7% | 4.5% | 87.9% | 0.055 |
| struggling | 547 | 40.6% | 5.5% | 53.9% | 0.378 |

## How predictable is default?

- Best possible AUC (the scorecard probability itself): 0.773
- Persona only: 0.721
- Inside a persona (average): 0.673
- Visible score only (features, no hidden terms) against default: 0.743

For scale: published cash-flow-only models reached AUCs of about 0.53 to 0.73 (CRA for FinRegLab, 2019).

## Do default and Fuliza lateness move together?

- Late share among defaulters: 11.9%
- Late share among non-defaulters: 12.5%
- AUC of `fuliza_late` as a predictor of default: 0.497

## Pillar scores against default (AUC, above 0.5 = higher score, more default)

- A_income_stability: 0.729
- B_cash_flow_buffer: 0.709
- C_borrowing_distress: 0.719
- D_affordability: 0.665
- E_obligations: 0.683
- F_history_growth: 0.613
- G_network: 0.699

## Single features with the strongest signal against default

- income_total_60: 0.261
- income_total_30: 0.262
- income_total_90: 0.263
- fee_share_of_income_90: 0.736
- balance_median_eod_90: 0.269
- amount_to_avg_monthly_income_90: 0.730
- amount_to_income_30: 0.727
- debt_service_ratio_90: 0.725
- income_count_60: 0.276
- income_count_30: 0.277

Single-feature AUCs above about 0.85 would suggest the label leaks into the features.

## Directions that disagree with the raw association

Directions were fixed from lending logic before any results (docs/scorecard_mapping.md) and are not tuned to the data. A disagreement means the feature's raw link to default is opposite to its assumed direction, usually because of persona structure in the simulated statements. It is a limitation to report, not something to fix by changing the direction.

- net_cash_flow_ratio_90 (B, set to -1, raw AUC 0.513)
- reversal_count_90 (C, set to +1, raw AUC 0.499)
- essential_outflow_share_90 (E, set to -1, raw AUC 0.637)

## Limitations

Features left out of the scorecard because lending logic does not support a direction (they remain model inputs; docs/scorecard_mapping.md): cash_deposit_share_90 (raw AUC 0.571), withdraw_share_of_income_90 (raw AUC 0.612).

Remaining features whose raw association disagrees with their preset direction (kept; directions are never tuned):

- net_cash_flow_ratio_90 (B, set to -1, raw AUC 0.513): a limitation of the simulated statements, reported as is
- reversal_count_90 (C, set to +1, raw AUC 0.499): a limitation of the simulated statements, reported as is
- essential_outflow_share_90 (E, set to -1, raw AUC 0.637): a limitation of the simulated statements, reported as is

Features expected to carry little or no signal in the simulation (where the raw AUC is near 0.5, the side of 0.5 it falls on is noise; listed whether or not they agree with the direction in this run):

- requested_term_days (set to +1, raw AUC 0.502, agrees in this run): no signal by design: the term is drawn at random, never from risk
- failed_payment_share_90 (set to +1, raw AUC 0.582, agrees in this run): most failures are the random 1% added to test the cleaning step, but a payment that a short wallet cannot cover and Fuliza does not fund can also fail, so it can carry some signal through tight cash
- All outcomes are simulated and the test set is small, so intervals are wide ([calibration_report.md](calibration_report.md#limits)).

Note on the AUCs in "How predictable is default?": they are computed on all 2,261 applications. The best possible
AUC (0.773) is the full scorecard probability **including** its hidden terms; the visible score (0.743 here) is the
scorecard without them. The visible scorecard's AUC on the **test vendors** only is the `scorecard_baseline` row of
[model_report.md](model_report.md#results). `fuliza_late` is an outcome recorded after the application, never a
model input.

## See also

- [Project README](../README.md)
- [Scorecard mapping](scorecard_mapping.md)
- [Model report](model_report.md)
- [Personas](personas.md)
