"""Generate synthetic M-Pesa statements, vendors and loan applications for informal-sector vendors."""
import argparse
import hashlib
import math
import os
import sys
import datetime as dt

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402

EAT_EPOCH = dt.datetime(1970, 1, 1)
PARAM_KEYS = ["tx_per_day", "ticket", "active_days", "trend", "weekly_cv", "repeat", "till_share",
              "fuliza_prop", "sweep_prob", "supplier_prob", "bill_miss"]


def tariff(table, amount):
    for upper, fee in table:
        if amount <= upper:
            return fee
    return table[-1][1]


def hid(prefix, *parts):
    return prefix + hashlib.md5("-".join(str(p) for p in parts).encode()).hexdigest()[:8].upper()


def make_vendor(rng, idx, max_months):
    names = list(C.PERSONAS)
    persona = rng.choice(names, p=[C.PERSONAS[n]["share"] for n in names])
    own = C.PERSONAS[persona]
    v = {"vendor_id": f"V{idx:05d}", "persona": persona}
    for key in PARAM_KEYS:
        src = own
        if rng.random() < C.PERSONA_OVERLAP:
            src = C.PERSONAS[rng.choice(C.ADJACENT[persona])]
        lo, hi = src[key]
        v[key] = rng.uniform(lo, hi)
    lo, hi = own["latent_risk"]
    v["latent_risk"] = rng.uniform(lo, hi)
    mid, half = (lo + hi) / 2, (hi - lo) / 2
    z = (v["latent_risk"] - mid) / half                # -1 to +1: position inside the persona's own risk range
    v["inflow_scale"] = 1 - C.RISK_INFLOW_EFFECT * z
    v["fuliza_prop"] = float(np.clip(v["fuliza_prop"] + C.RISK_FULIZA_EFFECT * z, 0, 1))
    v["bill_miss"] = float(np.clip(v["bill_miss"] + C.RISK_BILL_MISS_EFFECT * z, 0, 1))
    v["weekly_cv"] = float(v["weekly_cv"] * (1 + C.RISK_CV_EFFECT * z))
    v["trend"] = float(v["trend"] - C.RISK_TREND_EFFECT * z)
    months = int(rng.integers(own["months"][0], own["months"][1] + 1))
    if max_months:
        months = min(months, max_months)
    v["months_of_history"] = months
    v["history_days"] = months * 30 + (0 if months < 3 else int(rng.integers(0, 30)))
    v["business_type"] = str(rng.choice(C.BUSINESS_TYPES))
    v["gender"] = str(rng.choice(["female", "male"]))
    v["ticket"] *= C.TICKET_MULTIPLIER[v["business_type"]]
    v["seasonal"] = own["seasonal"]
    if own["seasonal"]:
        v["peak_ratio"] = rng.uniform(*own["peak_ratio"])
        v["peak_month"] = (12 + int(rng.integers(-1, 2)) - 1) % 12 + 1
    v["supplier_dow"] = int(rng.integers(0, 7))
    v["bill_dom"] = int(rng.integers(1, 8))
    v["till"] = str(int(rng.integers(100000, 999999)))
    v["paybill"] = str(int(rng.integers(100000, 999999)))
    v["agent"] = str(int(rng.integers(100000, 999999)))
    return v


def season(v, month):
    if not v["seasonal"]:
        return 1.0
    return v["peak_ratio"] ** (0.5 * math.cos(2 * math.pi * (month - v["peak_month"]) / 12))


