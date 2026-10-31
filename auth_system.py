"""
ExamPro Flask role-based authentication module.
Roles: admin (full access), teacher, student.
Existing students table is preserved; only password_hash is added.
Requires: Flask, psycopg[binary], Werkzeug.

INTEGRATE in app.py after app and get_db() are defined:
    from auth_system import register_auth
    register_auth(app, get_db)

Render environment variables:
    DATABASE_URL   (keep your existing value)
    SECRET_KEY     (permanent random secret; keep private)
    ADMIN_USERNAME (e.g. admin)
    ADMIN_PASSWORD (strong password)

Admin pages:
    /admin/teachers  -> create teacher logins
    /admin/students  -> set/reset student passwords
Login:
    /login
Students use admission number as username.
Protect your existing routes with:
    @login_required
or:
    @roles_required("admin", "teacher")
Admin automatically has access to every protected role area.
"""

import os
from functools import wraps

import psycopg
from psycopg.rows import dict_row
from flask import Blueprint, abort, flash, redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

auth = Blueprint("auth", __name__)

STYLE = """
<style>
body{margin:0;background:#0b1220;color:#edf2ff;font:15px Arial;min-height:100vh;display:grid;place-items:center;padding:22px}
.card{width:min(480px,100%);background:#142039;padding:28px;border:1px solid #30415f;border-radius:16px}
h1{margin-top:0}p{color:#b7c5dc;line-height:1.5}label{display:block;margin:15px 0 6px}
input{width:100%;box-sizing:border-box;padding:12px;border-radius:8px;border:1px solid #405475;background:#0c1729;color:white}
button{width:100%;margin-top:18px;padding:12px;border:0;border-radius:8px;background:#4778f5;color:white;font-weight:bold}
a{color:#9dbaff}.msg{padding:10px;background:#3b301e;border-radius:8px}
</style>
"""

def db():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is missing in Render Environment.")
    return psycopg.connect(url, row_factory=dict_row)

