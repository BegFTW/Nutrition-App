from flask import Flask, redirect, url_for
from login_home import auth_bp
from home import home_bp
from food_ml import food_bp
from social_media import social_bp

import threading
import time
import subprocess
import os

app = Flask(__name__, template_folder='templates')
app.secret_key = "dev"

app.register_blueprint(auth_bp)
app.register_blueprint(home_bp)
app.register_blueprint(food_bp)
app.register_blueprint(social_bp)

@app.route("/")
def index():
    return redirect(url_for("auth.login"))


def open_browser():
    time.sleep(2)  # wait for server to start

    url = "http://127.0.0.1:5000"

    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]

    for edge in edge_paths:
        if os.path.exists(edge):
            # 🔥 TRUE fullscreen (kiosk mode)
            subprocess.Popen([edge, "--start-fullscreen", url])
            return

    # fallback
    import webbrowser
    webbrowser.open(url)


if __name__ == "__main__":
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False)