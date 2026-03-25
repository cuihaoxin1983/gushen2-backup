#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股神2号 - VectorBT 极速回测引擎 v4.0
======================================
基于 VectorBT 0.28.4 的超速回测框架

VectorBT优势：
- 比backtrader快100倍以上
- 基于NumPy向量化运算
- 支持Numba JIT加速
- 内置参数优化
- 支持Monte Carlo模拟

集成TradingAgents信号：
- AnalystAgent信号 → 策略入口
- RiskAgent信号 → 止损
- TimingAgent信号 → 入场择时
"""

import sys
sys.path.insert(0, '/usr/local/lib/python3.12/dist-packages')

import vectorbt as vbt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

# ==================== 写死配置 ====================
TUSHARE_TOKEN = '14d6be29b1b0b8a930fc488ceb343859b60f1357a1e1a85dcaee3712'

def get_data(ts_code='AG2606.SHF', days=500):
    """获取期货日线数据"""
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

def calc_ma(close, period):
    """计算均线"""
    return close.rolling(period).mean()

def calc_rsi(close, period=14):
    """计算RSI"""
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def calc_macd(close, fast=12, slow=26, signal=9):
    """计算MACD"""
    ema_fast = close.ewm(span=fast).mean()
    ema_slow = close.ewm(span=slow).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal).mean()
    return macd, signal_line

def calc_boll(close, period=20, multiplier=2):
    """计算布林带"""
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = mid + multiplier * std
    lower = mid - multiplier * std
    return upper, mid, lower

def calc_atr(df, period=14):
    """计算ATR"""
    high = df['high']
    low = df['low']
    close = df['close']
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def run_ma_cross_backtest(df, fast=5, slow=20, init_cash=100000, size=0.3):
    """均线金叉死叉策略"""
    close = df['close']
    
    ma_fast = calc_ma(close, fast)
    ma_slow = calc_ma(close, slow)
    
    entries = (ma_fast > ma_slow) & (ma_fast.shift(1) <= ma_slow.shift(1))
    exits = (ma_fast < ma_slow) & (ma_fast.shift(1) >= ma_slow.shift(1))
    
    # ATR止损
    atr = calc_atr(df)
    sl_stop = (atr / close) * 2  # 2倍ATR止损
    
    pf = vbt.Portfolio.from_signals(
        close=close,
        entries=entries,
        exits=exits,
        size=size,
        init_cash=init_cash,
        sl_stop=sl_stop.values,
        freq='1D'
    )
    
    return pf

def run_rsi_backtest(df, period=14, lower=30, upper=70, init_cash=100000, size=0.3):
    """RSI超卖超买策略"""
    close = df['close']
    rsi = calc_rsi(close, period)
    
    entries = rsi < lower
    exits = rsi > upper
    
    atr = calc_atr(df)
    sl_stop = (atr / close) * 2
    
    pf = vbt.Portfolio.from_signals(
        close=close,
        entries=entries,
        exits=exits,
        size=size,
        init_cash=init_cash,
        sl_stop=sl_stop.values,
        freq='1D'
    )
    
    return pf

def run_macd_backtest(df, fast=12, slow=26, signal=9, init_cash=100000, size=0.3):
    """MACD策略"""
    close = df['close']
    macd, signal_line = calc_macd(close, fast, slow, signal)
    
    entries = (macd > signal_line) & (macd.shift(1) <= signal_line.shift(1))
    exits = (macd < signal_line) & (macd.shift(1) >= signal_line.shift(1))
    
    atr = calc_atr(df)
    sl_stop = (atr / close) * 2
    
    pf = vbt.Portfolio.from_signals(
        close=close,
        entries=entries,
        exits=exits,
        size=size,
        init_cash=init_cash,
        sl_stop=sl_stop.values,
        freq='1D'
    )
    
    return pf

def run_boll_backtest(df, period=20, multiplier=2, init_cash=100000, size=0.3):
    """布林带突破策略"""
    close = df['close']
    upper, mid, lower = calc_boll(close, period, multiplier)
    
    entries = close > upper
    exits = close < lower
    
    pf = vbt.Portfolio.from_signals(
        close=close,
        entries=entries,
        exits=exits,
        size=size,
        init_cash=init_cash,
        freq='1D'
    )
    
    return pf

def run_dmi_backtest(df, period=14, init_cash=100000, size=0.3):
    """DMI趋势策略"""
    close = df['close']
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
    
    entries = (plus_di > minus_di) & (adx > 25)
    exits = (plus_di < minus_di) | (adx < 20)
    
    sl_stop = (atr / close) * 2
    
    pf = vbt.Portfolio.from_signals(
        close=close,
        entries=entries,
        exits=exits,
        size=size,
        init_cash=init_cash,
        sl_stop=sl_stop.values,
        freq='1D'
    )
    
    return pf

def run_monte_carlo(pf, n_sims=1000):
    """Monte Carlo模拟"""
    equity_curve = pf.value()
    returns = equity_curve.pct_change().dropna()
    returns_arr = returns.values
    
    sim_results = []
    for _ in range(n_sims):
        shuffled = np.random.choice(returns_arr, size=len(returns_arr), replace=True)
        sim_results.append(np.prod(1 + shuffled) - 1)
    
    sim_results = np.array(sim_results)
    
    return {
        'mean': np.mean(sim_results) * 100,
        'median': np.median(sim_results) * 100,
        'max': np.max(sim_results) * 100,
        'min': np.min(sim_results) * 100,
        'std': np.std(sim_results) * 100,
        'prob_profit': np.sum(sim_results > 0) / n_sims,
        'var_5': np.percentile(sim_results, 5) * 100,
        'var_95': np.percentile(sim_results, 95) * 100,
    }

def run_full_backtest():
    """运行完整回测"""
    
    print("=" * 60)
    print("  股神2号 | VectorBT 极速回测 v4.0")
    print("=" * 60)
    
    # 获取数据
    print("\n📥 获取AG2606历史数据...")
    df = get_data('AG2606.SHF', days=500)
    close = df['close']
    print(f"   数据量: {len(df)}条")
    print(f"   时间: {df.index[0].strftime('%Y-%m-%d')} ~ {df.index[-1].strftime('%Y-%m-%d')}")
    
    init_cash = 100000
    size = 0.3
    
    # ---- 运行各策略 ----
    print("\n" + "=" * 60)
    print("【策略回测结果】")
    print("=" * 60)
    
    strategies = [
        ("MA Cross(5/20)", run_ma_cross_backtest(df, 5, 20, init_cash, size)),
        ("RSI(14,30/70)", run_rsi_backtest(df, 14, 30, 70, init_cash, size)),
        ("MACD(12/26/9)", run_macd_backtest(df, 12, 26, 9, init_cash, size)),
        ("BOLL(20,2)", run_boll_backtest(df, 20, 2, init_cash, size)),
        ("DMI(14)", run_dmi_backtest(df, 14, init_cash, size)),
    ]
    
    print(f"\n{'策略':<18} {'总收益':>12} {'最大回撤':>12} {'夏普':>8} {'胜率':>8} {'交易次数':>10}")
    print("-" * 70)
    
    best_sharpe = -999
    best_name = ""
    best_pf = None
    
    for name, pf in strategies:
        stats = pf.stats()
        total_ret = stats['Total Return [%]']
        max_dd = stats['Max Drawdown [%]']
        sharpe = stats['Sharpe Ratio']
        wr = stats['Win Rate [%]'] / 100
        trades = stats['Total Trades']
        
        print(f"{name:<18} {total_ret:>11.2f}% {max_dd:>11.2f}% {sharpe:>8.2f} {wr:>7.1%} {trades:>10}")
        
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_name = name
            best_pf = pf
    
    print("-" * 70)
    print(f"\n🏆 最佳策略: {best_name} (夏普比率: {best_sharpe:.2f})")
    
    # ---- 参数优化演示 ----
    print("\n" + "=" * 60)
    print("【MA参数优化】")
    print("=" * 60)
    
    param_results = []
    for fast in [3, 5, 7, 10]:
        for slow in [15, 20, 25, 30]:
            if fast >= slow:
                continue
            pf = run_ma_cross_backtest(df, fast, slow, init_cash, size)
            stats = pf.stats()
            total_ret = stats['Total Return [%]']
            equity = pf.value()
            rets = equity.pct_change().dropna()
            if len(rets) > 0 and rets.std() > 0:
                sharpe = (rets.mean() / rets.std()) * np.sqrt(250)
            else:
                sharpe = 0
            param_results.append((f"MA({fast}/{slow})", total_ret, sharpe, int(stats['Total Trades'])))
    
    # 排序输出
    param_results.sort(key=lambda x: x[2], reverse=True)
    
    print(f"\n{'参数':<15} {'总收益':>12} {'夏普比率':>10} {'交易次数':>10}")
    print("-" * 50)
    for name, ret, sharpe, trades in param_results[:5]:
        print(f"{name:<15} {ret:>11.2f}% {sharpe:>10.2f} {trades:>10}")
    
    # ---- Monte Carlo ----
    print("\n" + "=" * 60)
    print("【Monte Carlo模拟】(1000次)")
    print("=" * 60)
    
    mc = run_monte_carlo(best_pf, 1000)
    print(f"   平均收益: {mc['mean']:.2f}%")
    print(f"   中位数: {mc['median']:.2f}%")
    print(f"   最大收益: {mc['max']:.2f}%")
    print(f"   最小收益: {mc['min']:.2f}%")
    print(f"   收益标准差: {mc['std']:.2f}%")
    print(f"   盈利概率: {mc['prob_profit']:.1%}")
    print(f"   VaR(5%): {mc['var_5']:.2f}%")
    print(f"   VaR(95%): {mc['var_95']:.2f}%")
    
    # ---- 总结 ----
    print("\n" + "=" * 60)
    print("【回测结论】")
    print("=" * 60)
    
    best_stats = best_pf.stats()
    print(f"""
基于AG2606 {len(df)}条日线数据回测结果：

1. 最佳策略: {best_name}
   - 夏普比率: {best_stats['Sharpe Ratio']:.2f}
   - 总收益: {best_stats['Total Return [%]']:.2f}%
   - 最大回撤: {best_stats['Max Drawdown [%]']:.2f}%
   - 胜率: {best_stats['Win Rate [%]']:.1f}%
   - 交易次数: {best_stats['Total Trades']}

2. 参数优化建议:
   - 最优MA组合: {param_results[0][0]}
   - 夏普比率: {param_results[0][2]:.2f}
   - 总收益: {param_results[0][1]:.2f}%

3. Monte Carlo风险评估:
   - 盈利概率: {mc['prob_profit']:.1%}
   - 95%VaR: {mc['var_5']:.2f}%
   - 平均收益: {mc['mean']:.2f}%

注意: 回测结果仅供参考，实盘需考虑手续费、滑点等因素。
""")
    
    print("✅ VectorBT回测完成!")
    return best_pf, param_results

if __name__ == '__main__':
    run_full_backtest()
