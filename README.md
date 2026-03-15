# 📊 Retirement Monte Carlo Engine
### *Monthly, Time-Ordered Cash-Flow Simulation*

![Retirement Planning](https://img.shields.io/badge/Planning-Stress--Test-blue)
![Python](https://img.shields.io/badge/Language-Python-green)
![Monte Carlo](https://img.shields.io/badge/Model-Monte--Carlo-orange)

The **Retirement Monte Carlo Engine** is a financial planning tool designed to stress-test retirement portfolios against historical market episodes. Unlike basic calculators, it uses a **Stationary Block Bootstrap** to preserve the reality of market drawdowns, inflation spikes, and recovery periods observed in historical data.

---

## ⚖️ Disclaimer & Responsibility
**This notebook is for education and planning illustration only.** * **No Advice:** This is not investment, tax, or legal advice and is not a tax-filing model. 
* **User Responsibility:** This software is provided "as-is." The user assumes all risk and responsibility for the use of this engine, including any financial decisions or interpretations of the output. 
* **No Liability:** The author/developer retains no responsibility for errors, omissions, or inaccuracies within the model or for any financial losses resulting from its use. Outputs are conditional on assumptions and represent scenario distributions, not forecasts.

---

## 🚀 Key Capabilities
* **Historical Realism:** Uses Shiller `ie_data` to construct monthly total returns for stocks and bonds alongside CPI inflation.
* **Sophisticated Cash-Flows:** Models a strict withdrawal waterfall: **Taxable → Tax-Deferred → Roth**.
* **Adaptive Spending:** Supports "Guardrail" logic to simulate behavioral spending adjustments based on portfolio withdrawal rates.
* **Longevity Modeling:** Features stochastic mortality sampling using annual $q_x$ hazards for individuals and couples.
* **Optimization Suite:** Includes solvers for Maximum Safe Spending and two-stage Guardrail parameter optimization.

---

## 📉 Asset & Account Structure
The model manages four account "wrappers," each containing three "sleeves" (Stock/Bond/Cash).

| Wrapper | Liquidation Order | Tax Treatment |
| :--- | :---: | :--- |
| **Taxable** | 1st | Capital Gains (Average Basis) + Monthly Leakage Proxy |
| **Tax-Deferred (A/B)** | 2nd | Ordinary Income (Includes RMD Logic) |
| **Roth** | 3rd | Tax-Free |

---

## 🧬 Advanced Features

### 🛡️ Guardrail Spending Policy
Moves beyond "Constant Real" spending by implementing a behavioral feedback loop:
* **If Withdrawal Rate > Upper Guardrail:** Spending is cut by a fixed factor to preserve capital.
* **If Withdrawal Rate < Lower Guardrail:** Spending is increased to enjoy portfolio gains.

### ⚰️ Stochastic Mortality
Rather than a fixed "plan to age 95," the engine samples a death age for each path using actuarial tables. This allows for a more realistic distribution of outcomes and survivor benefit transitions.

### 🔍 One-Path Audit Trace
Run a single simulation path with a full end-of-year audit log. Review exactly when Social Security started, when a spouse passed away, and how RMDs were calculated for that specific scenario.

---

## ⚠️ Explicit Modeling Assumptions & Limitations

### Mortality
* **Source:** SSA 2022 period life table (Trustees Report 2025).
  URL: https://www.ssa.gov/oact/STATS/table4c6.html
* **No mortality improvement:** The period table does not include projected longevity gains.
* **Population:** General U.S. population, not annuitant or preferred-risk tables.
* **Horizon:** Each path runs until the last surviving spouse's sampled death age (driven by q_x draws, not a fixed max-age parameter). A hard cap of 100 prevents runaway paths.
* **Death timing:** SSA defines q_x as probability of dying before age x+1. Death is confirmed at end-of-year when age_eoy > sampled_trigger_age (strictly greater), consistent with this definition.

### RMD Assumptions
* **Uniform Lifetime Table** (IRS Pub 590-B, 2022 revision) used for all tax-deferred accounts.
* **Prior Dec 31 balance** is used as the RMD divisor basis per IRS rules.
* **Spouse >10 years younger rule** is not modeled (single-life table exception not applied).
* SECURE 2.0 start ages: born ≤1950 → 72; 1951–1959 → 73; ≥1960 → 75.

### Social Security
* `ss_claim_amount` inputs are in **today's real dollars**. The engine inflates each benefit to its nominal value at the claim year using cumulative simulated CPI, then applies annual COLA thereafter.
* **Taxation:** IRS Publication 915 provisional-income method is implemented (`compute_taxable_ss()`). Flat ordinary rate applied to the taxable portion. Progressive brackets, IRMAA, and QBI are not modeled.
* **Survivor logic:**
  - `"simplified"` mode (default): survivor receives the maximum currently-payable benefit.
  - `"ssa_like"` mode: enforces survivor eligibility age, linear reduction from 71.5% at age 60 to full benefit at the configured eligibility age. Survivor may keep own benefit if larger. Full SSA claiming rules (GPO, WEP, spousal benefit) are not modeled.
  - Reference: https://www.ssa.gov/pubs/EN-05-10084.pdf

### Tax Model Limitations
* Flat ordinary and capital gains rates (not progressive brackets).
* No NIIT, IRMAA, ACA, AMT, or QBI deductions.
* Taxable "drag" is a simplified leakage proxy applied only in positive-return months; it does not model explicit gain realization at rebalance.

### Data & Market Model
* Historical bootstrap (Shiller ie_data). Does not model regime transitions or tail events outside historical parameters.
* Shiller loader validates expected column layout and raises a clear error if the schema changes.

---

## 🚦 How to Use
1.  **Data Setup:** Ensure `ie_data.xls` (Shiller) and `mortality_table.csv` are in the project directory.
2.  **Configure:** Set initial balances, allocations, and spending rules in the **Parameters** section.
3.  **Simulate:** Run `run_simulation()` to generate success rates and wealth distributions.
4.  **Audit:** Use `one_path_trace()` to verify the mechanics on a single path.
5.  **Optimize:** Use the two-stage optimizer to identify the best guardrail configuration.

---
