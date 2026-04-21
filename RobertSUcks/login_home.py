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
import passlib

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

#setting up config for DB; we should probably move this to another space so our root password isn't open access
DB_CONFIG = {
    "host": "nurilog-db.mysql.database.azure.com",
    "port": 3306,
    "user": "tylercoleroot",
    "password": "Barker123!",
    "database": "NutriLog",
    "ssl_ca": "DigiCertGlobalRootG2.crt.pem",
    "ssl_disabled": False,
}

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

#register endpoint
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    message = None

    if request.method == "POST":
        #gets user attributes from the form
        user_id = request.form.get("user_id", "").strip()
        pass_key = request.form.get("pass_key", "").strip()
        #encrypts the password on the way
        encrypted_passkey = encrypt_password(pass_key)
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()

        #checks for all attributes required for the user creation
        if not all([pass_key, first_name, last_name]):
            message = "All fields are required."
        else:
            try:
                conn = mysql.connector.connect(**DB_CONFIG)
                cur = conn.cursor()

                # Insert new user
                cur.execute(
                    "INSERT INTO Users (user_id, pass_key, first_name, last_name) VALUES (%s, %s, %s, %s)",
                    (user_id, encrypted_passkey, first_name, last_name),
                )
                #commits, then closes the cursor
                conn.commit()
                conn.close()
                #then redirects 
                return redirect(url_for("auth.login"))

            except mysql.connector.Error as e:
                message = f"Database error: {e}"
        

    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
    <title>NutriLog | Create Account</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='styles.css') }}">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body>

<div class="auth-container">
    <div class="auth-card">
        <div class="auth-logo">
            <img src="{{ url_for('static', filename='nutrilog_icon.png') }}">
            <h1>NutriLog</h1>
        </div>

        <h2>Create Your Account</h2>
        <p class="subtitle">Join NutriLog and start tracking your progress today.</p>

        {% if message %}
            <div class="error-msg">{{ message }}</div>
        {% endif %}

        <form method="post" class="auth-form">
            <input name="user_id" placeholder="User ID" required>
            <input name="first_name" placeholder="First Name" required>
            <input name="last_name" placeholder="Last Name" required>
            <input name="pass_key" type="password" placeholder="Password" required>
            <button type="submit" class="primary-btn">Create Account</button>
        </form>

        <div class="auth-links">
            <span>Already have an account?</span>
            <a href="{{ url_for('auth.login') }}">Back to Login</a>
        </div>
    </div>
</div>

</body>
</html>
""", message=message)

# ----------------------
# LOGIN ROUTE
# ----------------------
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    #if there's already a user logged in, sends you home
    if session.get("user_id"):
        return redirect(url_for("home.home"))

    if request.method == "POST":
        #grabs password and user id
        entered_id = request.form.get("user_id", "").strip()
        entered_pass = request.form.get("pass_key", "").strip()
        
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cur_pw = conn.cursor() 
            
            cur_pw.execute("SELECT pass_key FROM Users WHERE user_id = %s", (entered_id,))

            db_password = cur_pw.fetchone()
            db_password = db_password[0]
            db_password = db_password.encode('utf-8')
            #grabs hashed password from the database, then converts it into utf-8 plaintext
            
            cur_pw.close()
            
            #verifies that the password entered and the hashed password in the database match up
            if decrypt_password(entered_pass, db_password): #if they do, it logs you in
                
                cur = conn.cursor(dictionary=True, buffered=True)
                
                #this line could be deleted
                cur.execute("SELECT pass_key FROM Users WHERE user_id = %s", (entered_id,))
                
                # Check Users table
                cur.execute(
                    "SELECT * FROM Users WHERE user_id = %s",
                    (entered_id,)
                )
                user = cur.fetchone()
            conn.close()

            if user:
                #if there is a user as a result of all that, sets session variables to customize experience per user, then redirects them to home
                session["user_id"] = user["user_id"]
                session["first_name"] = user["first_name"]
                session["last_name"] = user["last_name"]
                return redirect(url_for("home.home"))
            #room for different user types
            else:
                error = "Invalid User ID or Password. Please try again."

        except mysql.connector.Error as e:
            error = f"Database error: {e}"
        #catching error for incorrect hashes, which is just incorrect password
        except passlib.exc.UnknownHashError as e:
            error = f"Password Error: Please try again!"
        except Exception as e:
            error = f"An unknown error occurred: {e}"

    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
    <title>NutriLog | Login</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='styles.css') }}">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body>

<div class="auth-container">
    <div class="auth-card">

        <div class="auth-logo">
            <img src="{{ url_for('static', filename='nutrilog_icon.png') }}">
            <h1>NutriLog</h1>
        </div>

        <h2>Welcome Back</h2>
        <p class="subtitle">Sign in to your account to continue.</p>

        {% if error %}
            <div class="error-msg">{{ error }}</div>
        {% endif %}

        <form method="post" class="auth-form">
            <input type="text" name="user_id" placeholder="User ID" required>
            <input type="password" name="pass_key" placeholder="Password" required>
            <button type="submit" class="primary-btn">Login</button>
        </form>

        <div class="auth-links">
            <a href="{{ url_for('auth.register') }}">Create Account</a>
        </div>

    </div>
</div>

</body>
</html>
""", error=error)


#needs to be updated with password hashing. 
@auth_bp.route("/forgot", methods=["GET", "POST"])
def forgot_password():
    message = None
    password = None

    if request.method == "POST":
        #grabs user id
        user_id = request.form.get("user_id", "").strip()

        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cur = conn.cursor(dictionary=True)

            cur.execute("SELECT pass_key FROM Users WHERE user_id = %s", (user_id,))
            user = cur.fetchone()

            

            conn.close()

            if user:
                password = user["pass_key"]
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