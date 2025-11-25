#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通知推送模块
支持多种通知方式：控制台、邮件、Telegram、企业微信、钉钉、飞书
"""

import json
import requests
from pathlib import Path
from datetime import datetime
from loguru import logger
from typing import Dict, Optional


class Notifier:
    """通知推送器"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化通知器
        
        Args:
            config_path: 配置文件路径
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config' / 'notification_config.json'
        
        self.config = self._load_config(config_path)
        self.enabled_methods = self.config.get('enabled_methods', ['console'])
    
    def _load_config(self, config_path: Path) -> Dict:
        """加载配置文件"""
        try:
            if Path(config_path).exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                logger.warning(f"配置文件不存在: {config_path}，使用默认配置")
                return {'enabled_methods': ['console']}
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return {'enabled_methods': ['console']}
    
    def send(self, title: str, message: str, level: str = 'info'):
        """
        发送通知
        
        Args:
            title: 通知标题
            message: 通知内容
            level: 通知级别 (info/warning/error)
        """
        for method in self.enabled_methods:
            try:
                if method == 'console':
                    self._send_console(title, message, level)
                elif method == 'email':
                    self._send_email(title, message)
                elif method == 'telegram':
                    self._send_telegram(title, message)
                elif method == 'wecom':
                    self._send_wecom(title, message)
                elif method == 'dingtalk':
                    self._send_dingtalk(title, message)
                elif method == 'feishu':
                    self._send_feishu(title, message)
            except Exception as e:
                logger.error(f"发送通知失败 ({method}): {e}")
    
    def _send_console(self, title: str, message: str, level: str):
        """控制台输出"""
        separator = "=" * 80
        print(f"\n{separator}")
        print(f"📢 {title}")
        print(separator)
        print(message)
        print(separator)
    
    def _send_email(self, title: str, message: str):
        """邮件通知"""
        email_config = self.config.get('email', {})
        if not email_config.get('enabled', False):
            return
        
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        smtp_server = email_config.get('smtp_server')
        smtp_port = email_config.get('smtp_port', 587)
        sender = email_config.get('sender')
        password = email_config.get('password')
        receivers = email_config.get('receivers', [])
        
        if not all([smtp_server, sender, password, receivers]):
            logger.warning("邮件配置不完整，跳过邮件通知")
            return
        
        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = ', '.join(receivers)
        msg['Subject'] = title
        
        msg.attach(MIMEText(message, 'plain', 'utf-8'))
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)
        
        logger.info(f"✓ 邮件通知已发送: {title}")
    
    def _send_telegram(self, title: str, message: str):
        """Telegram Bot通知"""
        telegram_config = self.config.get('telegram', {})
        if not telegram_config.get('enabled', False):
            return
        
        bot_token = telegram_config.get('bot_token')
        chat_id = telegram_config.get('chat_id')
        
        if not all([bot_token, chat_id]):
            logger.warning("Telegram配置不完整，跳过Telegram通知")
            return
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        text = f"*{title}*\n\n{message}"
        
        payload = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'Markdown'
        }
        
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        
        logger.info(f"✓ Telegram通知已发送: {title}")
    
    def _send_wecom(self, title: str, message: str):
        """企业微信通知"""
        wecom_config = self.config.get('wecom', {})
        if not wecom_config.get('enabled', False):
            return
        
        webhook_url = wecom_config.get('webhook_url')
        
        if not webhook_url:
            logger.warning("企业微信配置不完整，跳过企业微信通知")
            return
        
        payload = {
            'msgtype': 'text',
            'text': {
                'content': f"{title}\n\n{message}"
            }
        }
        
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        
        logger.info(f"✓ 企业微信通知已发送: {title}")
    
    def _send_dingtalk(self, title: str, message: str):
        """钉钉通知"""
        dingtalk_config = self.config.get('dingtalk', {})
        if not dingtalk_config.get('enabled', False):
            return
        
        webhook_url = dingtalk_config.get('webhook_url')
        
        if not webhook_url:
            logger.warning("钉钉配置不完整，跳过钉钉通知")
            return
        
        payload = {
            'msgtype': 'text',
            'text': {
                'content': f"{title}\n\n{message}"
            }
        }
        
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()

        logger.info(f"✓ 钉钉通知已发送: {title}")

    def _send_feishu(self, title: str, message: str):
        """飞书机器人通知"""
        feishu_config = self.config.get('feishu', {})
        if not feishu_config.get('enabled', False):
            return

        webhook_url = feishu_config.get('webhook_url')

        if not webhook_url:
            logger.warning("飞书配置不完整，跳过飞书通知")
            return

        # 飞书支持富文本消息
        payload = {
            'msg_type': 'text',
            'content': {
                'text': f"{title}\n\n{message}"
            }
        }

        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()

        logger.info(f"✓ 飞书通知已发送: {title}")

