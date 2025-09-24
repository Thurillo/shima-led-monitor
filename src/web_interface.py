from flask import Flask, Response, render_template_string
import cv2
from led_detector import LEDDetector, LEDRegion, LEDStatus

app = Flask(__name__)

RTSP_URL = "rtsp://192.168.21.213:8554"  # Modifica con il tuo RTSP

# Configura le regioni LED
led_regions = [
    LEDRegion("status_main", 120, 80, 40, 40, "SHIMA_001"),
    # Aggiungi altre regioni se vuoi
]

led_detector = LEDDetector()

@app.route('/')
def index():
    html = """
    <html><head><title>Shima Monitor</title></head>
    <body>
    <h1>Benvenuto nel sistema Shima Monitor</h1>
    <p>Per vedere il video, visita: <a href="/video_feed">Stream Video</a></p>
    </body></html>
    """
    return render_template_string(html)

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

def gen_frames(rtsp_url):
    cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        print(f"Errore: impossibile aprire il flusso RTSP {rtsp_url}")
        return
    while True:
        success, frame = cap.read()
        if not success:
            print("Errore: impossibile leggere frame dal flusso")
            break

        # Rileva stato LED nel frame
        detections = led_detector.detect_multiple_leds(frame, led_regions)

        # Disegna overlay
        frame_with_overlay = draw_overlay(frame, detections)

        ret, buffer = cv2.imencode('.jpg', frame_with_overlay)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(RTSP_URL),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
