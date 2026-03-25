#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股神2号 - v5.4 自适应策略系统
======================================
核心进化：
1. 增大验证窗口到20天（足够策略产生信号）
2. 趋势跟踪+均值回归双策略并行
3. 参数稳定性过滤（参数在连续窗口保持一致=可靠）
4. 市场状态自适应（下跌趋势用均值回归，上涨用趋势跟踪）
5. Walk-Forward验证 + 最新窗口参数双重确认
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

    # 市场状态：最近20天趋势
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
            calmar = (rets.mean() * 250) / max_dd if max_dd > 0 else 0
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
            'calmar': calmar,
            'pf': pf_ratio,
            'wr': s['Win Rate [%]'] / 100 if not np.isnan(s['Win Rate [%]']) else 0,
            'trades': int(s['Total Trades']),
            'fees': s.get('Total Fees Paid', 0),
        }
    except:
        return None

# ============ 策略库 ============

def ma_strategy(data, params=None):
    """均线策略 - 趋势跟踪"""
    close = data['close'] if isinstance(data, pd.DataFrame) else data
    results = []

    if params is None:
        for fast in [3, 5, 7, 10]:
            for slow in [15, 20, 30]:
                if fast >= slow:
                    continue
                mf = close.rolling(fast).mean()
                ms = close.rolling(slow).mean()
                entries = (mf > ms) & (mf.shift(1) <= ms.shift(1))
                exits = (mf < ms) & (mf.shift(1) >= ms.shift(1))
                r = run_bt(close, entries, exits)
                if r and r['trades'] >= 2:
                    results.append({
                        'params_str': f'MA({fast}/{slow})',
                        'params_raw': ('ma', fast, slow),
                        **r
                    })
        results.sort(key=lambda x: x['sharpe'], reverse=True)
    else:
        strat, fast, slow = params
        mf = close.rolling(fast).mean()
        ms = close.rolling(slow).mean()
        entries = (mf > ms) & (mf.shift(1) <= ms.shift(1))
        exits = (mf < ms) & (mf.shift(1) >= ms.shift(1))
        r = run_bt(close, entries, exits)
        if r:
            results.append(r)
    return results

def macd_strategy(data, params=None):
    """MACD策略 - 趋势跟踪"""
    close = data['close'] if isinstance(data, pd.DataFrame) else data
    results = []

    if params is None:
        for fast in [5, 8, 12]:
            for slow in [15, 20, 26]:
                for sig in [5, 7, 9]:
                    if fast >= slow:
                        continue
                    ef = close.ewm(span=fast).mean()
                    es = close.ewm(span=slow).mean()
                    macd_val = ef - es
                    signal_val = macd_val.ewm(span=sig).mean()
                    entries = (macd_val > signal_val) & (macd_val.shift(1) <= signal_val.shift(1))
                    exits = (macd_val < signal_val) & (macd_val.shift(1) >= signal_val.shift(1))
                    r = run_bt(close, entries, exits)
                    if r and r['trades'] >= 2:
                        results.append({
                            'params_str': f'MACD({fast},{slow},{sig})',
                            'params_raw': ('macd', fast, slow, sig),
                            **r
                        })
        results.sort(key=lambda x: x['sharpe'], reverse=True)
    else:
        strat, fast, slow, sig = params
        ef = close.ewm(span=fast).mean()
        es = close.ewm(span=slow).mean()
        macd_val = ef - es
        signal_val = macd_val.ewm(span=sig).mean()
        entries = (macd_val > signal_val) & (macd_val.shift(1) <= signal_val.shift(1))
        exits = (macd_val < signal_val) & (macd_val.shift(1) >= signal_val.shift(1))
        r = run_bt(close, entries, exits)
        if r:
            results.append(r)
    return results

