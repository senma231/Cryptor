"""
批量下载工具 - 支持现货和合约数据
可自动获取所有交易对并批量下载
"""

import warnings
warnings.filterwarnings('ignore', category=Warning, module='urllib3')

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import requests
import pandas as pd
from datetime import datetime, timedelta
import time
from typing import List, Dict, Optional
from loguru import logger
import json


def download_klines_binance(
    base_url: str,
    symbol: str,
    interval: str,
    start_time: str,
    end_time: Optional[str] = None,
    limit: int = 1000,
    market_type: str = 'spot'
) -> pd.DataFrame:
    """
    下载币安K线数据(内部函数)

    Args:
        market_type: 'spot' 或 'futures'
    """
    start_ts = int(datetime.strptime(start_time, '%Y-%m-%d').timestamp() * 1000)
    if end_time:
        end_ts = int(datetime.strptime(end_time, '%Y-%m-%d').timestamp() * 1000)
    else:
        end_ts = int(datetime.now().timestamp() * 1000)

    all_data = []
    current_ts = start_ts

    while current_ts < end_ts:
        # 根据市场类型选择正确的API路径
        if market_type == 'futures':
            url = f"{base_url}/fapi/v1/klines"  # 合约API
        else:
            url = f"{base_url}/api/v3/klines"   # 现货API
        params = {
            'symbol': symbol,
            'interval': interval,
            'startTime': current_ts,
            'endTime': end_ts,
            'limit': limit
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not data:
                break

            all_data.extend(data)
            current_ts = data[-1][0] + 1
            time.sleep(0.1)

        except Exception as e:
            logger.error(f"请求失败: {e}")
            break

    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
        'taker_buy_quote', 'ignore'
    ])

    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')

    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)

    return df


