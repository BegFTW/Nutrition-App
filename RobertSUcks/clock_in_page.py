from flask import Blueprint, render_template_string, redirect, url_for, session
import mysql.connector
from datetime import datetime

clock_bp = Blueprint("clock", __name__, url_prefix="/clock")

# Database connection
DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "Barker123!",
    "database": "NutriLog",
}


def get_activity(student_id):
    """Get the most recent Activity_Log row for this student."""
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT log_id, student_id, clock_in_time, total_time, latitude, longitude
        FROM Activity_Log
        WHERE student_id = %s
        ORDER BY log_id DESC
        LIMIT 1
        """,
        (student_id,),
    )
    row = cur.fetchone()
    conn.close()
    return row


def insert_initial_activity(student_id):
    """Create an Activity_Log row with total_time = 0 and no clock_in_time."""
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO Activity_Log (student_id, clock_in_time, total_time, latitude, longitude)
        VALUES (%s, NULL, 0, NULL, NULL)
        """,
        (student_id,),
    )
    conn.commit()
    conn.close()


def update_activity(log_id, clock_in_time=None, total_time=None):
    """Update clock_in_time and/or total_time for a given log row."""
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor()

    fields = []
    values = []

    if clock_in_time is not None:
        fields.append("clock_in_time = %s")
        values.append(clock_in_time)
    elif clock_in_time is None:
        # explicitly set to NULL
        fields.append("clock_in_time = NULL")

    if total_time is not None:
        fields.append("total_time = %s")
        values.append(total_time)

    if not fields:
        conn.close()
        return

    values.append(log_id)

    query = f"""
        UPDATE Activity_Log
        SET {", ".join(fields)}
        WHERE log_id = %s
    """

    cur.execute(query, tuple(values))
    conn.commit()
    conn.close()


@clock_bp.route("/", methods=["GET"])
def index():
    """Main clock page: show current status + Clock In/Out button."""
    student_id = session.get("user_id")
    role = session.get("role")

    if not student_id:
        return redirect(url_for("auth.login"))

    # Only students should see this page
    if role != "student":
        return redirect(url_for("home.home"))

    activity = get_activity(student_id)
    if not activity:
        insert_initial_activity(student_id)
        activity = get_activity(student_id)

    clock_in_time = activity["clock_in_time"]
    total_time = activity.get("total_time") or 0

    # Decide which button to show
    clocked_in = clock_in_time is not None

    # Convert seconds to h:m:s
    hours = total_time // 3600
    minutes = (total_time % 3600) // 60
    seconds = total_time % 60

    home_url = url_for("home.home")
    maps_url = url_for("maps.index")
    food_url = url_for("food.index")
    logout_url = url_for("auth.logout")

    return render_template_string(
        """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Clock In/Out</title>
            <link rel="stylesheet" href="{{ url_for('static', filename='styles.css') }}">
        </head>
        <body class="home">

            <!-- ✅ ETSU header with icon + banner -->
            <div class="hero-section">
                <div class="hero-image">
                    <img src="{{ url_for('static', filename='nutrilog_icon.png') }}" alt="NutriLog Icon">
                </div>
            </div>

            <nav>
                <ul class="menu">
                    <li><a href="{{ home_url }}">Home</a></li>
                    <li><a href="{{ maps_url }}">Maps</a></li>
                    <li><a href="{{ food_url }}">Add Food</a></li>
                    <li>
                        <form method="post" action="{{ logout_url }}" style="display:inline;">
                            <button type="submit">Logout</button>
                        </form>
                    </li>
                </ul>
            </nav>

            <main>
                <section class="home">
                    <h1>Clock In / Out</h1>
                    <p><b>Student ID:</b> {{ student_id }}</p>
                    <p><b>Last Clock In Time:</b> {{ clock_in_time if clock_in_time else 'Not clocked in' }}</p>
                    <p><b>Total Time Worked:</b> {{ hours }}h {{ minutes }}m {{ seconds }}s</p>

                    {% if clocked_in %}
                        <form method="post" action="{{ url_for('clock.clock_out') }}">
                            <button type="submit">Clock Out</button>
                        </form>
                    {% else %}
                        <form method="post" action="{{ url_for('clock.clock_in') }}">
                            <button type="submit">Clock In</button>
                        </form>
                    {% endif %}
                </section>
            </main>
        </body>
        </html>
        """,
        student_id=student_id,
        clock_in_time=clock_in_time,
        clocked_in=clocked_in,
        hours=hours,
        minutes=minutes,
        seconds=seconds,
        home_url=home_url,
        maps_url=maps_url,
        food_url=food_url,
        logout_url=logout_url,
    )


@clock_bp.route("/clock-in", methods=["POST"])
def clock_in():
    student_id = session.get("user_id")
    role = session.get("role")

    if not student_id:
        return redirect(url_for("auth.login"))

    if role != "student":
        return redirect(url_for("home.home"))

    activity = get_activity(student_id)
    if not activity:
        insert_initial_activity(student_id)
        activity = get_activity(student_id)

    if activity["clock_in_time"] is None:
        now = datetime.now()
        update_activity(activity["log_id"], clock_in_time=now)

    return redirect(url_for("clock.index"))


@clock_bp.route("/clock-out", methods=["POST"])
def clock_out():
    student_id = session.get("user_id")
    role = session.get("role")

    if not student_id:
        return redirect(url_for("auth.login"))

    if role != "student":
        return redirect(url_for("home.home"))

    activity = get_activity(student_id)
    if not activity:
        return redirect(url_for("clock.index"))

    clock_in_time = activity["clock_in_time"]
    total_time = activity.get("total_time") or 0

    if clock_in_time is not None:
        now = datetime.now()

        if isinstance(clock_in_time, datetime):
            elapsed = int((now - clock_in_time).total_seconds())
        else:
            parsed = datetime.fromisoformat(str(clock_in_time))
            elapsed = int((now - parsed).total_seconds())

        if elapsed < 0:
            elapsed = 0

        new_total = total_time + elapsed

        update_activity(
            activity["log_id"],
            clock_in_time=None,
            total_time=new_total,
        )

    return redirect(url_for("clock.index"))