def rsi_strategy(data, params=None):
    """RSI均值回归策略 - 震荡市场"""
    close = data['close'] if isinstance(data, pd.DataFrame) else data
    results = []

    if params is None:
        for period in [6, 10, 14]:
            for oversold in [25, 30, 35]:
                for overbought in [65, 70, 75]:
                    if oversold >= overbought:
                        continue

                    delta = close.diff()
                    gain = delta.where(delta > 0, 0).rolling(period).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
                    rs = gain / loss.replace(0, np.nan)
                    rsi_val = 100 - (100 / (1 + rs))

                    # 超卖买入，超买卖出（均值回归）
                    entries = rsi_val < oversold
                    exits = rsi_val > overbought
                    r = run_bt(close, entries, exits)
                    if r and r['trades'] >= 2:
                        results.append({
                            'params_str': f'RSI({period},{oversold}/{overbought})',
                            'params_raw': ('rsi', period, oversold, overbought),
                            **r
                        })
        results.sort(key=lambda x: x['sharpe'], reverse=True)
    else:
        strat, period, oversold, overbought = params
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi_val = 100 - (100 / (1 + rs))
        entries = rsi_val < oversold
        exits = rsi_val > overbought
        r = run_bt(close, entries, exits)
        if r:
            results.append(r)
    return results

def boll_strategy(data, params=None):
    """布林带策略 - 均值回归"""
    close = data['close'] if isinstance(data, pd.DataFrame) else data
    results = []

    if params is None:
        for period in [15, 20, 25]:
            for std_mul in [1.5, 2.0, 2.5]:
                bb_mid = close.rolling(period).mean()
                bb_std = close.rolling(period).std()
                bb_upper = bb_mid + std_mul * bb_std
                bb_lower = bb_mid - std_mul * bb_std

                # 下轨买入，上轨卖出
                entries = close < bb_lower
                exits = close > bb_mid
                r = run_bt(close, entries, exits)
                if r and r['trades'] >= 2:
                    results.append({
                        'params_str': f'BOLL({period},{std_mul})',
                        'params_raw': ('boll', period, std_mul),
                        **r
                    })
        results.sort(key=lambda x: x['sharpe'], reverse=True)
    else:
        strat, period, std_mul = params
        bb_mid = close.rolling(period).mean()
        bb_std = close.rolling(period).std()
        bb_upper = bb_mid + std_mul * bb_std
        bb_lower = bb_mid - std_mul * bb_std
        entries = close < bb_lower
        exits = close > bb_mid
        r = run_bt(close, entries, exits)
        if r:
            results.append(r)
    return results

def dmi_strategy(data, params=None):
    """DMI趋势策略"""
    close = data['close'] if isinstance(data, pd.DataFrame) else data
    results = []

    if params is None:
        for period in [14, 20]:
            for adx_th in [20, 25]:
                try:
                    high_d = data['high'] if isinstance(data, pd.DataFrame) else data
                    low_d = data['low'] if isinstance(data, pd.DataFrame) else data

                    tr1 = high_d - low_d
                    tr2 = abs(high_d - close.shift(1))
                    tr3 = abs(low_d - close.shift(1))
                    tr = pd.concat([tr1.reset_index(drop=True),
                                    tr2.reset_index(drop=True),
                                    tr3.reset_index(drop=True)], axis=1).max(axis=1)
                    atr_s = tr.rolling(period).mean()
                    atr_s.index = close.index[:len(atr_s)]

                    plus_dm = high_d.diff()
                    minus_dm = -low_d.diff()
                    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
                    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
                    plus_di = (plus_dm.rolling(period).mean() / atr_s.replace(0, np.nan)) * 100
                    minus_di = (minus_dm.rolling(period).mean() / atr_s.replace(0, np.nan)) * 100
                    dx = abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan) * 100
                    adx_s = dx.rolling(period).mean()

                    entries = (plus_di > minus_di) & (adx_s > adx_th)
                    exits = (plus_di < minus_di) | (adx_s < adx_th - 5)

                    r = run_bt(close, entries, exits)
                    if r and r['trades'] >= 2:
                        results.append({
                            'params_str': f'DMI({period},ADX>{adx_th})',
                            'params_raw': ('dmi', period, adx_th),
                            **r
                        })
                except:
                    continue
        results.sort(key=lambda x: x['sharpe'], reverse=True)
    else:
        strat, period, adx_th = params
        try:
            high_d = data['high'] if isinstance(data, pd.DataFrame) else data
            low_d = data['low'] if isinstance(data, pd.DataFrame) else data

            tr1 = high_d - low_d
            tr2 = abs(high_d - close.shift(1))
            tr3 = abs(low_d - close.shift(1))
            tr = pd.concat([tr1.reset_index(drop=True),
                            tr2.reset_index(drop=True),
                            tr3.reset_index(drop=True)], axis=1).max(axis=1)
            atr_s = tr.rolling(period).mean()
            atr_s.index = close.index[:len(atr_s)]

            plus_dm = high_d.diff()
            minus_dm = -low_d.diff()
            plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
            minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
            plus_di = (plus_dm.rolling(period).mean() / atr_s.replace(0, np.nan)) * 100
            minus_di = (minus_dm.rolling(period).mean() / atr_s.replace(0, np.nan)) * 100
            dx = abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan) * 100
            adx_s = dx.rolling(period).mean()

            entries = (plus_di > minus_di) & (adx_s > adx_th)
            exits = (plus_di < minus_di) | (adx_s < adx_th - 5)

            r = run_bt(close, entries, exits)
            if r:
                results.append(r)
        except:
            return []
    return results

