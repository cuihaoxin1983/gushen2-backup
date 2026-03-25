#!/bin/bash
cd ~/.openclaw/workspace
git add AGENTS.md SOUL.md IDENTITY.md USER.md TOOLS.md HEARTBEAT.md memory/ skills/ 2>/dev/null
git commit -m "股神2号 每日备份 $(date '+%Y-%m-%d %H:%M')" 2>/dev/null
git push origin main 2>/dev/null
