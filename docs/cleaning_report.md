# Cleaning report

10,915,450 lines, 1000 vendors

## Rows per txn_type

| txn_type | rows | share |
|---|---|---|
| SEND_MONEY_IN | 6,294,489 | 57.7% |
| TILL_PAYMENT_IN | 3,854,317 | 35.3% |
| FEE | 244,329 | 2.2% |
| WITHDRAW_AGENT | 200,095 | 1.8% |
| AIRTIME_OUT | 89,950 | 0.8% |
| BUY_GOODS_OUT | 76,866 | 0.7% |
| FULIZA_REPAY | 67,669 | 0.6% |
| SEND_MONEY_OUT | 41,177 | 0.4% |
| FULIZA_DRAW | 27,210 | 0.2% |
| DEPOSIT_AGENT | 11,204 | 0.1% |
| PAYBILL_OUT | 7,517 | 0.1% |
| REVERSAL | 627 | 0.0% |

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
| is_failed (status Failed) | 14,945 |
| fuliza_funded payments | 27,210 |

## Check against txn_type_true (synthetic data only)

Agreement: 100.0000% of 10,915,450 rows
