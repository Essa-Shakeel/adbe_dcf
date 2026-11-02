# Adobe (ADBE) DCF Model

Python discounted cash flow model for Adobe. It pulls reported financials from SEC EDGAR (XBRL companyfacts) and market data from Yahoo Finance, then builds a 10-year unlevered FCF forecast under bear/base/bull scenarios. WACC comes from CAPM. Terminal value uses Gordon growth, with an exit-multiple cross-check, sensitivity tables and a reverse DCF.

Result as of Oct 9, 2026: probability-weighted value ~$314/share vs. a $241.05 price. See `ADBE_writeup.md` for the full write-up.

## Usage

```bash
pip install numpy pandas openpyxl matplotlib
python dcf_model.py              # live pull, writes ./outputs
python dcf_model.py --offline    # reuse cached ./data JSON
python dcf_model.py --price 250 --rf 0.045 --erp 0.055
```

SEC requests send a `User-Agent` header with a contact email (required by SEC fair-access policy). Edit `SEC_HEADERS` in `dcf_model.py` to use your own.

## Contents

| Path | What it is |
|---|---|
| `dcf_model.py` | The model |
| `ADBE_writeup.md` | Investment write-up |
| `data/` | Cached SEC and market data snapshot |
| `outputs/` | Excel model, charts, scenario and sensitivity tables |

## Disclaimer

For educational purposes only. Not investment advice, and not a recommendation to buy or sell any security. Forecasts are assumptions and may be wrong.

## License

MIT, see `LICENSE`.
