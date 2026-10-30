# Assumptions and Sources

Project: AI-Based Credit Scoring System for Informal Sector Vendors Using Mobile Money Transaction Data (Case: M-Pesa)

Status: v0.2. Rows 1 to 12 now hold the sources you found, tidied into one value per row. Rows marked **TODO** need a full citation (title, publisher, date, URL, page). Rows marked "Author's assumption" have no source yet. Match tags: exact, partial or context.

## 1. Parameter sources

| # | Parameter | Value used | Source (title, publisher, year, link, page) | Match | Notes |
|---|---|---|---|---|---|
| 1 | Typical sale size (ticket) | KES 50 to 300 by persona (see `personas.md`) | Author's assumption | n/a | No source found yet. Check the KNBS MSME survey and CBK payment statistics. Reasonable for low-value street and kiosk sales. |
| 2 | Transactions per active day | 3 to 40 by persona | Author's assumption | n/a | No source found yet. Later check against Safaricom reports. |
| 3 | Share of till vs. send-money inflows | Mixed in all personas. Till share about 20% to 40%, the rest send money | FSD Kenya. (2023, September 5). *How is finance supporting Kenyan businesses? Results from the 2023 FinAccess MSE tracker survey*. https://www.fsdkenya.org/finaccess/how-is-finance-supporting-kenyan-businesses-results-from-the-2023-finaccess-mse-tracker-survey/ | partial | 76% of MSEs said customers pay by send money (68% before). Till use "also grew" but no figure is given, and 76% is the share of businesses, not the share of value. The exact till/send-money split is an assumption. |
| 4 | Active days per month | 8 to 28 by persona | Author's assumption | n/a | Check the KNBS MSME survey (days or hours of operation). |
| 5 | Seasonality (peak vs. off-peak ratio) | Peak 2x to 3x off-peak for the seasonal persona | Author's assumption | n/a | No source found yet. |
| 6 | Repeat-customer share | 10% to 70% by persona | Author's assumption | n/a | No source found yet. |
| 7a | Mobile loan use among MSEs | 44% of MSEs had outstanding mobile loans (June 2023), down from 57% (October 2022) | FSD Kenya (2023), same page as row 3 | partial | Includes M-Shwari, KCB M-Pesa and Fuliza together. Gives no frequency or repayment speed. |
| 7b | Fuliza usage, adult population | 18.4% usage ("held steady") | Central Bank of Kenya, Kenya National Bureau of Statistics, & FSD Kenya. (2024). *2024 FinAccess household survey: Main report*. https://www.centralbank.go.ke/wp-content/uploads/2024/12/2024-FINACCESS-HOUSEHOLD-SURVEY-MAIN-REPORT.pdf. Section 3.1 (pp. 26 to 27, **TODO confirm page**) | exact for the adult population | Adults, not only vendors. Cite the Section 3.1 sentence. I could not confirm the 18.4 / 15.4 / 66.2 figures from Figure 2.3, so they are left out until you check the chart. |
| 7c | Fuliza repayment speed | Repaid in 1 to 3 days for the growing persona, slower for others | Author's assumption | n/a | No source found. |
| 8 | Bill payment regularity | Regular for stable and growing personas, irregular or missed for the others | Author's assumption. Context only: *Banking sub-sector report: Lessons from FinAccess surveys* (CBK, November 2025), p. 22, Section 3.6. **TODO full citation and URL check** | context | Reports 68.0% use mobile money for monthly expenses and 27.7% for daily expenses. Says nothing about bill regularity. |
| 9a | Loan size requested | Median about KES 5,000, range 500 to 10,000. Term 7 to 30 days | Banking sub-sector report (CBK, November 2025), p. 27, Figure 26: average mobile banking loan KES 6,171.2. **TODO full citation** | partial | Average amount lent, not requested amount. The range and the term are Author's assumptions. Bank (KES 340,500.7) and microfinance bank (KES 169,190.0) averages are out of scope. |
| 9b | Fuliza draw size | KES 50 to 1,000, typical about KES 218 | Safaricom Fuliza customer news article, financial year ended March 2026, paragraph 4. **TODO title, publisher, date, URL** | partial | Average overdraft draw, down from KES 241. Small and frequent draws. |
| 10a | Default rate: main target | About 16.6% of borrowers (`defaulted`) | Central Bank of Kenya et al. (2024), *2024 FinAccess household survey: Main report*, Executive Summary item 9 (your note says p. vii; I read p. ix, **TODO check which numbering you used**) | partial | "Did not pay at all." Up from 10.7% in 2021. Covers all borrowers, not only informal sector vendors. No informal-sector-only rate was found. |
| 10b | Default rate: stress scenario | About 61% (`late_or_default`) | FSD Kenya (2023), same page as row 3 | partial | MSE borrowers who "defaulted or paid late", self-reported, up from 43% in October 2022. No sample size is given. The Hustler Fund figure (49%) can be kept as a note. |

## 2. Modelling assumptions

| Assumption | Why it is reasonable | Effect if wrong |
|---|---|---|
| The synthetic data is a stand-in for real M-Pesa statements | Real statements cannot be shared because of privacy rules | Results show that the pipeline works, not how accurate it would be on real vendors |
| The default label comes from `latent_risk` plus random noise | No real repayment labels are available | Model performance on synthetic data may be higher than on real data |
| `defaulted` means "did not pay at all" and targets about 16.6% | It is the best-sourced definition (FinAccess 2024) | Other definitions give very different rates, so the 61% "late or default" version is run as a sensitivity test |
| The system simulates small mobile loans (KES 500 to 10,000, 7 to 30 days) | Informal vendors mainly use small mobile loans such as Fuliza and M-Shwari | Results do not carry over to larger business loans |
| Till and send-money inflows are mixed in all personas | 76% of MSEs say customers pay by send money | The exact split is unsourced, so features based on the till share could be misleading |
| Cash sales are not visible | They never pass through M-Pesa | Vendors who mostly sell in cash look smaller than they are |
| Vendors have one M-Pesa account | Simplifies the generator | Real vendors may also use personal and other mobile-money accounts |

## 3. Known limitations

- No source gives one agreed definition of default. The 16.6% and 61% figures use different definitions and different populations, so the label is a constructed one.
- No informal-sector-only default rate was found. The 16.6% covers all borrowers.
- Ticket size, transactions per day, active days, seasonality, repeat-customer share, bill regularity and repayment speed are assumptions.
- Fuliza and mobile loan figures mix MSE data (2023) and adult-population data (2024).

Add each new limitation here as you find it, and copy the final list into the limitations section of your report.

## 4. Public datasets

For each dataset in `data/raw/`, note the source URL, download date, licence, and what it is used for (see `data_dictionary.md`, section 5).