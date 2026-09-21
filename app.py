from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
import os
import datetime
import io
import pandas as pd
from database import get_db_connection

app = Flask(__name__)
app.secret_key = "anna_univ_tirunelveli_secret_key"

# Upload configurations
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5 MB limit
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 1. Homepage
@app.route("/")
def home():
    return render_template("index.html")

# 2. Student Leave Application Form (No Login Required)
@app.route("/apply-leave", methods=["GET", "POST"])
def apply_leave():
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        if request.method == "POST":
            student_name = request.form.get("student_name", "").strip()
            register_no = request.form.get("register_no", "").strip().upper()
            department_id = request.form.get("department_id")
            hostel_id = request.form.get("hostel_id")
            room_no = request.form.get("room_no", "").strip()
            year_of_study = request.form.get("year_of_study")
            semester = request.form.get("semester")
            student_phone = request.form.get("student_phone", "").strip()
            email = request.form.get("email", "").strip()
            father_name = request.form.get("father_name", "").strip()
            mother_name = request.form.get("mother_name", "").strip()
            parent_contact = request.form.get("parent_contact", "").strip()
            home_address = request.form.get("home_address", "").strip()

            application_type = request.form.get("application_type")
            from_date = request.form.get("from_date")
            to_date = request.form.get("to_date")
            departure_time = request.form.get("departure_time") or None
            expected_return_time = request.form.get("expected_return_time") or None
            purpose = request.form.get("purpose", "").strip()
            destination = request.form.get("destination", "").strip()

            # Upsert student details
            cur.execute("""
                INSERT INTO student (
                    register_no, student_name, email, student_phone, department_id,
                    hostel_id, room_no, year_of_study, semester, father_name,
                    mother_name, parent_contact, home_address
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (register_no) DO UPDATE SET
                    student_name = EXCLUDED.student_name,
                    room_no = EXCLUDED.room_no,
                    semester = EXCLUDED.semester,
                    parent_contact = EXCLUDED.parent_contact,
                    home_address = EXCLUDED.home_address
                RETURNING student_id;
            """, (
                register_no, student_name, email, student_phone, department_id,
                hostel_id, room_no, year_of_study, semester, father_name,
                mother_name, parent_contact, home_address
            ))
            student_id = cur.fetchone()["student_id"]

            # Generate Application Number (e.g., EL20260001)
            cur.execute("SELECT COALESCE(MAX(leave_id), 0) + 1 AS next_id FROM leave_application;")
            next_id = cur.fetchone()["next_id"]
            app_number = f"EL{datetime.date.today().year}{next_id:04d}"

            d1 = datetime.datetime.strptime(from_date, "%Y-%m-%d").date()
            d2 = datetime.datetime.strptime(to_date, "%Y-%m-%d").date() if to_date else d1
            number_of_days = max(1, (d2 - d1).days + 1)

            # Insert Application
            cur.execute("""
                INSERT INTO leave_application (
                    application_number, student_id, application_type, from_date, to_date,
                    number_of_days, departure_time, expected_return_time, home_address,
                    destination, purpose, parent_name, parent_contact
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING leave_id;
            """, (
                app_number, student_id, application_type, from_date, to_date,
                number_of_days, departure_time, expected_return_time, home_address,
                destination, purpose, father_name or mother_name, parent_contact
            ))
            leave_id = cur.fetchone()["leave_id"]

            # File upload for working-day leave
            file = request.files.get("advisor_hod_proof")
            if application_type == "WORKING_DAY" and file and allowed_file(file.filename):
                filename = secure_filename(f"{app_number}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                cur.execute("""
                    INSERT INTO leave_document (leave_id, document_type, file_name, file_path)
                    VALUES (%s, 'CLASS_ADVISOR_HOD_APPROVAL', %s, %s);
                """, (leave_id, filename, filepath))

            conn.commit()
            flash(f"Application submitted successfully! Your Tracking ID is {app_number}", "success")
            return redirect(url_for("track_leave", app_no=app_number))

        # Fetch hostels and the departments
        cur.execute("SELECT * FROM hostel ORDER BY hostel_id;")
        hostels = cur.fetchall()
        cur.execute("SELECT * FROM department ORDER BY department_id;")
        departments = cur.fetchall()
        return render_template("leave_form.html", hostels=hostels, departments=departments)
    finally:
        cur.close()
        conn.close()

# 3. Application Tracking & Digital Pass View
@app.route("/track", methods=["GET", "POST"])
def track_leave():
    app_no = request.args.get("app_no", "").strip().upper()
    leave_data = None
    pass_data = None

    if request.method == "POST":
        app_no = request.form.get("application_number", "").strip().upper()

    if app_no:
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT la.*, s.student_name, s.register_no, s.room_no, h.hostel_name, d.department_name, d.department_code
                FROM leave_application la
                JOIN student s ON la.student_id = s.student_id
                JOIN hostel h ON s.hostel_id = h.hostel_id
                JOIN department d ON s.department_id = d.department_id
                WHERE UPPER(TRIM(la.application_number)) = %s;
            """, (app_no,))
            leave_data = cur.fetchone()

            if leave_data and leave_data["status"] == "APPROVED":
                cur.execute("SELECT * FROM leave_pass WHERE leave_id = %s;", (leave_data["leave_id"],))
                pass_data = cur.fetchone()
        finally:
            cur.close()
            conn.close()

    return render_template("track.html", leave=leave_data, leave_pass=pass_data, app_no=app_no)

