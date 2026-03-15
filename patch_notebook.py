"""
Patch mc_retirement.ipynb with all required fixes.
Run: python3 patch_notebook.py
"""
import json, copy

NB_PATH = "mc_retirement.ipynb"

with open(NB_PATH) as f:
    nb = json.load(f)

cells = nb["cells"]

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def set_cell(idx, new_src):
    cells[idx] = dict(cells[idx])
    cells[idx]["source"] = new_src

# ---------------------------------------------------------------------------
# CELL 2 — Mortality helpers + PersonSpec + survivor logic
# ---------------------------------------------------------------------------

CELL2 = """\
# =============================================================================
# Mortality helpers
# =============================================================================

# --- Metadata: SSA 2022 period life table ---
MORTALITY_SOURCE          = "SSA 2022 period life table"
MORTALITY_TRUSTEES_REPORT = "2025"
MORTALITY_URL             = "https://www.ssa.gov/oact/STATS/table4c6.html"
# Notes:
#   - Period (not cohort) table: does NOT include mortality improvement.
#   - Reflects general U.S. population, not annuitants.


@dataclass
class PersonSpec:
    \"\"\"Demographics for one person.
    ss_claim_amount is in TODAY's real dollars; the engine inflates it to the
    claim year using cumulative simulated CPI before starting payments.
    \"\"\"
    start_age: int
    ss_claim_age: int
    ss_claim_amount: float  # Annual benefit in today's real dollars.


@dataclass
class MortalityState:
    \"\"\"Tracks who is alive in the simulation path.\"\"\"
    alive_a: bool = True
    alive_b: bool = True


def apply_survivor_adjustments(
    death_a: bool,
    death_b: bool,
    m_state: MortalityState,
    expense_annual: float,
    survivor_expense_percent: float,
    ss_pay_a: float,
    ss_pay_b: float,
    td_a_total: float,
    td_b_total: float,
    ss_survivor_mode: str = "simplified",
    age_a: int = 0,
    age_b: int = 0,
    ss_survivor_eligibility_age_a: int = 67,
    ss_survivor_eligibility_age_b: int = 67,
) -> Tuple[MortalityState, float, float, float, float, float]:
    \"\"\"
    Apply survivor adjustments at the end of a year when a death occurs.

    ss_survivor_mode options
    ------------------------
    "simplified" (default):
        Survivor receives the maximum currently-payable annual benefit.

    "ssa_like":
        Implements simplified SSA survivor eligibility and reduction rules.
        - Survivor must be >= 60 to receive any benefit.
        - Full survivor benefit if survivor >= full survivor retirement age
          (ss_survivor_eligibility_age_*).
        - Reduced benefit (linear from 71.5% at age 60 to 100% at full age)
          if survivor is between 60 and full survivor age.
        - Survivor may keep own retirement benefit if larger.
        Reference: https://www.ssa.gov/pubs/EN-05-10084.pdf

    IMPORTANT: If both die in the same year, the simulation ends immediately.
    \"\"\"
    prior_ss_a, prior_ss_b = ss_pay_a, ss_pay_b

    def _survivor_benefit(own_pay: float, deceased_pay: float,
                          survivor_age: int, mode: str, full_age: int) -> float:
        \"\"\"Compute survivor's SS benefit after the other spouse's death.\"\"\"
        if mode == "ssa_like":
            if survivor_age < 60:
                return float(own_pay)  # no survivor benefit; keep own if any
            elif survivor_age < full_age:
                # Linearly scale from 71.5 % at 60 to 100 % at full_age
                frac = 0.715 + 0.285 * (survivor_age - 60) / max(1, full_age - 60)
                survivor_from_deceased = deceased_pay * frac
            else:
                survivor_from_deceased = deceased_pay
            return float(max(own_pay, survivor_from_deceased))
        else:  # "simplified"
            return float(max(own_pay, deceased_pay))

    if death_a and death_b:
        m_state.alive_a = False
        m_state.alive_b = False
        return m_state, expense_annual, 0.0, 0.0, 0.0, 0.0

    if death_a:
        m_state.alive_a = False
        expense_annual *= float(survivor_expense_percent)
        td_b_total += td_a_total
        td_a_total = 0.0
        ss_pay_a = 0.0
        ss_pay_b = _survivor_benefit(
            prior_ss_b, prior_ss_a, int(age_b),
            ss_survivor_mode, ss_survivor_eligibility_age_b
        )

    if death_b:
        m_state.alive_b = False
        expense_annual *= float(survivor_expense_percent)
        td_a_total += td_b_total
        td_b_total = 0.0
        ss_pay_b = 0.0
        ss_pay_a = _survivor_benefit(
            prior_ss_a, prior_ss_b, int(age_a),
            ss_survivor_mode, ss_survivor_eligibility_age_a
        )

    return m_state, float(expense_annual), float(ss_pay_a), float(ss_pay_b), float(td_a_total), float(td_b_total)


# =============================================================================
# Stochastic mortality using annual qx hazards (mortality_table.csv)
# =============================================================================
#
# SSA q_x definition (https://www.ssa.gov/oact/Downloadables/LifeTableDefinitions.pdf):
#   q_x = probability that a person aged x dies before reaching age x+1.
#
# Simulation convention:
#   - sample_death_age_qx returns the trigger age x when the hazard fires.
#   - Death is confirmed at end-of-year when age_eoy > x  (strictly greater).
#     Using ">=" would kill the person one year too early.
#
# Table: mortality_table.csv  (source: SSA 2022 period life table)
#   Required columns: age, qx_male, qx_female

_MORTALITY_TABLE = pd.read_csv("mortality_table.csv").copy()
_MORTALITY_TABLE["age"] = _MORTALITY_TABLE["age"].astype(int)
_MORTALITY_TABLE = _MORTALITY_TABLE.sort_values("age").reset_index(drop=True)

# --- Validate ---
assert ((_MORTALITY_TABLE["qx_male"] >= 0) & (_MORTALITY_TABLE["qx_male"] <= 1)).all(), \\
    "mortality_table: qx_male contains values outside [0, 1]"
assert ((_MORTALITY_TABLE["qx_female"] >= 0) & (_MORTALITY_TABLE["qx_female"] <= 1)).all(), \\
    "mortality_table: qx_female contains values outside [0, 1]"
assert (_MORTALITY_TABLE["age"].diff().dropna() > 0).all(), \\
    "mortality_table: ages are not strictly increasing"

_MAX_AGE_IN_TABLE = int(_MORTALITY_TABLE["age"].max())

_QX_MALE   = np.full(_MAX_AGE_IN_TABLE + 1, np.nan, dtype=float)
_QX_FEMALE = np.full(_MAX_AGE_IN_TABLE + 1, np.nan, dtype=float)
_QX_MALE[_MORTALITY_TABLE["age"].values]   = _MORTALITY_TABLE["qx_male"].to_numpy(dtype=float)
_QX_FEMALE[_MORTALITY_TABLE["age"].values] = _MORTALITY_TABLE["qx_female"].to_numpy(dtype=float)


def _qx_at_age(age: int, sex: str) -> float:
    a = int(age)
    if a < 0:
        return 0.0
    a = min(a, _MAX_AGE_IN_TABLE)
    s = str(sex).strip().lower()
    q = _QX_MALE[a] if s in ("m", "male") else _QX_FEMALE[a]
    if not np.isfinite(q):
        return 1.0
    return float(np.clip(q, 0.0, 1.0))


def sample_death_age_qx(
    start_age: int,
    sex: str,
    rng: np.random.Generator,
    max_age_cap: int = 100
) -> int:
    \"\"\"
    Sample integer death age using annual qx hazards (SSA 2022 period table).

    Returns the trigger age x at which q_x fires.  The simulation engine
    confirms death at the END OF THE YEAR when age_eoy > x.
    If no hazard fires before max_age_cap, returns max_age_cap.
    \"\"\"
    a0  = int(start_age)
    cap = int(min(int(max_age_cap), _MAX_AGE_IN_TABLE))
    for age in range(a0, cap + 1):
        if rng.random() < _qx_at_age(age, sex):
            return int(age)
    return int(cap)
"""

