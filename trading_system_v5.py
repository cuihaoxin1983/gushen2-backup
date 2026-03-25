#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股神2号 - 完整量化交易系统 v5.2
======================================
进化内容：
1. 交易成本模型（手续费+滑点）
2. 资金管理（凯利公式）
3. 多维风险评估（夏普/Sortino/Calmar）
4. 策略稳定性评分
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

def run_backtest(close, entries, exits, fees=0.0003, slippage=0.0002):
    """执行回测并返回多维指标"""
    try:
        pf = vbt.Portfolio.from_signals(
            close, entries, exits,
            size=0.3, freq='1D',
            fixed_fees=fees,
            slippage=slippage,
            init_cash=100000
        )
        s = pf.stats()
        eq = pf.value()
        rets = eq.pct_change().dropna()
        
        if len(rets) > 0 and rets.std() > 0:
            sharpe = rets.mean() / rets.std() * np.sqrt(250)
            downside = rets[rets < 0]
            sortino = (rets.mean() / downside.std() * np.sqrt(250)) if len(downside) > 0 and downside.std() > 0 else 0
            peak = eq.cummax()
            dd = (peak - eq) / peak
            max_dd = dd.max()
            calmar = (rets.mean() * 250) / max_dd if max_dd > 0 else 0
            wins = rets[rets > 0].sum()
            losses = abs(rets[rets < 0].sum())
            pf_ratio = wins / losses if losses > 0 else 999
        else:
            sharpe = sortino = calmar = pf_ratio = 0
        
        stability = (sharpe * 0.4 + sortino * 0.3 + min(calmar, 3) * 0.3) if sharpe > 0 else 0
        wr = s['Win Rate [%]'] / 100 if not np.isnan(s['Win Rate [%]']) else 0
        
        return {
            'ret': s['Total Return [%]'],
            'dd': s['Max Drawdown [%]'],
            'sharpe': sharpe,
            'sortino': sortino,
            'calmar': calmar,
            'pf': pf_ratio,
            'stability': stability,
            'wr': wr,
            'trades': int(s['Total Trades']),
            'fees': s.get('Total Fees Paid', 0),
            'pf_obj': pf
        }
    except Exception as e:
        return None

def optimize(df):
    """策略优化"""
    close = df['close']
    results = []
    
    # MA优化
    for fast in [3, 5, 7, 10]:
        for slow in [15, 20, 25, 30, 40]:
            if fast >= slow: continue
            mf = close.rolling(fast).mean()
            ms = close.rolling(slow).mean()
            entries = (mf > ms) & (mf.shift(1) <= ms.shift(1))
            exits = (mf < ms) & (mf.shift(1) >= ms.shift(1))
            r = run_backtest(close, entries, exits)
            if r:
                r['params'] = f'MA({fast}/{slow})'
                results.append(r)
    
    # MACD优化
    for fast in [8, 12, 16]:
        for slow in [24, 26, 30]:
            for sig in [7, 9, 11]:
                if fast >= slow: continue
                ef = close.ewm(span=fast).mean()
                es = close.ewm(span=slow).mean()
                macd = ef - es
                signal = macd.ewm(span=sig).mean()
                entries = (macd > signal) & (macd.shift(1) <= signal.shift(1))
                exits = (macd < signal) & (macd.shift(1) >= signal.shift(1))
                r = run_backtest(close, entries, exits)
                if r:
                    r['params'] = f'MACD({fast},{slow},{sig})'
                    results.append(r)
    
    # DMI优化
    high = df['high']
    low = df['low']
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    plus_dm = high.diff().where(lambda x: (x > 0) & (x > -low.diff()), 0)
    minus_dm = (-low.diff()).where(lambda x: (x > 0) & (x > high.diff()), 0)
    plus_di = (plus_dm.rolling(14).mean() / atr) * 100
    minus_di = (minus_dm.rolling(14).mean() / atr) * 100
    dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100
    adx = dx.rolling(14).mean()
    
    for period in [10, 14, 20]:
        for adx_th in [20, 25, 30]:
            entries = (plus_di > minus_di) & (adx > adx_th)
            exits = (plus_di < minus_di) | (adx < adx_th - 5)
            r = run_backtest(close, entries, exits)
            if r:
                r['params'] = f'DMI({period},ADX>{adx_th})'
                results.append(r)
    
    results.sort(key=lambda x: x['sharpe'], reverse=True)
    return results

def get_signal(ind, price):
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
    
    if ind['macd'].iloc[-1] > ind['signal'].iloc[-1]: score += 0.1
    else: score -= 0.1
    
    rsi = ind['rsi'].iloc[-1]
    if rsi < 30: score += 0.2; reasons.append(f"RSI超卖({rsi:.0f})")
    elif rsi > 70: score -= 0.2; reasons.append(f"RSI超买({rsi:.0f})")
    
    bb_pos = (price - ind['bb_lower'].iloc[-1]) / (ind['bb_upper'].iloc[-1] - ind['bb_lower'].iloc[-1]) * 100
    if bb_pos < 20: score += 0.15; reasons.append(f"BOLL超卖({bb_pos:.0f}%)")
    elif bb_pos > 80: score -= 0.15; reasons.append(f"BOLL超买({bb_pos:.0f}%)")
    
    if ind['plus_di'].iloc[-1] > ind['minus_di'].iloc[-1]: score += 0.1
    else: score -= 0.1
    
    if ind['adx'].iloc[-1] > 25: score *= 1.2
    
    score = max(-1.0, min(1.0, score))
    sig = "BUY" if score >= 0.5 else ("SELL" if score <= -0.5 else "HOLD")
    return sig, score, abs(score), reasons

