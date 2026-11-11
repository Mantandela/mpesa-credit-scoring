# Vendor Personas

Project: AI-Based Credit Scoring System for Informal Sector Vendors Using Mobile Money Transaction Data (Case: M-Pesa)

Status: v0.6 (draft; the loan-outcome sections follow v0.6, the persona table is still v0.2). Changes from v0.1: small mobile loan product, new default definition (about 16.6%), `latent_risk` ranges rescaled, till/send-money mix for all personas, smaller Fuliza amounts. **Most numbers below are still starting values, not sourced figures.** Record the source or "Author's assumption" for each in `assumptions.md` before generating the final dataset.

## How personas are used

- A persona is a recipe for how a vendor's M-Pesa activity looks. Each vendor is assigned one persona.
- For each vendor, the generator draws its own parameters from the persona's ranges. No two vendors in a persona are identical.
- About 10% of vendors take some parameters from an adjacent persona, so personas overlap and the boundaries are blurry, as in real life.
- `persona` and `latent_risk` are used only by the generator. They are never model inputs.

## Persona table (amounts in KES)

| Parameter                                                    | 1. Stable daily trader                                 | 2. Growing vendor                                     | 3. Seasonal trader                        | 4. New vendor                           | 5. Struggling vendor                                  |
| ------------------------------------------------------------ | ------------------------------------------------------ | ----------------------------------------------------- | ----------------------------------------- | --------------------------------------- | ----------------------------------------------------- |
| Share of vendors                                             | 30%                                                    | 15%                                                   | 20%                                       | 15%                                     | 20%                                                   |
| Description                                                  | Steady daily sales, regular supplier and bill payments | Rising sales, restocks with Fuliza and repays quickly | Strong in peak months, very slow off-peak | Short history, building a customer base | Falling sales, tight cash, late or partial repayments |
| Months of history                                            | 12 to 24                                               | 12 to 24                                              | 12 to 24                                  | 1 to 3                                  | 6 to 24                                               |
| Incoming transactions per active day                         | 20 to 40                                               | 10 to 25                                              | 5 to 35 (varies by season)                | 5 to 20                                 | 3 to 12                                               |
| Median sale (ticket) size                                    | 100 to 200                                             | 120 to 250                                            | 100 to 300                                | 80 to 200                               | 50 to 150                                             |
| Active days per month                                        | 24 to 28                                               | 22 to 27                                              | 10 to 26 (varies by season)               | 15 to 25                                | 8 to 20                                               |
| Monthly inflow trend                                         | flat (-1% to +2%)                                      | +3% to +6%                                            | seasonal swing (peak 2x to 3x off-peak)   | +5% to +15% from a low base             | -3% to -8%                                            |
| Weekly inflow variation (coefficient of variation)           | 0.10 to 0.25                                           | 0.15 to 0.30                                          | 0.50 to 0.90                              | 0.30 to 0.60                            | 0.40 to 0.80                                          |
| Repeat-customer share                                        | 50% to 70%                                             | 35% to 55%                                            | 30% to 50%                                | 15% to 35%                              | 10% to 30%                                            |
| Till payments vs. send-money (inflows)                       | mix, about 40% till                                    | mix, about 40% till                                   | mix, about 35% till                       | mostly send-money, about 20% till       | mostly send-money, about 25% till                     |
| Days with near-zero balance per month                        | 0 to 2                                                 | 1 to 4                                                | 2 to 10 (off-peak)                        | 3 to 8                                  | 8 to 20                                               |
| Fuliza use (draws of KES 50 to 1,000, typical about KES 220) | rare                                                   | occasional, repaid in 1 to 3 days                     | spikes in off-peak, slower repayment      | occasional                              | frequent, slow or partial repayment                   |
| Bill payments (rent, electricity)                            | regular, on time                                       | regular                                               | irregular in off-peak                     | few or none                             | often missed or late                                  |
| Supplier payments (buy goods)                                | regular, weekly                                        | regular, growing                                      | follow the season                         | small and irregular                     | rare, shrinking                                       |
| `latent_risk` range                                          | 0.02 to 0.09                                           | 0.05 to 0.14                                          | 0.12 to 0.26                              | 0.12 to 0.23                            | 0.24 to 0.40                                          |

