# Repayment outcomes

**All data in this project is simulated, and so are the repayment outcomes recorded in the app.** Nothing here
describes a real borrower.

## Purpose

The score is trained on simulated defaults. Repayment tracking closes the loop: when a lender approves a loan, they
later record what happened to it (repaid on time, repaid late, or defaulted). Over time those recorded outcomes are a
labelled dataset that a future, reviewed retraining could use.

## What the app does and does not do

- A lender records the outcome of a loan **they approved**, once, on the Decided page. The outcome is final
  ([database.md](database.md#repayments-repayment-tracking) lists the rules and why a default is permanent).
- The vendor sees the status and the due date of their approved loans in History, read-only.
- An admin sees how many outcomes are recorded and can export them.
- **The live model is never retrained automatically, and recorded outcomes are never fed into scoring.** The score,
  the risk tiers and the estimated limits do not change when an outcome is recorded.
- **Retraining is a manual, reviewed step**: export the outcomes, check them (enough defaults, no single lender
  dominating, the period they cover), retrain offline with the existing scripts, evaluate (for example
  `python -m src.evaluate_calibration`, see [calibration_report.md](calibration_report.md)), and only then replace the model files, with the change reviewed and recorded.

## The export

Admin, Overview, **Export outcomes (CSV)**. It runs only when clicked, and every export writes an audit row (the
admin and the number of rows). Only loans with a **final** outcome are exported; loans still repaying are not.

| Column | Meaning |
| --- | --- |
| `application_id` | The application's internal id |
| `score_check_id` | The saved score check behind it. **Empty today:** an application is scored fresh from the statement uploaded with it and is not linked to a saved check |
| `snapshot_score` | The 300-850 score the lender saw |
| `snapshot_pd` | The estimated chance of default behind that score |
| `risk_tier` | Low, Moderate, High or Very high risk |
| `requested_amount` | The amount requested (KES) |
| `repay_within_days` | The repay-within days requested |
| `final_status` | `repaid_on_time`, `repaid_late` or `defaulted` |
| `recorded_date` | The date the outcome was recorded (Nairobi) |

**Not exported:** names, emails, organisation names, phone numbers, notes (the lender's decision note or repayment
note), statements, transactions, file names or any file data. The export is enough to compare predicted risk with the
recorded outcome. To retrain on features, the features would have to be rebuilt from statements, which the app never
stores; that is a separate, consented data collection, not something this export can do.

## Mapping to the three outcome classes

The planned three-class work (`src/train_multiclass.py`, [model_report_3class.md](model_report_3class.md)) uses the repayment status
classes of the simulation: 0 on time, 1 late, 2 default. The recorded outcomes map one to one:

| `final_status` | Class | Binary default label (`defaulted`) |
| --- | --- | --- |
| `repaid_on_time` | 0, on time | 0 |
| `repaid_late` | 1, late | 0 |
| `defaulted` | 2, default | 1 |

The binary model used today would use the last column; `late_or_default` (classes 1 and 2) is the secondary target.

## Limits

- The outcomes are simulated, and whatever a lender records reflects only the loans that lender approved. Loans that
  were declined have no outcome, so a model retrained on these labels alone would learn from approved applicants only
  (selection bias). A retraining has to account for that.
- An outcome recorded by mistake cannot be changed in the app, by design. A correction would need a reviewed change in
  the database itself, with its own audit note.

## See also

- [Project README](../README.md)
- [Database](database.md)
- [App overview](app_overview.md)
- [Three-class report](model_report_3class.md)