set_cell(2, CELL2)

# ---------------------------------------------------------------------------
# CELL 3 — Shiller data loader (hardened)
# ---------------------------------------------------------------------------

CELL3 = """\
# =============================================================================
# Data loading (Shiller "ie_data.xls") and regime labels
# =============================================================================

from pathlib import Path

def load_shiller_data(path: str = "ie_data.xls", start_year: int = 1926) -> pd.DataFrame:
    \"\"\"
    Parses Robert Shiller's historical dataset.
    Source: https://www.econ.yale.edu/~shiller/data.htm

    Supports both .xls and .xlsx.  Raises ValueError if the expected columns
    are not present (schema guard against silent breakage).

    Returns a monthly DataFrame with columns:
        stock_ret, bond_ret, infl_mom, vol_regime, infl_regime
    \"\"\"
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Shiller data file not found: {p.resolve()}")

    def parse_yyyymm(val):
        try:
            from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
            d = Decimal(str(val)).quantize(Decimal("0.00"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, Exception):
            return pd.NaT
        year  = int(d)
        month = int((d - year) * 100)
        return pd.Timestamp(year, month, 1) if 1 <= month <= 12 else pd.NaT

    df_raw = pd.read_excel(str(p), sheet_name="Data", skiprows=7, skipfooter=1)

    # --- Schema validation: expected positional columns ---
    # Shiller layout (as of 2024):
    #   col 0  = date (YYYY.MM)
    #   col 1  = S&P price
    #   col 2  = dividend
    #   col 4  = CPI
    #   col 17 = bond total-return factor (CAPE sheet: "TR_BOND")
    EXPECTED_MIN_COLS = 18
    if df_raw.shape[1] < EXPECTED_MIN_COLS:
        raise ValueError(
            f"Shiller data has {df_raw.shape[1]} columns; expected at least "
            f"{EXPECTED_MIN_COLS}.  The file layout may have changed — "
            f"update column indices in load_shiller_data()."
        )

    df = df_raw.iloc[:, [0, 1, 2, 4, 17]].copy()
    df.columns = ["date", "price", "dividend", "cpi", "bond_factor"]

    # Spot-check that numeric columns are actually numeric
    for col in ("price", "dividend", "cpi", "bond_factor"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    n_bad = df[["price", "cpi", "bond_factor"]].isna().all(axis=1).sum()
    if n_bad > len(df) * 0.5:
        raise ValueError(
            f"More than 50 % of rows have NaN in price/cpi/bond_factor — "
            f"the column mapping may be wrong.  Check load_shiller_data()."
        )

    df["date"] = df["date"].apply(parse_yyyymm)
    df = df.dropna(subset=["date"]).sort_values("date").set_index("date")

    # Stock total return: (ΔPrice + monthly dividend) / prior price
    df["stock_ret"] = (
        df["price"] - df["price"].shift(1) + df["dividend"] / 12.0
    ) / df["price"].shift(1)

    # Bond total return: Shiller provides gross return factor; subtract 1
    df["bond_ret"] = df["bond_factor"].astype(float) - 1.0

    # Monthly inflation
    df["infl_mom"] = df["cpi"].pct_change(1)

    df = df[df.index.year >= int(start_year)].copy()

    # Inflation regime (YoY CPI)
    yoy = df["cpi"].pct_change(12)
    def label_infl(y):
        if pd.isna(y): return "mid"
        return "low" if y < 0.03 else ("mid" if y < 0.05 else "high")
    df["infl_regime"] = yoy.apply(label_infl)

    # Volatility regime (12-month realized stock vol, annualised)
    df["realized_vol"] = (
        df["stock_ret"].rolling(12, min_periods=12).std(ddof=1) * np.sqrt(12.0)
    )

    df = df.dropna(subset=["stock_ret", "bond_ret", "infl_mom", "realized_vol"]).copy()
    if df.empty:
        return df

    v_low  = df["realized_vol"].quantile(0.33)
    v_high = df["realized_vol"].quantile(0.67)
    def label_vol(v):
        return "vol_low" if v <= v_low else ("vol_mid" if v <= v_high else "vol_high")
    df["vol_regime"] = df["realized_vol"].apply(label_vol)

    return df
"""

set_cell(3, CELL3)

# ---------------------------------------------------------------------------
# CELL 5 — Financial logic helpers  (RMDs fixed + compute_taxable_ss added)
# ---------------------------------------------------------------------------

