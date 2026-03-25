# Tushare Pro 数据源配置

## Token（永久写死，不可更改）
token: 14d6be29b1b0b8a930fc488ceb343859b60f1357a1e1a85dcaee3712

## 数据接口

### 实时分钟行情（主要使用）
- **接口：** `rt_fut_min`
- **描述：** 获取全市场期货合约实时分钟数据
- **支持周期：** 1min / 5min / 15min / 30min / 60min
- **方式：** Python SDK / HTTP RESTful API / WebSocket
- **限量：** 每分钟500次，支持多合约同时提取
- **权限：** 需单独开权限

### 辅助接口
- **主力合约映射：** `fut_mapping()` — 获取主力合约代码
- **历史K线：** `fut_daily()` — 期货日线数据

### rt_fut_min 输入参数
| 名称 | 类型 | 必选 | 描述 |
|------|------|------|------|
| ts_code | str | Y | 合约代码，支持多合约逗号分隔，如 `AG2606.SHF` |
| freq | str | Y | 分钟频度：`1MIN` / `5MIN` / `15MIN` / `30MIN` / `60MIN` |

### rt_fut_min 输出字段（部分）
| 字段 | 描述 |
|------|------|
| ts_code | 合约代码 |
| freq | 周期 |
| open | 开盘价 |
| high | 最高价 |
| low | 最低价 |
| close | 收盘价 |
| vol | 成交量 |
| amount | 成交额 |
| trade_time | 交易时间 |

### 调用示例
```python
import tushare as ts
ts.set_token('14d6be29b1b0b8a930fc488ceb343859b60f1357a1e1a85dcaee3712')
pro = ts.pro_api()

# 获取AG白银期货实时5分钟数据
df = pro.rt_fut_min(ts_code='AG2606.SHF', freq='5MIN')
print(df)
```

## ⚠️ 数据源锁定说明
本配置为股神2号唯一数据源，
所有期货和股票数据获取均通过Tushare Pro，
不允许切换到其他数据平台。

## 配置说明
本配置为股神2号专用数据源，
所有期货和股票数据获取均通过此接口，
不允许切换到其他数据平台。

## 最后更新
2026-03-25
