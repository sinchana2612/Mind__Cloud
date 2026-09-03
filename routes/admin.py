from datetime import datetime

import pandas as pd
from flask import Blueprint, flash, redirect, render_template, request, session
from flask import send_from_directory
import os
from database import get_db
from routes.auth import login_required
from utils.excel_import import import_students as import_students_from_excel
from utils.excel_import import import_teachers as import_teachers_from_excel
from utils.password import generate_default_password_from_dob, hash_password
from werkzeug.utils import secure_filename
import uuid

admin = Blueprint("admin", __name__)

ALLOWED_EXTENSIONS = {"jpg", "jpeg"}

def allowed_photo(filename):
    return (
        "." in filename and
        filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def _close(cursor, db):
    """Close database resources without masking the original request error."""
    if cursor:
        cursor.close()
    if db:
        db.close()


def _name():
    return session.get("name", "")


@admin.route("/admin/dashboard")
@login_required("admin")
def admin_dashboard():
    db = cursor = None
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) AS total FROM students")
        total_students = cursor.fetchone()["total"]
        cursor.execute("SELECT COUNT(*) AS total FROM teachers")
        total_teachers = cursor.fetchone()["total"]
        cursor.execute("SELECT COUNT(*) AS total FROM counselling_requests")
        total_requests = cursor.fetchone()["total"]
        cursor.execute("SELECT COUNT(*) AS total FROM counselling_requests WHERE status='Pending'")
        pending_requests = cursor.fetchone()["total"]
        cursor.execute("SELECT COUNT(*) AS total FROM counselling_requests WHERE is_closed=1")
        completed_sessions = cursor.fetchone()["total"]
        cursor.execute("""SELECT cr.id, u.UserName AS student_name, cr.category, cr.status, cr.created_at
            FROM counselling_requests cr JOIN students s ON cr.student_id=s.id
            JOIN users u ON s.user_id=u.id ORDER BY cr.created_at DESC LIMIT 5""")
        recent_requests = cursor.fetchall()
        return render_template("admin/dashboard.html", name=_name(), total_students=total_students,
            total_teachers=total_teachers, total_requests=total_requests, pending_requests=pending_requests,
            completed_sessions=completed_sessions, recent_requests=recent_requests)
    except Exception as error:
        flash(f"Unable to load dashboard: {error}", "danger")
        return render_template("admin/dashboard.html", name=_name(), total_students=0, total_teachers=0,
            total_requests=0, pending_requests=0, completed_sessions=0, recent_requests=[])
    finally:
        _close(cursor, db)

@admin.route("/admin/download_student_template")
@login_required("admin")
def download_student_template():
    return send_from_directory(
        os.path.join(os.getcwd(), "excel_templates"),
        "students_template.xlsx",
        as_attachment=True
    )


@admin.route("/admin/download_teacher_template")
@login_required("admin")
def download_teacher_template():
    return send_from_directory(
        os.path.join(os.getcwd(), "excel_templates"),
        "teachers_template.xlsx",
        as_attachment=True
    )


@admin.route("/admin/students")
@login_required("admin")
def student_management():
    db = cursor = None
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) AS total FROM students")
        total_students = cursor.fetchone()["total"]
        cursor.execute("SELECT COUNT(*) AS total FROM students WHERE assigned_teacher_id IS NULL")
        return render_template("admin/student_management.html", name=_name(), total_students=total_students,
            unassigned_students=cursor.fetchone()["total"])
    except Exception as error:
        flash(f"Unable to load student management: {error}", "danger")
        return redirect("/admin/dashboard")
    finally:
        _close(cursor, db)


