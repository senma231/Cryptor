"""
API密钥加密工具
使用AES-256加密算法保护敏感信息
"""

import os
import json
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
from cryptography.hazmat.backends import default_backend
import base64


class CryptoManager:
    """加密管理器 - 用于保护API密钥等敏感数据"""

    def __init__(self, master_key: str = None):
        """
        初始化加密管理器

        Args:
            master_key: 主密钥,用于生成加密密钥
        """
        if master_key is None:
            master_key = os.getenv('ENCRYPTION_KEY')
            if not master_key:
                raise ValueError("未找到加密密钥!请在.env中设置ENCRYPTION_KEY")

        self.cipher = Fernet(self._derive_key(master_key))

    def _derive_key(self, password: str) -> bytes:
        """从密码派生加密密钥"""
        # 使用PBKDF2算法派生密钥
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'vnpy_crypto_salt_2024',  # 固定盐值(生产环境应使用随机盐)
            iterations=100000,
            backend=default_backend()
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key

    def encrypt(self, data: str) -> str:
        """
        加密字符串

        Args:
            data: 待加密的明文

        Returns:
            加密后的密文(Base64编码)
        """
        encrypted = self.cipher.encrypt(data.encode())
        return encrypted.decode()

    def decrypt(self, encrypted_data: str) -> str:
        """
        解密字符串

        Args:
            encrypted_data: 加密的密文

        Returns:
            解密后的明文
        """
        decrypted = self.cipher.decrypt(encrypted_data.encode())
        return decrypted.decode()

    def encrypt_dict(self, data: dict) -> str:
        """
        加密字典对象

        Args:
            data: 待加密的字典

        Returns:
            加密后的JSON字符串
        """
        json_str = json.dumps(data)
        return self.encrypt(json_str)

    def decrypt_dict(self, encrypted_data: str) -> dict:
        """
        解密为字典对象

        Args:
            encrypted_data: 加密的数据

        Returns:
            解密后的字典
        """
        decrypted_json = self.decrypt(encrypted_data)
        return json.loads(decrypted_json)

    def save_encrypted_api_keys(self, api_keys: dict, filepath: str = 'config/api_keys.enc'):
        """
        保存加密的API密钥到文件

        Args:
            api_keys: API密钥字典,格式:
                {
                    "binance": {
                        "api_key": "xxx",
                        "api_secret": "xxx"
                    },
                    "okx": {
                        "api_key": "xxx",
                        "api_secret": "xxx",
                        "passphrase": "xxx"
                    }
                }
            filepath: 保存路径
        """
        encrypted = self.encrypt_dict(api_keys)
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, 'w') as f:
            f.write(encrypted)

        # 设置文件权限为只读
        os.chmod(filepath, 0o600)
        print(f"✓ API密钥已加密保存至: {filepath}")

    def load_encrypted_api_keys(self, filepath: str = 'config/api_keys.enc') -> dict:
        """
        从文件加载并解密API密钥

        Args:
            filepath: 加密文件路径

        Returns:
            解密后的API密钥字典
        """
        if not Path(filepath).exists():
            raise FileNotFoundError(f"未找到加密的API密钥文件: {filepath}")

        with open(filepath, 'r') as f:
            encrypted = f.read()

        return self.decrypt_dict(encrypted)


def generate_encryption_key() -> str:
    """生成随机加密密钥"""
    import secrets
    return secrets.token_hex(32)


def setup_api_keys_from_env():
    """从环境变量读取并加密保存API密钥"""
    from dotenv import load_dotenv
    load_dotenv()

    api_keys = {
        "binance": {
            "api_key": os.getenv('BINANCE_API_KEY', ''),
            "api_secret": os.getenv('BINANCE_API_SECRET', '')
        },
        "okx": {
            "api_key": os.getenv('OKX_API_KEY', ''),
            "api_secret": os.getenv('OKX_API_SECRET', ''),
            "passphrase": os.getenv('OKX_PASSPHRASE', '')
        }
    }

    # 检查是否有有效的API密钥
    has_keys = any(
        v.get('api_key') and v.get('api_secret')
        for v in api_keys.values()
    )

    if not has_keys:
        print("⚠️  警告: 未在.env中找到有效的API密钥")
        print("请编辑.env文件并填入真实的API密钥")
        return False

    crypto = CryptoManager()
    crypto.save_encrypted_api_keys(api_keys)
    return True


if __name__ == '__main__':
    print("=== VNPY API密钥加密工具 ===\n")

    # 生成新的加密密钥
    print("1. 生成加密密钥:")
    print(f"   ENCRYPTION_KEY={generate_encryption_key()}")
    print("   (请将此密钥添加到.env文件中)\n")

    # 从环境变量设置API密钥
    print("2. 加密API密钥:")
    if setup_api_keys_from_env():
        print("✓ API密钥加密成功!\n")
    else:
        print("✗ 请先配置.env文件中的API密钥\n")
