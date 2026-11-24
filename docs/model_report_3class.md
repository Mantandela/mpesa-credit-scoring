# Three-class model report (secondary target)

Classes: 0 on time, 1 late (a Fuliza draw unpaid past 30 days, not defaulted), 2 default (from the scorecard). Seed 42, 52 features, split by vendor. Outcomes are simulated, so these numbers describe recovery of the simulated labels.

## Class counts

| split | applications | on time | late | default |
|---|---|---|---|---|
| train | 1579 | 1142 | 150 | 287 |
| test | 350 | 247 | 41 | 62 |

## Results on test vendors

| model | macro AUC | accuracy | balanced accuracy | macro F1 |
|---|---|---|---|---|
| majority class | 0.500 | 0.706 | 0.333 | 0.276 |
| logistic | 0.690 | 0.717 | 0.403 | 0.394 |
| random_forest | 0.710 | 0.726 | 0.395 | 0.385 |
| xgboost | 0.700 | 0.720 | 0.423 | 0.424 |

Macro AUC is the average of the one-vs-rest AUCs. The late class is small, so its figures are noisy.

## Per class

| model | AUC on time | AUC late | AUC default | recall on time | recall late | recall default |
|---|---|---|---|---|---|---|
| logistic | 0.638 | 0.718 | 0.715 | 0.951 | 0.000 | 0.258 |
| random_forest | 0.648 | 0.717 | 0.764 | 0.976 | 0.000 | 0.210 |
| xgboost | 0.635 | 0.715 | 0.750 | 0.939 | 0.024 | 0.306 |

### Confusion matrix, logistic (rows actual, columns predicted)

| actual \ predicted | on time | late | default |
|---|---|---|---|
| on time | 235 | 0 | 12 |
| late | 41 | 0 | 0 |
| default | 46 | 0 | 16 |

### Confusion matrix, random_forest (rows actual, columns predicted)

| actual \ predicted | on time | late | default |
|---|---|---|---|
| on time | 241 | 0 | 6 |
| late | 41 | 0 | 0 |
| default | 49 | 0 | 13 |

### Confusion matrix, xgboost (rows actual, columns predicted)

| actual \ predicted | on time | late | default |
|---|---|---|---|
| on time | 232 | 1 | 14 |
| late | 40 | 1 | 0 |
| default | 43 | 0 | 19 |

