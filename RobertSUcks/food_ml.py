from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
from werkzeug.utils import secure_filename
from PIL import Image
import json
import uuid
from pathlib import Path
import mysql.connector
from mysql.connector import Error
from datetime import datetime
import csv
import re

import torch
import torch.nn as nn
from torchvision import models, transforms

# DB CONFIG (MATCH auth.py)
DB_CONFIG = {
    "host": "nurilog-db.mysql.database.azure.com",
    "port": 3306,
    "user": "tylercoleroot",
    "password": "Barker123!",
    "database": "NutriLog",
    "ssl_ca": "DigiCertGlobalRootG2.crt.pem",
    "ssl_disabled": False,
}

# helper to get a new DB connection (remember to close it!)
def _db_conn():
    return mysql.connector.connect(**DB_CONFIG)

food_bp = Blueprint("food", __name__, url_prefix="/food")

# --------- Model files ----------
BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "food_model_out"
WEIGHTS_PATH = MODEL_DIR / "best_model.pt"
IDX_TO_CLASS_PATH = MODEL_DIR / "idx_to_class.json"

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# --------- Upload dir for persisted previews ----------
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = STATIC_DIR / "food_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}

# --------- Nutrition CSV ----------
# Expected: 3rd column (index 2) is base grams (weight in grams)
# We will scale the rest of the fields to the user's entered grams.
NUTRITION_CSV_PATH = BASE_DIR / "../fixed_nutrition.csv"

# Fields we want to compute & display
NUTRI_FIELDS = ["calories", "protein", "carbohydrates", "fats", "fiber", "sugars", "sodium"]

