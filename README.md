# Market-Radar

A self-hosted market macro monitoring system (**Radar**). Unlike typical price tickers, Radar is a decision-support framework focused on **market fundamentals** and **global macro liquidity**, helping long-term investors gauge buy and sell zones across macro cycles.

## Overview

### Core monitoring dimensions

**1. Macro liquidity (Macro Liquidity)**

- Syncs global liquidity indicators in near real time: MOVE index, DXY (U.S. dollar index), SOFR overnight rate, and related FRED/Yahoo series.
- Classifies the macro backdrop as **tight**, **neutral**, or **loose** to reflect where liquidity stands for risk assets.

**2. BTC core fundamentals (accumulation signals)**

- Tracks MVRV, MVRV Z-Score, 200-week moving average, 377-day moving average, and supply-in-profit style metrics via [BGeometrics](https://bitcoin-data.com) (with price-based fallbacks).
- Includes an **AHR999**-style hoarding index proxy to flag potential dollar-cost-averaging / accumulation zones.

**3. Sentiment & auxiliary filters**

- Fear & Greed Index, funding rates, miner pressure, RSI, and other aux metrics to reduce noise from short-term sentiment.

### Why Radar

- **Global lens** — Focus on macro liquidity and long-term moving averages instead of single-day volatility.
- **Quiet automation** — No manual spreadsheets; structured reports on a schedule or on demand.
- **You own the stack** — Private deployment, transparent Python logic, and room to add your own indicators.

### Who it is for

- Long-term investors who want to avoid FUD/FOMO noise.
- Rational allocators who want data behind DCA or de-risking decisions.
- Users with basic Linux/Python who prefer systematic portfolio monitoring.

---

## Features (technical)

- **Macro**: SOFR, MOVE (Yahoo `^MOVE`), ICE DXY (Yahoo `DX-Y.NYB`), USD/JPY, US2Y–JP2Y spread (FRED)
- **Equity**: NAAIM Exposure Index, S&P 500 trailing P/E (multpl), VIX (FRED)
- **BTC Core**: Supply in profit, MVRV Z-Score, MA200W, MA377D (377D shown on a separate line under MA200W)
- **BTC Aux**: Weekly RSI, Fear & Greed, funding rate, AHR999, MVRV, miner shutdown estimate, NUPL proxy, miner pressure, volume ratio

Live threshold scoring drives ✅/❌ marks and section conclusions (no hardcoded placeholder values).

## Project layout

- `scripts/radar.py` — main data fetcher, scorer, and renderer (single source of truth)
- `scripts/generate_radar.sh` — cron-friendly wrapper with logging
- `requirements.txt` — Python dependencies

## Setup

```bash
pip install -r requirements.txt
export FRED_API_KEY=your_32_char_fred_key   # required for macro + VIX
# Optional — BGeometrics token (free tier works without a key)
export BGEOMETRICS_API_KEY=...
# Optional — Slack webhook
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
| On-chain (MVRV, supply profit, LTH) | BGeometrics (bitcoin-data.com) | Price-based proxy |
| Miner shutdown | mempool.space hashrate | — |

## Cron example

```cron
0 8 * * * /path/to/Market-Radar/scripts/generate_radar.sh
```
