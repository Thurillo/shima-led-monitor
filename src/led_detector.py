# LED Detector Module for Shima Knitting Machine Monitoring
# Detects and classifies LED status (Green/Yellow/Red/Off) from RTSP streams

import cv2
import numpy as np
import logging
from datetime import datetime
from typing import Tuple, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

class LEDStatus(Enum):
    """LED status enumeration"""
    OFF = "off"
    GREEN = "green" 
    YELLOW = "yellow"
    RED = "red"
    FLASHING_GREEN = "flashing_green"
    FLASHING_YELLOW = "flashing_yellow" 
    FLASHING_RED = "flashing_red"

@dataclass
class LEDRegion:
    """Defines a LED monitoring region"""
    name: str
    x: int
    y: int
    width: int
    height: int
    machine_id: str

@dataclass
class LEDDetection:
    """LED detection result"""
    region: LEDRegion
    status: LEDStatus
    confidence: float
    timestamp: datetime
    brightness: float
    
class LEDDetector:
    """
    Advanced LED detector for Shima knitting machine status monitoring
    Uses HSV color space detection and temporal analysis for flashing detection
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # HSV color ranges for LED detection
        # --- Modifica qui per adattare i range HSV ---
        # Allargati per più tolleranza alle variazioni di luce e fotocamera
        self.color_ranges = {
            LEDStatus.GREEN: {
                'lower': np.array([35, 40, 40]),   # prima era 40,50,50
                'upper': np.array([90, 255, 255])  # prima era 80,255,255
            },
            LEDStatus.YELLOW: {
                'lower': np.array([15, 70, 70]),   # prima 20,100,100
                'upper': np.array([40, 255, 255])  # prima 35,255,255
            },
            LEDStatus.RED: {
                'lower': np.array([0, 80, 60]),    # prima 0,120,70
                'upper': np.array([15, 255, 255])  # prima 10,255,255
            }
        }
        
        # Additional red range (wraps around HSV hue)
        self.red_range_2 = {
            'lower': np.array([165, 80, 60]),     # prima 170,120,70
            'upper': np.array([180, 255, 255])    # invariato
        }
        
        # Threshold di luminosità sotto cui LED è considerato OFF
        # Aumenta o diminuisci per stabilità sotto diverse condizioni di luce
        self.brightness_threshold = 25  # prima implicitamente 30
        
        # Temporal tracking for flashing detection
        self.status_history = {}
        self.history_length = 10  # frames to keep for flashing detection
        self.flashing_threshold = 3  # minimum changes to consider flashing
        
        # Morphological operations kernels
        self.kernel_small = np.ones((3,3), np.uint8)
        self.kernel_medium = np.ones((5,5), np.uint8)
        
    def preprocess_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Preprocess frame for LED detection
        Convert to HSV and apply blur to reduce noise
        """
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hsv_blurred = cv2.GaussianBlur(hsv, (5, 5), 0)
        return hsv_blurred
    
    def detect_led_color(self, roi_hsv: np.ndarray) -> Tuple[LEDStatus, float, float]:
        """
        Detect LED color in ROI using HSV color thresholds.
        Returns: (status, confidence, brightness)
        """
        brightness = np.mean(roi_hsv[:, :, 2])  # brightness channel

        if brightness < self.brightness_threshold:
            # LED troppo scuro, considerato spento
            return LEDStatus.OFF, 1.0, brightness
        
        # Crea maschere per ogni colore
        masks = {}

        # Verde - usa il range HSV ampliato (puoi modificare qui)
        masks[LEDStatus.GREEN] = cv2.inRange(roi_hsv, 
                                             self.color_ranges[LEDStatus.GREEN]['lower'],
                                             self.color_ranges[LEDStatus.GREEN]['upper'])
        
        # Giallo
        masks[LEDStatus.YELLOW] = cv2.inRange(roi_hsv,
                                             self.color_ranges[LEDStatus.YELLOW]['lower'],
                                             self.color_ranges[LEDStatus.YELLOW]['upper'])
        
        # Rosso - gestisce range doppio per effetto wrapping hue HSV
        red_mask1 = cv2.inRange(roi_hsv,
                               self.color_ranges[LEDStatus.RED]['lower'],
                               self.color_ranges[LEDStatus.RED]['upper'])
        red_mask2 = cv2.inRange(roi_hsv,
                               self.red_range_2['lower'],
                               self.red_range_2['upper'])
        masks[LEDStatus.RED] = cv2.bitwise_or(red_mask1, red_mask2)
        
        # Pulizia maschere con operazioni morfologiche per ridurre rumore
        for status in masks:
            masks[status] = cv2.morphologyEx(masks[status], cv2.MORPH_OPEN, self.kernel_small)
            masks[status] = cv2.morphologyEx(masks[status], cv2.MORPH_CLOSE, self.kernel_medium)
        
        # Calcolo confidence per ogni colore in base al numero di pixel attivi
        confidences = {}
        total_pixels = roi_hsv.shape[0] * roi_hsv.shape[1]
        for status, mask in masks.items():
            non_zero_pixels = cv2.countNonZero(mask)
            confidence = non_zero_pixels / total_pixels
            confidences[status] = confidence
        
        # Scegli il colore con confidence massima
        best_status = max(confidences.keys(), key=lambda x: confidences[x])
        best_confidence = confidences[best_status]
        
        # Se la confidence più alta è sotto soglia minima, considera LED spento
        if best_confidence < 0.1:
            return LEDStatus.OFF, 1.0, brightness
        
        return best_status, best_confidence, brightness
    
    def update_status_history(self, region_name: str, status: LEDStatus) -> None:
        """
        Aggiorna la storia degli stati della regione per riconoscere il lampeggio
        """
        if region_name not in self.status_history:
            self.status_history[region_name] = []
        
        self.status_history[region_name].append(status)
        
        # Mantieni solo gli ultimi frame definiti da history_length
        if len(self.status_history[region_name]) > self.history_length:
            self.status_history[region_name].pop(0)
    
    def detect_flashing(self, region_name: str, current_status: LEDStatus) -> LEDStatus:
        """
        Rileva se un LED è lampeggiante analizzando la storia degli stati
        """
        if region_name not in self.status_history:
            return current_status
        
        history = self.status_history[region_name]
        
        if len(history) < self.history_length:
            return current_status
        
        changes = 0
        base_color = None
        
        for i in range(1, len(history)):
            if history[i] != history[i-1]:
                changes += 1
                if history[i] in [LEDStatus.GREEN, LEDStatus.YELLOW, LEDStatus.RED]:
                    base_color = history[i]
        
        if changes >= self.flashing_threshold and base_color:
            if base_color == LEDStatus.GREEN:
                return LEDStatus.FLASHING_GREEN
            elif base_color == LEDStatus.YELLOW:
                return LEDStatus.FLASHING_YELLOW
            elif base_color == LEDStatus.RED:
                return LEDStatus.FLASHING_RED
        
        return current_status
    
    def detect_led_in_region(self, frame: np.ndarray, region: LEDRegion) -> LEDDetection:
        """
        Rileva lo stato del LED in una regione specifica
        """
        roi = frame[region.y:region.y+region.height, region.x:region.x+region.width]
        
        if roi.size == 0:
            self.logger.warning(f"Empty ROI for region {region.name}")
            return LEDDetection(
                region=region,
                status=LEDStatus.OFF,
                confidence=0.0,
                timestamp=datetime.now(),
                brightness=0.0
            )
        
        roi_hsv = self.preprocess_frame(roi)
        status, confidence, brightness = self.detect_led_color(roi_hsv)
        self.update_status_history(region.name, status)
        final_status = self.detect_flashing(region.name, status)
        
        return LEDDetection(
            region=region,
            status=final_status,
            confidence=confidence,
            timestamp=datetime.now(),
            brightness=brightness
        )
    
    def detect_multiple_leds(self, frame: np.ndarray, regions: List[LEDRegion]) -> List[LEDDetection]:
        """
        Rileva lo stato di più LED in più regioni
        """
        results = []
        
        for region in regions:
            try:
                detection = self.detect_led_in_region(frame, region)
                results.append(detection)
                self.logger.debug(f"Region {region.name}: {detection.status.value} (conf: {detection.confidence:.2f})")
            except Exception as e:
                self.logger.error(f"Error detecting LED in region {region.name}: {e}")
                
        return results
    
    def visualize_detections(self, frame: np.ndarray, detections: List[LEDDetection]) -> np.ndarray:
        """
        Visualizza le rilevazioni disegnando rettangoli colorati sulle regioni LED
        """
        result_frame = frame.copy()
        color_map = {
            LEDStatus.OFF: (128, 128, 128),
            LEDStatus.GREEN: (0, 255, 0),
            LEDStatus.YELLOW: (0, 255, 255),
            LEDStatus.RED: (0, 0, 255),
            LEDStatus.FLASHING_GREEN: (0, 128, 0),
            LEDStatus.FLASHING_YELLOW: (0, 128, 255),
            LEDStatus.FLASHING_RED: (0, 0, 128)
        }
        
        for detection in detections:
            region = detection.region
            status = detection.status
            color = color_map.get(status, (255, 255, 255))
            cv2.rectangle(result_frame, (region.x, region.y),
                          (region.x + region.width, region.y + region.height),
                          color, 2)
            label = f"{region.name}: {status.value}"
            cv2.putText(result_frame, label, (region.x, region.y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        return result_frame

# Se vuoi fare test rapido, aggiungi qui la configurazione e usa il detector
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    sample_regions = [
        LEDRegion("status_led_1", 100, 50, 30, 30, "shima_001"),
        LEDRegion("status_led_2", 200, 50, 30, 30, "shima_001"),
        LEDRegion("work_led", 150, 100, 40, 40, "shima_001")
    ]
    
    detector = LEDDetector()
    print("LED Detector initialized for Shima knitting machine monitoring")
    print(f"Configured for {len(sample_regions)} LED regions")
