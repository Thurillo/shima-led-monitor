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
        priority_colors = {"high": "#FF4444", "medium": "#FF8800", "low": "#44AA44"}
        priority_labels = {"high": "CRITICO", "medium": "ATTENZIONE", "low": "INFORMATIVO"}
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
    def __init__(self, config: WebhookConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)

    def send(self, title: str, message: str, priority: str = "medium", metadata: Dict = None) -> bool:
        if not self.config.enabled or not self.config.urls:
            return True

        if self.config.priority_filter and priority not in self.config.priority_filter:
            return True

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
        for url in self.config.urls:
            try:
                headers = {'Content-Type': 'application/json'}
                if self.config.headers:
                    headers.update(self.config.headers)
                response = requests.post(url, json=payload, headers=headers, timeout=self.config.timeout)
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
    def __init__(self, config: TelegramConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.base_url = f"https://api.telegram.org/bot{self.config.bot_token}"

    def send(self, title: str, message: str, priority: str = "medium", metadata: Dict = None) -> bool:
        if not self.config.enabled or not self.config.bot_token or not self.config.chat_ids:
            return True

        if self.config.priority_filter and priority not in self.config.priority_filter:
            return True

        emoji_map = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        emoji = emoji_map.get(priority, "ℹ️")
        formatted_message = f"{emoji} *{title}*\n\n{message}"

        if metadata:
            formatted_message += "\n\n*Dettagli:*"
            for key, value in metadata.items():
                if key != 'timestamp':
                    formatted_message += f"\n• {key}: `{value}`"

        success_count = 0
        for chat_id in self.config.chat_ids:
            try:
                payload = {'chat_id': chat_id, 'text': formatted_message, 'parse_mode': 'Markdown'}
                response = requests.post(f"{self.base_url}/sendMessage", json=payload, timeout=10)
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

class SlackProvider(NotificationProvider):
    def __init__(self, webhook_url: str, enabled: bool = True):
        self.webhook_url = webhook_url
        self.enabled = enabled
        self.logger = logging.getLogger(__name__)

    def send(self, title: str, message: str, priority: str = "medium", metadata: dict = None) -> bool:
        if not self.enabled or not self.webhook_url:
            return True

        payload = {
            "text": f"*{title}*\n{message}"
        }
        if metadata:
            details = "\n".join(f"- {k}: {v}" for k, v in metadata.items())
            payload["text"] += f"\n\n*Dettagli:*\n{details}"

        try:
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            if response.status_code == 200:
                self.logger.info("Slack notification inviata con successo")
                return True
            else:
                self.logger.error(f"Errore invio Slack: status {response.status_code} - {response.text}")
                return False
        except Exception as e:
            self.logger.error(f"Eccezione nell'invio Slack: {e}")
            return False

class NotificationManager:
    def __init__(self, config_file: str = None):
        self.logger = logging.getLogger(__name__)
        self.providers = []

        if config_file:
            self.load_configuration(config_file)

    def add_provider(self, provider: NotificationProvider):
        self.providers.append(provider)
        self.logger.info(f"Aggiunto provider notifiche: {type(provider).__name__}")

    def load_configuration(self, config_file: str):
        import yaml
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)

            notifications_config = config.get('notifications', {})

            if 'email' in notifications_config:
                email_config = EmailConfig(**notifications_config['email'])
                if email_config.enabled and email_config.recipients:
                    self.add_provider(EmailProvider(email_config))

            if 'webhook' in notifications_config:
                webhook_config = WebhookConfig(**notifications_config['webhook'])
                if webhook_config.enabled and webhook_config.urls:
                    self.add_provider(WebhookProvider(webhook_config))

            if 'telegram' in notifications_config:
                telegram_config = TelegramConfig(**notifications_config['telegram'])
                if telegram_config.enabled and telegram_config.bot_token:
                    self.add_provider(TelegramProvider(telegram_config))

            if 'slack' in notifications_config:
                slack_conf = notifications_config['slack']
                if slack_conf.get('enabled', False) and slack_conf.get('webhook_url'):
                    self.add_provider(SlackProvider(slack_conf['webhook_url'], enabled=True))

        except Exception as e:
            self.logger.error(f"Impossibile caricare configurazione notifiche: {e}")

    def send_notification(self, title: str, message: str, priority: str = "medium", metadata: Dict = None) -> bool:
        if not self.providers:
            self.logger.warning("Nessun provider di notifiche configurato")
            return False

        success_count = 0
        for provider in self.providers:
            try:
                if provider.send(title, message, priority, metadata):
                    success_count += 1
            except Exception as e:
                self.logger.error(f"Errore provider notifiche {type(provider).__name__}: {e}")

        success = success_count > 0
        if success:
            self.logger.info(f"Notifica inviata con successo tramite {success_count}/{len(self.providers)} provider")
        else:
            self.logger.error("Impossibile inviare notifica tramite qualsiasi provider")

        return success

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    manager = NotificationManager(config_file="config/camera_config.yaml")
    success = manager.send_notification(
        title="Test Notifica Slack",
        message="Questa è una notifica di prova dal sistema Shima Monitor.",
        priority="high",
        metadata={"test": "valore"}
    )
    print("Invio notifica Slack:", "Successo" if success else "Fallito")
