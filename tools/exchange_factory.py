# -*- coding: utf-8 -*-
"""
交易所工厂类 - 统一接口支持多个交易所
支持: Binance, OKX, Huobi/HTX
"""

import requests
import pandas as pd
from datetime import datetime
from typing import Optional, List, Dict
from loguru import logger


class ExchangeFactory:
    """交易所工厂类"""
    
    SUPPORTED_EXCHANGES = ['binance', 'okx', 'htx']
    
    @staticmethod
    def create(exchange: str, market_type: str = 'spot'):
        """
        创建交易所实例
        
        Args:
            exchange: 交易所名称 (binance/okx/htx)
            market_type: 市场类型 (spot/futures)
            
        Returns:
            交易所实例
        """
        exchange = exchange.lower()
        
        if exchange not in ExchangeFactory.SUPPORTED_EXCHANGES:
            raise ValueError(f"不支持的交易所: {exchange}. 支持的交易所: {ExchangeFactory.SUPPORTED_EXCHANGES}")
        
        if exchange == 'binance':
            return BinanceExchange(market_type)
        elif exchange == 'okx':
            return OKXExchange(market_type)
        elif exchange == 'htx':
            return HTXExchange(market_type)


class BaseExchange:
    """交易所基类"""
    
    def __init__(self, market_type: str = 'spot'):
        self.market_type = market_type
        self.base_url = ''
        self.name = ''
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """获取当前价格"""
        raise NotImplementedError
    
    def get_klines(self, symbol: str, interval: str, limit: int = 500) -> Optional[pd.DataFrame]:
        """获取K线数据"""
        raise NotImplementedError
    
    def get_all_symbols(self) -> List[str]:
        """获取所有交易对"""
        raise NotImplementedError


class BinanceExchange(BaseExchange):
    """币安交易所"""
    
    def __init__(self, market_type: str = 'spot'):
        super().__init__(market_type)
        self.name = 'Binance'
        
        if market_type == 'futures':
            self.base_url = 'https://fapi.binance.com'
        else:
            self.base_url = 'https://api.binance.com'
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """获取当前价格"""
        try:
            url = f"{self.base_url}/api/v3/ticker/price"
            response = requests.get(url, params={'symbol': symbol}, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return float(data['price'])
        except Exception as e:
            logger.error(f"获取Binance价格失败: {e}")
        
        return None
    
    def get_klines(self, symbol: str, interval: str, limit: int = 500) -> Optional[pd.DataFrame]:
        """获取K线数据"""
        try:
            url = f"{self.base_url}/api/v3/klines"
            params = {
                'symbol': symbol,
                'interval': interval,
                'limit': limit
            }
            
            response = requests.get(url, params=params, timeout=30)  # 增加超时时间

            if response.status_code == 200:
                data = response.json()
                
                df = pd.DataFrame(data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                    'taker_buy_quote', 'ignore'
                ])
                
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                
                return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        
        except Exception as e:
            logger.error(f"获取Binance K线失败: {e}")
        
        return None
    
    def get_all_symbols(self) -> List[str]:
        """获取所有交易对"""
        try:
            url = f"{self.base_url}/api/v3/exchangeInfo"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                symbols = [s['symbol'] for s in data['symbols'] if s['status'] == 'TRADING']
                return symbols
        
        except Exception as e:
            logger.error(f"获取Binance交易对失败: {e}")
        
        return []


