from flask import Flask, Response, render_template_string

app = Flask(__name__)

@app.route('/')
def index():
    # Puoi personalizzare con HTML o redirect
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

@app.route('/video_feed')
def video_feed():
    rtsp_url = "rtsp://192.168.21.213:8554"
    return Response(gen_frames(rtsp_url),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
