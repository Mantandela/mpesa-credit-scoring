# Sensitivity report: scorecard weights and hidden shock

2244 applications, 1000 vendors, 52 features, seed 42. Each variant redraws `defaulted` from a different scorecard (weights or shock size) for the same applications and retrains the models. All outcomes are simulated, so these numbers show how well the models recover simulated labels, not performance on real borrowers.

Published cash-flow-only models reached AUCs of about 0.53 to 0.73 (CRA for FinRegLab, 2019), a useful reference for how predictable real defaults are.

## 1. How predictable is default in each variant?

Best possible AUC is the scorecard probability itself. Persona only is the AUC from knowing just the vendor's persona. Inside a persona is the best possible AUC among vendors of the same persona.

| variant | default rate | late share | best possible AUC | persona only | inside a persona |
|---|---|---|---|---|---|
| author, shock 0.5 | 0.172 | 0.066 | 0.760 | 0.714 | 0.639 |
| equal, shock 0.5 | 0.172 | 0.066 | 0.757 | 0.707 | 0.644 |
| cashflow_heavy, shock 0.5 | 0.173 | 0.066 | 0.776 | 0.731 | 0.646 |
| fico_like, shock 0.5 | 0.175 | 0.066 | 0.740 | 0.688 | 0.643 |
| author, shock 0.25 | 0.179 | 0.066 | 0.758 | 0.729 | 0.590 |
| author, shock 0.9 | 0.172 | 0.065 | 0.799 | 0.714 | 0.734 |

## 2. Test AUC with 95% interval (vendors never seen in training)

| variant | test defaults | logistic | random_forest | xgboost | scorecard_baseline | rule_baseline |
|---|---|---|---|---|---|---|
| author, shock 0.5 | 64 of 347 | 0.759 (0.69 to 0.82) | 0.732 (0.66 to 0.80) | 0.713 (0.63 to 0.79) | 0.770 (0.70 to 0.84) | 0.772 (0.70 to 0.83) |
| equal, shock 0.5 | 61 of 347 | 0.753 (0.68 to 0.81) | 0.737 (0.66 to 0.80) | 0.728 (0.65 to 0.80) | 0.762 (0.69 to 0.82) | 0.760 (0.69 to 0.82) |
| cashflow_heavy, shock 0.5 | 65 of 347 | 0.778 (0.71 to 0.84) | 0.751 (0.68 to 0.81) | 0.724 (0.65 to 0.79) | 0.784 (0.71 to 0.84) | 0.786 (0.72 to 0.84) |
| fico_like, shock 0.5 | 62 of 347 | 0.733 (0.66 to 0.80) | 0.727 (0.65 to 0.79) | 0.716 (0.63 to 0.79) | 0.746 (0.67 to 0.81) | 0.746 (0.68 to 0.81) |
| author, shock 0.25 | 67 of 347 | 0.768 (0.70 to 0.83) | 0.753 (0.68 to 0.81) | 0.722 (0.64 to 0.79) | 0.773 (0.70 to 0.83) | 0.771 (0.70 to 0.83) |
| author, shock 0.9 | 62 of 347 | 0.751 (0.68 to 0.82) | 0.716 (0.65 to 0.79) | 0.703 (0.63 to 0.77) | 0.756 (0.68 to 0.83) | 0.759 (0.69 to 0.83) |

`scorecard_baseline` is the visible scorecard (features and weights, no fitting). `rule_baseline` ranks only by near-zero-balance days.

## 3. Cross-validated AUC (train and validation vendors, grouped by vendor)

More applications than the test set, so less noisy. This is the main comparison between models.

| variant | logistic | random_forest | xgboost |
|---|---|---|---|
| author, shock 0.5 | 0.710 | 0.708 | 0.700 |
| equal, shock 0.5 | 0.700 | 0.689 | 0.683 |
| cashflow_heavy, shock 0.5 | 0.734 | 0.725 | 0.721 |
| fico_like, shock 0.5 | 0.686 | 0.673 | 0.663 |
| author, shock 0.25 | 0.732 | 0.715 | 0.708 |
| author, shock 0.9 | 0.703 | 0.702 | 0.689 |

## 4. Share of the achievable gain captured

(Cross-validated AUC - 0.5) divided by (best possible AUC - 0.5). 100% means the model matches the scorecard probability.

| variant | logistic | random_forest | xgboost |
|---|---|---|---|
| author, shock 0.5 | 81% | 80% | 77% |
| equal, shock 0.5 | 78% | 74% | 71% |
| cashflow_heavy, shock 0.5 | 85% | 82% | 80% |
| fico_like, shock 0.5 | 77% | 72% | 68% |
| author, shock 0.25 | 90% | 83% | 80% |
| author, shock 0.9 | 68% | 68% | 63% |

## 5. Lender view: default rate among approved applicants when 80% are approved (test)

| variant | no scoring | logistic | random_forest | xgboost | scorecard_baseline | rule_baseline |
|---|---|---|---|---|---|---|
| author, shock 0.5 | 0.184 | 0.110 | 0.133 | 0.134 | 0.114 | 0.125 |
| equal, shock 0.5 | 0.176 | 0.109 | 0.128 | 0.123 | 0.124 | 0.117 |
| cashflow_heavy, shock 0.5 | 0.187 | 0.104 | 0.137 | 0.139 | 0.117 | 0.121 |
| fico_like, shock 0.5 | 0.179 | 0.124 | 0.126 | 0.122 | 0.118 | 0.125 |
| author, shock 0.25 | 0.193 | 0.108 | 0.137 | 0.144 | 0.114 | 0.125 |
| author, shock 0.9 | 0.179 | 0.118 | 0.143 | 0.152 | 0.114 | 0.125 |

Per-variant detail is in docs/model_report_v<number>.md (numbers follow the order of the tables).