def simulate_vendor(rng, v, end_date, out, n_days, shocks):
    """Append this vendor's statement lines to `out`. shocks: [(application day, shock)], sorted by day."""
    start = end_date - dt.timedelta(days=n_days - 1)
    vid = v["vendor_id"]
    hours = np.array(C.HOUR_WEIGHTS, dtype=float)
    hours /= hours.sum()

    state = {"bal": int(rng.integers(200, 2000)), "out": 0, "last": 0}
    day_in = []                                   # daily inflow totals
    cust_pool, supplier_ids = [], [hid("CP_", vid, "sup", k) for k in range(3)]
    biller_ids = [hid("CP_", vid, "bill", k) for k in range(2)]
    pending_bills = {}
    cv = v["weekly_cv"]
    week_factor = 1.0
    # Supplier and bill payments (assumptions.md row 8). The supplier payment is a share of the takings since the last
    # supplier day, the bill a share of the takings since the last bill day. At the start of each supplier week the
    # vendor decides whether it will pay the supplier; on the bill day, whether it pays the bill on time. A wallet that
    # cannot cover such a payment is topped up with a cash deposit at an agent first, so supplier_prob and bill_miss set
    # how regular the payments are, not the payment's size against a wallet emptied by the end-of-day withdrawal.
    sup = {"plan": False, "share": 0.0, "due": 0.0}      # this week: will the vendor pay? its share; amount so far
    bill = {"share": 0.0, "due": 0.0}                     # this bill month: its share; amount so far

    def emit(t, details, status, paid_in, withdrawn, cp, ttype):
        t = max(int(t), state["last"] + 1)
        state["last"] = t
        out.append((t, details, status, paid_in, withdrawn, state["bal"], vid, cp, ttype))

    def after_inflow(t):
        """Fuliza is repaid automatically from money that arrives."""
        if state["out"] > 0 and state["bal"] > 0:
            repay = min(state["out"], state["bal"])
            state["bal"] -= repay
            state["out"] -= repay
            emit(t + 1, "OD Loan Repayment to 232323 - M-PESA Overdraw", "Completed", 0, repay, "", "FULIZA_REPAY")

    def inflow(t, amount, details, cp, ttype):
        state["bal"] += amount
        emit(t, details, "Completed", amount, 0, cp, ttype)
        after_inflow(t)

    def pay(t, amount, ttype, normal, fuliza, cp, fee_table, fee_details):
        """A payment. Fuliza covers a shortfall with probability fuliza_prop."""
        fee = tariff(fee_table, amount) if fee_table else 0
        need = amount + fee
        if rng.random() < C.FAILED_PROB:
            emit(t, "Failed - " + normal, "Failed", 0, 0, cp, ttype)
            return False
        details = normal
        if state["bal"] < need:
            shortfall = need - state["bal"]
            draw = max(C.FULIZA_MIN_DRAW, int(math.ceil(shortfall / C.FULIZA_DRAW_ROUND)) * C.FULIZA_DRAW_ROUND)
            owed = draw + int(round(draw * C.FULIZA_ACCESS_FEE))
            if (rng.random() < v["fuliza_prop"] and draw <= C.FULIZA_MAX_DRAW
                    and state["out"] + owed <= C.FULIZA_LIMIT):
                state["bal"] += draw
                state["out"] += owed
                emit(t, "OverDraft of Credit Party", "Completed", draw, 0, "", "FULIZA_DRAW")
                details = fuliza
            else:
                if rng.random() < 0.2:
                    emit(t, "Failed - " + normal, "Failed", 0, 0, cp, ttype)
                return False
        state["bal"] -= amount
        emit(t, details, "Completed", 0, amount, cp, ttype)
        if fee:
            state["bal"] -= fee
            emit(t, fee_details, "Completed", 0, fee, "", "FEE")
        if rng.random() < C.REVERSAL_PROB:
            state["bal"] += amount
            emit(t + int(rng.integers(60, 600)), "Reversal - " + normal, "Completed", amount, 0, cp, "REVERSAL")
            after_inflow(state["last"])
        return True

    def top_up(t, need):
        """Cash deposit at an agent so the wallet covers a planned payment (Fuliza is repaid from it first)."""
        if state["bal"] < need:
            dep = int(math.ceil((need - state["bal"] + state["out"]) / 10.0)) * 10
            inflow(t, dep, f"Deposit of Funds at Agent - {v['agent']}", "", "DEPOSIT_AGENT")

    def new_or_repeat_customer():
        if cust_pool and rng.random() < v["repeat"]:
            return cust_pool[int(rng.integers(0, len(cust_pool)))]
        cp = hid("CP_", vid, "cust", len(cust_pool))
        cust_pool.append(cp)
        return cp

    for d in range(n_days):
        date = start + dt.timedelta(days=d)
        day0 = int((dt.datetime(date.year, date.month, date.day) - EAT_EPOCH).total_seconds())
        if d % 7 == 0:
            week_factor = float(rng.lognormal(-0.5 * cv * cv, cv))     # mean about 1
        s = season(v, date.month)
        trend = (1 + v["trend"]) ** (d / 30.0)
        wd = date.weekday()
        shock_mult = 1.0                           # a shock hits inflows for OBS_WINDOW_DAYS after its application
        for a_day, a_shock in shocks:
            if a_day <= d < a_day + C.OBS_WINDOW_DAYS:
                shock_mult = float(np.clip(math.exp(-C.SHOCK_INFLOW_EFFECT * a_shock), *C.SHOCK_CLIP))
        p_active = float(np.clip(v["active_days"] / 30.0 * math.sqrt(s) * math.sqrt(shock_mult), 0.05, 0.97))
        active = rng.random() < p_active
        events = []                                # (second of day, kind, amount, cp, details...)

        inflow_total = 0
        if active:
            lam = (v["tx_per_day"] * math.sqrt(s) * trend * week_factor * C.WEEKDAY_FACTOR[wd]
                   * v["inflow_scale"] * shock_mult)
            n = int(rng.poisson(max(lam, 0.0)))
            if n:
                tickets = rng.lognormal(math.log(max(v["ticket"], 20)), C.TICKET_SIGMA, n)
                secs = rng.choice(24, n, p=hours) * 3600 + rng.integers(0, 3600, n)
                is_till = rng.random(n) < v["till_share"]
                for k in range(n):
                    amt = max(C.MIN_TICKET, int(round(tickets[k])))
                    kind = "till_in" if is_till[k] else "send_in"
                    events.append((int(secs[k]), kind, amt, new_or_repeat_customer()))

        # Small mid-week restocks: as often as the vendor restocks at all (supplier_prob), as much as it uses Fuliza
        # (fuliza_prop), following its sales level (trend, season, shock). Bought at dawn, before the day's sales, so
        # a wallet emptied the night before needs Fuliza, repaid from the first sales. A growing vendor restocks with
        # Fuliza more and more often; a struggling vendor rarely restocks, and less over time (personas.md).
        level = trend * math.sqrt(s) * shock_mult
        p_restock = v["supplier_prob"] * v["fuliza_prop"] * C.SMALL_RESTOCK_PER_WEEK / 7 * level
        if active and rng.random() < min(p_restock, 1.0):
            events.append((int(rng.integers(*C.SMALL_RESTOCK_HOURS)) * 3600, "supplier",
                           int(rng.integers(*C.SMALL_RESTOCK_AMOUNT)) // 10 * 10, supplier_ids[int(rng.integers(0, 3))]))

        if rng.random() < C.DEPOSIT_PROB_PER_DAY:
            events.append((int(rng.integers(8, 17)) * 3600, "deposit", int(rng.integers(*C.DEPOSIT_AMOUNT)) // 10 * 10, ""))

        # planned supplier payment once a week: its share of the takings since the last supplier day
        if wd == v["supplier_dow"]:
            amt = int(sup["due"]) // 10 * 10
            if sup["plan"] and amt >= 50:
                events.append((int(rng.integers(7, 11)) * 3600, "supplier_planned", amt, supplier_ids[int(rng.integers(0, 3))]))
        if d == 0 or wd == v["supplier_dow"]:                     # a new supplier week starts
            # how often the vendor pays its supplier follows its sales level, like the restocks
            sup["plan"] = rng.random() < float(np.clip(v["supplier_prob"] * level, 0, 1))
            sup["share"], sup["due"] = (rng.uniform(*C.SUPPLIER_SHARE_OF_WEEK) if sup["plan"] else 0.0), 0.0
        # monthly bill: its share of the takings since the last bill day. Paid on time (topped up if needed) with
        # chance 1 - bill_miss, lower in a seasonal vendor's off-peak months (personas.md); otherwise it may be paid
        # late, without a top-up, so a late bill can still fail or need Fuliza
        if date.day == v["bill_dom"] and day_in:
            amt = int(bill["due"]) // 10 * 10
            if amt >= 100:
                if rng.random() < (1 - v["bill_miss"]) * min(1.0, s):
                    events.append((int(rng.integers(8, 15)) * 3600, "bill_planned", amt, biller_ids[int(rng.integers(0, 2))]))
                elif rng.random() < C.LATE_BILL_PROB:
                    pending_bills[d + int(rng.integers(5, 13))] = amt
        if d == 0 or date.day == v["bill_dom"]:                   # a new bill month starts
            bill["share"], bill["due"] = rng.uniform(*C.BILL_SHARE_OF_MONTH), 0.0
        if d in pending_bills:
            events.append((int(rng.integers(9, 16)) * 3600, "bill", pending_bills.pop(d), biller_ids[int(rng.integers(0, 2))]))
        # personal send money and airtime
        if rng.random() < rng.uniform(*C.PERSONAL_SEND_PER_MONTH) / 30:
            events.append((int(rng.choice(24, p=hours)) * 3600 + int(rng.integers(0, 3600)), "send_out",
                           int(rng.integers(*C.PERSONAL_SEND_AMOUNT)) // 10 * 10, hid("CP_", vid, "fam", int(rng.integers(0, 4)))))
        if rng.random() < rng.uniform(*C.AIRTIME_PER_MONTH) / 30:
            events.append((int(rng.choice(24, p=hours)) * 3600 + int(rng.integers(0, 3600)), "airtime",
                           int(rng.integers(*C.AIRTIME_AMOUNT)) // 10 * 10, ""))

        events.sort(key=lambda e: e[0])
        for sec, kind, amt, cp in events:
            t = day0 + sec
            if kind == "till_in":
                inflow(t, amt, f"Merchant Payment from {cp}", cp, "TILL_PAYMENT_IN")
                inflow_total += amt
            elif kind == "send_in":
                inflow(t, amt, f"Funds received from - {cp}", cp, "SEND_MONEY_IN")
                inflow_total += amt
            elif kind == "deposit":
                inflow(t, amt, f"Deposit of Funds at Agent - {v['agent']}", "", "DEPOSIT_AGENT")
            elif kind in ("supplier", "supplier_planned"):
                if kind == "supplier_planned":
                    top_up(t, amt)
                pay(t, amt, "BUY_GOODS_OUT", f"Merchant Payment to {v['till']} - {cp}",
                    f"Merchant Payment Fuliza M-Pesa to {v['till']} - {cp}", cp, None, "")
            elif kind in ("bill", "bill_planned"):
                if kind == "bill_planned":
                    top_up(t, amt + tariff(C.PAYBILL_FEE, amt))
                pay(t, amt, "PAYBILL_OUT", f"Pay Bill to {v['paybill']} - {cp} Acc. {vid}",
                    f"Pay Bill Fuliza M-Pesa to {v['paybill']} - {cp} Acc. {vid}", cp, C.PAYBILL_FEE, "Pay Bill Charge")
            elif kind == "send_out":
                pay(t, amt, "SEND_MONEY_OUT", f"Customer Transfer to - {cp}",
                    f"Customer Transfer Fuliza MPesa to - {cp}", cp, C.SEND_FEE, "Customer Transfer of Funds Charge")
            elif kind == "airtime":
                pay(t, amt, "AIRTIME_OUT", "Airtime Purchase", "Airtime Purchase Fuliza M-Pesa", "", None, "")

        day_in.append(inflow_total)
        sup["due"] += sup["share"] * inflow_total
        bill["due"] += bill["share"] * inflow_total

        # end of day: cash withdrawal at an agent
        if active and state["bal"] >= C.MIN_WITHDRAWAL and rng.random() < v["sweep_prob"]:
            amt = int(state["bal"] * rng.uniform(*C.SWEEP_FRACTION)) // 10 * 10
            fee = tariff(C.WITHDRAW_FEE, amt)
            if amt + fee > state["bal"]:
                amt = (state["bal"] - fee) // 10 * 10
                fee = tariff(C.WITHDRAW_FEE, amt)
            if amt >= C.MIN_WITHDRAWAL and amt + fee <= state["bal"]:
                t = day0 + int(rng.integers(19, 22)) * 3600 + int(rng.integers(0, 3600))
                state["bal"] -= amt
                emit(t, f"Customer Withdrawal At Agent - {v['agent']}", "Completed", 0, amt, "", "WITHDRAW_AGENT")
                state["bal"] -= fee
                emit(t, "Customer Withdrawal Charge", "Completed", 0, fee, "", "FEE")
    return start


def make_applications(rng, v, start, app_counter):
    """Application dates, amounts, terms and hidden shocks, all inside the vendor's history."""
    n_days = v["history_days"]
    lo_day = min(C.APPLICATION_MIN_DAY, n_days - 1)
    k = 1 if v["persona"] == "new" else int(rng.integers(1, 5))
    days = []
    for _ in range(40):
        if len(days) == k:
            break
        d = int(rng.uniform(*C.APPLICATION_FRACTION) * n_days) if not days else int(rng.uniform(lo_day, n_days - 1))
        d = int(np.clip(d, lo_day, n_days - 1))
        if all(abs(d - x) >= 45 for x in days):
            days.append(d)
    apps = []
    for d in sorted(days):
        app_counter[0] += 1
        amount = float(np.clip(rng.lognormal(math.log(C.LOAN_MEDIAN), C.LOAN_SIGMA), C.LOAN_MIN, C.LOAN_MAX))
        amount = round(amount / 100) * 100
        apps.append({
            "application_id": f"A{app_counter[0]:06d}", "vendor_id": v["vendor_id"],
            "application_date": (start + dt.timedelta(days=d)).date().isoformat(),
            "requested_amount": amount, "requested_term_days": int(rng.integers(C.TERM_RANGE[0], C.TERM_RANGE[1] + 1)),
            "hidden_shock": round(float(rng.normal()), 4)})
    return apps


def receipt_numbers(n, offset=0):
    """Unique 10-character base-36 codes that look like M-Pesa receipts. `offset` keeps them unique across chunks."""
    mod = 36 ** 10
    x = (np.arange(offset, offset + n, dtype=np.uint64) * np.uint64(2147483647) + np.uint64(987654321987)) % np.uint64(mod)
    chars = np.array(list("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
    digits = []
    for _ in range(10):
        digits.append(chars[(x % np.uint64(36)).astype(np.int64)])
        x = x // np.uint64(36)
    return ["".join(t) for t in zip(*digits[::-1])]


def save(df, out_dir, name):
    path = os.path.join(out_dir, name)
    try:
        df.to_parquet(path + ".parquet", index=False)
        return path + ".parquet"
    except Exception:
        df.to_csv(path + ".csv", index=False)
        return path + ".csv"


TX_COLUMNS = ["receipt_no", "completion_time", "details", "transaction_status", "paid_in", "withdrawn", "balance",
              "vendor_id", "counterparty_id", "txn_type_true"]


def to_frame(rows, offset):
    """Turn a list of raw statement lines (whole vendors only) into the transactions table."""
    tx = pd.DataFrame(rows, columns=["t", "details", "transaction_status", "paid_in", "withdrawn", "balance",
                                     "vendor_id", "counterparty_id", "txn_type_true"])
    tx["completion_time"] = pd.to_datetime(tx.pop("t"), unit="s")
    tx = tx.sort_values(["vendor_id", "completion_time"], kind="stable").reset_index(drop=True)
    tx.insert(0, "receipt_no", receipt_numbers(len(tx), offset))
    for c in ("paid_in", "withdrawn", "balance"):
        tx[c] = tx[c].astype(float)
    return tx[TX_COLUMNS]


class TxWriter:
    """Write transactions in chunks of whole vendors, one parquet row group each (csv fallback without pyarrow)."""

    def __init__(self, out_dir):
        self.out_dir, self.n, self.frames, self.writer = out_dir, 0, [], None
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
            self.pa, self.pq = pa, pq
        except ImportError:
            self.pa = self.pq = None

    def add(self, rows):
        if not rows:
            return
        df = to_frame(rows, self.n)
        self.n += len(df)
        if self.pq is None:
            self.frames.append(df)
            return
        table = self.pa.Table.from_pandas(df, preserve_index=False)
        if self.writer is None:
            self.writer = self.pq.ParquetWriter(os.path.join(self.out_dir, "transactions.parquet"), table.schema)
        self.writer.write_table(table, row_group_size=max(len(table), 1))

    def close(self):
        if self.writer is not None:
            self.writer.close()
            return os.path.join(self.out_dir, "transactions.parquet")
        return save(pd.concat(self.frames, ignore_index=True), self.out_dir, "transactions")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-vendors", type=int, default=C.N_VENDORS)
    ap.add_argument("--seed", type=int, default=C.SEED)
    ap.add_argument("--max-months", type=int, default=0, help="cap statement length (for quick checks)")
    ap.add_argument("--out-dir", default=C.OUT_DIR)
    a = ap.parse_args()

    rng = np.random.default_rng(a.seed)
    end_date = dt.datetime.strptime(C.END_DATE, "%Y-%m-%d")
    os.makedirs(a.out_dir, exist_ok=True)
    rows, vendors, apps, counter = [], [], [], [0]
    writer = TxWriter(a.out_dir)
    for i in range(1, a.n_vendors + 1):
        v = make_vendor(rng, i, a.max_months)
        total_days = v["history_days"] + C.OBS_WINDOW_DAYS        # history, then the outcome window
        start = end_date - dt.timedelta(days=total_days - 1)
        vapps = make_applications(rng, v, start, counter)
        shocks = sorted(((dt.date.fromisoformat(x["application_date"]) - start.date()).days, x["hidden_shock"]) for x in vapps)
        simulate_vendor(rng, v, end_date, rows, total_days, shocks)
        apps.extend(vapps)
        vendors.append({"vendor_id": v["vendor_id"], "business_type": v["business_type"], "gender": v["gender"],
                        "start_date": start.date().isoformat(), "months_of_history": v["months_of_history"],
                        "statement_days": total_days, "persona": v["persona"], "latent_risk": round(v["latent_risk"], 4)})
        if i % C.CHUNK_VENDORS == 0 or i == a.n_vendors:
            writer.add(rows)
            rows.clear()
            print(f"  {i}/{a.n_vendors} vendors, {writer.n:,} lines", flush=True)

    p1 = writer.close()
    p2 = save(pd.DataFrame(vendors), a.out_dir, "vendors")
    p3 = save(pd.DataFrame(apps), a.out_dir, "loan_applications")
    print(f"wrote {writer.n:,} transaction lines, {len(vendors)} vendors, {len(apps)} applications")
    print("outcomes are made later: python src/scorecard.py (after clean.py and features.py)")
    print(" ", p1, p2, p3, sep="\n  ")


if __name__ == "__main__":
    main()