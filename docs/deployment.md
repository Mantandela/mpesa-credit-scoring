# Deployment

A short checklist for the temporary deployment on Streamlit Community Cloud with a hosted PostgreSQL database
(Neon). The detailed database steps live in [database.md](database.md#neon-hosted-postgresql-for-the-temporary-deployment);
this page only puts them in order. **The deployment runs on simulated data only.**

1. **Database.** Create a Neon project and copy its connection string (the form is
   `postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require`, with your own values; never commit it).
2. **Secrets.** In the Streamlit Community Cloud app settings, add `DATABASE_URL` under Secrets. Locally the same key
   goes in `.streamlit/secrets.toml`, which is git-ignored.
3. **Tables.** They are created on the first page load (`docs/database.md`), on PostgreSQL as on SQLite.
4. **First accounts.** From your own machine, with `DATABASE_URL` set to the same database, run
   `python scripts/create_demo_users.py` once ([database.md](database.md#demo-users)).
5. **Model files.** The app scores with `models/logistic.joblib` and `models/reference.json`, which are built locally
   and git-ignored. The deployed app needs them too; see the open point below.
6. **Check.** Sign in as each role and run one score check before sharing the link.

**Open point:** the repository does not say how the model files reach the hosted app (they are git-ignored). Until
that is decided, a deployment from the repository alone shows "The scoring engine is still starting" on every score.

## See also

- [Project README](../README.md)
- [Database](database.md)
- [App overview](app_overview.md)
