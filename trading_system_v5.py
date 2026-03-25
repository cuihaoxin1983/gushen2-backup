#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股神2号 - v5.5 信号历史验证系统
======================================
核心理念：今天的信号，在历史上出现时，赚钱吗？

不再问："哪个参数最优？"
而是问："今天这个信号，历史胜率多少？"

原理：
1. 用指标规则生成"买入信号"（如RSI<30）
2. 在历史数据中，找到所有出现同样信号的日子
3. 如果信号后价格上涨 → 成功案例
4. VectorBT模拟：每次信号出现时买入，持有N天后卖出
5. 统计所有历史案例的胜率、平均收益
6. → 得到"这个信号的历史置信度"
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
    ma60 = close.rolling(60).mean()

    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    macd_hist = macd - signal

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
    plus_di = (plus_dm.rolling(14).mean() / atr.replace(0, np.nan)) * 100
    minus_di = (minus_dm.rolling(14).mean() / atr.replace(0, np.nan)) * 100
    dx = abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan) * 100
    adx = dx.rolling(14).mean()

    low_n = low.rolling(9).min()
    high_n = high.rolling(9).max()
    k = 50 * (close - low_n) / (high_n - low_n + 0.001)
    d = k.rolling(3).mean()
    j = 3 * k - 2 * d

    vol_annual = close.pct_change().rolling(20).std() * np.sqrt(250)

    trend_20d = (close.iloc[-1] / close.iloc[-20] - 1) if len(close) >= 20 else 0
    market_state = 'down' if trend_20d < -0.05 else ('up' if trend_20d > 0.05 else 'range')

    return {
        'close': close, 'high': high, 'low': low,
        'ma5': ma5, 'ma10': ma10, 'ma20': ma20, 'ma30': ma30, 'ma60': ma60,
        'macd': macd, 'signal': signal, 'macd_hist': macd_hist,
        'rsi': rsi, 'bb_upper': bb_upper, 'bb_mid': bb_mid, 'bb_lower': bb_lower,
        'atr': atr, 'plus_di': plus_di, 'minus_di': minus_di, 'adx': adx,
        'k': k, 'd': d, 'j': j, 'vol': vol_annual,
        'market_state': market_state, 'trend_20d': trend_20d
    }

def run_bt(close, entries, exits, fees=0.0003, slippage=0.0002):
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
            wins = rets[rets > 0].sum()
            losses = abs(rets[rets < 0].sum())
            pf_ratio = wins / losses if losses > 0 else 999
        else:
            return None

        return {
            'ret': s['Total Return [%]'],
            'dd': s['Max Drawdown [%]'],
            'sharpe': sharpe,
            'sortino': sortino,
            'pf': pf_ratio,
            'wr': s['Win Rate [%]'] / 100 if not np.isnan(s['Win Rate [%]']) else 0,
            'trades': int(s['Total Trades']),
            'fees': s.get('Total Fees Paid', 0),
        }
    except:
        return None

# ============ 信号历史验证 ============

def validate_signal_history(close, ind, signal_name, entries, exits, hold_days=5):
    """
    核心功能：验证"这个信号"在历史上出现时，跟随它赚钱吗？

    步骤：
    1. entries: 历史上所有出现这个信号的日子（布尔Series）
    2. 用VectorBT模拟：每次信号出现日买入，hold_days后卖出
    3. 统计所有交易：胜率、平均收益、夏普

    返回：验证结果字典
    """
    if entries.sum() < 3:
        return None

    try:
        pf = vbt.Portfolio.from_signals(
            close, entries, exits,
            size=0.3, freq='1D',
            fixed_fees=0.0003,
            slippage=0.0002,
            init_cash=100000
        )

        s = pf.stats()
        eq = pf.value()
        rets = eq.pct_change().dropna()

        trades = int(s['Total Trades'])
        if trades < 1:
            return None

        sharpe = rets.mean() / rets.std() * np.sqrt(250) if rets.std() > 0 else 0
        wr = s['Win Rate [%]'] / 100 if not np.isnan(s['Win Rate [%]']) else 0

        # 计算持仓期收益分布
        entry_dates = entries[entries].index
        period_returns = []
        for ed in entry_dates:
            try:
                idx = close.index.get_loc(ed)
                if idx + hold_days < len(close):
                    ret = (close.iloc[idx + hold_days] / close.iloc[idx]) - 1
                    period_returns.append(ret)
            except:
                continue

        avg_hold_return = np.mean(period_returns) * 100 if period_returns else 0
        win_rate_hold = np.mean([1 if r > 0 else 0 for r in period_returns]) if period_returns else 0

        return {
            'signal': signal_name,
            'occurrences': int(entries.sum()),
            'trades': trades,
            'ret': s['Total Return [%]'],
            'sharpe': sharpe,
            'wr': wr,
            'avg_hold_return': avg_hold_return,
            'win_rate_hold': win_rate_hold,
            'hold_days': hold_days,
            'pf_obj': pf
        }
    except Exception as e:
        return None

