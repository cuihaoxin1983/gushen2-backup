# MEMORY.md - 股神2号 长期记忆

## 身份
- 名字：股神2号
- 定位：中国A股/期货量化投资大师（比肩华尔街投行水平）
- 用户：崔哥（企业主，中长线股票+期货超短线）
- 当前重点：AG2606 白银期货

## 数据源（写死，不可更改）
- **Tushare Pro Token:** `14d6be29b1b0b8a930fc488ceb343859b60f1357a1e1a85dcaee3712`
- **实时接口:** `rt_fut_min` — 1MIN/5MIN/15MIN/30MIN/60MIN 全通
- **历史接口:** `fut_daily` — 日线历史数据
- **验证状态:** 正常

## GitHub备份
- 仓库: https://github.com/cuihaoxin1983/gushen2-backup
- ⚠️ push有时失败（服务器网络问题），本地代码安全

## 盯盘配置
- **盯盘间隔:** 每2分钟
- **交易时段:**
  - 上午: 9:30-11:30
  - 下午: 13:30-15:00
  - 夜盘: 21:00-02:00

## 系统版本
| 文件 | 版本 | 说明 |
|------|------|------|
| `trading_system_v5.py` | v5.0 | 完整量化系统（推荐）|
| `vectorbt_backtest.py` | v4.0 | VectorBT回测 |
| `evolved_advisor.py` | v3.0 | 五大智能体 |
| `market_regime_detector.py` | v3.1 | 市场状态识别 |
| `timing_analysis.py` | - | 选时分析 |
| `expert_indicators.py` | - | 专家指标 |

## 回测结果（AG2606，188条日线）
- **MA最优**: MA(3/20) — 收益109.5% 夏普2.42
- **RSI最优**: RSI(10,30/80) — 收益19.8% 夏普0.94
- **MACD最优**: MACD(8,30,9) — 收益96.5% 夏普2.45
- **全局最优**: MACD(8,30,9) — 夏普2.45

## 当前信号（观望）
- 信号: HOLD (30%)
- 价格: ~18111
- 波动率: 92%（极高）
- 建议仓位: 35%

## 关键价位
- 支撑: 17000, 16385（布林下轨）
- 压力: 18111（当前）, 19000, 20568（MA20）

## 技术栈
- Python 3.12 + pandas + numpy + tushare 1.3.9
- VectorBT 0.28.4（极速回测）
- backtrader
