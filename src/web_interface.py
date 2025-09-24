from flask import Flask, Response, render_template_string
import cv2

app = Flask(__name__)

RTSP_URL = "rtsp://admin:password@192.168.1.100:554/mjpeg/1"  # Modifica con il tuo RTSP

@app.route('/')
def index():
    html = """
    <html>
    <head><title>Shima Monitor</title></head>
    <body>
        <h1>Benvenuto nel sistema Shima Monitor</h1>
        <p>Per vedere il video, visita: <a href="/video_feed">Stream Video</a></p>
    </body>
    </html>
    """
    return render_template_string(html)

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
        else:
            ret, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/video_feed')
def video_feed():
    rtsp_url = "rtsp://192.168.21.213:8554"
    return Response(gen_frames(rtsp_url),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
