"""
交易所历史数据下载工具
支持币安(Binance)和OKX交易所
无需API密钥,使用公开接口
"""

import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional
import time

# 尝试导入loguru，如果失败则使用print
try:
    from loguru import logger
except:
    # 创建一个简单的logger替代品
    class SimpleLogger:
        def info(self, msg): print(f"[INFO] {msg}")
        def debug(self, msg): print(f"[DEBUG] {msg}")
        def warning(self, msg): print(f"[WARNING] {msg}")
        def error(self, msg): print(f"[ERROR] {msg}")
        def success(self, msg): print(f"[SUCCESS] {msg}")
    logger = SimpleLogger()


class DataDownloader:
    """历史数据下载器"""

    def __init__(self, exchange: str = 'binance'):
        """
        初始化下载器

        Args:
            exchange: 交易所名称 ('binance', 'okx', 或 'htx')
        """
        self.exchange = exchange.lower()
        self.base_url = self._get_base_url()
        self.data_dir = Path(f'data/historical/{self.exchange}')
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _get_base_url(self) -> str:
        """获取交易所API基础URL"""
        urls = {
            'binance': 'https://api.binance.com',
            'okx': 'https://www.okx.com'
        }
        return urls.get(self.exchange, urls['binance'])

    def download_klines_binance(
        self,
        symbol: str,
        interval: str,
        start_time: str,
        end_time: Optional[str] = None,
        limit: int = 1000
    ) -> pd.DataFrame:
        """
        下载币安K线数据

        Args:
            symbol: 交易对,如 'BTCUSDT'
            interval: K线周期
                - 1m, 3m, 5m, 15m, 30m (分钟)
                - 1h, 2h, 4h, 6h, 8h, 12h (小时)
                - 1d, 3d (天)
                - 1w (周)
                - 1M (月)
            start_time: 开始时间 'YYYY-MM-DD'
            end_time: 结束时间 'YYYY-MM-DD' (默认为今天)
            limit: 单次请求限制(最大1000)

        Returns:
            包含K线数据的DataFrame
        """
        # 转换时间为时间戳
        start_ts = int(datetime.strptime(start_time, '%Y-%m-%d').timestamp() * 1000)
        if end_time:
            end_ts = int(datetime.strptime(end_time, '%Y-%m-%d').timestamp() * 1000)
        else:
            end_ts = int(datetime.now().timestamp() * 1000)

        all_data = []
        current_ts = start_ts

        logger.info(f"开始下载 {symbol} {interval} K线数据")
        logger.info(f"时间范围: {start_time} ~ {end_time or '今天'}")

        while current_ts < end_ts:
            # 构造请求URL
            url = f"{self.base_url}/api/v3/klines"
            params = {
                'symbol': symbol,
                'interval': interval,
                'startTime': current_ts,
                'endTime': end_ts,
                'limit': limit
            }

            # 添加重试机制
            max_retries = 3
            retry_count = 0
            success = False

            while retry_count < max_retries and not success:
                try:
                    response = requests.get(url, params=params, timeout=30)  # 增加超时时间到30秒
                    response.raise_for_status()
                    data = response.json()

                    if not data:
                        break

                    all_data.extend(data)
                    current_ts = data[-1][0] + 1  # 下一批从最后一条的下一毫秒开始

                    logger.info(f"已下载 {len(all_data)} 条数据...")
                    success = True

                    # 避免请求过快
                    time.sleep(0.1)

                except requests.exceptions.RequestException as e:
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.warning(f"请求失败，正在重试 ({retry_count}/{max_retries}): {e}")
                        time.sleep(2)  # 等待2秒后重试
                    else:
                        logger.error(f"请求失败，已达到最大重试次数: {e}")
                        break

            if not success:
                break

        # 转换为DataFrame
        if not all_data:
            logger.warning("未下载到任何数据")
            return pd.DataFrame()

        df = pd.DataFrame(all_data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])

        # 数据类型转换
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')

        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)

        logger.info(f"✓ 成功下载 {len(df)} 条K线数据")
        return df

    def download_klines_okx(
        self,
        symbol: str,
        interval: str,
        start_time: str,
        end_time: Optional[str] = None
    ) -> pd.DataFrame:
        """
        下载OKX K线数据

        Args:
            symbol: 交易对,如 'BTC-USDT'
            interval: K线周期
                - 1m, 3m, 5m, 15m, 30m (分钟)
                - 1H, 2H, 4H (小时,注意大写)
                - 1D, 1W, 1M (天/周/月,注意大写)
            start_time: 开始时间 'YYYY-MM-DD'
            end_time: 结束时间 'YYYY-MM-DD'

        Returns:
            包含K线数据的DataFrame
        """
        # 转换interval格式 (1h -> 1H, 1d -> 1D)
        interval_map = {
            '1m': '1m', '3m': '3m', '5m': '5m', '15m': '15m', '30m': '30m',
            '1h': '1H', '2h': '2H', '4h': '4H', '6h': '6H', '12h': '12H',
            '1d': '1D', '1w': '1W', '1M': '1M'
        }
        okx_interval = interval_map.get(interval, interval)

        # 转换时间为时间戳(毫秒)
        start_ts = int(datetime.strptime(start_time, '%Y-%m-%d').timestamp() * 1000)
        if end_time:
            end_ts = int(datetime.strptime(end_time, '%Y-%m-%d').timestamp() * 1000)
        else:
            end_ts = int(datetime.now().timestamp() * 1000)

        all_data = []

        logger.info(f"开始下载 {symbol} {okx_interval} K线数据")
        logger.info(f"时间范围: {start_time} ({start_ts}) ~ {end_time or '今天'} ({end_ts})")

        # OKX API的正确理解（经过大量实际测试验证）：
        # 官方文档说明：
        # - after: "Pagination of data to return records earlier than the requested ts"
        # - before: "Pagination of data to return records newer than the requested ts"
        #
        # 实际行为（非常反直觉！）：
        # - 不带参数：返回最新的100条数据（降序：从新到旧）
        # - before=T：返回最新的100条数据，但**排除**时间戳>=T的数据（降序）
        # - after=T：返回早于T的100条数据（降序：从新到旧）
        #
        # before参数的问题：
        # - before=T只是过滤掉>=T的数据，不改变起始点
        # - 每次请求都从最新时间开始，导致大量重复数据
        # - 无法用于正常的分页下载
        #
        # 正确策略：使用after参数从最新往旧的方向下载
        # 1. 第一次请求使用after=end_ts+1，获取end_ts及之前的100条数据
        # 2. 后续请求使用after=oldest_ts，继续往更旧的方向获取
        # 3. 停止条件：当获取到的最旧时间戳 <= start_ts时停止

        url = f"{self.base_url}/api/v5/market/history-candles"
        after_ts = end_ts + 1  # after参数返回早于指定时间戳的数据
        max_iterations = 100
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            params = {
                'instId': symbol,
                'bar': okx_interval,
                'limit': 100,
                'after': after_ts
            }

            # 添加重试机制
            max_retries = 3
            retry_count = 0
            success = False

            while retry_count < max_retries and not success:
                try:
                    response = requests.get(url, params=params, timeout=30)
                    response.raise_for_status()
                    result = response.json()

                    if result['code'] != '0':
                        logger.error(f"API错误: {result['msg']}")
                        break

                    data = result['data']
                    success = True

                except requests.exceptions.RequestException as e:
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.warning(f"请求失败，正在重试 ({retry_count}/{max_retries}): {e}")
                        time.sleep(2)
                    else:
                        logger.error(f"请求失败，已达到最大重试次数: {e}")
                        break

            if not success:
                break

            # 继续处理data
            if not data:
                logger.info("没有更多数据，停止下载")
                break

            # OKX使用after参数时，返回的数据按时间戳降序排列（从新到旧）
            newest_ts = int(data[0][0])   # 最新的数据（第一条）
            oldest_ts = int(data[-1][0])  # 最旧的数据（最后一条）

            logger.debug(f"当前批次: newest={datetime.fromtimestamp(newest_ts/1000)}, oldest={datetime.fromtimestamp(oldest_ts/1000)}")
            logger.debug(f"目标范围: start={datetime.fromtimestamp(start_ts/1000)}, end={datetime.fromtimestamp(end_ts/1000)}")

            # 过滤时间范围内的数据
            filtered_data = [d for d in data if start_ts <= int(d[0]) <= end_ts]

            logger.debug(f"当前批次数据: {len(data)} 条, 过滤后: {len(filtered_data)} 条")

            if filtered_data:
                all_data.extend(filtered_data)
                logger.info(f"已下载 {len(all_data)} 条数据...")

            # 停止条件：如果最旧的数据已经早于或等于开始时间，说明已经覆盖了整个时间范围
            if oldest_ts <= start_ts:
                logger.info(f"已覆盖开始时间，停止下载")
                break

            # 更新after参数为当前批次最旧的时间戳
            # 下一次请求将返回早于oldest_ts的数据
            after_ts = oldest_ts

            time.sleep(0.2)

        if not all_data:
            logger.warning("未下载到任何数据")
            return pd.DataFrame()

        # 转换为DataFrame
        df = pd.DataFrame(all_data, columns=[
            'timestamp', 'open', 'high', 'low', 'close',
            'volume', 'volume_currency', 'volume_currency_quote', 'confirm'
        ])

        df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)

        df = df.sort_values('timestamp').reset_index(drop=True)

        logger.info(f"✓ 成功下载 {len(df)} 条K线数据")
        return df

    def download_klines_htx(
        self,
        symbol: str,
        interval: str,
        start_time: str,
        end_time: Optional[str] = None
    ) -> pd.DataFrame:
        """
        下载HTX/火币 K线数据

        Args:
            symbol: 交易对,如 'BTCUSDT' (会自动转换为小写)
            interval: K线周期
                - 1m, 5m, 15m, 30m (分钟)
                - 1h, 4h (小时)
                - 1d, 1w, 1M (天/周/月)
            start_time: 开始时间 'YYYY-MM-DD'
            end_time: 结束时间 'YYYY-MM-DD' (可选,默认今天)

        Returns:
            包含K线数据的DataFrame
        """
        from tools.exchange_factory import HTXExchange

        logger.info(f"开始下载HTX K线数据: {symbol} {interval}")

        # HTX使用小写符号
        symbol_lower = symbol.lower()

        # 转换时间格式
        start_ts = int(pd.Timestamp(start_time).timestamp())
        if end_time:
            end_ts = int(pd.Timestamp(end_time).timestamp())
        else:
            end_ts = int(pd.Timestamp.now().timestamp())

        # 创建HTX交易所实例
        htx = HTXExchange(market_type='spot')

        # HTX每次最多返回2000条数据
        all_data = []
        current_ts = start_ts

        # 计算每根K线的时间间隔（秒）
        interval_seconds = {
            '1m': 60, '5m': 300, '15m': 900, '30m': 1800,
            '1h': 3600, '4h': 14400,
            '1d': 86400, '1w': 604800, '1M': 2592000
        }.get(interval, 3600)

        while current_ts < end_ts:
            # 计算本次请求的数量
            remaining_bars = (end_ts - current_ts) // interval_seconds
            limit = min(2000, remaining_bars + 1)

            if limit <= 0:
                break

            logger.info(f"  下载 {pd.Timestamp(current_ts, unit='s')} 开始的 {limit} 条数据...")

            # 获取K线数据
            df = htx.get_klines(symbol_lower, interval, limit=limit)

            if df is None or df.empty:
                logger.warning(f"  未获取到数据")
                break

            # 过滤时间范围
            df = df[df['timestamp'] >= pd.Timestamp(current_ts, unit='s')]
            df = df[df['timestamp'] <= pd.Timestamp(end_ts, unit='s')]

            if not df.empty:
                all_data.append(df)
                # 更新当前时间戳到最后一条数据的时间
                current_ts = int(df['timestamp'].max().timestamp()) + interval_seconds
                logger.info(f"  ✓ 获取 {len(df)} 条数据")
            else:
                break

            # 避免请求过快
            import time
            time.sleep(0.2)

        if not all_data:
            logger.error("未获取到任何数据")
            return pd.DataFrame()

        # 合并所有数据
        df = pd.concat(all_data, ignore_index=True)
        df = df.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)

        logger.info(f"✓ 成功下载 {len(df)} 条K线数据")
        return df

    def download_and_save(
        self,
        symbol: str,
        interval: str,
        start_time: str,
        end_time: Optional[str] = None,
        format: str = 'parquet'
    ) -> str:
        """
        下载并保存数据到本地

        Args:
            symbol: 交易对
            interval: K线周期
            start_time: 开始时间
            end_time: 结束时间
            format: 保存格式 ('parquet', 'csv')

        Returns:
            保存的文件路径
        """
        # 根据交易所下载数据
        if self.exchange == 'binance':
            df = self.download_klines_binance(symbol, interval, start_time, end_time)
        elif self.exchange == 'okx':
            # OKX使用横杠分隔
            symbol_okx = symbol.replace('USDT', '-USDT').replace('BTC', 'BTC-')
            df = self.download_klines_okx(symbol_okx, interval, start_time, end_time)
        elif self.exchange == 'htx':
            df = self.download_klines_htx(symbol, interval, start_time, end_time)
        else:
            raise ValueError(f"不支持的交易所: {self.exchange}")

        if df.empty:
            logger.error("数据为空,取消保存")
            return ""

        # 构造文件名
        filename = f"{symbol}_{interval}_{start_time}_{end_time or 'now'}.{format}"
        filepath = self.data_dir / symbol / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # 保存文件
        if format == 'parquet':
            df.to_parquet(filepath, index=False)
        elif format == 'csv':
            df.to_csv(filepath, index=False)
        else:
            raise ValueError(f"不支持的格式: {format}")

        logger.info(f"✓ 数据已保存至: {filepath}")
        logger.info(f"  数据条数: {len(df)}")
        logger.info(f"  时间范围: {df['timestamp'].min()} ~ {df['timestamp'].max()}")
        logger.info(f"  文件大小: {filepath.stat().st_size / 1024:.2f} KB")

        return str(filepath)

    def get_popular_symbols(self) -> List[str]:
        """获取热门交易对列表"""
        if self.exchange == 'binance':
            return [
                'BTCUSDT', 'ETHUSDT', 'BNBUSDT',
                'SOLUSDT', 'XRPUSDT', 'ADAUSDT',
                'DOGEUSDT', 'AVAXUSDT', 'MATICUSDT', 'DOTUSDT'
            ]
        elif self.exchange == 'okx':
            return [
                'BTC-USDT', 'ETH-USDT', 'SOL-USDT',
                'XRP-USDT', 'ADA-USDT', 'DOGE-USDT'
            ]
        elif self.exchange == 'htx':
            return [
                'BTCUSDT', 'ETHUSDT', 'SOLUSDT',
                'XRPUSDT', 'ADAUSDT', 'DOGEUSDT'
            ]
        return []


