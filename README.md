# Market-Radar (JZ2/JZ3)

Automated market sentiment radar for Macro, Equity, and BTC (2.5 BTC DCA Campaign).

## Features
- **Macro (FRED)**: VIX, 10Y, DXY, SOFR, MOVE Index.
- **Equity**: NAAIM, Forward PE, Fear & Greed.
- **BTC Core**: MA200W, MA377D (Binance Native Calc), MVRV Z-Score, Supply Profit.
- **BTC Aux**: 10 Indicators including RSI Weekly, Funding Rate, AHR999 Proxy.

## SSoT Structure
- `scripts/radar.py`: Main data fetcher and renderer (SSoT).
- `scripts/generate_radar.sh`: crontab entry point (JZ3 Topic 205).
