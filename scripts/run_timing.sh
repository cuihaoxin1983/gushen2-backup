#!/bin/bash
# 股神2号定时盯盘 - 期货交易时间段
# 9:30-11:30 | 13:30-15:00 | 21:00-02:00(次日)

cd /root/.openclaw/workspace

TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
python3 timing_analysis.py 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' > /tmp/timing_clean.txt

# 保存完整报告
cp /tmp/timing_clean.txt /root/.openclaw/workspace/logs/latest_full_report.txt

# 提取关键字段
PRICE=$(grep "当前价格:" /tmp/timing_clean.txt | awk '{print $2}')
SIGNAL=$(grep "方向:" /tmp/timing_clean.txt | grep -v "多空信号" | head -1 | sed 's/.*方向: //' | awk '{print $1}')
CONF=$(grep "方向:" /tmp/timing_clean.txt | grep -v "多空信号" | head -1 | sed 's/.*置信度//' | sed 's/)//' | awk '{print $1}' | sed 's/(//')
BOLL=$(grep "BOLL位置:" /tmp/timing_clean.txt | awk '{print $2}')
RR=$(grep "盈亏比:" /tmp/timing_clean.txt | grep -o "1:[0-9]\.[0-9]" | head -1)
HOLD=$(grep "持仓周期:" /tmp/timing_clean.txt | sed 's/.*持仓周期: //')
POSITION=$(grep "建议仓位:" /tmp/timing_clean.txt | sed 's/.*建议仓位: //')
BUY=$(grep -c "✅" /tmp/timing_clean.txt)
SELL=$(grep -c "🔴" /tmp/timing_clean.txt)

# 写简洁状态文件
cat > /root/.openclaw/workspace/logs/latest_status.txt << EOF
股神2号 AG2606盯盘 $TIMESTAMP
===================================
信号: $SIGNAL ($CONF)
价格: $PRICE | BOLL: $BOLL
买信号: $BUY个 | 卖信号: $SELL个
盈亏比: $RR
周期: $HOLD | 仓位: $POSITION
EOF

# 写入历史（一行摘要）
echo "[$TIMESTAMP] $SIGNAL($CONF) | $PRICE | BOLL $BOLL | RR $RR | $HOLD | $POSITION" >> /root/.openclaw/workspace/logs/monitor_history.txt
