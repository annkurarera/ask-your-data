# loan_portfolio — Data Dictionary

Synthetic Indian retail loan book for the Text-to-SQL project. **All data is synthetic** (no real customers).

- **Rows:** 10,00,000 loans · **Customers:** ~5.6 lakh (some have multiple loans) · **Columns:** 33
- **Snapshot date (as-of):** 2026-09-30 · **Disbursements:** Apr 2020 – Sep 2026
- **Currency:** INR (whole rupees) · **Regenerate:** `python generate_loan_portfolio.py` (seed 42, same output every time)

## Columns

| Column | Type | Description |
|---|---|---|
| loan_id | text | Unique loan ID (`LN00000001`…), ordered by disbursement date |
| customer_id | text | Customer ID; one customer can hold several loans |
| customer_age | int | Age at disbursement (18–68) |
| gender | text | Male / Female |
| occupation | text | Salaried, Self-Employed, Business Owner, Professional |
| annual_income | int | Annual income (₹) |
| cibil_score | int | Credit score 300–900. **NULL = new-to-credit (NTC)**, ~5% |
| branch_code | text | Branch (`BR0001`…, 276 branches) |
| city / state / region | text | Branch location. Region: North, South, East, West, Central, North-East |
| city_tier | text | Tier 1 / Tier 2 / Tier 3 |
| product_type | text | Home Loan, Loan Against Property, Auto Loan, Personal Loan, Business Loan, Gold Loan, Education Loan |
| is_secured | bool | TRUE if backed by collateral |
| channel | text | Sourcing channel: Branch, Digital, DSA (direct selling agent), Partner (fintech / co-lending) |
| disbursement_date | date | Date the loan was disbursed |
| sanctioned_amount | int | Approved amount (₹) |
| disbursed_amount | int | Amount actually paid out (₹). Lower than sanctioned for ~15% of home loans (under-construction) |
| interest_rate | numeric | Annual rate (%) |
| tenure_months | int | Loan tenure in months |
| emi_amount | int | Monthly instalment (₹) |
| collateral_type | text | Residential Property, Commercial/Residential Property, Vehicle, Gold Jewellery, or `None` |
| collateral_value | int | Collateral value (₹); NULL if unsecured |
| ltv_ratio | numeric | Loan-to-value = disbursed / collateral value; NULL if unsecured |
| emis_paid | int | EMIs paid so far |
| outstanding_principal | numeric | Principal still owed (₹); 0 for closed loans |
| overdue_amount | numeric | Amount past due (₹) |
| dpd | int | Days past due (0 = current) |
| asset_classification | text | RBI-style bucket — see below; NULL for closed loans |
| loan_status | text | Active, Closed, NPA, Written Off |
| npa_date | date | Date the loan turned NPA (dpd crossed 90); NULL otherwise |
| closure_date | date | Date closed (maturity or prepayment); NULL if open |
| last_payment_date | date | Most recent payment; NULL if no EMI paid yet |

## Asset classification (RBI-style)

| Bucket | DPD |
|---|---|
| Standard | 0 |
| SMA-0 | 1–30 |
| SMA-1 | 31–60 |
| SMA-2 | 61–90 |
| Substandard | 91–455 (NPA ≤ 12 months) |
| Doubtful | 456–1185 |
| Loss | > 1185, or written off |

## Business metrics (for the semantic layer)

| Metric | Definition |
|---|---|
| Loan book / AUM | `SUM(outstanding_principal)` where `loan_status IN ('Active','NPA')` |
| Gross NPA % | NPA outstanding (`dpd > 90`) ÷ total book outstanding × 100 |
| SMA book | Outstanding where `asset_classification IN ('SMA-0','SMA-1','SMA-2')` |
| Disbursement volume | `SUM(disbursed_amount)` by period |
| Average ticket size | `AVG(disbursed_amount)` |
| FOIR | `emi_amount * 12 / annual_income` |
| Prepayment rate | Closed before maturity: `closure_date < disbursement_date + tenure_months` |
| Vintage | Year or quarter of `disbursement_date` |
| Indian financial year | Apr–Mar (FY26 = 1 Apr 2025 – 31 Mar 2026) |

## Planted patterns (use these to verify golden-set answers)

Overall Gross NPA ≈ **1.3%**. Expected directions:

1. **Products:** Business Loan (~5.9%) and Personal Loan (~4.0%) have the highest GNPA; Home Loan the lowest (~0.7%).
2. **Credit score:** GNPA falls sharply with CIBIL — ~13% below 600 vs under 0.1% above 800. NTC (NULL score) borrowers are riskier than average.
3. **Problem branches:** all branches in **Gaya, Muzaffarpur, Bareilly, Aligarh, Meerut**, plus one branch each in **Patna** and **Kanpur**, have ~2.5× the normal NPA rate.
4. **Tier:** Tier 3 cities are riskier than Tier 1 and 2.
5. **Channel:** DSA-sourced loans have the highest delinquency; Digital share grows from ~11% (2020) to ~32% (2026).
6. **COVID vintage:** loans disbursed Apr 2020 – Mar 2021 perform worst; Apr–May 2020 and May 2021 disbursements are sharply lower.
7. **Seasonality:** disbursements peak in **March** (year-end) and **Oct–Nov** (festive season); overall ~17% annual growth.
8. **Rates:** loans disbursed from Jun 2022 carry higher rates (hike cycle), easing from Mar 2025; lower CIBIL → higher rate.
9. **Over-leverage:** high-FOIR loans default more.
10. **Gold loans:** short tenure, mostly sourced at branches, most already closed.
