#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股神2号 - v6.0 TradingAgents + VectorBT 混合系统
======================================
核心架构（借鉴TradingAgents）：

1. Technical Analyst Agent - 技术指标分析
2. Bull Researcher - 多头研究员（找做多理由）
3. Bear Researcher - 空头研究员（找做空理由）  
4. Debate Module - 多空辩论（VectorBT验证事实）
5. Trader Agent - 综合决策
6. Risk Manager - 风险管理
7. Portfolio Manager - 最终审批

数据：Tushare Pro
LLM：MiniMax (abab6-chat)
回测：VectorBT
"""

import sys
sys.path.insert(0, '/usr/local/lib/python3.12/dist-packages')

import os
import vectorbt as vbt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from openai import OpenAI

# ============ 配置 ============
TUSHARE_TOKEN = '14d6be29b1b0b8a930fc488ceb343859b60f1357a1e1a85dcaee3712'
OPENAI_API_KEY = 'sk-cp-PdInlTwLhgtz3FvquCV2suVp0ZpKjS7RmAXbjAxgBQPF5vgyZO03B_jwID9wxjfC6pX-QcWTKEsJ40zkuo-l2GnpGCTVR6s098_qDKDOn2h8PKiRAGJvByo'
OPENAI_BASE_URL = 'https://api.minimax.chat/v1'

# LLM Client
llm = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
LLM_MODEL = "abab6-chat"

# ============ 数据获取 ============
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

def llm_call(prompt, system_prompt="你是一个专业的量化交易分析师"):
    """调用MiniMax LLM"""
    try:
        response = llm.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"LLM调用失败: {str(e)[:50]}"

# ============ VectorBT 历史验证 ============
def validate_signal(close, signal_series, hold_days=5):
    """验证信号的历史胜率"""
    if signal_series.sum() < 2:
        return None
    
    exits = signal_series.shift(hold_days).fillna(False)
    
    try:
        pf = vbt.Portfolio.from_signals(
            close, signal_series, exits,
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
        
        # 计算持有期收益
        entry_dates = signal_series[signal_series].index
        period_returns = []
        for ed in entry_dates:
            try:
                idx = close.index.get_loc(ed)
                if idx + hold_days < len(close):
                    ret = (close.iloc[idx + hold_days] / close.iloc[idx]) - 1
                    period_returns.append(ret)
            except:
                continue
        
        avg_ret = np.mean(period_returns) * 100 if period_returns else 0
        win_rate_hold = np.mean([1 if r > 0 else 0 for r in period_returns]) if period_returns else 0
        
        return {
            'occurrences': int(signal_series.sum()),
            'trades': trades,
            'sharpe': sharpe,
            'win_rate': wr,
            'avg_hold_return': avg_ret,
            'win_rate_hold': win_rate_hold,
            'ret': s['Total Return [%]']
        }
    except:
        return None

# ============ Agent 1: Technical Analyst ============
def technical_analyst_agent(ind, price):
    """技术分析师：评估当前技术指标状态"""
    
    rsi = ind['rsi'].iloc[-1]
    adx = ind['adx'].iloc[-1]
    plus_di = ind['plus_di'].iloc[-1]
    minus_di = ind['minus_di'].iloc[-1]
    bb_pos = (price - ind['bb_lower'].iloc[-1]) / (ind['bb_upper'].iloc[-1] - ind['bb_lower'].iloc[-1] + 0.001) * 100
    macd_hist = ind['macd_hist'].iloc[-1]
    j_val = ind['j'].iloc[-1]
    
    signal = {}
    if rsi < 30: signal['RSI'] = '超卖'
    elif rsi > 70: signal['RSI'] = '超买'
    else: signal['RSI'] = '中性'
    
    if plus_di > minus_di: signal['DMI'] = '多头'
    else: signal['DMI'] = '空头'
    
    if adx > 25: signal['ADX'] = '强趋势'
    else: signal['ADX'] = '震荡'
    
    if macd_hist > 0: signal['MACD'] = '正向'
    else: signal['MACD'] = '负向'
    
    if bb_pos < 20: signal['BOLL'] = '超卖'
    elif bb_pos > 80: signal['BOLL'] = '超买'
    else: signal['BOLL'] = '中性'
    
    if j_val < 20: signal['KDJ'] = '超卖'
    elif j_val > 80: signal['KDJ'] = '超买'
    else: signal['KDJ'] = '中性'
    
    # 技术评分
    score = 0
    if rsi < 30: score += 1
    elif rsi > 70: score -= 1
    if plus_di > minus_di: score += 1
    else: score -= 1
    if macd_hist > 0: score += 1
    else: score -= 1
    if bb_pos < 20: score += 1
    elif bb_pos > 80: score -= 1
    
    technical_view = "看多" if score > 0 else ("看空" if score < 0 else "中性")
    
    return {
        'signals': signal,
        'score': score,
        'view': technical_view,
        'price': price,
        'atr': ind['atr'].iloc[-1],
        'trend': ind['market_state']
    }

# ============ Agent 2 & 3: Bull/Bear Researchers ============
def bull_researcher_agent(ind, price, df, tech_analysis):
    """多头研究员：找做多理由，用VectorBT验证"""
    close = df['close']
    reasons = []
    evidence = []
    
    # RSI超卖
    rsi = ind['rsi'].iloc[-1]
    if rsi < 40:
        reasons.append(f"RSI={rsi:.0f}，处于偏弱区域，可能反弹")
        signal = ind['rsi'] < 30
        v = validate_signal(close, signal, hold_days=5)
        if v:
            evidence.append(f"RSI超卖历史胜率{v['win_rate_hold']*100:.0f}%，平均收益{v['avg_hold_return']:+.1f}%")
    
    # BOLL下轨
    bb_pos = (price - ind['bb_lower'].iloc[-1]) / (ind['bb_upper'].iloc[-1] - ind['bb_lower'].iloc[-1] + 0.001) * 100
    if bb_pos < 30:
        reasons.append(f"价格位于布林带下轨附近({bb_pos:.0f}%)，均值回归概率大")
        signal = close < ind['bb_lower']
        v = validate_signal(close, signal, hold_days=5)
        if v:
            evidence.append(f"BOLL下轨买入历史胜率{v['win_rate_hold']*100:.0f}%，平均收益{v['avg_hold_return']:+.1f}%")
    
    # DMI空头减弱
    plus_di = ind['plus_di'].iloc[-1]
    minus_di = ind['minus_di'].iloc[-1]
    if plus_di > minus_di:
        reasons.append(f"DMI显示多头(+{plus_di:.1f} vs -{minus_di:.1f})")
        signal = plus_di > minus_di
        v = validate_signal(close, signal, hold_days=3)
        if v:
            evidence.append(f"DMI多头信号历史胜率{v['win_rate_hold']*100:.0f}%")
    
    # KDJ超卖
    j_val = ind['j'].iloc[-1]
    if j_val < 30:
        reasons.append(f"KDJ J值={j_val:.0f}，超卖区域")
        signal = ind['j'] < 20
        v = validate_signal(close, signal, hold_days=5)
        if v:
            evidence.append(f"KDJ超卖历史胜率{v['win_rate_hold']*100:.0f}%")
    
    # LLM分析
    prompt = f"""白银期货AG2606当前价格{price}，技术指标如下：
    - RSI: {rsi:.0f}
    - DMI: +{plus_di:.1f}/-{minus_di:.1f}  
    - BOLL位置: {bb_pos:.0f}%
    - KDJ J值: {j_val:.0f}
    - 市场趋势: {ind['market_state']}
    
    请用30字以内分析做多的理由。"""
    
    llm_analysis = llm_call(prompt, "你是一个专业的期货技术分析师，擅长发现做多机会")
    
    return {
        'reasons': reasons,
        'evidence': evidence,
        'llm_analysis': llm_analysis,
        'bullish_score': len(reasons)
    }

def bear_researcher_agent(ind, price, df, tech_analysis):
    """空头研究员：找做空理由，用VectorBT验证"""
    close = df['close']
    reasons = []
    evidence = []
    
    rsi = ind['rsi'].iloc[-1]
    if rsi > 60:
        reasons.append(f"RSI={rsi:.0f}，处于偏强区域，可能回调")
        signal = ind['rsi'] > 70
        v = validate_signal(close, signal, hold_days=5)
        if v:
            evidence.append(f"RSI超买历史胜率{v['win_rate_hold']*100:.0f}%，平均收益{v['avg_hold_return']:+.1f}%")
    
    bb_pos = (price - ind['bb_lower'].iloc[-1]) / (ind['bb_upper'].iloc[-1] - ind['bb_lower'].iloc[-1] + 0.001) * 100
    if bb_pos > 70:
        reasons.append(f"价格位于布林带上轨({bb_pos:.0f}%)，回落概率大")
    
    plus_di = ind['plus_di'].iloc[-1]
    minus_di = ind['minus_di'].iloc[-1]
    if plus_di < minus_di:
        reasons.append(f"DMI显示空头(+{plus_di:.1f} vs -{minus_di:.1f})")
        signal = plus_di < minus_di
        v = validate_signal(close, signal, hold_days=3)
        if v:
            evidence.append(f"DMI空头信号历史胜率{v['win_rate_hold']*100:.0f}%")
    
    adx = ind['adx'].iloc[-1]
    if adx > 25 and plus_di < minus_di:
        reasons.append(f"ADX={adx:.0f}强势趋势中，顺势做空")
    
    # 均线空头
    ma5 = ind['ma5'].iloc[-1]
    ma20 = ind['ma20'].iloc[-1]
    if ma5 < ma20:
        reasons.append(f"均线空头排列(MA5={ma5:.0f}<MA20={ma20:.0f})")
    
    prompt = f"""白银期货AG2606当前价格{price}，技术指标如下：
    - RSI: {rsi:.0f}
    - DMI: +{plus_di:.1f}/-{minus_di:.1f}
    - BOLL位置: {bb_pos:.0f}%
    - ADX: {adx:.0f}
    - MA5: {ma5:.0f}, MA20: {ma20:.0f}
    - 市场趋势: {ind['market_state']}
    
    请用30字以内分析做空的理由。"""
    
    llm_analysis = llm_call(prompt, "你是一个专业的期货技术分析师，擅长发现做空机会")
    
    return {
        'reasons': reasons,
        'evidence': evidence,
        'llm_analysis': llm_analysis,
        'bearish_score': len(reasons)
    }

# ============ Agent 4: Trader ============
def trader_agent(bull_research, bear_research, tech_analysis):
    """交易员：综合多空论点，做出决策"""
    
    bull_strength = len(bull_research['reasons'])
    bear_strength = len(bear_research['reasons'])
    
    # 基于证据的评分
    bull_score = bull_research.get('bullish_score', 0)
    bear_score = bear_research.get('bearish_score', 0)
    
    # LLM辩论
    prompt = f"""作为交易员，请判断以下情况应该做多还是做空：

