#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股神2号 - 完整量化交易系统 v5.1
======================================
改进：
- DMI策略优化（含趋势确认过滤）
- 多周期共振信号
- 交易信号评分系统
- 策略排行榜
"""

import sys
sys.path.insert(0, '/usr/local/lib/python3.12/dist-packages')

import vectorbt as vbt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

TUSHARE_TOKEN = '14d6be29b1b0b8a930fc488ceb343859b60f1357a1e1a85dcaee3712'

def get_data(days=500):
    import tushare as ts
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
    df = pro.fut_daily(ts_code='AG2606.SHF', start_date=start, end_date=end)
    df = df.sort_values('trade_date').reset_index(drop=True)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.set_index('trade_date')
    return df

def get_rt():
    import tushare as ts
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()
    try:
        df = pro.rt_fut_min(ts_code='AG2606.SHF', freq='5MIN')
        return df['close'].iloc[-1] if len(df) > 0 else None
    except:
        return None

def calc_indicators(df):
    close = df['close']
    high = df['high']
    low = df['low']
    
    ma5 = close.rolling(5).mean()
    ma10 = close.rolling(10).mean()
    ma20 = close.rolling(20).mean()
    ma30 = close.rolling(30).mean()
    
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    macd_hist = (macd - signal) * 2
    
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
    plus_di = (plus_dm.rolling(14).mean() / atr) * 100
    minus_di = (minus_dm.rolling(14).mean() / atr) * 100
    dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100
    adx = dx.rolling(14).mean()
    
    vol = close.pct_change().rolling(20).std().iloc[-1] * np.sqrt(250)
    
    return {
        'close': close, 'ma5': ma5, 'ma10': ma10, 'ma20': ma20, 'ma30': ma30,
        'macd': macd, 'signal': signal, 'macd_hist': macd_hist,
        'rsi': rsi, 'bb_upper': bb_upper, 'bb_mid': bb_mid, 'bb_lower': bb_lower,
        'atr': atr, 'plus_di': plus_di, 'minus_di': minus_di, 'adx': adx,
        'vol': vol
    }

def optimize(strategy, df):
    close = df['close']
    results = []
    
    if strategy == 'MA':
        for fast in [3, 5, 7, 10]:
            for slow in [15, 20, 25, 30, 40]:
                if fast >= slow: continue
                mf = close.rolling(fast).mean()
                ms = close.rolling(slow).mean()
                entries = (mf > ms) & (mf.shift(1) <= ms.shift(1))
                exits = (mf < ms) & (mf.shift(1) >= ms.shift(1))
                pf = vbt.Portfolio.from_signals(close, entries, exits, size=0.3, freq='1D')
                s = pf.stats()
                eq = pf.value()
                rets = eq.pct_change().dropna()
                sh = (rets.mean()/rets.std()*np.sqrt(250)) if len(rets)>0 and rets.std()>0 else 0
                results.append({'params': f'MA({fast}/{slow})', 'ret': s['Total Return [%]'], 'dd': s['Max Drawdown [%]'], 'sharpe': sh, 'wr': s['Win Rate [%]']/100 if not np.isnan(s['Win Rate [%]']) else 0, 'trades': int(s['Total Trades']), 'pf': pf})
    
    elif strategy == 'RSI':
        for period in [10, 14, 20]:
            for lower in [20, 25, 30]:
                for upper in [70, 75, 80]:
                    delta = close.diff()
                    gain = delta.where(delta > 0, 0).rolling(period).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
                    rs = gain / loss.replace(0, np.nan)
                    rsi = 100 - (100 / (1 + rs))
                    entries = rsi < lower
                    exits = rsi > upper
                    pf = vbt.Portfolio.from_signals(close, entries, exits, size=0.3, freq='1D')
                    s = pf.stats()
                    eq = pf.value()
                    rets = eq.pct_change().dropna()
                    sh = (rets.mean()/rets.std()*np.sqrt(250)) if len(rets)>0 and rets.std()>0 else 0
                    results.append({'params': f'RSI({period},{lower}/{upper})', 'ret': s['Total Return [%]'], 'dd': s['Max Drawdown [%]'], 'sharpe': sh, 'wr': s['Win Rate [%]']/100 if not np.isnan(s['Win Rate [%]']) else 0, 'trades': int(s['Total Trades']), 'pf': pf})
    
    elif strategy == 'MACD':
        for fast in [8, 12, 16]:
            for slow in [24, 26, 30]:
                for signal in [7, 9, 11]:
                    if fast >= slow: continue
                    ef = close.ewm(span=fast).mean()
                    es = close.ewm(span=slow).mean()
                    macd = ef - es
                    sig = macd.ewm(span=signal).mean()
                    entries = (macd > sig) & (macd.shift(1) <= sig.shift(1))
                    exits = (macd < sig) & (macd.shift(1) >= sig.shift(1))
                    pf = vbt.Portfolio.from_signals(close, entries, exits, size=0.3, freq='1D')
                    s = pf.stats()
                    eq = pf.value()
                    rets = eq.pct_change().dropna()
                    sh = (rets.mean()/rets.std()*np.sqrt(250)) if len(rets)>0 and rets.std()>0 else 0
                    results.append({'params': f'MACD({fast},{slow},{signal})', 'ret': s['Total Return [%]'], 'dd': s['Max Drawdown [%]'], 'sharpe': sh, 'wr': s['Win Rate [%]']/100 if not np.isnan(s['Win Rate [%]']) else 0, 'trades': int(s['Total Trades']), 'pf': pf})
    
    elif strategy == 'DMI':
        for period in [10, 14, 20]:
            high = df['high']
            low = df['low']
            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(period).mean()
            plus_dm = high.diff()
            minus_dm = -low.diff()
            plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
            minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
            plus_di = (plus_dm.rolling(period).mean() / atr) * 100
            minus_di = (minus_dm.rolling(period).mean() / atr) * 100
            dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100
            adx = dx.rolling(period).mean()
            for adx_th in [20, 25, 30]:
                entries = (plus_di > minus_di) & (adx > adx_th)
                exits = (plus_di < minus_di) | (adx < adx_th - 5)
                pf = vbt.Portfolio.from_signals(close, entries, exits, size=0.3, freq='1D')
                s = pf.stats()
                eq = pf.value()
                rets = eq.pct_change().dropna()
                sh = (rets.mean()/rets.std()*np.sqrt(250)) if len(rets)>0 and rets.std()>0 else 0
                results.append({'params': f'DMI({period},ADX>{adx_th})', 'ret': s['Total Return [%]'], 'dd': s['Max Drawdown [%]'], 'sharpe': sh, 'wr': s['Win Rate [%]']/100 if not np.isnan(s['Win Rate [%]']) else 0, 'trades': int(s['Total Trades']), 'pf': pf})
    
    results.sort(key=lambda x: x['sharpe'], reverse=True)
    return results

def get_signal(ind, price):
    score = 0.0
    reasons = []
    
    # MA
    if price > ind['ma5'].iloc[-1]: score += 0.1
    else: score -= 0.1; reasons.append("价格<MA5")
    
    if ind['ma5'].iloc[-1] > ind['ma20'].iloc[-1] > ind['ma30'].iloc[-1]:
        score += 0.2; reasons.append("均线多头")
    elif ind['ma5'].iloc[-1] < ind['ma20'].iloc[-1] < ind['ma30'].iloc[-1]:
        score -= 0.2; reasons.append("均线空头")
    
    # MACD
    if ind['macd_hist'].iloc[-1] > 0: score += 0.15
    else: score -= 0.15
    
    if ind['macd'].iloc[-1] > ind['signal'].iloc[-1]: score += 0.1
    else: score -= 0.1
    
    # RSI
    rsi = ind['rsi'].iloc[-1]
    if rsi < 30: score += 0.2; reasons.append(f"RSI超卖({rsi:.0f})")
    elif rsi > 70: score -= 0.2; reasons.append(f"RSI超买({rsi:.0f})")
    
    # BOLL
    bb_pos = (price - ind['bb_lower'].iloc[-1]) / (ind['bb_upper'].iloc[-1] - ind['bb_lower'].iloc[-1]) * 100
    if bb_pos < 20: score += 0.15; reasons.append(f"BOLL超卖({bb_pos:.0f}%)")
    elif bb_pos > 80: score -= 0.15; reasons.append(f"BOLL超买({bb_pos:.0f}%)")
    
    # DMI
    if ind['plus_di'].iloc[-1] > ind['minus_di'].iloc[-1]: score += 0.1
    else: score -= 0.1
    
    if ind['adx'].iloc[-1] > 25: score *= 1.2
    
    score = max(-1.0, min(1.0, score))
    
    if score >= 0.5: sig = "BUY"
    elif score <= -0.5: sig = "SELL"
    else: sig = "HOLD"
    
    return sig, score, abs(score), reasons

def run():
    print("=" * 60)
    print("  股神2号 v5.1 | 全量化交易系统")
    print("=" * 60)
    
    print("\n📥 获取数据...")
    df = get_data(500)
    price = get_rt() or df['close'].iloc[-1]
    print(f"   {len(df)}条 | {df.index[0].strftime('%Y-%m-%d')} ~ {df.index[-1].strftime('%Y-%m-%d')}")
    print(f"   实时价格: {price:.0f}")
    
    print("\n📊 计算指标...")
    ind = calc_indicators(df)
    
    # 优化
    print("\n" + "=" * 60)
    print("【策略排行榜】(按夏普比率)")
    print("=" * 60)
    
    all_results = []
    for strat in ['MA', 'RSI', 'MACD', 'DMI']:
        results = optimize(strat, df)
        if results:
            best = results[0]
            all_results.append(best)
            print(f"  {strat}: {best['params']} | 收益:{best['ret']:.1f}% 夏普:{best['sharpe']:.2f} 胜率:{best['wr']:.0%} 交易:{best['trades']}")
    
    all_results.sort(key=lambda x: x['sharpe'], reverse=True)
    best = all_results[0] if all_results else None
    
    print("-" * 60)
    if best:
        print(f"  🏆 全局最优: {best['params']} (夏普{best['sharpe']:.2f})")
    
    # 信号
    print("\n" + "=" * 60)
    print("【实时信号】")
    print("=" * 60)
    
    sig, sc, conf, reasons = get_signal(ind, price)
    
    icon = {'BUY': '🟢买入', 'SELL': '🔴卖出', 'HOLD': '⏸️观望'}
    color = {'BUY': '32', 'SELL': '91', 'HOLD': '33'}
    
    print(f"\n  综合信号: \033[{color[sig]}m{icon[sig]}\033[0m (置信度{conf:.0%})")
    print(f"  评分: {sc:+.2f}")
    
    # 指标详情
    rsi = ind['rsi'].iloc[-1]
    bb_pos = (price - ind['bb_lower'].iloc[-1]) / (ind['bb_upper'].iloc[-1] - ind['bb_lower'].iloc[-1]) * 100
    adx = ind['adx'].iloc[-1]
    plus_d = ind['plus_di'].iloc[-1]
    minus_d = ind['minus_di'].iloc[-1]
    
    print(f"\n  指标状态:")
    print(f"    RSI(14): {rsi:.0f} {'超卖' if rsi<30 else '超买' if rsi>70 else '正常'}")
    print(f"    BOLL: {bb_pos:.0f}% {'超卖' if bb_pos<20 else '超买' if bb_pos>80 else '中性'}")
    print(f"    DMI: +{plus_d:.1f}/-{minus_d:.1f} {'多头' if plus_d>minus_d else '空头'}")
    print(f"    ADX: {adx:.1f} {'强趋势' if adx>25 else '震荡'}")
    
    if reasons:
        print(f"  信号依据:")
        for r in reasons:
            print(f"    • {r}")
    
    # 风控
    print("\n" + "=" * 60)
    print("【风控】")
    print("=" * 60)
    
    atr = ind['atr'].iloc[-1]
    vol = ind['vol']
    pos_mult = 0.5 if vol > 0.20 else (0.7 if vol > 0.10 else 1.0)
    max_pos = 0.7 * pos_mult
    
    print(f"\n  ATR: {atr:.0f} | 波动率: {vol:.0%} {'极高' if vol>0.20 else '高' if vol>0.10 else '正常'}")
    print(f"  仓位上限: {max_pos:.0%}")
    
    if sig == 'BUY':
        sl = price - 2 * atr
        tp = price + 3 * atr
        rr = 1.5
        print(f"\n  🟢 买入: {price:.0f}")
        print(f"     止损: {sl:.0f} ({2*atr:.0f}点)")
        print(f"     止盈: {tp:.0f} ({3*atr:.0f}点)")
        print(f"     盈亏比: 1:{rr:.1f}")
    elif sig == 'SELL':
        sl = price + 2 * atr
        tp = price - 3 * atr
        rr = 1.5
        print(f"\n  🔴 卖出: {price:.0f}")
        print(f"     止损: {sl:.0f} ({2*atr:.0f}点)")
        print(f"     止盈: {tp:.0f} ({3*atr:.0f}点)")
        print(f"     盈亏比: 1:{rr:.1f}")
    else:
        print(f"\n  ⏸️ 观望")
        print(f"     等待明确信号后再操作")
    
    # 关键价位
    print(f"\n  关键价位:")
    print(f"     支撑1: {ind['bb_lower'].iloc[-1]:.0f} (布林下轨)")
    print(f"     支撑2: {ind['ma20'].iloc[-1]:.0f} (MA20)")
    print(f"     当前: {price:.0f}")
    print(f"     压力1: {ind['bb_upper'].iloc[-1]:.0f} (布林上轨)")
    
    print("\n" + "=" * 60)
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

if __name__ == '__main__':
    run()
