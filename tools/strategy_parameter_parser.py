#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略参数解析器
用于从策略文件中提取和修改参数
"""

import ast
import re
from typing import Dict, List, Any, Tuple


class StrategyParameterParser:
    """策略参数解析器"""
    
    @staticmethod
    def parse_parameters(file_path: str) -> List[Dict[str, Any]]:
        """
        解析策略文件中的参数
        
        Args:
            file_path: 策略文件路径
            
        Returns:
            参数列表，每个参数包含：name, type, default_value, description
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []
        
        parameters = []
        
        # 遍历所有类定义
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # 查找__init__方法
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                        # 解析参数
                        params = StrategyParameterParser._parse_init_params(item, content)
                        parameters.extend(params)
        
        return parameters
    
    @staticmethod
    def _parse_init_params(func_node: ast.FunctionDef, content: str) -> List[Dict[str, Any]]:
        """解析__init__方法的参数"""
        parameters = []

        # 获取函数的文档字符串
        docstring = ast.get_docstring(func_node) or ""

        # 解析参数描述
        param_descriptions = StrategyParameterParser._parse_docstring(docstring)

        # 1. 解析函数参数（跳过self）
        for arg in func_node.args.args[1:]:
            param_name = arg.arg

            # 查找默认值
            default_value = None
            param_type = "int"  # 默认类型

            # 从defaults中获取默认值
            defaults = func_node.args.defaults
            args_count = len(func_node.args.args) - 1  # 减去self
            defaults_start = args_count - len(defaults)

            arg_index = func_node.args.args.index(arg) - 1  # 减去self
            if arg_index >= defaults_start:
                default_node = defaults[arg_index - defaults_start]
                default_value = StrategyParameterParser._get_node_value(default_node)

                # 根据默认值推断类型
                if isinstance(default_value, int):
                    param_type = "int"
                elif isinstance(default_value, float):
                    param_type = "float"
                elif isinstance(default_value, bool):
                    param_type = "bool"
                elif isinstance(default_value, str):
                    param_type = "str"
            
            # 获取参数描述
            description = param_descriptions.get(param_name, "")

            parameters.append({
                'name': param_name,
                'type': param_type,
                'default_value': default_value,
                'description': description
            })

        # 2. 解析__init__方法体内的self.xxx = value赋值语句
        for stmt in func_node.body:
            if isinstance(stmt, ast.Assign):
                # 检查是否是self.xxx = value的形式
                for target in stmt.targets:
                    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == 'self':
                        attr_name = target.attr

                        # 跳过以下划线开头的内部变量
                        if attr_name.startswith('_'):
                            continue

                        # 跳过特殊的内部状态变量
                        if attr_name in ['data', 'current_position', 'entry_price', 'peak_price']:
                            continue

                        # 获取赋值的值
                        value = StrategyParameterParser._get_node_value(stmt.value)

                        if value is not None:
                            # 推断类型
                            if isinstance(value, int):
                                param_type = "int"
                            elif isinstance(value, float):
                                param_type = "float"
                            elif isinstance(value, bool):
                                param_type = "bool"
                            elif isinstance(value, str):
                                param_type = "str"
                            else:
                                continue

                            # 尝试从注释中提取描述
                            description = ""
                            if hasattr(stmt, 'lineno'):
                                # 从源代码中查找同行注释
                                lines = content.split('\n')
                                if stmt.lineno <= len(lines):
                                    line = lines[stmt.lineno - 1]
                                    if '#' in line:
                                        description = line.split('#', 1)[1].strip()

                            parameters.append({
                                'name': attr_name,
                                'type': param_type,
                                'default_value': value,
                                'description': description
                            })

        return parameters
    
    @staticmethod
    def _get_node_value(node):
        """获取AST节点的值"""
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Num):  # Python 3.7兼容
            return node.n
        elif isinstance(node, ast.Str):  # Python 3.7兼容
            return node.s
        elif isinstance(node, ast.NameConstant):  # Python 3.7兼容
            return node.value
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            # 处理负数
            return -StrategyParameterParser._get_node_value(node.operand)
        return None
    
    @staticmethod
    def _parse_docstring(docstring: str) -> Dict[str, str]:
        """从文档字符串中解析参数描述"""
        descriptions = {}
        
        # 匹配 "param_name: description" 格式
        pattern = r'(\w+):\s*(.+?)(?=\n\s*\w+:|$)'
        matches = re.findall(pattern, docstring, re.DOTALL)
        
        for param_name, description in matches:
            descriptions[param_name] = description.strip()
        
        return descriptions
    
    @staticmethod
    def update_parameters(file_path: str, new_params: Dict[str, Any]) -> bool:
        """
        更新策略文件中的参数默认值
        
        Args:
            file_path: 策略文件路径
            new_params: 新的参数值字典
            
        Returns:
            是否成功更新
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 使用正则表达式替换__init__方法中的默认值
            for param_name, param_value in new_params.items():
                # 匹配参数定义，例如: fast_period=5
                pattern = rf'(\b{param_name}\s*=\s*)([^,\)]+)'
                
                # 根据类型格式化新值
                if isinstance(param_value, str):
                    new_value = f"'{param_value}'"
                else:
                    new_value = str(param_value)
                
                content = re.sub(pattern, rf'\g<1>{new_value}', content)
            
            # 写回文件
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return True
            
        except Exception as e:
            print(f"更新参数失败: {e}")
            return False

