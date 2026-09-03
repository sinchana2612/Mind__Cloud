from flask import Blueprint, flash, redirect, render_template, request, session

from database import get_db
from routes.auth import login_required

student = Blueprint("student", __name__)


def _close(cursor, db):
    if cursor:
        cursor.close()
    if db:
        db.close()


def _student_id(cursor):
    cursor.execute("SELECT id FROM students WHERE user_id=%s", (session.get("user_id"),))
    record = cursor.fetchone()
    return record["id"] if record else None


def _owns_request(cursor, request_id):
    cursor.execute("""SELECT cr.id, cr.is_closed FROM counselling_requests cr
        JOIN students s ON cr.student_id=s.id WHERE cr.id=%s AND s.user_id=%s""",
        (request_id, session.get("user_id")))
    return cursor.fetchone()


@student.route("/student/dashboard")
@login_required("student")
def student_dashboard():
    db = cursor = None
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        cursor.execute("""SELECT u.UserName, s.department, s.class, s.email FROM users u
            JOIN students s ON u.id=s.user_id WHERE u.id=%s""", (session.get("user_id"),))
        return render_template("student/dashboard.html", student=cursor.fetchone(), name=session.get("name", ""))
    except Exception as error:
        flash(f"Unable to load dashboard: {error}", "danger"); return redirect("/")
    finally: _close(cursor, db)


@student.route("/student/request", methods=["GET", "POST"])
@login_required("student")
def student_request():
    db = cursor = None
    source = request.args.get("source"); linked_request_id = request.args.get("linked_request_id")
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        if request.method == "POST":
            problem, category = request.form.get("problem", "").strip(), request.form.get("category", "").strip()
            student_id = _student_id(cursor)
            if not student_id:
                flash("Student profile not found. Please contact admin.", "danger"); return redirect("/student/dashboard")
            if not problem or not category:
                flash("Please provide both a problem and category.", "danger"); return redirect(request.url)
            cursor.execute("""INSERT INTO counselling_requests (student_id, problem, category, status, is_closed, linked_teacher_request_id)
                VALUES (%s,%s,%s,'Pending',0,%s)""", (student_id, problem, category, linked_request_id))
            request_id = cursor.lastrowid
            cursor.execute("""INSERT INTO counselling_messages (request_id, sender_role, message, confidential)
                VALUES (%s,'student',%s,%s)""", (request_id, problem, 1 if request.form.get("confidential") else 0))
            db.commit(); return redirect("/student/history")
        prefilled_message = "This counselling request is in response to the teacher-initiated counselling request." if source == "teacher_request" else ""
        return render_template("student/request.html", prefilled_message=prefilled_message, source=source)
    except Exception as error:
        if db: db.rollback()
        flash(f"Unable to submit request: {error}", "danger"); return redirect("/student/request")
    finally: _close(cursor, db)


@student.route("/student/teacher_requests")
@login_required("student")
def student_teacher_requests():
    db = cursor = None
    try:
        db = get_db(); cursor = db.cursor(dictionary=True); student_id = _student_id(cursor)
        if not student_id:
            flash("Student profile not found. Please contact admin.", "danger"); return redirect("/student/dashboard")
        cursor.execute("""SELECT tcr.id, u.UserName AS teacher_name, tcr.reason, tcr.message, tcr.status, tcr.created_at
            FROM teacher_counselling_requests tcr JOIN teachers t ON tcr.teacher_id=t.id JOIN users u ON t.user_id=u.id
            WHERE tcr.student_id=%s ORDER BY tcr.created_at DESC""", (student_id,))
        return render_template("student/teacher_requests.html", requests=cursor.fetchall(), name=session.get("name", ""))
    except Exception as error:
        flash(f"Unable to load teacher requests: {error}", "danger"); return redirect("/student/dashboard")
    finally: _close(cursor, db)


@student.route("/student/request/<int:request_id>", methods=["POST"])
@login_required("student")
def student_respond_request(request_id):
    db = cursor = None
    try:
        db = get_db(); cursor = db.cursor(dictionary=True); action = request.form.get("action")
        cursor.execute("""SELECT * FROM teacher_counselling_requests WHERE id=%s AND student_id=(
            SELECT id FROM students WHERE user_id=%s)""", (request_id, session.get("user_id")))
        teacher_request = cursor.fetchone()
        if not teacher_request:
            flash("Counselling request was not found.", "danger"); return redirect("/student/teacher_requests")
        if action not in ("accept", "reject"):
            flash("Invalid request action.", "danger"); return redirect("/student/teacher_requests")
        status = "Accepted" if action == "accept" else "Rejected"
        cursor.execute("UPDATE teacher_counselling_requests SET status=%s, responded_at=NOW() WHERE id=%s", (status, request_id))
        db.commit()
        if action == "accept": return redirect(f"/student/request?teacher_id={teacher_request['teacher_id']}&source=teacher_request&linked_request_id={request_id}")
        return redirect("/student/teacher_requests")
    except Exception as error:
        if db: db.rollback()
        flash(f"Unable to update request: {error}", "danger"); return redirect("/student/teacher_requests")
    finally: _close(cursor, db)


