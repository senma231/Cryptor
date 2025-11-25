#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立的下载工作进程 - 避免GUI线程问题
"""

import sys
import json
from tools.data_downloader import DataDownloader


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "message": "缺少参数"}))
        sys.exit(1)
    
    try:
        # 解析参数
        params = json.loads(sys.argv[1])
        exchange = params['exchange']
        symbol = params['symbol']
        market = params['market']
        interval = params['interval']
        start_date = params['start_date']
        
        # 创建下载器
        downloader = DataDownloader(exchange=exchange)
        
        # 下载数据
        df = None
        if exchange == 'binance':
            df = downloader.download_klines_binance(
                symbol=symbol,
                interval=interval,
                start_time=start_date,
                end_time=None
            )
        elif exchange == 'okx':
            # OKX需要横杠格式
            symbol_okx = symbol
            if '-' not in symbol_okx:
                symbol_okx = symbol_okx.replace('USDT', '-USDT')
            df = downloader.download_klines_okx(
                symbol=symbol_okx,
                interval=interval,
                start_time=start_date
            )
        elif exchange == 'htx':
            df = downloader.download_klines_htx(
                symbol=symbol,
                interval=interval,
                start_time=start_date,
                end_time=None
            )
        else:
            print(json.dumps({"success": False, "message": f"不支持的交易所: {exchange}"}))
            sys.exit(1)
        
        if df is None or df.empty:
            print(json.dumps({"success": False, "message": "未下载到数据"}))
            sys.exit(1)

        # 保存数据 - 使用与crypto_data_loader一致的目录结构
        # 路径格式: data/historical/{exchange}/{market}/{symbol}/
        from datetime import datetime
        symbol_dir = downloader.data_dir / market / symbol
        symbol_dir.mkdir(parents=True, exist_ok=True)

        # 文件名包含时间戳
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{symbol}_{interval}_{timestamp}.parquet"
        filepath = symbol_dir / filename

        # 保存为parquet格式
        df.to_parquet(str(filepath), index=False)

        # 返回成功
        result = {
            "success": True,
            "message": f"成功下载 {len(df)} 条数据",
            "filepath": str(filepath),
            "count": len(df)
        }
        print(json.dumps(result))
        sys.exit(0)
        
    except Exception as e:
        import traceback
        result = {
            "success": False,
            "message": f"下载失败: {str(e)}",
            "traceback": traceback.format_exc()
        }
        print(json.dumps(result))
        sys.exit(1)


if __name__ == '__main__':
    main()