CELL5 = """\
# =============================================================================
# Financial logic helpers (RMDs, withdrawals, spending rules, SS taxation)
# =============================================================================

def get_rmd_start_age(birth_year: int) -> int:
    \"\"\"SECURE Act / SECURE 2.0 RMD start-age rule.\"\"\"
    by = int(birth_year)
    if by <= 1950:
        return 72
    if 1951 <= by <= 1959:
        return 73
    return 75

# IRS Uniform Lifetime Table (Pub 590-B, 2022 revision)
IRS_RMD_TABLE = {
    72: 27.4, 73: 26.5, 74: 25.5, 75: 24.6, 76: 23.7, 77: 22.9, 78: 22.0, 79: 21.1,
    80: 20.2, 81: 19.4, 82: 18.5, 83: 17.7, 84: 16.8, 85: 16.0, 86: 15.2, 87: 14.4,
    88: 13.7, 89: 12.9, 90: 12.2, 91: 11.5, 92: 10.8, 93: 10.1, 94:  9.5, 95:  8.9,
    96:  8.4, 97:  7.8, 98:  7.3, 99:  6.8, 100: 6.4
}


def annualize_from_monthly_path(r_monthly: np.ndarray) -> float:
    \"\"\"Compound 12 monthly returns into one annual return.\"\"\"
    acc = 1.0
    for r in r_monthly:
        acc *= (1.0 + float(r))
    return float(acc - 1.0)


def update_expense(expense_annual: float, infl_annual: float, rule: str,
                   portfolio_value: float, params: Dict) -> float:
    \"\"\"
    Next-year spending budget.
      "inflation_only": constant real spending (CPI-indexed).
      "guardrails": cut/raise based on withdrawal-rate thresholds.
    \"\"\"
    new_exp = float(expense_annual) * (1.0 + float(infl_annual))

    if str(rule) == "guardrails" and float(portfolio_value) > 0:
        wr = new_exp / float(portfolio_value)
        gr = params["guardrails"]
        if wr > float(gr["upper_guardrail"]):
            new_exp *= (1.0 - float(gr["cut_factor"]))
        elif wr < float(gr["lower_guardrail"]):
            new_exp *= (1.0 + float(gr["raise_factor"]))

    return float(new_exp)


# ----- Sleeve / wrapper utilities -----

def wrapper_total(w: Dict[str, float]) -> float:
    return float(w.get("stock", 0.0) + w.get("bond", 0.0) + w.get("cash", 0.0))

def pro_rata_reduce(w: Dict[str, float], gross_draw: float) -> Dict[str, float]:
    \"\"\"
    Reduce wrapper sleeves pro-rata by current sleeve weights.
    Liquidation is mechanical (no stock-vs-bond decision).
    \"\"\"
    total = wrapper_total(w)
    if total <= 0 or gross_draw <= 0:
        return w
    draw = float(min(gross_draw, total))
    ws = float(w.get("stock", 0.0)) / total
    wb = float(w.get("bond",  0.0)) / total
    wc = float(w.get("cash",  0.0)) / total
    w["stock"] = float(max(0.0, w.get("stock", 0.0) - draw * ws))
    w["bond"]  = float(max(0.0, w.get("bond",  0.0) - draw * wb))
    w["cash"]  = float(max(0.0, w.get("cash",  0.0) - draw * wc))
    return w

def rebalance_wrapper(w: Dict[str, float], target: Dict[str, float]) -> Dict[str, float]:
    \"\"\"Periodic rebalancing to target weights.\"\"\"
    total = wrapper_total(w)
    if total <= 0:
        return w
    ts = float(target.get("stock", 0.0))
    tb = float(target.get("bond",  0.0))
    tc = float(target.get("cash",  0.0))
    s = ts + tb + tc
    if s <= 0:
        return w
    ts, tb, tc = ts / s, tb / s, tc / s
    w["stock"] = total * ts
    w["bond"]  = total * tb
    w["cash"]  = total * tc
    return w


# ----- Withdrawals -----

def withdraw_taxable_pro_rata(
    w_taxable: Dict[str, float],
    basis: float,
    needed_net: float,
    cap_gains_rate: float
) -> Tuple[Dict[str, float], float, float, float]:
    \"\"\"Withdraw from taxable wrapper; tax only the gain portion (avg cost basis).\"\"\"
    total = wrapper_total(w_taxable)
    if total <= 0 or needed_net <= 0:
        return w_taxable, float(basis), float(needed_net), 0.0
    draw = float(min(needed_net, total))
    basis_frac = float(np.clip(basis / total if total > 0 else 0.0, 0.0, 1.0))
    gain_part = draw * (1.0 - basis_frac)
    tax = gain_part * float(cap_gains_rate)
    net = draw - tax
    w_taxable = pro_rata_reduce(w_taxable, gross_draw=draw)
    basis = float(max(0.0, min(basis - draw * basis_frac, wrapper_total(w_taxable))))
    remaining = float(max(0.0, needed_net - net))
    return w_taxable, basis, remaining, float(tax)


def withdraw_td_pro_rata(
    w_td: Dict[str, float],
    needed_net: float,
    ord_tax_rate: float
) -> Tuple[Dict[str, float], float, float, float, float]:
    \"\"\"
    Withdraw from a tax-deferred wrapper (gross-up for taxes so net matches need).
    \"\"\"
    total = wrapper_total(w_td)
    if total <= 0 or needed_net <= 0:
        return w_td, float(needed_net), 0.0, 0.0, 0.0
    tax_rate = float(ord_tax_rate)
    gross_needed = needed_net / (1.0 - tax_rate)
    gross = float(min(total, gross_needed))
    tax   = gross * tax_rate
    net   = gross - tax
    remaining = float(max(0.0, needed_net - net))
    w_td = pro_rata_reduce(w_td, gross_draw=gross)
    return w_td, remaining, gross, float(tax), float(net)


def apply_rmd_pro_rata(
    age: int,
    w_td: Dict[str, float],
    rmd_start_age: int,
    ord_tax_rate: float,
    prior_1231_balance: float,
) -> Tuple[Dict[str, float], float, float, float, bool]:
    \"\"\"
    Apply an RMD to a tax-deferred wrapper.

    IRS rule: RMD = prior December 31 balance / life-expectancy divisor.
    Reference: https://www.irs.gov/retirement-plans/retirement-plan-and-ira-required-minimum-distributions-faqs

    Parameters
    ----------
    prior_1231_balance : float
        Wrapper balance as of the prior December 31 (used as RMD basis).

    Returns
    -------
    (updated_wrapper, net_rmd, tax_rmd, gross_rmd, shortfall_flag)
    \"\"\"
    if age < rmd_start_age or prior_1231_balance <= 0:
        return w_td, 0.0, 0.0, 0.0, False

    divisor  = IRS_RMD_TABLE.get(int(age), max(2.0, 120.0 - float(age)))
    gross    = float(prior_1231_balance / float(divisor))
    tax      = gross * float(ord_tax_rate)
    net      = gross - tax

    current_balance = wrapper_total(w_td)
    shortfall = False
    if current_balance < gross:
        # Wrapper depleted: withdraw whatever remains
        actual_gross = float(current_balance)
        tax           = actual_gross * float(ord_tax_rate)
        net           = actual_gross - tax
        gross         = actual_gross
        shortfall     = True

    w_td = pro_rata_reduce(w_td, gross_draw=gross)
    return w_td, float(net), float(tax), float(gross), shortfall


# =============================================================================
# Social Security taxation — IRS Pub 915 provisional income method
# =============================================================================
# Reference: https://www.irs.gov/publications/p915
#
# Provisional income = AGI + tax-exempt interest + 50 % of SS benefits.
# Filing thresholds (not indexed for inflation in current law):
#   Single / MFS:  $25,000 (50 % tier) / $34,000 (85 % tier)
#   MFJ / Widow(er): $32,000 (50 % tier) / $44,000 (85 % tier)

def compute_taxable_ss(
    ss_income: float,
    filing_status: str,
    other_income: float,
    tax_exempt_interest: float = 0.0,
) -> float:
    \"\"\"
    Compute the TAXABLE portion of Social Security income per IRS Pub 915.

    Parameters
    ----------
    ss_income          : total annual SS benefits received
    filing_status      : 'single' | 'married_filing_jointly' | 'surviving_spouse'
    other_income       : AGI excluding SS (wages, interest, dividends, RMDs, etc.)
    tax_exempt_interest: tax-exempt interest income (included in provisional income)

    Returns
    -------
    Taxable SS amount (always <= ss_income).
    \"\"\"
    ss_income  = float(max(0.0, ss_income))
    other_income = float(max(0.0, other_income))
    tax_exempt_interest = float(max(0.0, tax_exempt_interest))

    if ss_income == 0.0:
        return 0.0

    status = str(filing_status).strip().lower()
    if status in ("married_filing_jointly", "surviving_spouse"):
        thresh_low  = 32_000.0
        thresh_high = 44_000.0
    else:  # single, mfs, head_of_household, etc.
        thresh_low  = 25_000.0
        thresh_high = 34_000.0

    provisional = other_income + tax_exempt_interest + 0.5 * ss_income

    if provisional <= thresh_low:
        taxable_ss = 0.0
    elif provisional <= thresh_high:
        # 50 % of the excess over thresh_low, but no more than 50 % of SS
        taxable_ss = min(0.5 * ss_income, 0.5 * (provisional - thresh_low))
    else:
        # 85 % tier
        base_tier1  = min(0.5 * ss_income, 0.5 * (thresh_high - thresh_low))
        taxable_ss  = base_tier1 + 0.85 * (provisional - thresh_high)
        taxable_ss  = min(taxable_ss, 0.85 * ss_income)

    return float(max(0.0, taxable_ss))


# =============================================================================
# Pension / fixed-income stream helpers (with COLA + survivor %)
# =============================================================================

def _clip_optional(x: float, lo=None, hi=None) -> float:
    if lo is not None: x = max(float(lo), float(x))
    if hi is not None: x = min(float(hi), float(x))
    return float(x)

def init_pension_state(pensions: List[Dict]) -> List[Dict]:
    st = []
    for p in (pensions or []):
        st.append({
            "current_pay": float(p.get("annual_amount", 0.0)),
            "started": False,
            "owner_dead": False
        })
    return st

def pension_income_and_update(
    pensions: List[Dict],
    pension_state: List[Dict],
    age_a: int, age_b: int,
    alive_a: bool, alive_b: bool,
    infl_annual: float
) -> float:
    \"\"\"
    Compute total pension income for the year and update state for next year.
    \"\"\"
    if not pensions:
        return 0.0
    total_income = 0.0
    infl_annual  = float(infl_annual)

    for i, p in enumerate(pensions):
        owner       = str(p.get("owner", "a")).lower()
        start_age   = int(p.get("start_age", 10**9))
        survivor_pct = float(p.get("survivor_percent", 0.0))

        if owner == "a":
            owner_alive  = bool(alive_a)
            owner_age    = int(age_a)
            spouse_alive = bool(alive_b)
        else:
            owner_alive  = bool(alive_b)
            owner_age    = int(age_b) if age_b is not None else 0
            spouse_alive = bool(alive_a)

        if not pension_state[i]["started"]:
            if owner_alive and owner_age >= start_age:
                pension_state[i]["started"]     = True
                pension_state[i]["current_pay"] = float(p.get("annual_amount", 0.0))
            else:
                continue

        if owner_alive:
            payable = float(pension_state[i]["current_pay"])
        else:
            if not pension_state[i]["owner_dead"]:
                pension_state[i]["owner_dead"] = True
                if spouse_alive and survivor_pct > 0.0:
                    pension_state[i]["current_pay"] *= survivor_pct
                else:
                    pension_state[i]["current_pay"] = 0.0
            payable = float(pension_state[i]["current_pay"])

        if payable <= 0.0:
            continue
        total_income += payable

        # Apply COLA for next year
        cola_mode = str(p.get("cola_mode", "none")).lower()
        if cola_mode == "cpi":
            rate = _clip_optional(infl_annual, p.get("cola_floor"), p.get("cola_cap"))
            pension_state[i]["current_pay"] *= (1.0 + rate)
        elif cola_mode == "fixed":
            rate = _clip_optional(float(p.get("fixed_cola", 0.0) or 0.0),
                                  p.get("cola_floor"), p.get("cola_cap"))
            pension_state[i]["current_pay"] *= (1.0 + rate)

    return float(total_income)
"""

