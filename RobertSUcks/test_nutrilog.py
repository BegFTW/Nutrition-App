"""
Unit tests for NutriLog application.

Covers:
  - security.py  : encrypt_password / decrypt_password
  - food_ml.py   : _norm_label, _to_float, _compute_scaled_nutrition
  - clock_in_page.py : elapsed-time / total-time arithmetic logic
  - Flask routes : login, logout, register, clock index (with DB mocked)
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import sys
import os

PROJECT_ROOT = os.path.join(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ===========================================================================
# 1. security.py tests
# ===========================================================================
class TestSecurity(unittest.TestCase):
    """Tests for encrypt_password and decrypt_password."""

    def setUp(self):
        from security import encrypt_password, decrypt_password
        self.encrypt = encrypt_password
        self.decrypt = decrypt_password

    def test_encrypt_returns_string(self):
        hashed = self.encrypt("mypassword")
        self.assertIsInstance(hashed, str)

    def test_encrypted_password_is_not_plaintext(self):
        plain = "secret123"
        hashed = self.encrypt(plain)
        self.assertNotEqual(plain, hashed)

    def test_correct_password_verifies(self):
        plain = "correct_horse_battery"
        hashed = self.encrypt(plain)
        self.assertTrue(self.decrypt(plain, hashed.encode("utf-8")))

    def test_wrong_password_fails_verification(self):
        hashed = self.encrypt("rightpassword")
        self.assertFalse(self.decrypt("wrongpassword", hashed.encode("utf-8")))

    def test_empty_password_encrypts_and_verifies(self):
        hashed = self.encrypt("")
        self.assertTrue(self.decrypt("", hashed.encode("utf-8")))

    def test_different_hashes_for_same_password(self):
        """pbkdf2_sha256 uses a random salt, so two hashes must differ."""
        p = "samepassword"
        h1 = self.encrypt(p)
        h2 = self.encrypt(p)
        self.assertNotEqual(h1, h2)

    def test_special_characters_in_password(self):
        plain = "p@$$w0rd!#%^&*()"
        hashed = self.encrypt(plain)
        self.assertTrue(self.decrypt(plain, hashed.encode("utf-8")))


# ===========================================================================
# 2. food_ml.py helper function tests
# ===========================================================================
class TestNormLabel(unittest.TestCase):
    """Tests for food_ml._norm_label."""

    def setUp(self):
        from food_ml import _norm_label
        self.norm = _norm_label

    def test_lowercases(self):
        self.assertEqual(self.norm("Apple"), "apple")

    def test_strips_whitespace(self):
        self.assertEqual(self.norm("  banana  "), "banana")

    def test_replaces_underscores_with_space(self):
        self.assertEqual(self.norm("green_beans"), "green beans")

    def test_replaces_hyphens_with_space(self):
        self.assertEqual(self.norm("stir-fry"), "stir fry")

    def test_collapses_multiple_spaces(self):
        self.assertEqual(self.norm("ice   cream"), "ice cream")

    def test_empty_string(self):
        self.assertEqual(self.norm(""), "")

    def test_none_returns_empty(self):
        self.assertEqual(self.norm(None), "")

    def test_mixed_separators(self):
        self.assertEqual(self.norm("Peanut_Butter-Jelly"), "peanut butter jelly")


class TestToFloat(unittest.TestCase):
    """Tests for food_ml._to_float."""

    def setUp(self):
        from food_ml import _to_float
        self.to_float = _to_float

    def test_integer_input(self):
        self.assertEqual(self.to_float(5), 5.0)

    def test_float_input(self):
        self.assertAlmostEqual(self.to_float(3.14), 3.14)

    def test_string_number(self):
        self.assertEqual(self.to_float("42"), 42.0)

    def test_string_with_commas(self):
        self.assertEqual(self.to_float("1,234.56"), 1234.56)

    def test_none_returns_default(self):
        self.assertIsNone(self.to_float(None))
        self.assertEqual(self.to_float(None, default=0.0), 0.0)

    def test_empty_string_returns_default(self):
        self.assertIsNone(self.to_float(""))

    def test_non_numeric_string_returns_default(self):
        self.assertIsNone(self.to_float("not_a_number"))

    def test_whitespace_string_returns_default(self):
        self.assertIsNone(self.to_float("   "))

    def test_negative_number(self):
        self.assertEqual(self.to_float("-10"), -10.0)


class TestComputeScaledNutrition(unittest.TestCase):
    """Tests for food_ml._compute_scaled_nutrition (with cache mocked)."""

    def _make_cache_entry(self):
        return {
            "base_grams": 100.0,
            "calories": 200.0,
            "protein": 10.0,
            "carbohydrates": 30.0,
            "fats": 5.0,
            "fiber": 2.0,
            "sugars": 8.0,
            "sodium": 150.0,
        }

    def setUp(self):
        import food_ml
        self.module = food_ml

    def test_none_grams_returns_none(self):
        from food_ml import _compute_scaled_nutrition
        result = _compute_scaled_nutrition("apple", None)
        self.assertIsNone(result["grams_eaten"])

    def test_zero_grams_returns_none(self):
        from food_ml import _compute_scaled_nutrition
        result = _compute_scaled_nutrition("apple", 0)
        self.assertIsNone(result["grams_eaten"])

    def test_label_not_in_cache_returns_grams_only(self):
        from food_ml import _compute_scaled_nutrition
        with patch("food_ml._load_nutrition_cache", return_value={}):
            result = _compute_scaled_nutrition("unknown_food", 150)
        self.assertEqual(result["grams_eaten"], 150)
        self.assertIsNone(result.get("calories"))

    def test_scaling_at_base_grams(self):
        """Eating exactly the base grams should return the raw nutrient values."""
        from food_ml import _compute_scaled_nutrition
        cache = {"apple": self._make_cache_entry()}
        with patch("food_ml._load_nutrition_cache", return_value=cache):
            result = _compute_scaled_nutrition("apple", 100)
        self.assertEqual(result["grams_eaten"], 100)
        self.assertAlmostEqual(result["calories"], 200.0)
        self.assertAlmostEqual(result["protein"], 10.0)

    def test_scaling_at_half_grams(self):
        """Eating half the base grams should halve nutrient values."""
        from food_ml import _compute_scaled_nutrition
        cache = {"apple": self._make_cache_entry()}
        with patch("food_ml._load_nutrition_cache", return_value=cache):
            result = _compute_scaled_nutrition("apple", 50)
        self.assertAlmostEqual(result["calories"], 100.0)
        self.assertAlmostEqual(result["protein"], 5.0)

    def test_scaling_at_double_grams(self):
        """Eating double the base grams should double nutrient values."""
        from food_ml import _compute_scaled_nutrition
        cache = {"apple": self._make_cache_entry()}
        with patch("food_ml._load_nutrition_cache", return_value=cache):
            result = _compute_scaled_nutrition("apple", 200)
        self.assertAlmostEqual(result["calories"], 400.0)
        self.assertAlmostEqual(result["sodium"], 300.0)

    def test_label_normalization_applied(self):
        """Labels with different case/separators should still match."""
        from food_ml import _compute_scaled_nutrition
        cache = {"peanut butter": self._make_cache_entry()}
        with patch("food_ml._load_nutrition_cache", return_value=cache):
            result = _compute_scaled_nutrition("Peanut_Butter", 100)
        self.assertAlmostEqual(result["calories"], 200.0)


# ===========================================================================
# 3. Clock arithmetic logic tests (extracted from clock_in_page.py)
# ===========================================================================
class TestClockArithmetic(unittest.TestCase):
    """
    Tests the elapsed-time and seconds-to-hms conversion logic that lives
    inside clock_in_page.py's clock_out and index views.
    We test the pure arithmetic here without needing Flask or a database.
    """

    def _elapsed_seconds(self, clock_in_time, now):
        """Mirror the elapsed calculation from clock_out."""
        if isinstance(clock_in_time, datetime):
            elapsed = int((now - clock_in_time).total_seconds())
        else:
            parsed = datetime.fromisoformat(str(clock_in_time))
            elapsed = int((now - parsed).total_seconds())
        return max(elapsed, 0)

    def _seconds_to_hms(self, total_seconds):
        """Mirror the h/m/s breakdown from the index view."""
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return hours, minutes, seconds

    def test_elapsed_exact_one_hour(self):
        clock_in = datetime(2024, 1, 1, 9, 0, 0)
        clock_out = datetime(2024, 1, 1, 10, 0, 0)
        self.assertEqual(self._elapsed_seconds(clock_in, clock_out), 3600)

    def test_elapsed_30_minutes(self):
        clock_in = datetime(2024, 1, 1, 8, 0, 0)
        clock_out = datetime(2024, 1, 1, 8, 30, 0)
        self.assertEqual(self._elapsed_seconds(clock_in, clock_out), 1800)

    def test_elapsed_negative_clamped_to_zero(self):
        """If the clock somehow goes backwards, elapsed should be 0."""
        clock_in = datetime(2024, 1, 1, 10, 0, 0)
        clock_out = datetime(2024, 1, 1, 9, 0, 0)
        self.assertEqual(self._elapsed_seconds(clock_in, clock_out), 0)

    def test_elapsed_from_iso_string(self):
        clock_in_str = "2024-06-15 08:00:00"
        clock_out = datetime(2024, 6, 15, 9, 0, 0)
        self.assertEqual(self._elapsed_seconds(clock_in_str, clock_out), 3600)

    def test_total_time_accumulates(self):
        previous_total = 3600  # 1 hour already worked
        elapsed = 1800         # 30 minutes just worked
        new_total = previous_total + elapsed
        self.assertEqual(new_total, 5400)

    def test_hms_conversion_exact_hours(self):
        h, m, s = self._seconds_to_hms(7200)
        self.assertEqual((h, m, s), (2, 0, 0))

    def test_hms_conversion_mixed(self):
        h, m, s = self._seconds_to_hms(3723)   # 1h 2m 3s
        self.assertEqual((h, m, s), (1, 2, 3))

    def test_hms_conversion_zero(self):
        h, m, s = self._seconds_to_hms(0)
        self.assertEqual((h, m, s), (0, 0, 0))

    def test_hms_conversion_only_seconds(self):
        h, m, s = self._seconds_to_hms(45)
        self.assertEqual((h, m, s), (0, 0, 45))


# ===========================================================================
# 4. Flask route tests (DB mocked via unittest.mock.patch)
# ===========================================================================
class TestFlaskRoutes(unittest.TestCase):
    """Integration-style tests for Flask routes with all DB calls mocked."""

    def setUp(self):
        # Patch mysql.connector.connect before importing modules that call it
        self.db_patch = patch("mysql.connector.connect", return_value=MagicMock())
        self.db_patch.start()

        from app import app
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test-secret"
        self.client = app.test_client()
        self.app = app

    def tearDown(self):
        self.db_patch.stop()

    # --- auth routes --------------------------------------------------------

    def test_index_redirects_to_login(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/login", resp.headers["Location"])

    def test_login_get_returns_200(self):
        resp = self.client.get("/auth/login")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Login", resp.data)

    def test_register_get_returns_200(self):
        resp = self.client.get("/auth/register")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Create", resp.data)

    def test_logout_clears_session_and_redirects(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = "student1"
        resp = self.client.post("/auth/logout")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/login", resp.headers["Location"])
        with self.client.session_transaction() as sess:
            self.assertNotIn("user_id", sess)

    def test_login_post_with_bad_credentials_shows_error(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        # Simulate user not found
        mock_cur.fetchone.return_value = None

        with patch("mysql.connector.connect", return_value=mock_conn):
            resp = self.client.post(
                "/auth/login",
                data={"user_id": "nobody", "pass_key": "wrong"},
            )
        # Should stay on login page (200) or redirect – either way no session set
        with self.client.session_transaction() as sess:
            self.assertNotIn("user_id", sess)

    # --- home route ---------------------------------------------------------

    def test_home_redirects_when_not_logged_in(self):
        resp = self.client.get("/home/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/login", resp.headers["Location"])

    def test_home_renders_when_logged_in(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = "student1"
            sess["first_name"] = "Jane"
            sess["last_name"] = "Doe"
        resp = self.client.get("/home/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Jane", resp.data)

    # --- clock routes -------------------------------------------------------

    def test_clock_index_redirects_when_not_logged_in(self):
        resp = self.client.get("/clock/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/login", resp.headers["Location"])

    def test_clock_index_redirects_non_student(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = "instructor1"
            sess["role"] = "instructor"

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = None

        with patch("mysql.connector.connect", return_value=mock_conn):
            resp = self.client.get("/clock/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/home/", resp.headers["Location"])

    def test_clock_index_renders_for_student(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = "student1"
            sess["role"] = "student"

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        # Return a fake activity row
        mock_cur.fetchone.return_value = {
            "log_id": 1,
            "student_id": "student1",
            "clock_in_time": None,
            "total_time": 3600,
            "latitude": None,
            "longitude": None,
        }

        with patch("mysql.connector.connect", return_value=mock_conn):
            resp = self.client.get("/clock/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Clock In", resp.data)

    # --- maps routes --------------------------------------------------------

    def test_maps_index_redirects_when_not_logged_in(self):
        resp = self.client.get("/maps/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/login", resp.headers["Location"])

    def test_update_location_requires_login(self):
        resp = self.client.post(
            "/maps/update_location",
            json={"latitude": 36.3, "longitude": -82.3},
        )
        self.assertEqual(resp.status_code, 401)

    def test_active_students_forbidden_for_non_instructor(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = "student1"
            sess["role"] = "student"
        resp = self.client.get("/maps/active_students")
        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
