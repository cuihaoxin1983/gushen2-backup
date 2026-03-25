#!/bin/bash
# 股神2号盯盘v5.5 - 信号历史验证系统
cd /root/.openclaw/workspace

TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
python3 trading_system_v5.py 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' > /tmp/v55_output.txt

# 提取关键信息
SIGNAL=$(grep "综合信号:" /tmp/v55_output.txt | head -1 | sed 's/.*综合信号: //' | awk -F'[' '{print $2}' | sed 's/].*//')
CONF=$(grep "综合置信度:" /tmp/v55_output.txt | head -1 | sed 's/.*= //')
PRICE=$(grep "实时价格:" /tmp/v55_output.txt | head -1 | awk '{print $2}')
ATR=$(grep "ATR:" /tmp/v55_output.txt | head -1 | awk '{print $2}' | tr -d '|')
SCORE=$(grep "指标评分:" /tmp/v55_output.txt | head -1 | awk '{print $2}')
BEST=$(grep "最佳信号:" /tmp/v55_output.txt | head -1 | sed 's/.*最佳信号: //' | sed 's/ (.*//')
STATE=$(grep "市场状态:" /tmp/v55_output.txt | head -1 | sed 's/.*市场状态: //' | awk -F']' '{print $1}' | sed 's/\[//')

# 写简洁状态
cat > /root/.openclaw/workspace/logs/latest_status.txt << EOF
股神2号盯盘v5.5 $TIMESTAMP
===================================
市场: [$STATE]
信号: $SIGNAL (置信度$CONF)
价格: $PRICE | ATR:$ATR
指标评分: $SCORE
最优历史信号: $BEST
EOF

# 保存完整报告
cp /tmp/v55_output.txt /root/.openclaw/workspace/logs/latest_full_report.txt

# 历史追加
echo "[$TIMESTAMP] [$STATE] $SIGNAL($CONF) | $PRICE | ATR$ATR | $SCORE | $BEST" >> /root/.openclaw/workspace/logs/monitor_history.txt
