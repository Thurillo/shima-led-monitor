import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

import logging
from notification_system import NotificationManager

def test_slack_notification():
    # File di configurazione camere con webhook Slack
    config_file = "cameras.yaml"

    # Creazione istanza NotificationManager con caricamento configurazione
    manager = NotificationManager(configfile=config_file)

    # Parametri notifica di prova
    title = "Test Notifica Slack"
    message = "Questa è una notifica di prova dal sistema Shima Monitor."
    priority = "high"
    metadata = {"test": "valore"}

    # Invio notifica
    success = manager.sendnotifications(title=title, message=message, priority=priority, metadata=metadata)

    # Risultato test
    if success:
        print("Invio notifica Slack: Successo")
    else:
        print("Invio notifica Slack: Fallito")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_slack_notification()
