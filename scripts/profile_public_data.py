"""Profile every data file in data/raw/ (flat files or subfolders) into one column-level dictionary.
The PDF (FinAccess report) is skipped.

Run from the repo root:  python scripts/profile_public_data.py
Writes docs/public_data_profile.csv with: dataset, file, column, dtype, rows, n_missing, pct_missing, n_unique, example.
Reads: .csv, .xlsx/.xls, .dta (Stata), .sav (SPSS, needs pip install pyreadstat), .json, and german.data.
Survey files (.dta/.sav) also get the variable label as `description`.
"""
import pathlib
import pandas as pd

RAW = pathlib.Path("data/raw")
OUT = pathlib.Path("docs/public_data_profile.csv")
NROWS = 200_000  # PaySim has 6.3 million rows; profile a sample
GERMAN = ["checking_status", "duration_months", "credit_history", "purpose", "credit_amount", "savings",
          "employment_since", "instalment_rate", "personal_status_sex", "other_debtors", "residence_since",
          "property", "age", "other_instalment_plans", "housing", "existing_credits", "job",
          "people_liable", "telephone", "foreign_worker", "class"]

def read(path):
    """Return (dataframe, {column: description}) or (None, {})."""
    ext = path.suffix.lower()
    try:
        if ext == ".csv":
            try:
                return pd.read_csv(path, nrows=NROWS), {}
            except UnicodeDecodeError:
                return pd.read_csv(path, nrows=NROWS, encoding="latin-1"), {}
        if ext in {".xls", ".xlsx"}:
            return pd.read_excel(path, nrows=NROWS), {}
        if ext == ".json":
            return pd.read_json(path), {}
        if ext == ".dta":
            with pd.read_stata(path, iterator=True, convert_categoricals=False) as r:
                df = r.read(NROWS)
                return df, dict(r.variable_labels())
        if ext == ".sav":
            import pyreadstat
            df, meta = pyreadstat.read_sav(str(path), row_limit=NROWS)
            return df, dict(zip(meta.column_names, meta.column_labels))
        if path.suffix.lower() == ".data" and "german" in path.name.lower():
            return pd.read_csv(path, sep=" ", header=None, names=GERMAN), {}
    except Exception as e:
        print(f"skip {path}: {e}")
    return None, {}

if __name__ == "__main__":
    rows = []
    for path in sorted(RAW.rglob("*")):
        if not path.is_file() or path.name == "SOURCES.csv":
            continue
        df, desc = read(path)
        if df is None:
            continue
        dataset = path.stem if len(path.relative_to(RAW).parts) == 1 else path.relative_to(RAW).parts[0]
        for col in df.columns:
            s = df[col]
            rows.append({
                "dataset": dataset, "file": path.name, "column": col, "dtype": str(s.dtype),
                "rows": len(df), "n_missing": int(s.isna().sum()),
                "pct_missing": round(100 * s.isna().mean(), 2), "n_unique": int(s.nunique()),
                "example": "" if s.dropna().empty else str(s.dropna().iloc[0]),
                "description": desc.get(col, "") or "",
            })
    OUT.parent.mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"wrote {OUT} ({len(rows)} columns from {len({r['file'] for r in rows})} files)")