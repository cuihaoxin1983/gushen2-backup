#!/usr/bin/env python3
"""
tushare_pro_api.py
股神2号 专用 Tushare Pro 数据接口
数据源: Tushare Pro (rt_fut_min 实时分钟行情)
"""

import requests
import json
import pandas as pd
from typing import Optional, List

# ============================================================
# 配置（写死，不允许修改）
# ============================================================
TUSHARE_TOKEN = "14d6be29b1b0b8a930fc488ceb343859b60f1357a1e1a85dcaee3712"
TUSHARE_API_URL = "http://api.tushare.pro"

# ============================================================
# 核心API调用函数
# ============================================================

def call_api(api_name: str, params: dict, fields: str = "") -> pd.DataFrame:
    """
    通用Tushare Pro API调用
    
    Args:
        api_name: 接口名称，如 "rt_fut_min"
        params: 输入参数 dict
        fields: 输出字段列表，逗号分隔
    
    Returns:
        pd.DataFrame
    """
    payload = {
        "api_name": api_name,
        "token": TUSHARE_TOKEN,
        "params": params,
        "fields": fields
    }
    
    try:
        resp = requests.post(TUSHARE_API_URL, json=payload, timeout=30)
        data = resp.json()
        
        if data["code"] != 0:
            print(f"API调用失败: {data['msg']}")
            return pd.DataFrame()
        
        cols = data["data"]["fields"]
        rows = data["data"]["items"]
        
        return pd.DataFrame(rows, columns=cols)
    
    except Exception as e:
        print(f"请求异常: {e}")
        return pd.DataFrame()


# ============================================================
# 期货数据接口
# ============================================================

def get_fut_min(
    ts_code: str,
    freq: str = "5MIN",
    asset: str = "FT"
) -> pd.DataFrame:
    """
    获取期货实时分钟数据 (rt_fut_min)
    
    Args:
        ts_code: 合约代码，如 "AG2606.SHF"
        freq: 分钟周期 "1MIN" / "5MIN" / "15MIN" / "30MIN" / "60MIN"
        asset: 资产类型，默认 "FT" (期货)
    
    Returns:
        pd.DataFrame: 包含 open/high/low/close/vol/amount/trade_time 等
    """
    params = {
        "ts_code": ts_code,
        "freq": freq
    }
    
    fields = "ts_code,freq,open,high,low,close,vol,amount,trade_time"
    
    return call_api("rt_fut_min", params, fields)


def get_fut_mapping() -> pd.DataFrame:
    """
    获取期货主力合约映射
    """
    return call_api("fut_mapping", {}, "ts_code,trade_date,mapping_ts_code")


def get_fut_daily(
    ts_code: str,
    start_date: str = "",
    end_date: str = "",
    exchange: str = ""
) -> pd.DataFrame:
    """
    获取期货日线数据 (fut_daily)
    """
    params = {
        "ts_code": ts_code,
    }
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    
    fields = "ts_code,trade_date,open,high,low,close,vol,amount,oi,deliverable"
    
    return call_api("fut_daily", params, fields)


# ============================================================
# 测试
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("Tushare Pro API 测试")
    print("=" * 50)
    
    # 测试 rt_fut_min（AG白银期货5分钟）
    print("\n[测试] AG2606.SHF 5分钟行情:")
    df = get_fut_min("AG2606.SHF", freq="5MIN")
    if not df.empty:
        print(df.tail())
    else:
        print("获取数据失败，请检查权限或网络")
