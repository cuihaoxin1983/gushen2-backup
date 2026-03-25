#!/usr/bin/env python3
import sys
sys.path.insert(0, '/usr/local/lib/python3.12/dist-packages')

import tushare as ts

# 设置token（永久写死）
ts.set_token('14d6be29b1b0b8a930fc488ceb343859b60f1357a1e1a85dcaee3712')
pro = ts.pro_api()

print("=" * 60)
print("【股神2号】Tushare Pro 数据源测试")
print("=" * 60)

# 测试1：实时分钟行情
print("\n📊 实时5分钟行情 (AG2606):")
df1 = pro.rt_fut_min(ts_code='AG2606.SHF', freq='5MIN')
print(df1.tail(3).to_string())
print(f"✅ 实时数据 OK — 共 {len(df1)} 条")

# 测试2：历史日线数据
print("\n📈 历史日线数据 (AG2606):")
df2 = pro.fut_daily(ts_code='AG2606.SHF', start_date='20260301', end_date='20260325')
print(df2.tail(5).to_string())
print(f"✅ 历史数据 OK — 共 {len(df2)} 条")

print("\n" + "=" * 60)
print("数据源验证通过")
print("=" * 60)
