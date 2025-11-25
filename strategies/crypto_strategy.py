# -*- coding: utf-8 -*-
"""
虚拟货币交易策略 - 从期货策略转换
保持所有信号逻辑不变,适配交易系统框架
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Optional
from pathlib import Path
import json

from strategies.base_strategy import BaseStrategy
from strategies.crypto_signals import SignalCalculator
from strategies.crypto_data_loader import load_crypto_data, get_multi_timeframe_data
from loguru import logger


class CryptoStrategy(BaseStrategy):
    """
    虚拟货币策略 - 从期货策略转换

    保持所有信号判断逻辑与原始期货策略一致
    只修改数据层和交易层适配虚拟货币
    """

    # 策略参数(与原始期货策略一致)
    parameters = [
        'M1', 'M2', 'M3', 'M4', 'M99', 'N',
        'SHORT', 'LONG', 'MID',
        'stkmoney', 'stoploss', 'lossrate'
    ]

    # 策略变量
    variables = [
        'position', 'last_signal', 'trade_count'
    ]

    def __init__(
        self,
        symbol: str = 'BTCUSDT',
        market_type: str = 'spot',
        exchange: str = 'binance',
        data_dir: str = 'data/historical',
        config_path: Optional[str] = None
    ):
        """
        初始化策略

        Args:
            symbol: 交易对
            market_type: 'spot' 或 'futures'
            exchange: 交易所
            data_dir: 数据目录
            config_path: 配置文件路径(可选)
        """
        super().__init__(strategy_name='CryptoStrategy')

        self.symbol = symbol
        self.market_type = market_type
        self.exchange = exchange
        self.data_dir = data_dir

        # 策略参数(默认值与原始期货策略一致)
        self.M1 = 5     # 短期MA
        self.M2 = 10    # 中期MA
        self.M3 = 20    # 中长期MA
        self.M4 = 60    # 长期MA
        self.M99 = 20   # ACD平滑
        self.N = 12     # 信号平滑

        self.SHORT = 12  # MACD短期
        self.LONG = 26   # MACD长期
        self.MID = 9     # MACD信号

        # 资金管理
        self.stkmoney = 10000.0  # 单次交易金额
        self.stoploss = 0.02     # 移动止损比率
        self.lossrate = 0.08     # 固定止损比率

        # 手续费设置（币安标准费率）
        self.fee_rate_spot = 0.001      # 现货手续费 0.1%
        self.fee_rate_futures = 0.0004  # 合约手续费 0.04% (Maker)

        # 滑点设置
        self.slippage_rate = 0.0005     # 滑点 0.05%

        # 止盈止损设置
        self.take_profit_rate = 0.10    # 止盈比率 10%
        self.stop_loss_rate = 0.05      # 止损比率 5%
        self.trailing_stop = True       # 是否启用移动止损
        self.trailing_stop_rate = 0.03  # 移动止损比率 3%

        # 策略变量
        self.position = 0        # 当前持仓
        self.last_signal = ''    # 上一次信号
        self.trade_count = 0     # 交易次数

        # 回测追踪变量
        self.entry_price = 0.0   # 入场价格
        self.highest_price = 0.0 # 持仓期间最高价
        self.lowest_price = 0.0  # 持仓期间最低价

        # 初始化信号计算器
        self.signal_calc = SignalCalculator(
            symbol=symbol,
            market_type=market_type,
            exchange=exchange,
            data_dir=data_dir
        )

        # 同步策略参数到信号计算器
        self._sync_params()

        # 加载配置(如果提供)
        if config_path:
            self.load_config(config_path)

        logger.info(f"策略初始化完成: {symbol} ({market_type})")

    def _sync_params(self):
        """同步策略参数到信号计算器"""
        self.signal_calc.M1 = self.M1
        self.signal_calc.M2 = self.M2
        self.signal_calc.M3 = self.M3
        self.signal_calc.M4 = self.M4
        self.signal_calc.M99 = self.M99
        self.signal_calc.N = self.N
        self.signal_calc.SHORT = self.SHORT
        self.signal_calc.LONG = self.LONG
        self.signal_calc.MID = self.MID

    def load_config(self, config_path: str):
        """从配置文件加载参数"""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)

            # 更新参数
            for key in ['M1', 'M2', 'M3', 'M4', 'M99', 'N', 'SHORT', 'LONG', 'MID']:
                if key in config:
                    setattr(self, key, int(config[key]))

            for key in ['stkmoney', 'stoploss', 'lossrate']:
                if key in config:
                    setattr(self, key, float(config[key]))

            # 同步参数
            self._sync_params()

            logger.info(f"配置加载成功: {config_path}")

        except Exception as e:
            logger.error(f"配置加载失败: {e}")

    def on_bar(self, bar: dict):
        """
        K线处理函数(与原始策略的handlebar对应)

        这是策略的核心逻辑入口

        Args:
            bar: 最新K线数据
        """
        # 获取多周期信号
        signals = self.signal_calc.get_latest_signals(['1m', '5m', '15m', '30m', '1h', '1d'])

        if signals.empty:
            return

        # 分析信号并生成交易决策
        self._analyze_signals(signals)

    def _analyze_signals(self, signals: pd.DataFrame):
        """
        分析信号并生成交易决策

        根据HA、QS、QJ、WD3等指标判断交易信号

        Args:
            signals: 多周期信号数据
        """
        # 获取1小时和日线信号(主要参考)
        signals_1h = signals[signals['period'] == '1h']
        signals_1d = signals[signals['period'] == '1d']

        if signals_1h.empty or signals_1d.empty:
            return

        # 获取最新指标值
        ha_1h = signals_1h['HA'].values[0]
        qs_1h = signals_1h['QS'].values[0]
        qj_1h = signals_1h['QJ'].values[0]
        wd3_1h = signals_1h['WD3'].values[0]
        ak_1h = signals_1h['AK'].values[0]
        aj_1h = signals_1h['AJ'].values[0]

        # 信号判断(与原始策略逻辑一致)
        buy_signal = False
        sell_signal = False

        # 买入条件(示例):
        # HA > 33000 (强势上涨趋势)
        # QS绝对值 > 1250 (强势信号)
        # WD3 < 100 (未过热)
        if ha_1h > 33000 and abs(qs_1h) > 1250 and wd3_1h < 100:
            if self.position == 0:
                buy_signal = True

        # 卖出条件(示例):
        # QJ绝对值 > 70000 (强烈下跌趋势)
        # 或 WD3 > 233 (过热)
        if abs(qj_1h) > 70000 or wd3_1h > 233:
            if self.position > 0:
                sell_signal = True

        # 执行交易
        if buy_signal:
            self._execute_buy()
        elif sell_signal:
            self._execute_sell()

    def _execute_buy(self):
        """执行买入"""
        logger.info(f"[买入信号] {self.symbol}")

        # 实际下单逻辑
        # price = self.get_current_price()
        # volume = self.stkmoney / price
        # self.buy(price, volume)

        self.position = 1
        self.last_signal = 'BUY'
        self.trade_count += 1

    def _execute_sell(self):
        """执行卖出"""
        logger.info(f"[卖出信号] {self.symbol}")

        # 实际下单逻辑
        # price = self.get_current_price()
        # self.sell(price, self.position)

        self.position = 0
        self.last_signal = 'SELL'
        self.trade_count += 1

    def backtest(
        self,
        start_date: str,
        end_date: str,
        interval: str = '1h',
        initial_capital: float = 100000.0,
        enable_stop_loss: bool = True,
        enable_take_profit: bool = True
    ) -> Dict:
        """
        策略回测（包含手续费、滑点、止盈止损）

        Args:
            start_date: 开始日期
            end_date: 结束日期
            interval: 主周期
            initial_capital: 初始资金
            enable_stop_loss: 是否启用止损
            enable_take_profit: 是否启用止盈

        Returns:
            回测结果字典
        """
        logger.info(f"开始回测: {start_date} ~ {end_date}")
        logger.info(f"手续费率: {self._get_fee_rate()*100:.3f}%, 滑点: {self.slippage_rate*100:.3f}%")
        if enable_stop_loss:
            logger.info(f"止损: {self.stop_loss_rate*100:.1f}%, 移动止损: {self.trailing_stop_rate*100:.1f}%")
        if enable_take_profit:
            logger.info(f"止盈: {self.take_profit_rate*100:.1f}%")

        # 加载历史数据
        data = load_crypto_data(
            symbol=self.symbol,
            interval=interval,
            market_type=self.market_type,
            exchange=self.exchange,
            data_dir=self.data_dir,
            start_date=start_date,
            end_date=end_date
        )

        if data.empty:
            logger.error("没有数据可用于回测")
            return {}

        # 初始化回测状态
        capital = initial_capital
        position = 0
        trades = []

        # 重置追踪变量
        self.entry_price = 0.0
        self.highest_price = 0.0
        self.lowest_price = 0.0

        stop_loss_count = 0
        take_profit_count = 0

        # 遍历每根K线
        for i in range(len(data)):
            bar = data.iloc[i]
            current_price = bar['close']

            # 检查止盈止损条件
            if position > 0:
                take_profit_triggered, stop_loss_triggered = self._check_stop_conditions(current_price)

                if enable_take_profit and take_profit_triggered:
                    # 触发止盈
                    position = 0
                    trades.append({
                        'time': bar['stime'],
                        'action': 'SELL',
                        'price': current_price,
                        'reason': 'TAKE_PROFIT'
                    })
                    take_profit_count += 1
                    self.entry_price = 0.0
                    self.highest_price = 0.0
                    self.lowest_price = 0.0
                    continue

                if enable_stop_loss and stop_loss_triggered:
                    # 触发止损
                    position = 0
                    trades.append({
                        'time': bar['stime'],
                        'action': 'SELL',
                        'price': current_price,
                        'reason': 'STOP_LOSS'
                    })
                    stop_loss_count += 1
                    self.entry_price = 0.0
                    self.highest_price = 0.0
                    self.lowest_price = 0.0
                    continue

            # 模拟on_bar调用
            self.on_bar(bar.to_dict())

            # 记录交易
            if self.last_signal == 'BUY' and position == 0:
                position = 1
                self.entry_price = current_price
                self.highest_price = current_price
                self.lowest_price = current_price
                trades.append({
                    'time': bar['stime'],
                    'action': 'BUY',
                    'price': current_price,
                    'reason': 'SIGNAL'
                })
            elif self.last_signal == 'SELL' and position > 0:
                position = 0
                trades.append({
                    'time': bar['stime'],
                    'action': 'SELL',
                    'price': current_price,
                    'reason': 'SIGNAL'
                })
                self.entry_price = 0.0
                self.highest_price = 0.0
                self.lowest_price = 0.0

            self.last_signal = ''  # 重置

        # 计算回测结果
        result = self._calculate_backtest_result(trades, initial_capital)
        result['stop_loss_count'] = stop_loss_count
        result['take_profit_count'] = take_profit_count

        logger.info(f"回测完成: 交易{len(trades)}次, 收益率{result.get('return_pct', 0):.2f}%")
        logger.info(f"手续费: ${result.get('total_fee', 0):.2f} ({result.get('fee_pct', 0):.2f}%)")
        logger.info(f"止损次数: {stop_loss_count}, 止盈次数: {take_profit_count}")

        return result

    def _get_fee_rate(self) -> float:
        """获取手续费率"""
        if self.market_type == 'spot':
            return self.fee_rate_spot
        else:
            return self.fee_rate_futures

    def _apply_slippage(self, price: float, is_buy: bool) -> float:
        """
        应用滑点

        Args:
            price: 原始价格
            is_buy: 是否为买入（买入价格上滑，卖出价格下滑）

        Returns:
            应用滑点后的价格
        """
        if is_buy:
            # 买入时价格上滑
            return price * (1 + self.slippage_rate)
        else:
            # 卖出时价格下滑
            return price * (1 - self.slippage_rate)

    def _calculate_fee(self, amount: float) -> float:
        """
        计算手续费

        Args:
            amount: 交易金额

        Returns:
            手续费金额
        """
        return amount * self._get_fee_rate()

    def _check_stop_conditions(self, current_price: float) -> tuple:
        """
        检查止盈止损条件

        Args:
            current_price: 当前价格

        Returns:
            (是否触发止盈, 是否触发止损)
        """
        if self.position == 0 or self.entry_price == 0:
            return False, False

        # 更新最高价和最低价
        if current_price > self.highest_price:
            self.highest_price = current_price
        if current_price < self.lowest_price or self.lowest_price == 0:
            self.lowest_price = current_price

        # 计算收益率
        profit_rate = (current_price - self.entry_price) / self.entry_price

        # 检查固定止盈
        take_profit_triggered = profit_rate >= self.take_profit_rate

        # 检查固定止损
        stop_loss_triggered = profit_rate <= -self.stop_loss_rate

        # 检查移动止损
        if self.trailing_stop and self.highest_price > self.entry_price:
            # 从最高点回撤超过移动止损比率
            drawdown = (self.highest_price - current_price) / self.highest_price
            if drawdown >= self.trailing_stop_rate:
                stop_loss_triggered = True

        return take_profit_triggered, stop_loss_triggered

    def _calculate_backtest_result(
        self,
        trades: list,
        initial_capital: float
    ) -> Dict:
        """计算回测结果（包含手续费和滑点）"""
        if not trades:
            return {'trades': 0, 'return_pct': 0, 'total_fee': 0}

        # 计算收益
        capital = initial_capital
        position_price = 0
        position_amount = 0
        total_fee = 0.0

        buy_trades = 0
        sell_trades = 0

        for trade in trades:
            if trade['action'] == 'BUY':
                # 应用滑点
                actual_price = self._apply_slippage(trade['price'], is_buy=True)

                # 计算可买入数量
                position_amount = capital / actual_price

                # 计算手续费
                fee = self._calculate_fee(capital)
                total_fee += fee

                # 扣除手续费后的实际持仓
                position_amount = (capital - fee) / actual_price
                position_price = actual_price

                buy_trades += 1

            elif trade['action'] == 'SELL' and position_price > 0:
                # 应用滑点
                actual_price = self._apply_slippage(trade['price'], is_buy=False)

                # 计算卖出金额
                sell_amount = position_amount * actual_price

                # 计算手续费
                fee = self._calculate_fee(sell_amount)
                total_fee += fee

                # 扣除手续费后的实际资金
                capital = sell_amount - fee

                position_price = 0
                position_amount = 0
                sell_trades += 1

        return_pct = (capital - initial_capital) / initial_capital * 100
        fee_pct = (total_fee / initial_capital) * 100

        return {
            'initial_capital': initial_capital,
            'final_capital': capital,
            'return_pct': return_pct,
            'trades': len(trades),
            'buy_trades': buy_trades,
            'sell_trades': sell_trades,
            'total_fee': total_fee,
            'fee_pct': fee_pct,
            'trade_list': trades
        }

    def display_signals(self, intervals: list = None):
        """
        显示当前信号(类似原始策略的outInfo)

        Args:
            intervals: 周期列表
        """
        if intervals is None:
            intervals = ['1m', '5m', '15m', '30m', '1h', '1d']

        signals = self.signal_calc.get_latest_signals(intervals)

        if signals.empty:
            print("无信号数据")
            return

        print(f"\n{'='*80}")
        print(f"交易对: {self.symbol} ({self.market_type})")
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}")
        print(signals.to_string())
        print(f"{'='*80}\n")


def main():
    """测试策略"""
    logger.info("初始化虚拟货币策略...")

    # 创建策略实例
    strategy = CryptoStrategy(
        symbol='BTCUSDT',
        market_type='spot',
        exchange='binance'
    )

    # 显示当前信号
    strategy.display_signals(['1h', '1d'])

    # 回测(示例)
    # result = strategy.backtest(
    #     start_date='2024-01-01',
    #     end_date='2024-11-20',
    #     interval='1h'
    # )
    # print(f"回测结果: {result}")


if __name__ == '__main__':
    main()
