import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))
import yaml
import logging
from notification_system import NotificationManager, SlackProvider

def test_slack_notifications_per_camera():
    # Carica i dati delle camere da cameras.yaml
    with open('cameras.yaml', 'r') as f:
        cameras_config = yaml.safe_load(f)

    manager = NotificationManager()

    # Per ogni camera, aggiungi un provider Slack con il webhook specificato
    for camera in cameras_config.get('cameras', []):
        webhook_url = camera.get('slack_webhook_url')
        if webhook_url:
            slack_provider = SlackProvider(webhook_url)
            manager.add_provider(slack_provider)

    # Invia notifica di test a tutti i webhook aggiunti
    success = manager.send_notification(
        title="Test Notifica Slack per Camera",
        message="Questa è una notifica di prova inviata a tutti i webhook Slack delle camere.",
        priority="high",
        metadata={"test": "valore"}
    )

    if success:
        print("Invio notifiche Slack: Successo")
    else:
        print("Invio notifiche Slack: Fallito")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_slack_notifications_per_camera()
