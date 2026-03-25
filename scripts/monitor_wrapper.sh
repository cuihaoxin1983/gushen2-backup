#!/bin/bash
# 股神2号盯盘脚本 - 被cron调用
cd /root/.openclaw/workspace
python3 trading_advisor.py 2>&1 | tail -25