# Normalizes labels for better matching between model predictions and nutrition CSV entries.
def _norm_label(s: str) -> str:
    """Normalize labels to improve matching between model labels and CSV rows."""
    s = (s or "").strip().lower()
    s = re.sub(r"[_\-]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s

# Helper to safely parse floats, with support for strings with commas and empty values.
def _to_float(x, default=None):
    try:
        if x is None:
            return default
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip()
        if s == "":
            return default
        # remove commas
        s = s.replace(",", "")
        return float(s)
    except Exception:
        return default

# nutrition_cache maps normalized food label -> dict with base_grams and nutrients per that base_grams
_nutrition_cache = None

# Loads the nutrition CSV into _nutrition_cache for fast lookup. Handles both header and no-header formats.
def _load_nutrition_cache():
    """
    Loads fixed_nutrition.csv into a dictionary for fast lookup.
    Supports:
      - Header CSV (recommended): columns include food/label and nutrients
      - No-header CSV: fallback to fixed positions
    Required: base grams is column index 2 (3rd column).
    """

    # Use cached version if already loaded
    global _nutrition_cache
    if _nutrition_cache is not None:
        return _nutrition_cache

    # Create cache if doesn't exist
    cache = {}

    # Check if CSV file exists
    if not NUTRITION_CSV_PATH.exists():
        print(f"[FOOD_ML] WARNING: Nutrition CSV not found at {NUTRITION_CSV_PATH}")
        _nutrition_cache = cache
        return cache

    # Read CSV and populate cache
    try:
        with open(NUTRITION_CSV_PATH, "r", newline="", encoding="utf-8-sig") as f:
            # sniff header
            sample = f.read(4096)
            f.seek(0)

            has_header = csv.Sniffer().has_header(sample)
            reader = csv.reader(f)

            header = None

            # If header exists, normalize it for easier matching. If not, we'll rely on fixed column positions.
            if has_header:
                header = next(reader, None)
                header_norm = [_norm_label(h) for h in (header or [])]
            else:
                header_norm = []

            for row in reader:
                if not row:
                    continue

                # Determine label column:
                # If header exists and any typical label column name appears, use it.
                # Otherwise assume first column is the label.
                label = None
                if has_header and header:
                    # find label-like column
                    label_idx = None
                    for cand in ["label", "food", "food_name", "name", "item"]:
                        if cand in header_norm:
                            label_idx = header_norm.index(cand)
                            break
                    if label_idx is None:
                        label_idx = 0
                    if label_idx < len(row):
                        label = row[label_idx]
                else:
                    label = row[0] if len(row) > 0 else None

                label_n = _norm_label(label)
                if not label_n:
                    continue

                # base grams MUST be 3rd column (index 2)
                base_g = row[2] if len(row) > 2 else None
                base_grams = _to_float(base_g, default=None)
                if not base_grams or base_grams <= 0:
                    # Can't scale without base grams
                    continue

                entry = {"base_grams": float(base_grams)}

                if has_header and header:
                    # map nutrients by header names if present
                    # accepted header synonyms
                    synonyms = {
                        "calories": ["calories", "kcal", "cal", "energy"],
                        "protein": ["protein", "proteins"],
                        "carbohydrates": ["carbohydrates", "carbs", "carbohydrate"],
                        "fats": ["fats", "fat", "lipid", "lipids"],
                        "fiber": ["fiber", "fibre"],
                        "sugars": ["sugars", "sugar"],
                        "sodium": ["sodium", "salt"],
                    }

                    # for each nutrient field, find the first matching column in the header and parse it
                    for field, keys in synonyms.items():
                        idx = None
                        for k in keys:
                            if k in header_norm:
                                idx = header_norm.index(k)
                                break
                        if idx is not None and idx < len(row):
                            entry[field] = _to_float(row[idx], default=None)
                        else:
                            entry[field] = None
                else:
                    # fallback to fixed positional layout (common format)
                    # col0=label, col1=? optional, col2=base grams,
                    # then assume col3..col9 are calories, protein, carbs, fats, fiber, sugars, sodium
                    pos_map = {
                        "calories": 3,
                        "protein": 4,
                        "carbohydrates": 5,
                        "fats": 6,
                        "fiber": 7,
                        "sugars": 8,
                        "sodium": 9,
                    }
                    for field, idx in pos_map.items():
                        entry[field] = _to_float(row[idx], default=None) if len(row) > idx else None

                cache[label_n] = entry

        print(f"[FOOD_ML] Loaded nutrition rows: {len(cache)} from fixed_nutrition.csv")

    # csv reading errors should not crash the app, just result in an empty cache
    except Exception as e:
        print(f"[FOOD_ML] ERROR reading nutrition CSV: {e}")
        cache = {}


    # save cache to global variable for future use
    _nutrition_cache = cache
    return cache

# Given a food label and grams eaten, compute the scaled nutrition based on the cache.
def _compute_scaled_nutrition(label: str, grams: int | None):
    """
    Returns dict containing:
      grams_eaten, base_grams, scale,
      calories, protein, carbohydrates, fats, fiber, sugars, sodium
    Values are scaled to grams. Missing values stay None.
    """

    # if 0 grams or not provided, return early with just the grams_eaten field (which will be None or 0)
    if grams is None:
        return {"grams_eaten": None}

    # parse grams safely, ensuring it's a positive number. If invalid, treat as None.
    grams_f = _to_float(grams, default=None)
    if grams_f is None or grams_f <= 0:
        return {"grams_eaten": None}

    # load nutrition cache and find matching label
    cache = _load_nutrition_cache()
    key = _norm_label(label)
    row = cache.get(key)

    # if no matching label or missing/invalid base grams, we can't compute nutrition, but we can still return the grams eaten
    if not row:
        # no nutrition match found
        return {
            "grams_eaten": int(grams_f),
            "nutrition_found": False,
        }

    # base grams is required to scale nutrition. If missing or invalid, return with nutrition_found=False but still include grams_eaten.
    base_grams = row.get("base_grams")
    if not base_grams or base_grams <= 0:
        return {
            "grams_eaten": int(grams_f),
            "nutrition_found": False,
        }

    scale = grams_f / float(base_grams)

    # build output dict with scaled nutrition values. If specific nutrient is missing in the CSV, it will be None in the output.
    out = {
        "grams_eaten": int(grams_f),
        "base_grams": float(base_grams),
        "scale": float(scale),
        "nutrition_found": True,
    }

    # scale each nutrient if present
    for field in NUTRI_FIELDS:
        v = row.get(field, None)
        v = _to_float(v, default=None)
        out[field] = (v * scale) if v is not None else None

    return out

# Helper to format numbers for display, with safe handling of None and non-numeric values.
def _fmt_num(x, digits=1):
    if x is None:
        return ""
    try:
        return f"{float(x):.{digits}f}"
    except Exception:
        return ""

# Load class mapping from idx_to_class.json, and build a sorted list of class names for display.
with open(IDX_TO_CLASS_PATH, "r") as f:
    idx_to_class = json.load(f)
idx_to_class = {int(k): v for k, v in idx_to_class.items()}
class_names = sorted(set(idx_to_class.values()))
num_classes = len(idx_to_class)

print(f"[FOOD_ML] Loaded {num_classes} classes from idx_to_class.json")
print(f"[FOOD_ML] Sample classes: {class_names[:5]}")

# Build model (must match training)
def build_model(num_classes: int) -> torch.nn.Module:
    model = models.resnet50(weights=None)
    in_features = model.fc.in_features
    model.fc = nn.Linear(in_features, num_classes)
    return model

model = None

def _load_model():
    global model
    if model is not None:
        return model

    print(f"[FOOD_ML] Loading model from {WEIGHTS_PATH}...")
    model = build_model(num_classes).to(DEVICE)
    state = torch.load(WEIGHTS_PATH, map_location=DEVICE)
    model.load_state_dict(state)
    model.eval()
    print("[FOOD_ML] Model loaded successfully")
    return model

# Preprocess (must match your test_tfms)
preprocess = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225],
    ),
])

