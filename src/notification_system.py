# Notification System for Shima LED Monitoring
# Handles email, webhook, and other notification methods

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
    """Email notification configuration"""
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    username: str = ""
    password: str = ""
    recipients: List[str] = None
    use_tls: bool = True

class WebhookConfig(NotificationConfig):
    """Webhook notification configuration"""
    urls: List[str] = None
    timeout: int = 10
    headers: Dict[str, str] = None

class TelegramConfig(NotificationConfig):
    """Telegram notification configuration"""
    bot_token: str = ""
    chat_ids: List[str] = None

class NotificationProvider(ABC):
    """Abstract base class for notification providers"""
    
    @abstractmethod
    def send(self, title: str, message: str, priority: str = "medium", metadata: Dict = None) -> bool:
        """Send notification"""
        pass

class EmailProvider(NotificationProvider):
    """Email notification provider"""
    
    def __init__(self, config: EmailConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def send(self, title: str, message: str, priority: str = "medium", metadata: Dict = None) -> bool:
        """Send email notification"""
        if not self.config.enabled:
            return True
            
        if self.config.priority_filter and priority not in self.config.priority_filter:
            return True
        
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.config.username
            msg['To'] = ", ".join(self.config.recipients)
            msg['Subject'] = title
            
            # Priority mapping for email headers
            priority_headers = {
                "high": "1",
                "medium": "3", 
                "low": "5"
            }
            msg['X-Priority'] = priority_headers.get(priority, "3")
            
            # Create email body
            body = self._create_email_body(message, priority, metadata)
            msg.attach(MIMEText(body, 'html'))
            
            # Send email
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
        """Create HTML email body"""
        priority_colors = {
            "high": "#FF4444",
            "medium": "#FF8800", 
            "low": "#44AA44"
        }
        
        priority_labels = {
            "high": "CRITICO",
            "medium": "ATTENZIONE",
            "low": "INFORMATIVO"
        }
        
        color = priority_colors.get(priority, "#666666")
        label = priority_labels.get(priority, priority.upper())
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <div style="border-left: 4px solid {color}; padding: 10px; margin: 10px 0;">
                <h2 style="color: {color}; margin-top: 0;">
                    🚨 ALERT {label}
                </h2>
                <p style="font-size: 16px; margin: 10px 0;">
                    {message}
                </p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                <p style="font-size: 12px; color: #666;">
                    <strong>Timestamp:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}<br>
        """
        
        if metadata:
            html += "<strong>Dettagli:</strong><br>"
            for key, value in metadata.items():
                if key != 'timestamp':
                    html += f"&nbsp;&nbsp;• {key}: {value}<br>"
        
        html += """
                </p>
                <p style="font-size: 12px; color: #888; font-style: italic;">
                    Questo messaggio è stato generato automaticamente dal sistema di monitoraggio Shima.
                </p>
            </div>
        </body>
        </html>
        """
        
        return html

class WebhookProvider(NotificationProvider):
    """Webhook notification provider"""
    
    def __init__(self, config: WebhookConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def send(self, title: str, message: str, priority: str = "medium", metadata: Dict = None) -> bool:
        """Send webhook notification"""
        if not self.config.enabled or not self.config.urls:
            return True
            
        if self.config.priority_filter and priority not in self.config.priority_filter:
            return True
        
        # Prepare payload
        payload = {
            "title": title,
            "message": message,
            "priority": priority,
            "timestamp": datetime.now().isoformat(),
            "source": "shima_led_monitor"
        }
        
        if metadata:
            payload["metadata"] = metadata
        
        success_count = 0
        
        # Send to all configured webhooks
        for url in self.config.urls:
            try:
                headers = {'Content-Type': 'application/json'}
                if self.config.headers:
                    headers.update(self.config.headers)
                
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self.config.timeout
                )
                
                if response.status_code == 200:
                    success_count += 1
                    self.logger.debug(f"Webhook notification sent to {url}")
                else:
                    self.logger.warning(f"Webhook notification failed for {url}: {response.status_code}")
                    
            except Exception as e:
                self.logger.error(f"Failed to send webhook notification to {url}: {e}")
        
        success = success_count > 0
        if success:
            self.logger.info(f"Webhook notification sent to {success_count}/{len(self.config.urls)} endpoints")
        
        return success

class TelegramProvider(NotificationProvider):
    """Telegram notification provider"""
    
    def __init__(self, config: TelegramConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.base_url = f"https://api.telegram.org/bot{self.config.bot_token}"
    
    def send(self, title: str, message: str, priority: str = "medium", metadata: Dict = None) -> bool:
        """Send Telegram notification"""
        if not self.config.enabled or not self.config.bot_token or not self.config.chat_ids:
            return True
            
        if self.config.priority_filter and priority not in self.config.priority_filter:
            return True
        
        # Format message for Telegram
        emoji_map = {
            "high": "🔴",
            "medium": "🟡",
            "low": "🟢"
        }
        
        emoji = emoji_map.get(priority, "ℹ️")
        formatted_message = f"{emoji} *{title}*\\n\\n{message}"
        
        if metadata:
            formatted_message += "\\n\\n*Dettagli:*"
            for key, value in metadata.items():
                if key != 'timestamp':
                    formatted_message += f"\\n• {key}: `{value}`"
        
        success_count = 0
        
        # Send to all chat IDs
        for chat_id in self.config.chat_ids:
            try:
                payload = {
                    'chat_id': chat_id,
                    'text': formatted_message,
                    'parse_mode': 'Markdown'
                }
                
                response = requests.post(
                    f"{self.base_url}/sendMessage",
                    json=payload,
                    timeout=10
                )
                
                if response.status_code == 200:
                    success_count += 1
                    self.logger.debug(f"Telegram notification sent to {chat_id}")
                else:
                    self.logger.warning(f"Telegram notification failed for {chat_id}: {response.status_code}")
                    
            except Exception as e:
                self.logger.error(f"Failed to send Telegram notification to {chat_id}: {e}")
        
        success = success_count > 0
        if success:
            self.logger.info(f"Telegram notification sent to {success_count}/{len(self.config.chat_ids)} chats")
        
        return success

class NotificationManager:
    """Main notification manager coordinating all providers"""
    
    def __init__(self, config_file: str = None):
        self.logger = logging.getLogger(__name__)
        self.providers = []
        
        # Load configuration if provided
        if config_file:
            self.load_configuration(config_file)
    
    def add_provider(self, provider: NotificationProvider):
        """Add notification provider"""
        self.providers.append(provider)
        self.logger.info(f"Added notification provider: {type(provider).__name__}")
    
    def load_configuration(self, config_file: str):
        """Load notification configuration from file"""
        try:
            import yaml
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            notifications_config = config.get('notifications', {})
            
            # Setup email provider
            if 'email' in notifications_config:
                email_config = EmailConfig(**notifications_config['email'])
                if email_config.enabled and email_config.recipients:
                    self.add_provider(EmailProvider(email_config))
            
            # Setup webhook provider
            if 'webhook' in notifications_config:
                webhook_config = WebhookConfig(**notifications_config['webhook'])
                if webhook_config.enabled and webhook_config.urls:
                    self.add_provider(WebhookProvider(webhook_config))
            
            # Setup Telegram provider
            if 'telegram' in notifications_config:
                telegram_config = TelegramConfig(**notifications_config['telegram'])
                if telegram_config.enabled and telegram_config.bot_token:
                    self.add_provider(TelegramProvider(telegram_config))
            
        except Exception as e:
            self.logger.error(f"Failed to load notification configuration: {e}")
    
    def send_notification(self, title: str, message: str, priority: str = "medium", metadata: Dict = None) -> bool:
        """Send notification through all configured providers"""
        if not self.providers:
            self.logger.warning("No notification providers configured")
            return False
        
        success_count = 0
        
        for provider in self.providers:
            try:
                if provider.send(title, message, priority, metadata):
                    success_count += 1
            except Exception as e:
                self.logger.error(f"Error in notification provider {type(provider).__name__}: {e}")
        
        success = success_count > 0
        
        if success:
            self.logger.info(f"Notification sent successfully through {success_count}/{len(self.providers)} providers")
        else:
            self.logger.error("Failed to send notification through any provider")
        
        return success

# Example usage and testing
if __name__ == "__main__":
    # Test notification system
    logging.basicConfig(level=logging.INFO)
    
    # Create email provider
    email_config = EmailConfig(
        enabled=True,
        username="test@gmail.com",
        password="app_password",
        recipients=["recipient@example.com"]
    )
    
    # Create webhook provider
    webhook_config = WebhookConfig(
        enabled=True,
        urls=["http://localhost:8080/webhook"]
    )
    
    # Create manager and add providers
    manager = NotificationManager()
    manager.add_provider(EmailProvider(email_config))
    manager.add_provider(WebhookProvider(webhook_config))
    
    # Send test notification
    metadata = {
        'machine_id': 'SHIMA_001',
        'camera_id': 'shima_cam_001',
        'region_name': 'status_led'
    }
    
    manager.send_notification(
        title="Test Notification - Shima Monitor",
        message="LED stato cambiato da verde a rosso alle 14:30:25",
        priority="high",
        metadata=metadata
    )