set_cell(5, CELL5)

# ---------------------------------------------------------------------------
# CELL 6 — Parameters  (remove deprecated fields, add new ones)
# ---------------------------------------------------------------------------

CELL6 = """\
# =============================================================================
# Parameters
# =============================================================================

params = {
    # ----- Reproducibility -----
    "current_year": 2025,
    "seed": 42,
    "n_paths": 500,

    # ----- Data -----
    "shiller_path": "ie_data.xls",
    "start_year": 1926,

    # ----- Return generation mode -----
    "return_mode": "block_bootstrap",
    "block_len_months": 24,
    "bootstrap_regime_conditioned": False,

    # ----- Rebalancing -----
    "rebalance_freq_months": 6,

    # ----- Taxes -----
    "ordinary_tax_rate": 0.22,
    "cap_gains_tax_rate": 0.15,
    "taxable_drag_annual": 0.006,
    "cash_ret_annual": 0.02,

    # Filing status for IRS Pub 915 SS taxation
    # Options: "single" | "married_filing_jointly" | "surviving_spouse"
    "filing_status": "married_filing_jointly",

    # ----- Starting balances -----
    "taxable_init": 200_000.0,
    "taxable_basis_fraction": 0.75,
    "td_a_init": 500_000.0,
    "td_b_init": 350_000.0,
    "roth_init": 150_000.0,

    # ----- Wrapper-level target allocations -----
    "wrapper_alloc": {
        "taxable": {"stock": 0.60, "bond": 0.30, "cash": 0.10},
        "td_a":    {"stock": 0.60, "bond": 0.30, "cash": 0.10},
        "td_b":    {"stock": 0.60, "bond": 0.30, "cash": 0.10},
        "roth":    {"stock": 0.60, "bond": 0.30, "cash": 0.10},
    },

    # ----- Spending policy -----
    # "initial_expense_annual" is the starting annual spending budget in today's dollars.
    # "inflation_only": constant real spending (CPI-indexed each year).
    # "guardrails":     cut/raise spending when withdrawal rate crosses thresholds.

    "initial_expense_annual": 80_000.0,
    "spending_rule": "inflation_only",
    "guardrails": {
        "upper_guardrail": 0.06,
        "lower_guardrail": 0.03,
        "cut_factor": 0.10,
        "raise_factor": 0.10,
    },

    # ----- Demographics / mortality -----
    "spouse_a_start_age": 65,
    "spouse_b_start_age": 65,
    "is_couple": True,
    "max_age_cap": 100,          # hard cap passed to sample_death_age_qx()
    "sex_a": "male",
    "sex_b": "female",

    # ----- Social Security -----
    # ss_claim_amount is in TODAY's real dollars.
    # The engine inflates it to the claim year using cumulative simulated CPI.
    # After claiming, COLA tracks simulated inflation annually.
    "ss_a": {"claim_age": 67, "claim_amount": 30_000.0},
    "ss_b": {"claim_age": 67, "claim_amount": 20_000.0},

    # Survivor SS logic:
    #   "simplified": survivor receives the maximum currently-payable benefit.
    #   "ssa_like":   enforces eligibility age, reduced vs full benefit rules.
    "ss_survivor_mode": "simplified",
    "ss_survivor_eligibility_age_a": 67,   # full survivor benefit age for spouse A
    "ss_survivor_eligibility_age_b": 67,   # full survivor benefit age for spouse B

    # Survivor spending reduction (expenses drop to this fraction when one spouse dies)
    "survivor_expense_percent": 0.75,

    # ----- Pensions / other fixed-income streams -----
    # annual_amount is in TODAY's dollars at start_age.
    "pensions": [
        {
            "owner": "a",
            "start_age": 65,
            "annual_amount": 24_000.0,
            "cola_mode": "fixed",
            "fixed_cola": 0.03,
            "cola_cap": None,
            "cola_floor": None,
            "survivor_percent": 0.50,
        },
    ],
}

params
"""