# ============ 生成各类信号 ============

def generate_all_signals(df, ind):
    """生成所有策略的信号序列"""
    close = df['close']
    signals = {}

    # 1. MA金叉（均线多头）
    ma5 = ind['ma5']
    ma20 = ind['ma20']
    signals['MA_Golden'] = (ma5 > ma20) & (ma5.shift(1) <= ma20.shift(1))

    # 2. MA死叉（均线空头）
    signals['MA_Death'] = (ma5 < ma20) & (ma5.shift(1) >= ma20.shift(1))

    # 3. RSI超卖
    rsi = ind['rsi']
    signals['RSI_Oversold'] = rsi < 30
    signals['RSI_Edge'] = (rsi >= 30) & (rsi < 40)

    # 4. RSI超买
    signals['RSI_Overbought'] = rsi > 70
    signals['RSI_Edge_Bear'] = (rsi <= 70) & (rsi > 60)

    # 5. MACD柱转正
    macd_hist = ind['macd_hist']
    signals['MACD_Bull'] = (macd_hist > 0) & (macd_hist.shift(1) <= 0)

    # 6. MACD柱转负
    signals['MACD_Bear'] = (macd_hist < 0) & (macd_hist.shift(1) >= 0)

    # 7. BOLL超卖
    bb_lower = ind['bb_lower']
    signals['BOLL_Oversold'] = close < bb_lower

    # 8. BOLL偏下
    bb_upper = ind['bb_upper']
    bb_mid = ind['bb_mid']
    bb_pos = (close - bb_lower) / (bb_upper - bb_lower + 0.001)
    signals['BOLL_Low'] = (bb_pos < 0.2) & (bb_pos >= 0)

    # 9. DMI多头
    plus_di = ind['plus_di']
    minus_di = ind['minus_di']
    adx = ind['adx']
    signals['DMI_Bull'] = (plus_di > minus_di) & (adx > 20)

    # 10. DMI空头
    signals['DMI_Bear'] = (plus_di < minus_di) & (adx > 20)

    # 11. KDJ超卖
    j_val = ind['j']
    signals['KDJ_Oversold'] = j_val < 20

    # 12. 布林开口放大（波动率爆发）
    bb_width = (bb_upper - bb_lower) / bb_mid
    signals['BOLL_Expand'] = bb_width > bb_width.rolling(10).mean() * 1.2

    return signals

def evaluate_signal_quality(close, ind, df, hold_days_list=[3, 5, 7]):
    """
    评估每个信号的历史表现
    返回：信号排行榜
    """
    signals = generate_all_signals(df, ind)
    results = []

    for name, entries in signals.items():
        if entries.sum() < 3:
            continue

        # 多持仓期验证
        for hold_days in hold_days_list:
            exits = entries.shift(hold_days).fillna(False)

            r = validate_signal_history(close, ind, name, entries, exits, hold_days)
            if r and r['trades'] >= 2:
                results.append(r)

    if not results:
        return []

    # 按夏普排序
    results.sort(key=lambda x: x['sharpe'], reverse=True)
    return results

