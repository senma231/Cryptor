#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略文件加密/解密工具
支持策略文件(.qts)和回测配置文件(.qtb)的加密存储
"""

import json
import hashlib
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import base64


class StrategyEncryptor:
    """策略文件加密器"""
    
    # 文件类型
    STRATEGY_EXT = '.qts'  # Quant Trading Strategy
    BACKTEST_EXT = '.qtb'  # Quant Trading Backtest
    
    def __init__(self, password: str):
        """
        初始化加密器
        
        Args:
            password: 加密密码
        """
        self.password = password
        self.salt = b'quant_trading_system_2025'  # 固定盐值
        
    def _derive_key(self) -> bytes:
        """从密码派生加密密钥"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=100000,
            backend=default_backend()
        )
        key = base64.urlsafe_b64encode(kdf.derive(self.password.encode()))
        return key
    
    def encrypt_strategy(self, strategy_file: str, output_file: str = None) -> str:
        """
        加密策略文件
        
        Args:
            strategy_file: 原始策略文件路径（.py）
            output_file: 输出加密文件路径（.qts），如果为None则自动生成
            
        Returns:
            加密文件路径
        """
        strategy_path = Path(strategy_file)
        if not strategy_path.exists():
            raise FileNotFoundError(f"策略文件不存在: {strategy_file}")
        
        # 读取策略文件内容
        with open(strategy_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 创建元数据
        metadata = {
            'type': 'strategy',
            'name': strategy_path.stem,
            'original_file': strategy_path.name,
            'content': content
        }
        
        # 加密
        encrypted_data = self._encrypt_data(json.dumps(metadata, ensure_ascii=False))
        
        # 确定输出文件路径
        if output_file is None:
            output_file = strategy_path.parent / f"{strategy_path.stem}{self.STRATEGY_EXT}"
        
        # 写入加密文件
        with open(output_file, 'wb') as f:
            f.write(encrypted_data)
        
        return str(output_file)
    
    def encrypt_backtest_config(self, config: dict, output_file: str) -> str:
        """
        加密回测配置
        
        Args:
            config: 回测配置字典
            output_file: 输出文件路径
            
        Returns:
            加密文件路径
        """
        metadata = {
            'type': 'backtest',
            'config': config
        }
        
        encrypted_data = self._encrypt_data(json.dumps(metadata, ensure_ascii=False))
        
        with open(output_file, 'wb') as f:
            f.write(encrypted_data)
        
        return str(output_file)
    
    def decrypt_file(self, encrypted_file: str) -> dict:
        """
        解密文件
        
        Args:
            encrypted_file: 加密文件路径
            
        Returns:
            解密后的数据字典
        """
        with open(encrypted_file, 'rb') as f:
            encrypted_data = f.read()
        
        decrypted_json = self._decrypt_data(encrypted_data)
        return json.loads(decrypted_json)
    
    def _encrypt_data(self, data: str) -> bytes:
        """加密数据"""
        key = self._derive_key()
        f = Fernet(key)
        return f.encrypt(data.encode())
    
    def _decrypt_data(self, encrypted_data: bytes) -> str:
        """解密数据"""
        key = self._derive_key()
        f = Fernet(key)
        return f.decrypt(encrypted_data).decode()
    
    @staticmethod
    def verify_password(encrypted_file: str, password: str) -> bool:
        """
        验证密码是否正确
        
        Args:
            encrypted_file: 加密文件路径
            password: 待验证的密码
            
        Returns:
            密码是否正确
        """
        try:
            encryptor = StrategyEncryptor(password)
            encryptor.decrypt_file(encrypted_file)
            return True
        except Exception:
            return False