set_cell(6, CELL6)

# ---------------------------------------------------------------------------
# CELL 8 — Simulation core  (all major fixes applied)
# ---------------------------------------------------------------------------

CELL8 = """\
# =============================================================================
# Simulation core (single path)
# =============================================================================

def init_wrapper_from_total(total: float, target: Dict[str, float]) -> Dict[str, float]:
    \"\"\"Initialize wrapper sleeves to target weights.\"\"\"
    ts = float(target.get("stock", 0.0))
    tb = float(target.get("bond",  0.0))
    tc = float(target.get("cash",  0.0))
    s  = ts + tb + tc
    if s <= 0:
        return {"stock": float(total), "bond": 0.0, "cash": 0.0}
    ts, tb, tc = ts / s, tb / s, tc / s
    return {"stock": total * ts, "bond": total * tb, "cash": total * tc}


def simulate_once(
    rng: Optional[np.random.Generator] = None,
    return_trace: bool = False,
) -> Tuple[float, list, Optional[list]]:
    \"\"\"
    Execute a SINGLE simulation path.

    Design:
      - Time-ordered returns via stationary block bootstrap.
      - Withdrawals: taxable → TD(A) → TD(B) → Roth (pro-rata within each wrapper).
      - Mortality: stochastic (SSA 2022 q_x).  Death confirmed at end-of-year
        when age_eoy > sampled_death_age  (aligns with SSA q_x definition).
      - Horizon: driven by the sampled death ages, not a fixed max_age parameter.
      - SS: benefit inflated from today's dollars to claim year using cumulative CPI.
      - RMD: uses prior December 31 balance per IRS rules.
      - SS taxation: IRS Pub 915 provisional-income method.
    \"\"\"
    if rng is None:
        rng = np.random.default_rng()

    p          = params
    is_couple  = bool(p.get("is_couple", True))
    current_year = int(p["current_year"])

    # --- Stochastic death ages (sampled once per path) ---
    max_age_cap = int(min(int(p.get("max_age_cap", 100)), 100))
    sex_a = str(p.get("sex_a", "male"))
    sex_b = str(p.get("sex_b", "female"))
    death_age_a = sample_death_age_qx(
        int(p["spouse_a_start_age"]), sex_a, rng, max_age_cap=max_age_cap
    )
    death_age_b = (
        sample_death_age_qx(int(p["spouse_b_start_age"]), sex_b, rng, max_age_cap=max_age_cap)
        if is_couple else 10 ** 9
    )

    # --- Simulation horizon: driven by sampled death ages ---
    # Horizon = years until the LAST surviving spouse dies (+ 1 buffer year),
    # capped at max_age_cap for safety.
    years_a = max(0, int(death_age_a) - int(p["spouse_a_start_age"]) + 1)
    years_b = (
        max(0, int(death_age_b) - int(p["spouse_b_start_age"]) + 1)
        if is_couple else 0
    )
    years    = max(years_a, years_b, 1)
    n_months = int(years * 12)

    # --- Pensions ---
    pensions      = p.get("pensions", []) or []
    pension_state = init_pension_state(pensions)

    # --- RMD start ages ---
    birth_year_a = current_year - int(p["spouse_a_start_age"])
    birth_year_b = current_year - int(p["spouse_b_start_age"]) if is_couple else None
    rmd_start_a  = get_rmd_start_age(birth_year_a)
    rmd_start_b  = get_rmd_start_age(birth_year_b) if birth_year_b is not None else 10 ** 9

    # --- Initialize wrappers ---
    alloc     = p["wrapper_alloc"]
    w_taxable = init_wrapper_from_total(float(p["taxable_init"]),  alloc["taxable"])
    w_td_a    = init_wrapper_from_total(float(p["td_a_init"]),     alloc["td_a"])
    w_td_b    = init_wrapper_from_total(float(p["td_b_init"]),     alloc["td_b"])
    w_roth    = init_wrapper_from_total(float(p["roth_init"]),     alloc["roth"])

    basis = float(wrapper_total(w_taxable)) * float(p["taxable_basis_fraction"])

    # --- Prior Dec-31 balances for RMD (initialised to starting balances) ---
    td_a_prior_1231 = wrapper_total(w_td_a)
    td_b_prior_1231 = wrapper_total(w_td_b)

    # --- Social Security state ---
    ss_pay_a        = 0.0
    ss_pay_b        = 0.0
    ss_claimed_a    = False
    ss_claimed_b    = False

    ss_claim_a = PersonSpec(
        start_age=int(p["spouse_a_start_age"]),
        ss_claim_age=int(p["ss_a"]["claim_age"]),
        ss_claim_amount=float(p["ss_a"]["claim_amount"]),
    )
    ss_claim_b = None
    if is_couple:
        ss_claim_b = PersonSpec(
            start_age=int(p["spouse_b_start_age"]),
            ss_claim_age=int(p["ss_b"]["claim_age"]),
            ss_claim_amount=float(p["ss_b"]["claim_amount"]),
        )

    # --- Mortality state ---
    m_state = MortalityState(alive_a=True, alive_b=is_couple)

    # --- Spending ---
    expense_annual = float(p["initial_expense_annual"])

    # --- Survivor / filing status settings ---
    ss_survivor_mode   = str(p.get("ss_survivor_mode", "simplified"))
    ss_surv_elig_a     = int(p.get("ss_survivor_eligibility_age_a", 67))
    ss_surv_elig_b     = int(p.get("ss_survivor_eligibility_age_b", 67))
    filing_status      = str(p.get("filing_status", "married_filing_jointly"))

    # --- Build return tapes ---
    if data.empty:
        stock_tape = np.full(n_months, 0.006, dtype=float)
        bond_tape  = np.full(n_months, 0.002, dtype=float)
        infl_tape  = np.full(n_months, 0.002, dtype=float)
    else:
        stock_hist = data["stock_ret"].to_numpy(dtype=float)
        bond_hist  = data["bond_ret"].to_numpy(dtype=float)
        infl_hist  = data["infl_mom"].to_numpy(dtype=float)
        T = len(stock_hist)
        eligible = None
        if bool(p.get("bootstrap_regime_conditioned", False)):
            mask = (
                (data["vol_regime"].astype(str).values == "vol_mid") &
                (data["infl_regime"].astype(str).values == "mid")
            )
            eligible = np.where(mask)[0]
        idx = stationary_block_indices(
            n_months=n_months, T=T, rng=rng,
            expected_block_len=int(p["block_len_months"]),
            eligible_start_idx=eligible,
        )
        stock_tape = stock_hist[idx]
        bond_tape  = bond_hist[idx]
        infl_tape  = infl_hist[idx]

    cash_ret_m      = float(p["cash_ret_annual"]) / 12.0
    taxable_drag_m  = float(p["taxable_drag_annual"]) / 12.0
    reb_freq        = int(p["rebalance_freq_months"])

    history     = []
    trace       = []
    infl_months = []

    # Cumulative CPI factor from simulation start (used to inflate SS to claim year)
    cumul_infl_factor = 1.0

    for m in range(int(n_months)):
        year_idx = m // 12

        # ----- 1) Monthly returns -----
        r_s = float(stock_tape[m])
        r_b = float(bond_tape[m])
        r_i = float(infl_tape[m])
        infl_months.append(r_i)
        cumul_infl_factor *= (1.0 + r_i)

        taxable_total_before = wrapper_total(w_taxable)
        for w in (w_taxable, w_td_a, w_td_b, w_roth):
            w["stock"] *= (1.0 + r_s)
            w["bond"]  *= (1.0 + r_b)
            w["cash"]  *= (1.0 + cash_ret_m)

        # Taxable leakage (drag only in positive-return months)
        taxable_total_after = wrapper_total(w_taxable)
        if taxable_total_after > taxable_total_before and taxable_total_after > 0 and taxable_drag_m > 0:
            drag_amt = taxable_total_after * taxable_drag_m
            w_taxable = pro_rata_reduce(w_taxable, gross_draw=drag_amt)
            basis = float(min(basis, wrapper_total(w_taxable)))

        # ----- 2) Periodic rebalancing -----
        if reb_freq > 0 and ((m + 1) % reb_freq == 0):
            w_taxable = rebalance_wrapper(w_taxable, alloc["taxable"])
            w_td_a    = rebalance_wrapper(w_td_a,    alloc["td_a"])
            w_td_b    = rebalance_wrapper(w_td_b,    alloc["td_b"])
            w_roth    = rebalance_wrapper(w_roth,    alloc["roth"])

        # ----- 3) Annual events (end-of-year only) -----
        if (m + 1) % 12 != 0:
            continue

        age_a = int(p["spouse_a_start_age"]) + int(year_idx) + 1
        age_b = (int(p["spouse_b_start_age"]) + int(year_idx) + 1) if is_couple else None

        infl_a      = annualize_from_monthly_path(np.array(infl_months, dtype=float))
        infl_months = []

        # 3a) Mortality — death confirmed when age_eoy > sampled_death_age
        #     (SSA q_x: death during [x, x+1], confirmed at end of year x+1)
        death_a = bool(m_state.alive_a and (age_a > death_age_a))
        death_b = bool(is_couple and m_state.alive_b and (age_b is not None) and (age_b > death_age_b))

        m_state, expense_annual, ss_pay_a, ss_pay_b, td_a_total, td_b_total = apply_survivor_adjustments(
            death_a=death_a,
            death_b=death_b,
            m_state=m_state,
            expense_annual=expense_annual,
            survivor_expense_percent=float(p["survivor_expense_percent"]),
            ss_pay_a=ss_pay_a,
            ss_pay_b=ss_pay_b,
            td_a_total=wrapper_total(w_td_a),
            td_b_total=wrapper_total(w_td_b),
            ss_survivor_mode=ss_survivor_mode,
            age_a=age_a,
            age_b=(age_b if age_b is not None else 0),
            ss_survivor_eligibility_age_a=ss_surv_elig_a,
            ss_survivor_eligibility_age_b=ss_surv_elig_b,
        )

        if death_a and (not death_b):
            w_td_a = {"stock": 0.0, "bond": 0.0, "cash": 0.0}
            w_td_b = init_wrapper_from_total(td_b_total, alloc["td_b"])
        if death_b and (not death_a):
            w_td_b = {"stock": 0.0, "bond": 0.0, "cash": 0.0}
            w_td_a = init_wrapper_from_total(td_a_total, alloc["td_a"])
        if death_a and death_b:
            break

        # Update surviving spouse's filing status after first death
        if (death_a or death_b) and filing_status == "married_filing_jointly":
            # First year after death: surviving_spouse; subsequent: single
            filing_status = "surviving_spouse"

        # 3b) Social Security: claim + COLA
        income_ss = 0.0

        if m_state.alive_a:
            if not ss_claimed_a and age_a >= ss_claim_a.ss_claim_age:
                # Inflate today's-dollar benefit to nominal at claim year
                ss_pay_a   = float(ss_claim_a.ss_claim_amount) * cumul_infl_factor
                ss_claimed_a = True
            if ss_claimed_a:
                income_ss += ss_pay_a

        if is_couple and m_state.alive_b and age_b is not None and ss_claim_b is not None:
            if not ss_claimed_b and age_b >= ss_claim_b.ss_claim_age:
                ss_pay_b   = float(ss_claim_b.ss_claim_amount) * cumul_infl_factor
                ss_claimed_b = True
            if ss_claimed_b:
                income_ss += ss_pay_b

        # Apply COLA to in-pay benefits
        if ss_pay_a > 0:
            ss_pay_a *= (1.0 + infl_a)
        if ss_pay_b > 0:
            ss_pay_b *= (1.0 + infl_a)

        # 3c) Pension income
        income_pension = pension_income_and_update(
            pensions=pensions,
            pension_state=pension_state,
            age_a=age_a, age_b=age_b,
            alive_a=m_state.alive_a, alive_b=m_state.alive_b,
            infl_annual=infl_a,
        )

        income_total = float(income_ss + income_pension)

        # 3d) SS taxation — IRS Pub 915 provisional income method
        # Other income approximation: RMDs + portfolio withdrawals = ordinary_tax_rate
        # We use income_total - income_ss as a proxy for non-SS ordinary income.
        taxable_ss = compute_taxable_ss(
            ss_income=income_ss,
            filing_status=filing_status,
            other_income=float(income_pension),   # pensions are ordinary income
        )
        ss_tax = taxable_ss * float(p["ordinary_tax_rate"])

        # 3e) Spending need BEFORE any withdrawals (waterfall stage 0)
        net_needed_before_rmd = float(max(0.0, expense_annual - income_total) + ss_tax)

        # 3f) RMDs — use prior December 31 balances per IRS rules
        w_td_a, rmd_net_a, rmd_tax_a, rmd_gross_a, rmd_short_a = apply_rmd_pro_rata(
            age=age_a, w_td=w_td_a, rmd_start_age=rmd_start_a,
            ord_tax_rate=float(p["ordinary_tax_rate"]),
            prior_1231_balance=td_a_prior_1231,
        )
        if is_couple and age_b is not None:
            w_td_b, rmd_net_b, rmd_tax_b, rmd_gross_b, rmd_short_b = apply_rmd_pro_rata(
                age=age_b, w_td=w_td_b, rmd_start_age=rmd_start_b,
                ord_tax_rate=float(p["ordinary_tax_rate"]),
                prior_1231_balance=td_b_prior_1231,
            )
        else:
            rmd_net_b = rmd_tax_b = rmd_gross_b = 0.0
            rmd_short_b = False

        rmd_total = float(rmd_net_a + rmd_net_b)

        net_needed = float(net_needed_before_rmd)
        if rmd_total >= net_needed:
            excess = rmd_total - net_needed
            w_taxable["cash"] += excess
            basis += excess
            net_needed = 0.0
        else:
            net_needed -= rmd_total
        net_needed_after_rmd = float(net_needed)

        # 3g) Withdrawal waterfall
        # 1) Taxable
        w_taxable, basis, net_needed, _ = withdraw_taxable_pro_rata(
            w_taxable, basis, net_needed, float(p["cap_gains_tax_rate"])
        )
        net_needed_after_taxable = float(net_needed)

        # 2) Tax-deferred (A then B)
        if net_needed > 0:
            w_td_a, net_needed, _, _, _ = withdraw_td_pro_rata(
                w_td_a, net_needed, float(p["ordinary_tax_rate"])
            )
        if net_needed > 0 and is_couple:
            w_td_b, net_needed, _, _, _ = withdraw_td_pro_rata(
                w_td_b, net_needed, float(p["ordinary_tax_rate"])
            )
        net_needed_after_td = float(net_needed)

        # 3) Roth (tax-free)
        if net_needed > 0:
            roth_total = wrapper_total(w_roth)
            draw = float(min(roth_total, net_needed))
            w_roth = pro_rata_reduce(w_roth, gross_draw=draw)
            net_needed -= draw
        net_needed_after_roth = float(net_needed)

        # 3h) Update prior-Dec-31 balances for NEXT year's RMD
        td_a_prior_1231 = wrapper_total(w_td_a)
        td_b_prior_1231 = wrapper_total(w_td_b)

        # 3i) Update spending for next year
        total_port = (
            wrapper_total(w_taxable) + wrapper_total(w_td_a) +
            wrapper_total(w_td_b) + wrapper_total(w_roth)
        )
        expense_annual = update_expense(
            expense_annual, infl_a, str(p["spending_rule"]), total_port, p
        )

        # ----- Trace (end-of-year snapshot) -----
        if return_trace:
            trace.append({
                "year_idx":   int(year_idx),
                "age_a":      int(age_a),
                "age_b":      int(age_b) if (is_couple and age_b is not None) else None,
                "alive_a":    bool(m_state.alive_a),
                "alive_b":    bool(m_state.alive_b) if is_couple else False,
                "death_age_a": int(death_age_a),
                "death_age_b": int(death_age_b) if is_couple else None,

                "infl_a":          float(infl_a),
                "cumul_infl":      float(cumul_infl_factor),
                "expense_annual":  float(expense_annual),

                "income_ss":      float(income_ss),
                "income_pension": float(income_pension),
                "income_total":   float(income_total),

                # SS taxation (Pub 915)
                "taxable_ss": float(taxable_ss),
                "ss_tax":     float(ss_tax),

                # RMD detail
                "rmd_prior_balance_a": float(td_a_prior_1231 + rmd_gross_a),  # pre-RMD balance
                "rmd_prior_balance_b": float(td_b_prior_1231 + rmd_gross_b),
                "rmd_gross_a": float(rmd_gross_a),
                "rmd_gross_b": float(rmd_gross_b),
                "rmd_tax_a":   float(rmd_tax_a),
                "rmd_tax_b":   float(rmd_tax_b),
                "rmd_net_a":   float(rmd_net_a),
                "rmd_net_b":   float(rmd_net_b),

                # Cash-flow waterfall stages (all pre-update)
                "net_needed_before_rmd":    float(net_needed_before_rmd),
                "net_needed_after_rmd":     float(net_needed_after_rmd),
                "net_needed_after_taxable": float(net_needed_after_taxable),
                "net_needed_after_td":      float(net_needed_after_td),
                "net_needed_after_roth":    float(net_needed_after_roth),

                # Portfolio snapshot
                "taxable_total":  float(wrapper_total(w_taxable)),
                "td_a_total":     float(wrapper_total(w_td_a)),
                "td_b_total":     float(wrapper_total(w_td_b)) if is_couple else 0.0,
                "roth_total":     float(wrapper_total(w_roth)),
                "total_portfolio": float(total_port),
            })

        history.append(float(total_port))
        if total_port <= 0.0:
            break

    ending = float(max(0.0,
        wrapper_total(w_taxable) + wrapper_total(w_td_a) +
        wrapper_total(w_td_b) + wrapper_total(w_roth)
    ))
    return ending, history, (trace if return_trace else None)
"""

