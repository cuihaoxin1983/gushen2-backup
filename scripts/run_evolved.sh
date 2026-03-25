#!/bin/bash
# 股神2号盯盘v3 - 使用进化版分析器
cd /root/.openclaw/workspace

# 1. 积累分钟历史数据
python3 historical_minute_accumulator.py --accumulate 2>/dev/null

# 2. 运行进化版分析
TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
python3 evolved_advisor.py 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' > /tmp/evolved_report.txt

# 获取实时价格
PRICE=$(python3 - << 'PYEOF'
import sys; sys.path.insert(0, '/usr/local/lib/python3.12/dist-packages')
import tushare as ts
ts.set_token('14d6be29b1b0b8a930fc488ceb343859b60f1357a1e1a85dcaee3712')
df = ts.pro_api().rt_fut_min(ts_code='AG2606.SHF', freq='5MIN')
print(int(df['close'].iloc[-1]))
PYEOF
)

# 提取关键字段
SIGNAL=$(grep "综合信号" /tmp/evolved_report.txt | sed 's/.*【综合信号】//' | awk '{print $1}')
CONF=$(grep "综合信号" /tmp/evolved_report.txt | grep -o "(置信度[0-9]*%)" | sed 's/(置信度//' | sed 's/)//')
ATR=$(grep "ATR=" /tmp/evolved_report.txt | sed 's/.*ATR=//' | sed 's/ .*//')
VOL=$(grep "波动率=" /tmp/evolved_report.txt | sed 's/.*波动率=//' | sed 's/%.*//')
URGENCY=$(grep "择时入场" /tmp/evolved_report.txt | grep -oE "HIGH|MEDIUM|LOW|WAIT" | tail -1)
REASON=$(grep "→" /tmp/evolved_report.txt | head -1 | sed 's/.*→ //')

# 写入状态文件
cat > /root/.openclaw/workspace/logs/latest_status.txt << EOF
股神2号 AG2606盯盘v3 $TIMESTAMP
===================================
信号: $SIGNAL ($CONF)
价格: $PRICE | ATR:$ATR | 波动率:$VOL%
紧急度: $URGENCY
原因: $REASON
EOF

# 复制完整报告
cp /tmp/evolved_report.txt /root/.openclaw/workspace/logs/latest_full_report.txt

# 追加历史
echo "[$TIMESTAMP] $SIGNAL($CONF) | $PRICE | ATR$ATR | ${VOL}% | $URGENCY" >> /root/.openclaw/workspace/logs/monitor_history.txt
