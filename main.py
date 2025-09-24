import threading
import time
import os
import signal
import sys
import logging
from datetime import datetime
from flask import Flask, Response, render_template_string, jsonify
import cv2

from src.led_detector import LEDDetector, LEDRegion, LEDStatus
from src.notification_system import NotificationManager, SlackProvider

# Flask app
app = Flask(__name__)

# RTSP URL personalizzato
RTSP_URL = "rtsp://192.168.21.213:8554"

# Slack webhook personalizzato
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/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"

# Config LED region (modifica secondo coordinate reali)
led_regions = [
    LEDRegion("status_main", 120, 80, 40, 40, "SHIMA_001"),
]

led_detector = LEDDetector()

# Creo NotificationManager e aggiungo SlackProvider
notification_manager = NotificationManager()
slack_provider = SlackProvider(SLACK_WEBHOOK_URL)
notification_manager.add_provider(slack_provider)

# Stato notifiche per web UI (ultime 10 notifiche)
notification_history = []

# Funzione per log giornaliero
def open_daily_log():
    log_dir = "log"
    os.makedirs(log_dir, exist_ok=True)
    filename = datetime.now().strftime("Log-%d-%m-%Y.txt")
    filepath = os.path.join(log_dir, filename)
    return open(filepath, "a", encoding="utf-8")

log_file = open_daily_log()

# Gestione segnale per uscita pulita
def cleanup_and_exit(signum, frame):
    print(f"\nSegnale {signum} ricevuto, chiudo file log e arresto...")
    if not log_file.closed:
        log_file.close()
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup_and_exit)    # Ctrl+C
signal.signal(signal.SIGTERM, cleanup_and_exit)   # kill

def draw_overlay(frame, detections):
    color_map = {
        LEDStatus.OFF: (128, 128, 128),
        LEDStatus.GREEN: (0, 255, 0),
        LEDStatus.YELLOW: (0, 255, 255),
        LEDStatus.RED: (0, 0, 255),
        LEDStatus.FLASHING_GREEN: (0, 128, 0),
        LEDStatus.FLASHING_YELLOW: (0, 128, 255),
        LEDStatus.FLASHING_RED: (0, 0, 128)
    }
    for det in detections:
        region = det.region
        color = color_map.get(det.status, (255, 255, 255))
        cv2.rectangle(frame, (region.x, region.y), (region.x + region.width, region.y + region.height), color, 2)
        label = f"{region.name}: {det.status.value}"
        cv2.putText(frame, label, (region.x, region.y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return frame

def gen_frames():
    cap = cv2.VideoCapture(RTSP_URL)
    if not cap.isOpened():
        print(f"Errore: impossibile aprire il flusso RTSP {RTSP_URL}")
        return
    prev_status = {}
    while True:
        success, frame = cap.read()
        if not success:
            # Ignora silenziosamente e attendi
            time.sleep(0.1)
            continue

        detections = led_detector.detect_multiple_leds(frame, led_regions)
        frame = draw_overlay(frame, detections)

        # Gestione notifiche e log cambio stato
        for det in detections:
            key = det.region.name
            current = det.status.value
            old = prev_status.get(key)
            if old != current:
                prev_status[key] = current

                timestamp = datetime.now()
                time_str = timestamp.strftime("%H:%M:%S")
                camera_name = det.region.machine_id

                # Scrivi log file
                log_line = f"{camera_name};{old if old else 'None'};{current};{time_str}\n"
                log_file.write(log_line)
                log_file.flush()

                # Stampa su console solo cambi stato
                print(log_line.strip())

                # Aggiorna storico notifiche per UI e invia notifica Slack
                message = f"LED {key} cambiato da {old} a {current} alle {time_str}"
                success = notification_manager.send_notification(
                    title="Shima LED Monitor Alert",
                    message=message,
                    priority="high"
                )

                notification_history.append({
                    "time": time_str,
                    "message": message,
                    "success": success
                })
                if len(notification_history) > 10:
                    notification_history.pop(0)

        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/')
def index():
    html = """
    <html><head><title>Shima Monitor</title></head><body>
    <h1>Shima LED Monitor con notifiche Slack</h1>
    <p>Video live:</p>
    <img src="/video_feed" width="640" height="480" />
    <h2>Ultime notifiche:</h2>
    <ul id="notifications"></ul>
    <script>
    async function fetchNotifications() {
        const resp = await fetch('/api/notifications');
        const data = await resp.json();
        const ul = document.getElementById('notifications');
        ul.innerHTML = '';
        data.forEach(item => {
            const li = document.createElement('li');
            li.textContent = item.time + ': ' + item.message + (item.success ? ' ✅' : ' ❌');
            ul.appendChild(li);
        });
    }
    setInterval(fetchNotifications, 2000);
    fetchNotifications();
    </script>
    </body></html>
    """
    return render_template_string(html)

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/notifications')
def api_notifications():
    return jsonify(notification_history)

def run_flask():
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)

def main():
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("Web interface avviata all'indirizzo http://0.0.0.0:8080")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Interruzione ricevuta, chiudo...")
    finally:
        if not log_file.closed:
            log_file.close()
        print("File di log chiuso")

if __name__ == '__main__':
    main()
