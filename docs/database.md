# Database

The web app stores accounts, saved score results, applications, repayment outcomes and an audit log. **All data in this project is
simulated**: the model is trained on synthetic statements and the demo accounts are made up. No statement content is
ever stored: a score check keeps only the result (score, ratings, reason phrases, request, derived monthly income,
number of rows read), lenders receive only a summary, and the audit log holds actions and ids.

The database layer is `app/db.py` (SQLAlchemy 2.x Core). The same schema and queries run on two databases:

| Setting | Database |
| --- | --- |
| `DATABASE_URL` not set (default) | SQLite file `data/private/app.db` (or the file in `APP_DB_PATH`) |
| `DATABASE_URL` set | PostgreSQL, e.g. Neon or the local Docker container |

`DATABASE_URL` is read from the environment first, then from Streamlit secrets (`.streamlit/secrets.toml` locally,
the Secrets box on Streamlit Community Cloud). A URL starting with `postgresql://` or `postgres://` is rewritten to
`postgresql+psycopg://` automatically. The URL contains a password: the app never prints or logs it, and connection
errors show a fixed message instead. `data/private/`, `.env` and `.streamlit/secrets.toml` are gitignored.

## Schema changes (no migration tool)

Tables are created on first use, idempotently (`create_all` with `checkfirst`), so there is no migration step for a
new database. There is no migration tool: a later schema change needs a fresh database or a manual `ALTER TABLE`.

**Schema change (estimated eligibility):** `score_checks` has two new nullable columns, `max_amount` and
`comfortable_amount`. `create_all` does not add columns to an existing table, so a database created before this
change must be updated by hand:

- local SQLite: stop the app, delete `data/private/app.db` (all data is simulated) and start the app again; it is
  recreated with the new columns. Run `python scripts/create_demo_users.py` again.
- PostgreSQL (Neon or Docker), keeping the data:

  ```sql
  ALTER TABLE score_checks ADD COLUMN max_amount DOUBLE PRECISION;
  ALTER TABLE score_checks ADD COLUMN comfortable_amount DOUBLE PRECISION;
  ```

  Old saved checks then show "Not enough income data" until the vendor checks their score again.

**Out-of-date schema check:** at start-up the app compares the database with the schema in `app/db.py` (SQLite and
PostgreSQL). If columns are missing it writes one log line, for example
`Database schema out of date. See docs/database.md. Missing: score_checks.max_amount, score_checks.comfortable_amount`,
and every page shows a short card "Database schema out of date. See docs/database.md." instead of failing on the
first insert or select. Restart the app after fixing the database (the check runs once per process).

## Repayments (repayment tracking)

The `repayments` table holds what happened to an approved loan, recorded by the lender who approved it (see
[repayment_outcomes.md](repayment_outcomes.md)). **All data in this project, these outcomes included, is simulated.**

| Column | Meaning |
| --- | --- |
| `id` | Row id |
| `application_id` | The application (unique: one repayment per application; foreign key to `applications.id`) |
| `due_date` | Decision date in Nairobi plus the request's repay-within days (part days round up) |
| `status` | `repaying`, `repaid_on_time`, `repaid_late` or `defaulted` (CHECK constraint) |
| `recorded_by` | The lender user who recorded the outcome |
| `recorded_at` | When it was recorded (UTC) |
| `note` | Optional plain-text note from the lender, at most 300 characters (CHECK constraint); escaped when shown, never in the audit log or the export |
| `created_at` | When the row was written |

**When rows are written:** lazily. Approving an application writes nothing here; an approved application with no row
is "repaying". The row is written when the lender records the outcome. This keeps the approval code unchanged and
covers loans approved before the table existed without a backfill. The due date is computed the same way before and
after the row exists.

**Allowed changes** (enforced in `app/staff_service.py`, `record_repayment`, on the server):

- only from `repaying` to `repaid_on_time`, `repaid_late` or `defaulted`; those three are final and never change;
- only by the lender who approved the application, and only once it is approved; admins can view, vendors can view
  their own status, neither can write;
- `repaid_on_time` and `repaid_late` on or after the approval; `defaulted` only after the due date has passed;
- every change writes an audit row (actor, application reference, old and new status, never the note); a refused
  attempt writes one generic `repayment_refused` line;
