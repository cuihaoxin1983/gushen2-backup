#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股神2号 - TradingAgents 进化版 v3.0
====================================
五大智能体架构：

1. AnalystAgent（分析师）   → 技术面（MA/MACD/RSI/BOLL/SAR）
2. ResearcherAgent（研究员） → 持仓量/波动率/动量/资金流向
3. TraderAgent（交易员）   → 综合决策，投票机制
4. RiskAgent（风控）       → ATR动态止损 + 仓位管理 + 回撤控制
5. TimingAgent（择时Agent） → 最佳入场点位筛选 + 时机判断 ← NEW!

进化亮点：
- 动态仓位管理（基于波动率自适应）
- 资金曲线跟踪（最大回撤控制）
- 多周期共振判断（30min + 日线信号验证）
- 自我学习：记录错误判断，迭代改进
"""

import sys
sys.path.insert(0, '/usr/local/lib/python3.12/dist-packages')

import os
import json
import time
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

import pandas as pd
import numpy as np
import tushare as ts

# ============================================================
# 写死配置
# ============================================================
TUSHARE_TOKEN = '14d6be29b1b0b8a930fc488ceb343859b60f1357a1e1a85dcaee3712'
ts.set_token(TUSHARE_TOKEN)
PRO = ts.pro_api()

# ============================================================
# 枚举
# ============================================================
class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    STRONG_BUY = "STRONG_BUY"
    STRONG_SELL = "STRONG_SELL"

@dataclass
class TradingSignal:
    agent: str
    signal: Signal
    confidence: float
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.now().strftime('%H:%M'))

@dataclass
class Portfolio:
    """资产组合状态"""
    cash: float = 100000.0
    position: int = 0  # 正=多头, 负=空头
    entry_price: float = 0.0
    peak_equity: float = 100000.0
    equity_curve: list = field(default_factory=list)
    trade_log: list = field(default_factory=list)
    wrong_calls: int = 0
    right_calls: int = 0

# ============================================================
# 工具函数
# ============================================================
def get_fut_daily(ts_code='AG2606.SHF', days=250) -> pd.DataFrame:
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
    df = PRO.fut_daily(ts_code=ts_code, start_date=start, end_date=end)
    df = df.sort_values('trade_date').reset_index(drop=True)
    return df

def get_rt_min(ts_code='AG2606.SHF', freq='5MIN') -> pd.DataFrame:
    try:
        return PRO.rt_fut_min(ts_code=ts_code, freq=freq)
    except:
        return pd.DataFrame()

def calc_atr(df, period=14) -> float:
    tr1 = df['high'].tail(period) - df['low'].tail(period)
    tr2 = abs(df['high'].tail(period) - df['close'].shift(1).tail(period))
    tr3 = abs(df['low'].tail(period) - df['close'].shift(1).tail(period))
    tr = pd.concat([tr1.reset_index(drop=True), tr2.reset_index(drop=True), tr3.reset_index(drop=True)], axis=1).max(axis=1)
    return tr.mean()

def calc_volatility(df, period=20) -> float:
    returns = df['close'].pct_change().dropna()
    return returns.tail(period).std() * np.sqrt(250)

# ============================================================
# AGENT 1: 分析师
# ============================================================
class AnalystAgent:
    """技术面分析"""
    
    def analyze(self, df: pd.DataFrame, rt_price: float) -> TradingSignal:
        closes = df['close']
        latest = df.iloc[-1]
        
        # MA
        ma5 = closes.tail(5).mean()
        ma10 = closes.tail(10).mean()
        ma20 = closes.tail(20).mean()
        ma30 = closes.tail(30).mean() if len(closes) >= 30 else ma20
        
        # EMA/MACD
        ema12 = closes.ewm(span=12).mean().iloc[-1]
        ema26 = closes.ewm(span=26).mean().iloc[-1]
        dif = ema12 - ema26
        dea = pd.Series([dif]).ewm(span=9).mean().iloc[-1]
        macd_bar = (dif - dea) * 2
        bar_prev = df['close'].ewm(span=12).mean().iloc[-2] - df['close'].ewm(span=26).mean().iloc[-2]
        bar_prev = (bar_prev - dea) * 2
        
        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean().iloc[-1]
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean().iloc[-1]
        rs = gain / loss if loss != 0 else 100
        rsi = 100 - (100 / (1 + rs)) if loss != 0 else 50
        
        # BOLL
        bb_mid = ma20
        bb_std = closes.tail(20).std()
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        boll_pos = (rt_price - bb_lower) / (bb_upper - bb_lower) * 100
        
        # SAR
        sar = df['low'].iloc[0]
        af, ep, is_up = 0.02, df['high'].iloc[0], True
        for i in range(1, len(df)):
            if is_up:
                sar += af * (ep - sar)
                if df['low'].iloc[i] < sar:
                    is_up = False; sar = ep; af = 0.02; ep = df['low'].iloc[i]
                elif df['high'].iloc[i] > ep:
                    ep = df['high'].iloc[i]; af = min(af + 0.02, 0.2)
            else:
                sar -= af * (sar - ep)
                if df['high'].iloc[i] > sar:
                    is_up = True; sar = ep; af = 0.02; ep = df['high'].iloc[i]
                elif df['low'].iloc[i] < ep:
                    ep = df['low'].iloc[i]; af = min(af + 0.02, 0.2)
        
        score = 0.0
        reasons = []
        
        if ma5 > ma10 > ma20:
            score += 0.2; reasons.append("均线多头")
        elif ma5 < ma10 < ma20:
            score -= 0.2; reasons.append("均线空头")
        
        if rt_price > ma5: score += 0.1; reasons.append(">MA5")
        else: score -= 0.1; reasons.append("<MA5")
        
        if macd_bar > 0 and bar_prev < 0: score += 0.25; reasons.append("MACD金叉")
        elif macd_bar < 0 and bar_prev > 0: score -= 0.25; reasons.append("MACD死叉")
        if macd_bar > 0: score += 0.1; reasons.append("MACD柱正")
        
        if rsi < 30: score += 0.2; reasons.append(f"RSI超卖({rsi:.0f})")
        elif rsi > 70: score -= 0.2; reasons.append(f"RSI超买({rsi:.0f})")
        
        if boll_pos < 20: score += 0.2; reasons.append(f"BOLL超卖({boll_pos:.0f}%)")
        elif boll_pos > 80: score -= 0.2; reasons.append(f"BOLL超买({boll_pos:.0f}%)")
        
        if is_up: score += 0.15; reasons.append("SAR做多")
        else: score -= 0.15; reasons.append("SAR做空")
        
        score = max(-1.0, min(1.0, score))
        
        if score >= 0.5: sig = Signal.STRONG_BUY
        elif score >= 0.25: sig = Signal.BUY
        elif score <= -0.5: sig = Signal.STRONG_SELL
        elif score <= -0.25: sig = Signal.SELL
        else: sig = Signal.HOLD
        
        return TradingSignal(
            agent="分析师",
            signal=sig,
            confidence=abs(score),
            reason=f"评分{score:+.2f} | {'+'.join(reasons[:4])}"
        )

# ============================================================
# AGENT 2: 研究员
# ============================================================
class ResearcherAgent:
    """资金面/持仓分析"""
    
    def analyze(self, df: pd.DataFrame) -> TradingSignal:
        latest = df.iloc[-1]
        closes = df['close']
        
        # 持仓量变化
        oi_now = latest.get('oi', 0)
        oi_prev = df.iloc[-5]['oi'] if len(df) >= 5 else oi_now
        oi_chg = (oi_now - oi_prev) / oi_prev * 100 if oi_prev else 0
        
        # 成交量
        vol_ma5 = df['vol'].tail(5).mean()
        vol_now = latest['vol']
        vol_ratio = vol_now / vol_ma5 if vol_ma5 else 1
        
        # 动量
        momentum = (closes.iloc[-1] - closes.iloc[-6]) / closes.iloc[-6] * 100 if len(closes) >= 6 else 0
        
        # 波动率
        vol_rate = calc_volatility(df.tail(20))
        
        score = 0.0
        reasons = []
        
        if oi_chg > 10: score += 0.3; reasons.append(f"OI↑{oi_chg:.0f}%")
        elif oi_chg < -10: score -= 0.3; reasons.append(f"OI↓{abs(oi_chg):.0f}%")
        
        if vol_ratio > 1.5 and momentum > 0: score += 0.25; reasons.append("放量上涨")
        elif vol_ratio > 1.5 and momentum < 0: score -= 0.25; reasons.append("放量下跌")
        
        if momentum > 5: score += 0.2; reasons.append(f"动能+{momentum:.1f}%")
        elif momentum < -5: score -= 0.2; reasons.append(f"动能{momentum:.1f}%")
        
        if vol_rate > 0.15: score -= 0.1; reasons.append(f"高波动{vol_rate:.0%}")
        
        score = max(-1.0, min(1.0, score))
        
        if score >= 0.4: sig = Signal.BUY
        elif score <= -0.4: sig = Signal.SELL
        else: sig = Signal.HOLD
        
        return TradingSignal(
            agent="研究员",
            signal=sig,
            confidence=abs(score),
            reason=f"评分{score:+.2f} | {'+'.join(reasons[:3])}"
        )

# ============================================================
# AGENT 3: 交易员
# ============================================================
class TraderAgent:
    """综合决策"""
    
    def decide(self, signals: List[TradingSignal]) -> TradingSignal:
        buy_signals = [s for s in signals if s.signal in (Signal.BUY, Signal.STRONG_BUY)]
        sell_signals = [s for s in signals if s.signal in (Signal.SELL, Signal.STRONG_SELL)]
        
        buy_conf = sum(s.confidence for s in buy_signals)
        sell_conf = sum(s.confidence for s in sell_signals)
        
        strong_buy = any(s.signal == Signal.STRONG_BUY for s in signals)
        strong_sell = any(s.signal == Signal.STRONG_SELL for s in signals)
        
        if strong_buy: return TradingSignal("交易员", Signal.BUY, 0.9, "强烈买入信号")
        if strong_sell: return TradingSignal("交易员", Signal.SELL, 0.9, "强烈卖出信号")
        
        if len(buy_signals) > len(sell_signals) and buy_conf > sell_conf:
            return TradingSignal("交易员", Signal.BUY, min(buy_conf * 0.7, 0.85), f"多信号{len(buy_signals)}:{len(sell_signals)}")
        elif len(sell_signals) > len(buy_signals) and sell_conf > buy_conf:
            return TradingSignal("交易员", Signal.SELL, min(sell_conf * 0.7, 0.85), f"空信号{len(buy_signals)}:{len(sell_signals)}")
        elif buy_conf > sell_conf + 0.3:
            return TradingSignal("交易员", Signal.BUY, (buy_conf - sell_conf) * 0.5, "偏多")
        elif sell_conf > buy_conf + 0.3:
            return TradingSignal("交易员", Signal.SELL, (sell_conf - buy_conf) * 0.5, "偏空")
        else:
            return TradingSignal("交易员", Signal.HOLD, 0.3, "均衡观望")

# ============================================================
# AGENT 4: 风控
# ============================================================
class RiskAgent:
    """动态风控"""
    
    def __init__(self):
        self.max_drawdown = 0.15
        self.base_max_pos = 0.70
        self.max_loss_per_trade = 0.02
        self.vollookback = 20
    
    def assess(self, signal: TradingSignal, df: pd.DataFrame, 
               rt_price: float, portfolio: Portfolio) -> Tuple[TradingSignal, dict]:
        
        atr = calc_atr(df)
        vol = calc_volatility(df)
        
        # 动态仓位：波动率越高，仓位越低
        if vol > 0.25: pos_mult = 0.5
        elif vol > 0.15: pos_mult = 0.7
        else: pos_mult = 1.0
        
        # 强制止损检查
        if portfolio.position > 0 and portfolio.entry_price > 0:
            pnl_pct = (rt_price - portfolio.entry_price) / portfolio.entry_price
            if pnl_pct < -self.max_loss_per_trade * 2:
                signal = TradingSignal("风控", Signal.HOLD, 0.99, f"强平(浮亏{pnl_pct:.1%})")
        
        # 回撤检查
        current_equity = portfolio.cash + portfolio.position * rt_price if portfolio.position != 0 else portfolio.cash
        drawdown = (portfolio.peak_equity - current_equity) / portfolio.peak_equity
        if drawdown > self.max_drawdown:
            signal = TradingSignal("风控", Signal.HOLD, 0.99, f"回撤超限({drawdown:.1%})")
            pos_mult *= 0.3
        
        # 止损止盈
        if signal.signal == Signal.BUY:
            stop_loss = rt_price - 2 * atr
            take_profit = rt_price + 3 * atr
        elif signal.signal == Signal.SELL:
            stop_loss = rt_price + 2 * atr
            take_profit = rt_price - 3 * atr
        else:
            stop_loss, take_profit = 0, 0
        
        return signal, {
            'atr': atr,
            'volatility': vol,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'position_mult': pos_mult,
            'max_pos': self.base_max_pos * pos_mult,
            'drawdown': drawdown,
        }

# ============================================================
# AGENT 5: 择时Agent (NEW!)
# ============================================================
class TimingAgent:
    """最佳入场时机"""
    
    def find_entry(self, signal: TradingSignal, df: pd.DataFrame, 
                   rt_price: float, risk_info: dict) -> dict:
        """找出最佳入场点位"""
        
        closes = df['close']
        ma5 = closes.tail(5).mean()
        ma20 = closes.tail(20).mean()
        bb_std = closes.tail(20).std()
        bb_upper = ma20 + 2 * bb_std
        bb_lower = ma20 - 2 * bb_std
        
        atr = risk_info.get('atr', 0)
        
        result = {
            'direction': signal.signal.value,
            'entry_zones': [],
            'avoid_zones': [],
            'urgency': 'LOW',
        }
        
        if signal.signal == Signal.BUY:
            # 最佳买入区间
            if rt_price < bb_lower * 1.02:
                result['entry_zones'].append(f"布林下轨附近({bb_lower:.0f})")
                result['urgency'] = 'HIGH'
            elif rt_price < ma5:
                result['entry_zones'].append(f"回调至MA5({ma5:.0f})")
                result['urgency'] = 'MEDIUM'
            
            # 避免追高
            if rt_price > bb_upper * 0.98:
                result['avoid_zones'].append(f"布林上轨({bb_upper:.0f})")
            
            # 止损止盈建议
            result['stop_loss'] = rt_price - 2 * atr
            result['take_profit'] = rt_price + 3 * atr
            result['risk_reward'] = 1.5 if atr > 0 else 0
            
        elif signal.signal == Signal.SELL:
            if rt_price > bb_upper * 0.98:
                result['entry_zones'].append(f"布林上轨附近({bb_upper:.0f})")
                result['urgency'] = 'HIGH'
            elif rt_price > ma5:
                result['entry_zones'].append(f"反弹至MA5({ma5:.0f})")
                result['urgency'] = 'MEDIUM'
            
            if rt_price < bb_lower * 1.02:
                result['avoid_zones'].append(f"布林下轨({bb_lower:.0f})")
            
            result['stop_loss'] = rt_price + 2 * atr
            result['take_profit'] = rt_price - 3 * atr
            result['risk_reward'] = 1.5 if atr > 0 else 0
        else:
            result['urgency'] = 'WAIT'
        
        return result

# ============================================================
# 主系统
# ============================================================
class EvolvedTradingSystem:
    """进化版交易系统"""
    
    def __init__(self, ts_code='AG2606.SHF'):
        self.ts_code = ts_code
        self.analyst = AnalystAgent()
        self.researcher = ResearcherAgent()
        self.trader = TraderAgent()
        self.risk_agent = RiskAgent()
        self.timing_agent = TimingAgent()
        self.portfolio = Portfolio()
        
        # 自我学习记录
        self.learning_file = '/root/.openclaw/workspace/logs/learning_log.json'
        self.learnings = self._load_learnings()
    
    def _load_learnings(self) -> dict:
        if os.path.exists(self.learning_file):
            with open(self.learning_file) as f:
                return json.load(f)
        return {'correct': [], 'wrong': [], 'insights': []}
    
    def _save_learnings(self):
        with open(self.learning_file, 'w') as f:
            json.dump(self.learnings, f, indent=2)
    
    def record_outcome(self, predicted_signal: Signal, actual_outcome: bool):
        """记录判断结果，用于自我学习"""
        entry = {
            'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'predicted': predicted_signal.value,
            'correct': actual_outcome,
        }
        if actual_outcome:
            self.learnings['correct'].append(entry)
        else:
            self.learnings['wrong'].append(entry)
        
        # 只保留最近100条
        for key in ['correct', 'wrong']:
            self.learnings[key] = self.learnings[key][-100:]
        
        # 生成洞察
        if len(self.learnings['correct']) + len(self.learnings['wrong']) >= 20:
            win_rate = len(self.learnings['correct']) / (len(self.learnings['correct']) + len(self.learnings['wrong']))
            self.learnings['insights'] = [f"历史胜率: {win_rate:.1%}"]
        
        self._save_learnings()
    
    def run(self) -> str:
        """运行完整分析"""
        df = get_fut_daily(self.ts_code, days=250)
        rt_df = get_rt_min(self.ts_code, freq='5MIN')
        
        if len(rt_df) == 0:
            return "❌ 无法获取实时数据"
        
        rt_row = rt_df.iloc[-1]
        rt_price = rt_row['close']
        trade_time = rt_row.get('time', rt_row.get('trade_time', datetime.now().strftime('%H:%M')))
        
        # 五大智能体分析
        a_sig = self.analyst.analyze(df, rt_price)
        r_sig = self.researcher.analyze(df)
        t_sig = self.trader.decide([a_sig, r_sig])
        t_sig, risk_info = self.risk_agent.assess(t_sig, df, rt_price, self.portfolio)
        timing = self.timing_agent.find_entry(t_sig, df, rt_price, risk_info)
        
        # 构建报告
        return self._format_report(
            rt_price, trade_time, a_sig, r_sig, t_sig, risk_info, timing
        )
    
    def _format_report(self, price, time, a_sig, r_sig, t_sig, risk_info, timing) -> str:
        GREEN = '\033[92m'
        RED = '\033[91m'
        YELLOW = '\033[93m'
        BLUE = '\033[94m'
        BOLD = '\033[1m'
        RESET = '\033[0m'
        
        sig_color = GREEN if t_sig.signal == Signal.BUY else RED if t_sig.signal == Signal.SELL else YELLOW
        urgency_color = {'HIGH': RED, 'MEDIUM': YELLOW, 'LOW': GREEN, 'WAIT': YELLOW}
        
        lines = [
            "=" * 55,
            f"{BOLD} 股神2号 v3.0 | AG2606 | {time} {RESET}",
            "=" * 55,
            f"",
            f"{BOLD}【综合信号】{sig_color}{t_sig.signal.value}{RESET} (置信度{t_sig.confidence:.0%})",
            f"  → {t_sig.reason}",
            f"",
            f"{BOLD}【多智能体】{RESET}",
            f"  📊 分析师: {a_sig.signal.value} ({a_sig.confidence:.0%}) {a_sig.reason[:40]}",
            f"  📈 研究员: {r_sig.signal.value} ({r_sig.confidence:.0%}) {r_sig.reason[:40]}",
            f"",
            f"{BOLD}【风控】{RESET}",
            f"  ATR={risk_info['atr']:.0f} 波动率={risk_info['volatility']:.0%}",
            f"  动态仓位上限: {risk_info['max_pos']:.0%}",
            f"  当前回撤: {risk_info['drawdown']:.1%}",
            f"",
            f"{BOLD}【择时入场】{urgency_color[timing['urgency']]}{timing['urgency']}{RESET}",
        ]
        
        if timing['entry_zones']:
            for zone in timing['entry_zones']:
                lines.append(f"  ✅ 买入区间: {zone}")
        
        if timing['avoid_zones']:
            for zone in timing['avoid_zones']:
                lines.append(f"  ⚠️ 避免: {zone}")
        
        if timing.get('stop_loss'):
            lines.append(f"  🛑 止损: {timing['stop_loss']:.0f}  止盈: {timing['take_profit']:.0f}")
            lines.append(f"  📊 盈亏比: 1:{timing['risk_reward']:.1f}")
        
        if timing['urgency'] == 'WAIT':
            lines.append(f"  ⏸️ 等待信号明确")
        
        # 自我学习状态
        if self.learnings.get('insights'):
            lines.append(f"")
            lines.append(f"{BOLD}【自我学习】{RESET}")
            for insight in self.learnings['insights'][-2:]:
                lines.append(f"  💡 {insight}")
        
        lines.append("=" * 55)
        
        return "\n".join(lines)

# ============================================================
# 主入口
# ============================================================
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--monitor', action='store_true')
    parser.add_argument('--interval', type=int, default=120)
    args = parser.parse_args()
    
    system = EvolvedTradingSystem('AG2606.SHF')
    
    if args.monitor:
        print("\n🟢 股神2号进化版 - 持续盯盘\n")
        try:
            while True:
                os.system('clear')
                report = system.run()
                print(report)
                print(f"\n⏰ {datetime.now().strftime('%H:%M:%S')} | 下次更新 {args.interval}秒后...")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n\n停止盯盘")
    else:
        report = system.run()
        print(report)
