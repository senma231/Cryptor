# -*- coding: utf-8 -*-
"""
策略参数微调工具
用于安全地修改加密的策略参数
"""

import warnings
warnings.filterwarnings('ignore', category=Warning, module='urllib3')

import sys
from pathlib import Path

# 添加项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import json
from typing import Any
from loguru import logger
from tools.crypto_config import (
    load_strategy_params,
    save_strategy_params,
    init_encrypted_config,
    DEFAULT_STRATEGY_PARAMS
)


class StrategyTuner:
    """策略参数微调器"""

    def __init__(self, password: str = None):
        """
        初始化微调器

        Args:
            password: 加密密码（可选）
        """
        self.password = password
        self.params = None
        self._load_params()

    def _load_params(self):
        """加载当前参数"""
        try:
            self.params = load_strategy_params(self.password)
        except Exception as e:
            logger.warning(f"加载配置失败: {e}")
            logger.info("创建默认配置...")
            init_encrypted_config(self.password)
            self.params = load_strategy_params(self.password)

    def _save_params(self):
        """保存参数"""
        save_strategy_params(self.params, self.password)
        logger.info("✓ 参数已保存并加密")

    def show_current_params(self):
        """显示当前所有参数"""
        print("\n" + "=" * 60)
        print("           当前策略参数配置")
        print("=" * 60)

        # 信号参数
        print("\n【信号计算参数】")
        sp = self.params['signal_params']
        print(f"  MA周期:    M1={sp['M1']}, M2={sp['M2']}, M3={sp['M3']}, M4={sp['M4']}")
        print(f"  平滑周期:  M99={sp['M99']}, N={sp['N']}")
        print(f"  MACD:     SHORT={sp['SHORT']}, LONG={sp['LONG']}, MID={sp['MID']}")

        # 交易条件
        print("\n【交易条件参数】")
        tc = self.params['trading_conditions']
        print(f"  买入条件:  HA>{tc['buy']['HA_threshold']}, WD3<{tc['buy']['WD3_max']}, |QS|>{tc['buy']['QS_threshold']}")
        print(f"  卖出条件:  |QJ|>{tc['sell']['QJ_threshold']} 或 WD3>{tc['sell']['WD3_threshold']}")

        # 资金管理
        print("\n【资金管理参数】")
        mm = self.params['money_management']
        print(f"  初始资金:  ${mm['initial_capital']:,.0f}")
        print(f"  单次交易:  ${mm['stkmoney']:,.0f}")
        print(f"  止损设置:  移动止损={mm['stoploss']*100:.1f}%, 固定止损={mm['lossrate']*100:.1f}%")

        # 回测参数
        print("\n【回测参数】")
        bt = self.params['backtest']
        print(f"  起始索引:  {bt['start_index']}")
        print(f"  手续费率:  {bt['commission']*100:.2f}%")
        print(f"  滑点:     {bt['slippage']*100:.2f}%")

        print("\n" + "=" * 60)

    def update_signal_param(self, param_name: str, value: int):
        """
        更新信号计算参数

        Args:
            param_name: 参数名 (M1, M2, M3, M4, M99, N, SHORT, LONG, MID)
            value: 新值
        """
        if param_name not in self.params['signal_params']:
            raise ValueError(f"无效的参数名: {param_name}")

        old_value = self.params['signal_params'][param_name]
        self.params['signal_params'][param_name] = int(value)
        self._save_params()
        print(f"✓ {param_name}: {old_value} → {value}")

    def update_buy_condition(self, param_name: str, value: float):
        """
        更新买入条件参数

        Args:
            param_name: 参数名 (HA_threshold, WD3_max, QS_threshold)
            value: 新值
        """
        if param_name not in self.params['trading_conditions']['buy']:
            raise ValueError(f"无效的买入参数: {param_name}")

        old_value = self.params['trading_conditions']['buy'][param_name]
        self.params['trading_conditions']['buy'][param_name] = float(value)
        self._save_params()
        print(f"✓ 买入-{param_name}: {old_value} → {value}")

    def update_sell_condition(self, param_name: str, value: float):
        """
        更新卖出条件参数

        Args:
            param_name: 参数名 (QJ_threshold, WD3_threshold)
            value: 新值
        """
        if param_name not in self.params['trading_conditions']['sell']:
            raise ValueError(f"无效的卖出参数: {param_name}")

        old_value = self.params['trading_conditions']['sell'][param_name]
        self.params['trading_conditions']['sell'][param_name] = float(value)
        self._save_params()
        print(f"✓ 卖出-{param_name}: {old_value} → {value}")

    def update_money_management(self, param_name: str, value: float):
        """
        更新资金管理参数

        Args:
            param_name: 参数名
            value: 新值
        """
        if param_name not in self.params['money_management']:
            raise ValueError(f"无效的资金管理参数: {param_name}")

        old_value = self.params['money_management'][param_name]
        self.params['money_management'][param_name] = float(value)
        self._save_params()
        print(f"✓ {param_name}: {old_value} → {value}")

    def reset_to_default(self):
        """重置为默认参数"""
        self.params = DEFAULT_STRATEGY_PARAMS.copy()
        self._save_params()
        print("✓ 已重置为默认参数")

    def batch_update(self, updates: dict):
        """
        批量更新参数

        Args:
            updates: 更新字典，格式如:
            {
                'signal_params': {'M1': 6, 'M2': 12},
                'trading_conditions.buy': {'HA_threshold': 30000},
                ...
            }
        """
        for category, params in updates.items():
            if '.' in category:
                # 嵌套路径
                parts = category.split('.')
                target = self.params
                for part in parts:
                    target = target[part]
                target.update(params)
            else:
                self.params[category].update(params)

        self._save_params()
        print(f"✓ 批量更新完成: {len(updates)} 个类别")


