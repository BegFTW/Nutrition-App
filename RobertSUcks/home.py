from flask import Blueprint, session, redirect, url_for, render_template, request
import mysql.connector
from datetime import datetime
import calendar as cal
import json

home_bp = Blueprint("home", __name__, url_prefix="/home")

# =========================
# DB CONFIG (MATCH auth.py)
# =========================
DB_CONFIG = {
    "host": "nurilog-db.mysql.database.azure.com",
    "port": 3306,
    "user": "tylercoleroot",
    "password": "Barker123!",
    "database": "NutriLog",
    "ssl_ca": "DigiCertGlobalRootG2.crt.pem",
    "ssl_disabled": False,
}

def _db_conn():
    return mysql.connector.connect(**DB_CONFIG)

def _parse_items_json(val):
    """Meal_Log.meal_items_json -> list"""
    if val is None:
        return []
    if isinstance(val, (bytes, bytearray)):
        try:
            val = val.decode("utf-8", errors="ignore")
        except Exception:
            return []
    if isinstance(val, str):
        try:
            out = json.loads(val)
            return out if isinstance(out, list) else []
        except Exception:
            return []
    if isinstance(val, list):
        return val
    return []

def _fetch_meals_for_month(user_id: int, year: int, month: int):
    """
    Returns dict keyed by 'YYYY-MM-DD' => list of meals for that date
    Each meal: {log_id, created_at, meal_items:[...]}
    """
    conn = None
    cur = None
    out = {}

    # month boundaries
    start_dt = datetime(year, month, 1, 0, 0, 0)
    if month == 12:
        end_dt = datetime(year + 1, 1, 1, 0, 0, 0)
    else:
        end_dt = datetime(year, month + 1, 1, 0, 0, 0)

    try:
        conn = _db_conn()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT log_id, clock_time_meal, meal_items_json
            FROM Meal_Log
            WHERE user_id = %s
              AND clock_time_meal >= %s
              AND clock_time_meal < %s
            ORDER BY clock_time_meal DESC, log_id DESC
            """,
            (user_id, start_dt, end_dt),
        )
        rows = cur.fetchall() or []

        for r in rows:
            dt = r.get("clock_time_meal")
            if not dt:
                continue

            day_key = dt.strftime("%Y-%m-%d")
            created_at = dt.strftime("%Y-%m-%d %H:%M:%S")
            items = _parse_items_json(r.get("meal_items_json"))

            meal_obj = {
                "log_id": r.get("log_id"),
                "created_at": created_at,
                "meal_items": items,
            }

            out.setdefault(day_key, []).append(meal_obj)

    except Exception as e:
        # Don’t hard-crash the page; show empty calendar + message
        session["flash_msg"] = f"DB error loading meals for calendar: {e}"
        out = {}
    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass

    return out

def _month_nav(year: int, month: int):
    """Return (prev_year, prev_month, next_year, next_month)."""
    if month == 1:
        prev_y, prev_m = year - 1, 12
    else:
        prev_y, prev_m = year, month - 1

    if month == 12:
        next_y, next_m = year + 1, 1
    else:
        next_y, next_m = year, month + 1

    return prev_y, prev_m, next_y, next_m


@home_bp.route("/")
def home():
    if not session.get("user_id"):
        return redirect(url_for("auth.login"))

    user_id = int(session.get("user_id"))
    first_name = session.get("first_name", "User")
    last_name = session.get("last_name", "")

    # Nav URLs
    logout_url = url_for("auth.logout")
    food_url = url_for("food.index")
    social_url = url_for("social.index")

    # Calendar month selection
    now = datetime.now()
    year = request.args.get("year", type=int) or now.year
    month = request.args.get("month", type=int) or now.month
    if month < 1:
        month = 1
    if month > 12:
        month = 12

    # Pull meals for this month
    meals_by_day = _fetch_meals_for_month(user_id, year, month)

    # Build calendar grid (weeks)
    c = cal.Calendar(firstweekday=6)  # Sunday=6 for classic US layout
    month_days = list(c.itermonthdates(year, month))

    # chunk into weeks of 7
    weeks = [month_days[i:i+7] for i in range(0, len(month_days), 7)]

    # Month nav
    prev_y, prev_m, next_y, next_m = _month_nav(year, month)

    month_name = cal.month_name[month]
    today_key = now.strftime("%Y-%m-%d")
    
    return render_template(
        template_name_or_list="index.jinja2",
        user_id=user_id,
        first_name=first_name,
        last_name=last_name,
        logout_url=logout_url,
        food_url=food_url,
        year=year,
        month=month,
        month_name=month_name,
        weeks=weeks,
        meals_by_day=meals_by_day,
        prev_y=prev_y,
        prev_m=prev_m,
        next_y=next_y,
        next_m=next_m,
        today_key=today_key,
        social_url=social_url,
    )


