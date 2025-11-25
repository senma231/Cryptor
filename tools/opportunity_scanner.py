# -*- coding: utf-8 -*-
"""
机会交易对扫描器
实时监控多个交易对，通过指标分析找出交易机会
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import time
from datetime import datetime
from typing import List, Dict, Optional
import pandas as pd
from loguru import logger
from tools.exchange_factory import ExchangeFactory
from strategies.crypto_signals import SignalCalculator


class OpportunityScanner:
    """机会交易对扫描器"""
    
    def __init__(
        self,
        exchange: str = 'binance',
        market_type: str = 'spot',
        interval: str = '15m',
        min_volume_usdt: float = 1000000.0,  # 最小24h成交量（USDT）
        include_mainstream: bool = True,
        include_altcoins: bool = True
    ):
        """
        初始化扫描器
        
        Args:
            exchange: 交易所名称
            market_type: 市场类型
            interval: K线周期
            min_volume_usdt: 最小24h成交量
            include_mainstream: 是否包含主流币
            include_altcoins: 是否包含山寨币
        """
        self.exchange_name = exchange
        self.market_type = market_type
        self.interval = interval
        self.min_volume_usdt = min_volume_usdt
        self.include_mainstream = include_mainstream
        self.include_altcoins = include_altcoins
        
        # 创建交易所实例
        self.exchange = ExchangeFactory.create(exchange, market_type)
        
        # 主流币列表
        self.mainstream_coins = [
            'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT',
            'ADAUSDT', 'DOGEUSDT', 'MATICUSDT', 'DOTUSDT', 'LTCUSDT',
            'AVAXUSDT', 'LINKUSDT', 'ATOMUSDT', 'UNIUSDT', 'ETCUSDT'
        ]
        
        # 扫描结果
        self.opportunities = []
        
        logger.info(f"✓ 机会扫描器初始化: {exchange.upper()} ({market_type})")
        logger.info(f"  K线周期: {interval}")
        logger.info(f"  最小成交量: ${min_volume_usdt:,.0f}")
        logger.info(f"  主流币: {'包含' if include_mainstream else '排除'}")
        logger.info(f"  山寨币: {'包含' if include_altcoins else '排除'}")
    
    def get_scan_symbols(self) -> List[str]:
        """获取要扫描的交易对列表"""
        all_symbols = self.exchange.get_all_symbols()
        
        # 过滤USDT交易对
        usdt_symbols = [s for s in all_symbols if s.endswith('USDT')]
        
        # 根据配置过滤
        scan_symbols = []
        
        for symbol in usdt_symbols:
            is_mainstream = symbol in self.mainstream_coins
            
            if is_mainstream and self.include_mainstream:
                scan_symbols.append(symbol)
            elif not is_mainstream and self.include_altcoins:
                scan_symbols.append(symbol)
        
        logger.info(f"✓ 获取到 {len(scan_symbols)} 个交易对")
        
        return scan_symbols
    
    def analyze_symbol(self, symbol: str) -> Optional[Dict]:
        """
        分析单个交易对
        
        Returns:
            如果有机会返回分析结果，否则返回None
        """
        try:
            # 获取K线数据
            df = self.exchange.get_klines(symbol, self.interval, limit=200)
            
            if df is None or len(df) < 100:
                return None
            
            # 计算信号
            signal_calc = SignalCalculator(symbol, self.market_type)
            signals = signal_calc.calculate_signals(df)
            
            if not signals:
                return None
            
            # 获取当前价格
            current_price = self.exchange.get_current_price(symbol)
            
            if current_price is None:
                return None
            
            # 判断是否有买入机会
            buy_signal = (
                signals['HA'] == 1 and  # HA指标看涨
                signals['WD3'] > 0 and  # WD3指标看涨
                signals['QS'] > 0       # QS指标看涨
            )
            
            # 判断是否有卖出信号（避免）
            sell_signal = (
                signals['QJ'] == 1 or   # QJ指标看跌
                signals['WD3'] < 0      # WD3指标看跌
            )
            
            if buy_signal and not sell_signal:
                # 计算24h涨跌幅
                price_change_24h = ((df['close'].iloc[-1] - df['close'].iloc[-24]) / 
                                   df['close'].iloc[-24] * 100) if len(df) >= 24 else 0
                
                return {
                    'symbol': symbol,
                    'exchange': self.exchange_name,
                    'price': current_price,
                    'price_change_24h': price_change_24h,
                    'signals': signals,
                    'timestamp': datetime.now(),
                    'is_mainstream': symbol in self.mainstream_coins
                }
        
        except Exception as e:
            logger.debug(f"分析 {symbol} 失败: {e}")
        
        return None

    def scan_once(self) -> List[Dict]:
        """执行一次扫描"""
        logger.info(f"\n{'='*80}")
        logger.info(f"开始扫描 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*80}")

        # 获取要扫描的交易对
        symbols = self.get_scan_symbols()

        opportunities = []
        scanned = 0

        for symbol in symbols:
            scanned += 1

            if scanned % 10 == 0:
                logger.info(f"进度: {scanned}/{len(symbols)}")

            result = self.analyze_symbol(symbol)

            if result:
                opportunities.append(result)
                logger.success(f"✅ 发现机会: {symbol}")

            # 避免请求过快
            time.sleep(0.1)

        logger.info(f"\n扫描完成: 发现 {len(opportunities)} 个机会")

        return opportunities

    def display_opportunities(self, opportunities: List[Dict]):
        """显示发现的机会"""
        if not opportunities:
            print("\n❌ 未发现交易机会")
            return

        print(f"\n{'='*100}")
        print(f"发现 {len(opportunities)} 个交易机会")
        print(f"{'='*100}")

        # 按24h涨跌幅排序
        opportunities.sort(key=lambda x: x['price_change_24h'], reverse=True)

        print(f"\n{'序号':<4} {'交易对':<12} {'类型':<6} {'价格':<12} {'24h涨跌':<10} {'HA':<4} {'WD3':<6} {'QS':<6}")
        print("-" * 100)

        for i, opp in enumerate(opportunities, 1):
            coin_type = '主流' if opp['is_mainstream'] else '山寨'

            print(f"{i:<4} {opp['symbol']:<12} {coin_type:<6} "
                  f"${opp['price']:<11.4f} {opp['price_change_24h']:+.2f}% "
                  f"{opp['signals']['HA']:<4} {opp['signals']['WD3']:<6.2f} {opp['signals']['QS']:<6.2f}")

        print("-" * 100)

    def run_continuous(self, scan_interval: int = 300):
        """
        持续扫描

        Args:
            scan_interval: 扫描间隔（秒）
        """
        logger.info(f"\n开始持续扫描，间隔 {scan_interval} 秒")
        logger.info("按 Ctrl+C 停止\n")

        try:
            while True:
                opportunities = self.scan_once()
                self.opportunities = opportunities
                self.display_opportunities(opportunities)

                # 如果有机会，发送提醒
                if opportunities:
                    self.send_alert(opportunities)

                logger.info(f"\n等待 {scan_interval} 秒后进行下一次扫描...")
                time.sleep(scan_interval)

        except KeyboardInterrupt:
            logger.info("\n\n扫描已停止")

    def send_alert(self, opportunities: List[Dict]):
        """发送提醒（可以扩展为邮件、微信等）"""
        # 简单的控制台提醒
        print("\n" + "🔔" * 50)
        print(f"⚠️  发现 {len(opportunities)} 个交易机会！")

        for opp in opportunities[:5]:  # 只显示前5个
            print(f"   • {opp['symbol']}: ${opp['price']:.4f} ({opp['price_change_24h']:+.2f}%)")

        print("🔔" * 50 + "\n")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='机会交易对扫描器')
    parser.add_argument('--exchange', type=str, default='binance',
                        choices=['binance', 'okx', 'htx'],
                        help='交易所')
    parser.add_argument('--market', type=str, default='spot',
                        choices=['spot', 'futures'],
                        help='市场类型')
    parser.add_argument('--interval', type=str, default='15m',
                        help='K线周期')
    parser.add_argument('--min-volume', type=float, default=1000000.0,
                        help='最小24h成交量（USDT）')
    parser.add_argument('--no-mainstream', action='store_true',
                        help='排除主流币')
    parser.add_argument('--no-altcoins', action='store_true',
                        help='排除山寨币')
    parser.add_argument('--scan-interval', type=int, default=300,
                        help='扫描间隔（秒）')
    parser.add_argument('--once', action='store_true',
                        help='只扫描一次')

    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════════════════════╗
║            机会交易对扫描器                              ║
║        Opportunity Scanner                             ║
╠══════════════════════════════════════════════════════════╣
║  交易所:   {args.exchange.upper():40s}  ║
║  市场:     {'现货' if args.market == 'spot' else '合约':40s}  ║
║  K线周期:  {args.interval:40s}  ║
║  主流币:   {'排除' if args.no_mainstream else '包含':40s}  ║
║  山寨币:   {'排除' if args.no_altcoins else '包含':40s}  ║
╚══════════════════════════════════════════════════════════╝
""")

    scanner = OpportunityScanner(
        exchange=args.exchange,
        market_type=args.market,
        interval=args.interval,
        min_volume_usdt=args.min_volume,
        include_mainstream=not args.no_mainstream,
        include_altcoins=not args.no_altcoins
    )

    if args.once:
        opportunities = scanner.scan_once()
        scanner.display_opportunities(opportunities)
    else:
        scanner.run_continuous(args.scan_interval)


if __name__ == '__main__':
    main()


