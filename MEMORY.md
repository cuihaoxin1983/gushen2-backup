# MEMORY.md - 股神2号 长期记忆

## 身份
- 名字：股神2号
- 定位：中国A股/期货量化投资大师
- 用户：崔哥（企业主，期货超短线）
- 当前重点：AG2606 白银期货

## 盯盘系统（默认使用v6.0）
- **主程序**: `trading_system_v6.py`
- **框架**: TradingAgents多智能体 + VectorBT回测过滤
- **LLM**: MiniMax (abab6-chat)
- **API Key**: sk-api-ajVztMXXnsZz1nbFav0qTdZs4aSLt0B7t0rUvrW2ZBzFnZ24_OS3PeiP-Y92PkKYKs6RwQkAFxW4m4gBtUm8xJcSdMfzKwGj2yeqqbIerxQeyEmF1Ltjm9Q
- **数据**: Tushare Pro Token: 14d6be29b1b0b8a930fc488ceb343859b60f1357a1e1a85dcaee3712
- **盯盘间隔**: 每2分钟，交易时段: 9:30-11:30 / 13:30-15:00 / 21:00-02:00

## 核心架构（TradingAgents + VectorBT）
```
Agent 1: 技术分析师 → 技术指标评分
Agent 2: 多头研究员 → VectorBT验证做多信号
Agent 3: 空头研究员 → VectorBT验证做空信号
Agent 4: 交易员 → LLM辩论决策
Agent 5: 风控经理 → 仓位/止损计算
Agent 6: 投资组合经理 → 最终审批
```

## 核心文件
```bash
# 默认盯盘程序
python3 /root/.openclaw/workspace/trading_system_v6.py

# 查看状态
cat /root/.openclaw/workspace/logs/latest_status.txt
```

## 回测结果（AG2606，188条日线）
| 策略 | 最优参数 | 收益率 | 夏普 | 胜率 |
|------|---------|--------|------|------|
| MA | MA(3/20) | 109.5% | 2.42 | 50% |
| RSI | RSI(10,30/80) | 19.8% | 0.94 | 100% |
| MACD | MACD(8,30,9) | 96.5% | 2.45 | 40% |
| DMI | DMI(14,ADX>20) | 95.6% | 2.33 | 80% |

## GitHub
- 仓库: https://github.com/cuihaoxin1983/gushen2-backup
- push有时失败（网络问题），本地安全
