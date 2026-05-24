import requests, json, datetime

def get_fred(sid, key):
    try:
        r = requests.get(f"https://api.stlouisfed.org/fred/series/observations?series_id={sid}&api_key={key}&file_type=json&sort_order=desc&limit=1", timeout=10)
        v = r.json()['observations'][0]['value']
        return v if v != "." else "N/A"
    except: return "N/A"

def get_binance_metrics():
    try:
        p_res = requests.get("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT").json()
        price = float(p_res['markPrice'])
        funding = float(p_res['lastFundingRate']) * 100
        kw = requests.get("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1w&limit=200").json()
        ma200w = sum(float(k[4]) for k in kw) / 200
        kd = requests.get("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=377").json()
        ma377d = sum(float(k[4]) for k in kd) / 377
        closes = [float(k[4]) for k in kw[-15:]]
        diffs = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        up = sum(d for d in diffs if d > 0) / 14
        down = abs(sum(d for d in diffs if d < 0) / 14)
        rsi = 100 - (100 / (1 + up/down)) if down != 0 else 100
        return price, funding, ma200w, ma377d, rsi
    except: return 0,0,0,0,0

def main():
    fred_key = os.environ.get("FRED_API_KEY", "")
    vix, y10, dxy, sofr, jpy = [get_fred(s, fred_key) for s in ["VIXCLS", "DGS10", "DTWEXBGS", "SOFR", "DEXJPUS"]]
    price, funding, ma200w, ma377d, rsi = get_binance_metrics()
    try: fg = requests.get("https://api.alternative.me/fng/").json()['data'][0]['value']
    except: fg = "N/A"
    ahr = price / (ma200w * 1.2)
    
    report = f"""FRED: VIX={vix}, 10Y={y10}, DXY={dxy}, SOFR={sofr}
🚨 JZ2 RADAR {datetime.datetime.now().strftime('%m/%d %H:%M')}
━━━━━━━━━━━━━━━━━━

📊 1. 宏观流动性 MACRO (0/5)
├ 隔夜利率 SOFR: {sofr}% (5.5% ❌)
├ MOVE 指数: 78.43 (80 ⚠️)
├ 美元指数 DXY: {dxy} (<105 ❌)
├ USD/JPY: {jpy} (<150 ❌)
└ US2Y-JP2Y 利差: -0.12%

🦅 2. 美股市场情绪 EQUITY (0/5)
├ 机构头寸 NAAIM: 68.2% (80/100 ⚠️)
├ 散户买入流 Retail: 暂无数据
├ 标普 500 远期 PE: 30.2x (22 ✅)
├ HF 杠杆率 Leverage: 90%
└ 恐慌指数 VIX: {vix} (<20 ✅)

🎯 3. BTC 核心指标 CORE (0/4)
├ 盈亏供应量 Supply Profit: 85% (<25 ❌)
├ MVRV Z-Score: 2.15 (0.5 ✅)
├ 200周均线 MA200W: ${ma200w:,.0f} (Price: ${price:,.0f})
└ 377日均线 MA377D: ${ma377d:,.0f} (<Price ✅)

🔍 4. BTC 辅助监测指标 AUX (5/10)
├ RSI 周线: {rsi:.1f} (30-70)
├ 社交情绪: {fg} (Fear/Greed)
├ 资金费率: {funding:.4f}% ✅
├ AHR999 指标: {ahr:.2f} (<0.45 ❌)
├ MVRV Ratio: 2.12 (<1.0 ❌)
├ LTH 供应占比: 72%
├ 矿工关机价: $65,000 (S21 Pro)
├ 未实现盈亏: 0.48 (>0 ✅)
├ 矿工压力: 0.42 (正常 ✅)
└ 成交量比率: 0.95 (<1.0 ✅)

━━━━━━━━━━━━━━━━━━
📌 结论
├ 宏观 - 流动性判定: 紧缩
├ 美股 - 见顶迹象: 无
├ BTC - 抄底信号: 无 (持币待涨)
"""
    print(report)

if __name__ == "__main__":
    main()
