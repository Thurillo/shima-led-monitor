# Main Application for Shima LED Monitoring System
# Integrates RTSP streams, LED detection, and notification system

import logging
import signal
import sys
import time
import yaml
import json
from datetime import datetime
from typing import Dict, List
from pathlib import Path

from src.rtsp_client import RTSPManager, RTSPConfig
from src.led_detector import LEDDetector, LEDRegion, LEDStatus
from src.notification_system import NotificationManager
from config.settings import SETTINGS

class ShimaMonitor:
    """
    Main application class for Shima knitting machine LED monitoring
    Coordinates RTSP streams, LED detection, and notifications
    """
    
    def __init__(self, config_file: str = "config/camera_config.yaml"):
        self.logger = self._setup_logging()
        self.config_file = config_file
        
        # Core components
        self.rtsp_manager = RTSPManager()
        self.led_detector = LEDDetector()
        self.notification_manager = NotificationManager()
        
        # Monitoring state
        self.running = False
        self.monitoring_threads = {}
        self.last_status = {}
        
        # Load configuration
        self.cameras = {}
        self.led_regions = {}
        self.load_configuration()
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('logs/shima_monitor.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        return logging.getLogger(__name__)
    
    def load_configuration(self):
        """Load camera and LED region configuration from YAML file"""
        try:
            with open(self.config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            # Load camera configurations
            for camera_id, camera_config in config.get('cameras', {}).items():
                rtsp_config = RTSPConfig(
                    url=camera_config['rtsp_url'],
                    username=camera_config.get('username'),
                    password=camera_config.get('password'),
                    fps=camera_config.get('fps', 15),
                    buffer_size=camera_config.get('buffer_size', 2)
                )
                self.cameras[camera_id] = rtsp_config
            
            # Load LED region configurations
            for camera_id, regions in config.get('led_regions', {}).items():
                self.led_regions[camera_id] = []
                for region_config in regions:
                    region = LEDRegion(
                        name=region_config['name'],
                        x=region_config['x'],
                        y=region_config['y'],
                        width=region_config['width'],
                        height=region_config['height'],
                        machine_id=region_config['machine_id']
                    )
                    self.led_regions[camera_id].append(region)
            
            self.logger.info(f"Loaded configuration for {len(self.cameras)} cameras "
                           f"with {sum(len(regions) for regions in self.led_regions.values())} LED regions")
                           
        except Exception as e:
            self.logger.error(f"Error loading configuration: {e}")
            sys.exit(1)
    
    def start_monitoring(self):
        """Start monitoring all configured cameras"""
        if self.running:
            self.logger.warning("Monitoring is already running")
            return
        
        self.logger.info("Starting Shima LED monitoring system...")
        self.running = True
        
        # Start RTSP streams
        for camera_id, rtsp_config in self.cameras.items():
            if self.rtsp_manager.add_stream(camera_id, rtsp_config):
                self.logger.info(f"Started RTSP stream for camera {camera_id}")
            else:
                self.logger.error(f"Failed to start RTSP stream for camera {camera_id}")
        
        # Start monitoring threads
        import threading
        for camera_id in self.cameras.keys():
            thread = threading.Thread(
                target=self._monitor_camera,
                args=(camera_id,),
                daemon=True
            )
            thread.start()
            self.monitoring_threads[camera_id] = thread
        
        self.logger.info("All monitoring threads started")
    
    def _monitor_camera(self, camera_id: str):
        """Monitor LED status for a specific camera"""
        self.logger.info(f"Starting LED monitoring for camera {camera_id}")
        
        regions = self.led_regions.get(camera_id, [])
        if not regions:
            self.logger.warning(f"No LED regions configured for camera {camera_id}")
            return
        
        while self.running:
            try:
                # Get latest frame
                frame = self.rtsp_manager.get_frame(camera_id)
                if frame is None:
                    time.sleep(0.1)
                    continue
                
                # Detect LED status in all regions
                detections = self.led_detector.detect_multiple_leds(frame, regions)
                
                # Process each detection
                for detection in detections:
                    self._process_detection(camera_id, detection)
                
                # Control monitoring frequency
                time.sleep(1.0 / SETTINGS['monitoring_fps'])
                
            except Exception as e:
                self.logger.error(f"Error monitoring camera {camera_id}: {e}")
                time.sleep(1)
    
    def _process_detection(self, camera_id: str, detection):
        """Process a LED detection and handle status changes"""
        region_key = f"{camera_id}_{detection.region.name}"
        current_status = detection.status
        
        # Check if status changed
        if region_key not in self.last_status or self.last_status[region_key] != current_status:
            
            # Log status change
            old_status = self.last_status.get(region_key, "unknown")
            self.logger.info(f"LED status change in {region_key}: {old_status} -> {current_status.value}")
            
            # Send notification
            self._send_notification(detection, camera_id, old_status)
            
            # Update last status
            self.last_status[region_key] = current_status
            
            # Save to database/file if configured
            self._save_detection_history(detection, camera_id)
    
    def _send_notification(self, detection, camera_id: str, old_status: str):
        """Send notification for LED status change"""
        try:
            # Determine notification priority based on LED status
            priority = self._get_notification_priority(detection.status)
            
            message = self._create_notification_message(detection, camera_id, old_status)
            
            self.notification_manager.send_notification(
                title=f"Shima Machine Alert - {detection.region.machine_id}",
                message=message,
                priority=priority,
                metadata={
                    'camera_id': camera_id,
                    'machine_id': detection.region.machine_id,
                    'region_name': detection.region.name,
                    'status': detection.status.value,
                    'confidence': detection.confidence,
                    'timestamp': detection.timestamp.isoformat()
                }
            )
            
        except Exception as e:
            self.logger.error(f"Error sending notification: {e}")
    
    def _get_notification_priority(self, status: LEDStatus) -> str:
        """Determine notification priority based on LED status"""
        if status in [LEDStatus.RED, LEDStatus.FLASHING_RED]:
            return "high"
        elif status in [LEDStatus.YELLOW, LEDStatus.FLASHING_YELLOW]:
            return "medium"
        elif status in [LEDStatus.OFF]:
            return "medium"
        else:
            return "low"
    
    def _create_notification_message(self, detection, camera_id: str, old_status: str) -> str:
        """Create notification message"""
        machine_id = detection.region.machine_id
        region_name = detection.region.name
        new_status = detection.status.value
        timestamp = detection.timestamp.strftime("%H:%M:%S")
        
        # Map status to Italian descriptions
        status_descriptions = {
            "off": "spenta",
            "green": "verde (funzionamento normale)",
            "yellow": "gialla (attenzione)",
            "red": "rossa (errore)",
            "flashing_green": "verde lampeggiante (normale)",
            "flashing_yellow": "gialla lampeggiante (attenzione)",
            "flashing_red": "rossa lampeggiante (errore critico)"
        }
        
        status_desc = status_descriptions.get(new_status, new_status)
        
        return (f"Macchina {machine_id} - LED {region_name}: "
                f"Stato cambiato da {old_status} a {status_desc} "
                f"alle {timestamp}")
    
    def _save_detection_history(self, detection, camera_id: str):
        """Save detection history to file"""
        try:
            history_file = Path("logs/detection_history.jsonl")
            history_file.parent.mkdir(exist_ok=True)
            
            record = {
                'timestamp': detection.timestamp.isoformat(),
                'camera_id': camera_id,
                'machine_id': detection.region.machine_id,
                'region_name': detection.region.name,
                'status': detection.status.value,
                'confidence': detection.confidence,
                'brightness': detection.brightness
            }
            
            with open(history_file, 'a') as f:
                f.write(json.dumps(record) + '\n')
                
        except Exception as e:
            self.logger.error(f"Error saving detection history: {e}")
    
    def get_system_status(self) -> Dict:
        """Get current system status"""
        rtsp_stats = self.rtsp_manager.get_all_stats()
        
        status = {
            'running': self.running,
            'cameras': len(self.cameras),
            'active_streams': len([s for s in rtsp_stats.values() if s['is_connected']]),
            'total_led_regions': sum(len(regions) for regions in self.led_regions.values()),
            'rtsp_stats': rtsp_stats,
            'last_status': dict(self.last_status),
            'timestamp': datetime.now().isoformat()
        }
        
        return status
    
    def stop_monitoring(self):
        """Stop monitoring system"""
        if not self.running:
            return
        
        self.logger.info("Stopping Shima LED monitoring system...")
        self.running = False
        
        # Stop RTSP streams
        self.rtsp_manager.stop_all()
        
        # Wait for monitoring threads to finish
        for camera_id, thread in self.monitoring_threads.items():
            self.logger.info(f"Waiting for monitoring thread {camera_id} to finish...")
            thread.join(timeout=5)
        
        self.logger.info("Monitoring system stopped")
    
    def _signal_handler(self, signum, frame):
        """Handle system signals for graceful shutdown"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.stop_monitoring()
        sys.exit(0)

def main():
    """Main application entry point"""
    print("=" * 60)
    print("SHIMA SEIKI LED MONITORING SYSTEM")
    print("Sistema di monitoraggio LED per macchine per maglieria")
    print("=" * 60)
    
    try:
        # Create necessary directories
        Path("logs").mkdir(exist_ok=True)
        
        # Initialize and start monitoring system
        monitor = ShimaMonitor()
        monitor.start_monitoring()
        
        # Keep main thread alive
        print("\\nSistema di monitoraggio avviato.")
        print("Premi Ctrl+C per fermare il sistema.\\n")
        
        while True:
            time.sleep(10)
            
            # Print system status every 10 seconds
            status = monitor.get_system_status()
            active_cameras = status['active_streams']
            total_cameras = status['cameras']
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                  f"Telecamere attive: {active_cameras}/{total_cameras}")
            
    except KeyboardInterrupt:
        print("\\nRicevuto segnale di interruzione...")
    except Exception as e:
        print(f"Errore critico: {e}")
        logging.exception("Critical error in main application")
    finally:
        if 'monitor' in locals():
            monitor.stop_monitoring()

if __name__ == "__main__":
    main()