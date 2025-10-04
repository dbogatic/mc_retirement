# Retirement Monte Carlo Simulator  

## Disclaimer  
This tool is provided for **educational purposes only**.  
It does **not** constitute financial, investment, or tax advice.  
Users should exercise discretion in interpreting results and understand that errors or inaccuracies may exist.  
The methodology is **illustrative** and should not be relied upon for making personal financial decisions without consulting a qualified professional.  

**Note:** Portions of this code and documentation were developed with the assistance of **ChatGPT**.  

---

## 1. Key Inputs  

### Portfolio & Allocation  
- **Initial account balances:**  
  - Taxable  
  - Tax-deferred (two owners, A & B)  
  - Roth  

- **Asset allocation:**  
  - 60% equities  
  - 30% bonds  
  - 10% cash (**cash is modeled with a fixed 1% annual return**)  

### Taxes  
- Ordinary income tax rate: user-defined  
- Capital gains tax rate: user-defined  
- Taxable basis fraction: defines how much of the taxable account is treated as cost basis  

### Income  
- **Social Security (SS):**  
  - Each spouse has start age, initial amount, and COLA  

- **Pensions:**  
  - Each pension has start age, annual amount, COLA, and survivor benefit percent  

### Spending  
- Initial annual expense (user-specified)  
- Spending rule (fixed, % of portfolio, or guardrails)  
- Survivor adjustment (expense reduced to a fraction if one spouse dies)  

### Mortality  
- **Stochastic:** based on SSA mortality table (up to age 100)  
- **Deterministic:** fixed life expectancy if mortality is disabled  

---

## 2. Regime-Switching Inflation  

### Regime definition  
Inflation regimes are classified by monthly inflation rate:  
- Low: < 3% annualized  
- Mid: 3–5%  
- High: ≥ 5%  

### Transition dynamics  
- Regimes evolve using a Markov transition matrix.  
- Diagonal entries tuned for persistence.  
- Example: if currently in “low” regime, there is an 85% chance of remaining in “low” next year.  

### Inflation sampling  
- Within a regime, historical inflation observations are pooled.  
- A half-life weighting is applied, giving more weight to recent data.  
- Each year’s inflation is drawn randomly from this weighted pool.  

---

## 3. Return Modeling  

### Data source  
- Historical monthly Shiller data (equities, long-term government bonds, inflation).  

### Weighted statistics  
- For each regime:  
  - Compute weighted average returns and covariance matrix of stock/bond returns.  
  - Apply exponential half-life weighting so recent history matters more.  
- For unconditional case (no regimes):  
  - Same weighting applied to the full dataset.  

### Annualization  
- Means: multiplied by 12  
- Covariance: multiplied by 12  

### Distributional assumptions  
- **Normal:** multivariate normal with weighted mean/covariance.  
- **Student-t:** fat-tailed returns simulated via multivariate-t, with effective df set by `stock_df` and `bond_df`.  

### Correlation option  
- Use regime-specific correlations, or override with unconditional/global correlation.  

---

## 4. Simulation Mechanics  

Each simulation path proceeds year by year:  

1. **Mortality check**  
   - If a spouse reaches death age, adjust expenses and survivor benefits.  

2. **Income realization**  
   - Add Social Security and pensions (with COLA, survivor rules).  

3. **Expenses net of income**  
   - Remaining expenses must be funded via withdrawals.  

4. **Withdrawal sequence**  
   - RMDs: forced withdrawals from tax-deferred once RMD age reached.  
   - Taxable account: withdrawn first (basis vs gains taxed proportionally).  
   - Tax-deferred: withdrawn next, taxed at ordinary rate.  
   - Roth: last, tax-free.  

5. **Asset returns applied**  
   - Stock/bond returns drawn based on regime & chosen distribution.  
   - Cash earns fixed 1% return.  
   - Returns applied multiplicatively to all account balances.  

6. **Expense update**  
   - Next year’s expense updated per spending rule (fixed COLA, % portfolio, or guardrails).  

7. **Portfolio tracked**  
   - Portfolio value recorded each year.  
   - Simulation stops if portfolio depleted.  

---

## 5. Spending Rules  

- **Fixed:** expense inflated by actual inflation each year.  
- **Percent of portfolio:** expense set as fixed % of portfolio value.  
- **Guardrails:** expense adjusted up/down if withdrawal rate moves outside guardrail thresholds.  

---

## 6. Success Rate Analysis  

- Multiple simulation runs generate a distribution of outcomes.  
- **Success = portfolio never depletes before both spouses die.**  

Supports:  
- Binary search for max safe spending (spending level that achieves 90% success rate).  
- Guardrail optimization (search over cut/raise factors and guardrails to maximize sustainable spending).  
- Caches used to accelerate repeated evaluations.  

---

## 7. Outputs & Visualizations  

- **Spaghetti plots:** multiple portfolio paths with median and confidence bands.  
- **Trace tables:** detailed year-by-year cashflows, taxes, and balances.  
- **Safe spending curve:** success probability as a function of initial spending.  
- **Regime duration analysis:** historical persistence of inflation regimes.  
- **Regime frequency analysis:** distribution of regimes across simulated paths.  

---

## 8. Assumptions & Limitations  

- Cash return is fixed at 1%, independent of regime.  
- Shiller data used as historical baseline for stock/bond returns.  
- Correlations may shift by regime, but option exists to hold them constant at unconditional value.  
- Mortality capped at age 100.  
- No explicit modeling of healthcare shocks, annuities, or alternative assets.  
- Tax rules (RMD age, capital gains) based on SECURE 2.0 and current IRS guidance.  