def get_current_signals(ind, price):
    """获取当前激活的信号"""
    active = []
    reasons = []

    ma5 = ind['ma5'].iloc[-1]
    ma20 = ind['ma20'].iloc[-1]
    ma60 = ind['ma60'].iloc[-1]
    rsi = ind['rsi'].iloc[-1]
    bb_pos = (price - ind['bb_lower'].iloc[-1]) / (ind['bb_upper'].iloc[-1] - ind['bb_lower'].iloc[-1] + 0.001) * 100
    plus_di = ind['plus_di'].iloc[-1]
    minus_di = ind['minus_di'].iloc[-1]
    adx = ind['adx'].iloc[-1]
    macd_hist = ind['macd_hist'].iloc[-1]
    j_val = ind['j'].iloc[-1]

    # 记录所有激活的信号
    if price < ma5: active.append("价格<MA5")
    if ma5 < ma20: active.append("MA空头")
    if ma20 < ma60: active.append("MA20<MA60空头")
    if macd_hist < 0: active.append("MACD柱负向")
    if rsi < 30: active.append(f"RSI超卖({rsi:.0f})")
    elif rsi < 40: active.append(f"RSI偏弱({rsi:.0f})")
    if rsi > 70: active.append(f"RSI超买({rsi:.0f})")
    elif rsi > 60: active.append(f"RSI偏强({rsi:.0f})")
    if bb_pos < 20: active.append(f"BOLL超卖({bb_pos:.0f}%)")
    if plus_di < minus_di: active.append(f"DMI空头")
    if adx > 25: active.append(f"ADX强趋势({adx:.0f})")
    if j_val < 20: active.append(f"KDJ超卖({j_val:.0f})")
    if j_val > 80: active.append(f"KDJ超买({j_val:.0f})")

    # 综合评分
    score = 0.0
    if price > ma5: score += 0.1
    else: score -= 0.1

    if ma5 > ma20 > ind['ma30'].iloc[-1]:
        score += 0.25
    elif ma5 < ma20 < ind['ma30'].iloc[-1]:
        score -= 0.25

    if macd_hist > 0: score += 0.15
    else: score -= 0.15

    if rsi < 30: score += 0.3
    elif rsi > 70: score -= 0.3
    elif rsi < 40: score += 0.1
    elif rsi > 60: score -= 0.1

    if bb_pos < 20: score += 0.25
    elif bb_pos > 80: score -= 0.25

    if plus_di > minus_di: score += 0.15
    else: score -= 0.15

    if adx > 25: score *= 1.15
    elif adx < 20: score *= 0.8

    if j_val < 20: score += 0.15
    elif j_val > 80: score -= 0.15

    vol = ind['vol'].iloc[-1]
    if vol > 0.25: score *= 0.8
    elif vol < 0.10: score *= 0.9

    score = max(-1.0, min(1.0, score))

    if score >= 0.5: sig = "BUY"
    elif score <= -0.5: sig = "SELL"
    else: sig = "HOLD"

    return sig, score, abs(score), active

def kelly_formula(win_rate, avg_win_pct, avg_loss_pct):
    aw = max(avg_win_pct, 0.001)
    al = max(avg_loss_pct, 0.001)
    wl_ratio = aw / al
    k = (win_rate * wl_ratio - (1 - win_rate)) / wl_ratio
    return max(0.05, min(0.7, abs(k) * 0.5))

