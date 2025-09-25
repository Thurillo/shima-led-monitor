import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

import logging
from notification_system import NotificationManager

def test_slack_notification():
    # Specificare il file di configurazione (adeguare percorso se serve)
    config_file = "cameras.yaml"

    # Creare istanza NotificationManager caricando configurazione da file
    manager = NotificationManager(config_file=config_file)

    # Parametri notifica di test
    title = "Test Notifica Slack"
    message = "Questa è una notifica di prova dal sistema Shima Monitor."
    priority = "high"
    metadata = {"test": "valore"}

    # Inviare notifica
    success = manager.send_notification(title=title, message=message, priority=priority, metadata=metadata)

    if success:
        print("Invio notifica Slack: Successo")
    else:
        print("Invio notifica Slack: Fallito")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_slack_notification()