## Business types and gender

- `business_type` is assigned at random from `fresh_produce`, `food_stall`, `retail_kiosk`, `services`, `second_hand_clothes`. It can shift the ticket size and the season pattern, but it does not change `latent_risk`.
- `gender` is assigned independently of persona and `latent_risk`, so any disparity found in the fairness check comes from the model or the features, not from a bias built into the data. If you want to test whether the fairness check can detect bias, add a clearly labelled variant of the dataset with a controlled bias.

## Loan product

The system simulates **small mobile loans** (Fuliza and M-Shwari style), because that is the credit informal vendors actually use.

- `requested_amount`: drawn from a log-normal distribution with median about KES 5,000, clipped to KES 500 to 10,000. Anchor: average mobile bank loan of KES 6,171.2 (FinAccess 2024); the average Fuliza draw (about KES 218) is much smaller, so Fuliza draws inside `transactions` stay in the hundreds of shillings.
- `requested_term_days`: 7 to 30 days.
- Amount and term are drawn at random and never from risk. Both are marked as assumptions in `assumptions.md`.
- Larger loans (for example the microfinance average of KES 169,190) are out of scope.

## Linking persona to the loan outcome (v0.6)

The label must not be a simple function of the features, or the model will only rediscover the generator's rules. From v0.6 the outcomes are made in stages, after the statements exist (details in `docs/scorecard_mapping.md`, `src/scorecard.py`, `src/outcomes.py`):

1. Draw `latent_risk` for each vendor from the persona's range. A vendor's position inside its persona's range (`z`, -1 to +1) shifts its behaviour (`RISK_*_EFFECT` in `config.py`).
2. Create the statement day by day. It runs 90 days past the last possible application date, so every application has a full observation window.
3. Create loan applications (`requested_amount`, `requested_term_days`, random, never from risk) and draw a hidden `hidden_shock` per application. After the application date the shock lowers the vendor's inflows for 90 days.
4. Clean the statements and build features from transactions before the application date only.
5. **Default:** a cash-flow scorecard turns the features into a probability `p`: `logit(p) = intercept + 1.2 x score + 0.5 x z(latent_risk) + 0.5 x hidden_shock`, with the intercept set so the average `p` is 16.6%. `defaulted` is a Bernoulli draw from `p`. The scorecard weights are author assumptions (a published cash-flow weighting does not exist).
6. **Late:** read from the transactions. A Fuliza draw made in the first 60 days after the application that is still unpaid 30 days after the draw makes the application late.
7. **Status:** `repayment_status` is 2 for default, 1 for late (not defaulted), 0 on time. Primary target: binary `defaulted`. Secondary target: the three-class status.

The scorecard score, `p`, `latent_risk` and `hidden_shock` are never model inputs. The scorecard also serves as a baseline model.

Earlier versions: v0.4 drew `defaulted` as a coin flip with probability `latent_risk + shock` (best possible AUC about 0.72, equal to persona-only). v0.5 compared `latent_risk` plus noise with a cutoff. Both are replaced by the scorecard design above.

## Label definition (v0.6)

- **`defaulted` (main target):** 1 if the loan was not repaid at all. Anchor: 16.6% of borrowers "completely defaulted" in FinAccess 2024 (CBK et al., 2024). The average of `p` is calibrated to this rate; the realised rate varies slightly because of the Bernoulli draw.
- **`repayment_status` (secondary target):** 0 on time, 1 late, 2 default. Late means a Fuliza draw unpaid 30 days after it was drawn (Fuliza's 30-day term; IFRS 9 30-days-past-due presumption). An application with no Fuliza draw in the window counts as on time.
- `late_or_default` is 1 when the status is 1 or 2. It is not comparable to the 61% FSD Kenya figure (self-reported late or default on any credit), so that figure is context only.

## Checks after the first run (50 vendors, 6 months)

1. Balances add up on every row.
2. Each persona looks different on a few plots: weekly inflow, active days, and number of days near zero balance.
3. Persona overlap shows up: some vendors from different personas look alike.
4. The default rate per persona follows the order stable < growing < seasonal and new < struggling, but with visible exceptions.
5. The overall `defaulted` rate is between 14% and 19%, and all Fuliza draws are under KES 1,000.