def run():
    print("=" * 70)
    print("  股神2号 v5.5 | 信号历史验证系统")
    print("  核心问题：今天的信号，历史胜率多少？")
    print("=" * 70)

    print("\n[1/4] 获取数据...")
    df = get_data(500)
    price = get_rt() or df['close'].iloc[-1]
    n = len(df)
    print(f"   {n}条 | {df.index[0].strftime('%Y-%m-%d')} ~ {df.index[-1].strftime('%Y-%m-%d')}")
    print(f"   实时价格: {price:.0f}")

    print("\n[2/4] 计算指标...")
    ind = calc_indicators(df)

    market_state = ind['market_state']
    trend_20d = ind['trend_20d'] * 100
    state_map = {'up': 'UP', 'down': 'DOWN', 'range': 'RANGE'}
    print(f"\n   市场状态: [{state_map[market_state]}] (20日趋势: {trend_20d:+.1f}%)")

    print("\n[3/4] 信号历史验证...")
    print("  问题：这些信号在历史上出现时，跟随它赚钱吗？")
    print("-" * 70)

    # 评估所有信号
    signal_results = evaluate_signal_quality(df['close'], ind, df, hold_days_list=[3, 5, 7])

    if signal_results:
        print(f"\n  {'信号':<18} {'历史次数':>8} {'胜率':>7} {'平均持有收益':>12} {'夏普':>7}")
        print("  " + "-" * 56)

        shown = set()
        count = 0
        for r in signal_results:
            if r['signal'] in shown:
                continue
            shown.add(r['signal'])
            wr = r['win_rate_hold'] * 100
            icon = "OK" if wr > 50 else "WARN" if wr > 30 else "BAD"
            print(f"  {r['signal']:<18} {r['occurrences']:>6} {wr:>6.0f}% {r['avg_hold_return']:>+10.1f}% {r['sharpe']:>6.2f} [{icon}]")
            count += 1
            if count >= 10:
                break

        print()

        # 找最佳信号
        best = signal_results[0]
        print(f"  >> 最佳信号: {best['signal']}")
        print(f"     历史胜率: {best['win_rate_hold']*100:.0f}% | 持有{best['hold_days']}天平均: {best['avg_hold_return']:+.1f}%")
        print(f"     历史出现: {best['occurrences']}次 | 夏普: {best['sharpe']:.2f}")
    else:
        best = None
        print("  信号数据不足")

    print("\n[4/4] 实时信号 + 置信度...")

    sig, sc, conf, reasons = get_current_signals(ind, price)
    icon_map = {'BUY': 'BUY', 'SELL': 'SELL', 'HOLD': 'HOLD'}
    print(f"\n  综合信号: [{icon_map[sig]}] (指标评分置信度: {conf:.0%})")
    print(f"  指标评分: {sc:+.2f}")

    # 基于历史信号调整置信度
    if best and best['win_rate_hold'] > 0:
        hist_conf = best['win_rate_hold']
        # 综合：指标评分 + 历史胜率
        combined_conf = conf * 0.5 + hist_conf * 0.5
        print(f"\n  历史置信度: {hist_conf:.0%} (基于{best['occurrences']}次历史验证)")
        print(f"  综合置信度: {conf:.0%} × 50% + {hist_conf:.0%} × 50% = {combined_conf:.0%}")
    else:
        combined_conf = conf
        print(f"\n  综合置信度: {conf:.0%}")

    if reasons:
        print(f"\n  当前活跃信号: {len(reasons)}个")
        for r in reasons[:5]:
            print(f"    - {r}")

    # 风控
    print("\n" + "-" * 70)
    print("【风控+仓位】")
    print("-" * 70)

    atr = ind['atr'].iloc[-1]
    vol = ind['vol'].iloc[-1]
    pos_mult = 0.5 if vol > 0.20 else (0.7 if vol > 0.10 else 1.0)

    if best and best['win_rate_hold'] > 0:
        wr = best['win_rate_hold']
        avg_ret = best['avg_hold_return']
        k = kelly_formula(wr, avg_ret, 3.0)
    else:
        k = 0.3

    max_pos = min(k * pos_mult, 0.7)

    print(f"  ATR: {atr:.0f} | 波动率: {vol:.0%}")
    if best:
        print(f"  最佳信号: {best['signal']} (历史胜率: {best['win_rate_hold']*100:.0f}%)")
    print(f"  凯利仓位: {k*100:.0f}% → 建议: {max_pos*100:.1f}%")

    if sig == 'BUY':
        sl = price - 2 * atr
        tp = price + 3 * atr
        print(f"\n  [BUY] {price:.0f}")
        print(f"        止损: {sl:.0f} (-{2*atr/price*100:.1f}%)")
        print(f"        止盈: {tp:.0f} (+{3*atr/price*100:.1f}%)")
    elif sig == 'SELL':
        sl = price + 2 * atr
        tp = price - 3 * atr
        print(f"\n  [SELL] {price:.0f}")
        print(f"        止损: {sl:.0f} (+{2*atr/price*100:.1f}%)")
        print(f"        止盈: {tp:.0f} (-{3*atr/price*100:.1f}%)")
    else:
        print(f"\n  [HOLD] 观望")

    print(f"\n  关键价位: {ind['bb_lower'].iloc[-1]:.0f} / {price:.0f} / {ind['bb_upper'].iloc[-1]:.0f}")

    print("\n" + "=" * 70)
    print("【v5.5 核心升级】")
    print("=" * 70)
    print("""
  ✅ 信号历史验证：不再问"哪个参数最优"
  ✅ 问："今天这个信号，历史胜率多少？"
  ✅ VectorBT批量验证每个信号的历史表现
  ✅ 多持仓期验证(3/5/7天)
  ✅ 历史胜率 + 指标评分 → 综合置信度
  ✅ 直接告诉您：这个信号历史上跟着做赚了多少钱
""")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

if __name__ == '__main__':
    run()
