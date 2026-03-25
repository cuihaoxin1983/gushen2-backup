#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股神2号 - TradingAgents 投资顾问系统 v2.0
==============================================
基于 TradingAgents 框架的多智能体量化交易系统

架构：
  AnalystAgent（分析师）   → 技术面分析（MA/MACD/RSI/布林带/K线形态）
  ResearcherAgent（研究员） → 产业/持仓量/波动率/动量分析
  TraderAgent（交易员）   → 综合多智能体信号，决策多/空/观望
  RiskAgent（风控）       → ATR止损/仓位管理/回撤控制

数据源：Tushare Pro (写死)
Token: 14d6be29b1b0b8a930fc488ceb343859b60f1357a1e1a85dcaee3712

运行方式：
  python3 trading_advisor.py          # 一次性投资建议
  python3 trading_advisor.py --monitor # 持续盯盘模式
"""

import sys
sys.path.insert(0, '/usr/local/lib/python3.12/dist-packages')

import os
import json
import time
import signal
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd
import numpy as np
import tushare as ts

# ============================================================
# 写死配置 - 不允许修改
# ============================================================
TUSHARE_TOKEN = '14d6be29b1b0b8a930fc488ceb343859b60f1357a1e1a85dcaee3712'
ts.set_token(TUSHARE_TOKEN)
PRO = ts.pro_api()

# ============================================================
# 工具函数
# ============================================================
def get_fut_daily(ts_code: str, days: int = 250) -> pd.DataFrame:
    """获取期货日线历史数据"""
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
    df = PRO.fut_daily(ts_code=ts_code, start_date=start, end_date=end)
    df = df.sort_values('trade_date').reset_index(drop=True)
    return df

def get_rt_min(ts_code: str, freq: str = '5MIN') -> pd.DataFrame:
    """获取实时分钟数据"""
    try:
        return PRO.rt_fut_min(ts_code=ts_code, freq=freq)
    except:
        return pd.DataFrame()

def calc_ma(series: pd.Series, period: int) -> Optional[float]:
    if len(series) < period:
        return None
    return series.tail(period).mean()

def calc_atr(df: pd.DataFrame, period: int = 14) -> float:
    """计算ATR"""
    high = df['high'].tail(period)
    low = df['low'].tail(period)
    close_prev = df['close'].shift(1).tail(period)
    
    tr1 = high - low
    tr2 = abs(high - close_prev)
    tr3 = abs(low - close_prev)
    
    tr = pd.concat([tr1.reset_index(drop=True), 
                    tr2.reset_index(drop=True), 
                    tr3.reset_index(drop=True)], axis=1).max(axis=1)
    return tr.mean()

# ============================================================
# 信号枚举
# ============================================================
class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    CLOSE_LONG = "CLOSE_LONG"
    CLOSE_SHORT = "CLOSE_SHORT"
    STRONG_BUY = "STRONG_BUY"
    STRONG_SELL = "STRONG_SELL"

# ============================================================
# 数据结构
# ============================================================
@dataclass
class TradingSignal:
    agent: str
    signal: Signal
    confidence: float  # 0.0 ~ 1.0
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.now().strftime('%H:%M:%S'))

# ============================================================
# ANALYST AGENT - 分析师（技术面）
# ============================================================
class AnalystAgent:
    """技术面分析：MA趋势 / MACD / RSI / 布林带 / K线形态"""
    
    name = "分析师"
    
    def analyze(self, df: pd.DataFrame, rt_row: dict = None) -> TradingSignal:
        df = df.tail(60).copy()
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        closes = df['close']
        
        # ---- MA ----
        ma5 = calc_ma(closes, 5)
        ma10 = calc_ma(closes, 10)
        ma20 = calc_ma(closes, 20)
        ma60 = calc_ma(closes, 60) if len(closes) >= 60 else None
        
        # ---- EMA平滑 ----
        ema12 = closes.ewm(span=12).mean().iloc[-1]
        ema26 = closes.ewm(span=26).mean().iloc[-1]
        macd = ema12 - ema26
        signal_line = pd.Series([macd]).ewm(span=9).mean().iloc[-1]
        histogram = macd - signal_line
        hist_prev = df['close'].ewm(span=12).mean().iloc[-2] - df['close'].ewm(span=26).mean().iloc[-2] - signal_line
        
        # ---- RSI ----
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean().iloc[-1]
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean().iloc[-1]
        rs = gain / loss if loss != 0 else 100
        rsi = 100 - (100 / (1 + rs)) if loss != 0 else 50
        
        # ---- 布林带 ----
        bb_mid = calc_ma(closes, 20)
        bb_std = closes.tail(20).std()
        bb_upper = bb_mid + 2 * bb_std if bb_mid else None
        bb_lower = bb_mid - 2 * bb_std if bb_mid else None
        
        # ---- 当前价格 ----
        price = rt_row['close'] if rt_row else latest['close']
        
        # ---- 趋势打分 ----
        score = 0.0
        reasons = []
        
        # 均线
        if ma5 and ma10 and ma20:
            if ma5 > ma10 > ma20:
                score += 0.2
                reasons.append("均线多头")
            elif ma5 < ma10 < ma20:
                score -= 0.2
                reasons.append("均线空头")
        
        if ma5 and price > ma5:
            score += 0.1
            reasons.append("价格>MA5")
        elif ma5 and price < ma5:
            score -= 0.1
            reasons.append("价格<MA5")
        
        # MACD
        if histogram > 0 and hist_prev < 0:
            score += 0.25
            reasons.append("MACD金叉")
        elif histogram < 0 and hist_prev > 0:
            score -= 0.25
            reasons.append("MACD死叉")
        
        if histogram > 0:
            score += 0.1
            reasons.append("MACD柱正值")
        else:
            score -= 0.1
            reasons.append("MACD柱负值")
        
        # RSI
        if rsi < 30:
            score += 0.2
            reasons.append(f"RSI超卖({rsi:.0f})")
        elif rsi > 70:
            score -= 0.2
            reasons.append(f"RSI超买({rsi:.0f})")
        
        # 布林带
        if bb_upper and price > bb_upper:
            score -= 0.15
            reasons.append("突破布林上轨")
        elif bb_lower and price < bb_lower:
            score += 0.15
            reasons.append("跌破布林下轨")
        
        score = max(-1.0, min(1.0, score))
        
        if score >= 0.6:
            sig = Signal.STRONG_BUY
        elif score >= 0.3:
            sig = Signal.BUY
        elif score <= -0.6:
            sig = Signal.STRONG_SELL
        elif score <= -0.3:
            sig = Signal.SELL
        else:
            sig = Signal.HOLD
        
        reason = f"评分{score:+.2f} | {' + '.join(reasons[:4]) if reasons else '无明显信号'}"
        
        return TradingSignal(agent=self.name, signal=sig, confidence=abs(score), reason=reason)

# ============================================================
# RESEARCHER AGENT - 研究员（基本面/资金）
# ============================================================
class ResearcherAgent:
    """持仓量 / 动量 / 波动率 / 成交量分析"""
    
    name = "研究员"
    
    def analyze(self, df: pd.DataFrame) -> TradingSignal:
        df = df.tail(20).copy()
        latest = df.iloc[-1]
        closes = df['close']
        
        # 持仓量变化
        oi_now = latest.get('oi', 0)
        oi_prev = df.iloc[-5]['oi'] if len(df) >= 5 else oi_now
        oi_chg = (oi_now - oi_prev) / oi_prev * 100 if oi_prev else 0
        
        # 成交量异常
        vol_ma5 = df['vol'].tail(5).mean()
        vol_now = latest['vol']
        vol_ratio = vol_now / vol_ma5 if vol_ma5 else 1
        
        # 价格动量
        momentum_5d = (closes.iloc[-1] - closes.iloc[-6]) / closes.iloc[-6] * 100 if len(closes) >= 6 else 0
        
        # 波动率
        returns = df['close'].pct_change().dropna()
        vol_rate = returns.std() * np.sqrt(20) if len(returns) >= 2 else 0
        
        score = 0.0
        reasons = []
        
        # 持仓量
        if oi_chg > 10:
            score += 0.3
            reasons.append(f"持仓量↑{oi_chg:.1f}%")
        elif oi_chg < -10:
            score -= 0.3
            reasons.append(f"持仓量↓{abs(oi_chg):.1f}%")
        
        # 放量
        if vol_ratio > 1.5 and momentum_5d > 0:
            score += 0.25
            reasons.append("放量上涨")
        elif vol_ratio > 1.5 and momentum_5d < 0:
            score -= 0.25
            reasons.append("放量下跌")
        
        # 动量
        if momentum_5d > 5:
            score += 0.2
            reasons.append(f"5日动能+{momentum_5d:.1f}%")
        elif momentum_5d < -5:
            score -= 0.2
            reasons.append(f"5日动能{momentum_5d:.1f}%")
        
        # 波动率
        if vol_rate > 0.15:
            score -= 0.1
            reasons.append(f"高波动{vol_rate:.0%}")
        
        score = max(-1.0, min(1.0, score))
        
        if score >= 0.5:
            sig = Signal.BUY
        elif score <= -0.5:
            sig = Signal.SELL
        else:
            sig = Signal.HOLD
        
        reason = f"评分{score:+.2f} | {' + '.join(reasons[:3]) if reasons else '无明显信号'}"
        
        return TradingSignal(agent=self.name, signal=sig, confidence=abs(score), reason=reason)

# ============================================================
# TRADER AGENT - 交易员（综合决策）
# ============================================================
class TraderAgent:
    """汇总所有信号，投票决策"""
    
    name = "交易员"
    
    def decide(self, signals: List[TradingSignal]) -> TradingSignal:
        buy_votes = [s for s in signals if s.signal in (Signal.BUY, Signal.STRONG_BUY)]
        sell_votes = [s for s in signals if s.signal in (Signal.SELL, Signal.STRONG_SELL)]
        
        buy_conf = sum(s.confidence for s in buy_votes)
        sell_conf = sum(s.confidence for s in sell_votes)
        
        # 强烈信号优先
        strong_buy = any(s.signal == Signal.STRONG_BUY for s in signals)
        strong_sell = any(s.signal == Signal.STRONG_SELL for s in signals)
        
        if strong_buy:
            final_sig = Signal.BUY
            conf = 0.9
            reason = "分析师强烈做多信号"
        elif strong_sell:
            final_sig = Signal.SELL
            conf = 0.9
            reason = "分析师强烈做空信号"
        elif len(buy_votes) > len(sell_votes) and buy_conf > sell_conf:
            final_sig = Signal.BUY
            conf = min(buy_conf / max(len(buy_votes), 1) * 0.8, 0.85)
            reason = f"多空投票{len(buy_votes)}:{len(sell_votes)}"
        elif len(sell_votes) > len(buy_votes) and sell_conf > buy_conf:
            final_sig = Signal.SELL
            conf = min(sell_conf / max(len(sell_votes), 1) * 0.8, 0.85)
            reason = f"多空投票{len(buy_votes)}:{len(sell_votes)}"
        elif buy_conf > sell_conf + 0.2:
            final_sig = Signal.BUY
            conf = (buy_conf - sell_conf) * 0.6
            reason = "偏多信号"
        elif sell_conf > buy_conf + 0.2:
            final_sig = Signal.SELL
            conf = (sell_conf - buy_conf) * 0.6
            reason = "偏空信号"
        else:
            final_sig = Signal.HOLD
            conf = 0.3
            reason = "多空均衡，观望"
        
        return TradingSignal(agent=self.name, signal=final_sig, confidence=conf, reason=reason)

# ============================================================
# RISK AGENT - 风控
# ============================================================
class RiskAgent:
    """ATR止损 / 仓位计算 / 回撤控制"""
    
    name = "风控"
    
    def __init__(self):
        self.max_loss_pct = 0.02    # 单笔最大亏损2%
        self.max_position = 0.70     # 最大仓位70%
        self.atr_multiplier = 2.0   # ATR止损倍数
        self.risk_level = "NORMAL"   # NORMAL / HIGH / EXTREME
    
    def assess_risk(self, signal: TradingSignal, df: pd.DataFrame, 
                    rt_row: dict, position: int, entry_price: float) -> Tuple[TradingSignal, dict]:
        """风控检查，返回修正信号和风控建议"""
        
        atr = calc_atr(df)
        price = rt_row['close'] if rt_row else df['close'].iloc[-1]
        
        # 止损价
        if signal.signal == Signal.BUY:
            stop_loss = price - self.atr_multiplier * atr
            take_profit = price + 2.5 * atr
        elif signal.signal == Signal.SELL:
            stop_loss = price + self.atr_multiplier * atr
            take_profit = price - 2.5 * atr
        else:
            stop_loss, take_profit = 0, 0
        
        # 仓位
        if atr > 0:
            risk_amount = 100000 * self.max_loss_pct
            raw_pos = risk_amount / (self.atr_multiplier * atr)
            position_size = min(raw_pos / 100000, self.max_position)
        else:
            position_size = 0.1
        
        # 风险等级
        vol_20 = df['close'].pct_change().rolling(20).std().iloc[-1] * np.sqrt(20)
        if vol_20 > 0.25:
            self.risk_level = "EXTREME"
            position_size *= 0.5
        elif vol_20 > 0.15:
            self.risk_level = "HIGH"
            position_size *= 0.7
        
        # 持仓亏损强制止损
        if position > 0 and entry_price > 0:
            pnl_pct = (price - entry_price) / entry_price
            if pnl_pct < -self.max_loss_pct * 2:
                signal = TradingSignal(
                    agent=self.name,
                    signal=Signal.CLOSE_LONG,
                    confidence=0.99,
                    reason=f"触发强平(浮亏{pnl_pct:.1%})"
                )
        
        risk_info = {
            'atr': atr,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'position_size': position_size,
            'risk_level': self.risk_level,
        }
        
        return signal, risk_info

# ============================================================
# 投资顾问系统
# ============================================================
class TradingAdvisor:
    """股神2号投资顾问主控"""
    
    def __init__(self, ts_code: str = 'AG2606.SHF'):
        self.ts_code = ts_code
        
        self.analyst = AnalystAgent()
        self.researcher = ResearcherAgent()
        self.trader = TraderAgent()
        self.risk_agent = RiskAgent()
        
        # 状态
        self.position = 0
        self.entry_price = 0
        self.signals_history = []
    
    def get_data(self) -> Tuple[pd.DataFrame, dict]:
        """获取数据和实时行情"""
        df = get_fut_daily(self.ts_code, days=250)
        
        rt_df = get_rt_min(self.ts_code, freq='5MIN')
        rt_row = rt_df.iloc[-1].to_dict() if len(rt_df) > 0 else None
        
        return df, rt_row
    
    def analyze(self) -> Dict:
        """执行完整分析流程"""
        df, rt_row = self.get_data()
        
        if rt_row is None:
            return {'error': '无法获取实时数据'}
        
        price = rt_row['close']
        trade_time = rt_row.get('time', rt_row.get('trade_time', datetime.now().strftime('%H:%M')))
        
        # 各智能体分析
        analyst_sig = self.analyst.analyze(df, rt_row)
        researcher_sig = self.researcher.analyze(df)
        
        # 交易员决策
        all_signals = [analyst_sig, researcher_sig]
        trader_sig = self.trader.decide(all_signals)
        
        # 风控
        final_signal, risk_info = self.risk_agent.assess_risk(
            trader_sig, df, rt_row, self.position, self.entry_price
        )
        
        # 构建结果
        result = {
            'ts_code': self.ts_code,
            'trade_time': trade_time,
            'price': price,
            'analyst': analyst_sig,
            'researcher': researcher_sig,
            'trader': trader_sig,
            'final_signal': final_signal,
            'risk': risk_info,
            'position': self.position,
            'entry_price': self.entry_price,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        
        return result
    
    def format_report(self, r: Dict) -> str:
        """格式化投资建议报告"""
        sig = r['final_signal']
        risk = r.get('risk', {})
        
        sig_icon = {
            Signal.BUY: "🟢 买入",
            Signal.SELL: "🔴 卖出",
            Signal.HOLD: "⏸️ 观望",
            Signal.STRONG_BUY: "🟢🟢 强烈买入",
            Signal.STRONG_SELL: "🔴🔴 强烈卖出",
            Signal.CLOSE_LONG: "🟡 平仓",
        }.get(sig.signal, "❓")
        
        risk_color = {
            "NORMAL": "🟢",
            "HIGH": "🟡",
            "EXTREME": "🔴",
        }.get(risk.get('risk_level', 'NORMAL'), "⚪")
        
        lines = [
            "=" * 55,
            f"  股神2号 | AG2606 白银 | {r['trade_time']}",
            "=" * 55,
            "",
            f"  【当前价】{r['price']:.0f}",
            f"  【综合信号】{sig_icon} (置信度{sig.confidence:.0%})",
            f"    → {sig.reason}",
            "",
            "  ── 多智能体信号 ──────────────────────────",
            f"  📊 分析师: {r['analyst'].signal.value} ({r['analyst'].confidence:.0%})",
            f"     {r['analyst'].reason}",
            f"  📈 研究员: {r['researcher'].signal.value} ({r['researcher'].confidence:.0%})",
            f"     {r['researcher'].reason}",
            "",
            "  ── 风控建议 ───────────────────────────────",
            f"  {risk_color} 风险等级: {risk.get('risk_level', 'NORMAL')}",
            f"  📐 ATR: {risk.get('atr', 0):.1f}",
            f"  🛑 止损价: {risk.get('stop_loss', 0):.0f}" if risk.get('stop_loss') else "",
            f"  🎯 建议仓位: {risk.get('position_size', 0):.0%}",
            "",
        ]
        
        if r['position'] != 0:
            pos_type = "多" if r['position'] > 0 else "空"
            pnl = (r['price'] - r['entry_price']) / r['entry_price'] * 100
            pnl = pnl if r['position'] > 0 else -pnl
            lines.append(f"  📌 当前持仓: {pos_type}{abs(r['position'])}手 @ {r['entry_price']:.0f}")
            lines.append(f"     浮盈亏: {pnl:+.2f}%")
        
        lines.append("=" * 55)
        
        # 行动建议
        lines.append("")
        if sig.signal == Signal.BUY or sig.signal == Signal.STRONG_BUY:
            lines.append("  💡 操作建议: 可考虑开多/加多仓，止损设在场内")
        elif sig.signal == Signal.SELL or sig.signal == Signal.STRONG_SELL:
            lines.append("  💡 操作建议: 可考虑开空/加空仓，止损设在场内")
        else:
            lines.append("  💡 操作建议: 保持观望，等待明确信号")
        
        lines.append("")
        lines.append(f"  数据来源: Tushare Pro (Token已写死)")
        lines.append(f"  生成时间: {r['timestamp']}")
        
        return "\n".join(lines)
    
    def run_once(self) -> str:
        """运行一次分析并返回报告"""
        try:
            result = self.analyze()
            if 'error' in result:
                return f"❌ {result['error']}"
            return self.format_report(result)
        except Exception as e:
            import traceback
            return f"❌ 分析失败: {str(e)}\n{traceback.format_exc()}"


# ============================================================
# 主程序
# ============================================================
def main():
    parser = argparse.ArgumentParser(description='股神2号投资顾问')
    parser.add_argument('--monitor', action='store_true', help='持续盯盘模式')
    parser.add_argument('--interval', type=int, default=60, help='监控间隔秒数')
    args = parser.parse_args()
    
    advisor = TradingAdvisor('AG2606.SHF')
    
    if args.monitor:
        print("\n🟢 股神2号投资顾问 - 持续盯盘模式")
        print(f"   间隔: {args.interval}秒 | Ctrl+C 退出\n")
        
        running = True
        def signal_handler(sig, frame):
            nonlocal running
            running = False
            print("\n\n停止盯盘...")
        signal.signal(signal.SIGINT, signal_handler)
        
        while running:
            os.system('clear')
            report = advisor.run_once()
            print(report)
            print(f"\n⏰ {datetime.now().strftime('%H:%M:%S')} | 下次更新 {args.interval}秒后...")
            time.sleep(args.interval)
    else:
        # 一次性分析
        report = advisor.run_once()
        print(report)


if __name__ == '__main__':
    main()
