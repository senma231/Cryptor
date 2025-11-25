#!/usr/bin/env python3
"""
山寨币交易工具
专门针对DOGE、SHIB、SUI等高波动币种优化
"""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import json
import argparse
from tools.paper_trading import PaperTrader
from loguru import logger

# 配置日志
logger.remove()
logger.add(sys.stdout, level="INFO")


def load_altcoin_params():
    """加载山寨币参数配置"""
    config_path = project_root / 'config' / 'altcoin_strategy_params.json'
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        return None


def get_coin_params(symbol: str, market: str, config: dict):
    """
    获取特定币种的参数
    
    Args:
        symbol: 交易对（如DOGEUSDT）
        market: 市场类型（spot/futures）
        config: 配置字典
    
    Returns:
        参数字典
    """
    # 构建配置键
    if market == 'futures':
        config_key = f"{symbol}_FUTURES"
    else:
        config_key = symbol
    
    # 获取币种特定参数
    coin_params = config['coin_specific_params'].get(config_key)
    
    if not coin_params:
        logger.warning(f"未找到 {config_key} 的特定参数，使用默认参数")
        return config['default_params']
    
    return coin_params


def print_coin_info(symbol: str, market: str, params: dict, capital: float):
    """打印币种信息"""
    print(f"""
╔══════════════════════════════════════════════════════════╗
║              山寨币交易工具                              ║
║         Altcoin Trading Tool                           ║
╠══════════════════════════════════════════════════════════╣
║  交易对:   {symbol:40s}  ║
║  市场:     {'现货' if market == 'spot' else '合约':40s}  ║
║  类型:     {params.get('type', '未知'):40s}  ║
║  风险等级: {params.get('risk_level', '未知'):40s}  ║
╠══════════════════════════════════════════════════════════╣
║  初始资金: ${capital:,.2f}{' '*(38-len(f'{capital:,.2f}'))}  ║
║  止盈率:   {params['params']['take_profit_rate']*100:.1f}%{' '*(38-len(f"{params['params']['take_profit_rate']*100:.1f}%"))}  ║
║  止损率:   {params['params']['stop_loss_rate']*100:.1f}%{' '*(38-len(f"{params['params']['stop_loss_rate']*100:.1f}%"))}  ║
║  移动止损: {params['params']['trailing_stop_rate']*100:.1f}%{' '*(38-len(f"{params['params']['trailing_stop_rate']*100:.1f}%"))}  ║
║  滑点:     {params['params']['slippage_rate']*100:.2f}%{' '*(38-len(f"{params['params']['slippage_rate']*100:.2f}%"))}  ║
║  最大仓位: {params['params']['max_position_ratio']*100:.0f}%{' '*(38-len(f"{params['params']['max_position_ratio']*100:.0f}%"))}  ║
╠══════════════════════════════════════════════════════════╣
║  说明:                                                   ║
║  {params.get('notes', '无')[:52]:52s}  ║
╚══════════════════════════════════════════════════════════╝

⚠️  风险提示:
   • 山寨币波动极大，可能快速亏损
   • 严格遵守止损，保护本金
   • 不要使用高杠杆
   • 及时止盈，落袋为安
""")


def main():
    parser = argparse.ArgumentParser(description='山寨币交易工具')
    
    # 基本参数
    parser.add_argument('--exchange', type=str, default='binance',
                        choices=['binance', 'okx', 'htx'],
                        help='交易所')
    parser.add_argument('--symbol', type=str, required=True,
                        help='交易对（如DOGEUSDT）')
    parser.add_argument('--market', type=str, default='spot',
                        choices=['spot', 'futures'],
                        help='市场类型')
    parser.add_argument('--capital', type=float, required=True,
                        help='初始资金（USDT）')
    
    # 交易参数
    parser.add_argument('--interval', type=str, default='15m',
                        help='K线周期（推荐15m）')
    parser.add_argument('--check', type=int, default=60,
                        help='检查间隔（秒）')
    
    # 风险配置
    parser.add_argument('--risk-profile', type=str, default='balanced',
                        choices=['conservative', 'balanced', 'aggressive'],
                        help='风险配置（保守/平衡/激进）')
    
    # 功能开关
    parser.add_argument('--no-fees', action='store_true',
                        help='禁用手续费')
    parser.add_argument('--no-slippage', action='store_true',
                        help='禁用滑点')
    parser.add_argument('--no-stop-loss', action='store_true',
                        help='禁用止损（不推荐）')
    parser.add_argument('--no-take-profit', action='store_true',
                        help='禁用止盈（不推荐）')
    
    args = parser.parse_args()
    
    # 加载配置
    config = load_altcoin_params()
    if not config:
        logger.error("无法加载配置文件，退出")
        return
    
    # 获取币种参数
    coin_params = get_coin_params(args.symbol, args.market, config)
    
    # 打印币种信息
    print_coin_info(args.symbol, args.market, coin_params, args.capital)
    
    # 检查资金是否足够
    if 'recommended_capital' in coin_params.get('params', {}):
        recommended = coin_params['params']['recommended_capital']
        if args.capital < recommended:
            logger.warning(f"⚠️  建议资金: ${recommended} USDT，当前: ${args.capital} USDT")
            logger.warning(f"⚠️  资金不足可能导致频繁止损")
    
    # 风险提示
    risk_level = coin_params.get('risk_level', 'unknown')
    if risk_level in ['very-high', 'extreme']:
        print("⚠️⚠️⚠️ 极高风险警告 ⚠️⚠️⚠️")
        print("此币种风险极高，可能快速亏损！")
        print("建议:")
        print("  1. 使用极小仓位（<10%）")
        print("  2. 设置严格止损")
        print("  3. 不使用杠杆")
        print("  4. 随时准备止损离场")
        print()
        
        response = input("确认继续交易？(yes/no): ")
        if response.lower() != 'yes':
            print("已取消交易")
            return
    
    # 创建交易器
    logger.info("正在初始化交易器...")
    
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
    
    # 应用山寨币参数（需要修改PaperTrader类支持）
    # TODO: 将coin_params['params']应用到trader
    
    logger.info("开始模拟交易...")
    logger.info(f"按 Ctrl+C 停止交易")
    
    try:
        trader.run(args.interval, args.check)
    except KeyboardInterrupt:
        logger.info("\n用户中断交易")
        logger.info("正在保存交易记录...")


if __name__ == '__main__':
    main()

