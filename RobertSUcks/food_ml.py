from flask import Blueprint, render_template_string, request, redirect, url_for, session, jsonify
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


def _norm_label(s: str) -> str:
    """Normalize labels to improve matching between model labels and CSV rows."""
    s = (s or "").strip().lower()
    s = re.sub(r"[_\-]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


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


def _load_nutrition_cache():
    """
    Loads fixed_nutrition.csv into a dictionary for fast lookup.
    Supports:
      - Header CSV (recommended): columns include food/label and nutrients
      - No-header CSV: fallback to fixed positions
    Required: base grams is column index 2 (3rd column).
    """
    global _nutrition_cache
    if _nutrition_cache is not None:
        return _nutrition_cache

    cache = {}
    if not NUTRITION_CSV_PATH.exists():
        print(f"[FOOD_ML] WARNING: Nutrition CSV not found at {NUTRITION_CSV_PATH}")
        _nutrition_cache = cache
        return cache

    try:
        with open(NUTRITION_CSV_PATH, "r", newline="", encoding="utf-8-sig") as f:
            # sniff header
            sample = f.read(4096)
            f.seek(0)

            has_header = csv.Sniffer().has_header(sample)
            reader = csv.reader(f)

            header = None
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
    except Exception as e:
        print(f"[FOOD_ML] ERROR reading nutrition CSV: {e}")
        cache = {}

    _nutrition_cache = cache
    return cache


def _compute_scaled_nutrition(label: str, grams: int | None):
    """
    Returns dict containing:
      grams_eaten, base_grams, scale,
      calories, protein, carbohydrates, fats, fiber, sugars, sodium
    Values are scaled to grams. Missing values stay None.
    """
    if grams is None:
        return {"grams_eaten": None}

    grams_f = _to_float(grams, default=None)
    if grams_f is None or grams_f <= 0:
        return {"grams_eaten": None}

    cache = _load_nutrition_cache()
    key = _norm_label(label)
    row = cache.get(key)

    if not row:
        # no nutrition match found
        return {
            "grams_eaten": int(grams_f),
            "nutrition_found": False,
        }

    base_grams = row.get("base_grams")
    if not base_grams or base_grams <= 0:
        return {
            "grams_eaten": int(grams_f),
            "nutrition_found": False,
        }

    scale = grams_f / float(base_grams)

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


def _fmt_num(x, digits=1):
    if x is None:
        return ""
    try:
        # prefer 0 decimal for calories & sodium if large, otherwise 1 digit
        return f"{float(x):.{digits}f}"
    except Exception:
        return ""


# --------- Load class mapping ----------
with open(IDX_TO_CLASS_PATH, "r") as f:
    idx_to_class = json.load(f)
idx_to_class = {int(k): v for k, v in idx_to_class.items()}
class_names = sorted(set(idx_to_class.values()))
num_classes = len(idx_to_class)

print(f"[FOOD_ML] Loaded {num_classes} classes from idx_to_class.json")
print(f"[FOOD_ML] Sample classes: {class_names[:5]}")


# --------- Build model (must match training) ----------
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


# --------- Preprocess (must match your test_tfms) ----------
preprocess = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225],
    ),
])


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


def _require_login():
    return session.get("user_id") is not None


def _session_get_pred_history():
    hist = session.get("predicted_history", [])
    if not isinstance(hist, list):
        hist = []
    return hist


def _save_upload_to_static(file_storage) -> str:
    orig_name = secure_filename(file_storage.filename or "upload.jpg")
    ext = Path(orig_name).suffix.lower()
    if ext not in ALLOWED_EXTS:
        ext = ".jpg"

    out_name = f"{uuid.uuid4().hex}_{Path(orig_name).stem}{ext}"
    out_path = UPLOAD_DIR / out_name
    file_storage.save(out_path)

    return url_for("static", filename=f"food_uploads/{out_name}")


def _build_nav_buttons() -> str:
    logout_url = url_for("auth.logout")
    maps_url = url_for("maps.index")
    home_url = url_for("home.home")
    clock_url = url_for("clock.index")

    nav_buttons = f"""
        <li><a href="{home_url}">Home</a></li>
        <li><a href="{maps_url}">Maps</a></li>
        <li><a href="{clock_url}">Clock In/Out</a></li>

        <li>
            <form method="post" action="{logout_url}" style="display:inline;">
                <button type="submit">Logout</button>
            </form>
        </li>
    """
    return nav_buttons