# function to predict top-k classes for a given PIL image, returning a list of (label, probability) tuples.
@torch.no_grad()
def predict_topk(pil_img: Image.Image, k: int = 3):
    m = _load_model()
    img = pil_img.convert("RGB")
    x = preprocess(img).unsqueeze(0).to(DEVICE)
    logits = m(x)
    probs = torch.softmax(logits, dim=1)[0]
    topk = torch.topk(probs, k=min(k, probs.numel()))

    results = []
    for idx, p in zip(topk.indices.tolist(), topk.values.tolist()):
        label = idx_to_class.get(idx, f"class_{idx}")
        results.append((label, float(p)))
    return results

# helper to check if user is logged in. Used in all routes to protect them.
def _require_login():
    return session.get("user_id") is not None

# helper to get prediction history from session, ensuring it's always a list.
def _session_get_pred_history():
    hist = session.get("predicted_history", [])
    if not isinstance(hist, list):
        hist = []
    return hist

# helper to save uploaded file to static directory and return its URL. Ensures unique filenames and allowed extensions.
def _save_upload_to_static(file_storage) -> str:
    orig_name = secure_filename(file_storage.filename or "upload.jpg")
    ext = Path(orig_name).suffix.lower()
    if ext not in ALLOWED_EXTS:
        ext = ".jpg"

    out_name = f"{uuid.uuid4().hex}_{Path(orig_name).stem}{ext}"
    out_path = UPLOAD_DIR / out_name
    file_storage.save(out_path)

    return url_for("static", filename=f"food_uploads/{out_name}")

# Helper to build navigation buttons HTML. Your template references maps_url, food_url, clock_url, and logout_url which are generated here.
def _build_nav_buttons() -> str:
    logout_url = url_for("auth.logout")
    home_url = url_for("home.home")
    social_url = url_for("social.index")

    nav_buttons = f"""
        <li><a href="{home_url}">Home</a></li>
        <li><a href="{social_url}">Social Media</a></li>

        <li>
            <form method="post" action="{logout_url}" style="display:inline;">
                <button type="submit">Logout</button>
            </form>
        </li>
    """
    return nav_buttons