@admin.route("/admin/add_student", methods=["GET", "POST"])
@login_required("admin")
def add_student():
    db = cursor = None
    teachers = []

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT t.id, u.UserName
            FROM teachers t
            JOIN users u ON t.user_id = u.id
            ORDER BY u.UserName
        """)
        teachers = cursor.fetchall()

        if request.method == "POST":

            required = (
                "username",
                "usn",
                "dob",
                "department",
                "class",
                "section",
                "semester",
                "batch",
                "email",
                "phone",
                "gender",
                "parent_name",
                "parent_phone",
                "address",
                "admission_year"
            )

            values = {
                field: request.form.get(field, "").strip()
                for field in required
            }

            if not all(values.values()):
                flash("Please complete all required fields.", "danger")
                return render_template(
                    "admin/add_student.html",
                    teachers=teachers,
                    name=_name()
                )

            cursor.execute(
                "SELECT id FROM users WHERE USN=%s",
                (values["usn"],)
            )

            if cursor.fetchone():
                flash("USN already exists.", "danger")
                return render_template(
                    "admin/add_student.html",
                    teachers=teachers,
                    name=_name()
                )

            # ================= PHOTO ================= #

            photo_name = None

            photo = request.files.get("photo")

            if photo and photo.filename:

                if not allowed_photo(photo.filename):
                    flash("Only JPG/JPEG images are allowed.", "danger")
                    return render_template(
                        "admin/add_student.html",
                        teachers=teachers,
                        name=_name()
                    )

                photo_name = secure_filename(
                    f"{uuid.uuid4().hex}.jpg"
                )

                save_path = os.path.join(
                    "uploads",
                    "students",
                    photo_name
                )

                photo.save(save_path)

            # ========================================== #

            default_password = generate_default_password_from_dob(
                values["dob"]
            )

            cursor.execute("""
                INSERT INTO users
                (
                    UserName,
                    USN,
                    password,
                    role
                )
                VALUES
                (
                    %s,%s,%s,'student'
                )
            """,
            (
                values["username"],
                values["usn"],
                hash_password(default_password)
            ))

            user_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO students
                (
                    user_id,
                    assigned_teacher_id,
                    department,
                    class,
                    email,
                    gender,
                    dob,
                    phone,
                    parent_name,
                    parent_phone,
                    address,
                    semester,
                    section,
                    batch,
                    admission_year,
                    cgpa,
                    attendance,
                    career_goal,
                    interest_domain,
                    photo
                )
                VALUES
                (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
            """,
            (
                user_id,
                request.form.get("assigned_teacher") or None,
                values["department"],
                values["class"],
                values["email"],
                values["gender"],
                values["dob"],
                values["phone"],
                values["parent_name"],
                values["parent_phone"],
                values["address"],
                values["semester"],
                values["section"],
                values["batch"],
                values["admission_year"],
                request.form.get("cgpa") or 0,
                request.form.get("attendance") or 0,
                request.form.get("career_goal", "").strip(),
                request.form.get("interest_domain", "").strip(),
                photo_name
            ))

            db.commit()

            flash(
                f"Student added successfully!\n"
                f"Username : {values['usn']}\n"
                f"Default Password : {default_password}",
                "success"
            )

            return redirect("/admin/view_students")

        return render_template(
            "admin/add_student.html",
            teachers=teachers,
            name=_name()
        )

    except Exception as error:

        if db:
            db.rollback()

        flash(
            f"Unable to add student: {error}",
            "danger"
        )

        return render_template(
            "admin/add_student.html",
            teachers=teachers,
            name=_name()
        )

    finally:
        _close(cursor, db)

@admin.route("/admin/import_students", methods=["GET", "POST"])
@login_required("admin")
def import_students():
    if request.method == "POST" and _import_file("students"):
        return redirect("/admin/view_students")
    return render_template("admin/import_students.html", name=_name())


@admin.route("/admin/view_students")
@login_required("admin")
def view_students():
    db = cursor = None
    search = request.args.get("search", "").strip()
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        query = """SELECT s.id, u.UserName, u.USN, s.department, s.semester, s.section, s.email, s.phone, s.cgpa,
            s.attendance, t.employee_id, tu.UserName AS teacher_name FROM students s JOIN users u ON s.user_id=u.id
            LEFT JOIN teachers t ON s.assigned_teacher_id=t.id LEFT JOIN users tu ON t.user_id=tu.id"""
        params = ()
        if search:
            query += " WHERE u.UserName LIKE %s OR u.USN LIKE %s"; params = (f"%{search}%", f"%{search}%")
        cursor.execute(query + " ORDER BY u.UserName", params)
        return render_template("admin/view_students.html", students=cursor.fetchall(), search=search, name=_name())
    except Exception as error:
        flash(f"Unable to load students: {error}", "danger")
        return render_template("admin/view_students.html", students=[], search=search, name=_name())
    finally:
        _close(cursor, db)


