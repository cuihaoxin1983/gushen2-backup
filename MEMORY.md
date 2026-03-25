# MEMORY.md - 股神2号 长期记忆

## 身份
- 名字：股神2号
- 定位：中国A股/期货量化投资大师（比肩华尔街投行水平）
- 用户：崔哥（企业主，中长线股票+期货超短线）
- 当前重点：AG2606 白银期货

## 数据源（写死，不可更改）
- **Tushare Pro Token:** `14d6be29b1b0b8a930fc488ceb343859b60f1357a1e1a85dcaee3712`
- **实时接口:** `rt_fut_min` — 1MIN/5MIN/15MIN/30MIN/60MIN 全通 ✅
- **历史接口:** `fut_daily` — 日线历史数据 ✅
- **注意:** 历史分钟线`fut_bar`权限未开通
- **自积累:** `historical_minute_accumulator.py` 每2分钟抓取，自建分钟历史
- **验证状态:** 所有接口均正常（2026-03-25验证通过）

## 盯盘配置
- **盯盘间隔:** 每2分钟
- **交易时段:**
  - 上午: 9:30-11:30 (`*/2 9-11 * * 1-5`)
  - 下午: 13:30-15:00 (`*/2 13,14 * * 1-5`)
  - 夜盘: 21:00-02:00次日 (`*/2 21-23 * * 0-4` + `*/2 0,1,2 * * 1-5`)
- **状态文件:** `/root/.openclaw/workspace/logs/latest_status.txt`
- **完整报告:** `/root/.openclaw/workspace/logs/latest_full_report.txt`
- **历史记录:** `/root/.openclaw/workspace/logs/monitor_history.txt`

## 量化系统架构（TradingAgents进化版 v3.0）
五大智能体：
1. **AnalystAgent（分析师）** — MA/MACD/RSI/BOLL/SAR技术面
2. **ResearcherAgent（研究员）** — 持仓量/波动率/动量/资金流向
3. **TraderAgent（交易员）** — 投票综合决策
4. **RiskAgent（风控）** — ATR动态止损+仓位管理+回撤控制
5. **TimingAgent（择时Agent）** — 最佳入场点位筛选 ← NEW!

进化特性：
- 动态仓位（波动率自适应，波动越高仓位越低）
- 资金曲线跟踪（最大回撤控制）
- 自我学习记录（正确/错误判断，持续迭代）
- 分钟历史数据自积累（突破fut_bar权限限制）

## 核心文件
```bash
# 进化版主程序
python3 /root/.openclaw/workspace/evolved_advisor.py

# 选时系统
python3 /root/.openclaw/workspace/timing_analysis.py

# 专家指标
python3 /root/.openclaw/workspace/expert_indicators.py

# 分钟数据积累
python3 /root/.openclaw/workspace/historical_minute_accumulator.py --accumulate

# 查看状态
cat /root/.openclaw/workspace/logs/latest_status.txt
```

## 备份
- GitHub仓库: https://github.com/cuihaoxin1983/gushen2-backup
- 每日凌晨2点自动备份

## 当前AG2606分析
- 信号: HOLD (30%) — 均衡观望
- 价格: ~18111
- ATR: 1516, 波动率: 89%（极高）
- 紧急度: WAIT
- 注意: 白银波动率极高(89%年化)，动态仓位上限35%

## 技术栈
- Python 3.12 + pandas + numpy + tushare 1.3.9
- backtrader（回测框架）
- 数据路径: sys.path.insert(0, '/usr/local/lib/python3.12/dist-packages')
