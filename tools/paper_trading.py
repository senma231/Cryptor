# -*- coding: utf-8 -*-
"""
模拟交易工具（Paper Trading）
使用实时数据，虚拟资金，不真实下单
"""

import warnings
warnings.filterwarnings('ignore', category=Warning, module='urllib3')

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime, timedelta
import time
import json
from loguru import logger
from tools.live_monitor import LiveDataMonitor
from tools.crypto_config import load_strategy_params
from tools.price_precision import format_price, get_symbol_precision, format_amount
from tools.notifier import Notifier


class PaperTrader:
    """模拟交易器"""

    def __init__(
        self,
        symbol: str = 'BTCUSDT',
        market_type: str = 'spot',
        exchange: str = 'binance',
        initial_capital: float = 10000.0,
        enable_fees: bool = True,
        enable_slippage: bool = True,
        enable_stop_loss: bool = True,
        enable_take_profit: bool = True
    ):
        """
        初始化模拟交易器

        Args:
            symbol: 交易对
            market_type: 市场类型
            exchange: 交易所名称 ('binance', 'okx', 'htx')
            initial_capital: 初始资金
            enable_fees: 是否启用手续费
            enable_slippage: 是否启用滑点
            enable_stop_loss: 是否启用止损
            enable_take_profit: 是否启用止盈
        """
        self.symbol = symbol
        self.market_type = market_type
        self.exchange_name = exchange
        self.initial_capital = initial_capital

        # 交易状态
        self.capital = initial_capital
        self.position = 0.0  # 持仓数量
        self.entry_price = 0.0
        self.trades = []

        # 手续费和滑点配置
        self.enable_fees = enable_fees
        self.enable_slippage = enable_slippage
        self.fee_rate_spot = 0.001      # 现货手续费 0.1%
        self.fee_rate_futures = 0.0004  # 合约手续费 0.04%
        self.slippage_rate = 0.0005     # 滑点 0.05%

        # 止盈止损配置
        self.enable_stop_loss = enable_stop_loss
        self.enable_take_profit = enable_take_profit
        self.take_profit_rate = 0.10    # 止盈比率 10%
        self.stop_loss_rate = 0.05      # 止损比率 5%
        self.trailing_stop_rate = 0.03  # 移动止损 3%
        self.highest_price = 0.0        # 持仓期间最高价

        # 统计数据
        self.total_fees = 0.0
        self.stop_loss_count = 0
        self.take_profit_count = 0

        # 数据监控器
        self.monitor = LiveDataMonitor(symbol, market_type, exchange)

        # 策略参数
        try:
            self.params = load_strategy_params()
        except Exception:
            from tools.crypto_config import DEFAULT_STRATEGY_PARAMS
            self.params = DEFAULT_STRATEGY_PARAMS

        # 交易记录文件
        self.log_file = Path(f'paper_trading_{symbol}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')

        # 价格精度
        self.price_precision = get_symbol_precision(symbol)

        # 通知器
        self.notifier = Notifier()

        # 运行时间记录
        self.start_time = None
        self.last_report_time = None

        logger.info(f"✓ 模拟交易初始化: {symbol} ({market_type}) - {exchange.upper()}")
        logger.info(f"  初始资金: ${initial_capital:,.2f}")
        logger.info(f"  手续费: {'启用' if enable_fees else '禁用'} ({self._get_fee_rate()*100:.3f}%)")
        logger.info(f"  滑点: {'启用' if enable_slippage else '禁用'} ({self.slippage_rate*100:.3f}%)")
        logger.info(f"  止损: {'启用' if enable_stop_loss else '禁用'} ({self.stop_loss_rate*100:.1f}%)")
        logger.info(f"  止盈: {'启用' if enable_take_profit else '禁用'} ({self.take_profit_rate*100:.1f}%)")

    def _get_fee_rate(self) -> float:
        """获取手续费率"""
        if not self.enable_fees:
            return 0.0
        return self.fee_rate_futures if self.market_type == 'futures' else self.fee_rate_spot

    def _apply_slippage(self, price: float, is_buy: bool) -> float:
        """应用滑点"""
        if not self.enable_slippage:
            return price

        # 买入时价格上涨，卖出时价格下跌
        if is_buy:
            return price * (1 + self.slippage_rate)
        else:
            return price * (1 - self.slippage_rate)

    def _check_stop_conditions(self, current_price: float) -> tuple:
        """
        检查止盈止损条件

        Returns:
            (take_profit_triggered, stop_loss_triggered)
        """
        if self.position == 0:
            return False, False

        # 更新最高价
        if current_price > self.highest_price:
            self.highest_price = current_price

        # 计算当前盈亏比率
        pnl_rate = (current_price - self.entry_price) / self.entry_price

        # 检查止盈
        take_profit_triggered = False
        if self.enable_take_profit and pnl_rate >= self.take_profit_rate:
            take_profit_triggered = True

        # 检查止损
        stop_loss_triggered = False
        if self.enable_stop_loss:
            # 固定止损
            if pnl_rate <= -self.stop_loss_rate:
                stop_loss_triggered = True

            # 移动止损（从最高点回撤）
            if self.highest_price > self.entry_price:
                drawdown_from_high = (self.highest_price - current_price) / self.highest_price
                if drawdown_from_high >= self.trailing_stop_rate:
                    stop_loss_triggered = True

        return take_profit_triggered, stop_loss_triggered

    def buy(self, price: float, reason: str = ""):
        """模拟买入"""
        if self.position > 0:
            logger.warning("已有持仓，不能重复买入")
            return False

        # 应用滑点
        actual_price = self._apply_slippage(price, is_buy=True)

        # 计算手续费
        fee_rate = self._get_fee_rate()
        fee = self.capital * fee_rate
        self.total_fees += fee

        # 扣除手续费后的可用资金
        available_capital = self.capital - fee

        # 计算持仓数量
        self.position = available_capital / actual_price
        self.entry_price = actual_price
        self.highest_price = actual_price  # 初始化最高价

        trade = {
            'time': datetime.now().isoformat(),
            'action': 'BUY',
            'price': price,
            'actual_price': actual_price,
            'slippage': actual_price - price,
            'amount': self.position,
            'fee': fee,
            'capital_before': self.capital,
            'reason': reason
        }
        self.trades.append(trade)

        price_str = format_price(actual_price, self.price_precision)
        amount_str = format_amount(self.position)
        logger.info(f"✅ 模拟买入: ${price_str} x {amount_str}")
        if self.enable_slippage:
            logger.info(f"   滑点: ${actual_price - price:.2f}")
        if self.enable_fees:
            logger.info(f"   手续费: ${fee:.2f}")
        logger.info(f"   原因: {reason}")

        return True

    def sell(self, price: float, reason: str = ""):
        """模拟卖出"""
        if self.position == 0:
            logger.warning("无持仓，不能卖出")
            return False

        # 应用滑点
        actual_price = self._apply_slippage(price, is_buy=False)

        # 计算卖出金额
        sell_amount = self.position * actual_price

        # 计算手续费
        fee_rate = self._get_fee_rate()
        fee = sell_amount * fee_rate
        self.total_fees += fee

        # 扣除手续费后的实际收入
        self.capital = sell_amount - fee

        # 计算盈亏
        pnl = (actual_price - self.entry_price) / self.entry_price
        pnl_amount = self.capital - self.trades[-1]['capital_before']

        trade = {
            'time': datetime.now().isoformat(),
            'action': 'SELL',
            'price': price,
            'actual_price': actual_price,
            'slippage': price - actual_price,
            'amount': self.position,
            'fee': fee,
            'capital': self.capital,
            'pnl': pnl * 100,
            'pnl_amount': pnl_amount,
            'reason': reason
        }
        self.trades.append(trade)

        price_str = format_price(actual_price, self.price_precision)
        amount_str = format_amount(self.position)
        logger.info(f"✅ 模拟卖出: ${price_str} x {amount_str}")
        if self.enable_slippage:
            logger.info(f"   滑点: ${price - actual_price:.2f}")
        if self.enable_fees:
            logger.info(f"   手续费: ${fee:.2f}")
        logger.info(f"   盈亏: {pnl*100:+.2f}% (${pnl_amount:+,.2f})")
        logger.info(f"   资金: ${self.capital:,.2f}")
        logger.info(f"   原因: {reason}")

        self.position = 0.0
        self.entry_price = 0.0
        self.highest_price = 0.0

        return True

    def get_performance(self):
        """获取表现统计"""
        if not self.trades:
            return None

        buy_count = len([t for t in self.trades if t['action'] == 'BUY'])
        return_pct = (self.capital - self.initial_capital) / self.initial_capital * 100

        wins = [t for t in self.trades if 'pnl' in t and t['pnl'] > 0]
        losses = [t for t in self.trades if 'pnl' in t and t['pnl'] < 0]

        return {
            'total_trades': buy_count,
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': len(wins) / max(buy_count, 1) * 100,
            'return_pct': return_pct,
            'initial_capital': self.initial_capital,
            'final_capital': self.capital,
            'total_fees': self.total_fees,
            'fee_rate_pct': self.total_fees / self.initial_capital * 100,
            'stop_loss_count': self.stop_loss_count,
            'take_profit_count': self.take_profit_count
        }

    def generate_report(self, report_type: str = 'daily') -> str:
        """
        生成报告文本

        Args:
            report_type: 报告类型 ('daily' 或 'final')

        Returns:
            报告文本
        """
        now = datetime.now()

        # 计算运行时间
        if self.start_time:
            runtime = now - self.start_time
            runtime_str = f"{runtime.days}天 {runtime.seconds // 3600}小时 {(runtime.seconds % 3600) // 60}分钟"
        else:
            runtime_str = "未知"

        # 获取当前价格
        current_price = self.monitor.get_current_price()
        price_str = f"${current_price:.4f}" if current_price else "获取失败"

        # 基本信息
        report = f"""
交易对: {self.symbol}
市场类型: {'现货' if self.market_type == 'spot' else '合约'}
交易所: {self.exchange_name.upper()}
运行时间: {runtime_str}
当前价格: {price_str}
当前持仓: {'有 ({:.4f})'.format(self.position) if self.position > 0 else '无'}
"""

        # 性能统计
        if self.trades:
            perf = self.get_performance()
            profit_loss = perf['final_capital'] - perf['initial_capital']

            report += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 交易统计
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
初始资金: ${perf['initial_capital']:,.2f}
当前资金: ${perf['final_capital']:,.2f}
盈亏金额: ${profit_loss:+,.2f}
收益率: {perf['return_pct']:+.2f}%

