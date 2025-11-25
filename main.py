"""
VNPY量化交易系统 - 主程序
支持回测、模拟交易、实盘交易三种模式
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from loguru import logger

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))


def setup_logger(log_level: str = "INFO"):
    """配置日志系统"""
    logger.remove()  # 移除默认处理器

    # 控制台输出
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=log_level
    )

    # 文件输出
    logger.add(
        "data/logs/vnpy_{time:YYYY-MM-DD}.log",
        rotation="00:00",  # 每天凌晨轮转
        retention="30 days",  # 保留30天
        level=log_level,
        encoding="utf-8"
    )


def show_banner():
    """显示欢迎信息"""
    banner = """
    ╔══════════════════════════════════════════════════════════╗
    ║                                                          ║
    ║      VNPY 本地化量化交易系统                             ║
    ║      Local Quantitative Trading System                  ║
    ║                                                          ║
    ║      版本: 1.0.0                                         ║
    ║      支持: 回测 | 模拟交易 | 实盘交易                    ║
    ║                                                          ║
    ╚══════════════════════════════════════════════════════════╝
    """
    print(banner)


def check_environment():
    """检查运行环境"""
    logger.info("检查运行环境...")

    # 检查.env文件
    if not Path('.env').exists():
        logger.warning(".env 文件不存在,正在从模板创建...")
        if Path('.env.template').exists():
            import shutil
            shutil.copy('.env.template', '.env')
            logger.info("✓ .env 文件已创建,请编辑并填入真实的API密钥")
        else:
            logger.error("✗ 未找到.env.template文件")
            return False

    # 加载环境变量
    load_dotenv()

    # 检查关键目录
    required_dirs = ['data/historical', 'data/database', 'data/logs', 'backtest/reports']
    for dir_path in required_dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

    logger.info("✓ 环境检查完成")
    return True


def run_backtest(args):
    """运行回测"""
    logger.info(f"启动回测模式")
    logger.info(f"策略: {args.strategy}")
    logger.info(f"时间范围: {args.start} ~ {args.end}")

    # TODO: 实现回测逻辑
    print("\n📊 回测功能开发中...")
    print(f"   策略: {args.strategy}")
    print(f"   开始: {args.start}")
    print(f"   结束: {args.end}")
    print(f"   初始资金: {args.capital}")


def run_paper_trading(args):
    """运行模拟交易"""
    logger.info(f"启动模拟交易模式")
    logger.info(f"策略: {args.strategy}")

    # TODO: 实现模拟交易逻辑
    print("\n🔬 模拟交易功能开发中...")
    print(f"   策略: {args.strategy}")
    print(f"   初始资金: {args.capital}")


def run_live_trading(args):
    """运行实盘交易"""
    if not args.confirm:
        logger.error("⚠️  实盘交易需要添加 --confirm 参数确认")
        print("\n⚠️  实盘交易风险提示:")
        print("   - 实盘交易涉及真实资金,请务必谨慎")
        print("   - 建议先在模拟环境充分测试")
        print("   - 使用 --confirm 参数确认启动实盘交易")
        return

    logger.warning(f"⚠️  启动实盘交易模式 - 涉及真实资金!")
    logger.info(f"策略: {args.strategy}")

    # TODO: 实现实盘交易逻辑
    print("\n💰 实盘交易功能开发中...")
    print(f"   策略: {args.strategy}")
    print(f"   交易所: {args.exchange}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='VNPY本地化量化交易系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 回测
  python main.py --mode backtest --strategy trend_following --start 2024-01-01 --end 2024-11-20

  # 模拟交易
  python main.py --mode paper --strategy grid_maker

  # 实盘交易 (需要确认)
  python main.py --mode live --strategy arbitrage --confirm
        """
    )

    # 通用参数
    parser.add_argument('--mode', choices=['backtest', 'paper', 'live'],
                        required=True, help='运行模式')
    parser.add_argument('--strategy', type=str, required=True,
                        help='策略名称')
    parser.add_argument('--exchange', type=str, default='binance',
                        help='交易所 (默认: binance)')
    parser.add_argument('--capital', type=float, default=100000,
                        help='初始资金 (默认: 100000)')
    parser.add_argument('--log-level', type=str, default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='日志级别 (默认: INFO)')

    # 回测参数
    parser.add_argument('--start', type=str,
                        help='回测开始日期 (格式: YYYY-MM-DD)')
    parser.add_argument('--end', type=str,
                        help='回测结束日期 (格式: YYYY-MM-DD)')

    # 实盘确认
    parser.add_argument('--confirm', action='store_true',
                        help='确认启动实盘交易')

    args = parser.parse_args()

    # 初始化
    show_banner()
    setup_logger(args.log_level)

    if not check_environment():
        logger.error("环境检查失败,退出程序")
        return 1

    # 根据模式执行
    try:
        if args.mode == 'backtest':
            if not args.start or not args.end:
                logger.error("回测模式需要指定 --start 和 --end 参数")
                return 1
            run_backtest(args)

        elif args.mode == 'paper':
            run_paper_trading(args)

        elif args.mode == 'live':
            run_live_trading(args)

    except KeyboardInterrupt:
        logger.info("\n用户中断程序")
        return 0
    except Exception as e:
        logger.exception(f"程序异常: {e}")
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
