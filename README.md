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

## ⚠️ Explicit Modeling Compromises
This engine prioritizes transparency and cash-flow ordering over tax/accounting exactitude.

* **Tax Simplifications:** Uses flat ordinary and capital gains rates rather than progressive brackets.
* **No Specialized Tax Rules:** Does not model NIIT, IRMAA, ACA, AMT, or QBI deductions.
* **Social Security Tax:** Uses IRS provisional-income rules (IRC §86) with two tiers (50 %/85 %). Provisional income is computed from pension income + 50 % of SS; RMD withdrawals are excluded to avoid double-counting since they are taxed separately in the RMD step. Thresholds are configurable parameters (`ss_pi_threshold_1/2_single/couple`) so they can be updated if Congress changes the statutory amounts.
* **Taxable "Tax Drag":** Rebalancing does not realize gains explicitly; instead, a leakage proxy is applied only in positive market months.
* **RMD Accounting:** Uses the prior December 31 balance per IRS rules (IRC §401(a)(9)).
* **Market Model:** Based on historical bootstrap episodes; does not model forward-looking regime transitions or "Black Swan" events outside of historical parameters.
* **Scope:** No explicit healthcare shocks, LTC events, or behavioral frictions beyond the guardrails policy.

---

## 🚦 How to Use
1.  **Data Setup:** Ensure `ie_data.xls` (Shiller) and `mortality_table.csv` are in the project directory.
2.  **Configure:** Set initial balances, allocations, and spending rules in the **Parameters** section.
3.  **Simulate:** Run `run_simulation()` to generate success rates and wealth distributions.
4.  **Audit:** Use `one_path_trace()` to verify the mechanics on a single path.
5.  **Optimize:** Use the two-stage optimizer to identify the best guardrail configuration.

---
