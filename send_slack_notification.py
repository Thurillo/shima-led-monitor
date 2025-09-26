#!/usr/bin/env python3
import requests
import json
import sys

def send_slack_notification(webhook_url, title, message, metadata=None):
    payload = {
        "text": f"*{title}*\n{message}"
    }
    if metadata:
        details = "\n".join(f"- {k}: {v}" for k, v in metadata.items())
        payload["text"] += f"\n\n*Dettagli:*\n{details}"

    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(webhook_url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            print("Notifica inviata con successo")
            return True
        else:
            print(f"Errore invio Slack: status {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"Eccezione nell'invio Slack: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Uso: python3 send_slack_notification.py <webhook_url> <title> <message>")
        sys.exit(1)

    webhook_url = sys.argv[1]
    title = sys.argv[2]
    message = sys.argv[3]
    metadata = {"example_detail": "valore"}

    send_slack_notification(webhook_url, title, message, metadata)
