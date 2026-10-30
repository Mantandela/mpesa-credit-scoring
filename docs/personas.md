# Vendor Personas

Project: AI-Based Credit Scoring System for Informal Sector Vendors Using Mobile Money Transaction Data (Case: M-Pesa)

Status: v0.2 (draft). Changes from v0.1: small mobile loan product, new default definition (about 16.6%), `latent_risk` ranges rescaled, till/send-money mix for all personas, smaller Fuliza amounts. **Most numbers below are still starting values, not sourced figures.** Record the source or "Author's assumption" for each in `assumptions.md` before generating the final dataset.

## How personas are used

- A persona is a recipe for how a vendor's M-Pesa activity looks. Each vendor is assigned one persona.
- For each vendor, the generator draws its own parameters from the persona's ranges. No two vendors in a persona are identical.
- About 10% of vendors take some parameters from an adjacent persona, so personas overlap and the boundaries are blurry, as in real life.
- `persona` and `latent_risk` are used only by the generator. They are never model inputs.

## Persona table (amounts in KES)

| Parameter | 1. Stable daily trader | 2. Growing vendor | 3. Seasonal trader | 4. New vendor | 5. Struggling vendor |
|---|---|---|---|---|---|
| Share of vendors | 30% | 15% | 20% | 15% | 20% |
| Description | Steady daily sales, regular supplier and bill payments | Rising sales, restocks with Fuliza and repays quickly | Strong in peak months, very slow off-peak | Short history, building a customer base | Falling sales, tight cash, late or partial repayments |
| Months of history | 12 to 24 | 12 to 24 | 12 to 24 | 1 to 3 | 6 to 24 |
| Incoming transactions per active day | 20 to 40 | 10 to 25 | 5 to 35 (varies by season) | 5 to 20 | 3 to 12 |
| Median sale (ticket) size | 100 to 200 | 120 to 250 | 100 to 300 | 80 to 200 | 50 to 150 |
| Active days per month | 24 to 28 | 22 to 27 | 10 to 26 (varies by season) | 15 to 25 | 8 to 20 |
| Monthly inflow trend | flat (-1% to +2%) | +3% to +6% | seasonal swing (peak 2x to 3x off-peak) | +5% to +15% from a low base | -3% to -8% |
| Weekly inflow variation (coefficient of variation) | 0.10 to 0.25 | 0.15 to 0.30 | 0.50 to 0.90 | 0.30 to 0.60 | 0.40 to 0.80 |
| Repeat-customer share | 50% to 70% | 35% to 55% | 30% to 50% | 15% to 35% | 10% to 30% |
| Till payments vs. send-money (inflows) | mix, about 40% till | mix, about 40% till | mix, about 35% till | mostly send-money, about 20% till | mostly send-money, about 25% till |
| Days with near-zero balance per month | 0 to 2 | 1 to 4 | 2 to 10 (off-peak) | 3 to 8 | 8 to 20 |
| Fuliza use (draws of KES 50 to 1,000, typical about KES 220) | rare | occasional, repaid in 1 to 3 days | spikes in off-peak, slower repayment | occasional | frequent, slow or partial repayment |
| Bill payments (rent, electricity) | regular, on time | regular | irregular in off-peak | few or none | often missed or late |
| Supplier payments (buy goods) | regular, weekly | regular, growing | follow the season | small and irregular | rare, shrinking |
| `latent_risk` range | 0.02 to 0.09 | 0.05 to 0.14 | 0.12 to 0.26 | 0.12 to 0.23 | 0.24 to 0.40 |

## Business types and gender

- `business_type` is assigned at random from `fresh_produce`, `food_stall`, `retail_kiosk`, `services`, `second_hand_clothes`. It can shift the ticket size and the season pattern, but it does not change `latent_risk`.
- `gender` is assigned independently of persona and `latent_risk`, so any disparity found in the fairness check comes from the model or the features, not from a bias built into the data. If you want to test whether the fairness check can detect bias, add a clearly labelled variant of the dataset with a controlled bias.

## Loan product

The system simulates **small mobile loans** (Fuliza and M-Shwari style), because that is the credit informal vendors actually use.

- `requested_amount`: drawn from a log-normal distribution with median about KES 5,000, clipped to KES 500 to 10,000. Anchor: average mobile bank loan of KES 6,171.2 (FinAccess 2024); the average Fuliza draw (about KES 218) is much smaller, so Fuliza draws inside `transactions` stay in the hundreds of shillings.
- `requested_term_days`: 7 to 30 days.
- Amount and term are drawn at random and never from risk. Both are marked as assumptions in `assumptions.md`.
- Larger loans (for example the microfinance average of KES 169,190) are out of scope.

## Linking persona to the loan outcome

The label must not be a simple function of the features, or the model will only rediscover the generator's rules.

1. Draw `latent_risk` for each vendor from the persona's range.
2. Create the vendor's transactions. Features reflect `latent_risk` only partly, because of the overlap and noise above.
3. Create a loan application with `requested_amount` and `requested_term_days` as described under Loan product.
4. Set the default probability to `latent_risk + shock`, with `shock` drawn from a normal distribution (mean 0, standard deviation 0.10) and clipped to 0 to 1. The shock stands for events that the transactions cannot predict (illness, theft, a market closing).
5. Draw `defaulted` as 1 with that probability, otherwise 0. Set `days_past_due` accordingly.

## Label definition

- **`defaulted` (main target):** 1 if the loan was not repaid at all (serious non-payment). Anchor: 16.6% of borrowers "completely defaulted" in FinAccess 2024 (CBK et al., 2024; all borrowers, not only micro and small enterprises).
- **`late_or_default` (stress scenario):** 1 if `defaulted` is 1 or `days_past_due` is at least 1. Anchor: 61% of micro and small enterprise borrowers said they had defaulted or paid late (FSD Kenya, 2023; self-reported). Use it only in a separate sensitivity run, with the lateness parameter raised until the rate is near 61%.
- With the rescaled `latent_risk` ranges, a quick simulation gives an overall `defaulted` rate of about 17% (stable 7%, growing 10%, seasonal 19%, new 18%, struggling 34%). Check the real rate after the first run and nudge the ranges if it falls outside 14% to 19%.

## Checks after the first run (50 vendors, 6 months)

1. Balances add up on every row.
2. Each persona looks different on a few plots: weekly inflow, active days, and number of days near zero balance.
3. Persona overlap shows up: some vendors from different personas look alike.
4. The default rate per persona follows the order stable < growing < seasonal and new < struggling, but with visible exceptions.
5. The overall `defaulted` rate is between 14% and 19%, and all Fuliza draws are under KES 1,000.