def _parse_items_json(val):
    """
    Returns a list.
    Supports old format: ["pizza", "apple"]
    Supports new format: [{"label":"pizza","grams":180,"calories":...}, ...]
    """
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


def _normalize_meal_list(meal):
    """
    Ensure meal is always a list of dicts with:
      label, grams, calories, protein, carbohydrates, fats, fiber, sugars, sodium
    Backward compatible with old list-of-strings.
    """
    if not isinstance(meal, list):
        return []

    normalized = []
    for it in meal:
        if isinstance(it, str):
            normalized.append({"label": it, "grams": None})
        elif isinstance(it, dict):
            lbl = (it.get("label") or it.get("name") or "").strip()
            grams = it.get("grams", None)
            try:
                grams = int(float(grams)) if grams is not None and str(grams).strip() != "" else None
            except Exception:
                grams = None

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
                # only compute if at least one field missing
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


@food_bp.route("/", methods=["GET"])
def index():
    if not _require_login():
        return redirect(url_for("auth.login"))

    meal = _normalize_meal_list(session.get("meal_items", []))
    # compute nutrition for items that don't have it yet
    for it in meal:
        if it.get("grams") is not None and any(it.get(f) is None for f in NUTRI_FIELDS):
            _apply_nutrition_to_item(it)

    session["meal_items"] = meal

    search_query = session.get("last_search_query", "")
    current_image_url = session.get("current_image_url", None)
    current_preds = session.get("current_preds", None)
    history = _session_get_pred_history()
    nav_buttons = _build_nav_buttons()

    saved_meals = []
    try:
        user_id = int(session.get("user_id"))
        saved_meals = _fetch_saved_meals_for_user(user_id, limit=25)
    except Exception:
        saved_meals = []

    return render_template_string(
        PAGE_HTML,
        nav_buttons=nav_buttons,
        meal=meal,
        search_query=search_query,
        class_names=class_names[:5000],
        current_image_url=current_image_url,
        current_preds=current_preds,
        history=history,
        saved_meals=saved_meals,
        fmt_num=_fmt_num,
    )


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


@food_bp.route("/set_search", methods=["POST"])
def set_search():
    if not _require_login():
        return redirect(url_for("auth.login"))

    q = (request.form.get("search", "") or "").strip().lower()
    session["last_search_query"] = q
    return redirect(url_for("food.index"))


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


@food_bp.route("/clear_meal", methods=["POST"])
def clear_meal():
    if not _require_login():
        return redirect(url_for("auth.login"))
    session["meal_items"] = []
    return redirect(url_for("food.index"))


@food_bp.route("/clear_history", methods=["POST"])
def clear_history():
    if not _require_login():
        return redirect(url_for("auth.login"))
    session["predicted_history"] = []
    return redirect(url_for("food.index"))


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


