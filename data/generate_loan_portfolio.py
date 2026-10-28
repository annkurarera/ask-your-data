"""
generate_loan_portfolio.py
Synthetic BFSI retail loan portfolio (single table) for Text-to-SQL projects.

- Default 1,000,000 rows (10 lakh), reproducible with a fixed seed
- Portfolio snapshot as of 2026-09-30, loans disbursed Apr-2020 to Sep-2026
- Realistic Indian lending patterns planted (see data_dictionary.md)

Usage:
    python generate_loan_portfolio.py                     # 10 lakh rows
    python generate_loan_portfolio.py --rows 100000       # smaller sample
Requires: numpy, pandas, pyarrow (for parquet)
"""
import argparse
import numpy as np
import pandas as pd

AS_OF = np.datetime64("2026-09-30")

# (city, state, region, tier)
CITIES = [
    # Tier 1
    ("Mumbai", "Maharashtra", "West", 1), ("Delhi", "Delhi", "North", 1),
    ("Bengaluru", "Karnataka", "South", 1), ("Chennai", "Tamil Nadu", "South", 1),
    ("Hyderabad", "Telangana", "South", 1), ("Kolkata", "West Bengal", "East", 1),
    ("Pune", "Maharashtra", "West", 1), ("Ahmedabad", "Gujarat", "West", 1),
    # Tier 2
    ("Jaipur", "Rajasthan", "North", 2), ("Lucknow", "Uttar Pradesh", "North", 2),
    ("Kanpur", "Uttar Pradesh", "North", 2), ("Nagpur", "Maharashtra", "West", 2),
    ("Indore", "Madhya Pradesh", "Central", 2), ("Bhopal", "Madhya Pradesh", "Central", 2),
    ("Surat", "Gujarat", "West", 2), ("Vadodara", "Gujarat", "West", 2),
    ("Coimbatore", "Tamil Nadu", "South", 2), ("Kochi", "Kerala", "South", 2),
    ("Visakhapatnam", "Andhra Pradesh", "South", 2), ("Patna", "Bihar", "East", 2),
    ("Bhubaneswar", "Odisha", "East", 2), ("Chandigarh", "Chandigarh", "North", 2),
    ("Ludhiana", "Punjab", "North", 2), ("Nashik", "Maharashtra", "West", 2),
    ("Noida", "Uttar Pradesh", "North", 2), ("Gurugram", "Haryana", "North", 2),
    ("Ghaziabad", "Uttar Pradesh", "North", 2), ("Guwahati", "Assam", "North-East", 2),
    ("Raipur", "Chhattisgarh", "Central", 2), ("Ranchi", "Jharkhand", "East", 2),
    ("Dehradun", "Uttarakhand", "North", 2), ("Madurai", "Tamil Nadu", "South", 2),
    ("Mysuru", "Karnataka", "South", 2), ("Vijayawada", "Andhra Pradesh", "South", 2),
    # Tier 3
    ("Varanasi", "Uttar Pradesh", "North", 3), ("Agra", "Uttar Pradesh", "North", 3),
    ("Meerut", "Uttar Pradesh", "North", 3), ("Bareilly", "Uttar Pradesh", "North", 3),
    ("Aligarh", "Uttar Pradesh", "North", 3), ("Ajmer", "Rajasthan", "North", 3),
    ("Udaipur", "Rajasthan", "North", 3), ("Jodhpur", "Rajasthan", "North", 3),
    ("Kota", "Rajasthan", "North", 3), ("Gwalior", "Madhya Pradesh", "Central", 3),
    ("Jabalpur", "Madhya Pradesh", "Central", 3), ("Hubballi", "Karnataka", "South", 3),
    ("Belagavi", "Karnataka", "South", 3), ("Tirunelveli", "Tamil Nadu", "South", 3),
    ("Gaya", "Bihar", "East", 3), ("Muzaffarpur", "Bihar", "East", 3),
    ("Siliguri", "West Bengal", "East", 3), ("Durgapur", "West Bengal", "East", 3),
    ("Cuttack", "Odisha", "East", 3), ("Aurangabad", "Maharashtra", "West", 3),
    ("Kolhapur", "Maharashtra", "West", 3), ("Rajkot", "Gujarat", "West", 3),
    ("Bhavnagar", "Gujarat", "West", 3), ("Amritsar", "Punjab", "North", 3),
    ("Jalandhar", "Punjab", "North", 3),
]
CITY_WEIGHT = {1: 6.0, 2: 2.5, 3: 1.0}
BRANCHES_PER_TIER = {1: 12, 2: 5, 3: 2}
RISKY_CITIES = {"Gaya", "Muzaffarpur", "Bareilly", "Aligarh", "Meerut"}
RISKY_FIRST_BRANCH_CITIES = {"Patna", "Kanpur"}

