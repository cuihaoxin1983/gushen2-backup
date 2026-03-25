#!/bin/bash
# 股神2号盯盘 - TradingAgents + VectorBT 混合系统 (v6.0)
cd /root/.openclaw/workspace

TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
python3 trading_system_v6.py 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' > /tmp/v60_output.txt

# 提取关键信息
SIGNAL=$(grep "最终决策:" /tmp/v60_output.txt | head -1 | sed 's/.*最终决策: //' | awk '{print $1}')
CONF=$(grep "置信度" /tmp/v60_output.txt | grep "交易员" | head -1 | grep -o "[0-9]*%" | head -1 || echo "N/A")
PRICE=$(grep "AG2606" /tmp/v60_output.txt | head -1 | awk -F'|' '{print $3}' | awk '{print $2}')
STATE=$(grep "市场:" /tmp/v60_output.txt | head -1 | sed 's/.*市场: //' | sed 's/].*//' | sed 's/\[//')
LLM=$(grep "LLM建议:" /tmp/v60_output.txt | head -1 | sed 's/.*LLM建议: //' | cut -c1-15)

# 写简洁状态
cat > /root/.openclaw/workspace/logs/latest_status.txt << EOF
股神2号盯盘v6.0 $TIMESTAMP
===================================
市场: [$STATE]
信号: $SIGNAL (置信度$CONF)
价格: $PRICE
LLM建议: $LLM
EOF

# 保存完整报告
cp /tmp/v60_output.txt /root/.openclaw/workspace/logs/latest_full_report.txt

# 历史追加
echo "[$TIMESTAMP] [$STATE] $SIGNAL($CONF) | $PRICE | $LLM" >> /root/.openclaw/workspace/logs/monitor_history.txt