class BatchDownloader:
    """批量数据下载器"""

    def __init__(self, exchange: str = 'binance'):
        """
        初始化批量下载器

        Args:
            exchange: 交易所名称 ('binance' 或 'okx')
        """
        self.exchange = exchange.lower()
        self.base_url = self._get_base_url()
        self.data_dir = Path(f'data/historical/{self.exchange}')
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 请求限制(避免被封)
        self.request_delay = 0.5  # 每次请求间隔(秒)
        self.retry_times = 3      # 失败重试次数

    def _get_base_url(self) -> str:
        """获取交易所API基础URL"""
        urls = {
            'binance': 'https://api.binance.com',
            'binance_futures': 'https://fapi.binance.com',  # 合约
            'okx': 'https://www.okx.com'
        }
        return urls.get(self.exchange, urls['binance'])

    def get_spot_symbols(self, quote_asset: str = 'USDT') -> List[str]:
        """
        获取所有现货交易对

        Args:
            quote_asset: 计价货币,如 'USDT', 'BTC', 'ETH'

        Returns:
            交易对列表
        """
        logger.info(f"获取{self.exchange.upper()}所有{quote_asset}现货交易对...")

        if self.exchange == 'binance':
            url = f"{self.base_url}/api/v3/exchangeInfo"

            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()

                # 筛选活跃的USDT交易对
                symbols = [
                    s['symbol']
                    for s in data['symbols']
                    if s['quoteAsset'] == quote_asset
                    and s['status'] == 'TRADING'
                    and s['symbol'].endswith(quote_asset)
                ]

                logger.info(f"✓ 找到 {len(symbols)} 个{quote_asset}现货交易对")
                return sorted(symbols)

            except Exception as e:
                logger.error(f"获取交易对失败: {e}")
                return []

        return []

    def get_futures_symbols(self, quote_asset: str = 'USDT') -> List[str]:
        """
        获取所有永续合约交易对

        Args:
            quote_asset: 计价货币

        Returns:
            合约交易对列表
        """
        logger.info(f"获取{self.exchange.upper()}所有{quote_asset}永续合约...")

        if self.exchange == 'binance':
            url = "https://fapi.binance.com/fapi/v1/exchangeInfo"

            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()

                # 筛选永续合约
                symbols = [
                    s['symbol']
                    for s in data['symbols']
                    if s['quoteAsset'] == quote_asset
                    and s['contractType'] == 'PERPETUAL'
                    and s['status'] == 'TRADING'
                ]

                logger.info(f"✓ 找到 {len(symbols)} 个永续合约")
                return sorted(symbols)

            except Exception as e:
                logger.error(f"获取合约失败: {e}")
                return []

        return []

    def filter_by_volume(
        self,
        symbols: List[str],
        market_type: str = 'spot',
        min_volume_usdt: float = 1000000
    ) -> List[str]:
        """
        按24小时成交量筛选交易对

        Args:
            symbols: 交易对列表
            market_type: 'spot' 或 'futures'
            min_volume_usdt: 最小24h成交量(USDT)

        Returns:
            筛选后的交易对列表
        """
        logger.info(f"筛选成交量 >{min_volume_usdt:,.0f} USDT 的交易对...")

        if self.exchange == 'binance':
            if market_type == 'spot':
                url = f"{self.base_url}/api/v3/ticker/24hr"
            else:
                url = "https://fapi.binance.com/fapi/v1/ticker/24hr"

            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()

                # 创建成交量字典
                volume_map = {
                    item['symbol']: float(item['quoteVolume'])
                    for item in data
                }

                # 筛选
                filtered = [
                    s for s in symbols
                    if volume_map.get(s, 0) >= min_volume_usdt
                ]

                logger.info(f"✓ 筛选出 {len(filtered)} 个高流动性交易对")
                return sorted(filtered, key=lambda x: volume_map.get(x, 0), reverse=True)

            except Exception as e:
                logger.error(f"获取成交量失败: {e}")
                return symbols

        return symbols

    def batch_download(
        self,
        symbols: List[str],
        interval: str,
        start_time: str,
        end_time: Optional[str] = None,
        market_type: str = 'spot',
        max_symbols: Optional[int] = None,
        save_format: str = 'parquet'
    ) -> Dict[str, str]:
        """
        批量下载多个交易对

        Args:
            symbols: 交易对列表
            interval: K线周期
            start_time: 开始时间
            end_time: 结束时间
            market_type: 'spot' 或 'futures'
            max_symbols: 最大下载数量(None=全部)
            save_format: 保存格式

        Returns:
            下载结果字典 {symbol: filepath}
        """
        if max_symbols:
            symbols = symbols[:max_symbols]

        logger.info(f"开始批量下载 {len(symbols)} 个交易对")
        logger.info(f"市场类型: {market_type}")
        logger.info(f"时间范围: {start_time} ~ {end_time or '今天'}")

        results = {}
        failed = []

        # 根据市场类型选择API
        if market_type == 'futures':
            base_url = 'https://fapi.binance.com'
        else:
            base_url = self.base_url

        for i, symbol in enumerate(symbols, 1):
            logger.info(f"\n[{i}/{len(symbols)}] 下载 {symbol}...")

            # 重试机制
            for attempt in range(self.retry_times):
                try:
                    # 下载数据
                    df = download_klines_binance(
                        base_url, symbol, interval, start_time, end_time,
                        limit=1000, market_type=market_type
                    )

                    if df.empty:
                        logger.warning(f"{symbol} 无数据")
                        failed.append(symbol)
                        break

                    # 保存文件
                    subdir = f"{market_type}/{symbol}"
                    filename = f"{symbol}_{interval}_{start_time}_{end_time or 'now'}.{save_format}"
                    filepath = self.data_dir / subdir / filename
                    filepath.parent.mkdir(parents=True, exist_ok=True)

                    if save_format == 'parquet':
                        df.to_parquet(filepath, index=False)
                    else:
                        df.to_csv(filepath, index=False)

                    results[symbol] = str(filepath)
                    logger.info(f"✓ {symbol} 完成 ({len(df)}条数据, {filepath.stat().st_size/1024:.1f}KB)")
                    break

                except Exception as e:
                    if attempt < self.retry_times - 1:
                        logger.warning(f"重试 {attempt + 1}/{self.retry_times}...")
                        time.sleep(2)
                    else:
                        logger.error(f"✗ {symbol} 失败: {e}")
                        failed.append(symbol)

            # 避免请求过快
            time.sleep(self.request_delay)

        # 总结
        logger.info(f"\n{'='*60}")
        logger.info(f"批量下载完成!")
        logger.info(f"成功: {len(results)} 个")
        logger.info(f"失败: {len(failed)} 个")

        if failed:
            logger.warning(f"失败列表: {', '.join(failed[:10])}{'...' if len(failed) > 10 else ''}")

        # 保存下载记录
        record_file = self.data_dir / f"download_record_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(record_file, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'exchange': self.exchange,
                'market_type': market_type,
                'interval': interval,
                'start_time': start_time,
                'end_time': end_time,
                'total': len(symbols),
                'success': len(results),
                'failed': failed,
                'results': results
            }, f, indent=2)

        logger.info(f"下载记录已保存: {record_file}")

        return results


