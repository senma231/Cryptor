#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
依赖检查和自动安装脚本
在运行GUI前自动检查并安装缺失的依赖
"""

import sys
import subprocess
import importlib.util

# GUI运行所需的核心依赖
REQUIRED_PACKAGES = {
    'PyQt5': 'PyQt5==5.15.10',
    'pandas': 'pandas==2.1.4',
    'numpy': 'numpy==1.26.2',
    'requests': 'requests==2.31.0',
    'loguru': 'loguru==0.7.2',
}

def check_package(package_name):
    """检查包是否已安装"""
    spec = importlib.util.find_spec(package_name)
    return spec is not None

def install_package(package_spec):
    """安装包"""
    print(f"正在安装 {package_spec}...")
    try:
        subprocess.check_call([
            sys.executable, '-m', 'pip', 'install', 
            package_spec, '-q', '--upgrade'
        ])
        return True
    except subprocess.CalledProcessError:
        return False

def main():
    """主函数"""
    print("=" * 60)
    print("GUI依赖检查工具")
    print("=" * 60)
    print()
    
    missing_packages = []
    
    # 检查所有依赖
    print("正在检查依赖...")
    for package_name, package_spec in REQUIRED_PACKAGES.items():
        if check_package(package_name):
            print(f"✅ {package_name:15s} - 已安装")
        else:
            print(f"❌ {package_name:15s} - 未安装")
            missing_packages.append(package_spec)
    
    print()
    
    # 如果有缺失的包
    if missing_packages:
        print(f"发现 {len(missing_packages)} 个缺失的依赖包")
        print()
        
        # 询问是否自动安装
        response = input("是否自动安装缺失的依赖？(y/n): ").strip().lower()
        
        if response == 'y' or response == 'yes':
            print()
            print("=" * 60)
            print("开始安装依赖...")
            print("=" * 60)
            print()
            
            success_count = 0
            fail_count = 0
            
            for package_spec in missing_packages:
                if install_package(package_spec):
                    success_count += 1
                    print(f"✅ {package_spec} 安装成功")
                else:
                    fail_count += 1
                    print(f"❌ {package_spec} 安装失败")
            
            print()
            print("=" * 60)
            print(f"安装完成: 成功 {success_count} 个, 失败 {fail_count} 个")
            print("=" * 60)
            print()
            
            if fail_count > 0:
                print("⚠️  部分依赖安装失败，请手动安装：")
                print()
                print("pip install -r requirements.txt")
                print()
                return False
            else:
                print("✅ 所有依赖安装成功！")
                print()
                return True
        else:
            print()
            print("请手动安装依赖：")
            print()
            print("pip install -r requirements.txt")
            print()
            return False
    else:
        print("✅ 所有依赖都已安装！")
        print()
        return True

if __name__ == "__main__":
    success = main()
    
    if success:
        print("现在可以运行GUI了：")
        print()
        print("  python trading_gui.py")
        print()
        sys.exit(0)
    else:
        print("请先安装依赖后再运行GUI")
        sys.exit(1)