多头理由：
{chr(10).join(bull_research['reasons'])}

空头理由：
{chr(10).join(bear_research['reasons'])}

技术面：{tech_analysis['view']}，评分{tech_analysis['score']}

请直接回答：做多/做空/观望，并说明理由（50字以内）。"""
    
    llm_decision = llm_call(prompt, "你是一个经验丰富的期货交易员，基于事实做决策")
    
    # 最终决策
    if bull_strength > bear_strength + 1 and bull_score > bear_score:
        decision = "BUY"
        confidence = min(0.9, 0.3 + bull_strength * 0.15)
    elif bear_strength > bull_strength + 1 and bear_score > bull_score:
        decision = "SELL"
        confidence = min(0.9, 0.3 + bear_strength * 0.15)
    elif bull_strength == bear_strength:
        decision = "HOLD"
        confidence = 0.3
    else:
        decision = "HOLD"
        confidence = 0.25
    
    return {
        'decision': decision,
        'confidence': confidence,
        'bull_strength': bull_strength,
        'bear_strength': bear_strength,
        'llm_decision': llm_decision,
        'reason': '多空辩论结果'
    }

# ============ Agent 5: Risk Manager ============
def risk_manager(trader_decision, tech_analysis, price):
    """风险经理：计算仓位和止损"""
    
    atr = tech_analysis['atr']
    
    if trader_decision['decision'] == 'BUY':
        stop_loss = price - 2 * atr
        take_profit = price + 3 * atr
        risk_reward = 1.5
    elif trader_decision['decision'] == 'SELL':
        stop_loss = price + 2 * atr
        take_profit = price - 3 * atr
        risk_reward = 1.5
    else:
        stop_loss = take_profit = 0
        risk_reward = 0
    
    # 凯利仓位
    conf = trader_decision['confidence']
    win_rate = 0.55  # 基于历史验证的平均胜率
    avg_win = 0.03
    avg_loss = 0.02
    wl = avg_win / avg_loss
    k = (win_rate * wl - (1 - win_rate)) / wl
    kelly = max(0.05, min(0.7, abs(k) * 0.5 * conf))
    
    # 波动率调整
    vol = tech_analysis.get('vol', 0.15)
    pos_mult = 0.5 if vol > 0.20 else (0.7 if vol > 0.10 else 1.0)
    position = min(kelly * pos_mult, 0.7)
    
    return {
        'stop_loss': stop_loss,
        'take_profit': take_profit,
        'risk_reward': risk_reward,
        'position': position,
        'atr': atr
    }

# ============ Agent 6: Portfolio Manager ============
def portfolio_manager(trader_decision, risk):
    """投资组合经理：最终审批"""
    
    # 审批逻辑
    if trader_decision['confidence'] < 0.35:
        final = "HOLD"
        reason = "置信度不足"
    elif risk['position'] < 0.1:
        final = "HOLD"  
        reason = "仓位过小"
    elif trader_decision['decision'] in ['BUY', 'SELL']:
        final = trader_decision['decision']
        reason = f"批准{trader_decision['reason']}"
    else:
        final = "HOLD"
        reason = trader_decision.get('reason', '多空均衡')
    
    return {
        'final_decision': final,
        'position': risk['position'] if final != 'HOLD' else 0,
        'stop_loss': risk['stop_loss'] if final != 'HOLD' else 0,
        'take_profit': risk['take_profit'] if final != 'HOLD' else 0,
        'reason': reason,
        'atr': risk['atr']
    }

# ============ 主流程 ============
def run():
    print("=" * 70)
    print("  股神2号 v6.0 | TradingAgents + VectorBT 混合系统")
    print("  多智能体协作：Technical → Bull/Bear → Trader → Risk → PM")
    print("=" * 70)
    
    print("\n📥 获取数据...")
    df = get_data(500)
    price = get_rt() or df['close'].iloc[-1]
    ind = calc_indicators(df)
    
    market_state = ind['market_state']
    state_map = {'up': 'UP', 'down': 'DOWN', 'range': 'RANGE'}
    print(f"   AG2606 | {len(df)}条 | 价格: {price:.0f} | 市场: [{state_map[market_state]}]")
    
    print("\n" + "=" * 70)
    print("【Agent 1: 技术分析师】")
    print("-" * 70)
    
    tech = technical_analyst_agent(ind, price)
    print(f"  技术信号: {tech['signals']}")
    print(f"  技术评分: {tech['score']} → {tech['view']}")
    
    print("\n【Agent 2 & 3: 多空研究员辩论】")
    print("-" * 70)
    
    bull = bull_researcher_agent(ind, price, df, tech)
    bear = bear_researcher_agent(ind, price, df, tech)
    
    print(f"  🟢 多头理由 ({len(bull['reasons'])}个):")
    for r in bull['reasons'][:3]:
        print(f"     • {r}")
    for e in bull['evidence'][:2]:
        print(f"     📊 {e}")
    print(f"     LLM: {bull['llm_analysis'][:50]}...")
    
    print(f"\n  🔴 空头理由 ({len(bear['reasons'])}个):")
    for r in bear['reasons'][:3]:
        print(f"     • {r}")
    for e in bear['evidence'][:2]:
        print(f"     📊 {e}")
    print(f"     LLM: {bear['llm_analysis'][:50]}...")
    
    print("\n【Agent 4: 交易员决策】")
    print("-" * 70)
    
    trader = trader_agent(bull, bear, tech)
    icon = {'BUY': '🟢买入', 'SELL': '🔴卖出', 'HOLD': '⏸️观望'}
    print(f"  多头强度: {trader['bull_strength']} vs 空头强度: {trader['bear_strength']}")
    print(f"  交易员决策: {icon[trader['decision']]} (置信度{trader['confidence']:.0%})")
    print(f"  LLM建议: {trader['llm_decision'][:80]}")
    
    print("\n【Agent 5 & 6: 风控 + 投资组合经理】")
    print("-" * 70)
    
    risk = risk_manager(trader, tech, price)
    pm = portfolio_manager(trader, risk)
    
    icon_pm = {'BUY': '🟢买入', 'SELL': '🔴卖出', 'HOLD': '⏸️观望'}
    print(f"  最终决策: {icon_pm[pm['final_decision']]}")
    print(f"  决策理由: {pm['reason']}")
    
    if pm['final_decision'] != 'HOLD':
        print(f"  建议仓位: {pm['position']*100:.0f}%")
        print(f"  止损: {pm['stop_loss']:.0f} | 止盈: {pm['take_profit']:.0f}")
        print(f"  盈亏比: 1:{risk['risk_reward']:.1f}")
    else:
        print(f"  建议仓位: 0% (观望)")
    
    print(f"\n  ATR: {risk['atr']:.0f} | 关键价位: {ind['bb_lower'].iloc[-1]:.0f} / {price:.0f} / {ind['bb_upper'].iloc[-1]:.0f}")
    
    print("\n" + "=" * 70)
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

if __name__ == '__main__':
    run()