# parses the meal_items_json field from the database, which can be in various formats (list of strings, list of dicts, JSON string) and normalizes it to a list of dicts with label and grams.
def _parse_items_json(val):
    """
    Returns a list.
    Supports old format: ["pizza", "apple"]
    Supports new format: [{"label":"pizza","grams":180,"calories":...}, ...]
    """

    # if value is None, return empty list
    if val is None:
        return []
    
    # if value is bytes, try to decode it as utf-8 string
    if isinstance(val, (bytes, bytearray)):
        try:
            val = val.decode("utf-8", errors="ignore")
        except Exception:
            return []
        
    #if value is a string, try to parse it as JSON. If parsing fails, return empty list.
    if isinstance(val, str):
        try:
            out = json.loads(val)
            return out if isinstance(out, list) else []
        except Exception:
            return []

    # if value is already a list, return it. Otherwise return empty list.
    if isinstance(val, list):
        return val
    return []

# Helper to normalize meal items into a consistent format. Ensures each item is a dict with at least 'label' and 'grams', and preserves any existing nutrient info if present. Backward compatible with old list-of-strings format.
def _normalize_meal_list(meal):
    """
    Ensure meal is always a list of dicts with:
      label, grams, calories, protein, carbohydrates, fats, fiber, sugars, sodium
    Backward compatible with old list-of-strings.
    """
    if not isinstance(meal, list):
        return []

    # normalize each item in the meal list to ensure it's a dict with the expected fields. If item is a string, convert it to dict with label and None grams. If it's already a dict, ensure it has label and grams, and preserve any existing nutrient info.
    normalized = []
    for it in meal:
        if isinstance(it, str):
            normalized.append({"label": it, "grams": None})
        elif isinstance(it, dict):
            lbl = (it.get("label") or it.get("name") or "").strip()
            grams = it.get("grams", None)

            # safely parse grams to int if possible, otherwise set to None. This handles cases where grams might be a string or invalid value.
            try:
                grams = int(float(grams)) if grams is not None and str(grams).strip() != "" else None
            except Exception:
                grams = None

            # if label is missing or empty, skip this item since it's not valid. We can still keep items with missing grams, but label is essential for display and nutrition lookup.
            if not lbl:
                continue

            item = {"label": lbl, "grams": grams}

            # keep any stored nutrients if present
            for f in NUTRI_FIELDS:
                item[f] = _to_float(it.get(f, None), default=None)

            normalized.append(item)
        else:
            continue

    return normalized

# Helper to parse grams input from the form, ensuring it's a positive integer and within reasonable bounds. If invalid, returns None or a default value.
def _parse_grams_from_request(default_grams=100):
    raw = (request.form.get("grams", "") or "").strip()
    if raw == "":
        return None
    try:
        g = int(float(raw))
    except Exception:
        return default_grams
    if g <= 0:
        return default_grams
    if g > 5000:
        return 5000
    return g

# Helper to apply nutrition info to a meal item dict based on its label and grams. Mutates the item in-place. If nutrition info is not found, sets nutrient fields to None but leaves label and grams intact.
def _apply_nutrition_to_item(item: dict):
    """
    Mutates item in-place: fills calories/protein/carbs/fats/fiber/sugars/sodium
    based on label + grams. If no match, leaves them None.
    """
    label = item.get("label")
    grams = item.get("grams")
    scaled = _compute_scaled_nutrition(label, grams)

    # If nutrition not found, clear fields
    if not scaled.get("nutrition_found"):
        for f in NUTRI_FIELDS:
            item[f] = None
        return item

    for f in NUTRI_FIELDS:
        item[f] = scaled.get(f, None)
    return item

