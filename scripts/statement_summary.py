"""
Summarise a REAL M-Pesa statement into aggregate numbers only.

Runs on your own computer. Nothing is uploaded. The output contains NO names,
phone numbers, receipt numbers, dates of single transactions or single rows.
Categories with fewer than MIN_CELL events are reported as "<5".

Usage (from the repo root, creditscore env active):
    python scripts/statement_summary.py data/private/statement.csv
    python scripts/statement_summary.py data/private/statement.pdf --pdf-password 123456
Optional: --from 2025-01-01 --to 2025-06-30   (to look at one period)
Output:  docs/statement_summary.md   (safe to paste into chat after you read it)
Needs:   pandas; for PDF also pdfplumber (pip install pdfplumber)
"""
import argparse, re, sys
from pathlib import Path
import numpy as np
import pandas as pd

MIN_CELL = 5

# ---------- 1. read ----------
NUM = r"(-?[\d,]+\.\d{2})"
DATE = r"(\d{4}-\d{2}-\d{2}|\d{2}[-/]\d{2}[-/]\d{4})"
TX_RE = re.compile(r"^([A-Z0-9]{8,12})\s*" + DATE + r"\s*(\d{2}:\d{2}(?::\d{2})?)\s*(.*?)\s*([A-Za-z0]{5,12})\s*" + NUM + r"\s*" + NUM + r"\s*" + NUM + r"$")
TX_RE2 = re.compile(r"^([A-Z0-9]{8,12})\s*" + DATE + r"\s*(\d{2}:\d{2}(?::\d{2})?)\s*(.*?)\s*" + NUM + r"\s*" + NUM + r"\s*" + NUM + r"$")
START_RE = re.compile(r"^[A-Z0-9]{8,12}\s*" + DATE)

def parse_text_lines(lines):
    """Join wrapped lines, then match each transaction line."""
    joined, cur = [], None
    for ln in lines:
        ln = re.sub(r"\s+", " ", ln).strip()
        if not ln: continue
        if START_RE.match(ln):
            if cur: joined.append(cur)
            cur = ln
        elif cur and not re.match(r"^(page|receipt|statement|\d+ of \d+)", ln.lower()) and len(cur) < 400:
            cur += " " + ln
    if cur: joined.append(cur)
    rows = []
    for ln in joined:
        m = TX_RE.match(ln)
        if m:
            r, d, t, det, st, pi, wd, bal = m.groups()
            rows.append([r, d + " " + t, det, st.replace("0", "O").upper(), pi, wd, bal]); continue
        m = TX_RE2.match(ln)
        if m:
            r, d, t, det, pi, wd, bal = m.groups()
            rows.append([r, d + " " + t, det, "COMPLETED", pi, wd, bal])
    return pd.DataFrame(rows, columns=["receipt", "time", "details", "status", "paid_in", "withdrawn", "balance"]), len(joined)


def ocr_lines(path, pw=None, scale=2.0):
    """OCR an image-only PDF locally. Returns text lines rebuilt from word positions."""
    import pypdfium2 as pdfium
    from rapidocr_onnxruntime import RapidOCR
    engine = RapidOCR()
    pdf = pdfium.PdfDocument(str(path), password=pw)
    lines = []
    for i in range(len(pdf)):
        img = pdf[i].render(scale=scale).to_numpy()
        H = img.shape[0]; STRIP, OVER = 500, 80
        items, seen = [], set()
        for y0 in range(0, H, STRIP - OVER):
            res, _ = engine(img[y0:y0 + STRIP])
            for box, txt, conf in (res or []):
                ys = [pt[1] + y0 for pt in box]; xs = [pt[0] for pt in box]
                key = (round(sum(ys) / 4 / 12), round(min(xs) / 20), txt)
                if key in seen: continue
                seen.add(key)
                items.append((sum(ys) / 4, min(xs), max(ys) - min(ys), txt))
        items.sort()
        row, last_y, h = [], None, 1
        for y, x, hh, txt in items:
            if last_y is not None and abs(y - last_y) > max(8, 0.6 * h):
                lines.append(" ".join(t for _, t in sorted(row))); row = []
            row.append((x, txt)); last_y, h = y, max(hh, 1)
        if row: lines.append(" ".join(t for _, t in sorted(row)))
        print(f"OCR page {i+1}/{len(pdf)} done", flush=True)
    return lines

