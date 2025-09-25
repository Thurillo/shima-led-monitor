import logging
from src.notificationsystem import NotificationManager
from notification_system import NotificationManager

def test_slack_notification():
    # Configurazione del file YAML con i webhook delle camere
    config_file = "cameras.yaml"

    # Creazione NotificationManager caricando la configurazione
    manager = NotificationManager(configfile=config_file)

    # Parametri dell'esempio notifica
    title = "Test Notifica Slack"
    message = "Questa è una notifica di prova dal sistema Shima Monitor."
    priority = "high"
    metadata = {"test": "valore"}

    # Invio notifica usando NotificationManager
    success = manager.sendnotifications(title=title, message=message, priority=priority, metadata=metadata)

    if success:
        print("Invio notifica Slack: Successo")
    else:
        print("Invio notifica Slack: Fallito")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_slack_notification()