class OKXExchange(BaseExchange):
    """OKX交易所"""

    def __init__(self, market_type: str = 'spot'):
        super().__init__(market_type)
        self.name = 'OKX'
        self.base_url = 'https://www.okx.com'

        # OKX的产品类型
        if market_type == 'futures':
            self.inst_type = 'SWAP'  # 永续合约
        else:
            self.inst_type = 'SPOT'  # 现货

    def get_current_price(self, symbol: str) -> Optional[float]:
        """获取当前价格"""
        try:
            # OKX使用 BTC-USDT 格式
            inst_id = self._convert_symbol(symbol)

            url = f"{self.base_url}/api/v5/market/ticker"
            response = requests.get(url, params={'instId': inst_id}, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data['code'] == '0' and data['data']:
                    return float(data['data'][0]['last'])
        except Exception as e:
            logger.error(f"获取OKX价格失败: {e}")

        return None

    def get_klines(self, symbol: str, interval: str, limit: int = 500) -> Optional[pd.DataFrame]:
        """获取K线数据"""
        try:
            inst_id = self._convert_symbol(symbol)
            bar = self._convert_interval(interval)

            url = f"{self.base_url}/api/v5/market/candles"
            params = {
                'instId': inst_id,
                'bar': bar,
                'limit': min(limit, 300)  # OKX最多300根
            }

            response = requests.get(url, params=params, timeout=30)  # 增加超时时间

            if response.status_code == 200:
                data = response.json()
                if data['code'] == '0' and data['data']:
                    df = pd.DataFrame(data['data'], columns=[
                        'timestamp', 'open', 'high', 'low', 'close', 'volume',
                        'volCcy', 'volCcyQuote', 'confirm'
                    ])

                    df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms')
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        df[col] = df[col].astype(float)

                    # OKX返回的是倒序，需要反转
                    df = df.sort_values('timestamp').reset_index(drop=True)

                    return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]

        except Exception as e:
            logger.error(f"获取OKX K线失败: {e}")

        return None

    def get_all_symbols(self) -> List[str]:
        """获取所有交易对"""
        try:
            url = f"{self.base_url}/api/v5/public/instruments"
            response = requests.get(url, params={'instType': self.inst_type}, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data['code'] == '0':
                    # 转换为Binance格式 (BTC-USDT -> BTCUSDT)
                    symbols = [s['instId'].replace('-', '') for s in data['data']]
                    return symbols

        except Exception as e:
            logger.error(f"获取OKX交易对失败: {e}")

        return []

    def _convert_symbol(self, symbol: str) -> str:
        """转换交易对格式: BTCUSDT -> BTC-USDT"""
        # 简单处理，假设都是USDT交易对
        if '-' in symbol:
            return symbol

        if symbol.endswith('USDT'):
            base = symbol[:-4]
            return f"{base}-USDT"

        return symbol

    def _convert_interval(self, interval: str) -> str:
        """转换时间周期格式"""
        # Binance: 1m, 5m, 15m, 1h, 4h, 1d
        # OKX: 1m, 5m, 15m, 1H, 4H, 1D
        interval_map = {
            '1m': '1m',
            '3m': '3m',
            '5m': '5m',
            '15m': '15m',
            '30m': '30m',
            '1h': '1H',
            '2h': '2H',
            '4h': '4H',
            '6h': '6H',
            '12h': '12H',
            '1d': '1D',
            '1w': '1W',
            '1M': '1M'
        }

        return interval_map.get(interval, interval)


class HTXExchange(BaseExchange):
    """火币/HTX交易所"""

    def __init__(self, market_type: str = 'spot'):
        super().__init__(market_type)
        self.name = 'HTX'

        if market_type == 'futures':
            self.base_url = 'https://api.hbdm.com'  # 合约API
        else:
            self.base_url = 'https://api.huobi.pro'  # 现货API

    def get_current_price(self, symbol: str) -> Optional[float]:
        """获取当前价格"""
        try:
            # HTX使用 btcusdt 格式（小写）
            symbol_lower = symbol.lower()

            url = f"{self.base_url}/market/detail/merged"
            response = requests.get(url, params={'symbol': symbol_lower}, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data['status'] == 'ok':
                    return float(data['tick']['close'])
        except Exception as e:
            logger.error(f"获取HTX价格失败: {e}")

        return None

    def get_klines(self, symbol: str, interval: str, limit: int = 500) -> Optional[pd.DataFrame]:
        """获取K线数据"""
        try:
            symbol_lower = symbol.lower()
            period = self._convert_interval(interval)

            url = f"{self.base_url}/market/history/kline"
            params = {
                'symbol': symbol_lower,
                'period': period,
                'size': min(limit, 2000)  # HTX最多2000根
            }

            response = requests.get(url, params=params, timeout=30)  # 增加超时时间

            if response.status_code == 200:
                data = response.json()
                if data['status'] == 'ok':
                    df = pd.DataFrame(data['data'])

                    df['timestamp'] = pd.to_datetime(df['id'], unit='s')
                    df = df.rename(columns={
                        'open': 'open',
                        'high': 'high',
                        'low': 'low',
                        'close': 'close',
                        'vol': 'volume'
                    })

                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        df[col] = df[col].astype(float)

                    # HTX返回的是倒序，需要反转
                    df = df.sort_values('timestamp').reset_index(drop=True)

                    return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]

        except Exception as e:
            logger.error(f"获取HTX K线失败: {e}")

        return None

    def get_all_symbols(self) -> List[str]:
        """获取所有交易对"""
        try:
            url = f"{self.base_url}/v1/common/symbols"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data['status'] == 'ok':
                    # 转换为大写格式 (btcusdt -> BTCUSDT)
                    symbols = [s['symbol'].upper() for s in data['data'] if s['state'] == 'online']
                    return symbols

        except Exception as e:
            logger.error(f"获取HTX交易对失败: {e}")

        return []

    def _convert_interval(self, interval: str) -> str:
        """转换时间周期格式"""
        # Binance: 1m, 5m, 15m, 1h, 4h, 1d
        # HTX: 1min, 5min, 15min, 60min, 4hour, 1day
        interval_map = {
            '1m': '1min',
            '5m': '5min',
            '15m': '15min',
            '30m': '30min',
            '1h': '60min',
            '4h': '4hour',
            '1d': '1day',
            '1w': '1week',
            '1M': '1mon'
        }

        return interval_map.get(interval, interval)

