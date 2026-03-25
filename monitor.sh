#!/bin/bash
# 股神2号盯盘脚本 - 每5分钟运行一次
cd /root/.openclaw/workspace

# 运行选时分析
python3 timing_analysis.py > /tmp/timing_latest.txt 2>&1

# 提取关键信息
SIGNAL=$(grep "方向:" /tmp/timing_latest.txt | head -1)
PRICE=$(grep "当前价格:" /tmp/timing_latest.txt | head -1 | awk '{print $3}')
BOLL=$(grep "BOLL位置:" /tmp/timing_latest.txt | head -1 | awk '{print $3}')
ATR=$(grep "ATR波动:" /tmp/timing_latest.txt | head -1 | awk '{print $3}')
RR=$(grep "盈亏比评价:" /tmp/timing_latest.txt | head -1)
POSITION=$(grep "建议仓位:" /tmp/timing_latest.txt | head -1)
ADVICE=$(grep "建议持仓周期:" /tmp/timing_latest.txt | head -1)

# 保存到监控文件
cat > /root/.openclaw/workspace/logs/latest_signal.txt << EOF
AG2606盯盘信号 $(date '+%Y-%m-%d %H:%M')
=========================================
$SIGNAL
$PRICE
$BOLL
$ATR
$RR
$POSITION
$ADVICE
EOF

echo "$(date '+%H:%M:%S') 盯盘完成" >> /root/.openclaw/workspace/logs/monitor.log