- two tabs recording at the same moment: the unique `application_id` lets only the first through.

**Why `defaulted` is permanent:** these outcomes are the labels for a future retraining, and a default is the label
that matters most. If it could be quietly changed later (for example after a partial recovery), the export would mix
outcomes recorded under different rules and the audit trail would no longer match the data. A later recovery is a
new fact, not a correction; if it ever needs recording it should be a new, separately audited status, not an edit.

**Existing databases:** no manual step. The app creates missing tables at start-up (`create_all` with `checkfirst`, on
SQLite and PostgreSQL alike), so the first start after this change adds `repayments`; no existing table or column
changes. To create it without starting the app, run `python -c "from app import db; db.get_engine()"` from the repo
root with the same `DATABASE_URL` (or none, for SQLite).

## SQLite (default)

Nothing to set up:

```
python scripts/create_demo_users.py
streamlit run app/main.py
```

## Neon (hosted PostgreSQL, for the temporary deployment)

1. Create a project at neon.tech, and copy the connection string from the dashboard ("Connection string", psycopg
   / SQLAlchemy format). It has this form (placeholders, not real values):

   ```
   postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require
   ```

2. Local run against Neon (PowerShell; the variable lives only in this window):

   ```
   $env:DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require"
   python scripts/create_demo_users.py
   streamlit run app/main.py
   ```

3. Streamlit Community Cloud: in the app's Settings > Secrets, add

   ```toml
   DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require"
   ```

   The tables are created on the first page load. Create the demo users once from your machine with step 2.

Neon suspends an idle database; the first query after a pause can be slow or fail once. The app retries a failed
connection once, and the engine pings pooled connections before use (`pool_pre_ping`) and recycles them after
5 minutes. If the database is still unreachable the app shows "The database is not reachable right now".

## Local PostgreSQL with Docker (optional)

```
copy .env.example .env          # then set POSTGRES_PASSWORD (and the other values) in .env
docker compose up -d
$env:DATABASE_URL = "postgresql+psycopg://creditscore:<your password>@127.0.0.1:5432/creditscore"
python scripts/create_demo_users.py
streamlit run app/main.py
```

The container listens on 127.0.0.1 only. Use 127.0.0.1, not localhost, in the URL: on Windows localhost tries IPv6 (::1) first, which the container does not answer, so each connection waits for the timeout. `docker compose down -v` removes it and its data.

## Demo users

`python scripts/create_demo_users.py` creates 1 vendor, 2 lenders (Umoja SACCO, Tumaini Microfinance) and 1 admin
in whichever database `DATABASE_URL` selects. Passwords come from `DEMO_VENDOR_PASSWORD`, `DEMO_UMOJA_PASSWORD`,
`DEMO_TUMAINI_PASSWORD` and `DEMO_ADMIN_PASSWORD`, or are generated and printed once. Running it again leaves
existing accounts unchanged. It prints the database type, never the URL.

## Tests

- `python -m pytest` runs everything on SQLite and needs no PostgreSQL.
- With `DATABASE_URL` pointing at PostgreSQL, the database tests also run there: `python -m pytest -m postgres`.
  Each test creates its own temporary schema (`apptest_...`) and drops it afterwards, so existing tables are never
  touched; still, point it at a test database, not the deployment.
- CI (`.github/workflows/tests.yml`) has a second job that runs the `postgres` tests against a PostgreSQL 16 service
  container.

## Notes on portability

- Timestamps are timezone-aware UTC on both databases (SQLite stores them without an offset; they are read back as
  UTC).
- Emails are stored and compared lower-cased (a CHECK constraint enforces it) with a unique index.
- Application references (A-101, A-102, ...) are the row id plus 100, set in the same transaction as the insert, so
  concurrent applications can never share a reference.
- The failed sign-in counter and the lock are one atomic `UPDATE ... RETURNING`.
- On SQLite, concurrent writers wait for each other (30 s busy timeout); SQLite is meant for one machine and light
  use. Use PostgreSQL for the deployment.

## See also

- [Project README](../README.md)
- [Deployment](deployment.md)
- [App overview](app_overview.md)
- [Repayment outcomes](repayment_outcomes.md)
