# -*- coding: utf-8 -*-
"""
虚拟货币数据加载器
从本地历史数据文件加载K线数据
"""

import pandas as pd
from pathlib import Path
from typing import Optional
from loguru import logger


def load_crypto_data(
    symbol: str,
    interval: str,
    market_type: str = 'spot',
    exchange: str = 'binance',
    data_dir: str = 'data/historical',
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> pd.DataFrame:
    """
    从本地加载虚拟货币历史数据

    Args:
        symbol: 交易对,如'BTCUSDT'
        interval: K线周期,如'1m','5m','15m','30m','1h','1d'
        market_type: 'spot'(现货) 或 'futures'(合约)
        exchange: 交易所,如'binance'或'okx'
        data_dir: 数据根目录
        start_date: 开始日期(可选),如'2024-01-01'
        end_date: 结束日期(可选),如'2024-12-31'

    Returns:
        包含OHLCV数据的DataFrame,列名标准化:
        - stime: 时间戳(datetime)
        - open, high, low, close: OHLC价格
        - volume: 成交量
    """
    # 构建数据路径
    data_path = Path(data_dir) / exchange / market_type / symbol

    if not data_path.exists():
        raise FileNotFoundError(
            f"数据目录不存在: {data_path}\n"
            f"请先使用batch_downloader.py下载数据!"
        )

    # 查找匹配的数据文件
    files = list(data_path.glob(f'*_{interval}_*.parquet'))

    if not files:
        raise FileNotFoundError(
            f"未找到{symbol}的{interval}数据\n"
            f"路径: {data_path}\n"
            f"请先下载数据: python tools/batch_downloader.py "
            f"--market {market_type} --interval {interval} --start 2024-01-01"
        )

    # 使用最新的文件(按修改时间排序)
    latest_file = sorted(files, key=lambda x: x.stat().st_mtime)[-1]
    logger.info(f"加载数据: {latest_file.name}")

    # 读取parquet文件
    df = pd.read_parquet(latest_file)

    # 标准化列名(币安格式 → 通用格式)
    df = df.rename(columns={
        'timestamp': 'stime',
        'open': 'open',
        'high': 'high',
        'low': 'low',
        'close': 'close',
        'volume': 'volume',
        'quote_volume': 'quote_volume',  # USDT成交额
        'trades': 'trades',              # 成交笔数
    })

    # 确保时间列是datetime类型
    if not pd.api.types.is_datetime64_any_dtype(df['stime']):
        df['stime'] = pd.to_datetime(df['stime'])

    # 按时间排序
    df = df.sort_values('stime').reset_index(drop=True)

    # 时间范围过滤
    if start_date:
        df = df[df['stime'] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df['stime'] <= pd.to_datetime(end_date)]

    logger.info(
        f"✓ 加载完成: {len(df)}条数据, "
        f"时间范围: {df['stime'].min()} ~ {df['stime'].max()}"
    )

    return df


def get_latest_bar(
    symbol: str,
    interval: str,
    market_type: str = 'spot',
    exchange: str = 'binance',
    data_dir: str = 'data/historical'
) -> pd.Series:
    """
    获取最新一根K线

    Returns:
        包含最新K线数据的Series
    """
    df = load_crypto_data(symbol, interval, market_type, exchange, data_dir)
    return df.iloc[-1]


def get_multi_timeframe_data(
    symbol: str,
    intervals: list,
    market_type: str = 'spot',
    exchange: str = 'binance',
    data_dir: str = 'data/historical'
) -> dict:
    """
    获取多周期数据

    Args:
        symbol: 交易对
        intervals: 周期列表,如['1m', '5m', '1h', '1d']
        market_type: 市场类型
        exchange: 交易所
        data_dir: 数据目录

    Returns:
        字典 {interval: DataFrame}
    """
    result = {}

    for interval in intervals:
        try:
            df = load_crypto_data(symbol, interval, market_type, exchange, data_dir)
            result[interval] = df
            logger.info(f"✓ 加载{interval}数据: {len(df)}条")
        except Exception as e:
            logger.warning(f"⚠ 加载{interval}数据失败: {e}")
            result[interval] = pd.DataFrame()

    return result


if __name__ == '__main__':
    # 测试代码
    logger.info("测试数据加载器...")

    try:
        # 测试加载单周期数据
        df = load_crypto_data(
            symbol='BTCUSDT',
            interval='1h',
            market_type='spot',
            exchange='binance'
        )

        print(f"\n数据预览:")
        print(df.head())
        print(f"\n数据统计:")
        print(df.describe())

        # 测试多周期数据
        multi_data = get_multi_timeframe_data(
            symbol='BTCUSDT',
            intervals=['1m', '5m', '1h', '1d'],
            market_type='spot'
        )

        print(f"\n多周期数据加载:")
        for interval, data in multi_data.items():
            print(f"{interval}: {len(data)}条")

    except Exception as e:
        logger.error(f"测试失败: {e}")
