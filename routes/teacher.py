from datetime import datetime
from io import BytesIO

from flask import Blueprint, flash, redirect, render_template, request, send_file, session
import openpyxl
import pandas as pd

from database import get_db
from routes.auth import login_required
from utils.ai import generate_response

teacher = Blueprint("teacher", __name__)


def _close(cursor, db):
    if cursor: cursor.close()
    if db: db.close()


def _teacher_id(cursor):
    cursor.execute("SELECT id FROM teachers WHERE user_id=%s", (session.get("user_id"),))
    row = cursor.fetchone()
    return row["id"] if row else None


def _owns_request(cursor, request_id):
    cursor.execute("""SELECT cr.id, cr.is_closed FROM counselling_requests cr JOIN students s ON cr.student_id=s.id
        JOIN teachers t ON s.assigned_teacher_id=t.id WHERE cr.id=%s AND t.user_id=%s""", (request_id, session.get("user_id")))
    return cursor.fetchone()


@teacher.route("/teacher/dashboard")
@login_required("teacher")
def teacher_dashboard():
    db = cursor = None
    try:
        db=get_db(); cursor=db.cursor(dictionary=True)
        cursor.execute("""SELECT COUNT(DISTINCT cr.id) AS new_count FROM counselling_requests cr JOIN students s ON cr.student_id=s.id
            JOIN teachers t ON s.assigned_teacher_id=t.id JOIN counselling_messages cm ON cm.request_id=cr.id
            WHERE t.user_id=%s AND cr.is_closed=0 AND cm.sender_role='student'""", (session.get("user_id"),))
        return render_template("teacher/dashboard.html", name=session.get("name", ""), new_messages=(cursor.fetchone() or {}).get("new_count", 0))
    except Exception as error:
        flash(f"Unable to load dashboard: {error}", "danger"); return redirect("/")
    finally: _close(cursor, db)


@teacher.route("/teacher/request", methods=["GET", "POST"])
@login_required("teacher")
def teacher_request():
    db=cursor=None
    try:
        db=get_db(); cursor=db.cursor(dictionary=True)
        cursor.execute("""SELECT cr.id, cr.problem, cr.category, u.UserName AS student_name FROM counselling_requests cr
            JOIN students s ON cr.student_id=s.id JOIN users u ON s.user_id=u.id JOIN teachers t ON s.assigned_teacher_id=t.id
            WHERE t.user_id=%s AND cr.is_closed=0""", (session.get("user_id"),)); requests=cursor.fetchall()
        ai_text=None; selected_request_id=request.form.get("request_id") if request.method == "POST" else None
        if selected_request_id and "generate_ai" in request.form and _owns_request(cursor, selected_request_id):
            cursor.execute("SELECT sender_role, message FROM counselling_messages WHERE request_id=%s ORDER BY created_at", (selected_request_id,))
            ai_text=generate_response("\n".join(f"{m['sender_role']}: {m['message']}" for m in cursor.fetchall()))
        return render_template("teacher/request.html", requests=requests, ai_text=ai_text, selected_request_id=selected_request_id, name=session.get("name", ""))
    except Exception as error:
        flash(f"Unable to load requests: {error}", "danger"); return redirect("/teacher/dashboard")
    finally: _close(cursor, db)


@teacher.route("/teacher/send_request", methods=["GET", "POST"])
@login_required("teacher")
def teacher_send_request():
    db=cursor=None
    try:
        db=get_db(); cursor=db.cursor(dictionary=True); teacher_id=_teacher_id(cursor)
        if not teacher_id:
            flash("Teacher profile not found.", "danger"); return redirect("/teacher/dashboard")
        cursor.execute("""SELECT s.id, u.UserName FROM students s JOIN users u ON s.user_id=u.id
            WHERE s.assigned_teacher_id=%s""", (teacher_id,)); students=cursor.fetchall()
        if request.method == "POST":
            student_id=request.form.get("student_id"); reason=request.form.get("reason", "").strip(); message=request.form.get("message", "").strip()
            if not student_id or not reason:
                flash("Please select a student and reason.", "danger"); return render_template("teacher/send_request.html", students=students, name=session.get("name", ""))
            cursor.execute("SELECT id FROM students WHERE id=%s AND assigned_teacher_id=%s", (student_id, teacher_id))
            if not cursor.fetchone():
                flash("The selected student is not assigned to you.", "danger"); return render_template("teacher/send_request.html", students=students, name=session.get("name", ""))
            cursor.execute("INSERT INTO teacher_counselling_requests (teacher_id, student_id, reason, message) VALUES (%s,%s,%s,%s)", (teacher_id, student_id, reason, message))
            db.commit(); return render_template("teacher/send_request.html", students=students, success="Counselling request sent successfully", name=session.get("name", ""))
        return render_template("teacher/send_request.html", students=students, name=session.get("name", ""))
    except Exception as error:
        if db: db.rollback()
        flash(f"Unable to send counselling request: {error}", "danger"); return redirect("/teacher/send_request")
    finally: _close(cursor, db)


