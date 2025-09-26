import threading
import time
import os
import sys
import signal
import yaml
from datetime import datetime
from flask import Flask, Response, render_template, jsonify, send_from_directory, abort, url_for
import cv2

from src.led_detector import LEDDetector, LEDRegion, LEDStatus

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

cameras_config = []
cameras_data = {}
LOG_DIR = "log"

STATE_COLOR_MAP = {
    "off": "#808080",
    "green": "#00FF00",
    "yellow": "#FFFF00",
    "red": "#FF0000",
    "flashing_green": "#008000",
    "flashing_yellow": "#FFA500",
    "flashing_red": "#800000"
}

def load_cameras_config():
    global cameras_config, cameras_data
    try:
        with open('cameras.yaml', 'r') as f:
            config = yaml.safe_load(f)
            cameras_config = config.get('cameras', [])

        # Assicurati che tutte le camere abbiano un campo 'operator'
        for camera in cameras_config:
            if 'operator' not in camera:
                camera['operator'] = 'UNKNOWN'

        for camera in cameras_config:
            machine_id = camera['machine_id']
            cameras_data[machine_id] = {
                'status': {},
                'history': [],
                'detector': LEDDetector(),
                'log_file': None
            }
            cameras_data[machine_id]['log_file'] = open_camera_log(machine_id)

        print(f"Caricate {len(cameras_config)} camere dalla configurazione")
    except Exception as e:
        print(f"Errore caricamento configurazione camere: {e}")
        cameras_config = []

def open_camera_log(machine_id):
    os.makedirs(LOG_DIR, exist_ok=True)
    filename = datetime.now().strftime(f"Log-{machine_id}-%d-%m-%Y.txt")
    filepath = os.path.join(LOG_DIR, filename)
    return open(filepath, "a", encoding="utf-8")

def cleanup_and_exit(signum, frame):
    print(f"\nSegnale {signum} ricevuto, chiudo file log e arresto...")
    for machine_id in cameras_data:
        log_file = cameras_data[machine_id]['log_file']
        if log_file and not log_file.closed:
            log_file.close()
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup_and_exit)
signal.signal(signal.SIGTERM, cleanup_and_exit)

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

def gen_frames_for_camera(machine_id):
    camera_config = next((c for c in cameras_config if c['machine_id'] == machine_id), None)
    if not camera_config:
        return
        
    rtsp_url = camera_config['rtsp_url']
    led_regions = [LEDRegion(r['name'], r['x'], r['y'], r['width'], r['height'], machine_id) 
                   for r in camera_config['led_regions']]
    
    detector = cameras_data[machine_id]['detector']
    log_file = cameras_data[machine_id]['log_file']
    
    with suppress_stderr():
        cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        print(f"Errore: impossibile aprire il flusso RTSP {rtsp_url} per {machine_id}")
        return
        
    while True:
        success, frame = cap.read()
        if not success:
            time.sleep(0.1)
            continue

        detections = detector.detect_multiple_leds(frame, led_regions)
        frame = draw_overlay(frame, detections)

        for det in detections:
            key = f"{machine_id}_{det.region.name}"
            current = det.status.value
            old = cameras_data[machine_id]['status'].get(key)
            
            if old != current:
                cameras_data[machine_id]['status'][key] = current
                
                timestamp = datetime.now()
                time_str = timestamp.strftime("%H:%M:%S")
                
                log_line = f"{machine_id};{old if old else 'None'};{current};{time_str}\n"
                log_file.write(log_line)
                log_file.flush()
                
                print(log_line.strip())

                cameras_data[machine_id]['history'].append({
                    "time": time_str,
                    "message": log_line.strip(),
                    "success": None
                })
                if len(cameras_data[machine_id]['history']) > 10:
                    cameras_data[machine_id]['history'].pop(0)

        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/')
def index():
    cameras_list = "<ul>"
    for camera in cameras_config:
        machine_id = camera['machine_id']
        cameras_list += f'<li><a href="/camera/{machine_id}">{machine_id}</a></li>'
    cameras_list += "</ul>"
    
    html = f"""
    <html><head><title>Shima Monitor</title></head><body>
    <h1>Shima LED Monitor - Sistema Multi-Camera</h1>
    <h2>Camere disponibili:</h2>
    {cameras_list}
    <p><a href="/logs">Visualizza file di log</a></p>
    <p><a href="/camera_status">Visualizza stato tutte le camere</a></p>
    </body></html>
    """
    return render_template_string(html)

