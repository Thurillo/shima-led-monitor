import smtplib
import requests
import logging
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod

@dataclass
class NotificationConfig:
    """Base notification configuration"""
    enabled: bool = True
    priority_filter: List[str] = None  # None means all priorities

class EmailConfig(NotificationConfig):
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    username: str = ""
    password: str = ""
    recipients: List[str] = None
    use_tls: bool = True

class WebhookConfig(NotificationConfig):
    urls: List[str] = None
    timeout: int = 10
    headers: Dict[str, str] = None

class TelegramConfig(NotificationConfig):
    bot_token: str = ""
    chat_ids: List[str] = None

class NotificationProvider(ABC):
    @abstractmethod
    def send(self, title: str, message: str, priority: str = "medium", metadata: Dict = None) -> bool:
        pass

class EmailProvider(NotificationProvider):
    def __init__(self, config: EmailConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)

    def send(self, title: str, message: str, priority: str = "medium", metadata: Dict = None) -> bool:
        if not self.config.enabled:
            return True

        if self.config.priority_filter and priority not in self.config.priority_filter:
            return True

        try:
            msg = MIMEMultipart()
            msg['From'] = self.config.username
            msg['To'] = ", ".join(self.config.recipients)
            msg['Subject'] = title
            priority_headers = {"high": "1", "medium": "3", "low": "5"}
            msg['X-Priority'] = priority_headers.get(priority, "3")
            body = self._create_email_body(message, priority, metadata)
            msg.attach(MIMEText(body, 'html'))

            server = smtplib.SMTP(self.config.smtp_server, self.config.smtp_port)
            if self.config.use_tls:
                server.starttls()
            server.login(self.config.username, self.config.password)
            text = msg.as_string()
            server.sendmail(self.config.username, self.config.recipients, text)
            server.quit()

            self.logger.info(f"Email notification sent: {title}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to send email notification: {e}")
            return False

    def _create_email_body(self, message: str, priority: str, metadata: Dict = None) -> str:
        priority_colors = {"high": "#FF4444", "medium
