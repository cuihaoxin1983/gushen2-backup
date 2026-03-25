#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股神2号 - 最佳进场选时系统
==============================
基于专家指标体系，找出最佳买入/卖出时机

核心逻辑：
- BOLL超卖区间（<20%）+ WR超卖（>80）+ MACD底部背离 = 最佳买点
- BOLL超买区间（>80%）+ WR超买（<20）+ MACD顶部背离 = 最佳卖点
- DMI+向上突破 + SAR翻红 = 趋势确认做多
- DMI-向上突破 + SAR翻绿 = 趋势确认做空
"""

import sys
sys.path.insert(0, '/usr/local/lib/python3.12/dist-packages')

import tushare as ts
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

TUSHARE_TOKEN = '14d6be29b1b0b8a930fc488ceb343859b60f1357a1e1a85dcaee3712'
ts.set_token(TUSHARE_TOKEN)
PRO = ts.pro_api()

RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
BOLD = '\033[1m'
RESET = '\033[0m'

# ============================================================
# 数据获取
# ============================================================

def get_data(ts_code='AG2606.SHF', days=120):
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
    df = PRO.fut_daily(ts_code=ts_code, start_date=start, end_date=end)
    df = df.sort_values('trade_date').reset_index(drop=True)
    return df

def get_rt_price(ts_code='AG2606.SHF'):
    """获取实时价格"""
    try:
        df = PRO.rt_fut_min(ts_code=ts_code, freq='5MIN')
        if len(df) > 0:
            return df.iloc[-1]['close']
    except:
        pass
    return None

# ============================================================
# 指标计算
# ============================================================

def calc_all_indicators(df):
    """计算所有进场相关指标"""
    results = {}
    closes = df['close']
    high = df['high']
    low = df['low']
    
    # ---- BOLL ----
    ma20 = closes.tail(20).mean()
    std20 = closes.tail(20).std()
    boll_upper = ma20 + 2 * std20
    boll_mid = ma20
    boll_lower = ma20 - 2 * std20
    boll_pos = (closes.iloc[-1] - boll_lower) / (boll_upper - boll_lower) * 100
    
    results['boll'] = {
        'upper': boll_upper, 'mid': boll_mid, 'lower': boll_lower,
        'pos': boll_pos,
        'is_oversold': boll_pos < 20,
        'is_overbought': boll_pos > 80
    }
    
    # ---- WR ----
    wr14 = (high.rolling(14).max() - closes) / (high.rolling(14).max() - low.rolling(14).min()) * 100
    wr_val = wr14.iloc[-1]
    results['wr'] = {
        'value': wr_val,
        'is_oversold': wr_val > 80,
        'is_overbought': wr_val < 20
    }
    
    # ---- MACD ----
    ema12 = closes.ewm(span=12).mean()
    ema26 = closes.ewm(span=26).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9).mean()
    macd_bar = (dif - dea) * 2
    
    dif_now = dif.iloc[-1]
    dea_now = dea.iloc[-1]
    bar_now = macd_bar.iloc[-1]
    bar_prev = macd_bar.iloc[-2]
    bar_prev2 = macd_bar.iloc[-3] if len(macd_bar) >= 3 else bar_prev
    
    # 底部背离检测
    price_now = closes.iloc[-1]
    price_low = low.tail(5).min()
    bar_low = macd_bar.tail(5).min()
    
    results['macd'] = {
        'dif': dif_now, 'dea': dea_now, 'bar': bar_now,
        'is_golden_cross': bar_prev < 0 and bar_now > 0,
        'is_death_cross': bar_prev > 0 and bar_now < 0,
        'bottom_divergence': price_now < closes.iloc[-3] and bar_now > bar_prev2,
        'top_divergence': price_now > closes.iloc[-3] and bar_now < bar_prev2
    }
    
    # ---- DMI ----
    tr1 = high - low
    tr2 = abs(high - closes.shift(1))
    tr3 = abs(low - closes.shift(1))
    tr = pd.concat([tr1, tr2.reset_index(drop=True), tr3.reset_index(drop=True)], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean()
    
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
    
    plus_di = (plus_dm.rolling(14).mean() / atr14) * 100
    minus_di = (minus_dm.rolling(14).mean() / atr14) * 100
    dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100
    adx = dx.rolling(14).mean()
    
    results['dmi'] = {
        'plus_di': plus_di.iloc[-1],
        'minus_di': minus_di.iloc[-1],
        'adx': adx.iloc[-1],
        'trend': 'bullish' if plus_di.iloc[-1] > minus_di.iloc[-1] else 'bearish'
    }
    
    # ---- SAR ----
    sar_val = low.iloc[0]
    af = 0.02
    ep = high.iloc[0]
    is_up = True
    
    for i in range(1, len(df)):
        if is_up:
            sar_val = sar_val + af * (ep - sar_val)
            if low.iloc[i] < sar_val:
                is_up = False
                sar_val = ep
                af = 0.02
                ep = low.iloc[i]
            else:
                if high.iloc[i] > ep:
                    ep = high.iloc[i]
                    af = min(af + 0.02, 0.2)
        else:
            sar_val = sar_val - af * (sar_val - ep)
            if high.iloc[i] > sar_val:
                is_up = True
                sar_val = ep
                af = 0.02
                ep = high.iloc[i]
            else:
                if low.iloc[i] < ep:
                    ep = low.iloc[i]
                    af = min(af + 0.02, 0.2)
    
    results['sar'] = {
        'value': sar_val,
        'is_up': is_up,
        'signal': '做多' if is_up else '做空'
    }
    
    # ---- KDJ ----
    n = 9
    low_n = low.rolling(n).min()
    high_n = high.rolling(n).max()
    rsv = (closes - low_n) / (high_n - low_n) * 100
    k = rsv.ewm(com=2).mean()
    d = k.ewm(com=2).mean()
    j = 3 * k - 2 * d
    
    k_now, d_now = k.iloc[-1], d.iloc[-1]
    k_prev, d_prev = k.iloc[-2], d.iloc[-2]
    
    results['kdj'] = {
        'k': k_now, 'd': d_now, 'j': j.iloc[-1],
        'golden_cross': k_prev < d_prev and k_now > d_now,
        'death_cross': k_prev > d_prev and k_now < d_now,
        'oversold': k_now < 20,
        'overbought': k_now > 80
    }
    
    # ---- 均线 ----
    ma5 = closes.tail(5).mean()
    ma10 = closes.tail(10).mean()
    ma20 = closes.tail(20).mean()
    ma60 = closes.tail(60).mean() if len(closes) >= 60 else None
    
    results['ma'] = {
        'ma5': ma5, 'ma10': ma10, 'ma20': ma20, 'ma60': ma60,
        'price': closes.iloc[-1],
        'above_ma5': closes.iloc[-1] > ma5,
        'above_ma20': closes.iloc[-1] > ma20,
        'golden_ma5_20': ma5 > ma10 and closes.iloc[-1] > ma5,
        'death_ma5_20': ma5 < ma10 and closes.iloc[-1] < ma5
    }
    
    # ---- ATR止损 ----
    atr = atr14.iloc[-1]
    results['atr'] = atr
    
    return results

# ============================================================
# 选时决策
# ============================================================

def analyze_entry_points(ind):
    """分析最佳进场点"""
    
    price = ind['ma']['price']
    boll = ind['boll']
    wr = ind['wr']
    macd = ind['macd']
    dmi = ind['dmi']
    sar = ind['sar']
    kdj = ind['kdj']
    ma = ind['ma']
    atr = ind['atr']
    
    buy_score = 0
    sell_score = 0
    buy_reasons = []
    sell_reasons = []
    
    # ========== 买入信号 ==========
    
    # BOLL超卖
    if boll['is_oversold']:
        buy_score += 2
        buy_reasons.append(f"BOLL超卖({boll['pos']:.0f}%)")
    
    # WR超卖
    if wr['is_oversold']:
        buy_score += 1
        buy_reasons.append(f"WR超卖({wr['value']:.0f})")
    
    # MACD底部背离
    if macd['bottom_divergence']:
        buy_score += 3
        buy_reasons.append("MACD底背离")
    
    # MACD金叉
    if macd['is_golden_cross']:
        buy_score += 2
        buy_reasons.append("MACD金叉")
    
    # DMI做多
    if dmi['trend'] == 'bullish':
        buy_score += 1
        buy_reasons.append("DMI偏多")
    
    # SAR翻红
    if sar['is_up']:
        buy_score += 2
        buy_reasons.append(f"SAR翻红({sar['value']:.0f})")
    
    # KDJ超卖金叉
    if kdj['oversold'] and kdj['golden_cross']:
        buy_score += 2
        buy_reasons.append("KDJ超卖金叉")
    
    # 均线金叉
    if ma['golden_ma5_20']:
        buy_score += 1
        buy_reasons.append("MA5上穿MA10")
    
    # ========== 卖出信号 ==========
    
    if boll['is_overbought']:
        sell_score += 2
        sell_reasons.append(f"BOLL超买({boll['pos']:.0f}%)")
    
    if wr['is_overbought']:
        sell_score += 1
        sell_reasons.append(f"WR超买({wr['value']:.0f})")
    
    if macd['top_divergence']:
        sell_score += 3
        sell_reasons.append("MACD顶背离")
    
    if macd['is_death_cross']:
        sell_score += 2
        sell_reasons.append("MACD死叉")
    
    if dmi['trend'] == 'bearish':
        sell_score += 1
        sell_reasons.append("DMI偏空")
    
    if not sar['is_up']:
        sell_score += 2
        sell_reasons.append(f"SAR翻绿({sar['value']:.0f})")
    
    if kdj['overbought'] and kdj['death_cross']:
        sell_score += 2
        sell_reasons.append("KDJ超买死叉")
    
    if ma['death_ma5_20']:
        sell_score += 1
        sell_reasons.append("MA5下穿MA10")
    
    # ========== 止盈止损计算 ==========
    
    if buy_score > sell_score:
        direction = "做多"
        confidence = min(buy_score / 10, 1.0)
        entry_price = price
        stop_loss = price - 2 * atr
        take_profit = price + 3 * atr
        risk_reward = 3 * atr / (2 * atr) if atr > 0 else 0
        
        # 最佳买入区间
        if boll['is_oversold']:
            buy_zone = f"布林下轨附近({boll['lower']:.0f})"
        elif wr['is_oversold']:
            buy_zone = f"WR超卖区间({wr['value']:.0f})"
        else:
            buy_zone = f"当前价格({price:.0f})"
            
    elif sell_score > buy_score:
        direction = "做空"
        confidence = min(sell_score / 10, 1.0)
        entry_price = price
        stop_loss = price + 2 * atr
        take_profit = price - 3 * atr
        risk_reward = 3 * atr / (2 * atr) if atr > 0 else 0
        buy_zone = f"当前价格({price:.0f})"
    else:
        direction = "观望"
        confidence = 0.3
        entry_price = price
        stop_loss = 0
        take_profit = 0
        risk_reward = 0
    
    return {
        'direction': direction,
        'confidence': confidence,
        'buy_score': buy_score,
        'sell_score': sell_score,
        'buy_reasons': buy_reasons,
        'sell_reasons': sell_reasons,
        'entry_price': entry_price,
        'stop_loss': stop_loss,
        'take_profit': take_profit,
        'risk_reward': risk_reward,
        'buy_zone': buy_zone,
        'price': price,
        'atr': atr,
        'boll_pos': boll['pos'],
        'boll_lower': boll['lower'],
        'boll_upper': boll['upper'],
        'ma5': ma['ma5'],
        'ma20': ma['ma20']
    }

# ============================================================
# 显示
# ============================================================

def display_timing_report(ts_code='AG2606.SHF'):
    """显示选时报告"""
    
    os.system('clear')
    
    df = get_data(ts_code)
    ind = calc_all_indicators(df)
    result = analyze_entry_points(ind)
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    print("=" * 60)
    print(f"{BOLD}{BLUE}  股神2号 | 最佳进场选时系统{RESET}")
    print(f"  AG2606白银  |  {now}")
    print("=" * 60)
    
    price = result['price']
    
    print(f"\n{BOLD}【当前行情】{RESET}")
    print(f"  当前价格: {price:.0f}")
    print(f"  ATR波动:  {result['atr']:.1f} (波动率约{result['atr']/price*100:.1f}%)")
    print(f"  BOLL位置: {result['boll_pos']:.1f}%  (下轨={result['boll_lower']:.0f}, 上轨={result['boll_upper']:.0f})")
    print(f"  MA5={result['ma5']:.0f}  MA20={result['ma20']:.0f}")
    
    print(f"\n{BOLD}【多空信号打分】{RESET}")
    print(f"  {'买入信号:':>12} {GREEN}{result['buy_score']}分{RESET}  {'卖出信号:':>12} {RED}{result['sell_score']}分{RESET}")
    
    if result['buy_score'] > result['sell_score']:
        print(f"  方向: {GREEN}做多{RESET} (置信度{result['confidence']:.0%})")
    elif result['sell_score'] > result['buy_score']:
        print(f"  方向: {RED}做空{RESET} (置信度{result['confidence']:.0%})")
    else:
        print(f"  方向: {YELLOW}观望{RESET}")
    
    print(f"\n{BOLD}【买入理由】{RESET}")
    if result['buy_reasons']:
        for r in result['buy_reasons']:
            print(f"  ✅ {r}")
    else:
        print(f"  (无明确买入信号)")
    
    print(f"\n{BOLD}【卖出理由】{RESET}")
    if result['sell_reasons']:
        for r in result['sell_reasons']:
            print(f"  🔴 {r}")
    else:
        print(f"  (无明确卖出信号)")
    
    print(f"\n{'='*60}")
    print(f"{BOLD}{GREEN}【最佳进场方案】{RESET}")
    print(f"{'='*60}")
    
    if result['direction'] == "观望":
        print(f"\n  {YELLOW}⚠️ 当前无明确方向，建议观望等待{RESET}")
    else:
        print(f"\n  📍 最佳买入区间: {result['buy_zone']}")
        print(f"  🎯 入场价格: {result['entry_price']:.0f}")
        print(f"  🛑 止损价格: {result['stop_loss']:.0f} (2×ATR={result['atr']*2:.0f})")
        print(f"  🎯 止盈价格: {result['take_profit']:.0f} (3×ATR={result['atr']*3:.0f})")
        print(f"  📊 盈亏比: 1:{result['risk_reward']:.1f}")
        
        rr = result['risk_reward']
        if rr >= 2:
            rr_color = GREEN
            rr_eval = "优秀"
        elif rr >= 1.5:
            rr_color = YELLOW
            rr_eval = "良好"
        else:
            rr_color = RED
            rr_eval = "一般"
        
        print(f"  ✅ 盈亏比评价: {rr_color}{rr_eval}(1:{rr:.1f}){RESET}")
        
        # 仓位建议
        max_pos = 0.70
        if result['confidence'] < 0.5:
            rec_pos = max_pos * 0.3
            pos_advice = "轻仓试探(30%)"
        elif result['confidence'] < 0.7:
            rec_pos = max_pos * 0.5
            pos_advice = "半仓(50%)"
        else:
            rec_pos = max_pos
            pos_advice = "正常仓位(70%)"
        
        print(f"  💰 建议仓位: {pos_advice}")
        
        # 持仓周期
        if result['direction'] == "做多":
            if ind['boll']['is_oversold'] and ind['kdj']['oversold']:
                hold = "3-5天短线"
            elif ind['dmi']['trend'] == 'bullish':
                hold = "5-10天中线"
            else:
                hold = "1-3天超短"
        else:
            if ind['boll']['is_overbought']:
                hold = "3-5天短线"
            else:
                hold = "1-3天超短"
        
        print(f"  ⏰ 建议持仓周期: {hold}")
    
    print(f"\n{'='*60}")
    print(f"{BOLD}{BLUE}【关键价位提醒】{RESET}")
    print(f"  强支撑: {result['boll_lower']:.0f} (布林下轨)")
    print(f"  当前价: {price:.0f}")
    print(f"  强压力: {result['boll_upper']:.0f} (布林上轨)")
    print(f"  MA20:   {result['ma20']:.0f} (多空分界)")
    print(f"{'='*60}")
    print(f"\n  数据源: Tushare Pro (Token已写死)")
    print(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == '__main__':
    display_timing_report()
