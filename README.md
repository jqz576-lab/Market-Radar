# Market-Radar (JZ2/JZ3)

Automated market sentiment radar for Macro, Equity, and BTC (2.5 BTC DCA Campaign).

## Features

- **Macro**: SOFR, MOVE (Yahoo `^MOVE`), ICE DXY (Yahoo `DX-Y.NYB`), USD/JPY, US2Y–JP2Y spread (FRED)
- **Equity**: NAAIM Exposure Index, S&P 500 trailing P/E (multpl), VIX (FRED)
- **BTC Core**: Supply in profit, MVRV Z-Score, MA200W, MA377D
- **BTC Aux**: Weekly RSI, Fear & Greed, funding rate, AHR999, MVRV, miner shutdown estimate, NUPL proxy, miner pressure, volume ratio

All thresholds drive live ✅/❌ scoring and section conclusions (no hardcoded placeholder values).

## SSoT Structure

- `scripts/radar.py` — main data fetcher, scorer, and renderer (SSoT)
- `scripts/generate_radar.sh` — crontab entry point (JZ3 Topic 205)
- `requirements.txt` — Python dependencies

## Setup

```bash
pip install -r requirements.txt
export FRED_API_KEY=your_32_char_fred_key   # required for macro + VIX
# Optional — higher-quality on-chain data:
export BITBO_API_KEY=...
export GLASSNODE_API_KEY=...
# Optional — Slack push (Topic 205):
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

Copy `.env.example` to `.env` for `generate_radar.sh` to auto-load.

## Run

```bash
python3 scripts/radar.py
# or
./scripts/generate_radar.sh
```

Logs append to `logs/radar-YYYYMMDD.log` when using the shell wrapper.

## Data sources & fallbacks

| Metric | Primary | Fallback |
|--------|---------|----------|
| BTC price / MAs | Binance | CryptoCompare |
| Funding | Binance futures | Bybit linear |
| MOVE / DXY | Yahoo Finance | — |
| Macro rates | FRED | — |
| NAAIM | naaim.org scrape | — |
| S&P PE | multpl.com | — |
| On-chain (MVRV, supply profit) | Bitbo / Glassnode | Price-based proxy |
| Miner shutdown | mempool.space hashrate | — |

## Cron example

```cron
0 8 * * * /path/to/Market-Radar/scripts/generate_radar.sh
```
