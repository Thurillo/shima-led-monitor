import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

import yaml
import logging
from notification_system import NotificationManager, SlackProvider

def test_slack_notifications_per_camera():
    with open('cameras.yaml', 'r') as f:
        cameras_config = yaml.safe_load(f)

    manager = NotificationManager()

    for camera in cameras_config.get('cameras', []):
        webhook_url = camera.get('slack_webhook_url')
        print(f"Testing webhook URL: '{webhook_url}'")  # Debug
        if webhook_url and isinstance(webhook_url, str):
            cleaned_url = webhook_url.strip().strip("[]()")
            print(f"Using cleaned webhook URL: '{cleaned_url}'")  # Debug
            slack_provider = SlackProvider(cleaned_url)
            manager.add_provider(slack_provider)
            success = manager.send_notification(
                title="Test Notifica Slack per Camera",
                message=f"Notifica di prova per camera {camera.get('machine_id')}",
                priority="high",
                metadata={"test": "valore"}
            )
            print(f"Invio notifica per camera {camera.get('machine_id')}: {'Successo' if success else 'Fallito'}")
            manager.providers.clear()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_slack_notifications_per_camera()

