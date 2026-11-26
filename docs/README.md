# Documentation index

Every document in `docs/`, one line each: what it is for and when to read it. **All data and outcomes in this project
are simulated.** Each number has one owner, and other documents link to it instead of repeating it:

| Topic | Owner |
| --- | --- |
| Score formula, tier bands, tier mix, estimated limit | [scoring_function.md](scoring_function.md) |
| Model AUCs and the train / validation / test split | [model_report.md](model_report.md) |
| Scorecard numbers (outcome shares, predictability, directions) | [scorecard_report.md](scorecard_report.md) |
| Calibration and confidence intervals | [calibration_report.md](calibration_report.md) |
| Database schema | [database.md](database.md) |

Some reports are written by scripts and are overwritten when the script runs again (marked *generated* below, with
the script). Their "See also" and "Limits" sections were added by hand and have to be added again after a rerun.

## Scoring and models

- [scoring_function.md](scoring_function.md): how one statement becomes a probability of default, a 300-850 score, a
  risk tier, reasons and an estimated limit. Read first to understand the score.
- [scorecard_mapping.md](scorecard_mapping.md): the cash-flow scorecard's pillars, features, directions and weights.
  Read to see what the simulated outcome is built from.
- [scorecard_report.md](scorecard_report.md): outcome shares and how predictable default is in the simulation.
  *Generated* by `src/scorecard.py`.
- [model_report.md](model_report.md): the models against the baselines on the test vendors. *Generated* by
  `src/train_models.py`.
- [model_report_3class.md](model_report_3class.md): the secondary three-class target (on time, late, default).
  *Generated* by `src/train_multiclass.py`.
- [sensitivity_report.md](sensitivity_report.md): the comparison repeated under other scorecard weights and shock
  sizes. *Generated* by `src/sensitivity.py`.
- [model_report_v0.md](model_report_v0.md) to [model_report_v5.md](model_report_v5.md): the per-variant model
  reports behind the sensitivity report (v0 is the main run). *Generated* by `src/sensitivity.py`. Read only for the
  detail of one variant.

## Data and database

- [data_dictionary.md](data_dictionary.md): every table and column of the synthetic data, and the public datasets.
  Read when working on the generator, cleaning or features.
- [personas.md](personas.md): the five vendor personas and how outcomes are linked to them. Read to understand the
  simulated population.
- [assumptions.md](assumptions.md): every parameter with its source or "author's assumption", modelling assumptions
  and the known limitations. Read before quoting any figure as real.
- [cleaning_report.md](cleaning_report.md): transaction types and validation flags after cleaning. *Generated* by
  `src/clean.py`.
- [feature_report.md](feature_report.md): the leakage test and missing values of the features. *Generated* by
  `src/features.py`.
- [database.md](database.md): the app's database: SQLite or PostgreSQL, the schema notes, repayments, demo users and
  database tests. Read before running or deploying the app.
- `statement_summary.md` (not in the repository): aggregate numbers from the author's own statement, written by
  `scripts/statement_summary.py` and git-ignored because it derives from a real statement.

## App

- [app_overview.md](app_overview.md): roles, pages, privacy and security rules, and the app's limitations. Read first
  for the web app.
- [repayment_outcomes.md](repayment_outcomes.md): repayment tracking, the outcomes export and how it maps to the
  three outcome classes. Read before using recorded outcomes for anything.

## Evaluation

- [calibration_report.md](calibration_report.md): calibration, bootstrap intervals, the tier check and the score
  formula check for the deployed model. *Generated* by `python -m src.evaluate_calibration` (tables and figures in
  `reports/calibration/`). Read before making any claim about performance.

## Deployment

- [deployment.md](deployment.md): the checklist for the hosted deployment (Streamlit Community Cloud and Neon). Read
  with the database guide.

Figures used by the reports are in `docs/figures/`.

## See also

- [Project README](../README.md)
- [App overview](app_overview.md)
- [Calibration report](calibration_report.md)
