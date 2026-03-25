#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股神2号 - AG2606 实时30分钟K线监控
模拟文华财经Wh8风格界面
数据源: Tushare Pro (rt_fut_min) - Token已写死
"""

import sys
sys.path.insert(0, '/usr/local/lib/python3.12/dist-packages')

import tushare as ts
from datetime import datetime, timedelta
import os

# ==================== 写死配置 ====================
TUSHARE_TOKEN = '14d6be29b1b0b8a930fc488ceb343859b60f1357a1e1a85dcaee3712'
TS_CODE = 'AG2606.SHF'
FREQ = '30MIN'

ts.set_token(TUSHARE_TOKEN)
PRO = ts.pro_api()

# ==================== 颜色定义 ====================
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
BOLD = '\033[1m'
RESET = '\033[0m'

def color_text(text, color):
    return f"{color}{text}{RESET}"

def get_rt_data() -> tuple:
    """获取实时分钟数据"""
    df = PRO.rt_fut_min(ts_code=TS_CODE, freq=FREQ)
    
    if len(df) == 0:
        return None, None, None
    
    latest = df.iloc[-1]
    
    kline = {
        'time': latest.get('time', latest.get('trade_time', '')),
        'open': latest.get('open', latest.get('close', 0)),
        'high': latest.get('high', latest.get('close', 0)),
        'low': latest.get('low', latest.get('close', 0)),
        'close': latest.get('close', 0),
        'vol': latest.get('vol', 0),
        'amount': latest.get('amount', 0),
        'oi': latest.get('oi', 0),
    }
    
    return kline, df

def get_daily_ma() -> dict:
    """从日线数据计算均线作为参考"""
    try:
        daily = PRO.fut_daily(
            ts_code=TS_CODE,
            start_date=(datetime.now() - timedelta(days=60)).strftime('%Y%m%d'),
            end_date=datetime.now().strftime('%Y%m%d')
        )
        daily = daily.sort_values('trade_date')
        closes = list(daily['close'])
        
        result = {}
        if len(closes) >= 5:
            result['ma5'] = sum(closes[-5:]) / 5
        if len(closes) >= 10:
            result['ma10'] = sum(closes[-10:]) / 10
        if len(closes) >= 20:
            result['ma20'] = sum(closes[-20:]) / 20
        if len(closes) >= 20:
            bb_period = closes[-20:]
            ma = sum(bb_period) / 20
            variance = sum((x - ma) ** 2 for x in bb_period) / 20
            std = variance ** 0.5
            result['bb_upper'] = ma + 2 * std
            result['bb_mid'] = ma
            result['bb_lower'] = ma - 2 * std
        
        return result
    except:
        return {}

def display(kline, daily_ma):
    """显示界面"""
    os.system('clear')
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    print("=" * 60)
    print(f"{BOLD}  股神2号 - AG2606 30分钟K线实时监控{RESET}")
    print(f"  更新时间: {now}")
    print("=" * 60)
    
    if kline is None:
        print(f"{RED}❌ 数据获取失败{RESET}")
        return
    
    c = kline['close']
    o = kline['open']
    h = kline['high']
    l = kline['low']
    vol = kline['vol']
    oi = kline['oi']
    
    # 涨跌
    change = c - o
    pct = (change / o * 100) if o != 0 else 0
    
    price_color = GREEN if change > 0 else RED if change < 0 else YELLOW
    trend = "▲ 上涨" if change > 0 else "▼ 下跌" if change < 0 else "■ 平"
    
    print(f"\n{BOLD}{BLUE}  AG2606.SHF 白银主力{RESET}")
    print("-" * 60)
    print(f"\n  当前价: {price_color}{BOLD}{c:.0f}{RESET}")
    print(f"  开盘: {o:.0f}  最高: {h:.0f}  最低: {l:.0f}")
    print(f"  涨跌: {price_color}{change:+.0f} ({pct:+.2f}%){RESET}  {trend}")
    print(f"  成交量: {vol:,.0f}    持仓量: {oi:,.0f}")
    
    # 日线均线参考
    if daily_ma:
        print(f"\n{BOLD}  日线均线参考:{RESET}")
        ma5 = daily_ma.get('ma5', 0)
        ma10 = daily_ma.get('ma10', 0)
        ma20 = daily_ma.get('ma20', 0)
        
        print(f"  MA5:  {GREEN if c > ma5 else RED}{ma5:.0f}{RESET}  ", end="")
        print(f"MA10: {GREEN if c > ma10 else RED}{ma10:.0f}{RESET}  ", end="")
        print(f"MA20: {GREEN if c > ma20 else RED}{ma20:.0f}{RESET}")
        
        # 布林带
        bb_u = daily_ma.get('bb_upper', 0)
        bb_m = daily_ma.get('bb_mid', 0)
        bb_l = daily_ma.get('bb_lower', 0)
        if bb_u:
            print(f"\n{BOLD}  日线布林带:{RESET}")
            print(f"  上轨: {bb_u:.0f}  中轨: {GREEN if c > bb_m else RED}{bb_m:.0f}{RESET}  下轨: {bb_l:.0f}")
    
    # K线形态
    print(f"\n{BOLD}  形态分析:{RESET}")
    body = abs(c - o)
    upper_shadow = h - max(c, o)
    lower_shadow = min(c, o) - l
    full_range = h - l
    
    if full_range > 0:
        body_ratio = body / full_range
        
        if upper_shadow > body * 2 and lower_shadow < body:
            print(f"  ⚠️  倒锤头 → 上涨受阻")
        elif lower_shadow > body * 2 and upper_shadow < body:
            print(f"  ⚠️  锤子线 → 下跌受阻")
        elif body_ratio < 0.1:
            print(f"  ⚠️  十字星 → 多空分歧")
        elif c > o and c >= h * 0.998:
            print(f"  ✅ 光头阳线 → 强势")
        elif c < o and c <= l * 1.002:
            print(f"  ⚠️  光脚阴线 → 弱势")
        else:
            print(f"  → 常态K线")
    
    # 综合信号
    print(f"\n{BOLD}  综合信号:{RESET}")
    signals = []
    if daily_ma:
        if c > daily_ma.get('ma5', 0) and c > daily_ma.get('ma10', 0) and c > daily_ma.get('ma20', 0):
            signals.append("日线多头排列")
        elif c < daily_ma.get('ma5', 0) and c < daily_ma.get('ma10', 0) and c < daily_ma.get('ma20', 0):
            signals.append("日线空头排列")
        
        if c > daily_ma.get('ma5', 0):
            signals.append(f"站在MA5({daily_ma.get('ma5',0):.0f})上方")
        else:
            signals.append(f"跌破MA5({daily_ma.get('ma5',0):.0f})下方")
        
        bb_u = daily_ma.get('bb_upper', 0)
        bb_l = daily_ma.get('bb_lower', 0)
        if bb_u and c > bb_u:
            signals.append("突破布林上轨(超买)")
        elif bb_l and c < bb_l:
            signals.append("跌破布林下轨(超卖)")
    
    if not signals:
        print("  (日线数据不足)")
    for sig in signals:
        print(f"  • {sig}")
    
    # 持仓量变化判断
    try:
        daily2 = PRO.fut_daily(
            ts_code=TS_CODE,
            start_date=(datetime.now() - timedelta(days=5)).strftime('%Y%m%d'),
            end_date=datetime.now().strftime('%Y%m%d')
        )
        if len(daily2) >= 2:
            oi_prev = daily2.iloc[-2]['oi']
            oi_now = daily2.iloc[-1]['oi']
            oi_chg = (oi_now - oi_prev) / oi_prev * 100 if oi_prev else 0
            oi_str = f"持仓量5日变化: {GREEN if oi_chg > 0 else RED}{oi_chg:+.1f}%{RESET}"
            print(f"\n  {oi_str}")
    except:
        pass
    
    print("\n" + "=" * 60)
    print(f"  数据源: Tushare Pro (Token已写死 | 接口rt_fut_min)")
    print(f"  注意: 30分钟历史数据需fut_bar权限，当前用日线均线作参考")
    print(f"  按 Ctrl+C 退出")
    print("=" * 60)

def main():
    print("启动 AG2606 30分钟K线监控...")
    print("按 Ctrl+C 停止\n")
    
    try:
        kline, df = get_rt_data()
        daily_ma = get_daily_ma()
        display(kline, daily_ma)
    except KeyboardInterrupt:
        print("\n监控已停止")
    except Exception as e:
        import traceback
        print(f"{RED}错误: {e}{RESET}")
        traceback.print_exc()

if __name__ == '__main__':
    main()