PRODUCTS = ["Home Loan", "Loan Against Property", "Auto Loan", "Personal Loan",
            "Business Loan", "Gold Loan", "Education Loan"]
P_MIX = np.array([0.18, 0.07, 0.15, 0.28, 0.10, 0.17, 0.05])
MED_AMT = np.array([3_500_000, 2_500_000, 700_000, 300_000, 1_500_000, 150_000, 800_000])
SIG_AMT = np.array([0.55, 0.60, 0.45, 0.70, 0.65, 0.80, 0.50])
MIN_AMT = np.array([500_000, 500_000, 200_000, 50_000, 200_000, 20_000, 100_000])
MAX_AMT = np.array([30_000_000, 20_000_000, 2_500_000, 2_500_000, 10_000_000, 1_500_000, 4_000_000])
RATE_LO = np.array([8.25, 9.50, 8.75, 10.50, 11.00, 8.50, 9.00])
RATE_HI = np.array([9.90, 12.00, 11.50, 22.00, 18.00, 14.00, 12.50])
TENURES = [
    ([120, 180, 240, 300, 360], [0.10, 0.20, 0.30, 0.20, 0.20]),
    ([60, 84, 120, 180], [0.20, 0.25, 0.35, 0.20]),
    ([36, 48, 60, 72, 84], [0.15, 0.20, 0.35, 0.15, 0.15]),
    ([12, 24, 36, 48, 60], [0.15, 0.25, 0.30, 0.15, 0.15]),
    ([12, 24, 36, 48, 60], [0.15, 0.25, 0.30, 0.15, 0.15]),
    ([3, 6, 9, 12], [0.15, 0.25, 0.20, 0.40]),
    ([60, 84, 96, 120], [0.25, 0.30, 0.20, 0.25]),
]
BASE_LOGIT = np.array([-4.6, -4.0, -3.7, -2.7, -2.6, -4.6, -3.2])
ANNUAL_PREPAY = np.array([0.07, 0.06, 0.05, 0.09, 0.06, 0.0, 0.04])

OCCUPATIONS = np.array(["Salaried", "Self-Employed", "Business Owner", "Professional"])
OCC_MIX = [0.55, 0.20, 0.15, 0.10]
OCC_MED_INCOME = np.array([750_000, 900_000, 1_400_000, 1_800_000])
OCC_RISK = np.array([-0.20, 0.25, 0.30, -0.30])
TIER_INCOME_MULT = {1: 1.35, 2: 1.0, 3: 0.75}

CHANNELS = np.array(["Branch", "Digital", "DSA", "Partner"])
CHANNEL_RISK = np.array([0.0, 0.10, 0.45, 0.30])

SEASONALITY = {1: .90, 2: .95, 3: 1.35, 4: .80, 5: .85, 6: .90,
               7: .95, 8: 1.00, 9: 1.05, 10: 1.30, 11: 1.25, 12: 1.00}


def balance_after(p, r, n, k):
    """Outstanding principal after k EMIs on an amortising loan."""
    k = np.minimum(k, n)
    g_n = np.power(1 + r, n)
    g_k = np.power(1 + r, k)
    return p * (g_n - g_k) / (g_n - 1)


