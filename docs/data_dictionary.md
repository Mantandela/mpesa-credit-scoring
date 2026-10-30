# Data Dictionary

Project: AI-Based Credit Scoring System for Informal Sector Vendors Using Mobile Money Transaction Data (Case: M-Pesa)

Status: v0.2 (draft). Changes from v0.1: small mobile loans, new label definition, `late_or_default` column. Update this file whenever a column is added, renamed or removed.

The synthetic dataset has three tables. All identifiers are synthetic or hashed. No real personal data is used.

| Table | One row per | File (planned) |
|---|---|---|
| `transactions` | M-Pesa statement line | `data/synthetic/transactions.parquet` |
| `vendors` | vendor | `data/synthetic/vendors.parquet` |
| `loan_applications` | loan application | `data/synthetic/loan_applications.parquet` |

---

## 1. `transactions`

Mimics an M-Pesa statement. The first seven columns follow the layout of a real statement; the last three are added by the generator.

| Column | Type | Example | Description |
|---|---|---|---|
| `receipt_no` | string | `SK12AB34CD` | Unique transaction ID. Generated to look like an M-Pesa receipt (10 characters, letters and digits). |
| `completion_time` | datetime | `2026-03-14 09:42:17` | Date and time the transaction completed (East Africa Time). |
| `details` | string | `Customer Payment from CP_0412` | Free-text description, as on a real statement. Parsed in the cleaning stage to derive `txn_type`. |
| `transaction_status` | string | `Completed` | `Completed` or `Failed`. Failed rows are rare and added on purpose to test cleaning. |
| `paid_in` | float (KES) | `250.00` | Money received. 0 if the line is an outflow. |
| `withdrawn` | float (KES) | `0.00` | Money paid out, including transaction charges. 0 if the line is an inflow. |
| `balance` | float (KES) | `1840.00` | Running M-Pesa balance after the transaction. |
| `vendor_id` | string | `V00031` | Synthetic vendor ID. Links to `vendors`. |
| `counterparty_id` | string | `CP_0412` | Hashed ID of the other party (customer, supplier, biller). Real statements carry names or phone numbers inside `details`; here they are replaced by a hashed ID from the start. Blank for agent, airtime and fee lines. |
| `txn_type_true` | string | `TILL_PAYMENT_IN` | The generator's own label for the transaction type. Used only to check that the cleaning stage classifies correctly. **Never a model input.** |

### Transaction type taxonomy (`txn_type`)

The cleaning stage derives `txn_type` from `details`. It should reproduce `txn_type_true`.

| `txn_type` | Direction | Meaning |
|---|---|---|
| `TILL_PAYMENT_IN` | in | Customer pays the vendor's Lipa na M-Pesa till |
| `SEND_MONEY_IN` | in | Person-to-person money received |
| `SEND_MONEY_OUT` | out | Person-to-person money sent |
| `DEPOSIT_AGENT` | in | Cash deposited at an agent |
| `WITHDRAW_AGENT` | out | Cash withdrawn at an agent |
| `BUY_GOODS_OUT` | out | Payment to a supplier's till |
| `PAYBILL_OUT` | out | Bill payment (rent, electricity, water, school fees) |
| `AIRTIME_OUT` | out | Airtime purchase |
| `FULIZA_DRAW` | in | Fuliza overdraft used to cover a payment. Amounts are small, KES 50 to 1,000, typical about KES 220 |
| `FULIZA_REPAY` | out | Fuliza repayment |
| `FEE` | out | Transaction charge |
| `REVERSAL` | in or out | Reversal of an earlier transaction |

### Validation rules (checked in the cleaning stage)

1. Each row has either `paid_in > 0` or `withdrawn > 0`, not both.
2. `balance(t) = balance(t-1) + paid_in(t) - withdrawn(t)` for consecutive rows of the same vendor.
3. `receipt_no` is unique.
4. `completion_time` is increasing within a vendor once sorted, with no future dates.
5. `paid_in`, `withdrawn` and `balance` are never negative after Fuliza is accounted for.

---

## 2. `vendors`

| Column | Type | Example | Description |
|---|---|---|---|
| `vendor_id` | string | `V00031` | Primary key. |
| `business_type` | string | `food_stall` | One of: `fresh_produce`, `food_stall`, `retail_kiosk`, `services` (salon, repairs), `second_hand_clothes`. |
| `gender` | string | `female` | Synthetic, assigned independently of risk. Used **only** for the fairness check, never as a model feature. |
| `start_date` | date | `2025-09-01` | First date in the vendor's statement. |
| `months_of_history` | int | `13` | Length of the statement in months. |
| `persona` | string | `seasonal` | Persona used by the generator. **Generator-only. Never a model input.** |
| `latent_risk` | float (0 to 1) | `0.34` | Hidden underlying risk used to create loan outcomes. **Generator-only. Never a model input.** |

---

## 3. `loan_applications`

Supports the lender flow (the lender assesses a vendor when the vendor applies) and the affordability simulation.

| Column | Type | Example | Description |
|---|---|---|---|
| `application_id` | string | `A000212` | Primary key. |
| `vendor_id` | string | `V00031` | Links to `vendors`. |
| `application_date` | date | `2026-02-10` | Date of application. **Only transactions before this date may be used to build features for this application.** |
| `requested_amount` | float (KES) | `5000` | Amount the vendor applies for. Small mobile loan: KES 500 to 10,000, median about 5,000 (see `personas.md`). |
| `requested_term_days` | int | `30` | Requested repayment period, 7 to 30 days. |
| `defaulted` | int (0 or 1) | `0` | **Target label.** 1 if the loan was not repaid at all (serious non-payment). Generated from `latent_risk` plus random noise (see `personas.md`). Target rate about 16.6%. |
| `days_past_due` | int | `0` | Days late at the end of the observation window. 0 if repaid on time. |
| `late_or_default` | int (0 or 1) | `0` | 1 if `defaulted` is 1 or `days_past_due` is at least 1. Used only for the "late or default" stress scenario (about 61% in the stress run). **Never a model input.** |

---

## 4. Derived tables (later stages)

| Table | Created in | Description |
|---|---|---|
| `transactions_clean` | Stage 2 (cleaning) | Cleaned transactions with `txn_type`, parsed dates and validation flags |
| `features` | Stage 3 (features) | One row per loan application with rolling 30/60/90-day features, built only from data before `application_date` |
| `train`, `val`, `test` | Stage 4 (split) | Splits of the feature table with the `defaulted` label |

These will be documented here when they exist.

---

## 5. Public datasets

| Dataset | Source | Licence | Used for |
|---|---|---|---|
| (to fill in) | | | |

Record the source URL, download date and licence for each dataset in `data/raw/`.