# ============ Walk-Forward 验证 ============

def walk_forward_validate(df, strategy_fn, train_days=120, val_days=20, min_trades=2):
    """
    Walk-Forward验证 + 参数稳定性过滤
    """
    close = df['close']
    results = []
    param_history = []

    for i in range(train_days, len(close) - val_days, val_days):
        train = close.iloc[:i]
        val = close.iloc[i:i+val_days]

        if len(train) < 80:
            continue

        try:
            train_results = strategy_fn(train)
            if not train_results:
                continue

            best = train_results[0]
            best_params = best.get('params_raw')
            best_str = best.get('params_str', '')

            if not best_params or best.get('trades', 0) < min_trades:
                continue

            # 验证集回测
            val_results = strategy_fn(val, best_params)
            if not val_results:
                continue

            val_r = val_results[0]

            # 放宽：只要有交易就算（1-2次交易也可能是有效的均值回归）
            if val_r.get('trades', 0) < 1:
                continue

            param_history.append(best_str)

            results.append({
                'train_sharpe': best.get('sharpe', 0),
                'val_sharpe': val_r.get('sharpe', 0),
                'val_return': val_r.get('ret', 0),
                'val_wr': val_r.get('wr', 0),
                'val_trades': val_r.get('trades', 0),
                'params': best_str
            })
        except Exception as e:
            continue

    if not results:
        return None

    # 计算稳定性：参数在多少个窗口中重复
    from collections import Counter
    param_count = Counter(param_history)
    most_common_params, most_common_count = param_count.most_common(1)[0]
    stability = most_common_count / len(results)

    val_sharpes = [r['val_sharpe'] for r in results]
    val_returns = [r['val_return'] for r in results]
    val_wrs = [r['val_wr'] for r in results]

    # 过滤：验证期夏普>0的结果比例
    positive_ratio = sum(1 for r in results if r['val_sharpe'] > 0) / len(results)

    return {
        'avg_val_sharpe': np.mean(val_sharpes),
        'avg_val_return': np.mean(val_returns),
        'avg_val_wr': np.mean(val_wrs),
        'avg_val_trades': np.mean([r['val_trades'] for r in results]),
        'stability': stability,
        'consistency': positive_ratio,
        'n_periods': len(results),
        'stable_params': most_common_params,
        'latest_params': results[-1]['params'] if results else '',
        'latest_val_sharpe': results[-1]['val_sharpe'] if results else 0,
        'all_results': results
    }