交易次数: {perf['total_trades']}
盈利次数: {perf['wins']}
亏损次数: {perf['losses']}
胜率: {perf['win_rate']:.1f}%

总手续费: ${perf['total_fees']:,.2f} ({perf['fee_rate_pct']:.2f}%)
止盈次数: {perf['take_profit_count']}
止损次数: {perf['stop_loss_count']}
"""
        else:
            report += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 交易统计
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
初始资金: ${self.initial_capital:,.2f}
当前资金: ${self.capital:,.2f}

暂无交易记录
"""

        # 最近交易
        if self.trades:
            recent_trades = self.trades[-5:]  # 最近5笔交易
            report += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            report += "📝 最近交易\n"
            report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            for trade in recent_trades:
                time_str = trade['time'][:19]  # 只取日期和时间部分
                action = trade['action']
                price = trade['actual_price']

                if action == 'BUY':
                    report += f"{time_str} | 买入 @ ${price:.4f}\n"
                else:
                    pnl = trade.get('pnl', 0) * 100
                    report += f"{time_str} | 卖出 @ ${price:.4f} | 盈亏: {pnl:+.2f}%\n"

        return report

    def save_log(self):
        """保存交易记录"""
        log_data = {
            'symbol': self.symbol,
            'market_type': self.market_type,
            'start_time': self.trades[0]['time'] if self.trades else None,
            'end_time': datetime.now().isoformat(),
            'performance': self.get_performance(),
            'trades': self.trades
        }

        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)

        logger.info(f"交易记录已保存: {self.log_file}")

    def run(self, interval: str = '1h', check_interval: int = 60):
        """
        运行模拟交易

        Args:
            interval: K线周期
            check_interval: 检查间隔（秒）
        """
        logger.info(f"开始模拟交易 {self.symbol}")
        logger.info(f"K线周期: {interval}, 检查间隔: {check_interval}秒")
        logger.info("按 Ctrl+C 停止\n")

        # 记录开始时间
        self.start_time = datetime.now()
        self.last_report_time = self.start_time

        # 发送启动通知
        start_msg = f"""
交易对: {self.symbol}
市场类型: {'现货' if self.market_type == 'spot' else '合约'}
交易所: {self.exchange_name.upper()}
初始资金: ${self.initial_capital:,.2f}
K线周期: {interval}
检查间隔: {check_interval}秒

手续费: {'启用' if self.enable_fees else '禁用'}
滑点: {'启用' if self.enable_slippage else '禁用'}
止损: {'启用' if self.enable_stop_loss else '禁用'}
止盈: {'启用' if self.enable_take_profit else '禁用'}
"""
        self.notifier.send("🚀 模拟交易已启动", start_msg, 'info')

        try:
            while True:
                # 获取当前价格
                price = self.monitor.get_current_price()

                # 计算信号
                signals = self.monitor.calculate_live_signals(interval)

                if signals and price:
                    # 检查止盈止损
                    if self.position > 0:
                        take_profit_triggered, stop_loss_triggered = self._check_stop_conditions(price)

                        if take_profit_triggered:
                            self.take_profit_count += 1
                            self.sell(price, f"止盈触发 (盈利{self.take_profit_rate*100:.1f}%)")
                            continue

                        if stop_loss_triggered:
                            self.stop_loss_count += 1
                            pnl = (price - self.entry_price) / self.entry_price
                            if pnl <= -self.stop_loss_rate:
                                self.sell(price, f"固定止损触发 (亏损{abs(pnl)*100:.1f}%)")
                            else:
                                drawdown = (self.highest_price - price) / self.highest_price
                                self.sell(price, f"移动止损触发 (从高点回撤{drawdown*100:.1f}%)")
                            continue

                    # 检查交易信号
                    action = self.monitor.check_trading_signal(signals)

                    # 显示状态
                    price_str = format_price(price, self.price_precision)
                    position_str = format_amount(self.position) if self.position > 0 else '无'
                    print(f"\n{'='*60}")
                    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"价格: ${price_str}")
                    print(f"持仓: {position_str if self.position == 0 else '有 (' + position_str + ')'}")
                    print(f"资金: ${self.capital:,.2f}")

                    # 如果有持仓，显示盈亏和止盈止损状态
                    if self.position > 0:
                        pnl = (price - self.entry_price) / self.entry_price
                        print(f"浮动盈亏: {pnl*100:+.2f}%")
                        print(f"最高价: ${format_price(self.highest_price, self.price_precision)}")
                        if self.enable_take_profit:
                            print(f"止盈线: ${format_price(self.entry_price * (1 + self.take_profit_rate), self.price_precision)} (+{self.take_profit_rate*100:.1f}%)")
                        if self.enable_stop_loss:
                            print(f"止损线: ${format_price(self.entry_price * (1 - self.stop_loss_rate), self.price_precision)} (-{self.stop_loss_rate*100:.1f}%)")

                    # 执行交易
                    if action == 'BUY' and self.position == 0:
                        reason = f"HA={signals['HA']}, WD3={signals['WD3']}"
                        self.buy(price, reason)

                    elif action == 'SELL' and self.position > 0:
                        reason = f"QJ={signals['QJ']}, WD3={signals['WD3']}"
                        self.sell(price, reason)

                    # 显示收益
                    if self.trades:
                        perf = self.get_performance()
                        print(f"\n📊 当前表现:")
                        print(f"   交易次数: {perf['total_trades']}")
                        print(f"   胜率: {perf['win_rate']:.1f}%")
                        print(f"   总收益: {perf['return_pct']:+.2f}%")
                        print(f"   总手续费: ${perf['total_fees']:,.2f} ({perf['fee_rate_pct']:.2f}%)")
                        if self.enable_stop_loss:
                            print(f"   止损次数: {perf['stop_loss_count']}")
                        if self.enable_take_profit:
                            print(f"   止盈次数: {perf['take_profit_count']}")

                    print(f"{'='*60}")

                # 检查是否需要发送24小时报告
                now = datetime.now()
                if self.last_report_time:
                    time_since_last_report = now - self.last_report_time
                    if time_since_last_report >= timedelta(hours=24):
                        # 生成并发送24小时报告
                        report = self.generate_report('daily')
                        self.notifier.send("📊 24小时交易报告", report, 'info')
                        self.last_report_time = now
                        logger.info("✓ 已发送24小时报告")

                # 等待
                time.sleep(check_interval)

        except KeyboardInterrupt:
            logger.info("\n\n模拟交易已停止")

            # 如果有持仓，平仓
            if self.position > 0:
                price = self.monitor.get_current_price()
                if price:
                    self.sell(price, "手动停止")

            # 显示最终统计
            if self.trades:
                print("\n" + "="*80)
                print("最终交易统计")
                print("="*80)

                perf = self.get_performance()
                print(f"初始资金:    ${perf['initial_capital']:,.2f}")
                print(f"最终资金:    ${perf['final_capital']:,.2f}")
                print(f"总收益率:    {perf['return_pct']:+.2f}%")
                print(f"总手续费:    ${perf['total_fees']:,.2f} ({perf['fee_rate_pct']:.2f}%)")
                print(f"交易次数:    {perf['total_trades']}")
                print(f"盈利次数:    {perf['wins']}")
                print(f"亏损次数:    {perf['losses']}")
                print(f"胜率:        {perf['win_rate']:.1f}%")
                if self.enable_stop_loss:
                    print(f"止损次数:    {perf['stop_loss_count']}")
                if self.enable_take_profit:
                    print(f"止盈次数:    {perf['take_profit_count']}")
                print("="*80)

            # 保存记录
            self.save_log()

            # 发送最终报告通知
            final_report = self.generate_report('final')
            self.notifier.send("🏁 模拟交易已结束 - 最终报告", final_report, 'info')
            logger.info("✓ 已发送最终报告")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='模拟交易工具（Paper Trading）')
    parser.add_argument('--exchange', type=str, default='binance',
                        choices=['binance', 'okx', 'htx'],
                        help='交易所')
    parser.add_argument('--symbol', type=str, default='BTCUSDT',
                        help='交易对')
    parser.add_argument('--market', type=str, default='spot',
                        choices=['spot', 'futures'],
                        help='市场类型')
    parser.add_argument('--capital', type=float, default=10000.0,
                        help='初始资金')
    parser.add_argument('--interval', type=str, default='1h',
                        help='K线周期')
    parser.add_argument('--check', type=int, default=60,
                        help='检查间隔（秒）')
    parser.add_argument('--no-fees', action='store_true',
                        help='禁用手续费')
    parser.add_argument('--no-slippage', action='store_true',
                        help='禁用滑点')
    parser.add_argument('--no-stop-loss', action='store_true',
                        help='禁用止损')
    parser.add_argument('--no-take-profit', action='store_true',
                        help='禁用止盈')

    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════════════════════╗