def balance_check(df):
    """Keep rows whose balance equals previous balance + paid in - withdrawn (catches OCR digit errors)."""
    d = df.copy()
    expected = d["balance"].shift(1) + d["paid_in"] - d["withdrawn"]
    ok = (expected - d["balance"]).abs() < 0.51
    ok.iloc[0] = True
    return ok

def mask(s):
    s = re.sub(r"[A-Za-z]", "a", str(s)); return re.sub(r"\d", "9", s)

def diagnose(path, pw):
    import pdfplumber
    with pdfplumber.open(path, password=pw) as pdf:
        print(f"Pages: {len(pdf.pages)}")
        for i in (0, 1):
            if i >= len(pdf.pages): break
            pg = pdf.pages[i]
            tabs = pg.extract_tables()
            print(f"Page {i+1}: tables found = {len(tabs)}")
            print(f"Page {i+1}: first 12 text lines, letters->a digits->9 (safe to paste):")
            for ln in (pg.extract_text() or "").splitlines()[:12]:
                print("   ", mask(ln)[:140])

def read_statement(path, pw=None, use_ocr=False):
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        import pdfplumber
        lines, rows = [], []
        with pdfplumber.open(p, password=pw) as pdf:
            for page in pdf.pages:
                lines.extend((page.extract_text() or "").splitlines())
                for t in page.extract_tables():
                    rows.extend(t)
        out, n_start = parse_text_lines(lines)
        if len(out) < 10 and (use_ocr or not "".join(lines).strip()):
            print("No selectable text found: reading the PDF as images with OCR (a few minutes)...")
            lines = ocr_lines(p, pw)
            out, n_start = parse_text_lines(lines)
        if len(out) >= 10:
            print(f"Read {len(out)} of {n_start} transaction lines from the PDF text.")
            df = out
            for c in ("paid_in", "withdrawn", "balance"):
                df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")
            df["time"] = pd.to_datetime(df["time"], errors="coerce", dayfirst=not df["time"].str.match(r"^\d{4}").all())
            df = df.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
            df["withdrawn"] = df["withdrawn"].abs().fillna(0.0); df["paid_in"] = df["paid_in"].fillna(0.0)
            df = df.dropna(subset=["balance"]).reset_index(drop=True)
            ok = balance_check(df)
            print(f"Balance check: {ok.mean():.0%} of {len(df)} rows are consistent with the running balance "
                  f"({(~ok).sum()} rows dropped as likely OCR/parse errors).")
            if ok.mean() < 0.8:
                print("WARNING: below 80% consistent. The reading is poor; results would not be reliable.")
            return df[ok].reset_index(drop=True)
        width = max((len(r) for r in rows), default=0)
        df = pd.DataFrame([list(r) + [None] * (width - len(r)) for r in rows])
        df = df.map(lambda v: re.sub(r"\s+", " ", v).strip() if isinstance(v, str) else v)
    elif p.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(p, header=None)
    else:
        df = pd.read_csv(p, header=None, dtype=str, on_bad_lines="skip", engine="python")
    # find header row
    for i in range(min(len(df), 60)):
        vals = " ".join(str(v).lower() for v in df.iloc[i].values)
        if "receipt" in vals and "details" in vals:
            df.columns = [str(c).strip().lower() for c in df.iloc[i].values]
            df = df.iloc[i + 1:].reset_index(drop=True)
            break
    else:
        sys.exit("Could not read the PDF. Run:  python scripts/statement_summary.py <file> --diagnose  and paste the output.")
    cols = {}
    for c in df.columns:
        if "receipt" in c: cols[c] = "receipt"
        elif "completion" in c or c.startswith("time"): cols[c] = "time"
        elif "detail" in c: cols[c] = "details"
        elif "status" in c: cols[c] = "status"
        elif "paid" in c: cols[c] = "paid_in"
        elif "withdraw" in c: cols[c] = "withdrawn"
        elif "balance" in c: cols[c] = "balance"
    df = df.rename(columns=cols)[list(dict.fromkeys(cols.values()))]
    for c in ("paid_in", "withdrawn", "balance"):
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(r"[,\s]", "", regex=True), errors="coerce").fillna(0.0) \
                if c != "balance" else pd.to_numeric(df[c].astype(str).str.replace(r"[,\s]", "", regex=True), errors="coerce")
    df["time"] = pd.to_datetime(df["time"], errors="coerce", dayfirst=False)
    if df["time"].isna().mean() > 0.5:
        df["time"] = pd.to_datetime(df["time"].astype(str), errors="coerce", dayfirst=True)
    df = df.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
    df["withdrawn"] = df["withdrawn"].abs()
    return df

