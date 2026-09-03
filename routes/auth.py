from flask import Blueprint, flash, render_template, request, redirect, session
from functools import wraps
from database import get_db
from utils.password import verify_password

auth = Blueprint("auth", __name__)


# ================= LOGIN REQUIRED =================
def login_required(role=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not session.get("user_id"):
                return redirect("/")

            if role and session.get("role") != role:
                return "Unauthorized Access", 403

            return func(*args, **kwargs)
        return wrapper
    return decorator


# ================= LOGIN PAGE =================
@auth.route("/")
def login_page():
    return render_template("login.html")


# ================= LOGIN =================
@auth.route("/login", methods=["POST"])
def login():

    usn = request.form.get("USN", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "").strip()
    if not usn or not password or role not in {"student", "teacher", "admin"}:
        return render_template("login.html", error="Please provide valid login details.")

    db = cursor = None
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT *
            FROM users
            WHERE USN=%s
            AND role=%s
            """,
            (usn, role),
        )
        user = cursor.fetchone()
    except Exception:
        flash("Unable to sign in at the moment. Please try again.", "danger")
        return redirect("/")
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()

    if not user:
        return render_template(
            "login.html",
            error="Invalid Username or Password"
        )

    if not verify_password(user["password"], password):
        return render_template(
            "login.html",
            error="Invalid Username or Password"
        )

    session["user_id"] = user["id"]
    session["role"] = user["role"]
    session["name"] = user["UserName"]

    return redirect(f"/{role}/dashboard")


# ================= LOGOUT =================
@auth.route("/logout")
def logout():

    session.clear()

    return redirect("/")
