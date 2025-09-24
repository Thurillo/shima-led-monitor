# Let's create a comprehensive project structure for the Shima knitting machine monitoring system
import os
import json

# Define the project structure
project_structure = {
    "shima_monitor/": {
        "config/": {
            "__init__.py": "",
            "settings.py": "# Configuration settings for the monitoring system",
            "camera_config.yaml": "# Camera configuration file",
        },
        "src/": {
            "__init__.py": "",
            "led_detector.py": "# LED status detection module",
            "rtsp_client.py": "# RTSP stream client",
            "frigate_integration.py": "# Integration with Frigate NVR",
            "notification_system.py": "# Alert and notification system",
            "utils.py": "# Utility functions",
        },
        "models/": {
            "__init__.py": "",
            "led_classifier.py": "# LED color/state classification model",
        },
        "tests/": {
            "__init__.py": "",
            "test_led_detector.py": "# Tests for LED detection",
            "test_integration.py": "# Integration tests",
        },
        "docker/": {
            "Dockerfile": "# Docker configuration",
            "docker-compose.yml": "# Docker Compose setup",
        },
        "requirements.txt": "# Python dependencies",
        "README.md": "# Project documentation",
        "main.py": "# Main application entry point",
    }
}

print("PROGETTO SISTEMA DI MONITORAGGIO LED SHIMA SEIKI")
print("=" * 60)
print("Struttura del progetto creata per il monitoraggio delle luci LED")
print("delle macchine per maglieria Shima Seiki tramite AI e flussi RTSP")
print("\nStruttura delle cartelle:")

def print_structure(structure, indent=0):
    for item, content in structure.items():
        print("  " * indent + "├── " + item)
        if isinstance(content, dict):
            print_structure(content, indent + 1)

print_structure(project_structure)