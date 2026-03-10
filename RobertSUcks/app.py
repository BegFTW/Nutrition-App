from flask import Flask, redirect, url_for
from login_home import auth_bp
from home import home_bp
from clock_in_page import clock_bp
from maps import maps_bp
from food_ml import food_bp

app = Flask(__name__)
app.secret_key = "dev"

app.register_blueprint(auth_bp)
app.register_blueprint(home_bp)
app.register_blueprint(clock_bp) #do we need this?
app.register_blueprint(maps_bp) # do we need this either? useful for references but not much else (idc we can do whatever - Tyler)
app.register_blueprint(food_bp)

@app.route("/")
def index():
    return redirect(url_for("auth.login"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)