@teacher.route("/teacher/teacher_requests")
@login_required("teacher")
def teacher_view_requests():
    db=cursor=None
    try:
        db=get_db(); cursor=db.cursor(dictionary=True)
        cursor.execute("""SELECT tcr.id, u.UserName AS student_name, tcr.reason, tcr.message, tcr.status, tcr.created_at, tcr.responded_at
            FROM teacher_counselling_requests tcr JOIN students s ON tcr.student_id=s.id JOIN users u ON s.user_id=u.id
            JOIN teachers t ON tcr.teacher_id=t.id WHERE t.user_id=%s ORDER BY tcr.created_at DESC""", (session.get("user_id"),))
        return render_template("teacher/teacher_requests.html", requests=cursor.fetchall(), name=session.get("name", ""))
    except Exception as error:
        flash(f"Unable to load counselling requests: {error}", "danger"); return redirect("/teacher/dashboard")
    finally: _close(cursor, db)


@teacher.route("/teacher/history")
@login_required("teacher")
def teacher_history():
    db=cursor=None
    try:
        db=get_db(); cursor=db.cursor(dictionary=True)
        cursor.execute("""SELECT DISTINCT cr.id AS request_id, u.UserName AS student_name, cr.problem, cr.category,
            CASE WHEN cr.is_closed=1 THEN 'Ended' WHEN cr.status='Teacher Responded' THEN 'Completed' ELSE 'Pending' END AS status,
            cr.is_closed, cr.created_at, (SELECT student_feedback FROM counselling_responses WHERE request_id=cr.id LIMIT 1) AS student_feedback,
            (SELECT student_rating FROM counselling_responses WHERE request_id=cr.id LIMIT 1) AS student_rating,
            COALESCE((SELECT MAX(cm.confidential) FROM counselling_messages cm WHERE cm.request_id=cr.id AND cm.sender_role='student'),0) AS confidential
            FROM counselling_requests cr JOIN students s ON cr.student_id=s.id JOIN users u ON s.user_id=u.id JOIN teachers t ON s.assigned_teacher_id=t.id
            WHERE t.user_id=%s ORDER BY cr.created_at DESC""", (session.get("user_id"),))
        return render_template("teacher/history.html", history=cursor.fetchall(), name=session.get("name", ""))
    except Exception as error:
        flash(f"Unable to load history: {error}", "danger"); return redirect("/teacher/dashboard")
    finally: _close(cursor, db)


@teacher.route("/teacher/reply/<int:request_id>", methods=["GET", "POST"])
@login_required("teacher")
def teacher_reply(request_id):
    db=cursor=None; ai_text=None
    try:
        db=get_db(); cursor=db.cursor(dictionary=True); counselling_request=_owns_request(cursor, request_id)
        if not counselling_request:
            flash("Counselling request not found.", "danger"); return redirect("/teacher/request")
        closed=counselling_request["is_closed"] or 0
        if request.method == "POST" and not closed:
            if "generate_ai" in request.form:
                cursor.execute("SELECT sender_role, message FROM counselling_messages WHERE request_id=%s ORDER BY created_at", (request_id,))
                ai_text=generate_response("\n".join(f"{m['sender_role']}: {m['message']}" for m in cursor.fetchall()))
            elif "send_reply" in request.form:
                message=request.form.get("message", "").strip()
                if not message:
                    flash("Reply cannot be empty.", "danger"); return redirect(f"/teacher/reply/{request_id}")
                cursor.execute("INSERT INTO counselling_messages (request_id, sender_role, message) VALUES (%s,'teacher',%s)", (request_id,message))
                cursor.execute("""INSERT INTO counselling_responses (request_id, teacher_response, completed_at) VALUES (%s,%s,%s)
                    ON DUPLICATE KEY UPDATE teacher_response=VALUES(teacher_response), completed_at=VALUES(completed_at)""", (request_id,message,datetime.now()))
                cursor.execute("UPDATE counselling_requests SET status='Teacher Responded' WHERE id=%s AND is_closed=0", (request_id,)); db.commit(); return redirect(f"/teacher/reply/{request_id}")
        cursor.execute("SELECT sender_role, message, created_at FROM counselling_messages WHERE request_id=%s ORDER BY created_at", (request_id,))
        return render_template("teacher/reply.html", messages=cursor.fetchall(), ai_text=ai_text, closed=closed, request_id=request_id, name=session.get("name", ""))
    except Exception as error:
        if request.method == "POST" and db: db.rollback()
        flash(f"Unable to load conversation: {error}", "danger"); return redirect("/teacher/request")
    finally: _close(cursor, db)


