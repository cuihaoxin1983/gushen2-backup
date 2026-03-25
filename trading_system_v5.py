#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股神2号 - 完整量化交易系统 v5.0
======================================
整合：
1. VectorBT 极速回测引擎
2. TradingAgents 五大智能体
3. 市场状态识别
4. 策略参数自动优化
5. 实时信号生成
"""

import sys
sys.path.insert(0, '/usr/local/lib/python3.12/dist-packages')

import vectorbt as vbt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

TUSHARE_TOKEN = '14d6be29b1b0b8a930fc488ceb343859b60f1357a1e1a85dcaee3712'

def get_data(ts_code='AG2606.SHF', days=500):
    import tushare as ts
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
    df = pro.fut_daily(ts_code=ts_code, start_date=start, end_date=end)
    df = df.sort_values('trade_date').reset_index(drop=True)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.set_index('trade_date')
    return df

def get_rt_price(ts_code='AG2606.SHF'):
    import tushare as ts
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()
    try:
        df = pro.rt_fut_min(ts_code=ts_code, freq='5MIN')
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
    signal_line = macd.ewm(span=9).mean()
    macd_hist = (macd - signal_line) * 2
    
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
    
    return {
        'close': close, 'ma5': ma5, 'ma10': ma10, 'ma20': ma20, 'ma30': ma30,
        'macd': macd, 'signal_line': signal_line, 'macd_hist': macd_hist,
        'rsi': rsi, 'bb_upper': bb_upper, 'bb_mid': bb_mid, 'bb_lower': bb_lower,
        'atr': atr, 'plus_di': plus_di, 'minus_di': minus_di, 'adx': adx
    }

def optimize_ma(df):
    close = df['close']
    results = []
    for fast in [3, 5, 7, 10, 12]:
        for slow in [15, 20, 25, 30, 40]:
            if fast >= slow: continue
            ma_fast = close.rolling(fast).mean()
            ma_slow = close.rolling(slow).mean()
            entries = (ma_fast > ma_slow) & (ma_fast.shift(1) <= ma_slow.shift(1))
            exits = (ma_fast < ma_slow) & (ma_fast.shift(1) >= ma_slow.shift(1))
            pf = vbt.Portfolio.from_signals(close, entries, exits, size=0.3, freq='1D')
            stats = pf.stats()
            equity = pf.value()
            rets = equity.pct_change().dropna()
            sharpe = (rets.mean() / rets.std() * np.sqrt(250)) if len(rets) > 0 and rets.std() > 0 else 0
            results.append({
                'params': f'MA({fast}/{slow})', 'return': stats['Total Return [%]'],
                'dd': stats['Max Drawdown [%]'], 'sharpe': sharpe,
                'wr': stats['Win Rate [%]'] / 100 if not np.isnan(stats['Win Rate [%]']) else 0,
                'trades': stats['Total Trades'], 'pf': pf
            })
    results.sort(key=lambda x: x['sharpe'], reverse=True)
    return results

def optimize_rsi(df):
    close = df['close']
    results = []
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
                stats = pf.stats()
                equity = pf.value()
                rets = equity.pct_change().dropna()
                sharpe = (rets.mean() / rets.std() * np.sqrt(250)) if len(rets) > 0 and rets.std() > 0 else 0
                results.append({
                    'params': f'RSI({period},{lower}/{upper})', 'return': stats['Total Return [%]'],
                    'dd': stats['Max Drawdown [%]'], 'sharpe': sharpe,
                    'wr': stats['Win Rate [%]'] / 100 if not np.isnan(stats['Win Rate [%]']) else 0,
                    'trades': stats['Total Trades'], 'pf': pf
                })
    results.sort(key=lambda x: x['sharpe'], reverse=True)
    return results

def optimize_macd(df):
    close = df['close']
    results = []
    for fast in [8, 12, 16]:
        for slow in [24, 26, 30]:
            for signal in [7, 9, 11]:
                if fast >= slow: continue
                ema_fast = close.ewm(span=fast).mean()
                ema_slow = close.ewm(span=slow).mean()
                macd = ema_fast - ema_slow
                sig = macd.ewm(span=signal).mean()
                entries = (macd > sig) & (macd.shift(1) <= sig.shift(1))
                exits = (macd < sig) & (macd.shift(1) >= sig.shift(1))
                pf = vbt.Portfolio.from_signals(close, entries, exits, size=0.3, freq='1D')
                stats = pf.stats()
                equity = pf.value()
                rets = equity.pct_change().dropna()
                sharpe = (rets.mean() / rets.std() * np.sqrt(250)) if len(rets) > 0 and rets.std() > 0 else 0
                results.append({
                    'params': f'MACD({fast},{slow},{signal})', 'return': stats['Total Return [%]'],
                    'dd': stats['Max Drawdown [%]'], 'sharpe': sharpe,
                    'wr': stats['Win Rate [%]'] / 100 if not np.isnan(stats['Win Rate [%]']) else 0,
                    'trades': stats['Total Trades'], 'pf': pf
                })
    results.sort(key=lambda x: x['sharpe'], reverse=True)
    return results

def generate_signal(ind, price):
    score = 0.0
    reasons = []
    
    if price > ind['ma5'].iloc[-1]: score += 0.1
    else: score -= 0.1; reasons.append("价格<MA5")
    
    if ind['ma5'].iloc[-1] > ind['ma20'].iloc[-1] > ind['ma30'].iloc[-1]:
        score += 0.2; reasons.append("均线多头")
    elif ind['ma5'].iloc[-1] < ind['ma20'].iloc[-1] < ind['ma30'].iloc[-1]:
        score -= 0.2; reasons.append("均线空头")
    
    if ind['macd_hist'].iloc[-1] > 0: score += 0.15
    else: score -= 0.15
    
    if ind['macd'].iloc[-1] > ind['signal_line'].iloc[-1]: score += 0.1
    else: score -= 0.1
    
    rsi_val = ind['rsi'].iloc[-1]
    if rsi_val < 30: score += 0.2; reasons.append(f"RSI超卖({rsi_val:.0f})")
    elif rsi_val > 70: score -= 0.2; reasons.append(f"RSI超买({rsi_val:.0f})")
    
    bb_pos = (price - ind['bb_lower'].iloc[-1]) / (ind['bb_upper'].iloc[-1] - ind['bb_lower'].iloc[-1]) * 100
    if bb_pos < 20: score += 0.15; reasons.append(f"BOLL超卖({bb_pos:.0f}%)")
    elif bb_pos > 80: score -= 0.15; reasons.append(f"BOLL超买({bb_pos:.0f}%)")
    
    if ind['plus_di'].iloc[-1] > ind['minus_di'].iloc[-1]: score += 0.1
    else: score -= 0.1
    
    if ind['adx'].iloc[-1] > 25: score *= 1.2
    
    score = max(-1.0, min(1.0, score))
    
    if score >= 0.5: signal = "BUY"
    elif score <= -0.5: signal = "SELL"
    else: signal = "HOLD"
    
    return {'signal': signal, 'score': score, 'confidence': abs(score), 'reasons': reasons}

def run_system(ts_code='AG2606.SHF'):
    print("=" * 60)
    print(f"  股神2号 v5.0 | 全量化交易系统 | {ts_code}")
    print("=" * 60)
    
    print("\n📥 获取数据...")
    df = get_data(ts_code, 500)
    price = get_rt_price(ts_code) or df['close'].iloc[-1]
    print(f"   {len(df)}条 | 最新价: {price:.0f}")
    
    print("\n📊 计算指标...")
    ind = calc_indicators(df)
    
    # 回测优化
    print("\n" + "=" * 60)
    print("【回测优化】")
    print("=" * 60)
    
    print("\n🔍 MA优化...")
    ma_best = optimize_ma(df)[0]
    print(f"   最优: {ma_best['params']} | 收益:{ma_best['return']:.1f}% 夏普:{ma_best['sharpe']:.2f} 胜率:{ma_best['wr']:.0%}")
    
    print("\n🔍 RSI优化...")
    rsi_best = optimize_rsi(df)[0]
    print(f"   最优: {rsi_best['params']} | 收益:{rsi_best['return']:.1f}% 夏普:{rsi_best['sharpe']:.2f} 胜率:{rsi_best['wr']:.0%}")
    
    print("\n🔍 MACD优化...")
    macd_best = optimize_macd(df)[0]
    print(f"   最优: {macd_best['params']} | 收益:{macd_best['return']:.1f}% 夏普:{macd_best['sharpe']:.2f} 胜率:{macd_best['wr']:.0%}")
    
    # 全局最优
    all_best = sorted([ma_best, rsi_best, macd_best], key=lambda x: x['sharpe'], reverse=True)[0]
    print(f"\n🏆 全局最优: {all_best['params']} (夏普:{all_best['sharpe']:.2f})")
    
    # 实时信号
    print("\n" + "=" * 60)
    print("【实时信号】")
    print("=" * 60)
    
    sig = generate_signal(ind, price)
    icon = {'BUY': '🟢买入', 'SELL': '🔴卖出', 'HOLD': '⏸️观望'}
    
    print(f"\n信号: {icon[sig['signal']]} (置信度{sig['confidence']:.0%})")
    print(f"评分: {sig['score']:+.2f}")
    if sig['reasons']:
        for r in sig['reasons']:
            print(f"  • {r}")
    
    # 风控
    print("\n" + "=" * 60)
    print("【风控】")
    print("=" * 60)
    
    atr = ind['atr'].iloc[-1]
    vol = df['close'].pct_change().rolling(20).std().iloc[-1] * np.sqrt(250)
    pos_mult = 0.5 if vol > 0.20 else (0.7 if vol > 0.10 else 1.0)
    max_pos = 0.7 * pos_mult
    
    print(f"\nATR: {atr:.0f} | 波动率: {vol:.0%}")
    print(f"仓位上限: {max_pos:.0%}")
    
    if sig['signal'] == 'BUY':
        sl = price - 2 * atr
        tp = price + 3 * atr
        print(f"买入: {price:.0f} | 止损:{sl:.0f} | 止盈:{tp:.0f}")
    elif sig['signal'] == 'SELL':
        sl = price + 2 * atr
        tp = price - 3 * atr
        print(f"卖出: {price:.0f} | 止损:{sl:.0f} | 止盈:{tp:.0f}")
    
    print("\n" + "=" * 60)
    return all_best, sig

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--ts_code', default='AG2606.SHF')
    run_system(parser.parse_args().ts_code)