║              模拟交易工具                                ║
║         Paper Trading (No Real Money)                  ║
╠══════════════════════════════════════════════════════════╣
║  交易所:   {args.exchange.upper():40s}  ║
║  交易对:   {args.symbol:40s}  ║
║  市场:     {'现货' if args.market == 'spot' else '合约':40s}  ║
║  初始资金: ${args.capital:,.2f}{' '*(38-len(f'{args.capital:,.2f}'))}  ║
║  K线周期:  {args.interval:40s}  ║
║  手续费:   {'禁用' if args.no_fees else '启用':40s}  ║
║  滑点:     {'禁用' if args.no_slippage else '启用':40s}  ║
║  止损:     {'禁用' if args.no_stop_loss else '启用':40s}  ║
║  止盈:     {'禁用' if args.no_take_profit else '启用':40s}  ║
╚══════════════════════════════════════════════════════════╝

⚠️  注意: 这是模拟交易，使用虚拟资金，不会真实下单
✅  优点: 验证策略，积累经验，零风险
""")

    trader = PaperTrader(
        symbol=args.symbol,
        market_type=args.market,
        exchange=args.exchange,
        initial_capital=args.capital,
        enable_fees=not args.no_fees,
        enable_slippage=not args.no_slippage,
        enable_stop_loss=not args.no_stop_loss,
        enable_take_profit=not args.no_take_profit
    )
    trader.run(args.interval, args.check)


if __name__ == '__main__':
    main()