@teacher.route("/teacher/export_excel")
@login_required("teacher")
def export_excel():
    db=cursor=None
    try:
        db=get_db(); cursor=db.cursor(dictionary=True); teacher_id=_teacher_id(cursor)
        if not teacher_id:
            flash("Teacher profile not found.", "danger"); return redirect("/teacher/dashboard")
        cursor.execute("""SELECT u.UserName AS student_name, cr.problem, cr.category, cm.message, cm.created_at, cm.confidential,
            cres.teacher_response, cres.student_feedback, cres.student_rating, cm.request_id FROM counselling_messages cm
            JOIN counselling_requests cr ON cm.request_id=cr.id JOIN students s ON cr.student_id=s.id JOIN users u ON s.user_id=u.id
            LEFT JOIN counselling_responses cres ON cres.request_id=cr.id WHERE s.assigned_teacher_id=%s ORDER BY cm.request_id,cm.created_at""", (teacher_id,)); rows=cursor.fetchall()
        wb=openpyxl.Workbook(); ws=wb.active; ws.title="Counselling Report"
        ws.append(["Student Name","Problem","Category","Messages Combined","Counselling Date","Teacher Resolution","Student Feedback","Student Rating","AI Summary","Confidential"])
        grouped={}
        for row in rows:
            item=grouped.setdefault(row["request_id"], {"row":row,"messages":[],"confidential":0}); item["messages"].append(row["message"]); item["confidential"] |= bool(row["confidential"])
        for item in grouped.values():
            row=item["row"]; conversation="\n".join(item["messages"]); summary=generate_response(f"Summarize this counselling exchange in 3-5 human sentences.\n\nConversation:\n{conversation}\n\nSummary:")
            ws.append(["Anonymous Student" if item["confidential"] else row["student_name"],row["problem"],row["category"],conversation,row["created_at"].strftime("%Y-%m-%d %H:%M") if row["created_at"] else "",row["teacher_response"] or "",row["student_feedback"] or "",row["student_rating"] or "",summary,"YES" if item["confidential"] else "NO"])
        output=BytesIO(); wb.save(output); output.seek(0)
        return send_file(output, as_attachment=True, download_name="counselling_report.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as error:
        flash(f"Unable to export report: {error}", "danger"); return redirect("/teacher/history")
    finally: _close(cursor, db)


@teacher.route("/teacher/upload_performance", methods=["POST"])
@login_required("teacher")
def upload_performance():
    db=cursor=None
    try:
        file=request.files.get("excel_file")
        if not file or not file.filename: return render_template("teacher/dashboard.html", error="No file uploaded")
        if not file.filename.lower().endswith((".xlsx", ".xls")): return render_template("teacher/dashboard.html", error="Invalid file type. Upload .xlsx or .xls only")
        df=pd.read_excel(file,dtype=str); df.columns=[str(column).strip() for column in df.columns]
        required=["student_id","student_name","subject","marks","attendance_percentage"]
        if not all(column in df.columns for column in required): return render_template("teacher/dashboard.html", error=f"Excel columns mismatch. Found: {list(df.columns)}")
        db=get_db(); cursor=db.cursor(dictionary=True); teacher_id=_teacher_id(cursor)
        if not teacher_id: return render_template("teacher/dashboard.html", error="Teacher profile not found")
        for _,row in df.iterrows():
            if pd.isna(row["student_id"]): continue
            student_id=int(row["student_id"]); subject=str(row["subject"]).strip(); marks=int(float(row["marks"])); attendance=int(float(row["attendance_percentage"]))
            if not subject or not (0 <= marks <= 100 and 0 <= attendance <= 100): continue
            cursor.execute("SELECT id FROM students WHERE id=%s AND assigned_teacher_id=%s", (student_id, teacher_id))
            if not cursor.fetchone(): continue
            cursor.execute("""INSERT INTO student_performance (student_id,subject,marks,attendance_percentage) VALUES (%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE marks=VALUES(marks), attendance_percentage=VALUES(attendance_percentage)""", (student_id,subject,marks,attendance))
        db.commit(); return redirect("/teacher/performance")
    except Exception as error:
        if db: db.rollback()
        return render_template("teacher/dashboard.html", error=f"Upload failed: {error}")
    finally: _close(cursor, db)


@teacher.route("/teacher/performance")
@login_required("teacher")
def teacher_performance():
    db=cursor=None
    try:
        db=get_db(); cursor=db.cursor(dictionary=True); teacher_id=_teacher_id(cursor)
        if not teacher_id: flash("Teacher profile not found.", "danger"); return redirect("/teacher/dashboard")
        cursor.execute("""SELECT sp.student_id,u.UserName AS student_name,sp.subject,sp.marks,sp.attendance_percentage FROM student_performance sp
            JOIN students s ON sp.student_id=s.id JOIN users u ON s.user_id=u.id WHERE s.assigned_teacher_id=%s
            ORDER BY sp.marks ASC,sp.attendance_percentage ASC""", (teacher_id,)); rows=cursor.fetchall()
        for row in rows: row["category"]="Needs Counselling" if row["marks"] < 40 or row["attendance_percentage"] < 75 else "Average" if row["marks"] <= 70 else "Good"
        return render_template("teacher/performance.html", performances=rows, name=session.get("name", ""))
    except Exception as error:
        flash(f"Unable to load performance data: {error}", "danger"); return redirect("/teacher/dashboard")
    finally: _close(cursor, db)


@teacher.route("/teacher/performance/request/<int:student_id>")
@login_required("teacher")
def performance_counselling_request(student_id):
    return redirect(f"/teacher/send_request?student_id={student_id}&reason=Academic Performance / Attendance Concern")
