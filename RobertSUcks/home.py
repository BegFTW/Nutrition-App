from flask import Blueprint, redirect, url_for, session

home_bp = Blueprint("home", __name__, url_prefix="/home")


@home_bp.route("/")
def home():
    # Require login
    if not session.get("user_id"):
        return redirect(url_for("auth.login"))

    user_id = session.get("user_id")
    role = session.get("role")

    logout_url = url_for("auth.logout")
    maps_url = url_for("maps.index")
    food_url = url_for("food.index")
    clock_url = url_for("clock.index")

    # Base nav: Maps is visible to everyone
    nav_buttons = f"""
        <li><a href="{maps_url}">Maps</a></li>
        <li><a href="{food_url}">Add Food</a></li>
        <li><a href="{clock_url}">Clock In/Out</a></li>
    """

    if role == "user":
        # User-specific buttons
        nothing = 0
    else:
        # Trainer-specific "Students" button
        nothing = 1

    nav_buttons += f"""
        <li>
            <form method="post" action="{logout_url}" style="display:inline;">
                <button type="submit">Logout</button>
            </form>
        </li>
    """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>Home</title>
        <link rel="stylesheet" href="/static/styles.css">
    </head>
    <body class="home">

        <!-- Nutrilog header with icon and banner -->
        <div class="hero-section">
            <div class="hero-image">
                <img src="/static/nutrilog_icon.png" alt="NutriLog Icon">
            </div>
        </div>

        <!-- ✅ Moved the blue nav bar BELOW the icon -->
        <nav>
            <ul class="menu">
                {nav_buttons}
            </ul>
        </nav>

        <main>
            <section class="home" style="text-align:center;">
                <h1>Welcome to NutriLog!</h1>
                <h2>Get healthy or go back to playing league you fucking weeb!!</h2>
                <p>You are logged in as <b>{role}</b>: {user_id}</p>
            </section>
        </main>
    </body>
    </html>
    """