# ---------- 2. classify ----------
RULES = [  # (type, regex on lower-cased details); first match wins
    ("fuliza_draw", r"^overdraft(?!charge)|overdraftofcreditparty|fuliza.*(draw|disburs)|overdraw.*(draw|disburs)"),
    ("fuliza_repay", r"odloanrepayment|overdraft.*repay|fuliza.*repay|repayment.*overdraw"),
    ("fuliza_fee", r"overdraftcharge|fuliza.*(fee|charge)|accessfee"),
    ("mshwari_in", r"m-?shwari.*(loandisburse|loanreceived)|kcbm-?pesa.*(loan|disburs)|loandisburse|loanreceived"),
    ("mshwari_repay", r"m-?shwari.*(repay|loan)|kcbm-?pesa.*repay|loanrepayment|loan.*repay"),
    ("savings_move", r"m-?shwari.*(deposit|withdraw)|locksavings|kcbm-?pesa.*(deposit|withdraw)|mmf|ziidi"),
    ("fee", r"charge|fee"),
    ("till_in", r"(merchantpayment|payment).*from|customerpayment.*from|buygoods.*from|received.*till"),
    ("send_in", r"fundsreceivedfrom|receivedfrom|customertransferfrom"),
    ("send_out", r"customertransfer(fuliza\w*)?to|sentto|sendmoney"),
    ("till_out", r"merchantpayment(?!.*from)|customerpaymenttosmallbusiness|buygoods|till"),
    ("paybill_out", r"paybill|billpayment|^pay$"),
    ("airtime", r"airtime|bundle|databundle"),
    ("cash_out", r"withdraw|cashout"),
    ("cash_in", r"depositoffunds|cashin|depositatagent"),
    ("reversal", r"reversal"),
]
def classify(d, paid_in, withdrawn):
    s = re.sub(r"\s+", "", str(d).lower())
    for t, rx in RULES:
        if re.search(rx, s):
            return t
    return "other_in" if paid_in > 0 else "other_out"

def template(d):
    s = str(d)
    s = re.sub(r"\b\d{6,}\b", "<NUM>", s)          # phone / till / account numbers
    s = re.sub(r"\*+\d+", "<NUM>", s)
    s = re.sub(r"\s-\s.*$", " - <NAME>", s)          # everything after the dash is a name
    s = re.sub(r"\b[A-Z]{2,}(?:\s[A-Z]{2,})+\b", "<NAME>", s)
    return s.strip()[:60]

def counterparty(d):
    m = re.search(r"(\d{9,12}|\*{3,}\d{3,4})", str(d))
    if m: return m.group(1)
    m = re.search(r"-\s(.+)$", str(d))
    return m.group(1).strip().upper() if m else None

def q(x, p): return float(np.nanpercentile(x, p)) if len(x) else np.nan
def cell(n): return str(n) if n >= MIN_CELL else "<5"
def fmt(x, d=0): return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:,.{d}f}"