def init_auth_db():
    # Non-destructive: no existing student/exam/marks data is deleted.
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE students ADD COLUMN IF NOT EXISTS password_hash TEXT")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS teachers(
                    id BIGSERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    full_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS auth_admins(
                    id BIGSERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL
                )
            """)
            username = os.environ.get("ADMIN_USERNAME", "admin").strip()
            password = os.environ.get("ADMIN_PASSWORD")
            if password:
                cur.execute(
                    """INSERT INTO auth_admins(username,password_hash)
                       VALUES(%s,%s)
                       ON CONFLICT(username) DO UPDATE
                       SET password_hash=EXCLUDED.password_hash""",
                    (username, generate_password_hash(password)),
                )
        conn.commit()

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login", next=request.path))
        return fn(*args, **kwargs)
    return wrapped

def roles_required(*roles):
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not session.get("user_id"):
                return redirect(url_for("auth.login", next=request.path))
            if session.get("role") != "admin" and session.get("role") not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return decorate

@auth.route("/login", methods=["GET", "POST"])
def login():
    init_auth_db()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "")
        record = None
        with db() as conn:
            with conn.cursor() as cur:
                if role == "admin":
                    cur.execute("SELECT id,username,password_hash FROM auth_admins WHERE username=%s", (username,))
                elif role == "teacher":
                    cur.execute("SELECT id,username,full_name,password_hash FROM teachers WHERE username=%s", (username,))
                elif role == "student":
                    cur.execute("""SELECT id,admission_no AS username,name AS full_name,password_hash
                                   FROM students WHERE admission_no=%s""", (username,))
                else:
                    cur.execute("SELECT NULL WHERE FALSE")
                record = cur.fetchone()
        if record and record.get("password_hash") and check_password_hash(record["password_hash"], password):
            session.clear()
            session.update(user_id=record["id"], username=record["username"],
                           display_name=record.get("full_name", record["username"]), role=role)
            target = request.args.get("next", "/")
            if not target.startswith("/") or target.startswith("//"):
                target = "/"
            return redirect(target)
        flash("Invalid login details or account type.")
    return render_template_string("""
    <!doctype html><title>ExamPro Login</title>""" + STYLE + """
    <main class="card"><h1>ExamPro Login</h1><p>Sign in to your school account.</p>
    {% for m in get_flashed_messages() %}<p class="msg">{{m}}</p>{% endfor %}
    <form method="post">
    <label>Account type</label><select name="role">
      <option value="student">Student</option><option value="teacher">Teacher</option><option value="admin">Admin</option>
    </select>
    <label>Username / Admission number</label><input name="username" required>
    <label>Password</label><input type="password" name="password" required>
    <button>Sign in</button></form><p>Students: use your admission number. Ask the admin to set your password.</p></main>
    """)

@auth.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))

@auth.route("/admin/teachers", methods=["GET", "POST"])
@roles_required("admin")
def teachers():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")
        if not username or not name or len(password) < 8:
            flash("Fill all fields; password must be at least 8 characters.")
        else:
            try:
                with db() as conn:
                    with conn.cursor() as cur:
                        cur.execute("INSERT INTO teachers(username,full_name,password_hash) VALUES(%s,%s,%s)",
                                    (username, name, generate_password_hash(password)))
                    conn.commit()
                flash("Teacher account created.")
            except psycopg.errors.UniqueViolation:
                flash("That username already exists.")
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT username,full_name FROM teachers ORDER BY full_name")
            rows = cur.fetchall()
    return render_template_string("""
    <!doctype html><title>Teacher Accounts</title>""" + STYLE + """
    <main class="card"><h1>Teacher accounts</h1>{% for m in get_flashed_messages() %}<p class="msg">{{m}}</p>{% endfor %}
    <form method="post"><label>Teacher full name</label><input name="full_name" required>
    <label>Username</label><input name="username" required>
    <label>Password (8+ characters)</label><input type="password" name="password" minlength="8" required>
    <button>Create teacher</button></form><h3>Current teachers</h3>
    {% for r in rows %}<p>{{r.full_name}} — {{r.username}}</p>{% endfor %}
    <p><a href="/">App home</a> · <a href="/logout">Logout</a></p></main>
    """, rows=rows)

@auth.route("/admin/students", methods=["GET", "POST"])
@roles_required("admin")
def student_passwords():
    if request.method == "POST":
        admission = request.form.get("admission_no", "").strip()
        password = request.form.get("password", "")
        if not admission or len(password) < 8:
            flash("Enter admission number and password of at least 8 characters.")
        else:
            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""UPDATE students SET password_hash=%s WHERE admission_no=%s
                                   RETURNING admission_no""",
                                (generate_password_hash(password), admission))
                    found = cur.fetchone()
                conn.commit()
            flash("Student password saved." if found else "Admission number not found.")
    return render_template_string("""
    <!doctype html><title>Student Login Setup</title>""" + STYLE + """
    <main class="card"><h1>Student login setup</h1><p>Set or reset a password for an existing student.</p>
    {% for m in get_flashed_messages() %}<p class="msg">{{m}}</p>{% endfor %}
    <form method="post"><label>Admission number</label><input name="admission_no" required>
    <label>New password (8+ characters)</label><input type="password" name="password" minlength="8" required>
    <button>Save password</button></form><p><a href="/">App home</a> · <a href="/logout">Logout</a></p></main>
    """)

def register_auth(app, get_db=None):
    # Use a stable SECRET_KEY from Render so sessions survive restarts.
    if not app.secret_key:
        app.secret_key = os.environ.get("SECRET_KEY")
    if not app.secret_key:
        raise RuntimeError("Set SECRET_KEY in Render > Environment.")
    app.config.update(SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE="Lax",
                      SESSION_COOKIE_SECURE=True)
    app.register_blueprint(auth)
    with app.app_context():
        init_auth_db()
