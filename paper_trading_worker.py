#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模拟交易Worker - 独立进程运行模拟交易
"""

import sys
import json
import time
from datetime import datetime
from loguru import logger

# 配置日志
logger.remove()
logger.add(sys.stderr, level="INFO")


def run_paper_trading(params):
    """运行模拟交易"""
    try:
        from strategies.crypto_signals import SignalCalculator
        from tools.data_downloader import DataDownloader
        
        # 提取参数
        exchange = params.get('exchange', 'binance')
        symbol = params['symbol']
        market = params['market']
        interval = params['interval']
        capital = params['capital']
        
        logger.info(f"启动模拟交易: {symbol} {market} {interval}")
        logger.info(f"交易所: {exchange}")
        logger.info(f"初始资金: {capital} USDT")
        
        # 初始化
        downloader = DataDownloader(exchange=exchange)
        calc = SignalCalculator(symbol=symbol, market_type=market, exchange=exchange)
        
        # 交易状态
        position = None  # None表示空仓，否则存储持仓信息
        current_capital = capital
        trades = []
        
        logger.info("开始模拟回放历史数据...")

        # 加载历史数据
        from strategies.crypto_data_loader import load_crypto_data
        data = load_crypto_data(
            symbol=symbol,
            interval=interval,
            market_type=market,
            exchange=exchange
        )

        if data.empty:
            logger.error("无法加载历史数据")
            return {'success': False, 'message': '无法加载历史数据'}

        # 计算信号
        signals = calc.calculate_signals(interval)
        if signals.empty:
            logger.error("无法计算信号")
            return {'success': False, 'message': '无法计算信号'}

        logger.info(f"数据加载完成: {len(data)} 条, 从 {data['stime'].iloc[0]} 到 {data['stime'].iloc[-1]}")

        # 主循环 - 回放历史数据
        # 从第50条开始，确保有足够的历史数据计算指标
        start_idx = 50
        check_interval = 0.5  # 每0.5秒检查一次（加快演示速度）

        for i in range(start_idx, len(data)):
            try:
                # 获取当前K线数据
                current_bar = data.iloc[i]
                current_price = float(current_bar['close'])
                current_time = current_bar['stime']

                # 获取对应的信号
                if i < len(signals):
                    current_signal = signals.iloc[i]
                    buy_signal = current_signal.get('buy_signal', 0)
                    sell_signal = current_signal.get('sell_signal', 0)
                else:
                    buy_signal = 0
                    sell_signal = 0

                logger.debug(f"[{i}/{len(data)}] 价格: {current_price:.6f}, 买入信号: {buy_signal}, 卖出信号: {sell_signal}")
                
                # 交易逻辑
                if position is None and buy_signal > 0:
                    # 买入
                    position = {
                        'entry_price': current_price,
                        'entry_time': current_time,
                        'amount': current_capital / current_price
                    }
                    trades.append({
                        'time': str(current_time),
                        'action': 'BUY',
                        'price': current_price,
                        'capital': current_capital
                    })
                    logger.info(f"[买入] 价格: {current_price:.6f}, 数量: {position['amount']:.4f}")

                    # 发送状态更新
                    status = {
                        'type': 'trade',
                        'action': 'BUY',
                        'price': current_price,
                        'capital': current_capital,
                        'time': str(current_time)
                    }
                    print(json.dumps(status), flush=True)

                elif position is not None and sell_signal > 0:
                    # 卖出
                    exit_value = position['amount'] * current_price
                    pnl = (exit_value - current_capital) / current_capital * 100
                    current_capital = exit_value

                    trades.append({
                        'time': str(current_time),
                        'action': 'SELL',
                        'price': current_price,
                        'capital': current_capital,
                        'pnl': pnl
                    })
                    logger.info(f"[卖出] 价格: {current_price:.6f}, 收益: {pnl:.2f}%, 资金: {current_capital:.2f}")

                    # 发送状态更新
                    status = {
                        'type': 'trade',
                        'action': 'SELL',
                        'price': current_price,
                        'capital': current_capital,
                        'pnl': pnl,
                        'time': str(current_time)
                    }
                    print(json.dumps(status), flush=True)

                    position = None

                # 每10条数据发送一次心跳（避免输出过多）
                if i % 10 == 0:
                    heartbeat = {
                        'type': 'heartbeat',
                        'price': current_price,
                        'capital': current_capital,
                        'position': position is not None,
                        'time': str(current_time),
                        'progress': f"{i}/{len(data)}"
                    }
                    print(json.dumps(heartbeat), flush=True)

            except Exception as e:
                logger.error(f"循环错误: {e}")

            # 等待下一个周期（加快演示速度）
            time.sleep(check_interval)

        # 如果还有持仓，强制平仓
        if position is not None:
            final_price = float(data['close'].iloc[-1])
            exit_value = position['amount'] * final_price
            pnl = (exit_value - current_capital) / current_capital * 100
            current_capital = exit_value

            logger.info(f"[强制平仓] 价格: {final_price:.6f}, 收益: {pnl:.2f}%, 最终资金: {current_capital:.2f}")

            status = {
                'type': 'trade',
                'action': 'SELL (END)',
                'price': final_price,
                'capital': current_capital,
                'pnl': pnl,
                'time': str(data['stime'].iloc[-1])
            }
            print(json.dumps(status), flush=True)

        # 发送完成信号
        total_return = (current_capital - capital) / capital * 100
        final_status = {
            'type': 'complete',
            'initial_capital': capital,
            'final_capital': current_capital,
            'return_pct': total_return,
            'total_trades': len(trades)
        }
        print(json.dumps(final_status), flush=True)

        logger.info(f"模拟交易完成！总收益率: {total_return:.2f}%")
        
    except Exception as e:
        logger.error(f"模拟交易失败: {e}", exc_info=True)
        return {'success': False, 'message': str(e)}


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "message": "缺少参数"}))
        sys.exit(1)
    
    params_str = sys.argv[1]
    params = json.loads(params_str)
    
    run_paper_trading(params)

