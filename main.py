import threading
import time
import os
import sys
import signal
import yaml
from datetime import datetime
from flask import Flask, Response, render_template_string, jsonify, send_from_directory, abort
import cv2

from src.led_detector import LEDDetector, LEDRegion, LEDStatus
from src.notification_system import NotificationManager, SlackProvider

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

app = Flask(__name__)

# Costanti
LOG_DIR = "log"
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/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"
STATE_COLOR_MAP = {
    "off": "#808080",
    "green": "#00FF00",
    "yellow": "#FFFF00",
    "red": "#FF0000",
    "flashing_green": "#008000",
    "flashing_yellow": "#FFA500",
    "flashing_red": "#800000"
}

# Gestione notifiche
notification_manager = NotificationManager()
slack_provider = SlackProvider(SLACK_WEBHOOK_URL)
notification_manager.add_provider(slack_provider)

# Stato globale delle camere: 
# per ogni machine_id : { 'prev_status': {region_name: status}, 'notifications': [...] }
camera_states = {}

# Apertura log file giornaliero, uno solo per tutto
def open_daily_log():
    os.makedirs(LOG_DIR, exist_ok=True)
    filename = datetime.now().strftime("Log-%d-%m-%Y.txt")
    filepath = os.path.join(LOG_DIR, filename)
    return open(filepath, "a", encoding="utf-8")
log_file = open_daily_log()

def cleanup_and_exit(signum, frame):
    print(f"\nSegnale {signum} ricevuto, chiudo file log e arresto...")
    if not log_file.closed:
        log_file.close()
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup_and_exit)
signal.signal(signal.SIGTERM, cleanup_and_exit)

# Funzione per processare i LED regions multistream
def monitor_camera(camera_cfg):
    machine_id = camera_cfg['machine_id']
    rtsp_url = camera_cfg['rtsp_url']
    
    # Costruzione LEDRegion da config
    led_regions_cfg = camera_cfg.get('led_regions', [])
    led_regions = []
    for r in led_regions_cfg:
        led_regions.append(LEDRegion(r['name'], r['x'], r['y'], r['width'], r['height'], machine_id))

    led_detector = LEDDetector()
    prev_status = {}
    camera_states[machine_id] = {
        'prev_status': prev_status, 
        'notifications': []
    }

    with suppress_stderr():
        cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        print(f"Errore: impossibile aprire il flusso RTSP {rtsp_url} per camera {machine_id}")
        return

    while True:
        success, frame = cap.read()
        if not success:
            time.sleep(0.1)
            continue

        detections = led_detector.detect_multiple_leds(frame, led_regions)

        # Controllo cambi stato e gestioni notifiche
        for det in detections:
            key = det.region.name
            current = det.status.value
            old = prev_status.get(key)
            if old != current:
                prev_status[key] = current
                timestamp = datetime.now()
                time_str = timestamp.strftime("%H:%M:%S")
                
                # Log line camera;old;new;time
                log_line = f"{machine_id};{old if old else 'None'};{current};{time_str}\n"
                log_file.write(log_line)
                log_file.flush()

                print(log_line.strip())

                message = f"{machine_id} LED {key} cambiato da {old} a {current} alle {time_str}"
                success = notification_manager.send_notification(
                    title="Shima LED Monitor Alert",
                    message=message,
                    priority="high"
                )

                # Salvo storico notifiche per camera
                cam_notifications = camera_states[machine_id]['notifications']
                cam_notifications.append({
                    "time": time_str,
                    "message": message,
                    "success": success
                })
                if len(cam_notifications) > 50:
                    cam_notifications.pop(0)

        # Memorizzo frame con overlay per streaming  
        frame_with_overlay = draw_overlay(frame, detections)
        ret, jpeg = cv2.imencode('.jpg', frame_with_overlay)
        if ret:
            camera_states[machine_id]['frame'] = jpeg.tobytes()

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

