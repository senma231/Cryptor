# -*- coding: utf-8 -*-
"""
策略配置加密模块
用于加密保护策略参数，防止未授权查看和修改
"""

import json
import base64
import hashlib
from pathlib import Path
from typing import Dict, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class StrategyConfigCrypto:
    """策略配置加密器"""

    def __init__(self, password: str = None):
        """
        初始化加密器

        Args:
            password: 加密密码，不提供则使用默认密钥
        """
        if password is None:
            # 默认密钥（基于机器特征）
            password = self._get_machine_key()

        self.cipher = self._create_cipher(password)

    def _get_machine_key(self) -> str:
        """生成基于机器的默认密钥"""
        import platform
        import uuid

        # 组合多个机器特征
        machine_info = f"{platform.node()}-{uuid.getnode()}-VNPY_STRATEGY_2025"
        return hashlib.sha256(machine_info.encode()).hexdigest()[:32]

    def _create_cipher(self, password: str) -> Fernet:
        """创建加密器"""
        # 使用PBKDF2派生密钥
        salt = b'vnpy_strategy_salt_2025'
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return Fernet(key)

    def encrypt_config(self, config: Dict[str, Any]) -> bytes:
        """加密配置"""
        json_data = json.dumps(config, ensure_ascii=False)
        return self.cipher.encrypt(json_data.encode('utf-8'))

    def decrypt_config(self, encrypted_data: bytes) -> Dict[str, Any]:
        """解密配置"""
        decrypted = self.cipher.decrypt(encrypted_data)
        return json.loads(decrypted.decode('utf-8'))

    def save_encrypted_config(self, config: Dict[str, Any], filepath: str):
        """保存加密配置到文件"""
        encrypted = self.encrypt_config(config)

        # 添加文件头标识
        header = b'VNPY_ENCRYPTED_CONFIG_V1\n'

        with open(filepath, 'wb') as f:
            f.write(header + encrypted)

    def load_encrypted_config(self, filepath: str) -> Dict[str, Any]:
        """从文件加载加密配置"""
        with open(filepath, 'rb') as f:
            content = f.read()

        # 验证文件头
        header = b'VNPY_ENCRYPTED_CONFIG_V1\n'
        if not content.startswith(header):
            raise ValueError("无效的加密配置文件")

        encrypted_data = content[len(header):]
        return self.decrypt_config(encrypted_data)


# 默认策略参数（与原始策略一致）
DEFAULT_STRATEGY_PARAMS = {
    # === 信号计算参数 ===
    "signal_params": {
        "M1": 5,      # 短期MA周期
        "M2": 10,     # 中期MA周期
        "M3": 20,     # 中长期MA周期
        "M4": 60,     # 长期MA周期
        "M99": 20,    # ACD平滑周期
        "N": 12,      # 信号平滑周期
        "SHORT": 12,  # MACD短期
        "LONG": 26,   # MACD长期
        "MID": 9,     # MACD信号线
    },

    # === 交易条件参数 ===
    "trading_conditions": {
        # 买入条件
        "buy": {
            "HA_threshold": 25000,      # HA > 此值时考虑买入
            "WD3_max": 150,             # WD3 < 此值时允许买入
            "QS_threshold": 1250,       # |QS| > 此值时确认强势
        },
        # 卖出条件
        "sell": {
            "QJ_threshold": 50000,      # |QJ| > 此值时卖出
            "WD3_threshold": 200,       # WD3 > 此值时卖出（过热）
        }
    },

    # === 资金管理参数 ===
    "money_management": {
        "initial_capital": 100000.0,    # 初始资金
        "stkmoney": 10000.0,            # 单次交易金额
        "stoploss": 0.02,               # 移动止损比率
        "lossrate": 0.08,               # 固定止损比率
        "position_ratio": 1.0,          # 仓位比例
    },

    # === 回测参数 ===
    "backtest": {
        "start_index": 50,              # 从第N条数据开始（确保指标稳定）
        "commission": 0.001,            # 手续费率
        "slippage": 0.0005,             # 滑点
    }
}


def get_config_path() -> Path:
    """获取加密配置文件路径"""
    return Path(__file__).parent.parent / 'config' / 'strategy_params.enc'


def init_encrypted_config(password: str = None):
    """初始化加密配置文件"""
    crypto = StrategyConfigCrypto(password)
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    crypto.save_encrypted_config(DEFAULT_STRATEGY_PARAMS, str(config_path))
    print(f"✓ 加密配置文件已创建: {config_path}")
    return config_path


def load_strategy_params(password: str = None) -> Dict[str, Any]:
    """加载策略参数"""
    crypto = StrategyConfigCrypto(password)
    config_path = get_config_path()

    if not config_path.exists():
        # 首次使用，创建默认配置
        init_encrypted_config(password)

    return crypto.load_encrypted_config(str(config_path))


def save_strategy_params(params: Dict[str, Any], password: str = None):
    """保存策略参数"""
    crypto = StrategyConfigCrypto(password)
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    crypto.save_encrypted_config(params, str(config_path))


if __name__ == '__main__':
    # 测试加密功能
    print("测试策略配置加密...")

    # 初始化
    init_encrypted_config()

    # 加载
    params = load_strategy_params()
    print(f"\n加载的参数:")
    print(json.dumps(params, indent=2, ensure_ascii=False))

    # 修改并保存
    params['signal_params']['M1'] = 6
    save_strategy_params(params)

    # 重新加载验证
    params2 = load_strategy_params()
    print(f"\n修改后的M1: {params2['signal_params']['M1']}")

    print("\n✓ 加密功能测试通过")