@app.route('/camera/<machine_id>')
def camera_detail(machine_id):
    if machine_id not in cameras_data:
        abort(404, "Camera non trovata")
        
    html = f"""
    <html><head><title>{machine_id} - Dettaglio</title></head><body>
    <h1>Camera: {machine_id}</h1>
    <p>Video live:</p>
    <img src="/video_feed/{machine_id}" width="640" height="480" />
    <h2>Ultime notifiche:</h2>
    <ul id="notifications"></ul>
    <p><a href="/">Torna alla home</a></p>
    <script>
    async function fetchNotifications() {{
        const resp = await fetch('/api/notifications/{machine_id}');
        const data = await resp.json();
        const ul = document.getElementById('notifications');
        ul.innerHTML = '';
        data.forEach(item => {{
            const li = document.createElement('li');
            li.textContent = item.time + ': ' + item.message;
            ul.appendChild(li);
        }});
    }}
    setInterval(fetchNotifications, 2000);
    fetchNotifications();
    </script>
    </body></html>
    """
    return render_template_string(html)

@app.route('/video_feed/<machine_id>')
def video_feed(machine_id):
    if machine_id not in cameras_data:
        abort(404, "Camera non trovata")
    return Response(gen_frames_for_camera(machine_id),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/notifications/<machine_id>')
def api_notifications(machine_id):
    if machine_id not in cameras_data:
        abort(404, "Camera non trovata")
    return jsonify(cameras_data[machine_id]['history'])

@app.route('/camera_status')
def camera_status():
    html = f"""
    <html>
      <head>
        <title>Stato Camere</title>
        <meta http-equiv="refresh" content="15">
        <style>
          body {{
            margin: 0;
            padding: 20px;
            font-family: Arial, sans-serif;
            background-color: #222;
            color: white;
          }}
          .grid-container {{
            display: grid;
            grid-template-columns: repeat(10, 1fr);
            grid-template-rows: repeat(6, 1fr);
            gap: 10px;
            height: 90vh;
          }}
          .cell {{
            border: 2px solid #444;
            background-color: #111;
            display: flex;
            justify-content: center;
            align-items: center;
            font-size: 2vw;
            font-weight: bold;
            text-decoration: none;
            cursor: pointer;
            transition: all 0.3s;
          }}
          .cell:hover {{
            background-color: #333;
            transform: scale(1.05);
          }}
        </style>
      </head>
      <body>
        <h1>Stato Camere - Griglia di Monitoraggio</h1>
        <div class="grid-container">
    """
    
    for i in range(60):
        if i < len(cameras_config):
            camera = cameras_config[i]
            machine_id = camera['machine_id']
            
            first_region_key = f"{machine_id}_{camera['led_regions'][0]['name']}"
            last_state = cameras_data[machine_id]['status'].get(first_region_key, 'off').lower()
            color = STATE_COLOR_MAP.get(last_state, "#000000")
            
            html += f'<a href="/camera/{machine_id}" class="cell" style="color: {color};">{machine_id}</a>'
        else:
            html += '<div class="cell"></div>'
    
    html += """
        </div>
      </body>
    </html>
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

@app.route('/operator/<operator_name>')
def operator_status(operator_name):
    filtered_cameras = [cam for cam in cameras_config if cam.get('operator', '').upper() == operator_name.upper()]
    if not filtered_cameras:
        abort(404, description=f"Nessuna camera per operatore {operator_name}")

    return render_template('operator_status.html', operator=operator_name, cameras=filtered_cameras, cameras_data=cameras_data)

def run_flask():
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)

def main():
    load_cameras_config()
    
    if not cameras_config:
        print("Nessuna camera configurata, uscita...")
        return
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("Web interface avviata all'indirizzo http://0.0.0.0:8080")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Interruzione ricevuta, chiudo...")
    finally:
        for machine_id in cameras_data:
            log_file = cameras_data[machine_id]['log_file']
            if log_file and not log_file.closed:
                log_file.close()
        print("File di log chiusi")

if __name__ == '__main__':
    main()