@admin.route("/admin/teachers")
@login_required("admin")
def teacher_management():
    db = cursor = None
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) AS total FROM teachers"); total_teachers = cursor.fetchone()["total"]
        cursor.execute("SELECT COUNT(*) AS total FROM students WHERE assigned_teacher_id IS NULL")
        return render_template("admin/teacher_management.html", name=_name(), total_teachers=total_teachers,
            unassigned_students=cursor.fetchone()["total"])
    except Exception as error:
        flash(f"Unable to load teacher management: {error}", "danger"); return redirect("/admin/dashboard")
    finally:
        _close(cursor, db)


@admin.route("/admin/add_teacher", methods=["GET", "POST"])
@login_required("admin")
def add_teacher():
    db = cursor = None

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        if request.method == "POST":

            required = (
                "username",
                "employee_id",
                "dob",
                "department",
                "designation",
                "qualification",
                "experience",
                "office_room",
                "email",
                "phone",
                "gender"
            )

            values = {
                field: request.form.get(field, "").strip()
                for field in required
            }

            if not all(values.values()):
                flash("Please complete all required fields.", "danger")
                return render_template(
                    "admin/add_teacher.html",
                    name=_name()
                )

            cursor.execute(
                "SELECT id FROM users WHERE USN=%s",
                (values["employee_id"],)
            )

            if cursor.fetchone():
                flash("Employee ID already exists.", "danger")
                return render_template(
                    "admin/add_teacher.html",
                    name=_name()
                )

            # ================= PHOTO ================= #

            photo_name = None

            photo = request.files.get("photo")

            if photo and photo.filename:

                if not allowed_photo(photo.filename):
                    flash("Only JPG/JPEG images are allowed.", "danger")
                    return render_template(
                        "admin/add_teacher.html",
                        name=_name()
                    )

                photo_name = secure_filename(
                    f"{uuid.uuid4().hex}.jpg"
                )

                save_path = os.path.join(
                    "uploads",
                    "teachers",
                    photo_name
                )

                photo.save(save_path)

            # ========================================== #

            default_password = generate_default_password_from_dob(
                values["dob"]
            )

            cursor.execute("""
                INSERT INTO users
                (
                    UserName,
                    USN,
                    password,
                    role
                )
                VALUES
                (
                    %s,%s,%s,'teacher'
                )
            """,
            (
                values["username"],
                values["employee_id"],
                hash_password(default_password)
            ))

            user_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO teachers
                (
                    user_id,
                    department,
                    email,
                    designation,
                    employee_id,
                    gender,
                    dob,
                    phone,
                    qualification,
                    experience,
                    office_room,
                    photo
                )
                VALUES
                (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
            """,
            (
                user_id,
                values["department"],
                values["email"],
                values["designation"],
                values["employee_id"],
                values["gender"],
                values["dob"],
                values["phone"],
                values["qualification"],
                values["experience"],
                values["office_room"],
                photo_name
            ))

            db.commit()

            flash(
                f"Teacher added successfully!\n"
                f"Username : {values['employee_id']}\n"
                f"Default Password : {default_password}",
                "success"
            )

            return redirect("/admin/view_teachers")

        return render_template(
            "admin/add_teacher.html",
            name=_name()
        )

    except Exception as error:

        if db:
            db.rollback()

        flash(
            f"Unable to add teacher: {error}",
            "danger"
        )

        return render_template(
            "admin/add_teacher.html",
            name=_name()
        )

    finally:
        _close(cursor, db)


@admin.route("/admin/import_teachers", methods=["GET", "POST"])
@login_required("admin")
def import_teachers():
    if request.method == "POST" and _import_file("teachers"):
        return redirect("/admin/view_teachers")
    return render_template("admin/import_teachers.html", name=_name())


@admin.route("/admin/view_teachers")
@login_required("admin")
def view_teachers():
    db = cursor = None; search = request.args.get("search", "").strip()
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        query = """SELECT t.id, u.UserName, t.employee_id, t.department, t.designation, t.email, t.phone,
            t.qualification, t.experience, (SELECT COUNT(*) FROM students s WHERE s.assigned_teacher_id=t.id) AS total_students
            FROM teachers t JOIN users u ON t.user_id=u.id"""; params = ()
        if search:
            query += " WHERE u.UserName LIKE %s OR t.employee_id LIKE %s"; params = (f"%{search}%", f"%{search}%")
        cursor.execute(query + " ORDER BY u.UserName", params)
        return render_template("admin/view_teachers.html", teachers=cursor.fetchall(), search=search, name=_name())
    except Exception as error:
        flash(f"Unable to load teachers: {error}", "danger")
        return render_template("admin/view_teachers.html", teachers=[], search=search, name=_name())
    finally:
        _close(cursor, db)


@admin.route("/admin/assign_students", methods=["GET", "POST"])
@login_required("admin")
def assign_students():
    db = cursor = None
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        if request.method == "POST":
            student_id, teacher_id = request.form.get("student_id"), request.form.get("teacher_id")
            if not student_id or not teacher_id:
                flash("Select both a student and teacher.", "danger"); return redirect("/admin/assign_students")
            cursor.execute("SELECT id FROM teachers WHERE id=%s", (teacher_id,))
            if not cursor.fetchone():
                flash("Selected teacher was not found.", "danger"); return redirect("/admin/assign_students")
            cursor.execute("UPDATE students SET assigned_teacher_id=%s WHERE id=%s", (teacher_id, student_id))
            if not cursor.rowcount:
                flash("Selected student was not found.", "danger"); return redirect("/admin/assign_students")
            db.commit(); flash("Student assigned successfully.", "success"); return redirect("/admin/assign_students")
        cursor.execute("""SELECT s.id, u.UserName, u.USN, s.department, s.semester, s.section, tu.UserName AS teacher_name,
            s.assigned_teacher_id FROM students s JOIN users u ON s.user_id=u.id LEFT JOIN teachers t ON s.assigned_teacher_id=t.id
            LEFT JOIN users tu ON t.user_id=tu.id ORDER BY u.UserName"""); students = cursor.fetchall()
        cursor.execute("SELECT t.id, u.UserName, t.employee_id, t.department FROM teachers t JOIN users u ON t.user_id=u.id ORDER BY u.UserName")
        return render_template("admin/assign.html", students=students, teachers=cursor.fetchall(), name=_name())
    except Exception as error:
        if request.method == "POST" and db: db.rollback()
        flash(f"Unable to assign student: {error}", "danger"); return redirect("/admin/dashboard")
    finally:
        _close(cursor, db)


@admin.route("/admin/sessions")
@login_required("admin")
def sessions():
    db = cursor = None
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                cr.id,
                u.UserName AS student_name,
                cr.problem,
                cr.category,
                cr.status,
                cr.created_at,
                cr.is_closed,
                tu.UserName AS teacher_name
            FROM counselling_requests cr
            JOIN students s
                ON cr.student_id = s.id
            JOIN users u
                ON s.user_id = u.id
            LEFT JOIN teachers t
                ON s.assigned_teacher_id = t.id
            LEFT JOIN users tu
                ON t.user_id = tu.id
            ORDER BY cr.created_at DESC
        """)

        sessions = cursor.fetchall()

        return render_template(
            "admin/sessions.html",
            sessions=sessions,
            name=_name()
        )

    except Exception as error:
        flash(f"Unable to load sessions: {error}", "danger")
        return render_template(
            "admin/sessions.html",
            sessions=[],
            name=_name()
        )

    finally:
        _close(cursor, db)
