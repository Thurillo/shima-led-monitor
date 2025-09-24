import threading
import time
import os
import sys
import signal
from datetime import datetime
from flask import Flask, Response, render_template_string, jsonify, send_from_directory, abort
import cv2

from src.led_detector import LEDDetector, LEDRegion, LEDStatus
from src.notification_system import NotificationManager, SlackProvider

# Classe per sopprimere temporaneamente stderr
class suppress_stderr:
    def __enter__(self):
        self.stderr_fd = sys.stderr.fileno()
        self.null_fd = os.open(os.devnull, os.O_RDWR)
        self.old_stderr = os.dup(self.stderr_fd)
        os.dup2(self.null_fd, self.stderr_fd)

    def __exit__(self, exc_type, exc_val, exc_tb):
        os.dup2(self.old_stderr, self.stderr_fd)
        os.close(self.null_fd)
        os.close(self.old_stderr)

# Flask app
app = Flask(__name__)

# RTSP URL personalizzato
RTSP_URL = "rtsp://192.168.21.213:8554"

# Slack webhook personalizzato
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/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"

# Config LED region (da modificare secondo coordinate reali)
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

LOG_DIR = "log"

# Funzione per log giornaliero
def open_daily_log():
    os.makedirs(LOG_DIR, exist_ok=True)
    filename = datetime.now().strftime("Log-%d-%m-%Y.txt")
    filepath = os.path.join(LOG_DIR, filename)
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
    with suppress_stderr():
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
    <p><a href="/logs">Visualizza file di log</a></p>
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

# Route per lista file di log
@app.route('/logs')
def list_logs():
    try:
        files = os.listdir(LOG_DIR)
        files = sorted(files, reverse=True)  # Lista file ordinata più recente prima
    except FileNotFoundError:
        files = []

    links_html = "<ul>"
    for f in files:
        links_html += f'<li><a href="/logs/download/{f}">{f}</a></li>'
    links_html += "</ul>"

    html = f"""
    <html><head><title>File di Log</title></head><body>
    <h1>File di Log Disponibili</h1>
    {links_html}
    <p><a href="/">Torna alla home</a></p>
    </body></html>
    """
    return html

# Route per scaricare file log specifico
@app.route('/logs/download/<path:filename>')
def download_log(filename):
    # Sicurezza: assicurarsi che filename non esca dalla cartella log
    if '..' in filename or filename.startswith('/'):
        abort(400, "Nome file non valido")
    try:
        return send_from_directory(LOG_DIR, filename, as_attachment=True)
    except FileNotFoundError:
        abort(404, "File non trovato")

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
