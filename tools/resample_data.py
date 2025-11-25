#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据重采样工具 - 将1s数据转换为15s或其他周期

用途：
1. 将1s K线数据聚合为15s K线
2. 支持批量转换
3. 保持数据完整性
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
from typing import Optional
from loguru import logger
import argparse


def resample_klines(
    df: pd.DataFrame,
    target_interval: str,
    time_column: str = 'stime'
) -> pd.DataFrame:
    """
    重采样K线数据

    Args:
        df: 原始K线数据(DataFrame)
        target_interval: 目标周期,如'15S','30S','1T'(1分钟),'5T'(5分钟)
        time_column: 时间列名称

    Returns:
        重采样后的DataFrame

    周期格式说明：
        'S': 秒 (如 '15S' = 15秒)
        'T' 或 'min': 分钟 (如 '1T' = 1分钟)
        'H': 小时 (如 '1H' = 1小时)
        'D': 天 (如 '1D' = 1天)
    """
    if df.empty:
        logger.warning("输入数据为空")
        return df

    # 确保时间列是datetime类型
    if not pd.api.types.is_datetime64_any_dtype(df[time_column]):
        df[time_column] = pd.to_datetime(df[time_column])

    # 设置时间索引
    df_indexed = df.set_index(time_column)

    # 定义聚合规则
    agg_dict = {
        'open': 'first',    # 开盘价：第一个
        'high': 'max',      # 最高价：最大值
        'low': 'min',       # 最低价：最小值
        'close': 'last',    # 收盘价：最后一个
        'volume': 'sum',    # 成交量：求和
    }

    # 如果有额外列，也聚合
    if 'quote_volume' in df.columns:
        agg_dict['quote_volume'] = 'sum'  # USDT成交额
    if 'trades' in df.columns:
        agg_dict['trades'] = 'sum'  # 成交笔数

    # 执行重采样
    df_resampled = df_indexed.resample(target_interval).agg(agg_dict)

    # 删除空行(如果某些时间段没有数据)
    df_resampled = df_resampled.dropna(subset=['open', 'close'])

    # 重置索引,将时间列恢复为普通列
    df_resampled = df_resampled.reset_index()

    logger.info(
        f"✓ 重采样完成: {len(df)} 条 → {len(df_resampled)} 条 "
        f"({target_interval}周期)"
    )

    return df_resampled


def resample_file(
    input_file: str,
    output_file: Optional[str] = None,
    target_interval: str = '15S',
    time_column: str = 'stime'
) -> str:
    """
    重采样文件

    Args:
        input_file: 输入文件路径(.parquet或.csv)
        output_file: 输出文件路径(可选,默认自动生成)
        target_interval: 目标周期
        time_column: 时间列名称

    Returns:
        输出文件路径
    """
    input_path = Path(input_file)

    if not input_path.exists():
        raise FileNotFoundError(f"文件不存在: {input_file}")

    logger.info(f"读取文件: {input_path.name}")

    # 读取文件
    if input_path.suffix == '.parquet':
        df = pd.read_parquet(input_path)
    elif input_path.suffix == '.csv':
        df = pd.read_csv(input_path)
    else:
        raise ValueError(f"不支持的文件格式: {input_path.suffix}")

    # 重采样
    df_resampled = resample_klines(df, target_interval, time_column)

    # 生成输出文件名
    if output_file is None:
        # 从原文件名提取信息
        # 例如: BTCUSDT_1s_2024-01-01_2024-12-31.parquet
        # 转换为: BTCUSDT_15s_2024-01-01_2024-12-31.parquet
        name_parts = input_path.stem.split('_')
        if len(name_parts) >= 2:
            # 替换周期部分
            name_parts[1] = target_interval.lower().replace('s', 's')
            output_name = '_'.join(name_parts) + input_path.suffix
        else:
            # 简单添加后缀
            output_name = f"{input_path.stem}_{target_interval}{input_path.suffix}"

        output_file = str(input_path.parent / output_name)

    output_path = Path(output_file)

    # 保存文件
    logger.info(f"保存文件: {output_path.name}")
    if output_path.suffix == '.parquet':
        df_resampled.to_parquet(output_path, index=False)
    elif output_path.suffix == '.csv':
        df_resampled.to_csv(output_path, index=False)
    else:
        raise ValueError(f"不支持的输出格式: {output_path.suffix}")

    logger.info(f"✓ 文件已保存: {output_path}")

    return str(output_path)


