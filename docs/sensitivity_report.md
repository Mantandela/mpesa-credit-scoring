# Sensitivity report: scorecard weights and hidden shock

2261 applications, 1000 vendors, 52 features, seed 42. Each variant redraws `defaulted` from a different scorecard (weights or shock size) for the same applications and retrains the models. All outcomes are simulated, so these numbers show how well the models recover simulated labels, not performance on real borrowers.

Published cash-flow-only models reached AUCs of about 0.53 to 0.73 (CRA for FinRegLab, 2019), a useful reference for how predictable real defaults are.

## 1. How predictable is default in each variant?

Best possible AUC is the scorecard probability itself. Persona only is the AUC from knowing just the vendor's persona. Inside a persona is the best possible AUC among vendors of the same persona.

| variant | default rate | late share | best possible AUC | persona only | inside a persona |
|---|---|---|---|---|---|
| author, shock 0.5 | 0.182 | 0.103 | 0.773 | 0.721 | 0.673 |
| equal, shock 0.5 | 0.184 | 0.103 | 0.770 | 0.721 | 0.654 |
| cashflow_heavy, shock 0.5 | 0.183 | 0.103 | 0.776 | 0.724 | 0.674 |
| fico_like, shock 0.5 | 0.184 | 0.103 | 0.761 | 0.707 | 0.664 |
| author, shock 0.25 | 0.183 | 0.104 | 0.772 | 0.736 | 0.634 |
| author, shock 0.9 | 0.180 | 0.102 | 0.797 | 0.707 | 0.733 |

## 2. Test AUC with 95% interval (vendors never seen in training)

| variant | test defaults | logistic | random_forest | xgboost | scorecard_baseline | rule_baseline |
|---|---|---|---|---|---|---|
| author, shock 0.5 | 62 of 350 | 0.726 (0.64 to 0.81) | 0.757 (0.69 to 0.82) | 0.753 (0.68 to 0.83) | 0.747 (0.67 to 0.82) | 0.746 (0.67 to 0.82) |
| equal, shock 0.5 | 64 of 350 | 0.726 (0.65 to 0.81) | 0.757 (0.69 to 0.82) | 0.752 (0.68 to 0.82) | 0.749 (0.68 to 0.82) | 0.745 (0.67 to 0.82) |
| cashflow_heavy, shock 0.5 | 60 of 350 | 0.742 (0.67 to 0.82) | 0.776 (0.71 to 0.84) | 0.763 (0.69 to 0.83) | 0.767 (0.70 to 0.83) | 0.766 (0.69 to 0.83) |
| fico_like, shock 0.5 | 63 of 350 | 0.712 (0.63 to 0.79) | 0.749 (0.68 to 0.82) | 0.737 (0.66 to 0.81) | 0.734 (0.66 to 0.81) | 0.735 (0.66 to 0.81) |
| author, shock 0.25 | 63 of 350 | 0.783 (0.72 to 0.85) | 0.798 (0.73 to 0.86) | 0.779 (0.71 to 0.85) | 0.804 (0.74 to 0.86) | 0.800 (0.73 to 0.86) |
| author, shock 0.9 | 65 of 350 | 0.730 (0.65 to 0.81) | 0.770 (0.70 to 0.83) | 0.743 (0.67 to 0.81) | 0.757 (0.68 to 0.83) | 0.760 (0.69 to 0.83) |

`scorecard_baseline` is the visible scorecard (features and weights, no fitting). `rule_baseline` ranks only by near-zero-balance days.

## 3. Cross-validated AUC (train and validation vendors, grouped by vendor)

More applications than the test set, so less noisy. This is the main comparison between models.

| variant | logistic | random_forest | xgboost |
|---|---|---|---|
| author, shock 0.5 | 0.733 | 0.742 | 0.734 |
| equal, shock 0.5 | 0.730 | 0.743 | 0.740 |
| cashflow_heavy, shock 0.5 | 0.741 | 0.756 | 0.749 |
| fico_like, shock 0.5 | 0.723 | 0.735 | 0.730 |
| author, shock 0.25 | 0.744 | 0.746 | 0.734 |
| author, shock 0.9 | 0.717 | 0.715 | 0.707 |

## 4. Share of the achievable gain captured

(Cross-validated AUC - 0.5) divided by (best possible AUC - 0.5). 100% means the model matches the scorecard probability.

| variant | logistic | random_forest | xgboost |
|---|---|---|---|
| author, shock 0.5 | 85% | 89% | 86% |
| equal, shock 0.5 | 85% | 90% | 89% |
| cashflow_heavy, shock 0.5 | 87% | 93% | 90% |
| fico_like, shock 0.5 | 85% | 90% | 88% |
| author, shock 0.25 | 90% | 90% | 86% |
| author, shock 0.9 | 73% | 72% | 70% |

## 5. Lender view: default rate among approved applicants when 80% are approved (test)

| variant | no scoring | logistic | random_forest | xgboost | scorecard_baseline | rule_baseline |
|---|---|---|---|---|---|---|
| author, shock 0.5 | 0.177 | 0.112 | 0.106 | 0.101 | 0.114 | 0.113 |
| equal, shock 0.5 | 0.183 | 0.112 | 0.110 | 0.115 | 0.120 | 0.116 |
| cashflow_heavy, shock 0.5 | 0.171 | 0.107 | 0.108 | 0.108 | 0.111 | 0.105 |
| fico_like, shock 0.5 | 0.180 | 0.117 | 0.115 | 0.112 | 0.121 | 0.116 |
| author, shock 0.25 | 0.180 | 0.101 | 0.098 | 0.100 | 0.103 | 0.098 |
| author, shock 0.9 | 0.186 | 0.113 | 0.110 | 0.119 | 0.121 | 0.120 |

Per-variant detail is in docs/model_report_v<number>.md (numbers follow the order of the tables).

## Limits

- Every variant uses simulated outcomes, so the table shows how robust the comparison is to the simulation's own
  settings, not how the models would do on real data.
- Each test set holds about 60 defaults, so the test intervals are wide and overlap; the cross-validated table is the
  steadier comparison. See [calibration_report.md](calibration_report.md#limits).

## See also

- [Project README](../README.md)
- [Model report](model_report.md)
- [Scorecard report](scorecard_report.md)
- [Scorecard mapping](scorecard_mapping.md)
