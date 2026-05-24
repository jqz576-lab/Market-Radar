#!/usr/bin/env python3
"""JZ2 Market Radar — live data fetch, threshold scoring, and report output."""

from __future__ import annotations

import datetime
import time
import logging
import os
import re
import statistics
import sys
from dataclasses import dataclass
from typing import Callable, Optional

import requests

TIMEOUT = 15
UA = "Mozilla/5.0 (compatible; JZ2-Radar/1.0)"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA})

logger = logging.getLogger("radar")


def _get_json(url: str, **kwargs) -> dict | list:
    r = SESSION.get(url, timeout=TIMEOUT, **kwargs)
    r.raise_for_status()
    return r.json()


def _to_float(val) -> Optional[float]:
    if val is None or val == "N/A":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


@dataclass
class Check:
    label: str
    value_str: str
    hint: str
    passed: Optional[bool]


def _status(passed: Optional[bool]) -> str:
    if passed is None:
        return "—"
    return "✅" if passed else "❌"


def _score(checks: list[Check]) -> tuple[int, int]:
    scored = [c for c in checks if c.passed is not None]
    if not scored:
        return 0, 0
    return sum(1 for c in scored if c.passed), len(scored)


def _chk(
    label: str,
    value,
    fmt: str,
    hint: str,
    rule: Callable[[Optional[float]], Optional[bool]],
    *,
    unit: str = "",
) -> Check:
    fval = _to_float(value)
    if fval is None:
        vs = "N/A" if value in (None, "N/A") else str(value)
        return Check(label, vs, hint, None)
    return Check(label, fmt.format(fval) + unit, hint, rule(fval))


def get_fred(series_id: str, api_key: str) -> Optional[float]:
    if not api_key:
        return None
    try:
        data = _get_json(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 1,
            },
        )
        raw = data["observations"][0]["value"]
        return None if raw == "." else float(raw)
    except Exception as exc:
        logger.warning("FRED %s failed: %s", series_id, exc)
        return None


def get_yahoo_price(symbol: str) -> Optional[float]:
    try:
        data = _get_json(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={"interval": "1d", "range": "5d"},
        )
        return float(data["chart"]["result"][0]["meta"]["regularMarketPrice"])
    except Exception as exc:
        logger.warning("Yahoo %s failed: %s", symbol, exc)
        return None