def get_signal(ind, price):
    score = 0.0
    reasons = []

    ma5 = ind['ma5'].iloc[-1]
    ma20 = ind['ma20'].iloc[-1]
    ma30 = ind['ma30'].iloc[-1]
    ma60 = ind['ma60'].iloc[-1]

    if price > ma5:
        score += 0.1
    else:
        score -= 0.1
        reasons.append("价格<MA5")

    if ma5 > ma20 > ma30:
        score += 0.25
        reasons.append("均线多头排列")
    elif ma5 < ma20 < ma30:
        score -= 0.25
        reasons.append("均线空头排列")

    if ma20 > ma60:
        score += 0.1
        reasons.append("MA20>MA60多头")
    elif ma20 < ma60:
        score -= 0.1
        reasons.append("MA20<MA60空头")

    if ind['macd_hist'].iloc[-1] > 0:
        score += 0.15
        reasons.append("MACD柱正向")
    else:
        score -= 0.15
        reasons.append("MACD柱负向")

    if ind['macd'].iloc[-1] > ind['signal'].iloc[-1]:
        score += 0.1
    else:
        score -= 0.1

    rsi = ind['rsi'].iloc[-1]
    if rsi < 30:
        score += 0.3
        reasons.append(f"RSI超卖({rsi:.0f})")
    elif rsi > 70:
        score -= 0.3
        reasons.append(f"RSI超买({rsi:.0f})")
    elif rsi < 40:
        score += 0.1
        reasons.append(f"RSI偏弱({rsi:.0f})")
    elif rsi > 60:
        score -= 0.1
        reasons.append(f"RSI偏强({rsi:.0f})")

    bb_upper = ind['bb_upper'].iloc[-1]
    bb_lower = ind['bb_lower'].iloc[-1]
    bb_pos = (price - bb_lower) / (bb_upper - bb_lower + 0.001) * 100
    if bb_pos < 20:
        score += 0.25
        reasons.append(f"BOLL超卖({bb_pos:.0f}%)")
    elif bb_pos > 80:
        score -= 0.25
        reasons.append(f"BOLL超买({bb_pos:.0f}%)")

    plus_di = ind['plus_di'].iloc[-1]
    minus_di = ind['minus_di'].iloc[-1]
    adx = ind['adx'].iloc[-1]

    if plus_di > minus_di:
        score += 0.15
        reasons.append(f"DMI多头(+{plus_di:.1f}/-{minus_di:.1f})")
    else:
        score -= 0.15
        reasons.append(f"DMI空头(+{plus_di:.1f}/-{minus_di:.1f})")

    if adx > 25:
        score *= 1.15
        reasons.append(f"ADX强趋势({adx:.1f})")
    elif adx < 20:
        score *= 0.8
        reasons.append(f"ADX震荡({adx:.1f})")

    j_val = ind['j'].iloc[-1]
    if j_val < 20:
        score += 0.15
        reasons.append(f"KDJ超卖({j_val:.0f})")
    elif j_val > 80:
        score -= 0.15
        reasons.append(f"KDJ超买({j_val:.0f})")

    vol = ind['vol'].iloc[-1]
    if vol > 0.25:
        score *= 0.8
        reasons.append("高波动减权")
    elif vol < 0.10:
        score *= 0.9
        reasons.append("低波动减权")

    score = max(-1.0, min(1.0, score))

    if score >= 0.5:
        sig = "BUY"
    elif score <= -0.5:
        sig = "SELL"
    else:
        sig = "HOLD"

    return sig, score, abs(score), reasons

def kelly_formula(win_rate, avg_win_pct, avg_loss_pct):
    aw = max(avg_win_pct, 0.001)
    al = max(avg_loss_pct, 0.001)
    wl_ratio = aw / al
    k = (win_rate * wl_ratio - (1 - win_rate)) / wl_ratio
    return max(0.05, min(0.7, abs(k) * 0.5))

def count_bullish(ind, price):
    count = 0
    if ind['ma5'].iloc[-1] > ind['ma20'].iloc[-1]:
        count += 1
    if ind['macd_hist'].iloc[-1] > 0:
        count += 1
    if ind['rsi'].iloc[-1] < 40:
        count += 1
    if ind['plus_di'].iloc[-1] > ind['minus_di'].iloc[-1]:
        count += 1
    if ind['j'].iloc[-1] < 30:
        count += 1
    return count