# Route principale: pagina con lista camere e stato colore
@app.route('/camera_status')
def camera_status():
    rows = 6
    cols = 10
    cameras_list = list(camera_states.keys())
    cameras_list.sort()

    html = """
    <html>
    <head>
        <title>Stato Videocamere</title>
        <meta http-equiv="refresh" content="15">
        <style>
            body { background: #222; color: white; font-family: Arial, sans-serif; margin: 10px; }
            table { width: 100%; border-collapse: collapse; }
            td, th { border: 1px solid #444; text-align: center; padding: 8px; }
            a { text-decoration: none; color: white; font-weight: bold; display: block; }
        </style>
    </head>
    <body>
    <h1>Elenco Videocamere</h1>
    <table>
    """

    # Fill cells row x col
    idx = 0
    for r in range(rows):
        html += "<tr>"
        for c in range(cols):
            if idx < len(cameras_list):
                cam = cameras_list[idx]
                # Prendo ultimo stato dal primo led region
                prev_status = camera_states[cam]['prev_status']
                first_region = next(iter(prev_status), None)
                state = prev_status[first_region].lower() if first_region and prev_status.get(first_region) else 'off'
                color = STATE_COLOR_MAP.get(state, "#000000")
                html += f'<td style="color:{color};"><a href="/camera_status/{cam}">{cam}</a></td>'
                idx += 1
            else:
                html += "<td></td>"
        html += "</tr>"
    html += """
    </table>
    <p><a href="/">Torna alla home</a></p>
    </body>
    </html>
    """
    return html

# Pagina dettagliata camera con streaming e log realtime
@app.route('/camera_status/<machine_id>')
def camera_detail(machine_id):
    if machine_id not in camera_states:
        return f"Camera {machine_id} non trovata", 404

    html = f"""
    <html>
    <head>
        <title>Dettaglio {machine_id}</title>
        <meta http-equiv="refresh" content="15">
        <style>
            body {{ background: #222; color: white; font-family: Arial, sans-serif; padding: 10px; }}
            .video {{ max-width: 80vw; border: 2px solid #444; }}
            .log-box {{
                margin-top: 20px;
                height: 300px;
                overflow-y: scroll;
                background: #111;
                border: 1px solid #444;
                padding: 10px;
                font-family: monospace;
                white-space: pre-line;
            }}
        </style>
    </head>
    <body>
        <h1>Camera {machine_id}</h1>
        <img class="video" src="/video_feed/{machine_id}" alt="Stream {machine_id}"/>
        <div class="log-box" id="log">
            Caricamento log...
        </div>
        <p><a href="/camera_status">Torna alla lista camere</a></p>

        <script>
            async function fetchLog() {{
                const resp = await fetch('/api/log/{machine_id}');
                const data = await resp.json();
                const logDiv = document.getElementById('log');
                if(data.length === 0){{
                    logDiv.textContent = 'Nessun evento recente.';
                    return;
                }}
                logDiv.textContent = data.map(e => `[${{e.time}}] ${{e.message}} ${{e.success ? '✅' : '❌'}}`).join('\\n');
                logDiv.scrollTop = logDiv.scrollHeight;
            }}
            fetchLog();
            setInterval(fetchLog, 5000);
        </script>
    </body>
    </html>
    """
    return html

# Streaming individuale per camera
@app.route('/video_feed/<machine_id>')
def video_feed_machine(machine_id):
    if machine_id not in camera_states:
        return "Camera non trovata", 404

    def gen():
        while True:
            frame = camera_states[machine_id].get('frame')
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.05)

    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

# API per log di camera
@app.route('/api/log/<machine_id>')
def api_log_camera(machine_id):
    if machine_id not in camera_states:
        return jsonify([])

    return jsonify(camera_states[machine_id]['notifications'][-50:])  # ultimi 50 eventi

# --- Log files management (come prima) ---

@app.route('/')
def index():
    html = """
    <html><head><title>Shima Monitor</title></head><body>
    <h1>Shima LED Monitor con notifiche Slack</h1>
    <p><a href="/camera_status">Lista videocamere</a></p>
    <p><a href="/logs">Visualizza file di log</a></p>
    </body></html>
    """
    return html

@app.route('/logs')
def list_logs():
    try:
        files = os.listdir(LOG_DIR)
        files = sorted(files, reverse=True)
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

@app.route('/logs/download/<path:filename>')
def download_log(filename):
    if '..' in filename or filename.startswith('/'):
        abort(400, "Nome file non valido")
    try:
        return send_from_directory(LOG_DIR, filename, as_attachment=True)
    except FileNotFoundError:
        abort(404, "File non trovato")

def run_flask():
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)

def main():
    # Carico configurazione YAML
    with open("config/cameras.yaml", 'r') as f:
        cameras_config = yaml.safe_load(f)

    # Avvio un thread per ogni camera
    for cam_cfg in cameras_config.get('cameras', []):
        t = threading.Thread(target=monitor_camera, args=(cam_cfg,), daemon=True)
        t.start()
        print(f"Avviato monitoraggio per camera {cam_cfg.get('machine_id')}")

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