def batch_resample(
    data_dir: str,
    source_interval: str = '1s',
    target_interval: str = '15s',
    symbol: Optional[str] = None,
    market_type: str = 'spot',
    exchange: str = 'binance'
):
    """
    批量重采样目录下的所有文件

    Args:
        data_dir: 数据根目录
        source_interval: 源数据周期
        target_interval: 目标周期
        symbol: 交易对(可选,如果指定则只处理该交易对)
        market_type: 市场类型
        exchange: 交易所
    """
    # 构建搜索路径
    if symbol:
        search_path = Path(data_dir) / exchange / market_type / symbol
    else:
        search_path = Path(data_dir) / exchange / market_type

    if not search_path.exists():
        logger.error(f"目录不存在: {search_path}")
        return

    # 查找所有匹配的文件
    pattern = f"*_{source_interval}_*.parquet"
    files = list(search_path.rglob(pattern))

    if not files:
        logger.warning(f"未找到文件: {pattern}")
        return

    logger.info(f"找到 {len(files)} 个文件待处理")

    # 转换pandas周期格式
    # 15s → 15S, 1m → 1T, 1h → 1H
    pd_interval = target_interval.upper().replace('M', 'T').replace('MIN', 'T')
    if not any(c in pd_interval for c in ['S', 'T', 'H', 'D']):
        # 如果没有单位,假设是秒
        pd_interval = pd_interval + 'S'

    # 批量处理
    success_count = 0
    for i, file_path in enumerate(files, 1):
        try:
            logger.info(f"\n[{i}/{len(files)}] 处理: {file_path.name}")
            resample_file(str(file_path), target_interval=pd_interval)
            success_count += 1
        except Exception as e:
            logger.error(f"处理失败: {e}")
            continue

    logger.info(f"\n✓ 批量处理完成: {success_count}/{len(files)} 成功")


def main():
    """命令行使用"""
    parser = argparse.ArgumentParser(
        description='数据重采样工具 - 将1s数据转换为15s或其他周期',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 单文件转换
  python tools/resample_data.py \\
    --input data/historical/binance/spot/BTCUSDT/BTCUSDT_1s_2024-01-01_2024-12-31.parquet \\
    --target 15s

  # 批量转换目录
  python tools/resample_data.py \\
    --batch \\
    --data-dir data/historical \\
    --source 1s \\
    --target 15s \\
    --symbol BTCUSDT \\
    --market spot

支持的周期格式:
  秒级: 1s, 5s, 10s, 15s, 30s
  分钟: 1m, 3m, 5m, 15m, 30m
  小时: 1h, 2h, 4h
        """
    )

    # 单文件模式
    parser.add_argument('--input', type=str,
                        help='输入文件路径')
    parser.add_argument('--output', type=str,
                        help='输出文件路径(可选)')

    # 批量模式
    parser.add_argument('--batch', action='store_true',
                        help='批量处理模式')
    parser.add_argument('--data-dir', type=str, default='data/historical',
                        help='数据根目录')
    parser.add_argument('--source', type=str, default='1s',
                        help='源数据周期')
    parser.add_argument('--symbol', type=str,
                        help='交易对(可选)')
    parser.add_argument('--market', type=str, default='spot',
                        choices=['spot', 'futures'],
                        help='市场类型')
    parser.add_argument('--exchange', type=str, default='binance',
                        help='交易所')

    # 通用参数
    parser.add_argument('--target', type=str, default='15s',
                        help='目标周期 (如: 15s, 30s, 1m, 5m)')
    parser.add_argument('--time-column', type=str, default='stime',
                        help='时间列名称')

    args = parser.parse_args()

    # 配置日志
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=''),
        format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>"
    )

    print(f"""
╔════════════════════════════════════════════════╗
║         数据重采样工具                         ║
║         Data Resampling Tool                  ║
╚════════════════════════════════════════════════╝

目标周期: {args.target}
    """)

    try:
        if args.batch:
            # 批量模式
            if not args.data_dir:
                logger.error("批量模式需要指定 --data-dir")
                return 1

            logger.info("批量处理模式")
            batch_resample(
                data_dir=args.data_dir,
                source_interval=args.source,
                target_interval=args.target,
                symbol=args.symbol,
                market_type=args.market,
                exchange=args.exchange
            )
        else:
            # 单文件模式
            if not args.input:
                logger.error("单文件模式需要指定 --input")
                return 1

            logger.info("单文件处理模式")

            # 转换周期格式
            pd_interval = args.target.upper().replace('M', 'T').replace('MIN', 'T')
            if not any(c in pd_interval for c in ['S', 'T', 'H', 'D']):
                pd_interval = pd_interval + 'S'

            output_file = resample_file(
                input_file=args.input,
                output_file=args.output,
                target_interval=pd_interval,
                time_column=args.time_column
            )

            logger.info(f"\n✓ 处理完成: {output_file}")

        return 0

    except Exception as e:
        logger.error(f"\n✗ 错误: {e}")
        return 1


if __name__ == '__main__':
    exit(main())
