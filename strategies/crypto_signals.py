# -*- coding: utf-8 -*-
"""
虚拟货币信号计算模块
从期货策略转换,保持所有信号计算逻辑不变
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Optional

from strategies.indicators import (
    MA, EMA, SMA, STD, SUM, REF, ABS, IF, MAX, MIN, EXPMEMA
)
from strategies.crypto_data_loader import load_crypto_data
from loguru import logger


class SignalCalculator:
    """
    信号计算器 - 从期货策略转换

    保持所有指标计算和信号判断逻辑完全不变
    只修改数据输入层适配虚拟货币
    """

    def __init__(
        self,
        symbol: str = 'BTCUSDT',
        market_type: str = 'spot',
        exchange: str = 'binance',
        data_dir: str = 'data/historical'
    ):
        """
        初始化信号计算器

        Args:
            symbol: 交易对
            market_type: 'spot' 或 'futures'
            exchange: 交易所
            data_dir: 数据目录
        """
        self.symbol = symbol
        self.market_type = market_type
        self.exchange = exchange
        self.data_dir = data_dir

        # 策略参数(与原始期货策略完全一致)
        self.M1 = 5     # 短期MA周期
        self.M2 = 10    # 中期MA周期
        self.M3 = 20    # 中长期MA周期
        self.M4 = 60    # 长期MA周期
        self.M99 = 20   # ACD平滑周期
        self.N = 12     # 信号平滑周期

        self.SHORT = 12  # MACD短期
        self.LONG = 26   # MACD长期
        self.MID = 9     # MACD信号线

    def calculate_signals(self, interval: str) -> pd.DataFrame:
        """
        计算指定周期的所有信号指标

        这个函数与原始期货策略的GetZFIndexData()逻辑完全一致
        只是数据来源从期货API改为本地文件

        Args:
            interval: K线周期,如'15s','1m','5m','1h','1d'等

        Returns:
            包含所有信号指标的DataFrame
        """
        # 加载数据(替换原始的ContextInfo.get_market_data_ex)
        data = load_crypto_data(
            symbol=self.symbol,
            interval=interval,
            market_type=self.market_type,
            exchange=self.exchange,
            data_dir=self.data_dir
        )

        # ============== 以下代码与原始策略完全一致 ==============

        # MA系列
        data['MA1'] = np.nan_to_num(MA(data['close'], self.M1), nan=0)
        data['MA2'] = np.nan_to_num(MA(data['close'], self.M2), nan=0)
        data['MA3'] = np.nan_to_num(MA(data['close'], self.M3), nan=0)
        data['MA4'] = np.nan_to_num(MA(data['close'], self.M4), nan=0)

        # 展示用的MA
        data['MA20'] = data['MA3'].round(2)
        data['MA40'] = np.nan_to_num(MA(data['close'], 40), nan=0).round(2)
        data['MA60'] = data['MA4'].round(2)
        data['MA120'] = np.nan_to_num(MA(data['close'], 120), nan=0).round(2)
        data['MA250'] = np.nan_to_num(MA(data['close'], 250), nan=0).round(2)

        # HA指标(趋势强度)
        data['H4A1'] = ((data['MA1'] > data['MA1'].shift(1)) &
                       (data['MA3'] > data['MA3'].shift(1))).astype(int)
        data['HA'] = np.nan_to_num((MA(data['H4A1'], self.N) * 2500 * 16), nan=0).astype(int)

        # HD指标
        data['H4D1'] = (data['MA4'] > data['MA4'].shift(1)).astype(int)
        data['HD'] = np.nan_to_num((MA(data['H4D1'], self.N) * 2500 * 14), nan=0).astype(int)

        # 下跌趋势检测
        data['MD12'] = ((data['MA2'] < data['MA2'].shift(1)) &
                       (data['MA1'] < data['MA1'].shift(1))).astype(int)
        data['MD23'] = ((data['MA2'] < data['MA2'].shift(1)) &
                       (data['MA3'] < data['MA3'].shift(1))).astype(int)
        data['MD34'] = ((data['MA4'] < data['MA4'].shift(1)) &
                       (data['MA3'] < data['MA3'].shift(1))).astype(int)
        data['MD123'] = (data['MD12'] > 0) & (data['MD23'] > 0)
        data['MD234'] = (data['MD23'] > 0) & (data['MD34'] > 0)
        data['MQDQ'] = ((data['MD123'] > 0) & (data['MD234'] > 0)).astype(int)
        data['MQD'] = np.nan_to_num((MA(data['MQDQ'], self.N) * 200), nan=0)
        data['WXD1'] = (data['MQD'] > 100.3).astype(int)
        data['WOD'] = np.nan_to_num(MA(data['WXD1'], self.N) * 350, nan=0)

        # MACD相关
        data['DIF'] = np.nan_to_num((EMA(data['close'], self.SHORT) -
                                    EMA(data['close'], self.LONG)), nan=0)
        data['DEA'] = np.nan_to_num(MA(data['DIF'], self.MID), nan=0)

        # QS指标(强势信号)
        data['QS1'] = ((data['DIF'] > data['DEA']) &
                      (data['MA1'] > data['MA1'].shift(1)) &
                      (data['WOD'] < 80)).astype(int)
        data['QS'] = -np.nan_to_num((MA(data['QS1'], self.N) * 1500), nan=0).astype(int)

        # ZZ指标
        data['BA721'] = ((data['MA3'] > data['MA3'].shift(1)) &
                        (data['MA4'] > data['MA4'].shift(1)) &
                        (data['WOD'] < 66) &
                        (ABS(data['QS']) > 300)).astype(int)
        data['ZZ'] = np.nan_to_num((MA(data['BA721'], self.N) * 25000), nan=0).astype(int)

        # J1和F5指标
        data['MA4Q'] = ((data['MA4'] > data['MA4'].shift(1)) &
                       (data['WOD'] < 66)).astype(int)
        data['J1'] = np.nan_to_num(-MA(data['MA4Q'], self.N) * 2500 * 2, nan=0)
        data['F51'] = ((ABS(data['ZZ']) < 1000) &
                      (ABS(data['QS']) < 300) &
                      (ABS(data['J1']) > 4000)).astype(int)
        data['F5'] = np.nan_to_num((MA(data['F51'], self.N) * 2500 * 20), nan=0).astype(int)

        # QJ指标(趋势变化)
        data['QJ1'] = ((data['MA4'] < data['MA4'].shift(1)) &
                      (data['MA3'] < data['MA3'].shift(1)) &
                      (data['MA2'] < data['MA2'].shift(1)) &
                      (data['MA1'] < data['MA1'].shift(1))).astype(int)
        data['QJ'] = -np.nan_to_num((MA(data['QJ1'], self.N) * 2500 * 40), nan=0).astype(int)

        # WD3(威力度)
        data['WD3'] = data['WOD'].round().astype(int)

        # HZ系列
        data['H4Z1'] = ((data['MA4'] > data['MA4'].shift(1)) &
                       (data['MA3'] > data['MA3'].shift(1)) &
                       (data['MA1'] > data['MA1'].shift(1))).astype(int)
        data['HZ'] = np.nan_to_num((MA(data['H4Z1'], self.N) * 2500 * 16), nan=0).astype(int)
        data['F5Z1'] = ((data['F5'] < data['F5'].shift(1)) &
                       (data['HZ'] > data['HZ'].shift(1))).astype(int)
        data['F5Z2'] = ((data['F5'] > data['F5'].shift(1)) &
                       (data['HZ'] > data['HZ'].shift(1))).astype(int)
        data['TJF5'] = (data['F5Z1'] > 0) | (data['F5Z2'] > 0)
        data['ZF5'] = np.nan_to_num((MA(data['TJF5'], self.N) * 1780 * 8), nan=0).astype(int) * 40
        data['HZ1'] = np.nan_to_num((MA(data['H4Z1'], self.N) * 2500 * 16), nan=0).astype(int)

        # ACD累计差
        data['LC'] = data['close'].shift(1).fillna(0)
        data['DIF2'] = data['close'] - IF(
            data['close'] > data['LC'],
            MIN(data['low'], data['LC']),
            MAX(data['high'], data['LC'])
        )
        data['ACD'] = SUM(IF(data['close'] == data['LC'], 0, data['DIF2']), 0)
        data['S5W1'] = ((ABS(data['QJ']) < 650000) &
                       (ABS(data['QJ']) > 40000) &
                       (ABS(data['QJ']) < ABS(data['QJ'].shift(1))) &
                       (data['ACD'] > data['ACD'].shift(1))).astype(int)
        data['S5W'] = np.nan_to_num((MA(data['S5W1'], self.N) * 2500 * 190), nan=0).astype(int)

        # EXPEMA和CDC
        data['EXPEMA_Close'] = np.nan_to_num(EXPMEMA(data['close'], self.N), nan=0)
        data['MACCA'] = np.nan_to_num(EXPMEMA(data['ACD'], self.M99), nan=0)
        data['CDC'] = (data['MACCA'] - data['ACD']).round(2)

        # 波段之星(AK, AJ)
        data['Var2'] = np.nan_to_num((data['high'] + data['low'] + data['close'] * 2) / 4, nan=0)
        data['Var3'] = np.nan_to_num(EMA(data['Var2'], 21), nan=0)
        data['Var4'] = np.nan_to_num(STD(data['Var2'], 21), nan=0)
        data['wert'] = np.where(data['Var4'] == 0, 0, (data['Var2'] - data['Var3']) / data['Var4'])
        data['Var5'] = np.nan_to_num((np.float64(data['wert']) * 100 + 200) / 4, nan=0)
        data['Var6'] = np.nan_to_num((EMA(data['Var5'], 5) - 25) * 1.56, nan=0)
        data['AK'] = np.nan_to_num(EMA(data['Var6'], 2) * 1.22, nan=0).round(2)
        data['AD1'] = np.nan_to_num(EMA(data['AK'], 2), nan=0).round(2)
        data['AJ'] = np.nan_to_num(3 * data['AK'] - 2 * data['AD1'], nan=0).round(2)

        # CC指标(原为持仓量变化,这里用成交量变化替代)
        # 这是唯一需要适配的地方!
        data['CC'] = np.nan_to_num(
            data['volume'] - data['volume'].shift(1),  # ← 用volume替代openInterest
            nan=0
        ).astype(int)

        # 返回结果(与原始策略一致的列)
        result_data = data[[
            'high', 'low', 'MA20', 'MA40', 'MA60', 'MA120', 'MA250',
            'HA', 'QS', 'F5', 'QJ', 'WD3', 'CDC', 'AK', 'AJ', 'CC'
        ]].copy()
        result_data.insert(0, 'period', interval)
        result_data.insert(1, 'stime', data['stime'])

        return result_data

    def get_multi_period_signals(
        self,
        intervals: list = None
    ) -> Dict[str, pd.DataFrame]:
        """
        获取多周期信号数据

        与原始策略的handlebar函数逻辑一致

        Args:
            intervals: 周期列表,默认['15s','1m','5m','15m','30m','1h','1d']

        Returns:
            字典 {interval: signals_df}
        """
        if intervals is None:
            intervals = ['15s', '1m', '5m', '15m', '30m', '1h', '1d']

        results = {}
        for interval in intervals:
            try:
                signals = self.calculate_signals(interval)
                results[interval] = signals
                logger.info(f"✓ {interval}信号计算完成: {len(signals)}条")
            except Exception as e:
                logger.error(f"✗ {interval}信号计算失败: {e}")
                results[interval] = pd.DataFrame()

        return results

    def get_latest_signals(self, intervals: list = None) -> pd.DataFrame:
        """
        获取所有周期的最新一条信号

        类似原始策略的outInfo函数

        Args:
            intervals: 周期列表,默认['15s','1m','5m','15m','30m','1h','1d']

        Returns:
            汇总所有周期最新信号的DataFrame
        """
        if intervals is None:
            intervals = ['15s', '1m', '5m', '15m', '30m', '1h', '1d']

        multi_signals = self.get_multi_period_signals(intervals)

        # 取每个周期的最新一条
        latest_rows = []
        for interval, df in multi_signals.items():
            if not df.empty:
                latest_rows.append(df.iloc[-1])

        if not latest_rows:
            return pd.DataFrame()

        return pd.concat(latest_rows, axis=1).T.reset_index(drop=True)


def test_signal_calculator():
    """测试信号计算器"""
    logger.info("测试信号计算器...")

    calc = SignalCalculator(
        symbol='BTCUSDT',
        market_type='spot',
        exchange='binance'
    )

    # 测试单周期
    try:
        signals_1h = calc.calculate_signals('1h')
        print("\n1小时信号数据预览:")
        print(signals_1h.tail(10))

        # 测试多周期
        latest = calc.get_latest_signals(['1h', '1d'])
        print("\n最新信号汇总:")
        print(latest)

    except Exception as e:
        logger.error(f"测试失败: {e}")
        logger.info("请先下载数据: python tools/batch_downloader.py --market spot --interval 1h --start 2024-11-20 --top-n 5")


if __name__ == '__main__':
    test_signal_calculator()
