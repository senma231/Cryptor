#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测Worker进程
独立进程运行回测，避免GUI阻塞
"""

import sys
import json
import warnings
warnings.filterwarnings('ignore')

from pathlib import Path
from loguru import logger

# 配置logger输出到stderr
logger.remove()
logger.add(sys.stderr, format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {module}:{function}:{line} - {message}")


def run_backtest(params):
    """运行回测"""
    try:
        from strategies.crypto_data_loader import load_crypto_data
        from strategies.crypto_signals import SignalCalculator
        from tools.crypto_config import load_strategy_params, DEFAULT_STRATEGY_PARAMS

        # 提取参数
        exchange = params.get('exchange', 'binance')  # 获取交易所参数，默认binance
        symbol = params['symbol']
        market = params['market']
        interval = params['interval']
        capital = params['capital']
        backtest_type = params.get('backtest_type', '模拟回测')

        logger.info(f"开始{backtest_type}: {symbol} {market} {interval}")
        logger.info(f"交易所: {exchange}")
        logger.info(f"初始资金: {capital} USDT")

        # 加载策略参数
        try:
            strategy_params = load_strategy_params()
        except:
            logger.warning("使用默认策略参数")
            strategy_params = DEFAULT_STRATEGY_PARAMS

        # 加载数据
        logger.info("加载历史数据...")
        data = load_crypto_data(
            symbol=symbol,
            interval=interval,
            market_type=market,
            exchange=exchange  # 传递交易所参数
        )
        
        if data is None or len(data) == 0:
            return {
                'success': False,
                'message': f'没有找到{symbol}的历史数据，请先下载数据'
            }
        
        logger.info(f"数据范围: {data['stime'].min()} ~ {data['stime'].max()}")
        logger.info(f"数据条数: {len(data)}")
        
        # 计算信号
        logger.info("计算交易信号...")
        calc = SignalCalculator(symbol=symbol, market_type=market, exchange=exchange)
        signals = calc.calculate_signals(interval)
        
        # 合并价格数据
        signals['close'] = data['close'].values[:len(signals)]
        
        # 获取交易参数
        buy_params = strategy_params['trading_conditions']['buy']
        sell_params = strategy_params['trading_conditions']['sell']
        backtest_params = strategy_params['backtest']
        
        # 初始化回测变量
        initial_capital = capital
        current_capital = capital
        position = 0
        entry_price = 0
        trades = []
        
        # 回测循环
        start_index = backtest_params.get('start_index', 100)
        logger.info(f"开始回测，从第{start_index}条数据开始...")
        
        for i in range(start_index, len(signals)):
            row = signals.iloc[i]
            
            ha = row['HA']
            wd3 = row['WD3']
            qj = row['QJ']
            close = row['close']
            
            # 买入条件
            if position == 0 and ha > buy_params['HA_threshold'] and wd3 < buy_params['WD3_max']:
                position = current_capital / close
                entry_price = close
                trades.append({
                    'time': str(row['stime']),
                    'action': 'BUY',
                    'price': float(close),
                    'capital': float(current_capital)
                })
                logger.debug(f"买入: {close:.4f}, 资金: {current_capital:.2f}")
            
            # 卖出条件
            elif position > 0 and (abs(qj) > sell_params['QJ_threshold'] or wd3 > sell_params['WD3_threshold']):
                pnl = (close - entry_price) / entry_price
                current_capital = current_capital * (1 + pnl)
                trades.append({
                    'time': str(row['stime']),
                    'action': 'SELL',
                    'price': float(close),
                    'capital': float(current_capital),
                    'pnl': float(pnl * 100)
                })
                logger.debug(f"卖出: {close:.4f}, 收益: {pnl*100:.2f}%, 资金: {current_capital:.2f}")
                position = 0
                entry_price = 0
        
        # 如果还有持仓，以最后价格平仓
        if position > 0:
            final_price = signals.iloc[-1]['close']
            pnl = (final_price - entry_price) / entry_price
            current_capital = current_capital * (1 + pnl)
            trades.append({
                'time': str(signals.iloc[-1]['stime']),
                'action': 'SELL (END)',
                'price': float(final_price),
                'capital': float(current_capital),
                'pnl': float(pnl * 100)
            })
        
        # 计算结果
        total_return = (current_capital - initial_capital) / initial_capital * 100
        total_trades = len([t for t in trades if t['action'] == 'BUY'])

        # 计算胜率和盈亏比
        winning_trades = [t for t in trades if t.get('pnl', 0) > 0]
        losing_trades = [t for t in trades if t.get('pnl', 0) < 0]
        win_rate = len(winning_trades) / total_trades * 100 if total_trades > 0 else 0
        avg_win = sum([t['pnl'] for t in winning_trades]) / len(winning_trades) if winning_trades else 0
        avg_loss = sum([t['pnl'] for t in losing_trades]) / len(losing_trades) if losing_trades else 0
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0

        logger.info(f"✓ 回测完成")
        logger.info(f"总收益率: {total_return:.2f}%")
        logger.info(f"交易次数: {total_trades}")
        logger.info(f"胜率: {win_rate:.2f}%")

        # 保存完整报告到文件
        from datetime import datetime
        from pathlib import Path
        report_dir = Path('reports/backtest')
        report_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = report_dir / f"{symbol}_{market}_{interval}_{backtest_type}_{timestamp}.json"

        full_report = {
            'backtest_info': {
                'symbol': symbol,
                'exchange': exchange,
                'market': market,
                'interval': interval,
                'backtest_type': backtest_type,
                'timestamp': timestamp,
                'data_range': f"{data['stime'].min()} ~ {data['stime'].max()}",
                'data_count': len(data)
            },
            'performance': {
                'initial_capital': initial_capital,
                'final_capital': current_capital,
                'return_pct': total_return,
                'total_trades': total_trades,
                'winning_trades': len(winning_trades),
                'losing_trades': len(losing_trades),
                'win_rate': win_rate,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'profit_factor': profit_factor
            },
            'trades': trades
        }

        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(full_report, f, ensure_ascii=False, indent=2)

        logger.info(f"报告已保存: {report_file}")

        return {
            'success': True,
            'message': f'回测完成，总收益率: {total_return:.2f}%',
            'report_file': str(report_file),
            'result': {
                'symbol': symbol,
                'initial_capital': initial_capital,
                'final_capital': current_capital,
                'return_pct': total_return,
                'total_trades': total_trades,
                'win_rate': win_rate,
                'trades': trades[:10]  # 只返回前10条交易记录
            }
        }
        
    except Exception as e:
        logger.exception(f"回测失败: {e}")
        return {
            'success': False,
            'message': f'回测失败: {str(e)}'
        }


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({'success': False, 'message': '缺少参数'}))
        sys.exit(1)
    
    try:
        params = json.loads(sys.argv[1])
        result = run_backtest(params)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({'success': False, 'message': f'参数解析失败: {str(e)}'}))
        sys.exit(1)