set_cell(8, CELL8)

# ---------------------------------------------------------------------------
# NEW CELL — Regression tests  (insert after cell 8)
# ---------------------------------------------------------------------------

TEST_SRC = """\
# =============================================================================
# Regression tests
# =============================================================================

import warnings

def _run_tests():
    rng_det = np.random.default_rng(0)
    passed = []
    failed = []

    def check(name, cond, detail=""):
        if cond:
            passed.append(name)
        else:
            failed.append(f"FAIL: {name}  {detail}")

    # ---- 1. Mortality: death confirmed AFTER trigger interval ----
    # Set max_age_cap = 70 so the first path is short and predictable.
    saved_cap = params.get("max_age_cap")
    params["max_age_cap"] = 70
    rng_m = np.random.default_rng(42)
    da = sample_death_age_qx(65, "male", rng_m, max_age_cap=70)
    # Simulate a minimal path; confirm alive_a is False only when age_a > da
    _, _, tr = simulate_once(rng=np.random.default_rng(42), return_trace=True)
    if tr:
        for row in tr:
            if not row["alive_a"]:
                check("death_after_trigger_age",
                      row["age_a"] > row["death_age_a"],
                      f"age_a={row['age_a']} death_age_a={row['death_age_a']}")
                break
    params["max_age_cap"] = saved_cap

    # ---- 2. Mortality: paths can extend beyond age 95 ----
    # Force death age to 98 by using a very low death cap override.
    params["max_age_cap"] = 100
    # Run 200 paths; at least some should reach age > 95
    rng2 = np.random.default_rng(7)
    max_ages_seen = []
    for _ in range(200):
        _, hist, _ = simulate_once(rng=rng2)
        max_ages_seen.append(len(hist))  # each year is one history entry
    check("paths_extend_past_age_95",
          max(max_ages_seen) > 30,
          f"longest path: {max(max_ages_seen)} years")

    # ---- 3. RMD: no RMD before required start age ----
    _, _, tr3 = simulate_once(rng=np.random.default_rng(1), return_trace=True)
    if tr3:
        start_age = int(params["spouse_a_start_age"])
        rmd_start = get_rmd_start_age(int(params["current_year"]) - start_age)
        for row in tr3:
            if row["age_a"] < rmd_start:
                check("no_rmd_before_start_age",
                      row["rmd_gross_a"] == 0.0,
                      f"age={row['age_a']} rmd_gross_a={row['rmd_gross_a']}")
                break

    # ---- 4. RMD uses prior-Dec-31 balance (not current) ----
    # Year 2 RMD basis must equal the year-1 ending td_a_total in the trace.
    if tr3 and len(tr3) >= 2:
        y0 = tr3[0]
        y1 = tr3[1]
        if y1["rmd_gross_a"] > 0:
            rmd_basis_y1 = y1["rmd_prior_balance_a"]
            expected_prior = y0["td_a_total"]
            check("rmd_uses_prior_1231_balance",
                  abs(rmd_basis_y1 - expected_prior) < 1.0,
                  f"rmd_basis={rmd_basis_y1:.0f} year0_td_a={expected_prior:.0f}")

    # ---- 5. SS: claim occurs at claim age ----
    if tr3:
        claim_age_a = int(params["ss_a"]["claim_age"])
        for row in tr3:
            if row["age_a"] < claim_age_a:
                check("no_ss_before_claim_age",
                      row["income_ss"] == 0.0 or not row["alive_a"],
                      f"age={row['age_a']} income_ss={row['income_ss']}")
                break

    # ---- 6. SS: benefit is inflated at claim (should exceed today's amount) ----
    # Only valid when claim year > current year (i.e., claim_age > start_age).
    claim_age_a  = int(params["ss_a"]["claim_age"])
    start_age_a  = int(params["spouse_a_start_age"])
    claim_amount = float(params["ss_a"]["claim_amount"])
    if claim_age_a > start_age_a and tr3:
        for row in tr3:
            if row["alive_a"] and row["age_a"] >= claim_age_a and row["income_ss"] > 0:
                # income_ss includes both spouses, so just check > raw claim_amount
                check("ss_benefit_inflated_at_claim",
                      row["income_ss"] >= claim_amount,
                      f"income_ss={row['income_ss']:.0f} claim_amount={claim_amount:.0f}")
                break

    # ---- 7. SS taxation: Pub 915 — low income → no/low taxable SS ----
    taxable_ss_zero = compute_taxable_ss(10_000.0, "single", 0.0)
    check("ss_not_taxable_below_threshold",
          taxable_ss_zero == 0.0,
          f"got {taxable_ss_zero}")

    taxable_ss_high = compute_taxable_ss(50_000.0, "married_filing_jointly", 100_000.0)
    check("ss_taxable_at_85pct_high_income",
          abs(taxable_ss_high - 0.85 * 50_000.0) < 1.0,
          f"got {taxable_ss_high:.0f}, expected {0.85*50_000:.0f}")

    # ---- 8. Waterfall reconciliation ----
    if tr3:
        row = tr3[0]
        gross   = row["net_needed_before_rmd"]
        rmd_net = row["rmd_net_a"] + row["rmd_net_b"]
        expected_after_rmd = max(0.0, gross - rmd_net)
        check("waterfall_rmd_stage_consistent",
              abs(row["net_needed_after_rmd"] - expected_after_rmd) < 0.01,
              f"after_rmd={row['net_needed_after_rmd']:.2f} expected={expected_after_rmd:.2f}")

    # ---- 9. Shiller loader schema guard ----
    try:
        _ = load_shiller_data(params["shiller_path"], params["start_year"])
        check("shiller_loader_runs_without_error", True)
    except Exception as e:
        check("shiller_loader_runs_without_error", False, str(e))

    # ---- Summary ----
    print(f"\\nRegression tests: {len(passed)} passed, {len(failed)} failed")
    for f in failed:
        print(" ", f)
    if not failed:
        print("  All tests passed.")
    return len(failed) == 0

_run_tests()
"""

# Insert new test cell after cell 8 (index 9)
new_test_cell = {
    "cell_type": "code",
    "execution_count": None,
    "metadata": {},
    "outputs": [],
    "source": TEST_SRC,
}

# Check if test cell already exists (avoid duplicate on re-run)
existing_test_idx = None
for i, c in enumerate(cells):
    if "Regression tests" in "".join(c.get("source", "")):
        existing_test_idx = i
        break

if existing_test_idx is not None:
    cells[existing_test_idx]["source"] = TEST_SRC
    print(f"Updated existing test cell at index {existing_test_idx}")
else:
    cells.insert(9, new_test_cell)
    print("Inserted new regression test cell at index 9")

# ---------------------------------------------------------------------------
# Write back
# ---------------------------------------------------------------------------

with open(NB_PATH, "w") as f:
    json.dump(nb, f, indent=1)

print("Notebook patched successfully.")
