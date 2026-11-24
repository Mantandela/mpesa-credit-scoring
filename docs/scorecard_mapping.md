# Scorecard mapping: pillars, features and directions

The cash-flow scorecard (`src/scorecard.py`, settings in `SCORECARD_PILLARS` in `src/config.py`) turns features into
the default probability that the simulated labels are drawn from (`docs/personas.md`, `docs/assumptions.md` row 10c).
Each feature gets a **direction**: +1 means a higher value raises risk, -1 means it lowers risk. A pillar score is the
average of direction x z-score (median and standard deviation of all applications, clipped at +/-3) of its features.

**Directions were fixed from lending logic before any result and are never tuned to the data.** Features whose raw
association with the simulated default is opposite to their direction are listed in `docs/scorecard_report.md` as a
limitation; the direction is not changed. Weights and directions are author's assumptions (no published cash-flow
weights exist; see row 10c).

## Pillars and weights (weight set `author`)

| Pillar | Weight | Feature | Direction | Reads as |
|---|---|---|---|---|
| A income stability | 0.30 | weekly_income_cv_90 | +1 | more week-to-week swing in income, more risk |
| | | income_active_day_share_90 | -1 | more days with sales, less risk |
| | | repeat_sender_share_90 | -1 | more repeat customers, less risk |
| | | income_count_90 | -1 | more sales, less risk |
| | | median_ticket_90 | -1 | larger typical sale, less risk |
| B cash-flow buffer | 0.25 | near_zero_day_share_90 | +1 | more days ending near zero, more risk |
| | | balance_median_eod_90 | -1 | higher typical balance, less risk |
| | | balance_min_eod_90 | -1 | higher lowest balance, less risk |
| | | net_cash_flow_ratio_90 | -1 | more income left after payments and charges, less risk |
| | | balance_trend_90 | -1 | balance rising, less risk |
| | | balance_cv_90 | +1 | more variable balance, more risk |
| | | fee_share_of_income_90 | +1 | more charges per shilling earned, more risk |
| C borrowing distress | 0.15 | fuliza_draws_90 | +1 | more Fuliza draws, more risk |
| | | fuliza_funded_share_90 | +1 | more payments funded by Fuliza, more risk |
| | | fuliza_repay_lag_median_days_90 | +1 | slower Fuliza repayment, more risk |
| | | days_since_last_fuliza_draw | -1 | longer since the last draw, less risk |
| | | failed_payment_share_90 | +1 | more failed payments, more risk |
| | | fuliza_amount_90 | +1 | more borrowed on Fuliza, more risk |
| | | reversal_count_90 | +1 | more reversals, more risk |
| D affordability | 0.10 | amount_to_avg_monthly_income_90 | +1 | larger loan against monthly income, more risk |
| | | amount_to_income_30 | +1 | larger loan against last month's income, more risk |
| | | debt_service_ratio_90 | +1 | more income going to Fuliza repayment, more risk |
| | | requested_term_days | +1 | longer term, more risk |
| E obligations | 0.10 | paybill_months_paid_90 | -1 | bills paid in more months, less risk |
| | | supplier_spend_share_90 | -1 | more income spent on suppliers (restocking), less risk |
| | | supplier_count_90 | -1 | more supplier payments, less risk |
| | | essential_outflow_share_90 | -1 | more of the spending on bills and airtime, less risk |
| | | free_cash_flow_ratio_90 | -1 | more income left after bills and airtime, less risk |
| F history and growth | 0.05 | history_days | -1 | longer history, less risk |
| | | income_trend_30_vs_prior | -1 | income rising, less risk |
| | | fuliza_draws_30 | +1 | more recent Fuliza draws, more risk |
| G network | 0.05 | unique_senders_90 | -1 | more distinct customers, less risk |
| | | till_share_90 | -1 | more till (Lipa na M-Pesa) payments, less risk |

The equal, cash-flow-heavy and FICO-like weight sets in `WEIGHT_SETS` use the same features and directions.

## Features left out of the scorecard

Both features below are still built by `src/features.py` and remain **model inputs**; only the scorecard (and so the
simulated label) does not use them.

| Feature | Why it is left out |
|---|---|
| cash_deposit_share_90 | Direction not supported. Depositing cash at an agent can mean the vendor tops up a short wallet (more risk) or that it banks cash sales into M-Pesa (more visible income, less risk). Lending logic does not fix a sign. |
| withdraw_share_of_income_90 | Direction not supported (removed in v0.7; it was in pillar B with +1). A high share of income withdrawn at agents can mean the vendor takes its takings out to spend, leaving no buffer (more risk), or that it runs a cash business and withdraws takings to pay suppliers, staff and rent in cash, which is the normal pattern for informal vendors (no extra risk). Lending logic does not fix a sign, the same reasoning as for cash_deposit_share_90. |

Note on timing, for the thesis: the removal of withdraw_share_of_income_90 was decided after the first scorecard
report, where its raw association disagreed with the +1 direction (raw AUC 0.462 against default in that run). After
the v0.7 generator fix (supplier and bill payments), the same feature agrees with +1 (raw AUC 0.612), and it stays
out: the reason for the removal is the ambiguity above, which applies whatever the data shows. No other direction was
changed. Both numbers are given only so that the order of events is on record.