# ---------- 3. summarise ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path"); ap.add_argument("--pdf-password")
    ap.add_argument("--diagnose", action="store_true")
    ap.add_argument("--ocr", action="store_true", help="force OCR for image-only PDFs")
    ap.add_argument("--from", dest="d0"); ap.add_argument("--to", dest="d1")
    ap.add_argument("--out", default="docs/statement_summary.md")
    a = ap.parse_args()

    if a.diagnose:
        diagnose(a.path, a.pdf_password); return
    df = read_statement(a.path, a.pdf_password, a.ocr)
    if "status" in df: df = df[df["status"].astype(str).str.lower().str.contains("complet", na=True)]
    if a.d0: df = df[df["time"] >= a.d0]
    if a.d1: df = df[df["time"] <= a.d1 + " 23:59:59"]
    df["type"] = [classify(d, p, w) for d, p, w in zip(df["details"], df["paid_in"], df["withdrawn"])]
    df["day"] = df["time"].dt.normalize()
    df["month"] = df["time"].dt.to_period("M")
    df["cp"] = df["details"].map(counterparty)
    df["fz_funded"] = df["details"].str.lower().str.contains("fuliza", na=False)
    L = []
    add = L.append

    span_days = (df["day"].max() - df["day"].min()).days + 1
    add(f"# Statement summary (aggregates only)\n\nPeriod length: {span_days} days ({df['month'].nunique()} calendar months). Completed transactions: {len(df)}.\n")
    add("**Check before pasting:** this file has no names, numbers or single rows. Read it once anyway.\n")

    # type mix
    mix = df.groupby("type").agg(n=("type", "size"), paid_in=("paid_in", "sum"), withdrawn=("withdrawn", "sum")).sort_values("n", ascending=False)
    add("## 1. Transaction types (count and value, KES)\n\n| Type | Count | Paid in | Withdrawn |\n|---|---|---|---|")
    for t, r in mix.iterrows():
        add(f"| {t} | {cell(int(r.n))} | {fmt(r.paid_in) if r.n >= MIN_CELL else '-'} | {fmt(r.withdrawn) if r.n >= MIN_CELL else '-'} |")

    # activity (assumptions rows 2 and 4)
    per_day = df.groupby("day").size()
    per_month_days = df.groupby("month")["day"].nunique()
    add("\n## 2. Activity (replaces assumptions rows 2 and 4)\n")
    add(f"- Active days per month: median {fmt(per_month_days.median(),1)}, range {per_month_days.min()} to {per_month_days.max()}")
    core = df[~df["type"].isin(["fee", "fuliza_draw", "fuliza_fee"])]
    cpd = core.groupby("day").size()
    add(f"- Transactions per active day excluding fee and Fuliza-draw lines: median {fmt(cpd.median(),1)}, 90th percentile {fmt(q(cpd,90),1)}, max {cpd.max()}")
    add(f"- Transactions per active day (all lines): median {fmt(per_day.median(),1)}, 90th percentile {fmt(q(per_day,90),1)}, max {per_day.max()}")

    # inflows / ticket size (row 1) and till vs send (row 3)
    inc = df[df["type"].isin(["till_in", "send_in", "other_in"]) & (df["paid_in"] > 0)]
    add("\n## 3. Money received from people (excluding loans, cash-in, reversals)\n")
    if len(inc):
        add(f"- Ticket size (KES): 25th pct {fmt(q(inc.paid_in,25))}, median {fmt(q(inc.paid_in,50))}, 75th {fmt(q(inc.paid_in,75))}, 90th {fmt(q(inc.paid_in,90))}")
        by = inc.groupby("type").agg(n=("paid_in", "size"), v=("paid_in", "sum"))
        tot_n, tot_v = by.n.sum(), by.v.sum()
        add("\n| Inflow type | Share of count | Share of value |\n|---|---|---|")
        for t, r in by.iterrows():
            add(f"| {t} | {r.n/tot_n:.0%} | {r.v/tot_v:.0%} |")
        cp = inc["cp"].dropna()
        if len(cp):
            vc = cp.value_counts()
            repeat_tx = vc[vc > 1].sum() / vc.sum()
            add(f"\n- Repeat-sender share (row 6): {repeat_tx:.0%} of inflows come from a sender who appears more than once; {len(vc)} distinct senders (no identities shown)")
    # monthly inflow + seasonality (row 5)
    m_in = inc.groupby("month")["paid_in"].sum()
    if len(m_in) >= 4: m_in = m_in.iloc[1:-1]   # drop first and last month: usually partial
    if len(m_in) >= 3:
        add(f"\n- Monthly inflow (KES): min {fmt(m_in.min())}, median {fmt(m_in.median())}, max {fmt(m_in.max())}; peak/off-peak ratio (max / min full month) {m_in.max()/max(m_in.min(),1):.1f}")

    # balance
    bal = df.dropna(subset=["balance"]).groupby("day")["balance"].last()
    add("\n## 4. Balance behaviour\n")
    if len(bal):
        add(f"- End-of-day balance (KES): 10th pct {fmt(q(bal,10))}, median {fmt(q(bal,50))}, 90th {fmt(q(bal,90))}")
        add(f"- Share of active days ending below KES 100: {(bal<100).mean():.0%}; below KES 20: {(bal<20).mean():.0%}")

    # Fuliza (rows 7c, 9b)
    fd = df[df["type"] == "fuliza_draw"]
    fr = df[df["type"] == "fuliza_repay"]
    add("\n## 5. Fuliza (replaces assumptions rows 7c and 9b)\n")
    add(f"- Draw events: {cell(len(fd))}; repayment events: {cell(len(fr))}")
    amt = fd.paid_in.where(fd.paid_in > 0, fd.withdrawn)
    if len(fd) >= MIN_CELL:
        add(f"- Draw size (KES): median {fmt(q(amt,50))}, mean {fmt(amt.mean())}, 90th pct {fmt(q(amt,90))}, max {fmt(amt.max())}")
        add(f"- Draws per month: median {fmt(fd.groupby('month').size().median(),1)}")
        # repayment lag: days from each draw to the next repayment event
        lags = []
        rep_t = fr["time"].values
        for t in fd["time"].values:
            nxt = rep_t[rep_t >= t]
            if len(nxt): lags.append((nxt[0] - t) / np.timedelta64(1, "D"))
        if len(lags) >= MIN_CELL:
            add(f"- Days from a draw to the next repayment event: median {fmt(np.median(lags),1)}, 75th pct {fmt(q(lags,75),1)}, 90th {fmt(q(lags,90),1)} (approximate: repayments are not matched to a specific draw)")
    tot_d, tot_r = amt.sum(), fr.withdrawn.sum()
    out = df[df["withdrawn"] > 0]
    out = out[~out["type"].isin(["fuliza_repay", "fee", "fuliza_fee"])]
    if len(out) >= MIN_CELL:
        add(f"- Total drawn KES {fmt(tot_d)} vs total repaid KES {fmt(tot_r)} (repaid/drawn = {tot_r/max(tot_d,1):.0%})")
        add(f"- Payments funded by Fuliza: {out.fz_funded.mean():.0%} of outgoing payments by count, {out.loc[out.fz_funded,'withdrawn'].sum()/max(out.withdrawn.sum(),1):.0%} by value")
    # other loans
    li = df[df["type"] == "mshwari_in"]; lr = df[df["type"] == "mshwari_repay"]
    add("\n## 6. Other mobile loans (M-Shwari, KCB M-Pesa, other)\n")
    add(f"- Loan disbursements: {cell(len(li))}; repayments: {cell(len(lr))}")
    if len(li) >= MIN_CELL:
        add(f"- Loan amount received (KES): median {fmt(q(li.paid_in,50))}, range {fmt(li.paid_in.min())} to {fmt(li.paid_in.max())}")
    if 0 < len(li) < MIN_CELL:
        add("- Too few loan events to report amounts safely. Note them by hand if needed.")

    # unmatched templates so classification rules can be fixed without exposing data
    oth = df[df["type"].isin(["other_in", "other_out"])]
    add("\n## 7. Unclassified descriptions (masked) — send these so I can fix the rules\n")
    tc = oth["details"].map(template).value_counts()
    add("| Masked description | Count |\n|---|---|")
    for t, n in tc.head(15).items():
        if n >= MIN_CELL: add(f"| {t} | {n} |")
    add(f"\nUnclassified share of all transactions: {len(oth)/len(df):.0%}")

    add("\n## 8. Limits\n\n- One account, mixed personal and business use. Personal transfers (family, salary) are counted as inflows unless they are tagged otherwise, so ticket size and seasonality may be off.\n- Classification is by wording in the Details column and may mis-label some rows (see section 7).\n- Treat every value as 'observed, n=1', not as typical for vendors.")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L)); print(f"\nWritten to {a.out}")

if __name__ == "__main__":
    main()