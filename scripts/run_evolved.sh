#!/bin/bash
# 股神2号盯盘v5.2 - 使用最新版量化系统
cd /root/.openclaw/workspace

TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
python3 trading_system_v5.py 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' > /tmp/v52_output.txt

# 提取关键信息
SIGNAL=$(grep "综合信号:" /tmp/v52_output.txt | head -1 | sed 's/.*综合信号: //' | awk '{print $1}')
CONF=$(grep "置信度" /tmp/v52_output.txt | head -1 | grep -o "[0-9]*%" | head -1)
PRICE=$(grep "实时价格:" /tmp/v52_output.txt | head -1 | awk '{print $2}')
ATR=$(grep "ATR:" /tmp/v52_output.txt | head -1 | awk '{print $2}' | tr -d '|')
SCORE=$(grep "评分:" /tmp/v52_output.txt | head -1 | awk '{print $2}')
BEST=$(grep "全局最优" /tmp/v52_output.txt | head -1 | sed 's/.*最优: //' | sed 's/)//')
KELLY=$(grep "凯利仓位:" /tmp/v52_output.txt | head -1 | sed 's/.*仓位: //')

# 写简洁状态
cat > /root/.openclaw/workspace/logs/latest_status.txt << EOF
股神2号盯盘v5.2 $TIMESTAMP
===================================
信号: $SIGNAL ($CONF)
价格: $PRICE | ATR:$ATR
评分: $SCORE
最优策略: $BEST
建议仓位: $KELLY
EOF

# 保存完整报告
cp /tmp/v52_output.txt /root/.openclaw/workspace/logs/latest_full_report.txt

# 历史追加
echo "[$TIMESTAMP] $SIGNAL($CONF) | $PRICE | ATR$ATR | $SCORE | $BEST" >> /root/.openclaw/workspace/logs/monitor_history.txt
