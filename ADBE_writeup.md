# Adobe (ADBE): BUY, 12-month target price $315 (+30%)

**Price $241.05 (Oct 9, 2026) · Market cap $94B · 52-week range $190–$364 · Data: SEC 10-Q for Q3 FY26 (Aug 28, 2026), Yahoo Finance**

## The call
The market is pricing Adobe as if it is in decline. The financials don't support that. At $241 the stock trades at about 9x EV/TTM FCF ($10.6B), which is an 11% FCF yield. After expensing $2.1B of stock-based compensation it is still about 9%. The reverse DCF shows that today's price implies **only ~3% annual revenue growth for 10 years** at current margins, or a fall in GAAP EBIT margin from 36% to **~26%** at base-case growth. Meanwhile Adobe grew revenue 13% in Q3, raised FY26 guidance to $26.6B (+12%), guided ending ARR growth to ~10% and just passed 1B MAUs. Our probability-weighted DCF is **$314/share**. Even the bear case ($189, −21%) assumes growth slows to zero *and* margins fall 9 points. That is an asymmetric setup: about 2:1 upside to downside.

## Valuation summary
| Scenario (prob.) | Revenue growth Y1→Y10 | GAAP EBIT margin | Terminal g | $/share | vs. price |
|---|---|---|---|---|---|
| Bear (25%): GenAI erodes seats and pricing | 5% → 0% | 34% → 27% | 1.0% | **$189** | −21% |
| Base (50%): steady fade to maturity | 10% → 3.5% | 36% → 34% | 2.5% | **$323** | +34% |
| Bull (25%): Firefly / GenStudio monetise | 12% → 5% | 37% → 39% | 3.0% | **$420** | +74% |
| **Probability-weighted** | | | | **$314** | **+30%** |

**Method:** 10-year unlevered FCF, mid-year discounting, Gordon terminal value (terminal value is 46% of EV in the base case). **WACC 11.1%:** 10Y UST 5.23% + Blume-adjusted beta 1.28 × 5.0% ERP. Debt is only 6% of capital. **Conservative choices:** SBC is treated as a real cash cost (GAAP EBIT, no add-back). D&A converges to capex in the terminal year. The base-case terminal value implies only **9.0x EBITDA**, well below software peers. Net debt is $0.7B and diluted shares are 389M.

**Sensitivities (base case):** across WACC 9–13% × terminal growth 1–4%, values range from $249 to $503. *Every cell sits above the current price.* On revenue-growth shift × terminal margin, the stock is fairly valued only if growth runs **~2pp/yr below base** with terminal margins compressed to ~27%, or ~4pp below base with margins held. An exit-multiple cross-check at 8–18x EBITDA gives $266–$533.

## Why the market disagrees (and why we think it's overdone)
1. **GenAI disruption (the core bear case).** Image and video generation from OpenAI, Google and Midjourney, plus Canva and Figma at the low end, could compress Creative Cloud seats and pricing power. *Our view:* this is real but slow. Adobe still reached record revenue, 1B MAUs and raised guidance. Pricing tiers that include Firefly credits are holding ARPU so far. A fall to a 27% margin with zero growth still values the stock at $189.
2. **Deceleration.** Ending ARR growth of ~10% trails revenue growth of 12–13%, so FY27 revenue growth likely lands near 10%. That is exactly our base case Y1, not upside.
3. **CEO transition.** Anil Chakravarthy succeeds Shantanu Narayen on Dec 1, 2026, and there is an interim CFO. This adds execution uncertainty, but the move is internal and orderly.

## Capital return supports the floor
Adobe repurchased $6.8B in the first three quarters of FY26 (≈10% of today's market cap annualised) and cut its share count from ~404M to 389M in six months. At current prices every $1B of buybacks retires ~1% of shares. That is accretive if our intrinsic value is even roughly right.

## Risks to the call
- Seat contraction becomes visible in ARR, for example if net new ARR falls year over year. This would move us toward the bear case.
- GAAP margins compress faster than modelled from GenAI inference costs. Each 2pp of terminal margin is worth about $13/share.
- A higher discount rate: at 13% WACC, base value falls to ~$264, which is still +10%.
- Data caveat: Yahoo beta (1.42 raw) is volatile. We use a Blume adjustment.

**Catalysts:** Q4 FY26 results and FY27 guidance (mid-Dec 2026), the first strategy update from the new CEO, and Firefly / GenStudio ARR disclosure.

**Rating: BUY.** The base case does not require Adobe to win AI. It only requires the business to decline more slowly than the market fears. *Target $315 (probability-weighted DCF).*

---
*Model: `dcf_model.py` (reproducible: `python dcf_model.py`, or `--offline` for cached data). Outputs: `outputs/ADBE_DCF.xlsx`, sensitivity CSVs, `outputs/adbe_dcf_charts.png`. Not investment advice.*
