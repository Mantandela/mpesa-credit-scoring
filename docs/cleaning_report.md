# Cleaning report

2,709,034 lines, 300 vendors

## Rows per txn_type

| txn_type | rows | share |
|---|---|---|
| SEND_MONEY_IN | 1,540,845 | 56.9% |
| TILL_PAYMENT_IN | 969,549 | 35.8% |
| FEE | 65,007 | 2.4% |
| WITHDRAW_AGENT | 52,996 | 2.0% |
| AIRTIME_OUT | 23,592 | 0.9% |
| BUY_GOODS_OUT | 20,022 | 0.7% |
| FULIZA_REPAY | 15,209 | 0.6% |
| SEND_MONEY_OUT | 11,022 | 0.4% |
| FULIZA_DRAW | 5,564 | 0.2% |
| DEPOSIT_AGENT | 3,010 | 0.1% |
| PAYBILL_OUT | 2,033 | 0.1% |
| REVERSAL | 185 | 0.0% |

## Validation flags

| flag | rows |
|---|---|
| flag_both_amounts | 0 |
| flag_balance_break | 0 |
| flag_duplicate_receipt | 0 |
| flag_time_not_increasing | 0 |
| flag_future_date | 0 |
| flag_negative | 0 |
| flag_unknown_wording | 0 |
| is_failed (status Failed) | 3,890 |
| fuliza_funded payments | 5,564 |

## Check against txn_type_true (synthetic data only)

Agreement: 100.0000% of 2,709,034 rows