def kelly(win_rate, avg_win_pct, avg_loss_pct):
    """简化凯利：基于胜率和盈亏比（输入win_rate是小数，avg_win/loss_pct是百分比）"""
    # 转换百分比为小数
    wr = win_rate
    aw = avg_win_pct / 100
    al = max(avg_loss_pct / 100, 0.0001)
    wl_ratio = aw / al
    k = (wr * wl_ratio - (1 - wr)) / wl_ratio if wl_ratio > 0 else 0
    # 一半凯利，保守
    return max(0.05, min(0.7, abs(k) * 0.5))

def run():
    print("=" * 68)
    print("  股神2号 v5.2 | 完整量化系统（成本优化版）")
    print("=" * 68)
    
    print("\n📥 获取数据...")
    df = get_data(500)
    price = get_rt() or df['close'].iloc[-1]
    print(f"   {len(df)}条 | {df.index[0].strftime('%Y-%m-%d')} ~ {df.index[-1].strftime('%Y-%m-%d')}")
    print(f"   实时价格: {price:.0f}")
    
    print("\n📊 计算指标...")
    ind = calc_indicators(df)
    
    print("\n" + "=" * 68)
    print("【策略排行榜】(含成本: 手续费0.03% + 滑点0.02%)")
    print("=" * 68)
    print(f"\n{'参数':<22} {'收益':>9} {'回撤':>8} {'夏普':>7} {'Sortino':>8} {'Calmar':>7} {'盈亏比':>7} {'胜率':>6} {'交易':>5}")
    print("-" * 82)
    
    results = optimize(df)
    top5 = results[:5]
    
    for r in top5:
        print(f"  {r['params']:<22} {r['ret']:>8.1f}% {r['dd']:>7.1f}% {r['sharpe']:>6.2f} {r['sortino']:>7.2f} {r['calmar']:>6.2f} {r['pf']:>6.2f} {r['wr']*100:>5.0f}% {r['trades']:>4d}")
    
    print("-" * 68)
    best = results[0] if results else None
    if best:
        print(f"\n  🏆 全局最优: {best['params']}")
        print(f"     夏普: {best['sharpe']:.2f} | Sortino: {best['sortino']:.2f} | Calmar: {best['calmar']:.2f}")
        print(f"     稳定性评分: {best['stability']:.2f}")
        print(f"     手续费合计: ¥{best['fees']:.2f}")
    
    # 信号
    print("\n" + "=" * 68)
    print("【实时信号】")
    print("=" * 68)
    
    sig, sc, conf, reasons = get_signal(ind, price)
    icon = {'BUY': '🟢买入', 'SELL': '🔴卖出', 'HOLD': '⏸️观望'}
    col = {'BUY': '32', 'SELL': '91', 'HOLD': '33'}
    
    print(f"\n  综合信号: \033[{col[sig]}m{icon[sig]}\033[0m (置信度{conf:.0%})")
    print(f"  评分: {sc:+.2f}")
    
    rsi = ind['rsi'].iloc[-1]
    bb_pos = (price - ind['bb_lower'].iloc[-1]) / (ind['bb_upper'].iloc[-1] - ind['bb_lower'].iloc[-1]) * 100
    adx = ind['adx'].iloc[-1]
    pd_ = ind['plus_di'].iloc[-1]
    nd = ind['minus_di'].iloc[-1]
    
    print(f"\n  RSI: {rsi:.0f} | BOLL: {bb_pos:.0f}% | DMI: +{pd_:.1f}/-{nd:.1f} | ADX: {adx:.1f}")
    
    if reasons:
        for r in reasons:
            print(f"    • {r}")
    
    # 风控
    print("\n" + "=" * 68)
    print("【风控+仓位管理】")
    print("=" * 68)
    
    atr = ind['atr'].iloc[-1]
    vol = ind['vol']
    pos_mult = 0.5 if vol > 0.20 else (0.7 if vol > 0.10 else 1.0)
    
    if best and best['wr'] > 0 and best['trades'] > 0 and best['dd'] > 0:
        avg_w = best['ret'] / best['trades']
        avg_l = abs(best['dd']) / best['trades']
        k = kelly(best['wr'], avg_w, avg_l)
    else:
        k = 0.3
    
    max_pos = min(k * pos_mult, 0.7)
    
    print(f"\n  ATR: {atr:.0f} | 波动率: {vol:.0%}")
    print(f"  凯利仓位: {k*100:.0f}% × {pos_mult:.1f} = {max_pos*100:.1f}%")
    
    if sig == 'BUY':
        sl = price - 2 * atr
        tp = price + 3 * atr
        print(f"\n  🟢 买入: {price:.0f} | 止损: {sl:.0f} | 止盈: {tp:.0f} | 仓位: {max_pos*100:.1f}%")
    elif sig == 'SELL':
        sl = price + 2 * atr
        tp = price - 3 * atr
        print(f"\n  🔴 卖出: {price:.0f} | 止损: {sl:.0f} | 止盈: {tp:.0f} | 仓位: {max_pos*100:.1f}%")
    else:
        print(f"\n  ⏸️ 观望")
    
    print(f"\n  关键价位: {ind['bb_lower'].iloc[-1]:.0f} / {price:.0f} / {ind['bb_upper'].iloc[-1]:.0f}")
    
    print("\n" + "=" * 68)
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 68)

if __name__ == '__main__':
    run()
