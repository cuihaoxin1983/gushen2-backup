#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股神2号 - 专家组合指标系统
===============================
基于文华财经/同花顺专家指标体系

包含指标：
1. DMI/ADX - 趋势动量
2. BOLL - 布林带
3. MAKD - MACD
4. MA - 均线系统
5. KDJ - 随机指标
6. WR - 威廉指标
7. ASI - 振动升降指标
8. SAR - 止损点
9. RSRS - 成交量RSRS
10. 操盘分析 - 综合建议

数据源: Tushare Pro (写死Token)
"""

import sys
sys.path.insert(0, '/usr/local/lib/python3.12/dist-packages')

import tushare as ts
import pandas as pd
from datetime import datetime, timedelta
import os

# ==================== 写死配置 ====================
TUSHARE_TOKEN = '14d6be29b1b0b8a930fc488ceb343859b60f1357a1e1a85dcaee3712'
ts.set_token(TUSHARE_TOKEN)
PRO = ts.pro_api()

# ==================== 颜色 ====================
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
BOLD = '\033[1m'
RESET = '\033[0m'

# ============================================================
# 指标计算模块
# ============================================================

def get_data(ts_code='AG2606.SHF', days=100):
    """获取日线数据"""
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
    df = PRO.fut_daily(ts_code=ts_code, start_date=start, end_date=end)
    df = df.sort_values('trade_date').reset_index(drop=True)
    return df

def calc_ma(series, period):
    """均线"""
    if len(series) < period:
        return None
    return series.tail(period).mean()

def calc_ema(series, period):
    """指数移动平均"""
    return series.ewm(span=period).mean().iloc[-1]

def calc_boll(df, period=20, multiplier=2):
    """布林带"""
    closes = df['close']
    if len(closes) < period:
        return None, None, None
    mid = closes.tail(period).mean()
    std = closes.tail(period).std()
    upper = mid + multiplier * std
    lower = mid - multiplier * std
    # 当前位置百分比 (0%=下轨, 50%=中轨, 100%=上轨)
    pos = (closes.iloc[-1] - lower) / (upper - lower) * 100 if upper != lower else 50
    return upper, mid, lower, pos

def calc_macd(df, fast=12, slow=26, signal=9):
    """MACD"""
    closes = df['close']
    ema_fast = closes.ewm(span=fast).mean()
    ema_slow = closes.ewm(span=slow).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal).mean()
    macd_bar = (dif - dea) * 2  # 柱子=2倍差值
    
    dif_val = dif.iloc[-1]
    dea_val = dea.iloc[-1]
    bar_val = macd_bar.iloc[-1]
    bar_prev = macd_bar.iloc[-2]
    
    # 金叉/死叉判断
    if dif_prev := dif.iloc[-2] if len(dif) >= 2 else 0:
        if dif_prev < dea.iloc[-2] and dif_val > dea_val:
            cross = "金叉"
        elif dif_prev > dea.iloc[-2] and dif_val < dea_val:
            cross = "死叉"
        else:
            cross = "纠缠"
    else:
        cross = "纠缠"
    
    return dif_val, dea_val, bar_val, bar_prev, cross

def calc_dmi(df, period=14):
    """DMI/ADX 趋势动量"""
    high = df['high']
    low = df['low']
    close = df['close']
    
    # 真实波幅TR
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # 方向性指标
    plus_dm = high.diff()
    minus_dm = -low.diff()
    
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
    
    # 平滑
    atr = tr.rolling(period).mean()
    plus_di = (plus_dm.rolling(period).mean() / atr) * 100
    minus_di = (minus_dm.rolling(period).mean() / atr) * 100
    
    dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100
    adx = dx.rolling(period).mean()
    
    plus_val = plus_di.iloc[-1]
    minus_val = minus_di.iloc[-1]
    adx_val = adx.iloc[-1]
    
    # 信号
    if plus_val > minus_val:
        sig = "做多"
        strength = plus_val - minus_val
    else:
        sig = "做空"
        strength = minus_val - plus_val
    
    return plus_val, minus_val, adx_val, sig, strength

def calc_kdj(df, n=9, m1=3, m2=3):
    """KDJ指标"""
    low_n = df['low'].rolling(n).min()
    high_n = df['high'].rolling(n).max()
    
    rsv = (df['close'] - low_n) / (high_n - low_n) * 100
    rsv = rsv.fillna(50)
    
    k = rsv.ewm(com=m1-1).mean()
    d = k.ewm(com=m2-1).mean()
    j = 3 * k - 2 * d
    
    k_val = k.iloc[-1]
    d_val = d.iloc[-1]
    j_val = j.iloc[-1]
    
    # KDJ信号
    k_prev = k.iloc[-2]
    d_prev = d.iloc[-2]
    
    if k_prev < d_prev and k_val > d_val:
        kdj_sig = "金叉"
    elif k_prev > d_prev and k_val < d_val:
        kdj_sig = "死叉"
    else:
        kdj_sig = "纠缠"
    
    return k_val, d_val, j_val, kdj_sig

def calc_wr(df, period=14):
    """威廉指标"""
    high_n = df['high'].rolling(period).max()
    low_n = df['low'].rolling(period).min()
    
    wr = (high_n - df['close']) / (high_n - low_n) * 100
    
    wr_val = wr.iloc[-1]
    
    # 超买超卖
    if wr_val > 80:
        sig = "超卖"
    elif wr_val < 20:
        sig = "超买"
    else:
        sig = "正常"
    
    return wr_val, sig

def calc_asi(df, period=10):
    """ASI振动升降指标"""
    high = df['high']
    low = df['low']
    close = df['close']
    
    # 简化ASI
    A = abs(high - close.shift(1))
    B = abs(low - close.shift(1))
    C = abs(high - low.shift(1))
    D = abs(close.shift(1) - open_shifted if (open_shifted := df['open'].shift(1)) is not None else 0)
    
    if len(df) < 2:
        return 0, "纠缠"
    
    # 简化计算
    changes = abs(close - close.shift(1))
    asi = changes.rolling(period).sum()
    
    asi_val = asi.iloc[-1]
    asi_prev = asi.iloc[-2] if len(asi) >= 2 else asi_val
    
    if asi_val > asi_prev:
        sig = "偏多"
    elif asi_val < asi_prev:
        sig = "偏空"
    else:
        sig = "纠缠"
    
    return asi_val, sig

def calc_sar(df, af=0.02, max_af=0.2):
    """SAR止损点"""
    high = df['high']
    low = df['low']
    close = df['close']
    
    n = len(df)
    sar = low.iloc[0]
    af_val = af
    ep = high.iloc[0]
    is_up = True
    
    for i in range(1, n):
        if is_up:
            sar = sar + af_val * (ep - sar)
            if low.iloc[i] < sar:
                is_up = False
                sar = ep
                af_val = af
                ep = low.iloc[i]
            else:
                if high.iloc[i] > ep:
                    ep = high.iloc[i]
                    af_val = min(af_val + af, max_af)
        else:
            sar = sar - af_val * (sar - ep)
            if high.iloc[i] > sar:
                is_up = True
                sar = ep
                af_val = af
                ep = high.iloc[i]
            else:
                if low.iloc[i] < ep:
                    ep = low.iloc[i]
                    af_val = min(af_val + af, max_af)
    
    sar_val = sar
    price = close.iloc[-1]
    
    if price > sar_val:
        sig = "翻红(做多)"
    else:
        sig = "翻绿(做空)"
    
    return sar_val, price, sig

def calc_ma_system(df):
    """均线系统"""
    closes = df['close']
    
    ma5 = calc_ma(closes, 5)
    ma10 = calc_ma(closes, 10)
    ma20 = calc_ma(closes, 20)
    ma30 = calc_ma(closes, 30)
    
    price = closes.iloc[-1]
    
    # 多头排列
    if ma5 and ma10 and ma20 and ma30:
        if ma5 > ma10 > ma20 > ma30:
            trend = "多头排列"
        elif ma5 < ma10 < ma20 < ma30:
            trend = "空头排列"
        else:
            trend = "混乱"
    else:
        trend = "数据不足"
    
    buy_signals = 0
    
    if ma5 and price > ma5:
        buy_signals += 1
    if ma10 and price > ma10:
        buy_signals += 1
    if ma20 and price > ma20:
        buy_signals += 1
    if ma30 and price > ma30:
        buy_signals += 1
    
    return {
        'MA5': ma5, 'MA10': ma10, 'MA20': ma20, 'MA30': ma30,
        'price': price, 'trend': trend, 'buy_signals': buy_signals
    }

def calc_rsrs(df, period=20):
    """成交量RSRS"""
    vol = df['vol']
    close = df['close']
    
    if len(df) < period:
        return None, "数据不足"
    
    # 简化RSRS
    high_slope = (close - close.shift(period)).iloc[-1]
    vol_slope = (vol - vol.shift(period)).iloc[-1]
    
    if vol_slope > 0 and high_slope > 0:
        sig = "买入"
    elif vol_slope < 0 and high_slope < 0:
        sig = "卖出"
    else:
        sig = "中性"
    
    return 1 if sig == "买入" else 0, sig

def calc_trend_analysis(df, ma_sys):
    """操盘分析 - 综合建议"""
    closes = df['close']
    price = closes.iloc[-1]
    
    # 近期高低点
    high20 = closes.tail(20).max()
    low20 = closes.tail(20).min()
    range_val = high20 - low20
    
    # 震荡区间
    mid_range = (high20 + low20) / 2
    
    # 区间判断
    if price > mid_range * 1.01:
        type_ = "上涨趋势"
    elif price < mid_range * 0.99:
        type_ = "下跌趋势"
    else:
        type_ = "震荡行情"
    
    # 建议
    if type_ == "震荡行情":
        long_entry = low20 + range_val * 0.3
        short_entry = high20 - range_val * 0.3
        long_stop = low20 - range_val * 0.05
        short_stop = high20 + range_val * 0.05
        advice = f"{type_}，高抛低吸"
        intraday = f"接近{long_entry:.0f}可短多，止损{long_stop:.0f}；接近{short_entry:.0f}可短空，止损{short_stop:.0f}"
    elif type_ == "上涨趋势":
        advice = "趋势向上，回调做多为主"
        intraday = f"回调不破{ma_sys['MA20']:.0f}可做多"
    else:
        advice = "趋势向下，反弹做空为主"
        intraday = f"反弹不过{ma_sys['MA20']:.0f}可做空"
    
    return {
        'high20': high20,
        'low20': low20,
        'type': type_,
        'advice': advice,
        'intraday': intraday
    }

# ============================================================
# 主显示函数
# ============================================================

def display_expert_report(ts_code='AG2606.SHF'):
    """显示完整专家指标报告"""
    
    os.system('clear')
    
    df = get_data(ts_code)
    price = df['close'].iloc[-1]
    trade_date = df['trade_date'].iloc[-1]
    
    # 计算所有指标
    boll = calc_boll(df)
    macd = calc_macd(df)
    dmi = calc_dmi(df)
    kdj = calc_kdj(df)
    wr = calc_wr(df)
    asi = calc_asi(df)
    sar = calc_sar(df)
    ma_sys = calc_ma_system(df)
    rsrs, rsrs_sig = calc_rsrs(df)
    trend = calc_trend_analysis(df, ma_sys)
    
    print("=" * 60)
    print(f"{BOLD}  股神2号 | 专家组合指标 | AG2606 白银{RESET}")
    print(f"  日期: {trade_date}  当前价: {price:.0f}")
    print("=" * 60)
    
    print(f"\n{BOLD}【DMI/ADX 趋势动量】{RESET}")
    print(f"  DMI+={dmi[0]:.1f}  DMI-={dmi[1]:.1f}  ADX={dmi[2]:.1f}")
    print(f"  信号: {GREEN if dmi[3]=='做多' else RED}{dmi[3]}(强度{dmi[4]:.1f}){RESET}")
    print(f"  建议: {'偏多顺势' if dmi[3]=='做多' else '偏空顺势'}")
    
    print(f"\n{BOLD}【BOLL 布林带】{RESET}")
    print(f"  上轨={boll[0]:.0f}  中轨={boll[1]:.0f}  下轨={boll[2]:.0f}")
    print(f"  当前位置: {boll[3]:.1f}% {GREEN if boll[3]<30 else RED if boll[3]>70 else YELLOW}{'(底部/超卖)' if boll[3]<30 else '(顶部/超买)' if boll[3]>70 else '(中性)'}{RESET}")
    print(f"  信号: {GREEN}买入{RESET} {'(价格触底)' if boll[3]<30 else RED+'(价格触顶)' if boll[3]>70 else YELLOW+'(中性)'}{RESET}")
    
    print(f"\n{BOLD}【MAKD MACD】{RESET}")
    print(f"  DIF={macd[0]:.2f}  DEA={macd[1]:.2f}  MACD柱={macd[2]:+.2f}")
    macd_color = GREEN if macd[2] > 0 else RED
    bar_str = f"绿柱({macd_color}{macd[2]:.2f}{RESET})" if macd[2] < 0 else f"红柱({macd_color}{macd[2]:.2f}{RESET})"
    print(f"  状态: {macd[4]}  {bar_str}")
    print(f"  建议: {GREEN+'做多' if macd[4]=='金叉' else RED+'做空' if macd[4]=='死叉' else YELLOW+'观望'}{RESET}")
    
    print(f"\n{BOLD}【MA 均线系统】{RESET}")
    print(f"  MA5={ma_sys['MA5']:.0f} {'↑' if ma_sys['price'] > ma_sys['MA5'] else '↓'}  ", end="")
    print(f"MA10={ma_sys['MA10']:.0f} {'↑' if ma_sys['price'] > ma_sys['MA10'] else '↓'}  ", end="")
    print(f"MA20={ma_sys['MA20']:.0f} {'↑' if ma_sys['price'] > ma_sys['MA20'] else '↓'}  ", end="")
    print(f"MA30={ma_sys['MA30']:.0f} {'↑' if ma_sys['price'] > ma_sys['MA30'] else '↓'}")
    print(f"  趋势: {GREEN if '多' in ma_sys['trend'] else RED if '空' in ma_sys['trend'] else YELLOW}{ma_sys['trend']}{RESET}  买入信号:{ma_sys['buy_signals']}个")
    
    print(f"\n{BOLD}【KDJ 随机指标】{RESET}")
    print(f"  K={kdj[0]:.1f}  D={kdj[1]:.1f}  J={kdj[2]:.1f}")
    print(f"  信号: {GREEN if kdj[3]=='金叉' else RED if kdj[3]=='死叉' else YELLOW}{kdj[3]}{RESET}")
    
    print(f"\n{BOLD}【WR 威廉指标】{RESET}")
    print(f"  WR={wr[0]:.1f}  状态: {GREEN if '超卖' in wr[1] else RED if '超买' in wr[1] else YELLOW}{wr[1]}{RESET}")
    
    print(f"\n{BOLD}【SAR 止损点】{RESET}")
    print(f"  SAR={sar[0]:.0f}  当前价={sar[1]:.0f}")
    print(f"  信号: {GREEN if '翻红' in sar[2] else RED}{sar[2]}{RESET}")
    
    print(f"\n{BOLD}【ASI 振动升降指标】{RESET}")
    print(f"  ASI={asi[0]:.2f}  信号: {GREEN if asi[1]=='偏多' else RED if asi[1]=='偏空' else YELLOW}{asi[1]}{RESET}")
    
    print(f"\n{BOLD}【RSRS 成交量】{RESET}")
    rsrs_color = GREEN if rsrs == 1 else RED
    print(f"  信号: {rsrs_color}{rsrs_sig}{RESET}  买入信号:{GREEN if rsrs==1 else RED}{rsrs}个{RESET}")
    
    print(f"\n{'='*60}")
    print(f"{BOLD}【操盘分析】{RESET}")
    print(f"  震荡区间: {trend['low20']:.0f} - {trend['high20']:.0f}")
    print(f"  当前状态: {trend['type']}")
    print(f"  核心建议: {trend['advice']}")
    print(f"  日内建议: {trend['intraday']}")
    print(f"{'='*60}")
    
    # ==================== 综合决策 ====================
    print(f"\n{BOLD}{BLUE}【综合决策】{RESET}")
    
    # 汇总各指标信号
    buy_score = 0
    sell_score = 0
    
    # BOLL
    if boll[3] < 30:
        buy_score += 1
    elif boll[3] > 70:
        sell_score += 1
    
    # MACD
    if macd[4] == "金叉":
        buy_score += 2
    elif macd[4] == "死叉":
        sell_score += 2
    
    # DMI
    if dmi[3] == "做多":
        buy_score += 1
    else:
        sell_score += 1
    
    # WR
    if "超卖" in wr[1]:
        buy_score += 1
    elif "超买" in wr[1]:
        sell_score += 1
    
    # SAR
    if "翻红" in sar[2]:
        buy_score += 2
    else:
        sell_score += 2
    
    # KDJ
    if kdj[3] == "金叉":
        buy_score += 1
    elif kdj[3] == "死叉":
        sell_score += 1
    
    print(f"  多头指标数: {GREEN}{buy_score}{RESET}")
    print(f"  空头指标数: {RED}{sell_score}{RESET}")
    
    if buy_score > sell_score + 2:
        final = "🟢 强烈买入"
    elif sell_score > buy_score + 2:
        final = "🔴 强烈卖出"
    elif buy_score > sell_score:
        final = "🟢 买入"
    elif sell_score > buy_score:
        final = "🔴 卖出"
    else:
        final = "⏸️ 观望"
    
    print(f"\n  ★ 综合信号: {final}")
    print(f"\n{'='*60}")
    print(f"  数据源: Tushare Pro (Token已写死)")
    print(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == '__main__':
    display_expert_report()
