# App overview

The Nuru web app (`streamlit run app/main.py`, from the repo root). **All data in it is simulated**: synthetic
statements, demo accounts and simulated outcomes.

## Roles

| Role | Can | Cannot |
| --- | --- | --- |
| Vendor | Sign up, check a score, apply to a lender, follow applications and their repayment status, change settings | See other vendors, lenders' notes on other applications, or anything about lenders' work |
| Lender | Sign up (one account per organisation) or be added by an admin; review applications addressed to it, approve or decline, record repayment outcomes of its approved loans | See other lenders' applications, the vendor's statement, or the vendor's other score checks |
| Admin | See platform counts, manage accounts (add a lender or admin, disable, enable, unlock), read the audit log, export recorded outcomes | Decide applications, record repayments, or be created from the sign-up page |

Roles are checked on the server for every page and every service call (`app/service.py`, `app/staff_service.py`),
whatever the screen shows.

## Pages

- **Vendor:** Home (score, estimated limit, quick actions, business health, recent activity), Check score, Result,
  Reasons (with a what-if amount that never changes the score), Apply, Sent, History, Profile.
- **Lender:** Queue (pending applications), Decided (with repayment tracking), Review application, Profile.
- **Admin:** Overview, Users (and Add a lender or admin), Audit, Profile.
- **Signed out:** Sign in, and Create account (as a vendor or a lender).

## Privacy and security rules

- **Statements are never stored.** An upload is read once in memory, scored, and discarded; only the result (score,
  ratings, reasons, request, derived monthly income) is saved, and only if the vendor keeps "Save my score results"
  on. Uploads are Excel or CSV up to 10 MB (a PDF only if it has a text layer).
- **Apply scores the statement again.** The vendor uploads it with the application, it is scored fresh with the
  requested amount and term, and the application is sent only if that result allows it.
- **Lenders see a snapshot only:** score, risk level, chance of default, ratings, reasons, the request and the
  estimated limit, plus the vendor's name. Never the statement.
- **Decisions are final.** A lender approves or declines once; the optional note reaches the vendor.
- **Accounts:** passwords are hashed (scrypt) and never shown again; five failed sign-ins lock an account for ten
  minutes; there is no password reset or email verification in this prototype.
- **Audit log:** actions and ids only, never statement content, notes, amounts or passwords.
- **Errors** show a short card with an incident id; the database URL and stack traces are never shown or logged.

## Repayment outcomes

Lenders record what happened to each approved loan (repaid on time, repaid late, defaulted). The outcome is final, a
default only after the due date. Vendors see the status read-only; admins see counts and can export final outcomes
for a future reviewed retraining. The live model is never updated from them. Details:
[repayment_outcomes.md](repayment_outcomes.md); the table and its rules: [database.md](database.md#repayments-repayment-tracking).

## Limitations

- **Simulated data only.** See [calibration_report.md](calibration_report.md#limits).
- **No statement-ownership check.** The app does not check that an uploaded statement belongs to the signed-in
  vendor (for example by matching the name or phone number on the statement). A vendor could score someone else's
  statement. A real service would need this check and consent.
- **Self-registered lenders are not verified.** A lender who signs up is active at once and appears on every vendor's
  Apply list; an approval step would need a schema change (a pending state).
- **Placeholder loan-limit policy.** See [scoring_function.md](scoring_function.md#estimated-eligibility-prototype-policy).
- **No migrations.** See [database.md](database.md#schema-changes-no-migration-tool).
- **SQLite is for one machine.** Use PostgreSQL for a shared deployment ([deployment.md](deployment.md)).

## See also

- [Project README](../README.md)
- [Scoring function](scoring_function.md)
- [Database](database.md)
- [Repayment outcomes](repayment_outcomes.md)