def main():
    """命令行使用示例"""
    import argparse

    parser = argparse.ArgumentParser(description='交易所历史数据下载工具')
    parser.add_argument('--exchange', type=str, default='binance',
                        choices=['binance', 'okx', 'htx'], help='交易所')
    parser.add_argument('--symbol', type=str, required=True,
                        help='交易对,如 BTCUSDT')
    parser.add_argument('--interval', type=str, default='1h',
                        help='K线周期,如 1m, 5m, 1h, 1d')
    parser.add_argument('--start', type=str, required=True,
                        help='开始日期 YYYY-MM-DD')
    parser.add_argument('--end', type=str, default=None,
                        help='结束日期 YYYY-MM-DD (默认今天)')
    parser.add_argument('--format', type=str, default='parquet',
                        choices=['parquet', 'csv'], help='保存格式')

    args = parser.parse_args()

    # 配置日志
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=''),
        format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>"
    )

    print(f"""
╔════════════════════════════════════════════════╗
║     交易所历史数据下载工具                     ║
║     Historical Data Downloader                ║
╚════════════════════════════════════════════════╝

交易所: {args.exchange.upper()}
交易对: {args.symbol}
周  期: {args.interval}
时间段: {args.start} ~ {args.end or '今天'}
格  式: {args.format.upper()}
    """)

    try:
        downloader = DataDownloader(args.exchange)
        filepath = downloader.download_and_save(
            args.symbol,
            args.interval,
            args.start,
            args.end,
            args.format
        )

        if filepath:
            print(f"\n✅ 下载成功!")
            print(f"文件位置: {filepath}")
            print(f"\n💡 提示: 您可以使用此数据进行回测:")
            print(f"   python main.py --mode backtest --strategy your_strategy \\")
            print(f"     --start {args.start} --end {args.end or datetime.now().strftime('%Y-%m-%d')}")

    except Exception as e:
        logger.exception(f"下载失败: {e}")
        return 1

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
