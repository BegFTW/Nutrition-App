from flask import (
    Blueprint,
    render_template_string,
    request,
    redirect,
    url_for,
    session,
)
import mysql.connector
from security import encrypt_password, decrypt_password

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "Barker123!",
    "database": "NutriLog",
}


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if session.get("user_id"):
        return redirect(url_for("home.home"))

    if request.method == "POST":
        entered_id = request.form.get("user_id", "").strip()
        entered_pass = request.form.get("pass_key", "").strip()
    
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cur1 = conn.cursor()
            
            #grab the password to compare
            cur1.execute("SELECT pass_key FROM Users WHERE user_id = %s", (entered_id,))
            db_password = cur1.fetchone()
            db_password = db_password[0]
            db_password = db_password.encode('utf-8')
            entered_pass = entered_pass.encode('utf-8')
            
            cur1.close()
            
            if decrypt_password(entered_pass, db_password):
                cur2 = conn.cursor(dictionary=True)
                # Check User
                cur2.execute(
                    "SELECT * FROM Users WHERE user_id = %s",
                    (entered_id,)
                )
                user = cur2.fetchone()

            cur2.close()
            conn.close()

            if user:
            
                session["user_id"] = entered_id
                session["role"] = "user"
                return redirect(url_for("home.home"))
            #room for different user types
            else:
                error = "Invalid ID or Pass Key. Please try again."
        except mysql.connector.Error as e:
            error = f"Database error: {e}"

    return render_template_string(
        """
        <!doctype html>
        <html>
        <head>
            <title>Login</title>
            <link rel="stylesheet" href="{{ url_for('static', filename='styles.css') }}">
        </head>
        <body class="home">
            <div class="hero-section">
                <div class="hero-image">
                    <img src="{{ url_for('static', filename='nutrilog_icon.png') }}" alt="NutriLog Icon">
                </div>
            </div>

            <div align="center">
                <form method="post" align="center" style="margin-top: 20px;">
                    <h2>Log In</h2>
                    {% if error %}
                        <div style="color:red;">{{ error }}</div>
                    {% endif %}
                    <label for="user_id">Student or Instructor ID</label>
                    <input type="text" name="user_id" required><br>
                    <label for="pass_key">Pass Key</label>
                    <input type="password" name="pass_key" required><br>
                    <button type="submit">Login</button>
                </form>

                <div style="margin-top:20px;">
                    <form action="{{ url_for('auth.register') }}" method="get" style="display:inline;">
                        <button type="submit">Create an Account</button>
                    </form>
                    <form action="{{ url_for('auth.forgot_password') }}" method="get" style="display:inline;">
                        <button type="submit">Forgot Password</button>
                    </form>
                </div>
            </div>
        </body>
        </html>
        """,
        error=error,
    )


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    message = None

    if request.method == "POST":
        user_id = request.form.get("user_id", "").strip()
        pass_key = request.form.get("pass_key", "").strip()
        pass_key = encrypt_password(pass_key)
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()

        if not all([user_id, pass_key, first_name, last_name]):
            message = "All fields are required."
        else:
            try:
                conn = mysql.connector.connect(**DB_CONFIG)
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO Users (user_id, pass_key, first_name, last_name) VALUES (%s, %s, %s, %s)",
                    (user_id, pass_key, first_name, last_name),
                )
                conn.commit()
                conn.close()
                return redirect(url_for("auth.login"))
            except mysql.connector.Error as e:
                message = f"Database error: {e}"

    return render_template_string(
        """
        <!doctype html>
        <html>
        <head>
            <title>Create Account</title>
            <link rel="stylesheet" href="{{ url_for('static', filename='styles.css') }}">
        </head>
        <body class="home">
            <div class="hero-section">
                <div class="hero-image">
                    <img src="{{ url_for('static', filename='etsu_icon.png') }}" alt="ETSU Icon">
                </div>
                <div class="banner">
                    <h1>ETSU Nursing Student Tracker</h1>
                </div>
            </div>

            <form method="post" align="center" style="margin-top: 20px;">
                <h2>Create Account</h2>
                {% if message %}
                    <div style="color:red;">{{ message }}</div>
                {% endif %}
                <label for="user_id">User ID</label>
                <input type="text" name="user_id" required><br>
                <label for="pass_key">Pass Key</label>
                <input type="password" name="pass_key" required><br>
                <label for="first_name">First Name</label>
                <input type="text" name="first_name" required><br>
                <label for="last_name">Last Name</label>
                <input type="text" name="last_name" required><br>
                <label for="role">Role</label>
                <select name="role" required>
                    <option value="">Select One</option>
                    <option value="student">Student</option>
                    <option value="instructor">Instructor</option>
                </select><br><br>
                <button type="submit">Create Account</button>
            </form>

            <div align="center" style="margin-top:20px;">
                <a href="{{ url_for('auth.login') }}"><button type="button">Back to Login</button></a>
            </div>
        </body>
        </html>
        """,
        message=message,
    )


@auth_bp.route("/forgot", methods=["GET", "POST"])
def forgot_password():
    message = None
    password = None

    if request.method == "POST":
        user_id = request.form.get("user_id", "").strip()

        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cur = conn.cursor(dictionary=True)

            cur.execute("SELECT pass_key FROM Users WHERE user_id = %s", (user_id,))
            user = cur.fetchone()

            trainer = None
            if not user:
                #replace with trainer if we have? trainer class?
                cur.execute("SELECT pass_key FROM Instructors WHERE instructor_id = %s", (user_id,))
                instructor = cur.fetchone()

            conn.close()

            if user:
                password = user["pass_key"]
            elif instructor:
                password = instructor["pass_key"]
            else:
                message = "User not found."

        except mysql.connector.Error as e:
            message = f"Database error: {e}"

    return render_template_string(
        """
        <!doctype html>
        <html>
        <head>
            <title>Forgot Password</title>
            <link rel="stylesheet" href="{{ url_for('static', filename='styles.css') }}">
        </head>
        <body class="home">
            <div class="hero-section">
                <div class="hero-image">
                    <img src="{{ url_for('static', filename='etsu_icon.png') }}" alt="ETSU Icon">
                </div>
                <div class="banner">
                    <h1>ETSU Nursing Student Tracker</h1>
                </div>
            </div>

            <form method="post" align="center" style="margin-top: 20px;">
                <h2>Forgot Password</h2>
                {% if message %}
                    <div style="color:red;">{{ message }}</div>
                {% endif %}
                {% if password %}
                    <div style="color:green;">Your password is: <b>{{ password }}</b></div>
                {% endif %}
                <label for="user_id">Enter Your ID:</label>
                <input type="text" name="user_id" required><br>
                <button type="submit">Retrieve Password</button>
            </form>

            <div align="center" style="margin-top:20px;">
                <a href="{{ url_for('auth.login') }}"><button type="button">Back to Login</button></a>
            </div>
        </body>
        </html>
        """,
        message=message,
        password=password,
    )


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
