#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股神2号 - 分钟历史数据积累器
=============================
问题: rt_fut_min只返回1条实时数据
解决: 每2分钟抓取一次，保存到本地文件，积累历史分钟数据
"""

import sys
sys.path.insert(0, '/usr/local/lib/python3.12/dist-packages')

import tushare as ts
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import json

TUSHARE_TOKEN = '14d6be29b1b0b8a930fc488ceb343859b60f1357a1e1a85dcaee3712'
ts.set_token(TUSHARE_TOKEN)
PRO = ts.pro_api()

DATA_DIR = '/root/.openclaw/workspace/data/minute_data'

def ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)

def get_current_minute_data(ts_code='AG2606.SHF'):
    """获取各周期实时分钟数据"""
    result = {}
    for freq in ['1MIN', '5MIN', '15MIN', '30MIN', '60MIN']:
        try:
            df = PRO.rt_fut_min(ts_code=ts_code, freq=freq)
            if len(df) > 0:
                result[freq] = df.iloc[-1].to_dict()
        except:
            pass
    return result

def load_historical(ts_code, freq):
    """加载历史积累的分钟数据"""
    fpath = f"{DATA_DIR}/{ts_code.replace('.', '_')}_{freq}.csv"
    if os.path.exists(fpath):
        df = pd.read_csv(fpath)
        return df
    return pd.DataFrame()

def save_minute_data(ts_code='AG2606.SHF'):
    """保存当前分钟数据到历史"""
    ensure_dir()
    
    now = datetime.now()
    data = get_current_minute_data(ts_code)
    
    if not data:
        print(f"[{now.strftime('%H:%M:%S')}] 无数据")
        return
    
    for freq, row in data.items():
        fpath = f"{DATA_DIR}/{ts_code.replace('.', '_')}_{freq}.csv"
        new_row = pd.DataFrame([{
            'timestamp': now.strftime('%Y-%m-%d %H:%M:%S'),
            'ts_code': row.get('code', ts_code),
            'open': row.get('open', row.get('close', 0)),
            'high': row.get('high', row.get('close', 0)),
            'low': row.get('low', row.get('close', 0)),
            'close': row.get('close', 0),
            'vol': row.get('vol', 0),
            'amount': row.get('amount', 0),
            'oi': row.get('oi', 0),
        }])
        
        if os.path.exists(fpath):
            df_existing = pd.read_csv(fpath)
            # 去重：同一分钟只保留一条
            existing_times = set(df_existing['timestamp'].tolist())
            if now.strftime('%Y-%m-%d %H:%M:%S') not in existing_times:
                df_new = pd.concat([df_existing, new_row], ignore_index=True)
                df_new.to_csv(fpath, index=False)
        else:
            new_row.to_csv(fpath, index=False)
        
        count = len(pd.read_csv(fpath)) if os.path.exists(fpath) else 0
        print(f"[{now.strftime('%H:%M:%S')}] {freq}: {row.get('close', 0):.0f} (累计{count}条)")

def prune_old_data(ts_code='AG2606.SHF', keep_days=5):
    """清理过期数据，只保留最近N天"""
    ensure_dir()
    cutoff = (datetime.now() - timedelta(days=keep_days)).strftime('%Y-%m-%d')
    
    for freq in ['1MIN', '5MIN', '15MIN', '30MIN', '60MIN']:
        fpath = f"{DATA_DIR}/{ts_code.replace('.', '_')}_{freq}.csv"
        if os.path.exists(fpath):
            df = pd.read_csv(fpath)
            df = df[df['timestamp'] >= cutoff]
            df.to_csv(fpath, index=False)
            print(f"清理{freq}: 保留{len(df)}条")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--accumulate', action='store_true', help='抓取并保存当前分钟数据')
    parser.add_argument('--prune', action='store_true', help='清理过期数据')
    args = parser.parse_args()
    
    if args.accumulate:
        save_minute_data()
    elif args.prune:
        prune_old_data()
    else:
        # 展示已积累的数据
        ensure_dir()
        print("=" * 50)
        print("【分钟历史数据积累情况】")
        print("=" * 50)
        for freq in ['1MIN', '5MIN', '15MIN', '30MIN', '60MIN']:
            fpath = f"{DATA_DIR}/AG2606_SHF_{freq}.csv"
            if os.path.exists(fpath):
                df = pd.read_csv(fpath)
                print(f"  {freq}: {len(df)}条  {df['timestamp'].iloc[0]} ~ {df['timestamp'].iloc[-1]}")
            else:
                print(f"  {freq}: 0条 (未开始积累)")
        print("=" * 50)