PAGE_HTML = r"""
<!doctype html>
<html>
<head>
  <title>Add Food</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='styles.css') }}">
  <style>
    .card { border:1px solid #ddd; border-radius:12px; padding:16px; margin:16px auto; max-width:980px; background:#fff; }
    .row { display:flex; gap:18px; flex-wrap:wrap; }
    .col { flex:1; min-width:320px; }
    .pred { padding:10px; border:1px solid #eee; border-radius:10px; margin:8px 0; }
    .meal-item { padding:12px; border:1px solid #eee; border-radius:14px; margin:10px 0; background:#fff; }
    input[type="text"], input[type="number"] { width: 100%; padding:10px; }
    select { width: 100%; padding:10px; }
    .muted { color:#666; }

    .preview-wrap { margin-top:12px; }
    .preview-img {
      width:160px;
      height:120px;
      object-fit:cover;
      border-radius:10px;
      border:1px solid #eaeaea;
      display:none;
    }

    .history-row {
      display:flex;
      gap:12px;
      overflow-x:auto;
      padding:10px 2px;
      margin-top:10px;
    }
    .history-item {
      min-width:180px;
      border:1px solid #eee;
      border-radius:12px;
      padding:10px;
      background:#fafafa;
      flex:0 0 auto;
    }
    .history-item img {
      width:160px;
      height:120px;
      object-fit:cover;
      border-radius:10px;
      border:1px solid #eaeaea;
      display:block;
    }

    .history-meta { margin-top:8px; font-size:13px; }

    .small { padding:8px 10px; font-size:14px; }
    .edit-row { display:flex; gap:8px; align-items:center; margin-top:8px; flex-wrap:wrap; }
    .edit-row select { flex:1; min-width:220px; }
    .edit-row input[type="number"] { width:140px; }
    .grams-row { display:flex; gap:10px; align-items:center; margin-top:10px; }
    .grams-row input[type="number"] { width:180px; }

    .nutri-grid {
      display:grid;
      grid-template-columns: 1fr 1fr;
      gap:6px 12px;
      margin-top:10px;
      font-size:14px;
    }
    .nutri-grid div { padding:6px 8px; border:1px dashed #eee; border-radius:10px; background:#fafafa; }
    .nutri-grid b { display:inline-block; min-width:120px; }
  </style>
</head>

<body class="home">

  <div class="hero-section">
      <div class="hero-image">
          <img src="{{ url_for('static', filename='nutrilog_icon.png') }}" alt="NutriLog Icon">
      </div>
  </div>

  <nav>
      <ul class="menu">
          {{ nav_buttons|safe }}
      </ul>
  </nav>

  {% if session.get("flash_msg") %}
    <div class="card">
      <p class="muted">{{ session.get("flash_msg") }}</p>
    </div>
    {% set _ = session.pop("flash_msg") %}
  {% endif %}

  <div class="card">
    <h2>Add Food (Upload → Auto Predict → Pick → Add to Meal)</h2>

    <form id="predictForm" action="{{ url_for('food.predict') }}" method="post" enctype="multipart/form-data">
      <label><b>Upload a food image:</b></label><br><br>
      <input id="imageInput" type="file" name="image" accept="image/*" required>

      <div class="preview-wrap">
        <p id="pickedFileText" class="muted">No file selected yet.</p>
        <img id="mainImg" class="preview-img" alt="Food preview">
      </div>

      <p id="predictStatus" class="muted" style="margin-top:10px;"></p>
    </form>
  </div>

  <div class="card">
    <div class="row">
      <div class="col">
        <h3>Top 3 Predictions</h3>

        <div id="predArea">
          {% if current_preds %}
            <form action="{{ url_for('food.add_food') }}" method="post" id="addFoodForm">
              <div class="grams-row">
                <div style="flex:1;">
                  <label class="muted"><b>How many grams are you eating?</b></label>
                  <input type="number" name="grams" min="1" max="5000" step="1" value="100" required>
                </div>
              </div>

              {% for lbl, prob in current_preds %}
                <div class="pred">
                  <label style="display:flex; justify-content:space-between; align-items:center;">
                    <span>
                      <input type="radio" name="chosen_label" value="{{ lbl }}" required>
                      <b>{{ lbl }}</b>
                    </span>
                    <span>{{ prob }}</span>
                  </label>
                </div>
              {% endfor %}
              <button type="submit">Add Selected To Meal</button>
            </form>
          {% else %}
            <p id="noPredText">No predictions yet. Upload an image above.</p>
          {% endif %}
        </div>

        <hr>

        <h3>Wrong? Search and pick a food</h3>

        <form action="{{ url_for('food.set_search') }}" method="post" style="margin-bottom:10px;">
          <input type="text" name="search" placeholder="Search food label..." value="{{ search_query }}">
          <button type="submit" style="margin-top:8px;">Search</button>
        </form>

        {% if search_query %}
          {% set matches = [] %}
          {% for name in class_names %}
            {% if search_query in name.lower() %}
              {% set _ = matches.append(name) %}
            {% endif %}
          {% endfor %}

          <form action="{{ url_for('food.add_food') }}" method="post">
            <label><b>Matches:</b></label>
            <select name="chosen_label" required>
              {% for m in matches[:50] %}
                <option value="{{ m }}">{{ m }}</option>
              {% endfor %}
            </select>

            <div class="grams-row">
              <div style="flex:1;">
                <label class="muted"><b>Grams</b></label>
                <input type="number" name="grams" min="1" max="5000" step="1" value="100" required>
              </div>
            </div>

            <button type="submit" style="margin-top:8px;">Add Selected To Meal</button>
          </form>

          {% if matches|length == 0 %}
            <p>No matches found.</p>
          {% endif %}
        {% endif %}
      </div>

      <div class="col">
        <h3>Current Meal</h3>
        {% if meal and meal|length > 0 %}
          {% for item in meal %}
            {% set i = loop.index0 %}
            <div class="meal-item">
              <div style="display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap;">
                <div>
                  <b>{{ item.label }}</b>
                  {% if item.grams %}
                    <span class="muted"> — {{ item.grams }} g</span>
                  {% endif %}
                </div>

                <form action="{{ url_for('food.remove_meal_item') }}" method="post" style="margin:0;">
                  <input type="hidden" name="index" value="{{ i }}">
                  <button type="submit" class="small">Remove</button>
                </form>
              </div>

              <div class="nutri-grid">
                <div><b>Calories</b> {{ fmt_num(item.calories, 0) }}</div>
                <div><b>Protein (g)</b> {{ fmt_num(item.protein, 1) }}</div>
                <div><b>Carbs (g)</b> {{ fmt_num(item.carbohydrates, 1) }}</div>
                <div><b>Fats (g)</b> {{ fmt_num(item.fats, 1) }}</div>
                <div><b>Fiber (g)</b> {{ fmt_num(item.fiber, 1) }}</div>
                <div><b>Sugars (g)</b> {{ fmt_num(item.sugars, 1) }}</div>
                <div><b>Sodium (mg)</b> {{ fmt_num(item.sodium, 0) }}</div>
              </div>

              <form action="{{ url_for('food.edit_meal_item') }}" method="post" class="edit-row">
                <input type="hidden" name="index" value="{{ i }}">
                <select name="new_label">
                  <option value="" disabled selected>Change label…</option>
                  {% for n in class_names[:5000] %}
                    <option value="{{ n }}">{{ n }}</option>
                  {% endfor %}
                </select>

                <input type="number" name="grams" min="1" max="5000" step="1"
                       value="{{ item.grams if item.grams else 100 }}" required>

                <button type="submit" class="small">Edit</button>
              </form>
            </div>
          {% endfor %}

          <form action="{{ url_for('food.clear_meal') }}" method="post" style="margin-top:12px;">
            <button type="submit">Clear Meal</button>
          </form>

          <form action="{{ url_for('food.save_meal') }}" method="post" style="margin-top:12px;">
            <button type="submit">Save Meal</button>
          </form>

        {% else %}
          <p>No items added yet. Add foods and they’ll appear here.</p>
        {% endif %}

        <p style="margin-top:14px; color:#666;">
          (Your meal list is in session until you click “Save Meal”. Saved meals go into Meal_Log.meal_items_json.)
        </p>

        <p class="muted" style="margin-top:10px;">
          Debug: <a href="{{ url_for('food.db_debug') }}">/food/db_debug</a>
        </p>
      </div>
    </div>
  </div>

  <div class="card">
    <h3 style="display:flex; justify-content:space-between; align-items:center;">
      <span>Last Predicted (added to meal)</span>
      <form action="{{ url_for('food.clear_history') }}" method="post"
            onsubmit="return confirm('Clear all last predicted images?');" style="margin:0;">
        <button type="submit">Clear</button>
      </form>
    </h3>

    {% if history and history|length > 0 %}
      <div class="history-row">
        {% for item in history %}
          <div class="history-item">
            <img src="{{ item.image_url }}" alt="predicted">
            <div class="history-meta">
              <div><b>{{ item.label }}</b></div>
              {% if item.prob %}
                <div class="muted">{{ item.prob }}</div>
              {% endif %}
              {% if item.grams %}
                <div class="muted">{{ item.grams }} g</div>
              {% endif %}
              {% if item.calories is not none %}
                <div class="muted">{{ fmt_num(item.calories, 0) }} cal</div>
              {% endif %}
            </div>
          </div>
        {% endfor %}
      </div>
    {% else %}
      <p class="muted">No history yet. Add a predicted item to your meal to start building history.</p>
    {% endif %}
  </div>

  <div class="card">
    <h3>Saved Meals (from database)</h3>

    {% if saved_meals and saved_meals|length > 0 %}
      <div style="display:flex; flex-direction:column; gap:10px; margin-top:10px;">
        {% for m in saved_meals %}
          <div style="border:1px solid #eee; border-radius:12px; padding:12px; background:#fafafa;">
            <div style="display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap;">
              <div><b>{{ m.created_at }}</b></div>
              <div class="muted">Meal #{{ m.log_id }}</div>
            </div>

            {% if m.meal_items and m.meal_items|length > 0 %}
              <div style="margin-top:10px; display:flex; flex-direction:column; gap:10px;">
                {% for it in m.meal_items %}
                  <div style="border:1px solid #eee; border-radius:12px; padding:10px; background:#fff;">
                    <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:10px;">
                      <div>
                        <b>{{ it.label }}</b>
                        {% if it.grams %}<span class="muted"> — {{ it.grams }} g</span>{% endif %}
                      </div>
                      {% if it.calories is not none %}
                        <div class="muted">{{ fmt_num(it.calories, 0) }} calories</div>
                      {% endif %}
                    </div>

                    <div class="nutri-grid">
                      <div><b>Protein (g)</b> {{ fmt_num(it.protein, 1) }}</div>
                      <div><b>Carbs (g)</b> {{ fmt_num(it.carbohydrates, 1) }}</div>
                      <div><b>Fats (g)</b> {{ fmt_num(it.fats, 1) }}</div>
                      <div><b>Fiber (g)</b> {{ fmt_num(it.fiber, 1) }}</div>
                      <div><b>Sugars (g)</b> {{ fmt_num(it.sugars, 1) }}</div>
                      <div><b>Sodium (mg)</b> {{ fmt_num(it.sodium, 0) }}</div>
                    </div>
                  </div>
                {% endfor %}
              </div>
            {% else %}
              <div class="muted" style="margin-top:8px;">(No items)</div>
            {% endif %}
          </div>
        {% endfor %}
      </div>
    {% else %}
      <p class="muted">No saved meals yet. Add foods and click “Save Meal”.</p>
    {% endif %}
  </div>

  <script>
    const input = document.getElementById("imageInput");
    const mainImg = document.getElementById("mainImg");
    const pickedFileText = document.getElementById("pickedFileText");
    const predictStatus = document.getElementById("predictStatus");
    const predictForm = document.getElementById("predictForm");
    const predArea = document.getElementById("predArea");

    let lastObjectUrl = null;

    function renderPredictions(preds) {
      if (!preds || preds.length === 0) {
        predArea.innerHTML = '<p id="noPredText">No predictions yet. Upload an image above.</p>';
        return;
      }

      let html = '';
      html += `<form action="{{ url_for('food.add_food') }}" method="post" id="addFoodForm">`;

      html += `
        <div class="grams-row">
          <div style="flex:1;">
            <label class="muted"><b>How many grams are you eating?</b></label>
            <input type="number" name="grams" min="1" max="5000" step="1" value="100" required>
          </div>
        </div>
      `;

      for (const [lbl, prob] of preds) {
        const safeLbl = String(lbl).replace(/"/g, '&quot;');
        html += `
          <div class="pred">
            <label style="display:flex; justify-content:space-between; align-items:center;">
              <span>
                <input type="radio" name="chosen_label" value="${safeLbl}" required>
                <b>${lbl}</b>
              </span>
              <span>${prob}</span>
            </label>
          </div>
        `;
      }
      html += `<button type="submit">Add Selected To Meal</button></form>`;
      predArea.innerHTML = html;
    }

    async function autoPredict() {
      const file = input.files && input.files[0];
      if (!file) return;

      predictStatus.textContent = "Predicting...";

      const formData = new FormData(predictForm);

      try {
        const resp = await fetch(predictForm.action, {
          method: "POST",
          body: formData,
          headers: { "X-Requested-With": "fetch" }
        });

        const data = await resp.json();
        if (!resp.ok || !data.ok) {
          predictStatus.textContent = "Predict failed. Try a different image.";
          return;
        }

        if (data.image_url) {
          if (lastObjectUrl) {
            URL.revokeObjectURL(lastObjectUrl);
            lastObjectUrl = null;
          }
          mainImg.src = data.image_url;
          mainImg.style.display = "block";
        }

        renderPredictions(data.preds);
        predictStatus.textContent = "Prediction ready. Select the correct one, enter grams, and add to meal.";
      } catch (err) {
        console.error(err);
        predictStatus.textContent = "Predict crashed. Check your Flask console for the error.";
      }
    }

    input.addEventListener("change", () => {
      const file = input.files && input.files[0];

      if (!file) {
        pickedFileText.textContent = "No file selected yet.";
        mainImg.style.display = "none";
        if (lastObjectUrl) URL.revokeObjectURL(lastObjectUrl);
        lastObjectUrl = null;
        return;
      }

      pickedFileText.textContent = `Selected: ${file.name}`;

      if (lastObjectUrl) URL.revokeObjectURL(lastObjectUrl);
      lastObjectUrl = URL.createObjectURL(file);

      mainImg.src = lastObjectUrl;
      mainImg.style.display = "block";

      autoPredict();
    });
  </script>

</body>
</html>
"""
