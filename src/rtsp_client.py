# RTSP Client Module for ESP32 Camera Streams
# Handles RTSP stream connection and frame processing for Shima monitoring

import cv2
import threading
import queue
import logging
import time
from typing import Optional, Callable, Dict
from dataclasses import dataclass
import numpy as np

@dataclass
class RTSPConfig:
    """RTSP stream configuration"""
    url: str
    username: Optional[str] = None
    password: Optional[str] = None
    timeout: int = 30
    buffer_size: int = 1
    fps: int = 15
    resolution: tuple = (640, 480)

class RTSPClient:
    """
    RTSP client for ESP32-CAM streams with robust error handling
    Supports multiple concurrent streams and automatic reconnection
    """
    
    def __init__(self, config: RTSPConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Stream state
        self.is_running = False
        self.cap = None
        self.frame_queue = queue.Queue(maxsize=config.buffer_size)
        self.current_frame = None
        self.last_frame_time = 0
        
        # Threading
        self.capture_thread = None
        self.reconnect_thread = None
        
        # Statistics
        self.stats = {
            'frames_received': 0,
            'frames_dropped': 0,
            'connection_errors': 0,
            'last_fps': 0
        }
        
        # Callbacks
        self.frame_callback = None
        self.error_callback = None
        
    def _build_rtsp_url(self) -> str:
        """Build RTSP URL with authentication if provided"""
        base_url = self.config.url
        
        if self.config.username and self.config.password:
            # Insert credentials into URL
            if "://" in base_url:
                protocol, rest = base_url.split("://", 1)
                return f"{protocol}://{self.config.username}:{self.config.password}@{rest}"
        
        return base_url
    
    def _create_capture(self) -> Optional[cv2.VideoCapture]:
        """Create and configure video capture object"""
        try:
            rtsp_url = self._build_rtsp_url()
            self.logger.info(f"Connecting to RTSP stream: {rtsp_url.replace(self.config.password or '', '***')}")
            
            cap = cv2.VideoCapture(rtsp_url)
            
            # Set capture properties for optimal performance
            cap.set(cv2.CAP_PROP_BUFFER_SIZE, self.config.buffer_size)
            cap.set(cv2.CAP_PROP_FPS, self.config.fps)
            
            # Set timeout for connection
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.config.timeout * 1000)
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
            
            if not cap.isOpened():
                self.logger.error("Failed to open RTSP stream")
                return None
                
            # Test frame read
            ret, frame = cap.read()
            if not ret:
                self.logger.error("Failed to read initial frame from RTSP stream")
                cap.release()
                return None
            
            self.logger.info(f"RTSP stream connected successfully. Frame size: {frame.shape}")
            return cap
            
        except Exception as e:
            self.logger.error(f"Error creating RTSP capture: {e}")
            return None
    
    def _capture_frames(self):
        """Main capture loop running in separate thread"""
        frame_count = 0
        fps_counter_start = time.time()
        
        while self.is_running:
            try:
                if self.cap is None or not self.cap.isOpened():
                    self.logger.warning("RTSP connection lost, attempting reconnection...")
                    self._attempt_reconnection()
                    time.sleep(1)
                    continue
                
                ret, frame = self.cap.read()
                
                if not ret:
                    self.logger.warning("Failed to read frame from RTSP stream")
                    self.stats['connection_errors'] += 1
                    time.sleep(0.1)
                    continue
                
                # Update statistics
                self.stats['frames_received'] += 1
                frame_count += 1
                
                # Calculate FPS
                current_time = time.time()
                if current_time - fps_counter_start >= 1.0:
                    self.stats['last_fps'] = frame_count / (current_time - fps_counter_start)
                    frame_count = 0
                    fps_counter_start = current_time
                
                # Store current frame
                self.current_frame = frame.copy()
                self.last_frame_time = current_time
                
                # Add frame to queue (non-blocking)
                try:
                    if not self.frame_queue.full():
                        self.frame_queue.put_nowait(frame)
                    else:
                        # Drop oldest frame if buffer is full
                        try:
                            self.frame_queue.get_nowait()
                            self.stats['frames_dropped'] += 1
                        except queue.Empty:
                            pass
                        self.frame_queue.put_nowait(frame)
                except queue.Full:
                    self.stats['frames_dropped'] += 1
                
                # Call frame callback if set
                if self.frame_callback:
                    try:
                        self.frame_callback(frame)
                    except Exception as e:
                        self.logger.error(f"Error in frame callback: {e}")
                
            except Exception as e:
                self.logger.error(f"Error in capture loop: {e}")
                if self.error_callback:
                    self.error_callback(e)
                time.sleep(1)
    
    def _attempt_reconnection(self):
        """Attempt to reconnect to RTSP stream"""
        max_attempts = 5
        attempt = 0
        
        while attempt < max_attempts and self.is_running:
            attempt += 1
            self.logger.info(f"Reconnection attempt {attempt}/{max_attempts}")
            
            # Close existing connection
            if self.cap:
                self.cap.release()
                self.cap = None
            
            # Wait before reconnecting
            time.sleep(2 ** attempt)  # Exponential backoff
            
            # Create new connection
            self.cap = self._create_capture()
            if self.cap:
                self.logger.info("RTSP reconnection successful")
                return True
        
        self.logger.error("Failed to reconnect to RTSP stream after maximum attempts")
        return False
    
    def start(self) -> bool:
        """Start RTSP stream capture"""
        if self.is_running:
            self.logger.warning("RTSP client is already running")
            return True
        
        # Create initial connection
        self.cap = self._create_capture()
        if not self.cap:
            return False
        
        self.is_running = True
        
        # Start capture thread
        self.capture_thread = threading.Thread(target=self._capture_frames, daemon=True)
        self.capture_thread.start()
        
        self.logger.info("RTSP client started successfully")
        return True
    
    def stop(self):
        """Stop RTSP stream capture"""
        if not self.is_running:
            return
        
        self.logger.info("Stopping RTSP client...")
        self.is_running = False
        
        # Wait for threads to finish
        if self.capture_thread:
            self.capture_thread.join(timeout=5)
        
        # Release resources
        if self.cap:
            self.cap.release()
            self.cap = None
        
        # Clear frame queue
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                break
        
        self.logger.info("RTSP client stopped")
    
    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Get the most recent frame"""
        if not self.is_running:
            return None
        return self.current_frame
    
    def get_frame_from_queue(self, timeout: float = 1.0) -> Optional[np.ndarray]:
        """Get frame from queue with timeout"""
        try:
            return self.frame_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def set_frame_callback(self, callback: Callable[[np.ndarray], None]):
        """Set callback function called for each new frame"""
        self.frame_callback = callback
    
    def set_error_callback(self, callback: Callable[[Exception], None]):
        """Set callback function called on errors"""
        self.error_callback = callback
    
    def get_stats(self) -> Dict:
        """Get stream statistics"""
        stats = self.stats.copy()
        stats['is_connected'] = self.cap is not None and self.cap.isOpened()
        stats['queue_size'] = self.frame_queue.qsize()
        stats['last_frame_age'] = time.time() - self.last_frame_time if self.last_frame_time > 0 else float('inf')
        return stats
    
    def is_healthy(self) -> bool:
        """Check if stream is healthy"""
        if not self.is_running or not self.current_frame is not None:
            return False
        
        # Check if we're receiving recent frames
        frame_age = time.time() - self.last_frame_time
        return frame_age < 5.0  # Consider unhealthy if no frame in last 5 seconds

class RTSPManager:
    """
    Manager for multiple RTSP streams
    Handles multiple ESP32-CAM streams for different Shima machines
    """
    
    def __init__(self):
        self.clients = {}
        self.logger = logging.getLogger(__name__)
    
    def add_stream(self, stream_id: str, config: RTSPConfig) -> bool:
        """Add a new RTSP stream"""
        if stream_id in self.clients:
            self.logger.warning(f"Stream {stream_id} already exists")
            return False
        
        client = RTSPClient(config)
        if client.start():
            self.clients[stream_id] = client
            self.logger.info(f"Added RTSP stream: {stream_id}")
            return True
        
        return False
    
    def remove_stream(self, stream_id: str):
        """Remove RTSP stream"""
        if stream_id in self.clients:
            self.clients[stream_id].stop()
            del self.clients[stream_id]
            self.logger.info(f"Removed RTSP stream: {stream_id}")
    
    def get_frame(self, stream_id: str) -> Optional[np.ndarray]:
        """Get latest frame from specific stream"""
        if stream_id in self.clients:
            return self.clients[stream_id].get_latest_frame()
        return None
    
    def get_all_stats(self) -> Dict:
        """Get statistics for all streams"""
        return {stream_id: client.get_stats() 
                for stream_id, client in self.clients.items()}
    
    def stop_all(self):
        """Stop all RTSP streams"""
        for stream_id in list(self.clients.keys()):
            self.remove_stream(stream_id)

# Example usage
if __name__ == "__main__":
    # Example ESP32-CAM RTSP configuration
    config = RTSPConfig(
        url="rtsp://192.168.1.100:554/mjpeg/1",
        username="admin",
        password="password123",
        fps=15,
        buffer_size=2
    )
    
    client = RTSPClient(config)
    
    def frame_handler(frame):
        print(f"Received frame: {frame.shape}")
    
    client.set_frame_callback(frame_handler)
    
    if client.start():
        print("RTSP client started successfully")
        try:
            time.sleep(10)  # Run for 10 seconds
        except KeyboardInterrupt:
            pass
        finally:
            client.stop()
    else:
        print("Failed to start RTSP client")