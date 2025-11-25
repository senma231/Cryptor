#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
量化交易系统 - GUI主程序
支持币圈、股票、外汇等多市场交易
"""

import sys
import os
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QComboBox, QTextEdit, QGroupBox,
    QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox, QTableWidget,
    QTableWidgetItem, QMessageBox, QFileDialog, QProgressBar,
    QSplitter, QStatusBar, QMenuBar, QMenu, QAction, QSizePolicy,
    QInputDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QProcess
from PyQt5.QtGui import QIcon, QFont, QColor
import json
from datetime import datetime
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


class DownloadThread(QThread):
    """数据下载线程 - 改进版，避免Bus error"""
    progress = pyqtSignal(int, str)  # 进度信号 (百分比, 消息)
    finished = pyqtSignal(bool, str)  # 完成信号 (成功/失败, 消息)

    def __init__(self, exchange, symbol, market, interval, start_date):
        super().__init__()
        self.exchange = exchange
        self.symbol = symbol
        self.market = market
        self.interval = interval
        self.start_date = start_date
        self._is_running = True
        self._stop_requested = False

    def run(self):
        """运行下载"""
        try:
            # 在子线程中完全避免使用loguru
            # 方法：在导入任何使用loguru的模块之前，先monkey-patch loguru
            import sys
            import os

            # 创建一个完全静默的logger
            class SilentLogger:
                def __getattr__(self, name):
                    return lambda *args, **kwargs: None

            # 在导入之前替换loguru模块
            sys.modules['loguru'] = type(sys)('loguru')
            sys.modules['loguru'].logger = SilentLogger()

            # 现在可以安全导入
            sys.path.append(os.path.dirname(os.path.abspath(__file__)))
            from tools.data_downloader import DataDownloader

            if self._stop_requested:
                return

            self.progress.emit(10, "初始化下载器...")

            downloader = DataDownloader(exchange=self.exchange)

            if self._stop_requested:
                return

            self.progress.emit(30, f"开始下载 {self.symbol} 数据...")

            # 下载数据
            df = None
            if self.exchange == 'binance':
                df = downloader.download_klines_binance(
                    symbol=self.symbol,
                    interval=self.interval,
                    start_time=self.start_date,
                    end_time=None  # 下载到今天
                )
            elif self.exchange == 'okx':
                # OKX需要横杠格式
                symbol_okx = self.symbol
                if '-' not in symbol_okx:
                    # 转换 BTCUSDT -> BTC-USDT
                    symbol_okx = symbol_okx.replace('USDT', '-USDT')
                df = downloader.download_klines_okx(
                    symbol=symbol_okx,
                    interval=self.interval,
                    start_time=self.start_date
                )
            elif self.exchange == 'htx':
                df = downloader.download_klines_htx(
                    symbol=self.symbol,
                    interval=self.interval,
                    start_time=self.start_date,
                    end_time=None  # 下载到今天
                )
            else:
                self.finished.emit(False, f"不支持的交易所: {self.exchange}")
                return

            if self._stop_requested or df is None or df.empty:
                self.finished.emit(False, "下载被取消或无数据")
                return

            self.progress.emit(80, "保存数据...")

            # 保存数据
            filename = f"{self.symbol}_{self.market}_{self.interval}.csv"
            filepath = downloader.data_dir / filename

            # 确保目录存在
            filepath.parent.mkdir(parents=True, exist_ok=True)

            # 保存CSV
            df.to_csv(str(filepath), index=False)

            if self._stop_requested:
                return

            self.progress.emit(100, "下载完成！")
            self.finished.emit(True, f"成功下载 {len(df)} 条数据，保存到: {filepath}")

        except KeyboardInterrupt:
            self.finished.emit(False, "下载被用户中断")
        except Exception as e:
            import traceback
            error_msg = f"下载失败: {str(e)}\n\n详细错误:\n{traceback.format_exc()}"
            print(f"[DownloadThread Error] {error_msg}")  # 打印到控制台
            self.finished.emit(False, error_msg)

    def stop(self):
        """停止下载 - 使用标志位而不是terminate()"""
        self._stop_requested = True
        self._is_running = False
        # 不使用terminate()，让线程自然结束
        self.wait(2000)  # 等待最多2秒


class TradingGUI(QMainWindow):
    """量化交易系统主窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("量化交易系统 Beta v0.1")
        self.setGeometry(100, 100, 1400, 900)

        # 设置窗口图标
        from pathlib import Path
        icon_path = Path(__file__).parent / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # 初始化配置
        self.config = self.load_config()
        self.current_market_type = "crypto"  # crypto, stock, forex
        self.current_exchange = "binance"

        # 初始化下载进程
        self.download_process = None
        self.download_thread = None  # 保留以兼容旧代码
        self.download_output_buffer = {'stdout': '', 'stderr': ''}  # 累积所有输出

        # 初始化回测进程
        self.backtest_process = None
        self.backtest_output_buffer = {'stdout': '', 'stderr': ''}
        self.last_backtest_report = None  # 保存最后一次回测报告路径

        # 初始化模拟交易进程
        self.paper_trading_process = None
        self.paper_trading_running = False
        self.paper_trading_manual_stop = False  # 标记是否手动停止
        self.paper_trading_stats = {
            'initial_capital': 0,
            'current_capital': 0,
            'total_trades': 0
        }

        # 初始化策略和配置列表
        self.strategies = []  # 存储导入的策略
        self.backtest_configs = []  # 存储导入的回测配置
        self.strategy_dir = Path(__file__).parent / "strategies_imported"
        self.strategy_dir.mkdir(exist_ok=True)

        # 应用全局样式
        self.apply_stylesheet()

        # 创建UI
        self.init_ui()

    def apply_stylesheet(self):
        """应用全局样式表"""
        stylesheet = """
            QMainWindow {
                background-color: #2b2b2b;
            }

            QWidget {
                background-color: #2b2b2b;
                color: #e0e0e0;
            }

            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                border: 2px solid #404040;
                border-radius: 6px;
                margin-top: 12px;
                padding: 15px;
                background-color: #353535;
                color: #ffffff;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #ffffff;
            }

            QPushButton {
                background-color: #0d7377;
                color: #ffffff;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                min-width: 80px;
            }

            QPushButton:hover {
                background-color: #14a085;
            }

            QPushButton:pressed {
                background-color: #0a5f62;
            }

            QPushButton:disabled {
                background-color: #505050;
                color: #808080;
            }

            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                padding: 8px;
                border: 2px solid #404040;
                border-radius: 4px;
                background-color: #404040;
                color: #ffffff;
                font-size: 14px;
                min-height: 28px;
            }

            QLineEdit:focus, QComboBox:focus {
                border: 2px solid #0d7377;
                background-color: #4a4a4a;
            }

            QComboBox::drop-down {
                border: none;
                width: 30px;
            }

            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #ffffff;
                margin-right: 10px;
            }

            QComboBox QAbstractItemView {
                background-color: #404040;
                color: #ffffff;
                selection-background-color: #0d7377;
                border: 1px solid #0d7377;
            }

            QTextEdit {
                border: 2px solid #404040;
                border-radius: 4px;
                background-color: #1e1e1e;
                color: #e0e0e0;
                padding: 8px;
                font-size: 14px;
                font-family: "PingFang SC", "Microsoft YaHei", "SimHei", "Arial", sans-serif;
            }

            QTabWidget::pane {
                border: 2px solid #404040;
                border-radius: 4px;
                background-color: #353535;
                padding: 10px;
            }

            QTabBar::tab {
                background-color: #2b2b2b;
                color: #b0b0b0;
                padding: 12px 24px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }

            QTabBar::tab:selected {
                background-color: #353535;
                color: #14a085;
                border-bottom: 3px solid #14a085;
            }

            QTabBar::tab:hover {
                background-color: #404040;
                color: #ffffff;
            }

            QLabel {
                color: #e0e0e0;
                font-size: 14px;
                background-color: transparent;
            }

            QProgressBar {
                border: 2px solid #404040;
                border-radius: 4px;
                text-align: center;
                background-color: #2b2b2b;
                color: #ffffff;
                font-weight: bold;
            }

            QProgressBar::chunk {
                background-color: #0d7377;
                border-radius: 2px;
            }

            QTableWidget {
                border: 2px solid #404040;
                border-radius: 4px;
                background-color: #353535;
                gridline-color: #404040;
                color: #e0e0e0;
            }

            QTableWidget::item {
                padding: 5px;
                color: #e0e0e0;
            }

            QTableWidget::item:selected {
                background-color: #0d7377;
                color: #ffffff;
            }

            QHeaderView::section {
                background-color: #1e1e1e;
                color: #ffffff;
                padding: 10px;
                border: none;
                font-weight: bold;
                font-size: 13px;
            }

            QMenuBar {
                background-color: #2b2b2b;
                color: #e0e0e0;
            }

            QMenuBar::item:selected {
                background-color: #404040;
            }

            QMenu {
                background-color: #353535;
                color: #e0e0e0;
                border: 1px solid #404040;
            }

            QMenu::item:selected {
                background-color: #0d7377;
            }

            QStatusBar {
                background-color: #1e1e1e;
                color: #e0e0e0;
            }

            QScrollBar:vertical {
                background-color: #2b2b2b;
                width: 12px;
                border-radius: 6px;
            }

            QScrollBar::handle:vertical {
                background-color: #505050;
                border-radius: 6px;
                min-height: 20px;
            }

            QScrollBar::handle:vertical:hover {
                background-color: #606060;
            }

            QScrollBar:horizontal {
                background-color: #2b2b2b;
                height: 12px;
                border-radius: 6px;
            }

            QScrollBar::handle:horizontal {
                background-color: #505050;
                border-radius: 6px;
                min-width: 20px;
            }

            QScrollBar::handle:horizontal:hover {
                background-color: #606060;
            }
        """
        self.setStyleSheet(stylesheet)

    def init_ui(self):
        """初始化用户界面"""
        # 创建菜单栏
        self.create_menu_bar()

        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QVBoxLayout(central_widget)

        # 顶部：市场类型和交易所选择
        top_bar = self.create_top_bar()
        main_layout.addWidget(top_bar)

        # 中间：分割器（上方功能区 + 下方日志区）
        splitter = QSplitter(Qt.Vertical)

        # 上方：功能标签页
        self.tab_widget = QTabWidget()
        self.create_tabs()
        splitter.addWidget(self.tab_widget)

        # 下方：日志输出
        log_widget = self.create_log_widget()
        splitter.addWidget(log_widget)

        # 设置分割比例（上方70%，下方30%）
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)

        main_layout.addWidget(splitter)

        # 底部：状态栏
        self.create_status_bar()
        
    def create_menu_bar(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件")
        
        import_action = QAction("导入策略", self)
        import_action.triggered.connect(self.import_strategy)
        file_menu.addAction(import_action)
        
        export_action = QAction("导出配置", self)
        export_action.triggered.connect(self.export_config)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 工具菜单
        tools_menu = menubar.addMenu("工具")
        
        settings_action = QAction("系统设置", self)
        settings_action.triggered.connect(self.show_settings)
        tools_menu.addAction(settings_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助")
        
        doc_action = QAction("使用文档", self)
        doc_action.triggered.connect(self.show_documentation)
        help_menu.addAction(doc_action)
        
        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
    def create_top_bar(self):
        """创建顶部工具栏"""
        top_widget = QWidget()
        top_widget.setMaximumHeight(60)  # 增加最大高度
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(10, 10, 10, 15)  # 增加底部边距
        top_layout.setSpacing(10)  # 设置间距

        # 市场类型选择
        market_label = QLabel("市场类型:")
        market_label.setFont(QFont("Arial", 10, QFont.Bold))
        top_layout.addWidget(market_label)

        self.market_combo = QComboBox()
        self.market_combo.addItems(["币圈 (Crypto)", "股票 (Stock)", "外汇 (Forex)"])
        self.market_combo.currentIndexChanged.connect(self.on_market_changed)
        self.market_combo.setMaximumWidth(150)  # 限制宽度
        top_layout.addWidget(self.market_combo)

        top_layout.addSpacing(20)

        # 交易所选择
        exchange_label = QLabel("交易所:")
        exchange_label.setFont(QFont("Arial", 10, QFont.Bold))
        top_layout.addWidget(exchange_label)

        self.exchange_combo = QComboBox()
        self.update_exchange_list()
        self.exchange_combo.currentTextChanged.connect(self.on_exchange_changed)
        self.exchange_combo.setMaximumWidth(150)  # 限制宽度
        top_layout.addWidget(self.exchange_combo)

        top_layout.addStretch()

        # 连接状态指示
        self.status_label = QLabel("● 未连接")
        self.status_label.setStyleSheet("color: gray; font-size: 12px;")
        top_layout.addWidget(self.status_label)

        return top_widget

    def create_tabs(self):
        """创建功能标签页"""
        # 1. 数据下载
        self.tab_widget.addTab(self.create_data_download_tab(), "📥 数据下载")

        # 2. 回测测试
        self.tab_widget.addTab(self.create_backtest_tab(), "📊 回测测试")

        # 3. 模拟交易
        self.tab_widget.addTab(self.create_paper_trading_tab(), "🎮 模拟交易")

        # 4. 实盘交易
        self.tab_widget.addTab(self.create_live_trading_tab(), "💰 实盘交易")

        # 5. 策略列表
        self.tab_widget.addTab(self.create_strategy_tab(), "📋 策略列表")

        # 6. 实盘监控
        self.tab_widget.addTab(self.create_monitor_tab(), "📈 实盘监控")

        # 7. 机会扫描
        self.tab_widget.addTab(self.create_scanner_tab(), "🔍 机会扫描")

        # 8. 通知配置
        self.tab_widget.addTab(self.create_notification_tab(), "🔔 通知配置")

    def create_data_download_tab(self):
        """创建数据下载标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)  # 增加组件间距
        layout.setContentsMargins(20, 20, 20, 20)  # 增加边距

        # 配置组
        config_group = QGroupBox("下载配置")
        config_layout = QVBoxLayout()
        config_layout.setSpacing(12)  # 增加内部间距

        # 交易对
        symbol_layout = QHBoxLayout()
        symbol_label = QLabel("交易对:")
        symbol_label.setMinimumWidth(80)
        symbol_layout.addWidget(symbol_label)
        self.download_symbol = QLineEdit("DOGEUSDT")
        symbol_layout.addWidget(self.download_symbol)
        config_layout.addLayout(symbol_layout)

        # 市场类型
        market_layout = QHBoxLayout()
        market_label = QLabel("市场:")
        market_label.setMinimumWidth(80)
        market_layout.addWidget(market_label)
        self.download_market = QComboBox()
        self.download_market.addItems(["现货", "合约"])
        market_layout.addWidget(self.download_market)
        config_layout.addLayout(market_layout)

        # 时间周期
        interval_layout = QHBoxLayout()
        interval_label = QLabel("周期:")
        interval_label.setMinimumWidth(80)
        interval_layout.addWidget(interval_label)
        self.download_interval = QComboBox()
        self.download_interval.addItems(["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w", "1M"])
        self.download_interval.setCurrentText("15m")
        interval_layout.addWidget(self.download_interval)
        config_layout.addLayout(interval_layout)

        # 开始日期
        date_layout = QHBoxLayout()
        date_label = QLabel("开始日期:")
        date_label.setMinimumWidth(80)
        date_layout.addWidget(date_label)
        self.download_start_date = QLineEdit("2024-01-01")
        self.download_start_date.setPlaceholderText("格式: YYYY-MM-DD")
        date_layout.addWidget(self.download_start_date)
        config_layout.addLayout(date_layout)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # 进度条
        progress_group = QGroupBox("下载进度")
        progress_layout = QVBoxLayout()
        self.download_progress = QProgressBar()
        self.download_progress.setMinimumHeight(30)
        progress_layout.addWidget(self.download_progress)
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        self.download_btn = QPushButton("开始下载")
        self.download_btn.clicked.connect(self.start_download)
        self.download_btn.setMinimumHeight(40)
        btn_layout.addWidget(self.download_btn)

        self.stop_download_btn = QPushButton("停止")
        self.stop_download_btn.clicked.connect(self.stop_download)
        self.stop_download_btn.setEnabled(False)  # 初始状态禁用
        self.stop_download_btn.setMinimumHeight(40)
        btn_layout.addWidget(self.stop_download_btn)

        layout.addLayout(btn_layout)
        layout.addStretch()

        return widget

    def create_backtest_tab(self):
        """创建回测测试标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 回测类型
        type_group = QGroupBox("回测类型")
        type_layout = QHBoxLayout()

        self.backtest_type = QComboBox()
        self.backtest_type.addItems(["模拟回测", "实盘回测"])
        type_layout.addWidget(self.backtest_type)

        type_group.setLayout(type_layout)
        layout.addWidget(type_group)

        # 回测配置
        config_group = QGroupBox("回测配置")
        config_layout = QVBoxLayout()

        # 交易对
        symbol_layout = QHBoxLayout()
        symbol_layout.addWidget(QLabel("交易对:"))
        self.backtest_symbol = QLineEdit("DOGEUSDT")
        symbol_layout.addWidget(self.backtest_symbol)
        config_layout.addLayout(symbol_layout)

        # 市场类型
        market_layout = QHBoxLayout()
        market_layout.addWidget(QLabel("市场:"))
        self.backtest_market = QComboBox()
        self.backtest_market.addItems(["现货", "合约"])
        market_layout.addWidget(self.backtest_market)
        config_layout.addLayout(market_layout)

        # 时间周期
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("周期:"))
        self.backtest_interval = QComboBox()
        self.backtest_interval.addItems(["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w", "1M"])
        self.backtest_interval.setCurrentText("15m")
        interval_layout.addWidget(self.backtest_interval)
        config_layout.addLayout(interval_layout)

        # 初始资金
        capital_layout = QHBoxLayout()
        capital_layout.addWidget(QLabel("初始资金:"))
        self.backtest_capital = QDoubleSpinBox()
        self.backtest_capital.setRange(10, 1000000)
        self.backtest_capital.setValue(10000)
        self.backtest_capital.setSuffix(" USDT")
        capital_layout.addWidget(self.backtest_capital)
        config_layout.addLayout(capital_layout)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # 按钮
        btn_layout = QHBoxLayout()
        run_btn = QPushButton("运行回测")
        run_btn.clicked.connect(self.run_backtest)
        btn_layout.addWidget(run_btn)

        report_btn = QPushButton("查看报告")
        report_btn.clicked.connect(self.view_backtest_report)
        btn_layout.addWidget(report_btn)

        layout.addLayout(btn_layout)
        layout.addStretch()

        return widget

    def create_paper_trading_tab(self):
        """创建模拟交易标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 交易配置
        config_group = QGroupBox("交易配置")
        config_layout = QVBoxLayout()

        # 交易对
        symbol_layout = QHBoxLayout()
        symbol_layout.addWidget(QLabel("交易对:"))
        self.paper_symbol = QLineEdit("DOGEUSDT")
        symbol_layout.addWidget(self.paper_symbol)
        config_layout.addLayout(symbol_layout)

        # 市场类型
        market_layout = QHBoxLayout()
        market_layout.addWidget(QLabel("市场:"))
        self.paper_market = QComboBox()
        self.paper_market.addItems(["现货", "合约"])
        market_layout.addWidget(self.paper_market)
        config_layout.addLayout(market_layout)

        # 初始资金
        capital_layout = QHBoxLayout()
        capital_layout.addWidget(QLabel("初始资金:"))
        self.paper_capital = QDoubleSpinBox()
        self.paper_capital.setRange(10, 1000000)
        self.paper_capital.setValue(30)
        self.paper_capital.setSuffix(" USDT")
        capital_layout.addWidget(self.paper_capital)
        config_layout.addLayout(capital_layout)

        # 时间周期
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("周期:"))
        self.paper_interval = QComboBox()
        self.paper_interval.addItems(["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w", "1M"])
        self.paper_interval.setCurrentText("15m")
        interval_layout.addWidget(self.paper_interval)
        config_layout.addLayout(interval_layout)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # 状态显示
        status_group = QGroupBox("交易状态")
        status_layout = QVBoxLayout()

        self.paper_status_label = QLabel("状态: 未启动")
        status_layout.addWidget(self.paper_status_label)

        self.paper_profit_label = QLabel("当前盈亏: 0.00 USDT")
        status_layout.addWidget(self.paper_profit_label)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # 按钮
        btn_layout = QHBoxLayout()
        self.paper_start_btn = QPushButton("启动交易")
        self.paper_start_btn.clicked.connect(self.start_paper_trading)
        btn_layout.addWidget(self.paper_start_btn)

        self.paper_stop_btn = QPushButton("停止交易")
        self.paper_stop_btn.clicked.connect(self.stop_paper_trading)
        self.paper_stop_btn.setEnabled(False)
        btn_layout.addWidget(self.paper_stop_btn)

        layout.addLayout(btn_layout)
        layout.addStretch()

        return widget

    def create_live_trading_tab(self):
        """创建实盘交易标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 警告提示
        warning_label = QLabel("⚠️ 警告：实盘交易将使用真实资金，请谨慎操作！")
        warning_label.setStyleSheet("color: red; font-weight: bold; padding: 10px; background-color: #fff3cd;")
        layout.addWidget(warning_label)

        # API配置
        api_group = QGroupBox("API配置")
        api_layout = QVBoxLayout()

        # API Key
        key_layout = QHBoxLayout()
        key_layout.addWidget(QLabel("API Key:"))
        self.live_api_key = QLineEdit()
        self.live_api_key.setEchoMode(QLineEdit.Password)
        key_layout.addWidget(self.live_api_key)
        api_layout.addLayout(key_layout)

        # API Secret
        secret_layout = QHBoxLayout()
        secret_layout.addWidget(QLabel("API Secret:"))
        self.live_api_secret = QLineEdit()
        self.live_api_secret.setEchoMode(QLineEdit.Password)
        secret_layout.addWidget(self.live_api_secret)
        api_layout.addLayout(secret_layout)

        # 测试连接按钮
        test_btn = QPushButton("测试连接")
        test_btn.clicked.connect(self.test_api_connection)
        api_layout.addWidget(test_btn)

        api_group.setLayout(api_layout)
        layout.addWidget(api_group)

        # 交易配置
        config_group = QGroupBox("交易配置")
        config_layout = QVBoxLayout()

        # 交易对
        symbol_layout = QHBoxLayout()
        symbol_layout.addWidget(QLabel("交易对:"))
        self.live_symbol = QLineEdit("DOGEUSDT")
        symbol_layout.addWidget(self.live_symbol)
        config_layout.addLayout(symbol_layout)

        # 最大仓位
        position_layout = QHBoxLayout()
        position_layout.addWidget(QLabel("最大仓位:"))
        self.live_max_position = QDoubleSpinBox()
        self.live_max_position.setRange(10, 100000)
        self.live_max_position.setValue(100)
        self.live_max_position.setSuffix(" USDT")
        position_layout.addWidget(self.live_max_position)
        config_layout.addLayout(position_layout)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # 按钮
        btn_layout = QHBoxLayout()
        self.live_start_btn = QPushButton("启动实盘")
        self.live_start_btn.clicked.connect(self.start_live_trading)
        btn_layout.addWidget(self.live_start_btn)

        self.live_stop_btn = QPushButton("停止实盘")
        self.live_stop_btn.clicked.connect(self.stop_live_trading)
        self.live_stop_btn.setEnabled(False)
        btn_layout.addWidget(self.live_stop_btn)

        layout.addLayout(btn_layout)
        layout.addStretch()

        return widget

    def create_strategy_tab(self):
        """创建策略管理标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 创建标签页
        tab_widget = QTabWidget()

        # 策略文件标签页
        strategy_widget = QWidget()
        strategy_layout = QVBoxLayout(strategy_widget)

        self.strategy_table = QTableWidget()
        self.strategy_table.setColumnCount(5)
        self.strategy_table.setHorizontalHeaderLabels(["策略名称", "文件名", "加密", "导入时间", "操作"])

        # 设置表格样式
        self.strategy_table.setAlternatingRowColors(True)
        self.strategy_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.strategy_table.setSelectionMode(QTableWidget.SingleSelection)
        self.strategy_table.verticalHeader().setVisible(False)
        self.strategy_table.setShowGrid(True)

        # 设置列宽
        self.strategy_table.setColumnWidth(0, 180)  # 策略名称
        self.strategy_table.setColumnWidth(1, 220)  # 文件名
        self.strategy_table.setColumnWidth(2, 60)   # 加密
        self.strategy_table.setColumnWidth(3, 160)  # 导入时间
        self.strategy_table.setColumnWidth(4, 120)  # 操作

        # 设置表头自适应
        header = self.strategy_table.horizontalHeader()
        header.setStretchLastSection(True)

        # 设置行高
        self.strategy_table.verticalHeader().setDefaultSectionSize(40)

        strategy_layout.addWidget(self.strategy_table)

        # 策略按钮
        strategy_btn_layout = QHBoxLayout()
        strategy_btn_layout.setSpacing(10)

        import_strategy_btn = QPushButton("📥 导入策略")
        import_strategy_btn.setToolTip("导入加密的策略文件(.qts)")
        import_strategy_btn.setFixedHeight(36)
        import_strategy_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a9eff;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3d8ae6;
            }
            QPushButton:pressed {
                background-color: #2d7ad6;
            }
        """)
        import_strategy_btn.clicked.connect(self.import_strategy)
        strategy_btn_layout.addWidget(import_strategy_btn)

        encrypt_strategy_btn = QPushButton("🔒 加密策略")
        encrypt_strategy_btn.setToolTip("将.py文件加密为.qts文件")
        encrypt_strategy_btn.setFixedHeight(36)
        encrypt_strategy_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffa726;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #fb8c00;
            }
            QPushButton:pressed {
                background-color: #e67700;
            }
        """)
        encrypt_strategy_btn.clicked.connect(self.encrypt_strategy_file)
        strategy_btn_layout.addWidget(encrypt_strategy_btn)

        remove_strategy_btn = QPushButton("🗑️ 移除策略")
        remove_strategy_btn.setToolTip("从列表中移除选中的策略")
        remove_strategy_btn.setFixedHeight(36)
        remove_strategy_btn.setStyleSheet("""
            QPushButton {
                background-color: #ef5350;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e53935;
            }
            QPushButton:pressed {
                background-color: #c62828;
            }
        """)
        remove_strategy_btn.clicked.connect(self.remove_strategy)
        strategy_btn_layout.addWidget(remove_strategy_btn)

        strategy_btn_layout.addStretch()
        strategy_layout.addLayout(strategy_btn_layout)

        tab_widget.addTab(strategy_widget, "策略文件")

        # 回测配置标签页
        backtest_widget = QWidget()
        backtest_layout = QVBoxLayout(backtest_widget)

        self.backtest_config_table = QTableWidget()
        self.backtest_config_table.setColumnCount(5)
        self.backtest_config_table.setHorizontalHeaderLabels(["配置名称", "交易对", "周期", "导入时间", "操作"])

        # 设置表格样式
        self.backtest_config_table.setAlternatingRowColors(True)
        self.backtest_config_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.backtest_config_table.setSelectionMode(QTableWidget.SingleSelection)
        self.backtest_config_table.verticalHeader().setVisible(False)
        self.backtest_config_table.setShowGrid(True)

        # 设置列宽
        self.backtest_config_table.setColumnWidth(0, 200)  # 配置名称
        self.backtest_config_table.setColumnWidth(1, 150)  # 交易对
        self.backtest_config_table.setColumnWidth(2, 80)   # 周期
        self.backtest_config_table.setColumnWidth(3, 160)  # 导入时间
        self.backtest_config_table.setColumnWidth(4, 220)  # 操作（增加宽度以容纳微调按钮）

        # 设置表头自适应
        header = self.backtest_config_table.horizontalHeader()
        header.setStretchLastSection(True)

        # 设置行高
        self.backtest_config_table.verticalHeader().setDefaultSectionSize(40)

        backtest_layout.addWidget(self.backtest_config_table)

        # 回测配置按钮
        backtest_btn_layout = QHBoxLayout()
        backtest_btn_layout.setSpacing(10)

        import_backtest_btn = QPushButton("📥 导入配置")
        import_backtest_btn.setToolTip("导入加密的回测配置文件(.qtb)")
        import_backtest_btn.setFixedHeight(36)
        import_backtest_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a9eff;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3d8ae6;
            }
            QPushButton:pressed {
                background-color: #2d7ad6;
            }
        """)
        import_backtest_btn.clicked.connect(self.import_backtest_config)
        backtest_btn_layout.addWidget(import_backtest_btn)

        encrypt_backtest_btn = QPushButton("🔒 加密配置")
        encrypt_backtest_btn.setToolTip("将回测配置加密为.qtb文件")
        encrypt_backtest_btn.setFixedHeight(36)
        encrypt_backtest_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffa726;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #fb8c00;
            }
            QPushButton:pressed {
                background-color: #e67700;
            }
        """)
        encrypt_backtest_btn.clicked.connect(self.encrypt_backtest_config)
        backtest_btn_layout.addWidget(encrypt_backtest_btn)

        remove_backtest_btn = QPushButton("🗑️ 移除配置")
        remove_backtest_btn.setToolTip("从列表中移除选中的配置")
        remove_backtest_btn.setFixedHeight(36)
        remove_backtest_btn.setStyleSheet("""
            QPushButton {
                background-color: #ef5350;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e53935;
            }
            QPushButton:pressed {
                background-color: #c62828;
            }
        """)
        remove_backtest_btn.clicked.connect(self.remove_backtest_config)
        backtest_btn_layout.addWidget(remove_backtest_btn)

        backtest_btn_layout.addStretch()
        backtest_layout.addLayout(backtest_btn_layout)

        tab_widget.addTab(backtest_widget, "回测配置")

        layout.addWidget(tab_widget)

        return widget

    def create_monitor_tab(self):
        """创建实盘监控标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 持仓信息
        position_group = QGroupBox("持仓信息")
        position_layout = QVBoxLayout()

        self.position_table = QTableWidget()
        self.position_table.setColumnCount(6)
        self.position_table.setHorizontalHeaderLabels(["交易对", "方向", "数量", "成本", "当前价", "盈亏"])
        position_layout.addWidget(self.position_table)

        position_group.setLayout(position_layout)
        layout.addWidget(position_group)

        # 账户信息
        account_group = QGroupBox("账户信息")
        account_layout = QVBoxLayout()

        self.account_balance_label = QLabel("总资产: -- USDT")
        account_layout.addWidget(self.account_balance_label)

        self.account_profit_label = QLabel("总盈亏: -- USDT")
        account_layout.addWidget(self.account_profit_label)

        account_group.setLayout(account_layout)
        layout.addWidget(account_group)

        # 刷新按钮
        refresh_btn = QPushButton("刷新数据")
        refresh_btn.clicked.connect(self.refresh_monitor_data)
        layout.addWidget(refresh_btn)

        layout.addStretch()

        return widget

    def create_scanner_tab(self):
        """创建机会扫描标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 扫描配置
        config_group = QGroupBox("扫描配置")
        config_layout = QVBoxLayout()

        # 扫描范围
        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel("扫描范围:"))
        self.scanner_range = QComboBox()
        self.scanner_range.addItems(["热门币种", "全市场", "自定义列表"])
        range_layout.addWidget(self.scanner_range)
        config_layout.addLayout(range_layout)

        # 最小涨幅
        min_change_layout = QHBoxLayout()
        min_change_layout.addWidget(QLabel("最小涨幅:"))
        self.scanner_min_change = QDoubleSpinBox()
        self.scanner_min_change.setRange(-100, 100)
        self.scanner_min_change.setValue(5)
        self.scanner_min_change.setSuffix(" %")
        min_change_layout.addWidget(self.scanner_min_change)
        config_layout.addLayout(min_change_layout)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # 机会列表
        result_group = QGroupBox("扫描结果")
        result_layout = QVBoxLayout()

        self.scanner_table = QTableWidget()
        self.scanner_table.setColumnCount(5)
        self.scanner_table.setHorizontalHeaderLabels(["交易对", "当前价", "24h涨幅", "信号强度", "操作"])
        result_layout.addWidget(self.scanner_table)

        result_group.setLayout(result_layout)
        layout.addWidget(result_group)

        # 按钮
        btn_layout = QHBoxLayout()

        scan_btn = QPushButton("开始扫描")
        scan_btn.clicked.connect(self.start_scanner)
        btn_layout.addWidget(scan_btn)

        stop_scan_btn = QPushButton("停止扫描")
        stop_scan_btn.clicked.connect(self.stop_scanner)
        btn_layout.addWidget(stop_scan_btn)

        layout.addLayout(btn_layout)

        return widget

    def create_notification_tab(self):
        """创建通知配置标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 通知方式
        method_group = QGroupBox("通知方式")
        method_layout = QVBoxLayout()

        self.notify_console = QCheckBox("控制台输出")
        self.notify_console.setChecked(True)
        method_layout.addWidget(self.notify_console)

        self.notify_feishu = QCheckBox("飞书通知")
        method_layout.addWidget(self.notify_feishu)

        self.notify_email = QCheckBox("邮件通知")
        method_layout.addWidget(self.notify_email)

        self.notify_telegram = QCheckBox("Telegram通知")
        method_layout.addWidget(self.notify_telegram)

        method_group.setLayout(method_layout)
        layout.addWidget(method_group)

        # 飞书配置
        feishu_group = QGroupBox("飞书配置")
        feishu_layout = QVBoxLayout()

        webhook_layout = QHBoxLayout()
        webhook_layout.addWidget(QLabel("Webhook URL:"))
        self.feishu_webhook = QLineEdit()
        webhook_layout.addWidget(self.feishu_webhook)
        feishu_layout.addLayout(webhook_layout)

        feishu_group.setLayout(feishu_layout)
        layout.addWidget(feishu_group)

        # 按钮
        btn_layout = QHBoxLayout()

        save_btn = QPushButton("保存配置")
        save_btn.clicked.connect(self.save_notification_config)
        btn_layout.addWidget(save_btn)

        test_btn = QPushButton("测试通知")
        test_btn.clicked.connect(self.test_notification)
        btn_layout.addWidget(test_btn)

        layout.addLayout(btn_layout)
        layout.addStretch()

        return widget

    def create_log_widget(self):
        """创建日志输出组件"""
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)

        log_label = QLabel("📋 系统日志")
        log_label.setFont(QFont("Arial", 10, QFont.Bold))
        log_layout.addWidget(log_label)

        # 使用QTextEdit支持HTML颜色
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)

        # 设置字体
        font = QFont()
        if sys.platform == "darwin":
            font.setFamily("PingFang SC")
        elif sys.platform == "win32":
            font.setFamily("Microsoft YaHei")
        else:
            font.setFamily("Noto Sans CJK SC")
        font.setPointSize(12)
        self.log_text.setFont(font)

        # 设置样式
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 2px solid #404040;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        log_layout.addWidget(self.log_text)

        # 清空日志按钮
        clear_btn = QPushButton("清空日志")
        clear_btn.clicked.connect(self.clear_log)
        log_layout.addWidget(clear_btn)

        return log_widget

    def create_status_bar(self):
        """创建状态栏"""
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("就绪")

    # ==================== 工具方法 ====================

    def load_config(self):
        """加载配置"""
        try:
            with open('config/settings.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}

    def save_config(self):
        """保存配置"""
        try:
            with open('config/settings.json', 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log(f"保存配置失败: {str(e)}", "error")

    def show_message(self, title, message, msg_type="info"):
        """显示消息框（中文按钮）"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)

        if msg_type == "info":
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setStandardButtons(QMessageBox.Ok)
            msg_box.button(QMessageBox.Ok).setText("确定")
        elif msg_type == "warning":
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setStandardButtons(QMessageBox.Ok)
            msg_box.button(QMessageBox.Ok).setText("确定")
        elif msg_type == "error":
            msg_box.setIcon(QMessageBox.Critical)
            msg_box.setStandardButtons(QMessageBox.Ok)
            msg_box.button(QMessageBox.Ok).setText("确定")
        elif msg_type == "question":
            msg_box.setIcon(QMessageBox.Question)
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg_box.button(QMessageBox.Yes).setText("是")
            msg_box.button(QMessageBox.No).setText("否")

        return msg_box.exec_()

    def log(self, message, level="info"):
        """输出日志"""
        if not hasattr(self, 'log_text') or self.log_text is None:
            print(f"[LOG] {message}")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 设置颜色和前缀
        if level == "error":
            prefix = "[错误]"
            color = "#ff6b6b"  # 红色
        elif level == "warning":
            prefix = "[警告]"
            color = "#ffd93d"  # 黄色
        elif level == "success":
            prefix = "[成功]"
            color = "#6bcf7f"  # 绿色
        else:
            prefix = "[信息]"
            color = "#d4d4d4"  # 白色

        # 创建HTML格式的日志
        log_html = f'<span style="color: {color};">[{timestamp}] {prefix} {message}</span>'

        # 使用append添加HTML
        self.log_text.append(log_html)

        # 自动滚动到底部
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear_log(self):
        """清空日志"""
        self.log_text.clear()
        self.log("日志已清空")

    def update_exchange_list(self):
        """更新交易所列表"""
        self.exchange_combo.clear()

        if self.current_market_type == "crypto":
            self.exchange_combo.addItems(["Binance", "OKX", "HTX"])
        elif self.current_market_type == "stock":
            self.exchange_combo.addItems(["东方财富", "同花顺", "雪球"])
        elif self.current_market_type == "forex":
            self.exchange_combo.addItems(["OANDA", "IG", "FXCM"])

    # ==================== 事件处理 ====================

    def on_market_changed(self, index):
        """市场类型改变"""
        market_types = ["crypto", "stock", "forex"]
        selected_market = market_types[index]

        # 检查是否选择了未开发的市场类型
        if selected_market in ["stock", "forex"]:
            # 显示提示框
            market_name = "股票" if selected_market == "stock" else "外汇"
            QMessageBox.information(
                self,
                "功能开发中",
                f"📢 {market_name}市场功能正在开发中，敬请期待！\n\n目前仅支持币圈市场。",
                QMessageBox.Ok
            )

            # 切换回币圈
            self.market_combo.blockSignals(True)  # 暂时阻止信号，避免递归调用
            self.market_combo.setCurrentIndex(0)  # 切换回第一项（币圈）
            self.market_combo.blockSignals(False)  # 恢复信号

            self.log(f"⚠️  {market_name}市场功能开发中，已切换回币圈市场", "warning")
            return

        # 正常切换市场类型
        self.current_market_type = selected_market
        self.update_exchange_list()
        self.log(f"切换到 {self.market_combo.currentText()}")

    def on_exchange_changed(self, text):
        """交易所改变"""
        self.current_exchange = text.lower()
        # 清理文本，移除emoji和特殊符号
        clean_text = text.replace('✓', '').replace('@', '').replace('---', '').replace('(j)', '').strip()
        self.log(f"选择交易所: {clean_text}")

    # ==================== 功能方法 ====================

    def start_download(self):
        """开始下载数据 - 使用独立进程避免Bus error"""
        symbol = self.download_symbol.text().strip()
        market = self.download_market.currentText()
        interval = self.download_interval.currentText()
        start_date = self.download_start_date.text().strip()

        # 验证输入
        if not symbol:
            self.log("请输入交易对", "error")
            QMessageBox.warning(self, "输入错误", "请输入交易对")
            return

        if not start_date:
            self.log("请输入开始日期", "error")
            QMessageBox.warning(self, "输入错误", "请输入开始日期（格式：YYYY-MM-DD）")
            return

        self.log(f"开始下载 {symbol} {market} {interval} 数据，起始日期: {start_date}", "info")

        # 禁用下载按钮
        self.download_btn.setEnabled(False)
        self.stop_download_btn.setEnabled(True)
        self.download_progress.setValue(0)

        # 清空输出缓冲区
        self.download_output_buffer = {'stdout': '', 'stderr': ''}

        # 使用QProcess而不是QThread，避免Bus error
        self.download_process = QProcess(self)

        # 连接信号
        self.download_process.readyReadStandardOutput.connect(self.on_download_output)
        self.download_process.readyReadStandardError.connect(self.on_download_output)  # 也读取stderr
        self.download_process.finished.connect(self.on_download_process_finished)

        # 转换市场类型：中文 -> 英文
        market_map = {"现货": "spot", "合约": "futures"}
        market_en = market_map.get(market, market)

        # 准备参数
        params = json.dumps({
            'exchange': self.current_exchange,
            'symbol': symbol,
            'market': market_en,
            'interval': interval,
            'start_date': start_date
        })

        # 启动下载进程
        import sys
        python_exe = sys.executable
        self.download_process.start(python_exe, ['-u', 'download_worker.py', params])

        self.statusBar.showMessage("正在下载数据...")

    def on_download_progress(self, percent, message):
        """下载进度更新"""
        self.download_progress.setValue(percent)
        self.log(f"[{percent}%] {message}", "info")

    def on_download_finished(self, success, message):
        """下载完成（QThread方式）"""
        if success:
            self.log(message, "success")
            self.statusBar.showMessage("下载完成", 5000)
        else:
            self.log(message, "error")
            self.statusBar.showMessage("下载失败", 5000)

        # 恢复按钮状态
        self.download_btn.setEnabled(True)
        self.stop_download_btn.setEnabled(False)
        self.download_progress.setValue(0)

    def on_download_output(self):
        """处理下载进程的输出（QProcess方式）"""
        if self.download_process:
            # 读取标准输出并累积
            output = bytes(self.download_process.readAllStandardOutput()).decode('utf-8')
            self.download_output_buffer['stdout'] += output
            for line in output.strip().split('\n'):
                if line.strip() and not line.startswith('{'):
                    self.log(line, "info")

            # 读取标准错误（loguru输出到stderr）并累积
            error_output = bytes(self.download_process.readAllStandardError()).decode('utf-8')
            self.download_output_buffer['stderr'] += error_output
            for line in error_output.strip().split('\n'):
                if line.strip():
                    self.log(line, "info")

    def on_download_process_finished(self, exit_code, exit_status):
        """下载进程完成（QProcess方式）"""
        # 读取最后的输出（可能还有残留）
        if self.download_process:
            # 读取最后的输出并累积
            final_stdout = bytes(self.download_process.readAllStandardOutput()).decode('utf-8')
            final_stderr = bytes(self.download_process.readAllStandardError()).decode('utf-8')
            self.download_output_buffer['stdout'] += final_stdout
            self.download_output_buffer['stderr'] += final_stderr

            # 合并所有累积的输出
            all_output = self.download_output_buffer['stdout'] + '\n' + self.download_output_buffer['stderr']

            # 查找JSON结果
            result = None
            for line in reversed(all_output.strip().split('\n')):
                if line.strip():
                    try:
                        result = json.loads(line)
                        break
                    except:
                        continue

            if result and result.get('success'):
                self.download_progress.setValue(100)
                self.log(f"✅ {result['message']}", "success")
                self.log(f"文件保存到: {result['filepath']}", "info")
                QMessageBox.information(self, "下载成功", result['message'])
            else:
                error_msg = result.get('message', '下载失败') if result else '下载失败'
                self.log(f"❌ {error_msg}", "error")
                if result and 'traceback' in result:
                    self.log(result['traceback'], "error")
                QMessageBox.warning(self, "下载失败", error_msg)

        # 恢复按钮状态
        self.download_btn.setEnabled(True)
        self.stop_download_btn.setEnabled(False)
        self.statusBar.showMessage("就绪")

    def stop_download(self):
        """停止下载"""
        # 优先检查QProcess
        if hasattr(self, 'download_process') and self.download_process and self.download_process.state() == QProcess.Running:
            self.download_process.kill()
            self.log("下载已停止", "warning")
            self.statusBar.showMessage("下载已停止")
        # 兼容旧的QThread方式
        elif hasattr(self, 'download_thread') and self.download_thread and self.download_thread.isRunning():
            self.download_thread.stop()
            self.log("正在停止下载...", "warning")
            self.statusBar.showMessage("正在停止下载...")
        else:
            self.log("没有正在运行的下载任务", "warning")

    def run_backtest(self):
        """运行回测"""
        backtest_type = self.backtest_type.currentText()
        symbol = self.backtest_symbol.text().strip()
        market = self.backtest_market.currentText()
        interval = self.backtest_interval.currentText()
        capital = self.backtest_capital.value()

        # 验证输入
        if not symbol:
            self.log("请输入交易对", "error")
            QMessageBox.warning(self, "输入错误", "请输入交易对")
            return

        self.log(f"开始{backtest_type}: {symbol} {market} {interval}, 初始资金: {capital} USDT", "info")

        # 清空输出缓冲区
        self.backtest_output_buffer = {'stdout': '', 'stderr': ''}

        # 使用QProcess运行回测
        self.backtest_process = QProcess(self)

        # 连接信号
        self.backtest_process.readyReadStandardOutput.connect(self.on_backtest_output)
        self.backtest_process.readyReadStandardError.connect(self.on_backtest_output)
        self.backtest_process.finished.connect(self.on_backtest_process_finished)

        # 转换市场类型：中文 -> 英文
        market_map = {"现货": "spot", "合约": "futures"}
        market_en = market_map.get(market, market)

        # 准备参数
        params = json.dumps({
            'exchange': self.current_exchange,  # 添加交易所参数
            'symbol': symbol,
            'market': market_en,
            'interval': interval,
            'capital': capital,
            'backtest_type': backtest_type
        })

        # 启动回测进程
        python_exe = sys.executable
        self.backtest_process.start(python_exe, ['-u', 'backtest_worker.py', params])

        self.statusBar.showMessage("正在运行回测...")

    def on_backtest_output(self):
        """读取回测进程输出"""
        if self.backtest_process:
            # 读取并累积stdout
            output = bytes(self.backtest_process.readAllStandardOutput()).decode('utf-8')
            self.backtest_output_buffer['stdout'] += output

            # 读取并累积stderr
            error_output = bytes(self.backtest_process.readAllStandardError()).decode('utf-8')
            self.backtest_output_buffer['stderr'] += error_output

            # 显示日志（stderr中的loguru输出）
            if error_output:
                for line in error_output.split('\n'):
                    if line.strip():
                        self.log(line, "info")

    def on_backtest_process_finished(self, exit_code, exit_status):
        """回测进程完成"""
        # 读取最后的输出
        if self.backtest_process:
            output = bytes(self.backtest_process.readAllStandardOutput()).decode('utf-8')
            self.backtest_output_buffer['stdout'] += output

            error_output = bytes(self.backtest_process.readAllStandardError()).decode('utf-8')
            self.backtest_output_buffer['stderr'] += error_output

        # 解析JSON结果
        stdout = self.backtest_output_buffer['stdout']
        result = None

        # 尝试从stdout中提取JSON
        for line in stdout.split('\n'):
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                try:
                    result = json.loads(line)
                    break
                except:
                    continue

        # 显示结果
        if result and result.get('success'):
            self.log(f"✅ {result['message']}", "success")

            # 保存报告文件路径
            if 'report_file' in result:
                self.last_backtest_report = result['report_file']
                self.log(f"报告已保存: {self.last_backtest_report}", "info")

            # 显示回测结果
            if 'result' in result:
                r = result['result']
                self.log(f"初始资金: {r['initial_capital']:.2f} USDT", "info")
                self.log(f"最终资金: {r['final_capital']:.2f} USDT", "info")
                self.log(f"总收益率: {r['return_pct']:.2f}%", "success" if r['return_pct'] > 0 else "error")
                self.log(f"交易次数: {r['total_trades']}", "info")
                if 'win_rate' in r:
                    self.log(f"胜率: {r['win_rate']:.2f}%", "info")

                msg = f"回测完成！\n\n"
                msg += f"初始资金: {r['initial_capital']:.2f} USDT\n"
                msg += f"最终资金: {r['final_capital']:.2f} USDT\n"
                msg += f"总收益率: {r['return_pct']:.2f}%\n"
                msg += f"交易次数: {r['total_trades']}\n"
                if 'win_rate' in r:
                    msg += f"胜率: {r['win_rate']:.2f}%"

                QMessageBox.information(self, "回测完成", msg)
        else:
            error_msg = result.get('message', '回测失败') if result else '回测失败'
            self.log(f"❌ {error_msg}", "error")
            QMessageBox.warning(self, "回测失败", error_msg)

        self.statusBar.showMessage("就绪")

    def view_backtest_report(self):
        """查看回测报告"""
        if not self.last_backtest_report:
            # 如果没有最近的报告，让用户选择报告文件
            from pathlib import Path
            report_dir = Path('reports/backtest')
            if not report_dir.exists():
                QMessageBox.warning(self, "无报告", "还没有生成任何回测报告！\n请先运行回测。")
                return

            # 列出所有报告文件
            report_files = sorted(report_dir.glob('*.json'), key=lambda x: x.stat().st_mtime, reverse=True)
            if not report_files:
                QMessageBox.warning(self, "无报告", "还没有生成任何回测报告！\n请先运行回测。")
                return

            # 使用最新的报告
            self.last_backtest_report = str(report_files[0])
            self.log(f"打开最新报告: {self.last_backtest_report}", "info")

        # 读取并显示报告
        try:
            import json
            from pathlib import Path

            with open(self.last_backtest_report, 'r', encoding='utf-8') as f:
                report = json.load(f)

            # 创建报告窗口
            report_window = QMessageBox(self)
            report_window.setWindowTitle("回测报告")
            report_window.setIcon(QMessageBox.Information)

            # 构建报告内容
            info = report['backtest_info']
            perf = report['performance']

            content = f"""
<h3>回测信息</h3>
<table>
<tr><td><b>交易对:</b></td><td>{info['symbol']}</td></tr>
<tr><td><b>交易所:</b></td><td>{info['exchange']}</td></tr>
<tr><td><b>市场:</b></td><td>{info['market']}</td></tr>
<tr><td><b>周期:</b></td><td>{info['interval']}</td></tr>
<tr><td><b>回测类型:</b></td><td>{info['backtest_type']}</td></tr>
<tr><td><b>数据范围:</b></td><td>{info['data_range']}</td></tr>
<tr><td><b>数据条数:</b></td><td>{info['data_count']}</td></tr>
</table>

<h3>回测结果</h3>
<table>
<tr><td><b>初始资金:</b></td><td>{perf['initial_capital']:.2f} USDT</td></tr>
<tr><td><b>最终资金:</b></td><td>{perf['final_capital']:.2f} USDT</td></tr>
<tr><td><b>总收益率:</b></td><td style="color: {'green' if perf['return_pct'] > 0 else 'red'}"><b>{perf['return_pct']:.2f}%</b></td></tr>
<tr><td><b>总交易次数:</b></td><td>{perf['total_trades']}</td></tr>
<tr><td><b>盈利次数:</b></td><td>{perf['winning_trades']}</td></tr>
<tr><td><b>亏损次数:</b></td><td>{perf['losing_trades']}</td></tr>
<tr><td><b>胜率:</b></td><td>{perf['win_rate']:.2f}%</td></tr>
<tr><td><b>平均盈利:</b></td><td>{perf['avg_win']:.2f}%</td></tr>
<tr><td><b>平均亏损:</b></td><td>{perf['avg_loss']:.2f}%</td></tr>
<tr><td><b>盈亏比:</b></td><td>{perf['profit_factor']:.2f}</td></tr>
</table>

<p><small>报告文件: {Path(self.last_backtest_report).name}</small></p>
"""

            report_window.setText(content)
            report_window.setTextFormat(1)  # RichText

            # 添加"查看详细交易"按钮
            detail_btn = report_window.addButton("查看详细交易", QMessageBox.ActionRole)
            report_window.addButton(QMessageBox.Ok)

            result = report_window.exec_()

            # 如果点击了"查看详细交易"
            if report_window.clickedButton() == detail_btn:
                self.show_trade_details(report['trades'])

            self.log("报告查看完成", "info")

        except Exception as e:
            self.log(f"打开报告失败: {str(e)}", "error")
            QMessageBox.warning(self, "错误", f"无法打开报告文件:\n{str(e)}")

    def show_trade_details(self, trades):
        """显示详细交易记录"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem

        dialog = QDialog(self)
        dialog.setWindowTitle("详细交易记录")
        dialog.resize(800, 600)

        layout = QVBoxLayout(dialog)

        # 创建表格
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["时间", "操作", "价格", "资金", "收益率"])
        table.setRowCount(len(trades))

        # 填充数据
        for i, trade in enumerate(trades):
            table.setItem(i, 0, QTableWidgetItem(trade['time']))
            table.setItem(i, 1, QTableWidgetItem(trade['action']))
            table.setItem(i, 2, QTableWidgetItem(f"{trade['price']:.4f}"))
            table.setItem(i, 3, QTableWidgetItem(f"{trade['capital']:.2f}"))
            pnl = trade.get('pnl', 0)
            pnl_item = QTableWidgetItem(f"{pnl:.2f}%" if pnl != 0 else "-")
            if pnl > 0:
                pnl_item.setForeground(QColor(107, 207, 127))  # 绿色
            elif pnl < 0:
                pnl_item.setForeground(QColor(255, 107, 107))  # 红色
            table.setItem(i, 4, pnl_item)

        # 自动调整列宽
        table.resizeColumnsToContents()

        layout.addWidget(table)
        dialog.exec_()

    def start_paper_trading(self):
        """启动模拟交易"""
        symbol = self.paper_symbol.text().strip()
        market = self.paper_market.currentText()
        capital = self.paper_capital.value()
        interval = self.paper_interval.currentText()

        # 验证输入
        if not symbol:
            self.log("请输入交易对", "error")
            QMessageBox.warning(self, "输入错误", "请输入交易对")
            return

        self.log(f"启动模拟交易: {symbol} {market}, 资金: {capital} USDT, 周期: {interval}", "success")

        self.paper_start_btn.setEnabled(False)
        self.paper_stop_btn.setEnabled(True)
        self.paper_status_label.setText("状态: 运行中")
        self.paper_trading_running = True
        self.paper_trading_manual_stop = False  # 重置手动停止标记

        # 记录初始状态
        self.paper_trading_stats = {
            'initial_capital': capital,
            'current_capital': capital,
            'total_trades': 0
        }

        # 使用QProcess运行模拟交易
        self.paper_trading_process = QProcess(self)

        # 连接信号
        self.paper_trading_process.readyReadStandardOutput.connect(self.on_paper_trading_output)
        self.paper_trading_process.readyReadStandardError.connect(self.on_paper_trading_output)
        self.paper_trading_process.finished.connect(self.on_paper_trading_finished)

        # 转换市场类型：中文 -> 英文
        market_map = {"现货": "spot", "合约": "futures"}
        market_en = market_map.get(market, market)

        # 准备参数
        params = json.dumps({
            'exchange': self.current_exchange,
            'symbol': symbol,
            'market': market_en,
            'interval': interval,
            'capital': capital
        })

        # 启动模拟交易进程
        python_exe = sys.executable

        # 设置工作目录
        import os
        work_dir = os.path.dirname(os.path.abspath(__file__))
        self.paper_trading_process.setWorkingDirectory(work_dir)

        self.log(f"工作目录: {work_dir}", "info")
        self.log(f"启动命令: {python_exe} -u paper_trading_worker.py", "info")
        self.log(f"参数: {params}", "info")

        # 添加错误处理
        self.paper_trading_process.errorOccurred.connect(self.on_paper_trading_error)
        self.paper_trading_process.stateChanged.connect(self.on_paper_trading_state_changed)

        self.paper_trading_process.start(python_exe, ['-u', 'paper_trading_worker.py', params])

        # 等待进程启动
        if not self.paper_trading_process.waitForStarted(3000):
            self.log("进程启动失败！", "error")
            self.paper_start_btn.setEnabled(True)
            self.paper_stop_btn.setEnabled(False)
            self.paper_status_label.setText("状态: 启动失败")
            return

        self.log(f"模拟交易进程已启动 (PID: {self.paper_trading_process.processId()})", "success")
        self.statusBar.showMessage("模拟交易运行中...")

    def on_paper_trading_output(self):
        """处理模拟交易输出"""
        if not self.paper_trading_process:
            return

        # 读取stdout
        output = bytes(self.paper_trading_process.readAllStandardOutput()).decode('utf-8')
        if output:
            for line in output.strip().split('\n'):
                line = line.strip()
                if not line:
                    continue

                # 尝试解析JSON状态更新
                if line.startswith('{'):
                    try:
                        status = json.loads(line)
                        if status.get('type') == 'trade':
                            # 交易信号
                            action = status['action']
                            price = status['price']
                            capital = status['capital']

                            # 更新统计数据
                            self.paper_trading_stats['current_capital'] = capital
                            if 'BUY' in action:
                                self.log(f"[买入] 价格: {price:.6f}, 资金: {capital:.2f} USDT", "success")
                                self.paper_trading_stats['total_trades'] += 1
                            elif 'SELL' in action:
                                pnl = status.get('pnl', 0)
                                self.log(f"[卖出] 价格: {price:.6f}, 收益: {pnl:.2f}%, 资金: {capital:.2f} USDT",
                                        "success" if pnl > 0 else "error")

                            # 更新状态显示
                            profit = capital - self.paper_trading_stats['initial_capital']
                            profit_pct = profit / self.paper_trading_stats['initial_capital'] * 100
                            self.paper_profit_label.setText(f"当前盈亏: {profit:.2f} USDT ({profit_pct:.2f}%)")

                        elif status.get('type') == 'heartbeat':
                            # 心跳信号，更新价格（不在日志中显示，避免刷屏）
                            price = status['price']
                            capital = status['capital']
                            position = status['position']
                            progress = status.get('progress', '')
                            pos_text = "持仓中" if position else "空仓"
                            status_text = f"状态: 运行中 | {pos_text} | 价格: {price:.6f} | {progress}"
                            self.paper_status_label.setText(status_text)

                            # 更新当前资金
                            self.paper_trading_stats['current_capital'] = capital

                        elif status.get('type') == 'complete':
                            # 完成信号
                            initial = status['initial_capital']
                            final = status['final_capital']
                            return_pct = status['return_pct']
                            total_trades = status['total_trades']

                            self.log(f"模拟交易完成！", "success")
                            self.log(f"初始资金: {initial:.2f} USDT", "info")
                            self.log(f"最终资金: {final:.2f} USDT", "info")
                            self.log(f"总收益率: {return_pct:.2f}%", "success" if return_pct > 0 else "error")
                            self.log(f"交易次数: {total_trades}", "info")

                            # 更新最终状态
                            profit = final - initial
                            self.paper_profit_label.setText(f"最终盈亏: {profit:.2f} USDT ({return_pct:.2f}%)")

                            # 显示完整结果对话框
                            result_msg = f"""
<h3>模拟交易完成</h3>
<table style="width: 100%;">
<tr><td><b>初始资金:</b></td><td>{initial:.2f} USDT</td></tr>
<tr><td><b>最终资金:</b></td><td>{final:.2f} USDT</td></tr>
<tr><td><b>总收益:</b></td><td style="color: {'green' if profit >= 0 else 'red'}"><b>{profit:+.2f} USDT ({return_pct:+.2f}%)</b></td></tr>
<tr><td><b>交易次数:</b></td><td>{total_trades}</td></tr>
</table>
<p><small>已完成全部历史数据回放</small></p>
"""

                            msg_box = QMessageBox(self)
                            msg_box.setWindowTitle("模拟交易完成")
                            msg_box.setIcon(QMessageBox.Information if return_pct >= 0 else QMessageBox.Warning)
                            msg_box.setText(result_msg)
                            msg_box.setTextFormat(1)  # RichText
                            msg_box.exec_()

                    except Exception as e:
                        # 不是JSON，当作普通日志
                        self.log(line, "info")
                else:
                    self.log(line, "info")

        # 读取stderr
        error_output = bytes(self.paper_trading_process.readAllStandardError()).decode('utf-8')
        if error_output:
            for line in error_output.strip().split('\n'):
                if line.strip():
                    self.log(line, "info")

    def on_paper_trading_error(self, error):
        """模拟交易进程错误"""
        # 如果是手动停止，不显示错误信息
        if self.paper_trading_manual_stop:
            return

        error_messages = {
            0: "进程启动失败",
            1: "进程崩溃",
            2: "进程超时",
            3: "写入错误",
            4: "读取错误",
            5: "未知错误"
        }
        error_msg = error_messages.get(error, f"错误代码: {error}")
        self.log(f"模拟交易进程错误: {error_msg}", "error")

    def on_paper_trading_state_changed(self, state):
        """模拟交易进程状态变化"""
        # 只在启动时显示状态，避免日志刷屏
        if state == 1:  # 正在启动
            self.log(f"进程正在启动...", "info")
        elif state == 2:  # 运行中
            self.log(f"进程已启动，开始运行", "info")

    def on_paper_trading_finished(self, exit_code, exit_status):
        """模拟交易进程结束"""
        # 如果是手动停止，显示友好信息
        if self.paper_trading_manual_stop:
            self.log("模拟交易已手动停止", "info")
        elif exit_code == 0:
            self.log("模拟交易正常结束", "success")
        else:
            self.log(f"模拟交易异常结束 (退出码: {exit_code})", "warning")

        self.paper_trading_running = False
        self.paper_start_btn.setEnabled(True)
        self.paper_stop_btn.setEnabled(False)
        self.paper_status_label.setText("状态: 已停止")
        self.statusBar.showMessage("就绪")

    def stop_paper_trading(self):
        """停止模拟交易"""
        if not self.paper_trading_process or not self.paper_trading_running:
            return

        # 标记为手动停止
        self.paper_trading_manual_stop = True

        # 显示当前结果
        initial = self.paper_trading_stats['initial_capital']
        current = self.paper_trading_stats['current_capital']
        trades = self.paper_trading_stats['total_trades']

        if initial > 0:
            profit = current - initial
            profit_pct = profit / initial * 100

            result_msg = f"""
<h3>模拟交易结果</h3>
<table style="width: 100%;">
<tr><td><b>初始资金:</b></td><td>{initial:.2f} USDT</td></tr>
<tr><td><b>当前资金:</b></td><td>{current:.2f} USDT</td></tr>
<tr><td><b>盈亏:</b></td><td style="color: {'green' if profit >= 0 else 'red'}"><b>{profit:+.2f} USDT ({profit_pct:+.2f}%)</b></td></tr>
<tr><td><b>交易次数:</b></td><td>{trades}</td></tr>
</table>
<p><small>注意：这是手动停止时的中间结果</small></p>
"""

            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("模拟交易结果")
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setText(result_msg)
            msg_box.setTextFormat(1)  # RichText
            msg_box.exec_()

        # 终止进程
        self.log("正在停止模拟交易...", "info")
        self.paper_trading_process.terminate()  # 使用terminate而不是kill，更优雅

        # 等待进程结束（最多2秒）
        if not self.paper_trading_process.waitForFinished(2000):
            self.paper_trading_process.kill()  # 如果2秒后还没结束，强制终止

        self.paper_trading_process = None
        self.paper_trading_running = False
        self.paper_start_btn.setEnabled(True)
        self.paper_stop_btn.setEnabled(False)
        self.paper_stop_btn.setEnabled(False)
        self.paper_status_label.setText("状态: 已停止")

        self.statusBar.showMessage("模拟交易已停止")

    def test_api_connection(self):
        """测试API连接"""
        api_key = self.live_api_key.text()
        api_secret = self.live_api_secret.text()

        if not api_key or not api_secret:
            QMessageBox.warning(self, "警告", "请输入API Key和Secret")
            return

        self.log("测试API连接...")
        # TODO: 实际测试API连接
        self.log("API连接成功", "success")
        self.status_label.setText("● 已连接")
        self.status_label.setStyleSheet("color: green;")

    def start_live_trading(self):
        """启动实盘交易"""
        reply = self.show_message(
            "确认",
            "确定要启动实盘交易吗？这将使用真实资金！",
            "question"
        )

        if reply == QMessageBox.Yes:
            self.log("启动实盘交易", "success")
            self.live_start_btn.setEnabled(False)
            self.live_stop_btn.setEnabled(True)
            # TODO: 调用实际的实盘交易功能

    def stop_live_trading(self):
        """停止实盘交易"""
        self.log("停止实盘交易", "warning")
        self.live_start_btn.setEnabled(True)
        self.live_stop_btn.setEnabled(False)

    def import_strategy(self):
        """导入加密的策略文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择策略文件",
            "",
            "策略文件 (*.qts);;All Files (*)"
        )

        if not file_path:
            return

        # 弹出密码输入对话框
        password, ok = QInputDialog.getText(
            self,
            "输入密码",
            "请输入策略文件的解密密码:",
            QLineEdit.Password
        )

        if not ok or not password:
            return

        try:
            from tools.strategy_crypto import StrategyEncryptor

            # 验证密码
            encryptor = StrategyEncryptor(password)
            data = encryptor.decrypt_file(file_path)

            if data['type'] != 'strategy':
                QMessageBox.warning(self, "错误", "这不是一个策略文件！")
                return

            # 保存到导入目录
            strategy_name = data['name']
            save_path = self.strategy_dir / f"{strategy_name}.py"

            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(data['content'])

            # 添加到列表
            from datetime import datetime
            strategy_info = {
                'name': strategy_name,
                'file': data['original_file'],
                'encrypted': True,
                'import_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'path': str(save_path)
            }
            self.strategies.append(strategy_info)

            # 更新表格
            self.update_strategy_table()

            self.log(f"✅ 策略导入成功: {strategy_name}", "success")
            QMessageBox.information(self, "成功", f"策略 {strategy_name} 导入成功！")

        except Exception as e:
            self.log(f"❌ 策略导入失败: {e}", "error")
            QMessageBox.critical(self, "错误", f"策略导入失败:\n{str(e)}\n\n可能原因：密码错误或文件损坏")

    def update_strategy_table(self):
        """更新策略表格"""
        self.strategy_table.setRowCount(len(self.strategies))

        for i, strategy in enumerate(self.strategies):
            # 策略名称
            name_item = QTableWidgetItem(strategy['name'])
            name_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.strategy_table.setItem(i, 0, name_item)

            # 文件名
            file_item = QTableWidgetItem(strategy['file'])
            file_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.strategy_table.setItem(i, 1, file_item)

            # 加密状态
            encrypted_item = QTableWidgetItem("✓" if strategy['encrypted'] else "✗")
            encrypted_item.setTextAlignment(Qt.AlignCenter)
            if strategy['encrypted']:
                encrypted_item.setForeground(QColor("#6bcf7f"))  # 绿色
            else:
                encrypted_item.setForeground(QColor("#ff6b6b"))  # 红色
            self.strategy_table.setItem(i, 2, encrypted_item)

            # 导入时间
            time_item = QTableWidgetItem(strategy['import_time'])
            time_item.setTextAlignment(Qt.AlignCenter)
            self.strategy_table.setItem(i, 3, time_item)

            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            btn_layout.setSpacing(4)

            view_btn = QPushButton("查看")
            view_btn.setFixedSize(50, 28)
            view_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4a9eff;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #3d8ae6;
                }
                QPushButton:pressed {
                    background-color: #2d7ad6;
                }
            """)
            view_btn.clicked.connect(lambda checked, idx=i: self.view_strategy(idx))
            btn_layout.addWidget(view_btn)

            # 微调按钮
            tune_btn = QPushButton("微调")
            tune_btn.setFixedSize(50, 28)
            tune_btn.setStyleSheet("""
                QPushButton {
                    background-color: #ffa726;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #fb8c00;
                }
                QPushButton:pressed {
                    background-color: #e67700;
                }
            """)
            tune_btn.clicked.connect(lambda checked, idx=i: self.tune_strategy(idx))
            btn_layout.addWidget(tune_btn)

            btn_layout.addStretch()

            self.strategy_table.setCellWidget(i, 4, btn_widget)

    def view_strategy(self, index):
        """查看策略代码"""
        if index >= len(self.strategies):
            return

        strategy = self.strategies[index]

        try:
            with open(strategy['path'], 'r', encoding='utf-8') as f:
                content = f.read()

            # 创建自定义对话框
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QLabel
            from PyQt5.QtCore import Qt

            dialog = QDialog(self)
            dialog.setWindowTitle(f"策略代码 - {strategy['name']}")
            dialog.setMinimumSize(800, 600)

            layout = QVBoxLayout(dialog)

            # 信息标签
            info_label = QLabel(f"<b>文件:</b> {strategy['file']}<br><b>导入时间:</b> {strategy['import_time']}")
            info_label.setStyleSheet("padding: 10px; background-color: #2d2d2d; border-radius: 4px;")
            layout.addWidget(info_label)

            # 代码显示区域
            code_text = QTextEdit()
            code_text.setReadOnly(True)
            code_text.setPlainText(content)
            code_text.setStyleSheet("""
                QTextEdit {
                    background-color: #1e1e1e;
                    color: #d4d4d4;
                    font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
                    font-size: 12px;
                    border: 1px solid #3d3d3d;
                    border-radius: 4px;
                    padding: 10px;
                }
            """)
            layout.addWidget(code_text)

            # 确定按钮
            ok_btn = QPushButton("确定")
            ok_btn.setFixedHeight(36)
            ok_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4a9eff;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 24px;
                    font-size: 13px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #3d8ae6;
                }
                QPushButton:pressed {
                    background-color: #2d7ad6;
                }
            """)
            ok_btn.clicked.connect(dialog.accept)
            layout.addWidget(ok_btn, alignment=Qt.AlignRight)

            dialog.exec_()

        except Exception as e:
            self.show_message("错误", f"无法读取策略文件:\n{str(e)}", "error")

    def tune_strategy(self, index):
        """微调策略参数"""
        if index >= len(self.strategies):
            return

        strategy = self.strategies[index]

        try:
            from tools.strategy_parameter_parser import StrategyParameterParser

            # 解析策略参数
            parameters = StrategyParameterParser.parse_parameters(strategy['path'])

            if not parameters:
                self.show_message("提示", "该策略没有可调整的参数", "warning")
                return

            # 创建参数调整对话框
            from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                        QPushButton, QFormLayout, QSpinBox, QDoubleSpinBox,
                                        QLineEdit, QCheckBox, QScrollArea, QWidget)
            from PyQt5.QtCore import Qt

            dialog = QDialog(self)
            dialog.setWindowTitle(f"微调策略参数 - {strategy['name']}")
            dialog.setMinimumSize(500, 400)

            main_layout = QVBoxLayout(dialog)

            # 标题
            title_label = QLabel(f"<h3>📊 {strategy['name']}</h3>")
            title_label.setStyleSheet("padding: 10px; background-color: #2d2d2d; border-radius: 4px;")
            main_layout.addWidget(title_label)

            # 创建滚动区域
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet("""
                QScrollArea {
                    border: 1px solid #3d3d3d;
                    border-radius: 4px;
                    background-color: #1e1e1e;
                }
            """)

            scroll_widget = QWidget()
            form_layout = QFormLayout(scroll_widget)
            form_layout.setSpacing(15)

            # 存储输入控件
            input_widgets = {}

            # 为每个参数创建输入控件
            for param in parameters:
                param_name = param['name']
                param_type = param['type']
                default_value = param['default_value']
                description = param['description']

                # 创建标签（纯文本，不使用HTML）
                label_text = f"{param_name}"
                if description:
                    label_text = f"{param_name}\n{description}"
                label = QLabel(label_text)
                label.setWordWrap(True)
                label.setStyleSheet("QLabel { color: #d4d4d4; font-size: 12px; }")

                # 根据类型创建输入控件
                if param_type == "int":
                    widget = QSpinBox()
                    widget.setRange(-999999, 999999)
                    if default_value is not None:
                        widget.setValue(int(default_value))
                    widget.setStyleSheet("""
                        QSpinBox {
                            background-color: #2d2d2d;
                            color: white;
                            border: 1px solid #3d3d3d;
                            border-radius: 4px;
                            padding: 5px;
                            min-height: 25px;
                        }
                    """)
                elif param_type == "float":
                    widget = QDoubleSpinBox()
                    widget.setRange(-999999.0, 999999.0)
                    widget.setDecimals(4)
                    if default_value is not None:
                        widget.setValue(float(default_value))
                    widget.setStyleSheet("""
                        QDoubleSpinBox {
                            background-color: #2d2d2d;
                            color: white;
                            border: 1px solid #3d3d3d;
                            border-radius: 4px;
                            padding: 5px;
                            min-height: 25px;
                        }
                    """)
                elif param_type == "bool":
                    widget = QCheckBox()
                    if default_value is not None:
                        widget.setChecked(bool(default_value))
                elif param_type == "str":
                    widget = QLineEdit()
                    if default_value is not None:
                        widget.setText(str(default_value))
                    widget.setStyleSheet("""
                        QLineEdit {
                            background-color: #2d2d2d;
                            color: white;
                            border: 1px solid #3d3d3d;
                            border-radius: 4px;
                            padding: 5px;
                            min-height: 25px;
                        }
                    """)
                else:
                    widget = QLineEdit()
                    if default_value is not None:
                        widget.setText(str(default_value))

                input_widgets[param_name] = (widget, param_type)
                form_layout.addRow(label, widget)

            scroll.setWidget(scroll_widget)
            main_layout.addWidget(scroll)

            # 按钮
            btn_layout = QHBoxLayout()
            btn_layout.addStretch()

            cancel_btn = QPushButton("取消")
            cancel_btn.setFixedHeight(36)
            cancel_btn.setStyleSheet("""
                QPushButton {
                    background-color: #666;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 24px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #777;
                }
            """)
            cancel_btn.clicked.connect(dialog.reject)
            btn_layout.addWidget(cancel_btn)

            ok_btn = QPushButton("确定")
            ok_btn.setFixedHeight(36)
            ok_btn.setStyleSheet("""
                QPushButton {
                    background-color: #6bcf7f;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 24px;
                    font-size: 13px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #5abf6f;
                }
                QPushButton:pressed {
                    background-color: #4aaf5f;
                }
            """)
            ok_btn.clicked.connect(dialog.accept)
            btn_layout.addWidget(ok_btn)

            main_layout.addLayout(btn_layout)

            # 显示对话框
            if dialog.exec_() == QDialog.Accepted:
                # 收集新参数值
                new_params = {}
                for param_name, (widget, param_type) in input_widgets.items():
                    if param_type == "int":
                        new_params[param_name] = widget.value()
                    elif param_type == "float":
                        new_params[param_name] = widget.value()
                    elif param_type == "bool":
                        new_params[param_name] = widget.isChecked()
                    elif param_type == "str":
                        new_params[param_name] = widget.text()

                # 更新策略文件
                if StrategyParameterParser.update_parameters(strategy['path'], new_params):
                    self.log(f"✅ 策略参数已更新: {strategy['name']}", "success")
                    self.show_message("成功", f"策略参数已更新！\n\n{new_params}", "info")
                else:
                    self.show_message("错误", "更新策略参数失败！", "error")

        except Exception as e:
            self.log(f"❌ 微调策略失败: {e}", "error")
            self.show_message("错误", f"微调策略失败:\n{str(e)}", "error")

    def remove_strategy(self):
        """移除策略"""
        current_row = self.strategy_table.currentRow()
        if current_row < 0:
            self.show_message("提示", "请先选择要移除的策略", "warning")
            return

        strategy = self.strategies[current_row]
        reply = self.show_message(
            "确认",
            f"确定要移除策略 {strategy['name']} 吗？",
            "question"
        )

        if reply == QMessageBox.Yes:
            self.strategies.pop(current_row)
            self.update_strategy_table()
            self.log(f"已移除策略: {strategy['name']}", "info")

    def encrypt_strategy_file(self):
        """加密策略文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择要加密的策略文件",
            "",
            "Python Files (*.py);;All Files (*)"
        )

        if not file_path:
            return

        # 输入密码
        password, ok = QInputDialog.getText(
            self,
            "设置密码",
            "请输入加密密码（至少6位）:",
            QLineEdit.Password
        )

        if not ok or not password:
            return

        if len(password) < 6:
            QMessageBox.warning(self, "错误", "密码长度至少为6位！")
            return

        # 确认密码
        password_confirm, ok = QInputDialog.getText(
            self,
            "确认密码",
            "请再次输入密码:",
            QLineEdit.Password
        )

        if not ok or password != password_confirm:
            QMessageBox.warning(self, "错误", "两次输入的密码不一致！")
            return

        # 选择输出路径
        from pathlib import Path
        default_output = str(Path(file_path).with_suffix('.qts'))
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存加密文件",
            default_output,
            "策略文件 (*.qts);;All Files (*)"
        )

        if not output_path:
            return

        try:
            from tools.strategy_crypto import StrategyEncryptor
            encryptor = StrategyEncryptor(password)
            output_file = encryptor.encrypt_strategy(file_path, output_path)

            self.log(f"✅ 策略加密成功: {output_file}", "success")
            QMessageBox.information(
                self,
                "成功",
                f"策略文件已加密！\n\n输出文件: {output_file}\n\n⚠️ 请妥善保管密码，丢失后无法恢复！"
            )

        except Exception as e:
            self.log(f"❌ 策略加密失败: {e}", "error")
            QMessageBox.critical(self, "错误", f"策略加密失败:\n{str(e)}")

    def import_backtest_config(self):
        """导入回测配置"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择回测配置文件",
            "",
            "回测配置 (*.qtb);;All Files (*)"
        )

        if not file_path:
            return

        # 弹出密码输入对话框
        password, ok = QInputDialog.getText(
            self,
            "输入密码",
            "请输入配置文件的解密密码:",
            QLineEdit.Password
        )

        if not ok or not password:
            return

        try:
            from tools.strategy_crypto import StrategyEncryptor

            # 验证密码
            encryptor = StrategyEncryptor(password)
            data = encryptor.decrypt_file(file_path)

            if data['type'] != 'backtest':
                QMessageBox.warning(self, "错误", "这不是一个回测配置文件！")
                return

            # 添加到列表
            from datetime import datetime
            from pathlib import Path
            config_info = {
                'name': Path(file_path).stem,
                'config': data['config'],
                'import_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            self.backtest_configs.append(config_info)

            # 更新表格
            self.update_backtest_config_table()

            self.log(f"✅ 回测配置导入成功", "success")
            QMessageBox.information(self, "成功", "回测配置导入成功！")

        except Exception as e:
            self.log(f"❌ 回测配置导入失败: {e}", "error")
            QMessageBox.critical(self, "错误", f"回测配置导入失败:\n{str(e)}\n\n可能原因：密码错误或文件损坏")

    def update_backtest_config_table(self):
        """更新回测配置表格"""
        self.backtest_config_table.setRowCount(len(self.backtest_configs))

        for i, config in enumerate(self.backtest_configs):
            cfg = config['config']

            # 配置名称
            name_item = QTableWidgetItem(config['name'])
            name_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.backtest_config_table.setItem(i, 0, name_item)

            # 交易对（处理嵌套结构）
            symbol = 'N/A'
            if 'market_config' in cfg and 'symbol' in cfg['market_config']:
                symbol = cfg['market_config']['symbol']
            elif 'symbol' in cfg:
                symbol = cfg['symbol']
            symbol_item = QTableWidgetItem(symbol)
            symbol_item.setTextAlignment(Qt.AlignCenter)
            self.backtest_config_table.setItem(i, 1, symbol_item)

            # 周期（处理嵌套结构）
            interval = 'N/A'
            if 'market_config' in cfg and 'interval' in cfg['market_config']:
                interval = cfg['market_config']['interval']
            elif 'interval' in cfg:
                interval = cfg['interval']
            interval_item = QTableWidgetItem(interval)
            interval_item.setTextAlignment(Qt.AlignCenter)
            self.backtest_config_table.setItem(i, 2, interval_item)

            # 导入时间
            time_item = QTableWidgetItem(config['import_time'])
            time_item.setTextAlignment(Qt.AlignCenter)
            self.backtest_config_table.setItem(i, 3, time_item)

            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            btn_layout.setSpacing(4)

            view_btn = QPushButton("查看")
            view_btn.setFixedSize(50, 28)
            view_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4a9eff;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #3d8ae6;
                }
                QPushButton:pressed {
                    background-color: #2d7ad6;
                }
            """)
            view_btn.clicked.connect(lambda checked, idx=i: self.view_backtest_config(idx))
            btn_layout.addWidget(view_btn)

            load_btn = QPushButton("加载")
            load_btn.setFixedSize(50, 28)
            load_btn.setStyleSheet("""
                QPushButton {
                    background-color: #6bcf7f;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #5abf6f;
                }
                QPushButton:pressed {
                    background-color: #4aaf5f;
                }
            """)
            load_btn.clicked.connect(lambda checked, idx=i: self.load_backtest_config(idx))
            btn_layout.addWidget(load_btn)

            # 微调按钮
            tune_btn = QPushButton("微调")
            tune_btn.setFixedSize(50, 28)
            tune_btn.setStyleSheet("""
                QPushButton {
                    background-color: #ffa726;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #ff9716;
                }
                QPushButton:pressed {
                    background-color: #ff8706;
                }
            """)
            tune_btn.clicked.connect(lambda checked, idx=i: self.tune_backtest_config(idx))
            btn_layout.addWidget(tune_btn)

            btn_layout.addStretch()

            self.backtest_config_table.setCellWidget(i, 4, btn_widget)

    def view_backtest_config(self, index):
        """查看回测配置"""
        if index >= len(self.backtest_configs):
            return

        config = self.backtest_configs[index]

        import json
        config_text = json.dumps(config['config'], indent=2, ensure_ascii=False)

        # 创建自定义对话框
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QLabel
        from PyQt5.QtCore import Qt

        dialog = QDialog(self)
        dialog.setWindowTitle(f"回测配置 - {config['name']}")
        dialog.setMinimumSize(600, 500)

        layout = QVBoxLayout(dialog)

        # 信息标签
        info_label = QLabel(f"<b>导入时间:</b> {config['import_time']}")
        info_label.setStyleSheet("padding: 10px; background-color: #2d2d2d; border-radius: 4px;")
        layout.addWidget(info_label)

        # JSON显示区域
        json_text = QTextEdit()
        json_text.setReadOnly(True)
        json_text.setPlainText(config_text)
        json_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
                font-size: 12px;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 10px;
            }
        """)
        layout.addWidget(json_text)

        # 确定按钮
        ok_btn = QPushButton("确定")
        ok_btn.setFixedHeight(36)
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a9eff;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 24px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3d8ae6;
            }
            QPushButton:pressed {
                background-color: #2d7ad6;
            }
        """)
        ok_btn.clicked.connect(dialog.accept)
        layout.addWidget(ok_btn, alignment=Qt.AlignRight)

        dialog.exec_()

    def load_backtest_config(self, index):
        """加载回测配置到回测标签页"""
        if index >= len(self.backtest_configs):
            return

        config = self.backtest_configs[index]['config']

        # 切换到回测标签页
        self.tab_widget.setCurrentIndex(1)  # 回测测试是第2个标签页（索引从0开始）

        # 处理嵌套结构的配置（如market_config）
        if 'market_config' in config:
            market_config = config['market_config']
            if 'symbol' in market_config:
                self.backtest_symbol.setText(market_config['symbol'])
            if 'market_type' in market_config:
                market_map = {"spot": "现货", "futures": "合约"}
                market_text = market_map.get(market_config['market_type'], market_config['market_type'])
                idx = self.backtest_market.findText(market_text)
                if idx >= 0:
                    self.backtest_market.setCurrentIndex(idx)
            if 'interval' in market_config:
                idx = self.backtest_interval.findText(market_config['interval'])
                if idx >= 0:
                    self.backtest_interval.setCurrentIndex(idx)
        else:
            # 处理扁平结构的配置
            if 'symbol' in config:
                self.backtest_symbol.setText(config['symbol'])
            if 'market' in config:
                market_map = {"spot": "现货", "futures": "合约"}
                market_text = market_map.get(config['market'], config['market'])
                idx = self.backtest_market.findText(market_text)
                if idx >= 0:
                    self.backtest_market.setCurrentIndex(idx)
            if 'interval' in config:
                idx = self.backtest_interval.findText(config['interval'])
                if idx >= 0:
                    self.backtest_interval.setCurrentIndex(idx)

        self.log(f"✅ 已加载回测配置: {self.backtest_configs[index]['name']}", "success")
        QMessageBox.information(self, "成功", "回测配置已加载到回测标签页！")

    def tune_backtest_config(self, index):
        """微调回测配置参数"""
        if index >= len(self.backtest_configs):
            return

        config_entry = self.backtest_configs[index]
        config = config_entry['config']

        # 创建微调对话框
        from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLabel,
                                     QSpinBox, QDoubleSpinBox, QLineEdit, QCheckBox,
                                     QPushButton, QScrollArea, QWidget, QHBoxLayout)
        from PyQt5.QtCore import Qt

        dialog = QDialog(self)
        dialog.setWindowTitle(f"微调回测配置 - {config_entry['name']}")
        dialog.setMinimumSize(600, 500)

        main_layout = QVBoxLayout(dialog)

        # 标题
        title_label = QLabel(f"📊 {config_entry['name']}")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #4a9eff;
                padding: 10px;
            }
        """)
        main_layout.addWidget(title_label)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #2b2b2b;
            }
        """)

        scroll_widget = QWidget()
        form_layout = QFormLayout(scroll_widget)
        form_layout.setSpacing(15)
        form_layout.setContentsMargins(20, 20, 20, 20)

        # 存储输入控件的字典
        input_widgets = {}

        # 字段名中文映射
        field_name_map = {
            'symbol': '交易对',
            'market_type': '市场类型',
            'exchange': '交易所',
            'interval': '时间周期',
            'start_date': '开始日期',
            'end_date': '结束日期',
            'M1': '短期MA',
            'M2': '中期MA',
            'M3': '中长期MA',
            'M4': '长期MA',
            'M99': 'ACD平滑',
            'N': '信号平滑',
            'SHORT': 'MACD短期',
            'LONG': 'MACD长期',
            'MID': 'MACD信号',
            'stkmoney': '单次交易金额',
            'stoploss': '移动止损比率',
            'lossrate': '固定止损比率',
            'spot_fee_rate': '现货手续费',
            'futures_fee_rate': '合约手续费',
            'slippage_rate': '滑点',
            'take_profit_rate': '止盈比率',
            'stop_loss_rate': '止损比率',
            'trailing_stop': '启用移动止损',
            'trailing_stop_rate': '移动止损比率',
            'initial_capital': '初始资金',
            'position_sizing': '仓位管理',
            'max_position_pct': '最大仓位比例',
            'reserve_cash_pct': '保留现金比例',
            'HA_threshold': 'HA阈值',
            'WD3_max': 'WD3最大值',
            'QS_threshold': 'QS阈值',
            'QJ_threshold': 'QJ阈值',
            'WD3_threshold': 'WD3阈值',
            'save_trades': '保存交易记录',
            'save_signals': '保存信号',
            'generate_report': '生成报告',
            'plot_results': '绘制结果',
        }

        # 过滤掉的元数据字段
        excluded_fields = {
            'name', 'description', 'version', 'created_date', 'comment',
            'source', 'original_files', 'conversion_date', 'compatibility',
            'tested_symbols', 'original', 'adapted', 'reason', 'impact'
        }

        # 提取所有可调参数
        def extract_params(cfg, prefix=''):
            """递归提取配置中的参数"""
            params = []
            for key, value in cfg.items():
                # 跳过元数据字段
                if key in excluded_fields:
                    continue

                if isinstance(value, dict):
                    # 递归处理嵌套字典
                    params.extend(extract_params(value, f"{prefix}{key}."))
                elif isinstance(value, (int, float, str, bool)):
                    # 使用中文名称
                    display_name = field_name_map.get(key, key)
                    full_name = f"{prefix}{display_name}" if prefix else display_name
                    params.append((f"{prefix}{key}", full_name, value, type(value).__name__))
            return params

        params = extract_params(config)

        # 为每个参数创建输入控件
        for param_path, display_name, value, param_type in params:
            # 创建标签（使用中文名称）
            label = QLabel(display_name)
            label.setStyleSheet("QLabel { color: #d4d4d4; font-size: 12px; }")

            # 根据类型创建输入控件
            if param_type == 'int':
                widget = QSpinBox()
                widget.setRange(-999999, 999999)
                widget.setValue(value)
                widget.setStyleSheet("""
                    QSpinBox {
                        background-color: #3d3d3d;
                        color: #d4d4d4;
                        border: 1px solid #555;
                        border-radius: 4px;
                        padding: 5px;
                    }
                """)
            elif param_type == 'float':
                widget = QDoubleSpinBox()
                widget.setRange(-999999.0, 999999.0)
                widget.setDecimals(6)
                widget.setValue(value)
                widget.setStyleSheet("""
                    QDoubleSpinBox {
                        background-color: #3d3d3d;
                        color: #d4d4d4;
                        border: 1px solid #555;
                        border-radius: 4px;
                        padding: 5px;
                    }
                """)
            elif param_type == 'bool':
                widget = QCheckBox()
                widget.setChecked(value)
                widget.setStyleSheet("QCheckBox { color: #d4d4d4; }")
            else:  # str
                widget = QLineEdit()
                widget.setText(str(value))
                widget.setStyleSheet("""
                    QLineEdit {
                        background-color: #3d3d3d;
                        color: #d4d4d4;
                        border: 1px solid #555;
                        border-radius: 4px;
                        padding: 5px;
                    }
                """)

            form_layout.addRow(label, widget)
            input_widgets[param_path] = (widget, param_type)

        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)

        # 按钮
        btn_layout = QHBoxLayout()

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedHeight(36)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #555;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 24px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("确定")
        ok_btn.setFixedHeight(36)
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #6bcf7f;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 24px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5abf6f;
            }
        """)

        def save_changes():
            """保存修改"""
            # 更新配置
            def set_nested_value(cfg, path, value):
                """设置嵌套字典的值"""
                keys = path.split('.')
                current = cfg
                for key in keys[:-1]:
                    if key not in current:
                        current[key] = {}
                    current = current[key]
                current[keys[-1]] = value

            for param_path, (widget, param_type) in input_widgets.items():
                if param_type == 'int':
                    value = widget.value()
                elif param_type == 'float':
                    value = widget.value()
                elif param_type == 'bool':
                    value = widget.isChecked()
                else:  # str
                    value = widget.text()

                set_nested_value(config, param_path, value)

            # 更新表格显示
            self.update_backtest_config_table()

            self.log(f"✅ 回测配置已更新: {config_entry['name']}", "success")
            QMessageBox.information(self, "成功", "回测配置参数已更新！")
            dialog.accept()

        ok_btn.clicked.connect(save_changes)
        btn_layout.addWidget(ok_btn)

        main_layout.addLayout(btn_layout)

        dialog.exec_()

    def remove_backtest_config(self):
        """移除回测配置"""
        current_row = self.backtest_config_table.currentRow()
        if current_row < 0:
            self.show_message("提示", "请先选择要移除的配置", "warning")
            return

        config = self.backtest_configs[current_row]
        reply = self.show_message(
            "确认",
            f"确定要移除配置 {config['name']} 吗？",
            "question"
        )

        if reply == QMessageBox.Yes:
            self.backtest_configs.pop(current_row)
            self.update_backtest_config_table()
            self.log(f"已移除配置: {config['name']}", "info")

    def encrypt_backtest_config(self):
        """加密回测配置"""
        # 获取当前回测标签页的配置
        symbol = self.backtest_symbol.text().strip()
        market = self.backtest_market.currentText()
        interval = self.backtest_interval.currentText()

        if not symbol:
            QMessageBox.warning(self, "提示", "请先在回测标签页中配置参数")
            return

        # 转换市场类型
        market_map = {"现货": "spot", "合约": "futures"}
        market_en = market_map.get(market, market)

        config = {
            'exchange': self.current_exchange,
            'symbol': symbol,
            'market': market_en,
            'interval': interval
        }

        # 输入密码
        password, ok = QInputDialog.getText(
            self,
            "设置密码",
            "请输入加密密码（至少6位）:",
            QLineEdit.Password
        )

        if not ok or not password:
            return

        if len(password) < 6:
            QMessageBox.warning(self, "错误", "密码长度至少为6位！")
            return

        # 确认密码
        password_confirm, ok = QInputDialog.getText(
            self,
            "确认密码",
            "请再次输入密码:",
            QLineEdit.Password
        )

        if not ok or password != password_confirm:
            QMessageBox.warning(self, "错误", "两次输入的密码不一致！")
            return

        # 选择输出路径
        default_output = f"{symbol}_{interval}_backtest.qtb"
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存加密配置",
            default_output,
            "回测配置 (*.qtb);;All Files (*)"
        )

        if not output_path:
            return

        try:
            from tools.strategy_crypto import StrategyEncryptor
            encryptor = StrategyEncryptor(password)
            output_file = encryptor.encrypt_backtest_config(config, output_path)

            self.log(f"✅ 回测配置加密成功: {output_file}", "success")
            QMessageBox.information(
                self,
                "成功",
                f"回测配置已加密！\n\n输出文件: {output_file}\n\n⚠️ 请妥善保管密码，丢失后无法恢复！"
            )

        except Exception as e:
            self.log(f"❌ 回测配置加密失败: {e}", "error")
            QMessageBox.critical(self, "错误", f"回测配置加密失败:\n{str(e)}")

    def refresh_monitor_data(self):
        """刷新监控数据"""
        self.log("刷新监控数据")
        # TODO: 刷新持仓和账户信息

    def start_scanner(self):
        """开始扫描"""
        scan_range = self.scanner_range.currentText()
        min_change = self.scanner_min_change.value()

        self.log(f"开始扫描机会: {scan_range}, 最小涨幅: {min_change}%")
        # TODO: 调用实际的扫描功能

    def stop_scanner(self):
        """停止扫描"""
        self.log("停止扫描", "warning")

    def save_notification_config(self):
        """保存通知配置"""
        config = {
            "enabled_methods": [],
            "feishu": {
                "enabled": self.notify_feishu.isChecked(),
                "webhook_url": self.feishu_webhook.text()
            }
        }

        if self.notify_console.isChecked():
            config["enabled_methods"].append("console")
        if self.notify_feishu.isChecked():
            config["enabled_methods"].append("feishu")
        if self.notify_email.isChecked():
            config["enabled_methods"].append("email")
        if self.notify_telegram.isChecked():
            config["enabled_methods"].append("telegram")

        try:
            with open('config/notification_config.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            self.log("通知配置已保存", "success")
        except Exception as e:
            self.log(f"保存失败: {str(e)}", "error")

    def test_notification(self):
        """测试通知"""
        self.log("发送测试通知...")
        # TODO: 调用实际的通知测试
        self.log("测试通知已发送", "success")

    def export_config(self):
        """导出配置"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出配置",
            "config_backup.json",
            "JSON Files (*.json)"
        )

        if file_path:
            self.log(f"导出配置到: {file_path}", "success")

    def show_settings(self):
        """显示系统设置"""
        self.log("打开系统设置")
        # TODO: 打开设置窗口

    def show_documentation(self):
        """显示使用文档"""
        self.log("打开使用文档")
        # TODO: 打开文档

    def show_about(self):
        """显示关于"""
        QMessageBox.about(
            self,
            "关于",
            "量化交易系统 v1.0\n\n"
            "支持币圈、股票、外汇等多市场交易\n"
            "集成回测、模拟交易、实盘交易等功能\n\n"
            "© 2024 量化交易系统"
        )


def main():
    """主函数"""
    app = QApplication(sys.argv)

    # 设置应用样式
    app.setStyle('Fusion')

    # 创建主窗口
    window = TradingGUI()
    window.show()

    # 启动日志
    window.log("系统启动成功", "success")
    window.log(f"当前市场: {window.market_combo.currentText()}")
    window.log(f"当前交易所: {window.exchange_combo.currentText()}")

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

