# Three-class model report (secondary target)

Classes: 0 on time, 1 late (a Fuliza draw unpaid past 30 days, not defaulted), 2 default (from the scorecard). Seed 42, 52 features, split by vendor. Outcomes are simulated, so these numbers describe recovery of the simulated labels.

## Class counts

| split | applications | on time | late | default |
|---|---|---|---|---|
| train | 1561 | 1181 | 105 | 275 |
| test | 347 | 257 | 26 | 64 |

## Results on test vendors

| model | macro AUC | accuracy | balanced accuracy | macro F1 |
|---|---|---|---|---|
| majority class | 0.500 | 0.741 | 0.333 | 0.284 |
| logistic | 0.689 | 0.738 | 0.363 | 0.348 |
| random_forest | 0.689 | 0.726 | 0.342 | 0.314 |
| xgboost | 0.670 | 0.735 | 0.366 | 0.352 |

Macro AUC is the average of the one-vs-rest AUCs. The late class is small, so its figures are noisy.

## Per class

| model | AUC on time | AUC late | AUC default | recall on time | recall late | recall default |
|---|---|---|---|---|---|---|
| logistic | 0.733 | 0.606 | 0.728 | 0.965 | 0.000 | 0.125 |
| random_forest | 0.716 | 0.626 | 0.726 | 0.965 | 0.000 | 0.062 |
| xgboost | 0.679 | 0.639 | 0.691 | 0.957 | 0.000 | 0.141 |

### Confusion matrix, logistic (rows actual, columns predicted)

| actual \ predicted | on time | late | default |
|---|---|---|---|
| on time | 248 | 1 | 8 |
| late | 25 | 0 | 1 |
| default | 56 | 0 | 8 |

### Confusion matrix, random_forest (rows actual, columns predicted)

| actual \ predicted | on time | late | default |
|---|---|---|---|
| on time | 248 | 0 | 9 |
| late | 26 | 0 | 0 |
| default | 60 | 0 | 4 |

### Confusion matrix, xgboost (rows actual, columns predicted)

| actual \ predicted | on time | late | default |
|---|---|---|---|
| on time | 246 | 0 | 11 |
| late | 26 | 0 | 0 |
| default | 55 | 0 | 9 |

