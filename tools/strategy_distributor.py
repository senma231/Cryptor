# -*- coding: utf-8 -*-
"""
策略分发工具
用于打包分发策略时的密钥管理
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import shutil
from datetime import datetime
from tools.crypto_config import (
    StrategyConfigCrypto,
    load_strategy_params,
    save_strategy_params,
    get_config_path,
    DEFAULT_STRATEGY_PARAMS
)


def set_distribution_password(new_password: str):
    """
    设置分发密码

    将当前配置用新密码重新加密，便于分发给他人

    Args:
        new_password: 新的分发密码
    """
    # 加载当前配置（使用机器密钥）
    try:
        current_params = load_strategy_params()
        print("✓ 已加载当前配置")
    except Exception:
        print("! 当前无配置，使用默认参数")
        current_params = DEFAULT_STRATEGY_PARAMS.copy()

    # 用新密码保存
    new_crypto = StrategyConfigCrypto(new_password)
    config_path = get_config_path()
    new_crypto.save_encrypted_config(current_params, str(config_path))

    print(f"✓ 配置已用新密码加密")
    print(f"  文件: {config_path}")
    print(f"\n⚠️  重要：请记住此密码，接收者需要使用相同密码解密")


def import_with_password(password: str):
    """
    使用密码导入配置

    接收者使用此功能导入分发的加密配置

    Args:
        password: 分发时设置的密码
    """
    config_path = get_config_path()

    if not config_path.exists():
        print(f"✗ 配置文件不存在: {config_path}")
        return False

    try:
        # 用提供的密码解密
        crypto = StrategyConfigCrypto(password)
        params = crypto.load_encrypted_config(str(config_path))

        # 用本机密钥重新加密（便于后续使用）
        save_strategy_params(params)

        print("✓ 配置导入成功！")
        print("  已转换为本机密钥，后续使用无需再输入密码")
        return True

    except Exception as e:
        print(f"✗ 导入失败: {e}")
        print("  请检查密码是否正确")
        return False


def export_package(output_dir: str, password: str):
    """
    导出完整的策略包

    Args:
        output_dir: 输出目录
        password: 分发密码
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 需要打包的文件
    files_to_copy = [
        'tools/crypto_config.py',
        'tools/strategy_tuner.py',
        'tools/strategy_distributor.py',
        'tools/batch_downloader.py',
        'strategies/indicators.py',
        'strategies/crypto_signals.py',
        'strategies/crypto_data_loader.py',
        'strategies/crypto_strategy.py',
        'strategies/base_strategy.py',
        'test_strategy.py',
        'requirements.txt',
        '用户使用手册.md',
    ]

    print(f"正在导出策略包到: {output_path}")

    # 复制文件
    for file_path in files_to_copy:
        src = project_root / file_path
        if src.exists():
            dst = output_path / file_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            print(f"  ✓ {file_path}")
        else:
            print(f"  ! 跳过（不存在）: {file_path}")

    # 创建加密配置
    try:
        params = load_strategy_params()
    except Exception:
        params = DEFAULT_STRATEGY_PARAMS.copy()

    crypto = StrategyConfigCrypto(password)
    config_dst = output_path / 'config' / 'strategy_params.enc'
    config_dst.parent.mkdir(parents=True, exist_ok=True)
    crypto.save_encrypted_config(params, str(config_dst))
    print(f"  ✓ config/strategy_params.enc (已加密)")

    # 创建导入说明
    readme_content = f"""# 策略包导入说明

## 首次使用

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 导入加密配置（使用分发者提供的密码）：
```bash
python tools/strategy_distributor.py --import --password "您的密码"
```

3. 验证配置：
```bash
python tools/strategy_tuner.py --show
```

## 日常使用

- 下载数据: `python tools/batch_downloader.py --market spot --interval 1h --start 2024-01-01 --top-n 10`
- 运行回测: `python test_strategy.py`
- 调整参数: `python tools/strategy_tuner.py`

## 注意事项

- 首次导入后，配置会转换为您本机的密钥
- 后续使用无需再输入密码
- 请妥善保管分发密码

---
生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

    readme_path = output_path / 'README_IMPORT.md'
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(readme_content)
    print(f"  ✓ README_IMPORT.md")

    print(f"\n✓ 策略包导出完成!")
    print(f"  位置: {output_path}")
    print(f"  密码: {password}")
    print(f"\n请将整个目录打包发送给接收者，并告知密码")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='策略分发工具')
    parser.add_argument('--set-password', type=str,
                        help='设置分发密码（重新加密当前配置）')
    parser.add_argument('--import', dest='import_config', action='store_true',
                        help='导入配置（接收者使用）')
    parser.add_argument('--password', type=str,
                        help='密码（用于导入或导出）')
    parser.add_argument('--export', type=str,
                        help='导出策略包到指定目录')

    args = parser.parse_args()

    if args.set_password:
        set_distribution_password(args.set_password)

    elif args.import_config:
        if not args.password:
            args.password = input("请输入分发密码: ")
        import_with_password(args.password)

    elif args.export:
        if not args.password:
            args.password = input("请设置分发密码: ")
        export_package(args.export, args.password)

    else:
        # 交互式菜单
        print("\n策略分发工具")
        print("=" * 40)
        print("1. 设置分发密码（打包前使用）")
        print("2. 导入配置（接收者使用）")
        print("3. 导出完整策略包")
        print("0. 退出")
        print("-" * 40)

        choice = input("请选择: ").strip()

        if choice == '1':
            password = input("请输入新的分发密码: ")
            if password:
                set_distribution_password(password)
            else:
                print("密码不能为空")

        elif choice == '2':
            password = input("请输入分发密码: ")
            import_with_password(password)

        elif choice == '3':
            output_dir = input("输出目录 [默认: dist/strategy_package]: ").strip()
            if not output_dir:
                output_dir = 'dist/strategy_package'
            password = input("设置分发密码: ")
            if password:
                export_package(output_dir, password)
            else:
                print("密码不能为空")


if __name__ == '__main__':
    main()
