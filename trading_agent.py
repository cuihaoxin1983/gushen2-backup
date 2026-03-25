#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股神2号 - TradingAgents 量化交易系统
Multi-Agent Quantitative Trading System

架构：
  Analyst Agent（分析师）   → 宏观/技术面分析
  Researcher Agent（研究员）→ 基本面/产业链研究
  Trader Agent（交易员）   → 择时与仓位决策
  Risk Agent（风控）       → 止损/仓位/回撤控制

数据源：Tushare Pro (已写死)
回测框架：Backtrader
"""

import sys
sys.path.insert(0, '/usr/local/lib/python3.12/dist-packages')

import os
import json
import warnings
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd
import numpy as np
import tushare as ts
import backtrader as bt

warnings.filterwarnings('ignore')

# ============================================================
# TUSHARE CONFIG（写死）
# ============================================================
TUSHARE_TOKEN = '14d6be29b1b0b8a930fc488ceb343859b60f1357a1e1a85dcaee3712'
ts.set_token(TUSHARE_TOKEN)
PRO = ts.pro_api()

# ============================================================
# 工具函数
# ============================================================
def get_fut_daily(ts_code: str, days: int = 250) -> pd.DataFrame:
    """获取期货日线历史数据"""
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
    df = PRO.fut_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
    df = df.sort_values('trade_date').reset_index(drop=True)
    return df

def get_rt_fut_min(ts_code: str, freq: str = '5MIN') -> pd.DataFrame:
    """获取实时分钟数据（最近一根）"""
    try:
        df = PRO.rt_fut_min(ts_code=ts_code, freq=freq)
        return df
    except Exception as e:
        print(f"⚠️ 实时数据获取失败: {e}")
        return pd.DataFrame()

# ============================================================
# 信号枚举
# ============================================================
class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    CLOSE_LONG = "CLOSE_LONG"
    CLOSE_SHORT = "CLOSE_SHORT"

# ============================================================
# 交易信号数据结构
# ============================================================
@dataclass
class TradingSignal:
    agent: str
    signal: Signal
    confidence: float  # 0.0 ~ 1.0
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.now().strftime('%Y-%m-%d %H:%M'))

# ============================================================
# ANALYST AGENT - 分析师（技术面 + 宏观）
# ============================================================
class AnalystAgent:
    """技术面分析师：看K线形态、均线、MACD、RSI、布林带"""

    name = "AnalystAgent(分析师)"

    def __init__(self):
        self.lookback = 60  # 看最近60根日K

    def analyze(self, df: pd.DataFrame) -> TradingSignal:
        df = df.tail(self.lookback).copy()

        # ---- 均线系统 ----
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()

        # ---- MACD ----
        exp12 = df['close'].ewm(span=12).mean()
        exp26 = df['close'].ewm(span=26).mean()
        df['macd'] = exp12 - exp26
        df['signal'] = df['macd'].ewm(span=9).mean()
        df['histogram'] = df['macd'] - df['signal']

        # ---- RSI ----
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        df['rsi'] = 100 - (100 / (1 + rs))

        # ---- 布林带 ----
        df['bb_mid'] = df['close'].rolling(20).mean()
        df['bb_std'] = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_mid'] + 2 * df['bb_std']
        df['bb_lower'] = df['bb_mid'] - 2 * df['bb_std']

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # ---- 趋势判断 ----
        uptrend = latest['ma5'] > latest['ma20'] > latest['ma60']
        downtrend = latest['ma5'] < latest['ma20'] < latest['ma60']

        # ---- MACD 金叉/死叉 ----
        macd_bullish = prev['histogram'] < 0 and latest['histogram'] > 0
        macd_bearish = prev['histogram'] > 0 and latest['histogram'] < 0

        # ---- RSI 极值 ----
        rsi_oversold = latest['rsi'] < 30
        rsi_overbought = latest['rsi'] > 70

        # ---- 布林带开口 ----
        bb_squeeze = (df['bb_upper'].iloc[-1] - df['bb_lower'].iloc[-1]) < \
                     (df['bb_upper'].iloc[-5] - df['bb_lower'].iloc[-5]) * 0.8

        # ---- 综合打分 ----
        score = 0
        reasons = []

        if uptrend:
            score += 0.2
            reasons.append("均线多头排列")
        if downtrend:
            score -= 0.2
            reasons.append("均线空头排列")
        if macd_bullish:
            score += 0.25
            reasons.append("MACD金叉")
        if macd_bearish:
            score -= 0.25
            reasons.append("MACD死叉")
        if rsi_oversold:
            score += 0.2
            reasons.append("RSI超卖")
        if rsi_overbought:
            score -= 0.2
            reasons.append("RSI超买")
        if bb_squeeze:
            score += 0.1
            reasons.append("布林带收口")

        # 突破布林上轨
        if latest['close'] > latest['bb_upper']:
            score += 0.15
            reasons.append("突破布林上轨")

        # 跌破布林下轨
        if latest['close'] < latest['bb_lower']:
            score -= 0.15
            reasons.append("跌破布林下轨")

        # 限制在[-1, 1]
        score = max(-1.0, min(1.0, score))

        if score >= 0.5:
            signal = Signal.BUY
        elif score <= -0.5:
            signal = Signal.SELL
        else:
            signal = Signal.HOLD

        reason_str = f"技术面评分{score:.2f}({'偏多' if score>0 else '偏空' if score<0 else '中性'})，{' + '.join(reasons[:4])}"

        print(f"  [{self.name}] {reason_str}")

        return TradingSignal(
            agent=self.name,
            signal=signal,
            confidence=abs(score),
            reason=reason_str
        )

# ============================================================
# RESEARCHER AGENT - 研究员（产业链/事件驱动）
# ============================================================
class ResearcherAgent:
    """基本面/事件研究员：持仓量变化、波动率、近期事件"""

    name = "ResearcherAgent(研究员)"

    def analyze(self, df: pd.DataFrame) -> TradingSignal:
        df = df.tail(20).copy()

        # ---- 波动率分析 ----
        df['returns'] = df['close'].pct_change()
        vol = df['returns'].std() * np.sqrt(20)  # 月化波动率

        # ---- 持仓量变化 ----
        oi_change_pct = (df['oi'].iloc[-1] - df['oi'].iloc[-5]) / df['oi'].iloc[-5] * 100

        # ---- 价格动量 ----
        momentum_5d = (df['close'].iloc[-1] - df['close'].iloc[-6]) / df['close'].iloc[-6] * 100

        # ---- 成交量异常 ----
        vol_ma5 = df['vol'].rolling(5).mean().iloc[-1]
        vol_current = df['vol'].iloc[-1]
        vol_surge = vol_current > vol_ma5 * 1.5

        reasons = []
        score = 0.0

        # 持仓量大幅增加 → 趋势可能延续
        if oi_change_pct > 5:
            score += 0.3
            reasons.append(f"持仓量增加{oi_change_pct:.1f}%")
        elif oi_change_pct < -5:
            score -= 0.3
            reasons.append(f"持仓量减少{abs(oi_change_pct):.1f}%")

        # 高波动率 → 谨慎
        if vol > 0.10:
            score -= 0.1
            reasons.append(f"高波动率({vol:.1%})")

        # 放量上涨
        if vol_surge and momentum_5d > 0:
            score += 0.25
            reasons.append("放量上涨")
        elif vol_surge and momentum_5d < 0:
            score -= 0.25
            reasons.append("放量下跌")

        # 动量
        if momentum_5d > 3:
            score += 0.2
            reasons.append(f"5日动能+{momentum_5d:.1f}%")
        elif momentum_5d < -3:
            score -= 0.2
            reasons.append(f"5日动能{momentum_5d:.1f}%")

        score = max(-1.0, min(1.0, score))

        if score >= 0.5:
            signal = Signal.BUY
        elif score <= -0.5:
            signal = Signal.SELL
        else:
            signal = Signal.HOLD

        reason_str = f"基本面评分{score:.2f}，{' + '.join(reasons[:3])}"
        print(f"  [{self.name}] {reason_str}")

        return TradingSignal(
            agent=self.name,
            signal=signal,
            confidence=abs(score),
            reason=reason_str
        )

# ============================================================
# TRADER AGENT - 交易员（综合决策 + 择时）
# ============================================================
class TraderAgent:
    """交易员：汇总分析师+研究员信号，给出最终决策"""

    name = "TraderAgent(交易员)"

    def decide(self, signals: List[TradingSignal]) -> TradingSignal:
        print(f"\n  [{self.name}] 综合决策:")

        buy_count = sum(1 for s in signals if s.signal == Signal.BUY)
        sell_count = sum(1 for s in signals if s.signal == Signal.SELL)

        # 加权置信度
        buy_conf = sum(s.confidence for s in signals if s.signal == Signal.BUY)
        sell_conf = sum(s.confidence for s in signals if s.signal == Signal.SELL)

        final_signal = Signal.HOLD
        confidence = 0.0
        reasons = []

        if buy_count > sell_count and buy_conf > sell_conf:
            final_signal = Signal.BUY
            confidence = (buy_conf / max(buy_count, 1)) * 0.8
            reasons.append(f"多数信号做多({buy_count} vs {sell_count})")
        elif sell_count > buy_count and sell_conf > buy_conf:
            final_signal = Signal.SELL
            confidence = (sell_conf / max(sell_count, 1)) * 0.8
            reasons.append(f"多数信号做空({sell_count} vs {buy_count})")
        elif buy_count == sell_count and buy_conf > sell_conf:
            final_signal = Signal.BUY
            confidence = (buy_conf - sell_conf) * 0.5
            reasons.append("信号均衡偏多")
        elif buy_count == sell_count and sell_conf > buy_conf:
            final_signal = Signal.SELL
            confidence = (sell_conf - buy_conf) * 0.5
            reasons.append("信号均衡偏空")
        else:
            reasons.append("信号不明，保持观望")

        reason_str = " | ".join(reasons)
        print(f"  → 最终决策: {final_signal.value} (置信度{confidence:.2%})")

        return TradingSignal(
            agent=self.name,
            signal=final_signal,
            confidence=confidence,
            reason=reason_str
        )

# ============================================================
# RISK AGENT - 风控（止损/仓位/回撤）
# ============================================================
class RiskAgent:
    """风控：ATR止损 + 动态仓位 + 回撤控制"""

    name = "RiskAgent(风控)"

    def __init__(self):
        self.max_loss_per_trade = 0.02      # 单笔最大亏损2%
        self.max_drawdown = 0.15             # 最大回撤15%
        self.max_position = 0.8              # 最大仓位80%
        self.atr_multiplier = 2.0            # ATR倍数

    def calc_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """计算ATR"""
        high = df['high'].iloc[-period:]
        low = df['low'].iloc[-period:]
        close = df['close'].iloc[-period:]

        tr1 = high - low
        tr2 = abs(high - close.shift(1).iloc[-period:])
        tr3 = abs(low - close.shift(1).iloc[-period:])

        tr = pd.concat([tr1.reset_index(drop=True),
                        tr2.reset_index(drop=True),
                        tr3.reset_index(drop=True)], axis=1).max(axis=1)
        atr = tr.rolling(period).mean().iloc[-1]
        return atr

    def check_risk(self, signal: TradingSignal, df: pd.DataFrame,
                   current_position: float, equity: float,
                   entry_price: float) -> Tuple[TradingSignal, float, float]:
        """风控检查，返回修正后的信号、止损价、仓位"""

        atr = self.calc_atr(df)
        latest_price = df['close'].iloc[-1]

        # ---- 止损计算 ----
        if signal.signal == Signal.BUY:
            stop_loss = latest_price - self.atr_multiplier * atr
            take_profit = latest_price + 2 * self.atr_multiplier * atr
        elif signal.signal == Signal.SELL:
            stop_loss = latest_price + self.atr_multiplier * atr
            take_profit = latest_price - 2 * self.atr_multiplier * atr
        else:
            stop_loss, take_profit = 0, 0

        # ---- 仓位计算 ----
        risk_amount = equity * self.max_loss_per_trade
        if atr > 0:
            position_size = risk_amount / (self.atr_multiplier * atr)
            position_pct = min(position_size / equity, self.max_position)
        else:
            position_pct = 0.1

        # ---- 风控信号修正 ----
        modified_signal = signal
        reasons = []

        # 如果当前亏损过大，强制平仓
        if current_position > 0 and entry_price > 0:
            unrealized_pnl = (latest_price - entry_price) / entry_price
            if unrealized_pnl < -self.max_loss_per_trade * 2:
                modified_signal = TradingSignal(
                    agent=self.name,
                    signal=Signal.CLOSE_LONG,
                    confidence=0.99,
                    reason=f"触发强平(浮亏{unrealized_pnl:.1%})"
                )
                reasons.append("强制止损")

        # 回撤超限，空仓观望
        if self.max_drawdown > 0 and current_position == 0:
            # 这里应该检查 equity peakdrawdown，实际用简化版
            pass

        final_reasons = signal.reason
        if reasons:
            final_reasons += " | " + " + ".join(reasons)

        print(f"  [{self.name}] ATR={atr:.1f} 止损={stop_loss:.0f} 仓位={position_pct:.0%}")

        return modified_signal, stop_loss, position_pct

# ============================================================
# TRADING AGENTS SYSTEM - 多智能体系统
# ============================================================
class TradingAgentsSystem:
    """多智能体量化交易系统主控"""

    def __init__(self, ts_code: str = 'AG2606.SHF'):
        self.ts_code = ts_code

        # 初始化各智能体
        self.analyst = AnalystAgent()
        self.researcher = ResearcherAgent()
        self.trader = TraderAgent()
        self.risk_agent = RiskAgent()

        # 状态
        self.position = 0       # 持仓手数
        self.entry_price = 0    # 开仓价
        self.equity = 100000.0 # 初始资金
        self.peak_equity = self.equity

        print("=" * 60)
        print(f"  股神2号 TradingAgents 量化系统")
        print(f"  交易品种: {ts_code}")
        print(f"  初始资金: {self.equity:,.0f}")
        print("=" * 60)

    def run(self):
        """运行一次多智能体决策"""

        # 1. 获取数据
        print(f"\n📊 [{self.ts_code}] 数据加载中...")
        df = get_fut_daily(self.ts_code, days=250)
        if len(df) < 60:
            print("❌ 数据不足，无法分析")
            return

        latest_price = df['close'].iloc[-1]
        print(f"  最新价: {latest_price} | 数据量: {len(df)}条")

        # 2. Analyst 分析
        analyst_signal = self.analyst.analyze(df)

        # 3. Researcher 分析
        researcher_signal = self.researcher.analyze(df)

        # 4. Trader 决策
        all_signals = [analyst_signal, researcher_signal]
        trader_signal = self.trader.decide(all_signals)

        # 5. Risk 风控
        risk_signal, stop_loss, position_pct = self.risk_agent.check_risk(
            trader_signal, df,
            self.position, self.equity, self.entry_price
        )

        # 6. 执行交易逻辑
        self._execute(trader_signal, risk_signal, latest_price, stop_loss, position_pct)

        # 7. 输出状态
        self._print_status(latest_price)

    def _execute(self, signal: TradingSignal, risk_signal: TradingSignal,
                price: float, stop_loss: float, position_pct: float):
        """执行交易"""

        # 风控优先
        final_signal = risk_signal if risk_signal.signal != Signal.HOLD else signal

        if final_signal.signal == Signal.BUY and self.position <= 0:
            # 开多或平空
            if self.position < 0:
                print(f"  🟢 平空单 @ {price}")
                pnl = (self.entry_price - price) * abs(self.position)
                self.equity += pnl
                print(f"  💰 平空盈亏: {pnl:+.0f}")
            # 开多
            target_pos = int(self.equity * position_pct / price)
            if target_pos > 0:
                self.position = target_pos
                self.entry_price = price
                print(f"  🟢 开多 {self.position}手 @ {price}")

        elif final_signal.signal == Signal.SELL and self.position >= 0:
            # 开空或平多
            if self.position > 0:
                print(f"  🔴 平多单 @ {price}")
                pnl = (price - self.entry_price) * self.position
                self.equity += pnl
                print(f"  💰 平多盈亏: {pnl:+.0f}")
            # 开空
            target_pos = int(self.equity * position_pct / price)
            if target_pos > 0:
                self.position = -target_pos
                self.entry_price = price
                print(f"  🔴 开空 {abs(self.position)}手 @ {price}")

        elif final_signal.signal == Signal.CLOSE_LONG and self.position > 0:
            print(f"  🟡 强制平多 @ {price}")
            pnl = (price - self.entry_price) * self.position
            self.equity += pnl
            print(f"  💰 平多盈亏: {pnl:+.0f}")
            self.position = 0

        elif final_signal.signal == Signal.HOLD:
            print(f"  ⏸️ 保持观望")

    def _print_status(self, price: float):
        """打印当前状态"""
        if self.position != 0:
            pnl_pct = (price - self.entry_price) / self.entry_price * 100
            pnl_pct = pnl_pct if self.position > 0 else -pnl_pct
            unrealized = (price - self.entry_price) * abs(self.position)
            unrealized = unrealized if self.position > 0 else -unrealized
            direction = "多" if self.position > 0 else "空"
            print(f"\n  📌 持仓: {direction}{abs(self.position)}手 @ {self.entry_price}")
            print(f"     当前: {price} ({pnl_pct:+.2f}%)")
            print(f"     浮盈: {unrealized:+.0f}")
        else:
            print(f"\n  📌 空仓中")

        # 更新峰值
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity
        drawdown = (self.peak_equity - self.equity) / self.peak_equity * 100
        print(f"  💵 账户净值: {self.equity:,.0f} | 最大回撤: {drawdown:.1f}%")

    def backtest(self, start_date: str = None, end_date: str = None):
        """回测模式（基于日线）"""
        print("\n" + "=" * 60)
        print("  回测模式")
        print("=" * 60)

        if start_date is None:
            start_date = (datetime.now() - timedelta(days=250)).strftime('%Y%m%d')
        if end_date is None:
            end_date = datetime.now().strftime('%Y%m%d')

        df = PRO.fut_daily(ts_code=self.ts_code,
                          start_date=start_date, end_date=end_date)
        df = df.sort_values('trade_date').reset_index(drop=True)

        print(f"  回测区间: {start_date} ~ {end_date}")
        print(f"  数据量: {len(df)} 条")

        # 简化的回测：按日线信号操作
        bt_results = self._run_backtest(df)
        self._print_backtest_results(bt_results, df)

    def _run_backtest(self, df: pd.DataFrame) -> Dict:
        """运行回测引擎"""
        initial = 100000.0
        equity = initial
        position = 0
        entry = 0
        trades = []

        for i in range(20, len(df)):
            window = df.iloc[:i].copy()

            # Analyst信号
            a_sig = self.analyst.analyze(window)
            # Researcher信号
            r_sig = self.researcher.analyze(window)
            # Trader决策
            signals = [a_sig, r_sig]

            buy_c, sell_c = sum(1 for s in signals if s.signal == Signal.BUY), \
                           sum(1 for s in signals if s.signal == Signal.SELL)

            current_price = df.iloc[i]['close']
            date = df.iloc[i]['trade_date']

            # 简单策略
            if buy_c > sell_c and position <= 0:
                if position < 0:
                    pnl = (entry - current_price) * abs(position)
                    equity += pnl
                    trades.append({'date': date, 'type': 'cover', 'pnl': pnl})
                position = int(equity * 0.3 / current_price)
                entry = current_price
                trades.append({'date': date, 'type': 'buy', 'price': entry, 'pos': position})

            elif sell_c > buy_c and position >= 0:
                if position > 0:
                    pnl = (current_price - entry) * position
                    equity += pnl
                    trades.append({'date': date, 'type': 'sell', 'pnl': pnl})
                position = -int(equity * 0.3 / current_price)
                entry = current_price
                trades.append({'date': date, 'type': 'short', 'price': entry, 'pos': abs(position)})

        # 平仓
        if position != 0:
            final_price = df.iloc[-1]['close']
            if position > 0:
                pnl = (final_price - entry) * position
            else:
                pnl = (entry - final_price) * abs(position)
            equity += pnl
            position = 0

        total_return = (equity - initial) / initial * 100
        win_trades = [t for t in trades if 'pnl' in t and t['pnl'] > 0]
        lose_trades = [t for t in trades if 'pnl' in t and t['pnl'] < 0]

        return {
            'initial': initial,
            'final': equity,
            'total_return': total_return,
            'num_trades': len([t for t in trades if 'pnl' in t]),
            'win_trades': len(win_trades),
            'lose_trades': len(lose_trades),
            'win_rate': len(win_trades) / max(len(win_trades) + len(lose_trades), 1),
            'max_win': max([t['pnl'] for t in trades if 'pnl' in t], default=0),
            'max_loss': min([t['pnl'] for t in trades if 'pnl' in t], default=0),
        }

    def _print_backtest_results(self, results: Dict, df: pd.DataFrame):
        """打印回测结果"""
        print("\n" + "=" * 60)
        print("  📈 回测结果")
        print("=" * 60)
        print(f"  初始资金:  {results['initial']:>15,.0f}")
        print(f"  最终净值:  {results['final']:>15,.0f}")
        print(f"  总收益率:  {results['total_return']:>15,.2f}%")
        print(f"  总交易次数: {results['num_trades']:>14}")
        print(f"  盈利次数:  {results['win_trades']:>14}")
        print(f"  亏损次数:  {results['lose_trades']:>14}")
        print(f"  胜率:      {results['win_rate']:>14.1%}")
        print(f"  单笔最大盈利: {results['max_win']:>12,.0f}")
        print(f"  单笔最大亏损: {results['max_loss']:>12,.0f}")

        # 计算年化收益
        days = len(df)
        years = days / 250
        annualized = ((results['final'] / results['initial']) ** (1/years) - 1) * 100
        print(f"  年化收益率: {annualized:>12.2f}%")

        # 计算夏普比（简化）
        returns_series = df['close'].pct_change().dropna()
        sharpe = returns_series.mean() / returns_series.std() * np.sqrt(250) if returns_series.std() > 0 else 0
        print(f"  夏普比率(简化): {sharpe:>10.2f}")
        print("=" * 60)

# ============================================================
# 主程序入口
# ============================================================
if __name__ == '__main__':
    print("""
    ╔═══════════════════════════════════════════╗
    ║     股神2号 TradingAgents 量化系统 v1.0    ║
    ║     Multi-Agent Quantitative Trading      ║
    ╚═══════════════════════════════════════════╝
    """)

    # 交易品种
    TS_CODE = 'AG2606.SHF'

    # 创建系统
    system = TradingAgentsSystem(ts_code=TS_CODE)

    # 1. 实时决策
    print("\n" + "▶" * 30)
    print("  [实时决策模式]")
    print("▶" * 30)
    system.run()

    # 2. 回测
    print("\n" + "▶" * 30)
    print("  [历史回测模式]")
    print("▶" * 30)
    system.backtest()
