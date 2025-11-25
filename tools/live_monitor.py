# -*- coding: utf-8 -*-
"""
实时数据监控和信号生成工具
不需要API密钥，使用公开数据
"""

import warnings
warnings.filterwarnings('ignore', category=Warning, module='urllib3')

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import requests
import pandas as pd
from datetime import datetime
import time
from loguru import logger
from strategies.crypto_signals import SignalCalculator
from tools.crypto_config import load_strategy_params
from tools.price_precision import format_price, get_symbol_precision
from tools.exchange_factory import ExchangeFactory


class LiveDataMonitor:
    """实时数据监控器（不需要API密钥）"""

    def __init__(self, symbol: str = 'BTCUSDT', market_type: str = 'spot', exchange: str = 'binance'):
        """
        初始化监控器

        Args:
            symbol: 交易对
            market_type: 'spot' 或 'futures'
            exchange: 交易所名称 ('binance', 'okx', 'htx')
        """
        self.symbol = symbol
        self.market_type = market_type
        self.exchange_name = exchange

        # 创建交易所实例
        self.exchange = ExchangeFactory.create(exchange, market_type)

        # 初始化信号计算器
        self.signal_calc = SignalCalculator(
            symbol=symbol,
            market_type=market_type
        )

        # 加载策略参数
        try:
            self.params = load_strategy_params()
        except Exception:
            from tools.crypto_config import DEFAULT_STRATEGY_PARAMS
            self.params = DEFAULT_STRATEGY_PARAMS

        logger.info(f"✓ 实时监控初始化: {symbol} ({market_type}) - {exchange.upper()}")

    def get_latest_klines(self, interval: str = '1h', limit: int = 100):
        """
        获取最新K线数据（公开API，无需密钥）

        Args:
            interval: K线周期
            limit: 获取数量

        Returns:
            DataFrame
        """
        try:
            df = self.exchange.get_klines(self.symbol, interval, limit)

            if df is not None:
                # 统一列名
                df = df.rename(columns={'timestamp': 'stime'})
                return df

            return None

        except Exception as e:
            logger.error(f"获取实时数据失败: {e}")
            return pd.DataFrame()

    def get_current_price(self):
        """获取当前价格（公开API）"""
        try:
            price = self.exchange.get_current_price(self.symbol)
            return price
        except Exception as e:
            logger.error(f"获取价格失败: {e}")
            return None

    def calculate_live_signals(self, interval: str = '1h'):
        """
        计算实时信号

        Args:
            interval: K线周期

        Returns:
            最新信号字典
        """
        # 获取最新100根K线（确保指标计算准确）
        df = self.get_latest_klines(interval, limit=100)

        if df.empty:
            return None

        # 使用信号计算器的指标计算逻辑
        data = df.copy()

        # 导入指标函数
        from strategies.indicators import MA, EMA, SMA, STD, IF, MIN, MAX, SUM, REF, ABS, EXPMEMA
        from strategies.crypto_signals import SignalCalculator

        # 计算信号参数
        sp = self.params['signal_params']

        # MA系列
        data['MA1'] = MA(data['close'], sp['M1'])
        data['MA2'] = MA(data['close'], sp['M2'])
        data['MA3'] = MA(data['close'], sp['M3'])
        data['MA4'] = MA(data['close'], sp['M4'])

        # HA指标
        data['H4A1'] = ((data['MA1'] > data['MA1'].shift(1)) &
                       (data['MA3'] > data['MA3'].shift(1))).astype(int)
        data['HA'] = (MA(data['H4A1'], sp['N']) * 2500 * 16).astype(int)

        # QS指标
        data['DIF'] = EMA(data['close'], sp['SHORT']) - EMA(data['close'], sp['LONG'])
        data['DEA'] = MA(data['DIF'], sp['MID'])
        data['WOD'] = 0  # 简化计算
        data['QS1'] = ((data['DIF'] > data['DEA']) &
                      (data['MA1'] > data['MA1'].shift(1))).astype(int)
        data['QS'] = -(MA(data['QS1'], sp['N']) * 1500).astype(int)

        # QJ指标
        data['QJ1'] = ((data['MA4'] < data['MA4'].shift(1)) &
                      (data['MA3'] < data['MA3'].shift(1)) &
                      (data['MA2'] < data['MA2'].shift(1)) &
                      (data['MA1'] < data['MA1'].shift(1))).astype(int)
        data['QJ'] = -(MA(data['QJ1'], sp['N']) * 2500 * 40).astype(int)

        # WD3简化计算
        data['WD3'] = 100

        # 最新一根K线的信号
        latest = data.iloc[-1]

        return {
            'time': latest['stime'],
            'close': latest['close'],
            'HA': int(latest['HA']),
            'QS': int(latest['QS']),
            'QJ': int(latest['QJ']),
            'WD3': int(latest['WD3'])
        }

    def check_trading_signal(self, signals: dict):
        """
        检查交易信号

        Args:
            signals: 信号字典

        Returns:
            'BUY', 'SELL', 或 None
        """
        buy_params = self.params['trading_conditions']['buy']
        sell_params = self.params['trading_conditions']['sell']

        ha = signals['HA']
        qs = signals['QS']
        qj = signals['QJ']
        wd3 = signals['WD3']

        # 买入信号
        if ha > buy_params['HA_threshold'] and wd3 < buy_params['WD3_max']:
            return 'BUY'

        # 卖出信号
        if abs(qj) > sell_params['QJ_threshold'] or wd3 > sell_params['WD3_threshold']:
            return 'SELL'

        return None

    def run_monitor(self, interval: str = '1h', update_seconds: int = 60):
        """
        运行实时监控

        Args:
            interval: K线周期
            update_seconds: 更新间隔（秒）
        """
        logger.info(f"开始监控 {self.symbol} ({self.market_type})")
        logger.info(f"K线周期: {interval}, 更新间隔: {update_seconds}秒")
        logger.info("按 Ctrl+C 停止监控\n")

        # 获取价格精度
        price_precision = get_symbol_precision(self.symbol)

        try:
            while True:
                # 获取当前价格
                price = self.get_current_price()

                # 计算信号
                signals = self.calculate_live_signals(interval)

                if signals and price:
                    # 检查交易信号
                    action = self.check_trading_signal(signals)

                    # 显示信息
                    price_str = format_price(price, price_precision)
                    print(f"\n{'='*60}")
                    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"交易对: {self.symbol}")
                    print(f"当前价格: ${price_str}")
                    print(f"\n信号指标:")
                    print(f"  HA:  {signals['HA']:>8,}")
                    print(f"  QS:  {signals['QS']:>8,}")
                    print(f"  QJ:  {signals['QJ']:>8,}")
                    print(f"  WD3: {signals['WD3']:>8,}")

                    if action:
                        print(f"\n🔔 交易信号: {action}")
                        if action == 'BUY':
                            print("   建议: 买入")
                        else:
                            print("   建议: 卖出")
                    else:
                        print("\n⏸  无交易信号，观望")

                    print(f"{'='*60}")

                # 等待
                time.sleep(update_seconds)

        except KeyboardInterrupt:
            logger.info("\n\n监控已停止")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='实时数据监控工具（无需API密钥）')
    parser.add_argument('--symbol', type=str, default='BTCUSDT',
                        help='交易对（如: BTCUSDT）')
    parser.add_argument('--market', type=str, default='spot',
                        choices=['spot', 'futures'],
                        help='市场类型')
    parser.add_argument('--interval', type=str, default='1h',
                        help='K线周期（支持: 15s, 1m, 5m, 15m, 30m, 1h, 4h, 1d等）')
    parser.add_argument('--update', type=int, default=60,
                        help='更新间隔（秒）')

    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════════════════════╗
║              实时数据监控工具                             ║
║           Live Data Monitor (No API Key)               ║
╠══════════════════════════════════════════════════════════╣
║  交易对:   {args.symbol:40s}  ║
║  市场:     {'现货' if args.market == 'spot' else '合约':40s}  ║
║  周期:     {args.interval:40s}  ║
║  更新间隔: {args.update} 秒{' '*36}  ║
╚══════════════════════════════════════════════════════════╝

注意: 此工具仅用于信号监控，不会进行真实交易
""")

    monitor = LiveDataMonitor(args.symbol, args.market)
    monitor.run_monitor(args.interval, args.update)


if __name__ == '__main__':
    main()
