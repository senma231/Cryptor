# -*- coding: utf-8 -*-
"""
价格精度管理工具
根据币种价格自动调整显示精度
"""


def get_price_precision(price: float) -> int:
    """
    根据价格大小返回合适的显示精度

    Args:
        price: 价格

    Returns:
        小数位数
    """
    if price >= 1000:
        return 2  # BTC等高价币：68,906.70
    elif price >= 1:
        return 4  # ETH等中价币：3,456.7890
    elif price >= 0.01:
        return 6  # 低价币：0.123456
    else:
        return 8  # 极低价币（SHIB等）：0.00001234


def format_price(price: float, precision: int = None) -> str:
    """
    格式化价格显示

    Args:
        price: 价格
        precision: 指定精度（None则自动判断）

    Returns:
        格式化后的价格字符串
    """
    if precision is None:
        precision = get_price_precision(price)

    return f"{price:,.{precision}f}"


def format_amount(amount: float, precision: int = 6) -> str:
    """
    格式化数量显示

    Args:
        amount: 数量
        precision: 精度

    Returns:
        格式化后的数量字符串
    """
    return f"{amount:.{precision}f}"


def format_percentage(pct: float, precision: int = 2) -> str:
    """
    格式化百分比显示

    Args:
        pct: 百分比值
        precision: 精度

    Returns:
        格式化后的百分比字符串
    """
    return f"{pct:+.{precision}f}%"


# 预定义常见币种精度
SYMBOL_PRECISION = {
    # 高价币 - 2位小数
    'BTCUSDT': 2,
    'BCHUSDT': 2,

    # 中高价币 - 3位小数
    'ETHUSDT': 3,
    'BNBUSDT': 3,
    'SOLUSDT': 3,
    'XRPUSDT': 4,

    # 中价币 - 4位小数
    'ADAUSDT': 4,
    'DOGEUSDT': 5,
    'DOTUSDT': 4,
    'AVAXUSDT': 4,
    'LINKUSDT': 4,
    'MATICUSDT': 4,

    # 低价币 - 6-8位小数
    'SHIBUSDT': 8,
    'PEPEUSDT': 8,
    '1000PEPEUSDT': 6,
    '1000SHIBUSDT': 6,
}


def get_symbol_precision(symbol: str, default_price: float = None) -> int:
    """
    获取指定交易对的精度

    Args:
        symbol: 交易对符号
        default_price: 默认价格（用于自动判断）

    Returns:
        小数位数
    """
    # 优先使用预定义精度
    if symbol in SYMBOL_PRECISION:
        return SYMBOL_PRECISION[symbol]

    # 根据价格自动判断
    if default_price is not None:
        return get_price_precision(default_price)

    # 默认精度
    return 4


if __name__ == '__main__':
    # 测试
    test_prices = [
        (68906.70, "BTC"),
        (3456.789, "ETH"),
        (145.67, "SOL"),
        (0.6789, "XRP"),
        (0.000012, "SHIB"),
    ]

    print("价格格式化测试：")
    print("=" * 50)

    for price, name in test_prices:
        formatted = format_price(price)
        precision = get_price_precision(price)
        print(f"{name:8s} ${formatted:>15s} (精度: {precision}位)")
