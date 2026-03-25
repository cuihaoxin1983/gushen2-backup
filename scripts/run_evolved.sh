#!/bin/bash
# 股神2号盯盘v5.4 - 自适应策略系统
cd /root/.openclaw/workspace

TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
python3 trading_system_v5.py 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' > /tmp/v54_output.txt

# 提取关键信息
SIGNAL=$(grep "综合信号:" /tmp/v54_output.txt | head -1 | sed 's/.*综合信号: //' | awk -F'[' '{print $2}' | sed 's/].*//')
CONF=$(grep "置信度" /tmp/v54_output.txt | head -1 | grep -o "[0-9]*%" | head -1)
PRICE=$(grep "实时价格:" /tmp/v54_output.txt | head -1 | awk '{print $2}')
ATR=$(grep "ATR:" /tmp/v54_output.txt | head -1 | awk '{print $2}' | tr -d '|')
SCORE=$(grep "评分:" /tmp/v54_output.txt | head -1 | awk '{print $2}')
BEST=$(grep "最优策略:" /tmp/v54_output.txt | head -1 | sed 's/.*最优策略: //' | sed 's/ (.*//')
STATE=$(grep "市场状态:" /tmp/v54_output.txt | head -1 | sed 's/.*市场状态: //' | awk -F']' '{print $1}' | sed 's/\[//')

# 写简洁状态
cat > /root/.openclaw/workspace/logs/latest_status.txt << EOF
股神2号盯盘v5.4 $TIMESTAMP
===================================
市场: [$STATE]
信号: $SIGNAL ($CONF)
价格: $PRICE | ATR:$ATR
评分: $SCORE
最优策略: $BEST
EOF

# 保存完整报告
cp /tmp/v54_output.txt /root/.openclaw/workspace/logs/latest_full_report.txt

# 历史追加
echo "[$TIMESTAMP] [$STATE] $SIGNAL($CONF) | $PRICE | ATR$ATR | $SCORE | $BEST" >> /root/.openclaw/workspace/logs/monitor_history.txt
