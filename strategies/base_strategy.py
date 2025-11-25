"""
策略基类
所有交易策略都应继承此类
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from datetime import datetime
from loguru import logger


class BaseStrategy(ABC):
    """交易策略基类"""

    def __init__(self, strategy_name: str, parameters: Dict = None):
        """
        初始化策略

        Args:
            strategy_name: 策略名称
            parameters: 策略参数字典
        """
        self.strategy_name = strategy_name
        self.parameters = parameters or {}
        self.positions = {}  # 当前持仓
        self.orders = []  # 订单记录
        self.is_running = False

        logger.info(f"初始化策略: {strategy_name}")
        logger.info(f"策略参数: {parameters}")

    @abstractmethod
    def on_bar(self, bar: Dict):
        """
        K线数据回调 (必须实现)

        Args:
            bar: K线数据字典,包含:
                - symbol: 交易对
                - open: 开盘价
                - high: 最高价
                - low: 最低价
                - close: 收盘价
                - volume: 成交量
                - datetime: 时间戳
        """
        pass

    def on_tick(self, tick: Dict):
        """
        Tick数据回调 (可选实现,高频策略需要)

        Args:
            tick: Tick数据
        """
        pass

    def on_order(self, order: Dict):
        """
        订单状态更新回调

        Args:
            order: 订单信息
        """
        logger.info(f"订单更新: {order}")
        self.orders.append(order)

    def on_trade(self, trade: Dict):
        """
        成交回调

        Args:
            trade: 成交信息
        """
        logger.info(f"成交通知: {trade}")

    def buy(self, symbol: str, price: float, volume: float) -> Dict:
        """
        买入

        Args:
            symbol: 交易对
            price: 价格
            volume: 数量

        Returns:
            订单信息
        """
        order = {
            'symbol': symbol,
            'direction': 'buy',
            'price': price,
            'volume': volume,
            'datetime': datetime.now(),
            'status': 'pending'
        }

        logger.info(f"[{self.strategy_name}] 买入信号: {symbol} @ {price}, 数量: {volume}")
        return order

    def sell(self, symbol: str, price: float, volume: float) -> Dict:
        """
        卖出

        Args:
            symbol: 交易对
            price: 价格
            volume: 数量

        Returns:
            订单信息
        """
        order = {
            'symbol': symbol,
            'direction': 'sell',
            'price': price,
            'volume': volume,
            'datetime': datetime.now(),
            'status': 'pending'
        }

        logger.info(f"[{self.strategy_name}] 卖出信号: {symbol} @ {price}, 数量: {volume}")
        return order

    def get_position(self, symbol: str) -> Optional[Dict]:
        """获取持仓信息"""
        return self.positions.get(symbol)

    def update_position(self, symbol: str, position: Dict):
        """更新持仓"""
        self.positions[symbol] = position

    def start(self):
        """启动策略"""
        self.is_running = True
        logger.info(f"策略 [{self.strategy_name}] 已启动")

    def stop(self):
        """停止策略"""
        self.is_running = False
        logger.info(f"策略 [{self.strategy_name}] 已停止")

    def get_strategy_info(self) -> Dict:
        """获取策略信息"""
        return {
            'name': self.strategy_name,
            'parameters': self.parameters,
            'is_running': self.is_running,
            'positions': self.positions,
            'total_orders': len(self.orders)
        }


class TrendFollowingStrategy(BaseStrategy):
    """趋势跟踪策略示例"""

    def __init__(self):
        super().__init__(
            strategy_name="趋势跟踪策略",
            parameters={
                'fast_period': 10,  # 快速均线周期
                'slow_period': 30,  # 慢速均线周期
                'atr_period': 14,  # ATR周期
            }
        )
        self.price_history = []
        self.fast_ma = None
        self.slow_ma = None

    def on_bar(self, bar: Dict):
        """K线回调 - 实现均线策略"""
        close_price = bar['close']
        self.price_history.append(close_price)

        # 保持历史数据在合理范围
        if len(self.price_history) > self.parameters['slow_period'] + 10:
            self.price_history.pop(0)

        # 计算均线
        if len(self.price_history) >= self.parameters['slow_period']:
            self.fast_ma = sum(self.price_history[-self.parameters['fast_period']:]) / self.parameters['fast_period']
            self.slow_ma = sum(self.price_history[-self.parameters['slow_period']:]) / self.parameters['slow_period']

            # 金叉做多信号
            if self.fast_ma > self.slow_ma:
                if not self.get_position(bar['symbol']):
                    self.buy(bar['symbol'], close_price, 1.0)

            # 死叉做空信号
            elif self.fast_ma < self.slow_ma:
                if self.get_position(bar['symbol']):
                    self.sell(bar['symbol'], close_price, 1.0)
