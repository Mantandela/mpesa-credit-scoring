"""Small hand-built M-Pesa-style statements for the tests.

Nothing here comes from the generator, so the tests run in seconds and do not need the data folders. The wording of
`details` follows docs/data_dictionary.md, and the running balance is kept consistent on purpose, so a clean statement
raises no validation flag. A test that wants a defect injects one itself.
"""
import numpy as np
import pandas as pd

COLUMNS = ["vendor_id", "receipt_no", "completion_time", "details", "transaction_status", "paid_in", "withdrawn",
           "balance", "counterparty_id", "txn_type_true"]


def make_vendor(vendor_id="V0001", start="2026-01-01", days=120, daily_in=200.0, opening=1000.0, n_customers=6):
    """One vendor: a till payment every day, a supplier payment and an agent withdrawal (with its fee) every 7 days,
    a paybill every 30 days, and a Fuliza draw repaid two days later every 15 days. Returns a raw transactions frame."""
    events = []

    def add(day, minutes, details, paid_in, withdrawn, cp, true, status="Completed"):
        events.append((pd.Timestamp(start) + pd.Timedelta(days=day, hours=9, minutes=minutes),
                       details, status, paid_in, withdrawn, cp, true))

    for d in range(days):
        add(d, 0, f"Merchant Payment from CP_{d % n_customers:04d}", daily_in, 0, f"CP_{d % n_customers:04d}", "TILL_PAYMENT_IN")
        if d % 7 == 3:
            add(d, 10, "Merchant Payment to 123456 - CP_S001", 0, 300, "CP_S001", "BUY_GOODS_OUT")
        if d % 7 == 5:
            add(d, 20, "Customer Withdrawal At Agent - AG01", 0, 500, "", "WITHDRAW_AGENT")
            add(d, 21, "Customer Withdrawal Charge", 0, 11, "", "FEE")
        if d % 30 == 10:
            add(d, 30, "Pay Bill to 888880 - CP_B001 Acc. 1234", 0, 800, "CP_B001", "PAYBILL_OUT")
        if d % 15 == 6:
            add(d, 40, "OverDraft of Credit Party", 300, 0, "", "FULIZA_DRAW")
            add(d + 2, 50, "OD Loan Repayment to 232323 - M-PESA Overdraw", 0, 309, "", "FULIZA_REPAY")
    events.sort(key=lambda e: e[0])                     # time order first, then the running balance and receipt numbers
    rows, bal = [], opening
    for seq, (t, details, status, paid_in, withdrawn, cp, true) in enumerate(events, start=1):
        bal = bal + paid_in - withdrawn
        rows.append({"vendor_id": vendor_id, "receipt_no": f"{vendor_id}R{seq:06d}", "completion_time": t,
                     "details": details, "transaction_status": status, "paid_in": float(paid_in),
                     "withdrawn": float(withdrawn), "balance": float(bal), "counterparty_id": cp, "txn_type_true": true})
    return pd.DataFrame(rows, columns=COLUMNS)


def recompute_balance(df, opening=1000.0):
    """Rebuild the running balance after rows were changed or removed (keeps the statement consistent)."""
    df = df.sort_values("completion_time", kind="stable").reset_index(drop=True).copy()
    df["balance"] = opening + (df.paid_in - df.withdrawn).cumsum()
    return df


def make_apps(vendor_id="V0001", dates=("2026-03-15",), amount=5000.0, term=14):
    return pd.DataFrame({"application_id": [f"A_{vendor_id}_{i}" for i in range(len(dates))],
                         "vendor_id": vendor_id,
                         "application_date": pd.to_datetime(list(dates)),
                         "requested_amount": amount, "requested_term_days": term})


def make_vendors_table(vendor_ids, personas=None):
    personas = personas or ["stable", "growing", "seasonal", "new", "struggling"]
    return pd.DataFrame({"vendor_id": list(vendor_ids),
                         "persona": [personas[i % len(personas)] for i in range(len(vendor_ids))],
                         "business_type": "retail_kiosk",
                         "gender": ["F" if i % 2 else "M" for i in range(len(vendor_ids))]})