# 4. Staff Login (Direct Matching & Hash Verification)
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip().upper()
        password = request.form.get("password", "").strip()

        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT u.user_id, u.username, u.password_hash, u.role, u.is_active,
                       COALESCE(s.staff_id, u.staff_id) AS staff_id,
                       COALESCE(s.staff_name, u.role) AS staff_name,
                       s.hostel_id
                FROM user_account u
                LEFT JOIN staff s ON u.staff_id = s.staff_id
                WHERE UPPER(TRIM(u.username)) = %s AND u.is_active = TRUE;
            """, (username,))
            user = cur.fetchone()
        finally:
            cur.close()
            conn.close()

        password_matched = False
        if user:
            stored_val = str(user["password_hash"]).strip()
            
            # Match 1: Staff ID entered as password (PDW0001 == PDW0001)
            if password.upper() == user["username"].upper():
                password_matched = True
            # Match 2: Direct string match with database value
            elif stored_val == password:
                password_matched = True
            # Match 3: Secure cryptographic hash check
            else:
                try:
                    if check_password_hash(stored_val, password):
                        password_matched = True
                except Exception:
                    pass

        if user and password_matched:
            session["user_id"] = user["user_id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["staff_id"] = user["staff_id"] or user["user_id"]
            session["staff_name"] = user["staff_name"]

            # Role redirection
            if "POTHIGAI" in user["role"]:
                return redirect(url_for("pothigai_dashboard"))
            elif "THAMIRABARANI" in user["role"]:
                return redirect(url_for("thamirabarani_dashboard"))
            elif "EXECUTIVE" in user["role"]:
                return redirect(url_for("executive_dashboard"))
            elif "DEAN" in user["role"]:
                return redirect(url_for("dean_dashboard"))
        else:
            flash("Invalid credentials. Please verify your Staff ID and Password.", "danger")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Successfully signed out.", "info")
    return redirect(url_for("login"))

# 5. Pothigai Deputy Warden Dashboard
@app.route("/dashboard/pothigai")
def pothigai_dashboard():
    if not session.get("role") or "POTHIGAI" not in session.get("role"):
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM v_pothigai_applications ORDER BY submitted_at DESC;")
        applications = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    return render_template("pothigai_dashboard.html", applications=applications)

# 6. Thamirabarani Deputy Warden Dashboard
@app.route("/dashboard/thamirabarani")
def thamirabarani_dashboard():
    if not session.get("role") or "THAMIRABARANI" not in session.get("role"):
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM v_thamirabarani_applications ORDER BY submitted_at DESC;")
        applications = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    return render_template("thamirabarani_dashboard.html", applications=applications)

# 7. Executive Warden Dashboard
@app.route("/dashboard/executive")
def executive_dashboard():
    if not session.get("role") or "EXECUTIVE" not in session.get("role"):
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT la.*, s.student_name, s.register_no, s.room_no, h.hostel_name, d.department_code
            FROM leave_application la
            JOIN student s ON la.student_id = s.student_id
            JOIN hostel h ON s.hostel_id = h.hostel_id
            JOIN department d ON s.department_id = d.department_id
            ORDER BY la.submitted_at DESC;
        """)
        applications = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    return render_template("executive_dashboard.html", applications=applications)

# 8. Dean Dashboard
@app.route("/dashboard/dean")
def dean_dashboard():
    if not session.get("role") or "DEAN" not in session.get("role"):
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT la.*, s.student_name, s.register_no, s.room_no, h.hostel_name, d.department_code
            FROM leave_application la
            JOIN student s ON la.student_id = s.student_id
            JOIN hostel h ON s.hostel_id = h.hostel_id
            JOIN department d ON s.department_id = d.department_id
            ORDER BY la.submitted_at DESC;
        """)
        applications = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    return render_template("dean_dashboard.html", applications=applications)

# 9. Approval Action Route (Fires Database Triggers)
@app.route("/approve-leave/<int:leave_id>", methods=["POST"])
def approve_leave(leave_id):
    if not session.get("role") or ("DEPUTY_WARDEN" not in session.get("role")):
        return redirect(url_for("login"))

    decision = request.form.get("decision")
    remarks = request.form.get("remarks", "Processed by Deputy Warden")
    staff_id = session.get("staff_id")

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO approval (leave_id, staff_id, decision, remarks)
            VALUES (%s, %s, %s, %s);
        """, (leave_id, staff_id, decision, remarks))
        conn.commit()
    finally:
        cur.close()
        conn.close()

    flash(f"Application marked as {decision}.", "success")
    return redirect(request.referrer or url_for("home"))

# 10. Excel Export Route
@app.route("/export-excel")
def export_excel():
    if not session.get("role") or session.get("role") not in ["EXECUTIVE_WARDEN", "DEAN"]:
        return redirect(url_for("login"))

    conn = get_db_connection()
    try:
        query = "SELECT * FROM v_excel_leave_report;"
        df = pd.read_sql_query(query, conn)
    finally:
        conn.close()

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Hostel Leaves')
    output.seek(0)

    filename = f"AURCT_Hostel_Leaves_{datetime.date.today()}.xlsx"
    return send_file(
        output,
        download_name=filename,
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

if __name__ == "__main__":
    # host='0.0.0.0' binds to all network adapters so phones on your Wi-Fi can connect
    app.run(host="0.0.0.0", port=5000, debug=True)