# Configuration Settings for Shima LED Monitor
# Central configuration file for the monitoring system

import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).parent.parent
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"
CONFIG_DIR = BASE_DIR / "config"

# Ensure directories exist
LOGS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

# Main application settings
SETTINGS = {
    # Monitoring configuration
    "monitoring_fps": 2,  # LED detection frequency
    "frame_buffer_size": 2,
    "connection_timeout": 30,
    "max_reconnect_attempts": 5,
    "reconnect_delay": 2,
    
    # LED detection parameters
    "led_detection": {
        "confidence_threshold": 0.3,
        "high_confidence_threshold": 0.7,
        "brightness_threshold": 30,
        "flashing_history_length": 15,
        "flashing_min_changes": 4,
        "gaussian_blur_kernel": 5,
        "morphology_kernel_size": 3,
    },
    
    # HSV color ranges for LED detection
    "color_ranges": {
        "green": {
            "lower": [40, 50, 50],
            "upper": [80, 255, 255]
        },
        "yellow": {
            "lower": [20, 100, 100], 
            "upper": [35, 255, 255]
        },
        "red_1": {
            "lower": [0, 120, 70],
            "upper": [10, 255, 255]
        },
        "red_2": {
            "lower": [170, 120, 70],
            "upper": [180, 255, 255]
        }
    },
    
    # Logging configuration
    "logging": {
        "level": "INFO",
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "file_path": LOGS_DIR / "shima_monitor.log",
        "max_size_mb": 50,
        "backup_count": 5
    },
    
    # Data storage
    "storage": {
        "detection_history": LOGS_DIR / "detection_history.jsonl",
        "screenshots_dir": DATA_DIR / "screenshots",
        "debug_frames_dir": DATA_DIR / "debug_frames",
        "database_path": DATA_DIR / "shima_monitor.db"
    },
    
    # Notification settings
    "notifications": {
        "enabled": True,
        "rate_limit_seconds": 60,  # Minimum time between same-type notifications
        "priority_mapping": {
            "red": "high",
            "flashing_red": "high", 
            "yellow": "medium",
            "flashing_yellow": "medium",
            "off": "medium",
            "green": "low",
            "flashing_green": "low"
        }
    },
    
    # Web interface (optional)
    "web_interface": {
        "enabled": False,
        "host": "0.0.0.0",
        "port": 8080,
        "debug": False
    },
    
    # Development/Debug settings
    "debug": {
        "save_debug_frames": False,
        "show_led_regions": True,
        "verbose_logging": False,
        "test_mode": False,
        "mock_cameras": False
    }
}

# ESP32-CAM default settings
ESP32_CAM_DEFAULTS = {
    "rtsp_path": "/mjpeg/1",
    "username": "admin",
    "fps": 15,
    "resolution": (640, 480),
    "buffer_size": 2,
    "timeout": 30
}

# Shima machine LED status descriptions (Italian)
LED_STATUS_DESCRIPTIONS = {
    "off": "Spenta - Macchina ferma",
    "green": "Verde - Funzionamento normale",
    "yellow": "Gialla - Attenzione richiesta",
    "red": "Rossa - Errore/Allarme",
    "flashing_green": "Verde lampeggiante - Normale (intermittente)",
    "flashing_yellow": "Gialla lampeggiante - Attenzione (intermittente)", 
    "flashing_red": "Rossa lampeggiante - Errore critico"
}

# Notification templates (Italian)
NOTIFICATION_TEMPLATES = {
    "status_change": "Macchina {machine_id} - LED {region_name}: Stato cambiato da {old_status} a {new_status} alle {timestamp}",
    "connection_lost": "Persa connessione con camera {camera_id} per macchina {machine_id}",
    "connection_restored": "Ripristinata connessione con camera {camera_id} per macchina {machine_id}",
    "system_startup": "Sistema di monitoraggio LED Shima avviato",
    "system_shutdown": "Sistema di monitoraggio LED Shima arrestato"
}

# Frigate integration settings
FRIGATE_INTEGRATION = {
    "enabled": False,
    "frigate_url": "http://localhost:5000",
    "mqtt_server": "localhost",
    "mqtt_port": 1883,
    "mqtt_topic_prefix": "shima_monitor"
}

# Database schema for optional SQLite storage
DATABASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    camera_id TEXT NOT NULL,
    machine_id TEXT NOT NULL,
    region_name TEXT NOT NULL,
    status TEXT NOT NULL,
    confidence REAL NOT NULL,
    brightness REAL NOT NULL,
    old_status TEXT,
    notification_sent BOOLEAN DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_detections_timestamp ON detections(timestamp);
CREATE INDEX IF NOT EXISTS idx_detections_machine ON detections(machine_id);
CREATE INDEX IF NOT EXISTS idx_detections_status ON detections(status);
"""

# Environment variable overrides
def load_env_overrides():
    """Load configuration overrides from environment variables"""
    
    # RTSP credentials from environment
    if os.getenv("RTSP_USERNAME"):
        ESP32_CAM_DEFAULTS["username"] = os.getenv("RTSP_USERNAME")
    
    if os.getenv("RTSP_PASSWORD"):
        ESP32_CAM_DEFAULTS["password"] = os.getenv("RTSP_PASSWORD")
    
    # Email settings from environment
    if os.getenv("SMTP_USERNAME"):
        SETTINGS["email"] = SETTINGS.get("email", {})
        SETTINGS["email"]["username"] = os.getenv("SMTP_USERNAME")
    
    if os.getenv("SMTP_PASSWORD"):
        SETTINGS["email"] = SETTINGS.get("email", {})
        SETTINGS["email"]["password"] = os.getenv("SMTP_PASSWORD")
    
    # Debug mode from environment
    if os.getenv("DEBUG", "").lower() in ["true", "1", "yes"]:
        SETTINGS["debug"]["verbose_logging"] = True
        SETTINGS["logging"]["level"] = "DEBUG"
    
    # Test mode from environment
    if os.getenv("TEST_MODE", "").lower() in ["true", "1", "yes"]:
        SETTINGS["debug"]["test_mode"] = True

# Load environment overrides on import
load_env_overrides()

# Validation functions
def validate_camera_config(config):
    """Validate camera configuration"""
    required_fields = ["rtsp_url", "machine_id"]
    for field in required_fields:
        if field not in config:
            raise ValueError(f"Missing required field in camera config: {field}")
    
    if not config["rtsp_url"].startswith(("rtsp://", "http://")):
        raise ValueError("Invalid RTSP URL format")
    
    return True

def validate_led_region_config(config):
    """Validate LED region configuration"""
    required_fields = ["name", "x", "y", "width", "height", "machine_id"]
    for field in required_fields:
        if field not in config:
            raise ValueError(f"Missing required field in LED region config: {field}")
    
    # Validate coordinates
    for coord in ["x", "y", "width", "height"]:
        if not isinstance(config[coord], int) or config[coord] < 0:
            raise ValueError(f"Invalid {coord} value in LED region config")
    
    return True

# Export main settings
__all__ = [
    "SETTINGS",
    "ESP32_CAM_DEFAULTS", 
    "LED_STATUS_DESCRIPTIONS",
    "NOTIFICATION_TEMPLATES",
    "FRIGATE_INTEGRATION",
    "DATABASE_SCHEMA",
    "validate_camera_config",
    "validate_led_region_config"
]