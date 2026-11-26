# Cleaning report

10,639,737 lines, 1000 vendors

## Rows per txn_type

| txn_type | rows | share |
|---|---|---|
| SEND_MONEY_IN | 6,126,026 | 57.6% |
| TILL_PAYMENT_IN | 3,705,057 | 34.8% |
| FEE | 251,546 | 2.4% |
| WITHDRAW_AGENT | 199,727 | 1.9% |
| BUY_GOODS_OUT | 92,584 | 0.9% |
| AIRTIME_OUT | 87,110 | 0.8% |
| DEPOSIT_AGENT | 61,038 | 0.6% |
| FULIZA_REPAY | 41,856 | 0.4% |
| SEND_MONEY_OUT | 39,736 | 0.4% |
| FULIZA_DRAW | 19,693 | 0.2% |
| PAYBILL_OUT | 14,704 | 0.1% |
| REVERSAL | 660 | 0.0% |

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
| duplicate receipt_no across the whole file | 0 |
| is_failed (status Failed) | 5,898 |
| fuliza_funded payments | 19,693 |

## Check against txn_type_true (synthetic data only)

Agreement: 100.0000% of 10,639,737 rows

## See also

- [Project README](../README.md)
- [Data dictionary](data_dictionary.md)
- [Feature report](feature_report.md)
