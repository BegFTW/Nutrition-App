from flask import Blueprint, render_template, redirect, url_for, session, request, jsonify
import mysql.connector

maps_bp = Blueprint("maps", __name__, url_prefix="/maps")

DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "Barker123!",
    "database": "NutriLog",
}


def get_student_initials(student_id):
    initials = "ST"
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT first_name, last_name
            FROM Students
            WHERE student_id = %s
            """,
            (student_id,),
        )
        row = cur.fetchone()
        conn.close()
    except mysql.connector.Error as e:
        print("DB error in get_student_initials:", e)
        row = None

    if row and row[0] and row[1]:
        first, last = row
        initials = (first[0] + last[0]).upper()

    return initials


@maps_bp.route("/", methods=["GET"])
def index():
    if not session.get("user_id"):
        return redirect(url_for("auth.login"))

    user_id = session.get("user_id")
    role = session.get("role")

    if role == "student":
        initials = get_student_initials(user_id)
        return render_template(
            "map.html",
            user_id=user_id,
            role=role,
            initials=initials,
        )

    if role == "instructor":
        return render_template(
            "instructor_map.html",
            user_id=user_id,
            role=role,
        )

    return redirect(url_for("home.home"))


@maps_bp.route("/update_location", methods=["POST"])
def update_location():
    if not session.get("user_id"):
        return jsonify({"status": "error", "message": "Not logged in"}), 401

    student_id = session.get("user_id")
    data = request.get_json() or {}
    lat = data.get("latitude")
    lng = data.get("longitude")

    if lat is None or lng is None:
        return jsonify({"status": "error", "message": "Missing coordinates"}), 400

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT log_id
            FROM Activity_Log
            WHERE student_id = %s
            ORDER BY log_id DESC
            LIMIT 1
            """,
            (student_id,),
        )
        row = cur.fetchone()

        cur = conn.cursor()
        if row:
            cur.execute(
                """
                UPDATE Activity_Log
                SET latitude = %s,
                    longitude = %s
                WHERE log_id = %s
                """,
                (lat, lng, row["log_id"]),
            )
        else:
            cur.execute(
                """
                INSERT INTO Activity_Log (student_id, clock_in_time, total_time, latitude, longitude)
                VALUES (%s, NULL, 0, %s, %s)
                """,
                (student_id, lat, lng),
            )

        conn.commit()
        conn.close()

    except mysql.connector.Error as e:
        print("DB error in update_location:", e)
        return jsonify({"status": "error", "message": "DB error"}), 500

    return jsonify({"status": "ok"})


@maps_bp.route("/active_students", methods=["GET"])
def active_students():
    if not session.get("user_id"):
        return jsonify({"status": "error", "message": "Not logged in"}), 401

    if session.get("role") != "instructor":
        return jsonify({"status": "error", "message": "Forbidden"}), 403

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT s.student_id,
                   s.first_name,
                   s.last_name,
                   a.latitude,
                   a.longitude
            FROM Students s
            JOIN Activity_Log a ON s.student_id = a.student_id
            WHERE a.latitude IS NOT NULL
              AND a.longitude IS NOT NULL
              AND a.log_id = (
                SELECT MAX(a2.log_id)
                FROM Activity_Log a2
                WHERE a2.student_id = s.student_id
              )
            """
        )
        rows = cur.fetchall()
        conn.close()
    except mysql.connector.Error as e:
        print("DB error in active_students:", e)
        return jsonify({"status": "error", "message": "DB error"}), 500

    students = []
    for row in rows:
        first = row["first_name"] or ""
        last = row["last_name"] or ""
        initials = (first[:1] + last[:1]).upper() if (first or last) else "ST"

        students.append(
            {
                "student_id": row["student_id"],
                "initials": initials,
                "lat": float(row["latitude"]),
                "lng": float(row["longitude"]),
            }
        )

    return jsonify({"status": "ok", "students": students})