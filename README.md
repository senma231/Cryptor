# 量化交易系统

> 基于 Python 和 PyQt5 的加密货币量化交易系统

[![Build](https://github.com/senma231/Cryptor/actions/workflows/build.yml/badge.svg)](https://github.com/senma231/Cryptor/actions/workflows/build.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## 📋 功能特性

### 核心功能

- **📥 数据下载**
  - 支持多个交易所（Binance、OKX、HTX）
  - 支持现货和合约市场
  - 支持多种时间周期（1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w, 1M）
  - 自动保存为 Parquet 格式

- **📊 回测测试**
  - 基于历史数据的策略回测
  - 60+ 技术指标支持
  - 详细的回测报告生成
  - 支持参数微调优化

- **🎮 模拟交易**
  - 实时行情模拟
  - 真实交易环境模拟
  - 实时盈亏统计
  - 支持手动停止

- **📋 策略管理**
  - 策略导入导出
  - 参数可视化调整
  - 策略文件管理

---

## 🚀 快速开始

### 下载可执行文件

访问 [Releases](https://github.com/senma231/Cryptor/releases) 页面下载最新版本：

- **Windows**: `量化交易系统.exe`
- **macOS (Intel)**: `量化交易系统-macOS-Intel.zip`
- **macOS (Apple Silicon)**: `量化交易系统-macOS-ARM.zip`

### 系统要求

- **Windows**: Windows 10 或更高版本（64位）
- **macOS**: macOS 10.14 或更高版本
- **内存**: 建议 4GB 以上
- **硬盘**: 建议 10GB 以上可用空间

### 运行程序

#### Windows
1. 下载 `量化交易系统.exe`
2. 双击运行即可

#### macOS
1. 下载对应版本的 `.zip` 文件并解压
2. 将 `量化交易系统.app` 拖到"应用程序"文件夹
3. 首次运行需要右键点击 → "打开"
4. 如提示"无法验证开发者"，请前往"系统偏好设置" → "安全性与隐私"允许运行

---

## 📦 自动打包说明

本项目使用 GitHub Actions 自动打包多平台可执行文件。

### 支持的平台

- **Windows** (x64)
- **macOS Intel** (x86_64)
- **macOS Apple Silicon** (ARM64)

### 发布新版本

创建版本标签时，会自动打包并创建 GitHub Release：

```bash
git tag v2.0.0
git push origin v2.0.0
```

打包完成后，可执行文件会自动上传到 Releases 页面。

---

## 🛠️ 技术栈

- **GUI 框架**: PyQt5
- **数据处理**: Pandas, NumPy
- **交易所接口**: CCXT
- **数据存储**: Parquet
- **加密**: Cryptography
- **打包工具**: PyInstaller

---

## 🎯 使用说明

### 1. 数据下载

1. 打开程序，切换到"数据下载"标签页
2. 选择交易所（Binance/OKX/HTX）
3. 选择市场类型（现货/合约）
4. 输入交易对（如 BTCUSDT）
5. 选择时间周期
6. 设置日期范围
7. 点击"开始下载"

### 2. 回测测试

1. 切换到"回测测试"标签页
2. 选择策略文件
3. 配置回测参数
4. 点击"开始回测"
5. 查看回测报告

### 3. 模拟交易

1. 切换到"模拟交易"标签页
2. 选择策略文件
3. 配置交易参数
4. 点击"开始模拟"
5. 实时查看交易情况

### 4. 策略管理

1. 切换到"策略列表"标签页
2. 查看已有策略
3. 导入新策略
4. 调整策略参数

---

## 📝 更新日志

### v2.0.0 (2025-11-25)

- ✨ 新增 GitHub Actions 自动打包
- ✨ 支持 Windows 和 macOS 多平台
- ✨ 支持 13 种 K 线周期
- ✨ 优化回测性能
- ✨ 改进 GUI 界面
- 🐛 修复已知问题

---

## 🤝 贡献指南

欢迎贡献代码！请遵循以下步骤：

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

---

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

## 📞 联系方式

- **Issues**: [GitHub Issues](https://github.com/senma231/Cryptor/issues)
- **Discussions**: [GitHub Discussions](https://github.com/senma231/Cryptor/discussions)

---

## ⚠️ 免责声明

本软件仅供学习和研究使用。使用本软件进行实际交易的风险由用户自行承担。

- 加密货币交易具有高风险
- 过去的表现不代表未来的结果
- 请谨慎使用，做好风险管理
- 作者不对任何交易损失负责

---

## 🙏 致谢

感谢以下开源项目：

- [PyQt5](https://www.riverbankcomputing.com/software/pyqt/) - GUI 框架
- [CCXT](https://github.com/ccxt/ccxt) - 加密货币交易库
- [Pandas](https://pandas.pydata.org/) - 数据分析库
- [NumPy](https://numpy.org/) - 科学计算库
- [PyInstaller](https://www.pyinstaller.org/) - 打包工具

---

**⭐ 如果这个项目对你有帮助，请给个 Star！**