def main():
    """命令行使用"""
    import argparse

    parser = argparse.ArgumentParser(description='批量下载交易所数据')
    parser.add_argument('--exchange', type=str, default='binance',
                        choices=['binance', 'okx'])
    parser.add_argument('--market', type=str, default='spot',
                        choices=['spot', 'futures'],
                        help='市场类型: spot=现货, futures=合约')
    parser.add_argument('--interval', type=str, default='1h',
                        help='K线周期 (支持: 1s,1m,3m,5m,15m,30m,1h,2h,4h,6h,8h,12h,1d,3d,1w,1M)')
    parser.add_argument('--start', type=str, required=True,
                        help='开始日期 YYYY-MM-DD')
    parser.add_argument('--end', type=str, default=None,
                        help='结束日期')
    parser.add_argument('--quote', type=str, default='USDT',
                        help='计价货币')
    parser.add_argument('--min-volume', type=float, default=1000000,
                        help='最小24h成交量(USDT)')
    parser.add_argument('--max-count', type=int, default=None,
                        help='最大下载数量')
    parser.add_argument('--top-n', type=int, default=None,
                        help='只下载前N个(按成交量)')
    parser.add_argument('--symbols', type=str, default=None,
                        help='指定交易对,多个用逗号分隔(如: BTCUSDT,ETHUSDT)')

    args = parser.parse_args()

    # 配置日志
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=''),
        format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>"
    )

    print(f"""
╔════════════════════════════════════════════════╗
║         批量数据下载工具                       ║
║         Batch Data Downloader                 ║
╚════════════════════════════════════════════════╝

交易所: {args.exchange.upper()}
市  场: {'现货' if args.market == 'spot' else '合约'}
周  期: {args.interval}
时间段: {args.start} ~ {args.end or '今天'}
    """)

    try:
        downloader = BatchDownloader(args.exchange)

        # 获取交易对列表
        if args.symbols:
            # 使用用户指定的交易对
            symbols = [s.strip().upper() for s in args.symbols.split(',')]
            logger.info(f"使用指定交易对: {', '.join(symbols)}")
        else:
            # 自动获取交易对
            if args.market == 'spot':
                symbols = downloader.get_spot_symbols(args.quote)
            else:
                symbols = downloader.get_futures_symbols(args.quote)

            if not symbols:
                logger.error("未找到任何交易对!")
                return 1

            # 按成交量筛选
            symbols = downloader.filter_by_volume(
                symbols,
                args.market,
                args.min_volume
            )

        # 限制数量
        if args.top_n:
            symbols = symbols[:args.top_n]
            logger.info(f"只下载前 {args.top_n} 个交易对")

        if args.max_count:
            symbols = symbols[:args.max_count]

        # 确认
        print(f"\n将下载 {len(symbols)} 个交易对")
        print(f"预计耗时: {len(symbols) * 2} 秒")
        confirm = input("\n确认开始下载? (y/n): ")

        if confirm.lower() != 'y':
            print("已取消")
            return 0

        # 批量下载
        results = downloader.batch_download(
            symbols,
            args.interval,
            args.start,
            args.end,
            args.market,
            args.max_count
        )

        print(f"\n✅ 批量下载完成!")
        print(f"成功: {len(results)} 个交易对")
        print(f"数据位置: data/historical/{args.exchange}/{args.market}/")

    except KeyboardInterrupt:
        print("\n\n用户中断下载")
        return 0
    except Exception as e:
        logger.exception(f"下载失败: {e}")
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