def generate(n_rows: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    # ---------------- branches ----------------
    br_city, br_risky = [], []
    for ci, (city, _, _, tier) in enumerate(CITIES):
        for j in range(BRANCHES_PER_TIER[tier]):
            br_city.append(ci)
            br_risky.append(city in RISKY_CITIES or (city in RISKY_FIRST_BRANCH_CITIES and j == 0))
    br_city = np.array(br_city)
    br_risky = np.array(br_risky)
    n_br = len(br_city)
    br_code = np.array([f"BR{i + 1:04d}" for i in range(n_br)])
    city_tier = np.array([c[3] for c in CITIES])
    br_w = np.array([CITY_WEIGHT[city_tier[c]] / BRANCHES_PER_TIER[city_tier[c]] for c in br_city])
    br_w = br_w / br_w.sum()

    # ---------------- customers ----------------
    n_cust = int(n_rows * 0.78)
    c_branch = rng.choice(n_br, n_cust, p=br_w)
    c_tier = city_tier[br_city[c_branch]]
    c_gender = np.where(rng.random(n_cust) < 0.31, "Female", "Male")
    c_occ = rng.choice(4, n_cust, p=OCC_MIX)
    tier_mult = np.vectorize(TIER_INCOME_MULT.get)(c_tier)
    c_income = np.exp(np.log(OCC_MED_INCOME[c_occ] * tier_mult) + 0.55 * rng.standard_normal(n_cust))
    c_income = np.clip(np.round(c_income, -3), 180_000, 20_000_000)
    c_cibil = np.clip(np.round(rng.normal(735, 65, n_cust)), 300, 900)
    c_ntc = rng.random(n_cust) < 0.05            # new-to-credit -> no score
    c_age_now = np.clip(np.round(rng.normal(38, 10, n_cust)), 21, 68)

    # ---------------- loans ----------------
    cust = rng.integers(0, n_cust, n_rows)
    branch = c_branch[cust]
    city_idx = br_city[branch]
    tier = city_tier[city_idx]
    occ = c_occ[cust]
    income = c_income[cust]
    ntc = c_ntc[cust]
    cibil = c_cibil[cust]
    cibil_eff = np.where(ntc, 700, cibil)
    prod = rng.choice(len(PRODUCTS), n_rows, p=P_MIX)

    # disbursement date: growth + festive/March seasonality + COVID dip
    months = pd.period_range("2020-04", "2026-09", freq="M")
    w = np.array([SEASONALITY[m.month] * 1.17 ** (i / 12) for i, m in enumerate(months)])
    for m, f in (("2020-04", 0.25), ("2020-05", 0.45), ("2021-05", 0.60)):
        w[months.get_loc(pd.Period(m, "M"))] *= f
    mi = rng.choice(len(months), n_rows, p=w / w.sum())
    m_start = months.start_time.values.astype("datetime64[D]")
    dim = months.days_in_month.values
    disb = m_start[mi] + (rng.random(n_rows) * dim[mi]).astype(int).astype("timedelta64[D]")
    disb = np.minimum(disb, AS_OF)
    days_elapsed = (AS_OF - disb).astype(int)
    m_elapsed = (days_elapsed / 30.44).astype(int)
    t_norm = mi / (len(months) - 1)

    # tenure
    tenure = np.zeros(n_rows, dtype=int)
    for p, (opts, pr) in enumerate(TENURES):
        idx = prod == p
        tenure[idx] = rng.choice(opts, idx.sum(), p=pr)

    # interest rate (credit-score pricing + 2022 hike cycle + 2025 cuts)
    span = RATE_HI[prod] - RATE_LO[prod]
    rate = RATE_LO[prod] + span * rng.beta(2, 5, n_rows)
    rate += np.clip((750 - cibil_eff) * 0.012, -0.5, 3.0) * span / 10 + ntc * 0.8
    rate += np.where(disb >= np.datetime64("2022-06-01"), 0.9, 0.0)
    rate += np.where(disb >= np.datetime64("2025-03-01"), -0.6, 0.0)
    rate = np.round(np.clip(rate, RATE_LO[prod], RATE_HI[prod] + 1.0), 2)
    r = rate / 1200

    # amount, capped by income (FOIR) except gold; 8% over-leveraged
    amt = np.exp(np.log(MED_AMT[prod]) + SIG_AMT[prod] * rng.standard_normal(n_rows))
    annuity = (1 - np.power(1 + r, -tenure)) / r
    cap = 0.55 * income / 12 * annuity
    apply_cap = (prod != 5) & (rng.random(n_rows) > 0.08)
    amt = np.where(apply_cap, np.minimum(amt, cap), amt)
    sanctioned = np.round(np.clip(amt, MIN_AMT[prod], MAX_AMT[prod]), -3)
    partial = (prod == 0) & (rng.random(n_rows) < 0.15)
    disbursed = np.where(partial, np.round(sanctioned * rng.uniform(0.6, 0.95, n_rows), -3), sanctioned)
    g = np.power(1 + r, tenure)
    emi = np.round(disbursed * r * g / (g - 1))
    foir = emi * 12 / income

    # channel mix shifts to digital over time; gold mostly branch
    u = rng.random(n_rows)
    pb, pdg, pdsa = 0.50 - 0.22 * t_norm, 0.10 + 0.28 * t_norm, 0.28 - 0.06 * t_norm
    chan = np.where(u < pb, 0, np.where(u < pb + pdg, 1, np.where(u < pb + pdg + pdsa, 2, 3)))
    gold = prod == 5
    ug = rng.random(n_rows)
    chan = np.where(gold, np.where(ug < 0.85, 0, np.where(ug < 0.95, 1, 3)), chan)

    # collateral
    coll_type = np.full(n_rows, "None", dtype=object)
    ltv = np.full(n_rows, np.nan)
    def set_coll(mask, name, lo, hi):
        coll_type[mask] = name
        ltv[mask] = rng.uniform(lo, hi, mask.sum())
    set_coll(prod == 0, "Residential Property", 0.55, 0.85)
    set_coll(prod == 1, "Commercial/Residential Property", 0.40, 0.65)
    set_coll(prod == 2, "Vehicle", 0.70, 0.90)
    set_coll(prod == 5, "Gold Jewellery", 0.60, 0.75)
    set_coll((prod == 4) & (rng.random(n_rows) < 0.25), "Commercial/Residential Property", 0.40, 0.60)
    set_coll((prod == 6) & (sanctioned > 750_000), "Residential Property", 0.50, 0.80)
    ltv = np.round(ltv, 4)
    coll_value = np.where(np.isnan(ltv), np.nan, np.round(disbursed / ltv, -3))
    secured = coll_type != "None"

    # ---------------- credit performance ----------------
    covid_vintage = (disb >= np.datetime64("2020-04-01")) & (disb < np.datetime64("2021-04-01"))
    age_at_disb = np.clip(c_age_now[cust] - days_elapsed / 365.25, 18, 70).round()
    edu = prod == 6
    age_at_disb = np.where(edu, rng.integers(19, 30, n_rows), age_at_disb)
    z = (BASE_LOGIT[prod] + (700 - cibil_eff) * 0.022 + ntc * 0.7
         + 2.2 * (np.clip(foir, 0, 1.2) - 0.4) + CHANNEL_RISK[chan] + OCC_RISK[occ]
         + br_risky[branch] * 1.0 + covid_vintage * 0.55 + (age_at_disb < 25) * 0.3 + (tier == 3) * 0.15)
    p_bad = 1 / (1 + np.exp(-z)) * np.minimum(1.0, (m_elapsed + 1) / 18)
    delinquent = (rng.random(n_rows) < p_bad) & (m_elapsed >= 1)
    # gold loans overdue >4 months past maturity are settled by auction -> closed
    delinquent &= ~((prod == 5) & (m_elapsed > tenure + 4))

    sev = rng.random(n_rows)
    p_npa = 0.30 + 0.15 * (cibil_eff < 650)
    dpd = np.where(sev < p_npa, 91 + rng.exponential(300, n_rows),
          np.where(sev < p_npa + 0.12, rng.integers(61, 91, n_rows),
          np.where(sev < p_npa + 0.32, rng.integers(31, 61, n_rows), rng.integers(1, 31, n_rows))))
    dpd = np.minimum(dpd, np.maximum(1, days_elapsed - 30)).astype(int)
    dpd = np.where(delinquent, dpd, 0)

    # closures: maturity or prepayment (only non-delinquent)
    years = m_elapsed / 12
    p_prepaid = 1 - np.power(1 - ANNUAL_PREPAY[prod], years)
    prepaid = (rng.random(n_rows) < p_prepaid) & (m_elapsed >= 6)
    matured = m_elapsed >= tenure
    closed = ~delinquent & (matured | prepaid)
    close_m = np.where(prepaid & ~matured,
                       6 + rng.random(n_rows) * (np.minimum(m_elapsed, tenure) - 6), tenure)
    close_m = np.where(prepaid & matured, np.minimum(close_m, tenure), close_m).astype(int)
    closure_date = disb + np.round(close_m * 30.44).astype(int).astype("timedelta64[D]")
    closure_date = np.minimum(closure_date, AS_OF)

    overdue_emis = np.ceil(dpd / 30).astype(int)
    emis_due = np.minimum(m_elapsed, tenure)
    emis_paid = np.where(closed, np.where(prepaid & ~matured, close_m, tenure),
                         np.maximum(0, emis_due - overdue_emis))
    outstanding = np.where(closed, 0.0, np.round(balance_after(disbursed, r, tenure, emis_paid), 2))
    overdue_amt = np.where(dpd > 0, np.minimum(emi * np.maximum(overdue_emis, 1), outstanding + emi), 0.0)

    # status & RBI-style asset classification
    unsecured_wo = (~secured) & (dpd > 720) & (rng.random(n_rows) < 0.6)
    status = np.where(closed, "Closed",
             np.where(unsecured_wo, "Written Off",
             np.where(dpd > 90, "NPA", "Active")))
    asset = np.select(
        [closed, unsecured_wo, dpd == 0, dpd <= 30, dpd <= 60, dpd <= 90, dpd <= 455, dpd <= 1185],
        [None, "Loss", "Standard", "SMA-0", "SMA-1", "SMA-2", "Substandard", "Doubtful"],
        default="Loss").astype(object)

    npa_date = np.where(dpd > 90, AS_OF - (dpd - 90).astype("timedelta64[D]"), np.datetime64("NaT", "D"))
    lp_cur = AS_OF - rng.integers(0, 30, n_rows).astype("timedelta64[D]")
    lp_del = AS_OF - (dpd + rng.integers(0, 10, n_rows)).astype("timedelta64[D]")
    last_pay = np.where(closed, closure_date, np.where(dpd > 0, lp_del, lp_cur))
    last_pay = np.where((~closed) & ((last_pay <= disb) | (emis_paid == 0)), np.datetime64("NaT", "D"), last_pay)

    df = pd.DataFrame({
        "customer_id": np.char.add("CUS", np.char.zfill((cust + 1).astype(str), 7)),
        "customer_age": age_at_disb.astype(int),
        "gender": c_gender[cust],
        "occupation": OCCUPATIONS[occ],
        "annual_income": income.astype(np.int64),
        "cibil_score": pd.array(np.where(ntc, np.nan, cibil), dtype="Int64"),
        "branch_code": br_code[branch],
        "city": np.array([c[0] for c in CITIES])[city_idx],
        "state": np.array([c[1] for c in CITIES])[city_idx],
        "region": np.array([c[2] for c in CITIES])[city_idx],
        "city_tier": np.char.add("Tier ", tier.astype(str)),
        "product_type": np.array(PRODUCTS)[prod],
        "is_secured": secured,
        "channel": CHANNELS[chan],
        "disbursement_date": disb,
        "sanctioned_amount": sanctioned.astype(np.int64),
        "disbursed_amount": disbursed.astype(np.int64),
        "interest_rate": rate,
        "tenure_months": tenure,
        "emi_amount": emi.astype(np.int64),
        "collateral_type": coll_type,
        "collateral_value": pd.array(coll_value, dtype="Int64"),
        "ltv_ratio": ltv,
        "emis_paid": emis_paid.astype(int),
        "outstanding_principal": outstanding,
        "overdue_amount": np.round(overdue_amt, 2),
        "dpd": dpd,
        "asset_classification": asset,
        "loan_status": status,
        "npa_date": npa_date,
        "closure_date": np.where(closed, closure_date, np.datetime64("NaT", "D")),
        "last_payment_date": last_pay,
    })
    df = df.sort_values(["disbursement_date", "customer_id"], kind="stable").reset_index(drop=True)
    df.insert(0, "loan_id", np.char.add("LN", np.char.zfill((np.arange(n_rows) + 1).astype(str), 8)))
    for c in ["disbursement_date", "npa_date", "closure_date", "last_payment_date"]:
        df[c] = pd.to_datetime(df[c]).dt.date
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=1_000_000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="loan_portfolio")
    a = ap.parse_args()
    df = generate(a.rows, a.seed)
    df.to_csv(f"{a.out}.csv", index=False)
    try:
        df.to_parquet(f"{a.out}.parquet", index=False)
    except ImportError:
        print("pyarrow not installed - skipped parquet")
    print(f"Wrote {len(df):,} rows x {df.shape[1]} columns to {a.out}.csv")