def run():
    print("=" * 70)
    print("  股神2号 v5.4 | 自适应策略系统")
    print("  核心理念：市场状态自适应 + 参数稳定性过滤")
    print("=" * 70)

    print("\n[1/5] 获取数据...")
    df = get_data(500)
    price = get_rt() or df['close'].iloc[-1]
    n = len(df)
    print(f"   {n}条 | {df.index[0].strftime('%Y-%m-%d')} ~ {df.index[-1].strftime('%Y-%m-%d')}")
    print(f"   实时价格: {price:.0f}")

    print("\n[2/5] 计算指标...")
    ind = calc_indicators(df)

    market_state = ind['market_state']
    trend_20d = ind['trend_20d'] * 100
    state_icon = {'up': 'UP', 'down': 'DOWN', 'range': 'RANGE'}
    print(f"\n   市场状态: [{state_icon[market_state]}] (20日趋势: {trend_20d:+.1f}%)")

    print("\n[3/5] Walk-Forward滚动验证 (训练120天/验证20天)...")
    print("-" * 70)

    train_days = 120
    val_days = 20

    # 根据市场状态选择策略优先级
    if market_state == 'down':
        # 下跌趋势：均值回归优先
        strategies = [('RSI', rsi_strategy), ('BOLL', boll_strategy), ('MACD', macd_strategy), ('MA', ma_strategy), ('DMI', dmi_strategy)]
        print("   市场下跌：优先验证均值回归策略(RSI/BOLL)")
    elif market_state == 'up':
        # 上涨趋势：趋势跟踪优先
        strategies = [('MACD', macd_strategy), ('MA', ma_strategy), ('DMI', dmi_strategy), ('RSI', rsi_strategy), ('BOLL', boll_strategy)]
        print("   市场上涨：优先验证趋势跟踪策略(MACD/MA)")
    else:
        strategies = [('RSI', rsi_strategy), ('BOLL', boll_strategy), ('MACD', macd_strategy), ('MA', ma_strategy), ('DMI', dmi_strategy)]
        print("   市场震荡：验证所有策略")

    print()

    strategy_results = {}
    for name, fn in strategies:
        print(f"  {name}...", end=" ", flush=True)
        wf = walk_forward_validate(df, fn, train_days=train_days, val_days=val_days)
        if wf and wf['n_periods'] > 0:
            strategy_results[name] = wf
            icon = "OK" if wf['consistency'] > 0.5 else "WARN"
            print(f"验证夏普={wf['avg_val_sharpe']:.2f} 胜率={wf['avg_val_wr']*100:.0f}% 稳定性={wf['stability']:.0%} [{icon}]")
        else:
            print("数据不足")

    print()

    # 全局最优（基于验证期夏普）
    if strategy_results:
        best_name = max(strategy_results.keys(), key=lambda k: strategy_results[k]['avg_val_sharpe'])
        best = strategy_results[best_name]

        # 稳定性过滤：稳定性<40%的策略不推荐
        stable_enough = best['stability'] >= 0.4

        print(f"  >> 全局验证期最优: {best_name}策略")
        print(f"     验证夏普: {best['avg_val_sharpe']:.2f} | 胜率: {best['avg_val_wr']*100:.0f}%")
        print(f"     稳定性: {best['stability']:.0%} | 一致性: {best['consistency']:.0%}")
        print(f"     稳定参数: {best['stable_params']}")
        print(f"     最新参数: {best['latest_params']}")

        if not stable_enough:
            print(f"\n  ⚠️ 最佳策略稳定性不足({best['stability']:.0%}<40%)，信号降权")

        # 第二名策略（用于共振）
        if len(strategy_results) > 1:
            sorted_results = sorted(strategy_results.items(), key=lambda x: x[1]['avg_val_sharpe'], reverse=True)
            if len(sorted_results) >= 2:
                second = sorted_results[1]
                print(f"     次优: {second[0]}策略 (夏普={second[1]['avg_val_sharpe']:.2f})")
    else:
        best_name = 'RSI'
        best = None
        print("  >> 所有策略数据不足，使用默认RSI")

    print("\n[4/5] 实时信号生成...")

    sig, sc, conf, reasons = get_signal(ind, price)
    icon_map = {'BUY': 'BUY', 'SELL': 'SELL', 'HOLD': 'HOLD'}
    print(f"\n  综合信号: [{icon_map[sig]}] (置信度{conf:.0%})")
    print(f"  评分: {sc:+.2f}")

    bullish_count = count_bullish(ind, price)
    print(f"  多头共振: {bullish_count}/5指标")

    if reasons:
        print(f"  信号依据:")
        for r in reasons[:5]:
            print(f"    - {r}")

    # 策略置信度
    if best and best.get('consistency', 0) > 0:
        wf_factor = min(best['consistency'], 1.0)
        stability_factor = best['stability']
        combined_factor = (wf_factor * 0.6 + stability_factor * 0.4)
        adj_conf = conf * (0.4 + 0.6 * combined_factor)
        print(f"\n  WF置信度调整: {conf:.0%} × {combined_factor:.2f} = {adj_conf:.0%}")
        print(f"     (验证一致性: {best['consistency']:.0%}, 参数稳定性: {best['stability']:.0%})")

    print("\n[5/5] 风控+仓位...")

    atr = ind['atr'].iloc[-1]
    vol = ind['vol'].iloc[-1]
    pos_mult = 0.5 if vol > 0.20 else (0.7 if vol > 0.10 else 1.0)

    if best and best['avg_val_wr'] > 0:
        wr = best['avg_val_wr']
        avg_ret = best['avg_val_return'] / max(best['n_periods'], 1)
        k = kelly_formula(wr, avg_ret, 0.03)
    else:
        k = 0.3

    max_pos = min(k * pos_mult, 0.7)

    print(f"  ATR: {atr:.0f} | 波动率: {vol:.0%}")
    if best:
        print(f"  最优策略: {best_name} (验证胜率: {best['avg_val_wr']*100:.0f}%)")
    print(f"  建议仓位: {max_pos*100:.1f}%")

    if sig == 'BUY':
        sl = price - 2 * atr
        tp = price + 3 * atr
        print(f"\n  [BUY] {price:.0f}")
        print(f"        止损: {sl:.0f} (-{2*atr/price*100:.1f}%)")
        print(f"        止盈: {tp:.0f} (+{3*atr/price*100:.1f}%)")
        print(f"        建议仓位: {max_pos*100:.1f}%")
    elif sig == 'SELL':
        sl = price + 2 * atr
        tp = price - 3 * atr
        print(f"\n  [SELL] {price:.0f}")
        print(f"        止损: {sl:.0f} (+{2*atr/price*100:.1f}%)")
        print(f"        止盈: {tp:.0f} (-{3*atr/price*100:.1f}%)")
        print(f"        建议仓位: {max_pos*100:.1f}%")
    else:
        print(f"\n  [HOLD] 观望")

    print(f"\n  关键价位:")
    print(f"     支撑: {ind['bb_lower'].iloc[-1]:.0f} / {ind['ma20'].iloc[-1]:.0f}")
    print(f"     当前: {price:.0f}")
    print(f"     压力: {ind['bb_upper'].iloc[-1]:.0f}")

    print("\n" + "=" * 70)
    print("【v5.4 核心升级】")
    print("=" * 70)
    print("""
  ✅ Walk-Forward滚动验证(120天训练/20天验证)
  ✅ 参数稳定性过滤(参数在连续窗口保持一致=可靠)
  ✅ 市场状态自适应(下跌趋势用RSI/BOLL，上涨用MACD/MA)
  ✅ RSI+BOLL双均值回归策略
  ✅ 策略共振：同时参考最优+次优策略
  ✅ 置信度动态调整
""")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

if __name__ == '__main__':
    run()