def get_naaim() -> Optional[float]:
    try:
        r = SESSION.get(
            "https://www.naaim.org/programs/naaim-exposure-index/",
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        m = re.search(
            r"Exposure Index number is\*?:</h4><div[^>]*>([\d.]+)</div>",
            r.text,
            re.IGNORECASE,
        )
        return float(m.group(1)) if m else None
    except Exception as exc:
        logger.warning("NAAIM scrape failed: %s", exc)
        return None


def get_sp500_pe() -> Optional[float]:
    try:
        r = SESSION.get(
            "https://www.multpl.com/s-p-500-pe-ratio",
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        m = re.search(r"Current S&P 500 PE Ratio is ([0-9.]+)", r.text)
        return float(m.group(1)) if m else None
    except Exception as exc:
        logger.warning("multpl PE failed: %s", exc)
        return None


def get_fear_greed() -> Optional[float]:
    try:
        data = _get_json("https://api.alternative.me/fng/")
        return float(data["data"][0]["value"])
    except Exception as exc:
        logger.warning("Fear/Greed failed: %s", exc)
        return None


BGAPI_BASE = os.environ.get("BGEOMETRICS_API_URL", "https://api.bitcoin-data.com")


def _bgapi_auth_params() -> dict:
    token = (
        os.environ.get("BGEOMETRICS_API_KEY", "").strip()
        or os.environ.get("BGAPI_TOKEN", "").strip()
    )
    return {"token": token} if token else {}


def _bgeometrics_last(metric_path: str, value_key: str) -> Optional[float]:
    """Fetch latest scalar from BGeometrics (bitcoin-data.com)."""
    url = f"{BGAPI_BASE}/v1/{metric_path}/last"
    params = _bgapi_auth_params()
    for attempt in range(2):
        try:
            data = _get_json(url, params=params)
            return float(data[value_key])
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 429 and attempt == 0:
                logger.warning("BGeometrics rate limited, retrying %s", metric_path)
                time.sleep(2)
                continue
            logger.warning("BGeometrics %s failed: %s", metric_path, exc)
            return None
        except Exception as exc:
            logger.warning("BGeometrics %s failed: %s", metric_path, exc)
            return None
    return None


def _onchain_metrics(price: float, daily_closes: list[float]) -> dict:
    supply_profit = _bgeometrics_last("utxos-in-profit-pct", "utxosInProfitPct")
    mvrv_z = _bgeometrics_last("mvrv-zscore", "mvrvZscore")
    mvrv_ratio = _bgeometrics_last("mvrv", "mvrv")

    # sthLthRatio = STH/LTH → LTH% = 100 / (1 + ratio)
    sth_lth = _bgeometrics_last("sth-lth-ratio", "sthLthRatio")
    lth_pct = (100.0 / (1.0 + sth_lth)) if sth_lth is not None and sth_lth >= 0 else None

    bg_ok = any(v is not None for v in (supply_profit, mvrv_z, mvrv_ratio, lth_pct))
    if not bg_ok and len(daily_closes) >= 200:
        realized_proxy = sum(daily_closes[-200:]) / 200
        if mvrv_ratio is None and realized_proxy > 0:
            mvrv_ratio = price / realized_proxy
        if mvrv_z is None:
            std = statistics.pstdev(daily_closes[-200:]) or 1.0
            mvrv_z = (price - realized_proxy) / std
        if supply_profit is None:
            window = daily_closes[-365:]
            supply_profit = sum(1 for c in window if price > c) / len(window) * 100

    return {
        "supply_profit": supply_profit,
        "mvrv_z": mvrv_z,
        "mvrv_ratio": mvrv_ratio,
        "lth_pct": lth_pct,
        "source": "bgeometrics" if bg_ok else "proxy",
    }


def _cryptocompare_daily(limit: int = 2000) -> list[dict]:
    data = _get_json(
        "https://min-api.cryptocompare.com/data/v2/histoday",
        params={"fsym": "BTC", "tsym": "USD", "limit": limit},
    )
    return data["Data"]["Data"]


def _weekly_rsi(closes: list[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, period + 1):
        d = closes[-period - 1 + i] - closes[-period - 2 + i]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + (sum(gains) / period) / avg_loss))



def _get_funding_bybit() -> Optional[float]:
    try:
        data = _get_json(
            "https://api.bybit.com/v5/market/tickers",
            params={"category": "linear", "symbol": "BTCUSDT"},
        )
        row = data["result"]["list"][0]
        return float(row["fundingRate"]) * 100
    except Exception as exc:
        logger.warning("Bybit funding failed: %s", exc)
        return None

def get_btc_market() -> dict:
    out = {
        "price": None,
        "funding": None,
        "ma200w": None,
        "ma377d": None,
        "rsi": None,
        "vol_ratio": None,
        "daily_closes": [],
    }

    try:
        prem = _get_json(
            "https://fapi.binance.com/fapi/v1/premiumIndex",
            params={"symbol": "BTCUSDT"},
        )
        if isinstance(prem, dict) and prem.get("code") == 0 and "msg" in prem:
            raise RuntimeError(prem["msg"])
        out["price"] = float(prem["markPrice"])
        out["funding"] = float(prem["lastFundingRate"]) * 100
        kw = _get_json(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": "BTCUSDT", "interval": "1w", "limit": 200},
        )
        kd = _get_json(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": "BTCUSDT", "interval": "1d", "limit": 400},
        )
        w_closes = [float(k[4]) for k in kw]
        d_closes = [float(k[4]) for k in kd]
        out["daily_closes"] = d_closes
        if len(w_closes) >= 200:
            out["ma200w"] = sum(w_closes[-200:]) / 200
        if len(d_closes) >= 377:
            out["ma377d"] = sum(d_closes[-377:]) / 377
        out["rsi"] = _weekly_rsi(w_closes)
        logger.info("BTC data: Binance")
        return out
    except Exception as exc:
        logger.warning("Binance failed (%s), trying CryptoCompare", exc)

    try:
        days = _cryptocompare_daily(2000)
        d_closes = [float(d["close"]) for d in days]
        out["daily_closes"] = d_closes
        out["price"] = d_closes[-1] if d_closes else None
        if len(d_closes) >= 377:
            out["ma377d"] = sum(d_closes[-377:]) / 377
        if len(d_closes) >= 1400:
            out["ma200w"] = sum(d_closes[-1400:]) / 1400
        weekly = d_closes[::7][-200:]
        out["rsi"] = _weekly_rsi(weekly)
        vols = [float(d["volumefrom"]) for d in days[-30:]]
        if vols:
            out["vol_ratio"] = (sum(vols[-7:]) / 7) / (sum(vols) / len(vols))
        logger.info("BTC data: CryptoCompare")
    except Exception as exc:
        logger.error("CryptoCompare failed: %s", exc)

    if out["funding"] is None:
        out["funding"] = _get_funding_bybit()

    return out


def get_miner_shutdown_price() -> Optional[float]:
    try:
        data = _get_json("https://mempool.space/api/v1/mining/hashrate/1w")
        hashrate = float(data["hashrates"][-1]["avgHashrate"])  # H/s
    except Exception as exc:
        logger.warning("mempool hashrate failed: %s", exc)
        return None

    power_w = float(os.environ.get("MINER_POWER_W", "3250"))
    elec_kwh = float(os.environ.get("MINER_ELEC_USD_KWH", "0.05"))
    eff = float(os.environ.get("MINER_EFFICIENCY_J_TH", "15"))
    network_th = hashrate / 1e12  # TH/s
    miner_th = power_w / eff if eff else 0
    if miner_th <= 0 or network_th <= 0:
        return None
    daily_btc = 3.125 * 144 * (miner_th / network_th)
    daily_cost = (power_w / 1000) * 24 * elec_kwh
    shutdown = daily_cost / daily_btc if daily_btc > 0 else None
    return shutdown if shutdown and shutdown > 100 else None


def get_miner_pressure(daily_closes: list[float]) -> Optional[float]:
    fee_score = 0.5
    try:
        fees = _get_json("https://mempool.space/api/v1/mining/blocks/fees/1w")
        avg_fee = sum(b.get("avgFees", 0) for b in fees) / max(len(fees), 1)
        fee_score = min(avg_fee / 5_000_000, 1.0)
    except Exception:
        pass
    if len(daily_closes) < 30:
        return fee_score
    peak = max(daily_closes[-30:])
    drawdown = (peak - daily_closes[-1]) / peak if peak else 0
    return min(1.0, max(0.0, 0.5 * fee_score + 0.5 * drawdown))


def get_nupl_proxy(price: float, daily_closes: list[float]) -> Optional[float]:
    if len(daily_closes) < 200 or price <= 0:
        return None
    realized = sum(daily_closes[-200:]) / 200
    return (price - realized) / price if realized > 0 else None


def _safe_ahr(price: Optional[float], ma200w: Optional[float]) -> Optional[float]:
    if price is None or ma200w is None or ma200w <= 0:
        return None
    return price / (ma200w * 1.2)


def _lines(checks: list[Check]) -> str:
    return "\n".join(
        f"├ {c.label}: {c.value_str} ({c.hint} {_status(c.passed)})" for c in checks
    )


def build_report() -> tuple[str, bool]:
    fred_key = os.environ.get("FRED_API_KEY", "").strip()

    sofr = get_fred("SOFR", fred_key)
    us2y = get_fred("DGS2", fred_key)
    jp2y = get_fred("IRLTLT01JPM156N", fred_key)
    vix = get_fred("VIXCLS", fred_key)
    jpy = get_fred("DEXJPUS", fred_key)
    spread = (us2y - jp2y) if us2y is not None and jp2y is not None else None

    move = get_yahoo_price("%5EMOVE")
    dxy = get_yahoo_price("DX-Y.NYB")
    naaim = get_naaim()
    sp_pe = get_sp500_pe()

    btc = get_btc_market()
    price = btc["price"]
    onchain = _onchain_metrics(price or 0, btc["daily_closes"])
    ahr = _safe_ahr(price, btc["ma200w"])
    fg = get_fear_greed()
    shutdown = get_miner_shutdown_price()
    miner_p = get_miner_pressure(btc["daily_closes"])
    nupl = get_nupl_proxy(price or 0, btc["daily_closes"])

    if btc["vol_ratio"] is None and len(btc["daily_closes"]) >= 30:
        recent = statistics.pstdev(btc["daily_closes"][-7:])
        base = statistics.pstdev(btc["daily_closes"][-30:]) or 1
        btc["vol_ratio"] = recent / base

    macro_checks = [
        _chk("隔夜利率 SOFR", sofr, "{:.2f}", "<5.5%", lambda v: v < 5.5, unit="%"),
        _chk("MOVE 指数", move, "{:.2f}", "<80", lambda v: v < 80),
        _chk("美元指数 DXY", dxy, "{:.2f}", "<105", lambda v: v < 105),
        _chk("USD/JPY", jpy, "{:.2f}", "<150", lambda v: v < 150),
        _chk("US2Y-JP2Y 利差", spread, "{:.2f}", ">0%", lambda v: v > 0, unit="%"),
    ]
    macro_total = len(macro_checks)
    macro_pass = sum(1 for c in macro_checks if c.passed is True)
    macro_scored = [c for c in macro_checks if c.passed is not None]
    macro_pass_scored = sum(1 for c in macro_scored if c.passed)
    macro_verdict = (
        "宽松"
        if macro_scored and macro_pass_scored >= max(2, len(macro_scored) * 0.6)
        else ("中性" if macro_scored and macro_pass_scored >= len(macro_scored) * 0.4 else "紧缩")
    )

    equity_checks = [
        _chk("机构头寸 NAAIM", naaim, "{:.1f}", "≥80 见顶", lambda v: v >= 80, unit="%"),
        Check("散户买入流 Retail", "暂无数据", "—", None),
        _chk("标普500 PE (trailing)", sp_pe, "{:.1f}", "≥22 偏贵", lambda v: v >= 22, unit="x"),
        Check("HF 杠杆率 Leverage", "N/A", "需数据源", None),
        _chk("恐慌指数 VIX", vix, "{:.2f}", "≥20 恐慌", lambda v: v >= 20),
    ]
    equity_total = len(equity_checks)
    equity_pass = sum(1 for c in equity_checks if c.passed is True)
    equity_verdict = "有" if equity_pass >= 2 else "无"

    ma200w, ma377d = btc["ma200w"], btc["ma377d"]
    core_checks = [
        _chk(
            "盈亏供应量 Supply Profit",
            onchain["supply_profit"],
            "{:.1f}",
            "<25% 抄底",
            lambda v: v < 25,
            unit="%",
        ),
        _chk("MVRV Z-Score", onchain["mvrv_z"], "{:.2f}", "<0.5 低估", lambda v: v < 0.5),
        Check(
            "200周均线 MA200W",
            f"${ma200w:,.0f}" if ma200w else "N/A",
            f"Price ${price:,.0f}" if price else "—",
            True if price and ma200w and price > ma200w else (False if price and ma200w else None),
        ),
        Check(
            "377日均线 MA377D",
            f"${ma377d:,.0f}" if ma377d else "N/A",
            "Price>MA" if price and ma377d and price > ma377d else "Price<MA",
            True if price and ma377d and price > ma377d else (False if price and ma377d else None),
        ),
    ]
    core_total = len(core_checks)
    core_pass = sum(1 for c in core_checks if c.passed is True)

    aux_checks = [
        _chk("RSI 周线", btc["rsi"], "{:.1f}", "30–70", lambda v: 30 <= v <= 70),
        _chk("社交情绪", fg, "{:.0f}", "≤25 恐惧", lambda v: v <= 25),
        _chk(
            "资金费率",
            btc["funding"],
            "{:.4f}",
            "<0.01%",
            lambda v: abs(v) < 0.01,
            unit="%",
        ),
        _chk("AHR999 指标", ahr, "{:.2f}", "<0.45 定投", lambda v: v < 0.45),
        _chk("MVRV Ratio", onchain["mvrv_ratio"], "{:.2f}", "<1.0 低估", lambda v: v < 1.0),
        _chk("LTH 供应占比", onchain["lth_pct"], "{:.1f}", ">60%", lambda v: v > 60, unit="%"),
        _chk(
            "矿工关机价",
            shutdown,
            "${:,.0f}",
            f"vs ${price:,.0f}" if price else "—",
            lambda v: price is not None and v < price,
        ),
        _chk("未实现盈亏 NUPL", nupl, "{:.2f}", "<0 低估", lambda v: v < 0),
        _chk("矿工压力", miner_p, "{:.2f}", "<0.6 正常", lambda v: v < 0.6),
        _chk("成交量比率", btc["vol_ratio"], "{:.2f}", "<1.0", lambda v: v < 1.0),
    ]
    aux_total = len(aux_checks)
    aux_pass = sum(1 for c in aux_checks if c.passed is True)

    bottom_hits = core_pass + sum(
        1 for c in aux_checks if c.passed and c.label in ("AHR999 指标", "社交情绪", "MVRV Ratio")
    )
    if core_pass >= 2 or (ahr is not None and ahr < 0.45):
        btc_verdict = "有 (考虑定投)"
    elif bottom_hits >= 1:
        btc_verdict = "弱"
    else:
        btc_verdict = "无 (持币待涨)"

    onchain_note = ""
    if onchain.get("source") == "proxy":
        onchain_note = "\nℹ️ 链上指标为价格代理（BGeometrics 不可用）；可设置 BGEOMETRICS_API_KEY 提高限额"

    ts = datetime.datetime.now().strftime("%m/%d %H:%M")
    ok = price is not None and price > 0
    report = f"""🚨 JZ2 RADAR {ts}
━━━━━━━━━━━━━━━━━━

📊 1. 宏观流动性 MACRO ({macro_pass}/{macro_total})
{_lines(macro_checks)}

🦅 2. 美股市场情绪 EQUITY ({equity_pass}/{equity_total})
{_lines(equity_checks)}

🎯 3. BTC 核心指标 CORE ({core_pass}/{core_total})
{_lines(core_checks)}

🔍 4. BTC 辅助监测指标 AUX ({aux_pass}/{aux_total})
{_lines(aux_checks)}

━━━━━━━━━━━━━━━━━━
📌 结论
├ 宏观 - 流动性判定: {macro_verdict}
├ 美股 - 见顶迹象: {equity_verdict}
├ BTC - 抄底信号: {btc_verdict}
{onchain_note}
"""
    return report, ok


def post_slack(report: str) -> None:
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not webhook:
        logger.info("SLACK_WEBHOOK_URL not set; skipping Slack")
        return
    try:
        SESSION.post(webhook, json={"text": report}, timeout=TIMEOUT).raise_for_status()
        logger.info("Slack post OK")
    except Exception as exc:
        logger.error("Slack post failed: %s", exc)


def main() -> int:
    logging.basicConfig(
        level=getattr(logging, os.environ.get("RADAR_LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if not os.environ.get("FRED_API_KEY", "").strip():
        logger.warning("FRED_API_KEY missing — macro series will be N/A")

    report, ok = build_report()
    print(report)
    post_slack(report)
    if not ok:
        logger.error("BTC price unavailable")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