@student.route("/student/history")
@login_required("student")
def student_history():
    db = cursor = None
    try:
        db = get_db(); cursor = db.cursor(dictionary=True); student_id = _student_id(cursor)
        if not student_id:
            flash("Student profile not found. Please contact admin.", "danger"); return redirect("/student/dashboard")
        cursor.execute("""SELECT cr.id, cr.problem, cr.category, cr.status, cr.is_closed, cr.created_at,
            COALESCE((SELECT MAX(cm.confidential) FROM counselling_messages cm WHERE cm.request_id=cr.id AND cm.sender_role='student'),0) AS confidential
            FROM counselling_requests cr WHERE cr.student_id=%s ORDER BY cr.created_at DESC""", (student_id,))
        return render_template("student/history.html", history=cursor.fetchall())
    except Exception as error:
        flash(f"Unable to load request history: {error}", "danger"); return redirect("/student/dashboard")
    finally: _close(cursor, db)


@student.route("/student/reply/<int:request_id>", methods=["GET", "POST"])
@login_required("student")
def student_reply(request_id):
    db = cursor = None
    try:
        db = get_db(); cursor = db.cursor(dictionary=True); counselling_request = _owns_request(cursor, request_id)
        if not counselling_request:
            flash("Counselling request not found.", "danger"); return redirect("/student/history")
        closed = counselling_request["is_closed"] or 0
        if request.method == "POST" and not closed:
            message = request.form.get("message", "").strip()
            if not message:
                flash("Message cannot be empty.", "danger"); return redirect(f"/student/reply/{request_id}")
            cursor.execute("INSERT INTO counselling_messages (request_id, sender_role, message) VALUES (%s,'student',%s)", (request_id, message))
            cursor.execute("UPDATE counselling_requests SET status='Pending' WHERE id=%s AND is_closed=0", (request_id,))
            db.commit(); return redirect(f"/student/reply/{request_id}")
        cursor.execute("SELECT sender_role, message, created_at FROM counselling_messages WHERE request_id=%s ORDER BY created_at", (request_id,)); messages = cursor.fetchall()
        cursor.execute("SELECT teacher_response, student_rating FROM counselling_responses WHERE request_id=%s", (request_id,)); response = cursor.fetchone()
        return render_template("student/reply.html", messages=messages, request_id=request_id, closed=closed, current_rating=response["student_rating"] if response else None, name=session.get("name", ""))
    except Exception as error:
        if request.method == "POST" and db: db.rollback()
        flash(f"Unable to load conversation: {error}", "danger"); return redirect("/student/history")
    finally: _close(cursor, db)


@student.route("/student/end_chat/<int:request_id>", methods=["POST"])
@login_required("student")
def end_chat(request_id):
    db = cursor = None
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        if not _owns_request(cursor, request_id):
            flash("Counselling request not found.", "danger"); return redirect("/student/history")
        cursor.execute("UPDATE counselling_requests SET is_closed=1, status='Completed' WHERE id=%s", (request_id,))
        cursor.execute("INSERT INTO counselling_responses (request_id) VALUES (%s) ON DUPLICATE KEY UPDATE request_id=request_id", (request_id,))
        db.commit(); return redirect(f"/student/feedback/{request_id}")
    except Exception as error:
        if db: db.rollback()
        flash(f"Unable to end chat: {error}", "danger"); return redirect(f"/student/reply/{request_id}")
    finally: _close(cursor, db)


@student.route("/student/feedback/<int:request_id>", methods=["GET", "POST"])
@login_required("student")
def student_feedback(request_id):
    db = cursor = None
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        if not _owns_request(cursor, request_id):
            flash("Counselling request not found.", "danger"); return redirect("/student/history")
        if request.method == "POST":
            feedback = request.form.get("feedback", "").strip(); rating = request.form.get("rating") or None
            if not feedback:
                flash("Feedback cannot be empty.", "danger"); return redirect(f"/student/feedback/{request_id}")
            cursor.execute("UPDATE counselling_responses SET student_feedback=%s, student_rating=%s WHERE request_id=%s", (feedback, rating, request_id))
            db.commit(); return redirect("/student/history")
        return render_template("student/feedback.html", request_id=request_id)
    except Exception as error:
        if db: db.rollback()
        flash(f"Unable to save feedback: {error}", "danger"); return redirect("/student/history")
    finally: _close(cursor, db)


@student.route("/student/send_counselling_request", methods=["GET", "POST"])
@login_required("student")
def student_send_counselling_request():
    # This legacy route is retained; its template name and behavior are unchanged.
    return student_request()