# Helper to fetch saved meals for a user from the Meal_Log table, parse and normalize them, and return a list of meals with their items and nutrition info. Handles various formats of stored meal items and ensures the output is consistent for display.
def _fetch_saved_meals_for_user(user_id: int, limit: int = 25):
    """
    Reads saved meals from Meal_Log for this user.
    Uses key name 'meal_items' (NOT 'items') to avoid Jinja dict method collision.
    """
    conn = None
    cur = None
    saved = []
    try:
        conn = _db_conn()
        cur = conn.cursor(dictionary=True)

        cur.execute(
            """
            SELECT log_id, clock_time_meal, calories_gained, meal_items_json
            FROM Meal_Log
            WHERE user_id = %s
            ORDER BY COALESCE(clock_time_meal, NOW()) DESC, log_id DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        rows = cur.fetchall() or []

        for r in rows:
            dt = r.get("clock_time_meal")
            created_at = dt.strftime("%Y-%m-%d %H:%M:%S") if hasattr(dt, "strftime") else (str(dt) if dt else "")

            raw_items = _parse_items_json(r.get("meal_items_json"))
            norm_items = _normalize_meal_list(raw_items)

            # If older saved rows don't include nutrients, compute them on display
            for it in norm_items:
                if any(it.get(f) is None for f in NUTRI_FIELDS):
                    _apply_nutrition_to_item(it)

            saved.append({
                "log_id": r.get("log_id"),
                "created_at": created_at,
                "calories_gained": r.get("calories_gained"),
                "meal_items": norm_items,
            })

    except Exception as e:
        print(f"[FOOD_ML] ERROR loading saved meals: {e}")
        session["flash_msg"] = f"DB error loading saved meals: {e}"
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

    return saved

# NEW: Group saved meals by day based on their created_at timestamp. This allows the template to display meals grouped by day with a header for each day.
def _group_saved_meals_by_day(saved_meals: list[dict]):
    """
    Input: saved_meals list with 'created_at' like "YYYY-MM-DD HH:MM:SS"
    Output: list of dicts: [{"day":"YYYY-MM-DD","meals":[...]}] sorted newest day first.
    """
    buckets = {}

    for m in (saved_meals or []):
        created_at = (m.get("created_at") or "").strip()
        day = created_at[:10] if len(created_at) >= 10 else "Unknown Date"
        buckets.setdefault(day, []).append(m)

    days_sorted = sorted(buckets.keys(), reverse=True)
    grouped = [{"day": d, "meals": buckets[d]} for d in days_sorted]
    return grouped

# --------- Routes ----------
@food_bp.route("/db_debug", methods=["GET"])
def db_debug():
    if not _require_login():
        return redirect(url_for("auth.login"))

    info = {
        "db_config_database": DB_CONFIG.get("database"),
        "session_user_id": session.get("user_id"),
        "connected_database()": None,
        "meal_log_columns": [],
        "nutrition_csv_path": str(NUTRITION_CSV_PATH),
        "nutrition_csv_exists": NUTRITION_CSV_PATH.exists(),
        "nutrition_rows_loaded": len(_load_nutrition_cache()),
    }

    conn = None
    cur = None
    try:
        conn = _db_conn()
        cur = conn.cursor()

        cur.execute("SELECT DATABASE()")
        row = cur.fetchone()
        info["connected_database()"] = row[0] if row else None

        cur.execute("SHOW COLUMNS FROM Meal_Log")
        cols = cur.fetchall() or []
        info["meal_log_columns"] = [c[0] for c in cols]

    except Exception as e:
        info["error"] = str(e)
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

    return jsonify(info)

# Main page for food logging. Displays current meal items, search form, image upload form, prediction results, and saved meals. Handles various formats of meal items in session and ensures nutrition info is computed for display.
@food_bp.route("/", methods=["GET"])
def index():
    if not _require_login():
        return redirect(url_for("auth.login"))

    meal = _normalize_meal_list(session.get("meal_items", []))
    for it in meal:
        if it.get("grams") is not None and any(it.get(f) is None for f in NUTRI_FIELDS):
            _apply_nutrition_to_item(it)
    session["meal_items"] = meal

    search_query = session.get("last_search_query", "")
    current_image_url = session.get("current_image_url", None)
    current_preds = session.get("current_preds", None)
    history = _session_get_pred_history()

    saved_meals = []
    try:
        user_id = int(session.get("user_id"))
        saved_meals = _fetch_saved_meals_for_user(user_id, limit=25)
    except Exception:
        saved_meals = []

    # NEW: grouped by day
    saved_meals_grouped = _group_saved_meals_by_day(saved_meals)

    # Nav URLs (your template references these)
    food_url = url_for("food.index")
    social_url = url_for("social.index")

    return render_template(
      template_name_or_list="food_ml.jinja2",
      meal=meal,
      search_query=search_query,
      class_names=class_names[:5000],
      current_image_url=current_image_url,
      current_preds=current_preds,
      history=history,
      saved_meals=saved_meals,
      saved_meals_grouped=saved_meals_grouped,  # <-- pass grouped
      fmt_num=_fmt_num,
      food_url=food_url,
      social_url=social_url,
      home_url=url_for("home.home"),
    )

# Route to handle image upload and prediction. Validates login, checks for uploaded file, saves it, runs prediction, stores results in session, and redirects back to index. Also supports AJAX requests by returning JSON responses with appropriate status codes.
@food_bp.route("/predict", methods=["POST"])
def predict():
    if not _require_login():
        if request.headers.get("X-Requested-With") == "fetch":
            return jsonify({"ok": False, "error": "not_logged_in"}), 401
        return redirect(url_for("auth.login"))

    file = request.files.get("image")
    if not file or file.filename == "":
        if request.headers.get("X-Requested-With") == "fetch":
            return jsonify({"ok": False, "error": "no_file"}), 400
        return redirect(url_for("food.index"))

    try:
        image_url = _save_upload_to_static(file)
    except Exception as e:
        print(f"[FOOD_ML] ERROR saving upload: {e}")
        if request.headers.get("X-Requested-With") == "fetch":
            return jsonify({"ok": False, "error": "save_failed"}), 400
        return redirect(url_for("food.index"))

    try:
        rel = image_url.split("/static/", 1)[-1]
        img_path = STATIC_DIR / rel
        pil_img = Image.open(img_path)
    except Exception as e:
        print(f"[FOOD_ML] ERROR reading image: {e}")
        if request.headers.get("X-Requested-With") == "fetch":
            return jsonify({"ok": False, "error": "bad_image"}), 400
        return redirect(url_for("food.index"))

    preds = predict_topk(pil_img, k=3)
    preds_fmt = [(lbl, f"{prob*100:.2f}%") for lbl, prob in preds]

    session["current_image_url"] = image_url
    session["current_preds"] = preds_fmt
    session["last_search_query"] = ""

    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify({"ok": True, "image_url": image_url, "preds": preds_fmt})

    return redirect(url_for("food.index"))

# Route to handle search form submission. Validates login, gets search query, stores it in session, and redirects back to index. The index route will use this query to pre-fill the search box and filter class names for display.
@food_bp.route("/set_search", methods=["POST"])
def set_search():
    if not _require_login():
        return redirect(url_for("auth.login"))

    q = (request.form.get("search", "") or "").strip().lower()
    session["last_search_query"] = q
    return redirect(url_for("food.index"))

# Route to add a food item to the current meal. Validates login, gets chosen label and grams from form, computes nutrition, updates session meal list, and redirects back to index. Also updates prediction history if applicable.
@food_bp.route("/add", methods=["POST"])
def add_food():
    if not _require_login():
        return redirect(url_for("auth.login"))

    chosen = (request.form.get("chosen_label", "") or "").strip()
    grams = _parse_grams_from_request(default_grams=100)

    if chosen:
        meal = _normalize_meal_list(session.get("meal_items", []))

        item = {"label": chosen, "grams": grams}
        _apply_nutrition_to_item(item)

        meal.append(item)
        session["meal_items"] = meal

        current_image_url = session.get("current_image_url", None)
        current_preds = session.get("current_preds", None) or []

        chosen_prob = ""
        for lbl, prob in current_preds:
            if lbl == chosen:
                chosen_prob = prob
                break

        if current_image_url:
            hist = _session_get_pred_history()
            hist.append({
                "image_url": current_image_url,
                "label": chosen,
                "prob": chosen_prob,
                "grams": grams,
                **{f: item.get(f) for f in NUTRI_FIELDS},
            })
            session["predicted_history"] = hist[-30:]

    session["current_image_url"] = None
    session["current_preds"] = None
    session["last_search_query"] = ""
    return redirect(url_for("food.index"))

# Route to remove a meal item by index. Validates login, gets index from form, updates session meal list, and redirects back to index. Ensures index is valid before modifying the meal list.
@food_bp.route("/remove_meal_item", methods=["POST"])
def remove_meal_item():
    if not _require_login():
        return redirect(url_for("auth.login"))

    try:
        idx = int(request.form.get("index", "-1"))
    except ValueError:
        return redirect(url_for("food.index"))

    meal = _normalize_meal_list(session.get("meal_items", []))

    if 0 <= idx < len(meal):
        meal.pop(idx)
        session["meal_items"] = meal

    return redirect(url_for("food.index"))

# Route to edit a meal item by index. Validates login, gets index, new label, and new grams from form, updates the specific meal item in session, and redirects back to index. Recomputes nutrition for the edited item.
@food_bp.route("/edit_meal_item", methods=["POST"])
def edit_meal_item():
    """
    Edit BOTH the label and grams for a meal entry,
    and recompute scaled nutrition.
    """
    if not _require_login():
        return redirect(url_for("auth.login"))

    try:
        idx = int(request.form.get("index", "-1"))
    except ValueError:
        return redirect(url_for("food.index"))

    new_label = (request.form.get("new_label", "") or "").strip()
    new_grams = _parse_grams_from_request(default_grams=100)

    meal = _normalize_meal_list(session.get("meal_items", []))

    if 0 <= idx < len(meal):
        if new_label:
            meal[idx]["label"] = new_label
        meal[idx]["grams"] = new_grams

        _apply_nutrition_to_item(meal[idx])

        session["meal_items"] = meal

    return redirect(url_for("food.index"))

# Route to clear the current meal list in session. Validates login, resets meal_items to an empty list, and redirects back to index.
@food_bp.route("/clear_meal", methods=["POST"])
def clear_meal():
    if not _require_login():
        return redirect(url_for("auth.login"))
    session["meal_items"] = []
    return redirect(url_for("food.index"))

# Route to clear the prediction history in session. Validates login, resets predicted_history to an empty list, and redirects back to index.
@food_bp.route("/clear_history", methods=["POST"])
def clear_history():
    if not _require_login():
        return redirect(url_for("auth.login"))
    session["predicted_history"] = []
    return redirect(url_for("food.index"))

# Route to save the current meal list in session to the Meal_Log table in the database. Validates login, ensures meal list is not empty, computes nutrition for each item, saves as JSON with a timestamp, and redirects back to index with a success or error message.
@food_bp.route("/save_meal", methods=["POST"])
def save_meal():
    """
    Saves current session meal list into Meal_Log.meal_items_json,
    with a timestamp in clock_time_meal.

    Each item saved includes:
      label, grams, calories, protein, carbohydrates, fats, fiber, sugars, sodium
    """
    if not _require_login():
        return redirect(url_for("auth.login"))

    try:
        user_id = int(session.get("user_id"))
    except Exception:
        session["flash_msg"] = f"Save failed: session.user_id is not an integer ({session.get('user_id')})"
        return redirect(url_for("food.index"))

    meal = _normalize_meal_list(session.get("meal_items", []))

    if len(meal) == 0:
        session["flash_msg"] = "Meal is empty — add items first."
        return redirect(url_for("food.index"))

    # ensure nutrition is computed before saving
    for it in meal:
        _apply_nutrition_to_item(it)

    session["meal_items"] = meal

    meal_items_json = json.dumps(meal)
    now_dt = datetime.now()

    conn = None
    cur = None
    try:
        conn = _db_conn()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO Meal_Log (user_id, calories_gained, clock_time_meal, meal_items_json)
            VALUES (%s, %s, %s, %s)
            """,
            (user_id, None, now_dt, meal_items_json),
        )
        conn.commit()

        session["flash_msg"] = f"Meal saved! (log_id={cur.lastrowid})"
        return redirect(url_for("food.index"))

    except Error as e:
        session["flash_msg"] = f"MySQL error saving meal: {e}"
        return redirect(url_for("food.index"))

    except Exception as e:
        session["flash_msg"] = f"Unknown error saving meal: {e}"
        return redirect(url_for("food.index"))

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

