#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股神2号 - 市场状态识别 + MACD背离检测
==========================================
进化v3.1: 
- 市场状态识别（趋势/震荡/高波动）
- MACD背离自动检测
- ATR异常预警
"""

import sys
sys.path.insert(0, '/usr/local/lib/python3.12/dist-packages')

import tushare as ts
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

TUSHARE_TOKEN = '14d6be29b1b0b8a930fc488ceb343859b60f1357a1e1a85dcaee3712'
ts.set_token(TUSHARE_TOKEN)
PRO = ts.pro_api()

def get_data(days=120):
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
    df = PRO.fut_daily(ts_code='AG2606.SHF', start_date=start, end_date=end)
    df = df.sort_values('trade_date').reset_index(drop=True)
    return df

def detect_market_regime(df):
    """市场状态识别：趋势/震荡/高波动"""
    closes = df['close']
    
    # 计算ADX判断趋势强度
    high = df['high']
    low = df['low']
    close = df['close']
    
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1.reset_index(drop=True), tr2.reset_index(drop=True), tr3.reset_index(drop=True)], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean()
    
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
    
    plus_di = (plus_dm.rolling(14).mean() / atr14) * 100
    minus_di = (minus_dm.rolling(14).mean() / atr14) * 100
    dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100
    adx = dx.rolling(14).mean()
    
    adx_val = adx.iloc[-1]
    
    # 趋势判断
    if adx_val > 25:
        if plus_di.iloc[-1] > minus_di.iloc[-1]:
            regime = "上涨趋势"
        else:
            regime = "下跌趋势"
    else:
        regime = "震荡整理"
    
    # 波动率
    vol = closes.pct_change().rolling(20).std().iloc[-1] * np.sqrt(250)
    if vol > 0.20:
        vol_status = "极高波动"
    elif vol > 0.10:
        vol_status = "正常波动"
    else:
        vol_status = "低波动"
    
    return {
        'regime': regime,
        'adx': adx_val,
        'plus_di': plus_di.iloc[-1],
        'minus_di': minus_di.iloc[-1],
        'vol_status': vol_status,
        'volatility': vol
    }

def detect_macd_divergence(df, lookback=20):
    """MACD背离检测"""
    closes = df['close'].tail(lookback)
    
    # 计算MACD
    ema12 = closes.ewm(span=12).mean()
    ema26 = closes.ewm(span=26).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9).mean()
    macd_bar = (dif - dea) * 2
    
    # 找最近5根K线的最低点/最高点
    prices = closes.tail(5).values
    bars = macd_bar.tail(5).values
    
    # 简化背离检测
    price_trend = prices[-1] - prices[0]  # 正=上涨，负=下跌
    macd_trend = bars[-1] - bars[0]  # 正=柱放大，负=柱缩小
    
    divergence = None
    
    # 底背离：价格新低，MACD柱没有新低
    if prices[-1] == prices.min():  # 价格创新低
        if macd_bar.tail(5).min() > macd_bar.tail(10).min():
            divergence = "底背离(看涨)"
    
    # 顶背离：价格新高，MACD柱没有新高
    if prices[-1] == prices.max():  # 价格创新高
        if macd_bar.tail(5).max() < macd_bar.tail(10).max():
            divergence = "顶背离(看跌)"
    
    return {
        'divergence': divergence,
        'dif': dif.iloc[-1],
        'dea': dea.iloc[-1],
        'macd_bar': macd_bar.iloc[-1]
    }

def detect_atr_anomaly(df):
    """ATR异常预警"""
    closes = df['close']
    high = df['high']
    low = df['low']
    close_prev = closes.shift(1)
    
    tr1 = high - low
    tr2 = abs(high - close_prev)
    tr3 = abs(low - close_prev)
    atr = pd.concat([tr1.reset_index(drop=True), tr2.reset_index(drop=True), tr3.reset_index(drop=True)], axis=1).max(axis=1)
    
    atr14 = atr.rolling(14).mean()
    atr_ratio = atr.iloc[-1] / atr14.iloc[-1]
    
    warning = None
    if atr_ratio > 1.5:
        warning = f"🔴 ATR异常放大({atr_ratio:.1f}倍)，警惕大幅波动"
    elif atr_ratio > 1.2:
        warning = f"🟡 ATR偏高({atr_ratio:.1f}倍)，注意风险"
    
    return {
        'atr14': atr14.iloc[-1],
        'atr_current': atr.iloc[-1],
        'atr_ratio': atr_ratio,
        'warning': warning
    }

def generate_insights(df):
    """生成操作建议"""
    regime = detect_market_regime(df)
    divergence = detect_macd_divergence(df)
    atr_info = detect_atr_anomaly(df)
    
    insights = []
    
    # 市场状态建议
    if regime['regime'] == "震荡整理":
        insights.append(("高抛低吸", "区间操作"))
    elif regime['regime'] == "上涨趋势":
        insights.append(("回调做多", "趋势跟随"))
    else:
        insights.append(("反弹做空", "趋势跟随"))
    
    # 波动率建议
    if regime['volatility'] > 0.20:
        insights.append(("降低仓位", f"波动率{regime['volatility']:.0%}极高"))
        insights.append(("缩短持仓周期", "高波动环境"))
    elif regime['volatility'] < 0.10:
        insights.append(("适当加仓", f"波动率{regime['volatility']:.0%}正常"))
    
    # 背离建议
    if divergence['divergence']:
        if "底背离" in divergence['divergence']:
            insights.append(("关注抄底机会", divergence['divergence']))
        else:
            insights.append(("警惕顶部风险", divergence['divergence']))
    
    # ATR预警
    if atr_info['warning']:
        insights.append(("注意止损", atr_info['warning']))
    
    return regime, divergence, atr_info, insights

def run_analysis():
    df = get_data(120)
    price = df['close'].iloc[-1]
    trade_date = df['trade_date'].iloc[-1]
    
    regime, divergence, atr_info, insights = generate_insights(df)
    
    print("=" * 60)
    print(f"  股神2号 v3.1 | AG2606 | {trade_date}")
    print("=" * 60)
    
    print(f"\n📊 市场状态: {regime['regime']}")
    print(f"  ADX={regime['adx']:.1f} DMI+={regime['plus_di']:.1f} DMI-={regime['minus_di']:.1f}")
    print(f"  波动率: {regime['volatility']:.1%} ({regime['vol_status']})")
    
    print(f"\n📉 MACD状态:")
    print(f"  DIF={divergence['dif']:.2f} DEA={divergence['dea']:.2f} MACD柱={divergence['macd_bar']:.2f}")
    if divergence['divergence']:
        print(f"  ⚠️ {divergence['divergence']}")
    else:
        print(f"  无背离")
    
    print(f"\n⚠️ ATR预警:")
    print(f"  ATR={atr_info['atr_current']:.0f} (均值{atr_info['atr14']:.0f})")
    if atr_info['warning']:
        print(f"  {atr_info['warning']}")
    else:
        print(f"  正常")
    
    print(f"\n💡 操作建议:")
    for title, desc in insights:
        print(f"  • {title}: {desc}")
    
    print("=" * 60)
    
    return {
        'regime': regime,
        'divergence': divergence,
        'atr': atr_info,
        'insights': insights,
        'price': price
    }

if __name__ == '__main__':
    run_analysis()