def interactive_menu():
    """交互式菜单"""
    tuner = StrategyTuner()

    while True:
        print("\n" + "=" * 50)
        print("      策略参数微调工具")
        print("=" * 50)
        print("1. 查看当前参数")
        print("2. 修改信号参数 (MA/MACD)")
        print("3. 修改买入条件")
        print("4. 修改卖出条件")
        print("5. 修改资金管理")
        print("6. 重置为默认参数")
        print("7. 快速优化预设")
        print("0. 退出")
        print("-" * 50)

        choice = input("请选择操作: ").strip()

        if choice == '0':
            print("再见!")
            break

        elif choice == '1':
            tuner.show_current_params()

        elif choice == '2':
            print("\n信号参数: M1, M2, M3, M4, M99, N, SHORT, LONG, MID")
            param = input("参数名: ").strip().upper()
            try:
                value = int(input("新值: "))
                tuner.update_signal_param(param, value)
            except Exception as e:
                print(f"错误: {e}")

        elif choice == '3':
            print("\n买入参数: HA_threshold, WD3_max, QS_threshold")
            param = input("参数名: ").strip()
            try:
                value = float(input("新值: "))
                tuner.update_buy_condition(param, value)
            except Exception as e:
                print(f"错误: {e}")

        elif choice == '4':
            print("\n卖出参数: QJ_threshold, WD3_threshold")
            param = input("参数名: ").strip()
            try:
                value = float(input("新值: "))
                tuner.update_sell_condition(param, value)
            except Exception as e:
                print(f"错误: {e}")

        elif choice == '5':
            print("\n资金参数: initial_capital, stkmoney, stoploss, lossrate, position_ratio")
            param = input("参数名: ").strip()
            try:
                value = float(input("新值: "))
                tuner.update_money_management(param, value)
            except Exception as e:
                print(f"错误: {e}")

        elif choice == '6':
            confirm = input("确认重置为默认参数? (y/n): ")
            if confirm.lower() == 'y':
                tuner.reset_to_default()

        elif choice == '7':
            print("\n预设方案:")
            print("1. 保守型 - 高阈值，低风险")
            print("2. 激进型 - 低阈值，高收益")
            print("3. 平衡型 - 默认参数")

            preset = input("选择预设: ").strip()

            if preset == '1':
                tuner.batch_update({
                    'trading_conditions': {
                        'buy': {'HA_threshold': 30000, 'WD3_max': 120, 'QS_threshold': 1500},
                        'sell': {'QJ_threshold': 40000, 'WD3_threshold': 180}
                    }
                })
                print("✓ 已应用保守型预设")

            elif preset == '2':
                tuner.batch_update({
                    'trading_conditions': {
                        'buy': {'HA_threshold': 20000, 'WD3_max': 180, 'QS_threshold': 1000},
                        'sell': {'QJ_threshold': 60000, 'WD3_threshold': 220}
                    }
                })
                print("✓ 已应用激进型预设")

            elif preset == '3':
                tuner.reset_to_default()

        else:
            print("无效选择")


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description='策略参数微调工具')
    parser.add_argument('--show', action='store_true', help='显示当前参数')
    parser.add_argument('--reset', action='store_true', help='重置为默认参数')
    parser.add_argument('--set', type=str, help='设置参数，格式: 类别.参数=值')
    parser.add_argument('--interactive', '-i', action='store_true', help='交互式模式')

    args = parser.parse_args()

    tuner = StrategyTuner()

    if args.show:
        tuner.show_current_params()

    elif args.reset:
        tuner.reset_to_default()
        tuner.show_current_params()

    elif args.set:
        # 解析设置命令: signal_params.M1=6
        try:
            path, value = args.set.split('=')
            parts = path.split('.')

            if len(parts) == 2:
                category, param = parts
                if category == 'signal_params':
                    tuner.update_signal_param(param, int(value))
                elif category == 'money_management':
                    tuner.update_money_management(param, float(value))
            elif len(parts) == 3:
                category, sub, param = parts
                if sub == 'buy':
                    tuner.update_buy_condition(param, float(value))
                elif sub == 'sell':
                    tuner.update_sell_condition(param, float(value))

        except Exception as e:
            print(f"设置失败: {e}")
            print("格式示例: --set signal_params.M1=6")

    elif args.interactive:
        interactive_menu()

    else:
        # 默认进入交互模式
        interactive_menu()


if __name__ == '__main__':
    main()
