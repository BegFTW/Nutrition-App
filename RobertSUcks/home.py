from flask import Blueprint, session, redirect, url_for, render_template_string, request
import mysql.connector
from datetime import datetime
import calendar as cal
import json

home_bp = Blueprint("home", __name__, url_prefix="/home")

# =========================
# DB CONFIG (MATCH auth.py)
# =========================
DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "Barker123!",
    "database": "NutriLog",
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
    maps_url = url_for("maps.index")
    food_url = url_for("food.index")
    clock_url = url_for("clock.index")

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

    return render_template_string(
        PAGE_HTML,
        user_id=user_id,
        first_name=first_name,
        last_name=last_name,
        logout_url=logout_url,
        maps_url=maps_url,
        food_url=food_url,
        clock_url=clock_url,
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
    )


PAGE_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
  <title>NutriLog | Dashboard</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='styles.css') }}">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">

  <style>
    .container { max-width: 1100px; margin: 0 auto; padding: 18px; }

    .hero { text-align:center; padding: 18px 10px 8px 10px; }
    .hero h1 { margin: 0; }
    .hero p { margin: 8px 0 0 0; color:#666; }

    .card { border:1px solid #ddd; border-radius:12px; padding:16px; margin:16px auto; background:#fff; }

    .dash-grid { display:grid; grid-template-columns: 1fr; gap: 16px; }

    .calendar-wrap { border:1px solid #eee; border-radius:14px; overflow:hidden; background:#fff; }
    .cal-head {
      display:flex; justify-content:space-between; align-items:center;
      padding: 12px 14px; border-bottom:1px solid #eee; background:#fafafa;
      gap: 10px; flex-wrap: wrap;
    }
    .cal-title { font-weight: 700; font-size: 18px; }
    .cal-nav { display:flex; gap: 10px; align-items:center; }
    .cal-nav a {
      text-decoration:none; border:1px solid #ddd; background:#fff; color:#222;
      padding: 8px 10px; border-radius: 10px; display:inline-block;
    }
    .cal-nav a:hover { background:#f3f3f3; }

    .cal-grid { width:100%; border-collapse: collapse; table-layout: fixed; }
    .cal-grid th {
      background:#fff; padding:10px 6px; font-size: 13px; color:#666;
      border-bottom:1px solid #eee;
    }
    .cal-grid td {
      height: 108px; vertical-align: top; padding: 10px;
      border-top:1px solid #f0f0f0; border-right:1px solid #f0f0f0;
      position: relative;
      background:#fff;
    }
    .cal-grid tr td:last-child { border-right:none; }

    .day-num { font-weight: 700; font-size: 14px; }
    .muted { color:#999; }

    .outside { background:#fcfcfc; color:#aaa; }
    .today {
      outline: 2px solid #333;
      outline-offset: -2px;
      border-radius: 10px;
    }

    .meal-badge {
      margin-top: 10px;
      display:inline-flex;
      align-items:center;
      gap: 8px;
      border:1px solid #ddd;
      border-radius: 999px;
      padding: 6px 10px;
      background:#fafafa;
      cursor:pointer;
      user-select:none;
      font-size: 13px;
    }
    .meal-badge:hover { background:#f0f0f0; }

    .meal-dot {
      width: 8px; height: 8px; border-radius: 999px; background:#333;
      display:inline-block;
    }

    /* Modal */
    .modal-backdrop {
      position:fixed; inset:0;
      background: rgba(0,0,0,0.45);
      display:none;
      align-items:center;
      justify-content:center;
      padding: 18px;
      z-index: 9999;
    }
    .modal {
      width: min(860px, 100%);
      background:#fff;
      border-radius: 16px;
      border:1px solid #eee;
      box-shadow: 0 20px 80px rgba(0,0,0,0.2);
      overflow:hidden;
    }
    .modal-head {
      display:flex; justify-content:space-between; align-items:center;
      padding: 12px 14px;
      background:#fafafa;
      border-bottom: 1px solid #eee;
      gap: 10px;
    }
    .modal-title { font-weight: 800; }
    .modal-close {
      border:1px solid #ddd;
      background:#fff;
      border-radius: 10px;
      padding: 8px 10px;
      cursor:pointer;
    }
    .modal-body { padding: 14px; }

    .meal-list { display:flex; flex-direction:column; gap:10px; }
    .meal-row {
      border:1px solid #eee;
      border-radius: 14px;
      padding: 10px 12px;
      background:#fff;
      display:flex;
      justify-content:space-between;
      gap: 12px;
      flex-wrap: wrap;
      cursor:pointer;
    }
    .meal-row:hover { background:#fafafa; }

    .meal-items { margin-top: 12px; }
    .meal-item {
      border:1px solid #eee;
      border-radius: 12px;
      padding: 10px;
      background:#fff;
      margin-top: 10px;
    }

    .nutri-grid {
      display:grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px 12px;
      margin-top: 10px;
      font-size: 14px;
    }
    .nutri-grid div {
      padding: 6px 8px;
      border: 1px dashed #eee;
      border-radius: 10px;
      background: #fafafa;
    }
    .nutri-grid b { display:inline-block; min-width:120px; }

    /* Flash message */
    .flash { color:#666; }

    /* Sugar tracker */
    .sugar-card { border:1px solid #ddd; border-radius:12px; padding:16px; margin:16px auto; background:#fff; }
    .sugar-header { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:10px; flex-wrap:wrap; gap:8px; }
    .sugar-title { font-weight:700; font-size:16px; }
    .sugar-amount { font-size:22px; font-weight:800; }
    .sugar-limit { color:#999; font-size:14px; }
    .sugar-bar-bg { background:#f0f0f0; border-radius:999px; height:14px; overflow:hidden; margin-bottom:8px; }
    .sugar-bar-fill { height:100%; border-radius:999px; transition:width 0.4s ease; background:#4caf50; }
    .sugar-bar-fill.warn { background:#ff9800; }
    .sugar-bar-fill.over { background:#f44336; }
    .sugar-note { font-size:13px; color:#888; }

  </style>
</head>

<body>
  <nav class="navbar">
    <div class="logo">
      <img src="{{ url_for('static', filename='nutrilog_icon.png') }}" alt="NutriLog">
      <span>NutriLog</span>
    </div>

    <ul class="menu">
      <li>
        <form action="{{ maps_url }}" method="get">
          <button type="submit" class="nav-btn">Maps</button>
        </form>
      </li>

      <li>
        <form action="{{ food_url }}" method="get">
          <button type="submit" class="nav-btn">Add Food</button>
        </form>
      </li>

      <li>
        <form action="{{ clock_url }}" method="get">
          <button type="submit" class="nav-btn">Clock In/Out</button>
        </form>
      </li>

      <li>
        <form action="{{ logout_url }}" method="post">
          <button type="submit" class="nav-btn">Logout</button>
        </form>
      </li>
    </ul>
  </nav>

  <header class="hero">
    <h1>Welcome back, {{ first_name }}!</h1>
    <p>Your personalized nutrition dashboard</p>
  </header>

  <main class="container">

    {% if session.get("flash_msg") %}
      <div class="card">
        <p class="flash">{{ session.get("flash_msg") }}</p>
      </div>
      {% set _ = session.pop("flash_msg") %}
    {% endif %}

    <div class="dash-grid">

      <div class="card">
        <h2>Dashboard Overview</h2>
        <p>You are logged in as:</p>
        <div class="user-badge">
          <strong>User ID:</strong> {{ user_id }}<br>
          <strong>Name:</strong> {{ first_name }} {{ last_name }}
        </div>
      </div>

      <div id="sugarTrackerCard" class="sugar-card" style="display:none;">
        <div class="sugar-header">
          <span class="sugar-title"> Today's Sugar</span>
          <span>
            <span class="sugar-amount" id="sugarToday">0</span>
            <span class="sugar-limit"> g &nbsp;/&nbsp; 50 g recommended</span>
          </span>
        </div>
        <div class="sugar-bar-bg">
          <div class="sugar-bar-fill" id="sugarBar" style="width:0%;"></div>
        </div>
        <div class="sugar-note" id="sugarNote">No meals logged today yet.</div>
      </div>
      
      <div class="calendar-wrap">
        <div class="cal-head">
          <div class="cal-title">{{ month_name }} {{ year }}</div>
          <div class="cal-nav">
            <a href="{{ url_for('home.home', year=prev_y, month=prev_m) }}">&larr; Prev</a>
            <a href="{{ url_for('home.home') }}">Today</a>
            <a href="{{ url_for('home.home', year=next_y, month=next_m) }}">Next &rarr;</a>
          </div>
        </div>

        <table class="cal-grid">
          <thead>
            <tr>
              <th>Sun</th><th>Mon</th><th>Tue</th><th>Wed</th><th>Thu</th><th>Fri</th><th>Sat</th>
            </tr>
          </thead>
          <tbody>
            {% for week in weeks %}
              <tr>
                {% for d in week %}
                  {% set d_key = d.strftime('%Y-%m-%d') %}
                  {% set is_outside = (d.month != month) %}
                  {% set is_today = (d_key == today_key) %}
                  {% set day_meals = meals_by_day.get(d_key, []) %}

                  <td class="{{ 'outside' if is_outside else '' }} {{ 'today' if is_today else '' }}">
                    <div class="day-num">
                      {{ d.day }}
                      {% if is_outside %}
                        <span class="muted">({{ d.strftime('%b') }})</span>
                      {% endif %}
                    </div>

                    {% if day_meals and (not is_outside) %}
                      <div class="meal-badge"
                           onclick="openDay('{{ d_key }}')"
                           title="Click to view meals">
                        <span class="meal-dot"></span>
                        <span><b>{{ day_meals|length }}</b> meal{{ '' if day_meals|length == 1 else 's' }}</span>
                      </div>
                    {% endif %}
                  </td>
                {% endfor %}
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>

    </div>
  </main>

  <!-- Modal -->
  <div id="modalBackdrop" class="modal-backdrop" onclick="closeModal(event)">
    <div class="modal" onclick="event.stopPropagation();">
      <div class="modal-head">
        <div class="modal-title" id="modalTitle">Meals</div>
        <button class="modal-close" onclick="hideModal()">Close</button>
      </div>
      <div class="modal-body">
        <div id="modalContent"></div>
      </div>
    </div>
  </div>

 <script>
  // meals_by_day from Flask
  const MEALS_BY_DAY = {{ meals_by_day|tojson }};

  // --- Sugar tracker ---
  const SUGAR_LIMIT_G = 50;
  const TODAY_KEY = "{{ today_key }}";

  (function initSugarTracker() {
    const todayMeals = MEALS_BY_DAY[TODAY_KEY] || [];
    if (todayMeals.length === 0) return;

    let totalSugar = 0;
    let hasData = false;
    for (const meal of todayMeals) {
      for (const it of (meal.meal_items || [])) {
        if (it.sugars != null) {
          totalSugar += Number(it.sugars) || 0;
          hasData = true;
        }
      }
    }

    if (!hasData) return;

    const card  = document.getElementById("sugarTrackerCard");
    const label = document.getElementById("sugarToday");
    const bar   = document.getElementById("sugarBar");
    const note  = document.getElementById("sugarNote");

    card.style.display = "";
    label.textContent = totalSugar.toFixed(1);

    const pct = Math.min((totalSugar / SUGAR_LIMIT_G) * 100, 100);
    bar.style.width = pct + "%";

    if (totalSugar > SUGAR_LIMIT_G) {
      bar.classList.add("over");
      note.textContent = ` ${(totalSugar - SUGAR_LIMIT_G).toFixed(1)} g over the daily recommended limit.`;
    } else if (totalSugar > SUGAR_LIMIT_G * 0.75) {
      bar.classList.add("warn");
      note.textContent = `Getting close to the daily recommended limit (${SUGAR_LIMIT_G} g).`;
    } else {
      note.textContent = `${(SUGAR_LIMIT_G - totalSugar).toFixed(1)} g remaining for today.`;
    }
  })();

  const backdrop = document.getElementById("modalBackdrop");
  const modalTitle = document.getElementById("modalTitle");
  const modalContent = document.getElementById("modalContent");

  function showModal() {
    backdrop.style.display = "flex";
    document.body.style.overflow = "hidden";
  }

  function hideModal() {
    backdrop.style.display = "none";
    modalContent.innerHTML = "";
    document.body.style.overflow = "";
  }

  function closeModal(e) {
    hideModal();
  }

  function escClose(e) {
    if (e.key === "Escape") hideModal();
  }
  document.addEventListener("keydown", escClose);

  function safe(x) {
    return (x === null || x === undefined) ? "" : String(x);
  }

  function toNum(x) {
    const n = Number(x);
    return Number.isFinite(n) ? n : 0;
  }

  function fmtNum(x, digits=1) {
    if (x === null || x === undefined || x === "") return "";
    const n = Number(x);
    if (Number.isNaN(n)) return "";
    return n.toFixed(digits);
  }

  // ---- NEW: totals helpers ----
  function computeTotalsFromItems(items) {
    const totals = {
      calories: 0,
      protein: 0,
      carbohydrates: 0,
      fats: 0,
      fiber: 0,
      sugars: 0,
      sodium: 0,
      hasAny: false,
    };

    if (!Array.isArray(items)) return totals;

    for (const it of items) {
      // if any numeric exists we consider "hasAny"
      const cals = toNum(it?.calories);
      const p = toNum(it?.protein);
      const carbs = toNum(it?.carbohydrates);
      const f = toNum(it?.fats);
      const fib = toNum(it?.fiber);
      const sug = toNum(it?.sugars);
      const sod = toNum(it?.sodium);

      // detect if this item has any meaningful nutrition fields present
      const anyPresent =
        (it && (it.calories != null || it.protein != null || it.carbohydrates != null ||
               it.fats != null || it.fiber != null || it.sugars != null || it.sodium != null));

      if (anyPresent) totals.hasAny = true;

      totals.calories += cals;
      totals.protein += p;
      totals.carbohydrates += carbs;
      totals.fats += f;
      totals.fiber += fib;
      totals.sugars += sug;
      totals.sodium += sod;
    }

    return totals;
  }

  function computeMealTotals(meal) {
    const items = meal?.meal_items || [];
    return computeTotalsFromItems(items);
  }

  function computeDayTotals(meals) {
    const totals = {
      calories: 0,
      protein: 0,
      carbohydrates: 0,
      fats: 0,
      fiber: 0,
      sugars: 0,
      sodium: 0,
      hasAny: false,
    };

    if (!Array.isArray(meals)) return totals;

    for (const m of meals) {
      const t = computeMealTotals(m);
      totals.calories += t.calories;
      totals.protein += t.protein;
      totals.carbohydrates += t.carbohydrates;
      totals.fats += t.fats;
      totals.fiber += t.fiber;
      totals.sugars += t.sugars;
      totals.sodium += t.sodium;
      if (t.hasAny) totals.hasAny = true;
    }

    return totals;
  }

  function renderTotalsCard(title, totals) {
    // If no nutrition exists in stored items, show a friendly note
    if (!totals?.hasAny) {
      return `
        <div style="border:1px solid #eee; border-radius:14px; padding:12px; background:#fafafa; margin-bottom:12px;">
          <div style="font-weight:800; margin-bottom:6px;">${safe(title)}</div>
          <div class="muted">(No nutrition totals available for these saved meals — older meals may not have nutrition fields saved.)</div>
        </div>
      `;
    }

    return `
      <div style="border:1px solid #eee; border-radius:14px; padding:12px; background:#fafafa; margin-bottom:12px;">
        <div style="font-weight:800; margin-bottom:8px;">${safe(title)}</div>
        <div class="nutri-grid">
          <div><b>Calories</b> ${Math.round(totals.calories)}</div>
          <div><b>Protein (g)</b> ${fmtNum(totals.protein, 1)}</div>
          <div><b>Carbs (g)</b> ${fmtNum(totals.carbohydrates, 1)}</div>
          <div><b>Fats (g)</b> ${fmtNum(totals.fats, 1)}</div>
          <div><b>Fiber (g)</b> ${fmtNum(totals.fiber, 1)}</div>
          <div style="border-color:${totals.sugars > 50 ? '#f44336' : totals.sugars > 37.5 ? '#ff9800' : '#eee'}; background:${totals.sugars > 50 ? '#fff5f5' : totals.sugars > 37.5 ? '#fff8f0' : '#fafafa'};">
            <b> Sugars (g)</b> ${fmtNum(totals.sugars, 1)}${totals.sugars > 50 ? ' ' : ''}
          </div>
          <div><b>Sodium (mg)</b> ${Math.round(totals.sodium)}</div>
        </div>
      </div>
    `;
  }

  function renderMealItems(items) {
    if (!Array.isArray(items) || items.length === 0) {
      return `<div class="muted">(No items found in this meal)</div>`;
    }

    let html = `<div class="meal-items">`;
    items.forEach((it) => {
      const label = safe(it.label || it.name || "Item");
      const grams = (it.grams != null) ? `${it.grams} g` : "";

      const calories = (it.calories != null) ? fmtNum(it.calories, 0) : "";
      const protein  = (it.protein != null) ? fmtNum(it.protein, 1) : "";
      const carbs    = (it.carbohydrates != null) ? fmtNum(it.carbohydrates, 1) : "";
      const fats     = (it.fats != null) ? fmtNum(it.fats, 1) : "";
      const fiber    = (it.fiber != null) ? fmtNum(it.fiber, 1) : "";
      const sugars   = (it.sugars != null) ? fmtNum(it.sugars, 1) : "";
      const sodium   = (it.sodium != null) ? fmtNum(it.sodium, 0) : "";

      html += `
        <div class="meal-item">
          <div style="display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap;">
            <div><b>${label}</b> <span class="muted">${grams ? "— " + grams : ""}</span></div>
            <div class="muted">${calories ? calories + " cal" : ""}</div>
          </div>

          <div class="nutri-grid">
            <div><b>Protein (g)</b> ${protein}</div>
            <div><b>Carbs (g)</b> ${carbs}</div>
            <div><b>Fats (g)</b> ${fats}</div>
            <div><b>Fiber (g)</b> ${fiber}</div>
            <div><b>Sugars (g)</b> ${sugars}</div>
            <div><b>Sodium (mg)</b> ${sodium}</div>
          </div>
        </div>
      `;
    });

    html += `</div>`;
    return html;
  }

  // ---- UPDATED: first popup includes DAILY TOTALS + per-meal totals in list ----
  function openDay(dayKey) {
    const meals = MEALS_BY_DAY[dayKey] || [];
    modalTitle.textContent = `Meals on ${dayKey}`;

    if (!meals.length) {
      modalContent.innerHTML = `<div class="muted">No meals saved for this day.</div>`;
      showModal();
      return;
    }

    const dayTotals = computeDayTotals(meals);

    let html = "";
    html += renderTotalsCard("Daily Summary (all meals)", dayTotals);

    html += `<div class="meal-list">`;
    meals.forEach((m, idx) => {
      const created = safe(m.created_at);
      const logId = safe(m.log_id);

      const mt = computeMealTotals(m);
      const mealSummaryLine = mt.hasAny
        ? `<div class="muted">${Math.round(mt.calories)} cal • P ${fmtNum(mt.protein,1)}g • C ${fmtNum(mt.carbohydrates,1)}g • F ${fmtNum(mt.fats,1)}g</div>`
        : `<div class="muted">(No nutrition totals stored)</div>`;

      html += `
        <div class="meal-row" onclick="openMeal('${dayKey}', ${idx})">
          <div>
            <div><b>Meal #${logId}</b></div>
            <div class="muted">${created}</div>
            ${mealSummaryLine}
          </div>
          <div class="muted">Click to view</div>
        </div>
      `;
    });
    html += `</div>`;

    modalContent.innerHTML = html;
    showModal();
  }

  // ---- UPDATED: meal popup includes MEAL TOTALS before items ----
  function openMeal(dayKey, index) {
    const meals = MEALS_BY_DAY[dayKey] || [];
    const m = meals[index];
    if (!m) return;

    const created = safe(m.created_at);
    const logId = safe(m.log_id);

    modalTitle.textContent = `Meal #${logId} (${dayKey})`;

    const items = m.meal_items || [];
    const mealTotals = computeTotalsFromItems(items);

    let html = `
      <div style="display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap;">
        <div><b>Saved:</b> ${created}</div>
        <button class="modal-close" onclick="openDay('${dayKey}')">Back to day</button>
      </div>
      <hr style="border:none; border-top:1px solid #eee; margin: 12px 0;">
    `;

    html += renderTotalsCard("Meal Total", mealTotals);
    html += renderMealItems(items);

    modalContent.innerHTML = html;
  }
</script>

</body>
</html>
"""