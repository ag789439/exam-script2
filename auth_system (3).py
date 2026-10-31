"""
Exam Script Flask role-based authentication module - PostgreSQL edition.
Roles: admin (full access), teacher, student.

This module and app.py share ONE database: both get their connection from
db.py, which reads DATABASE_URL. That is why a student created on the
Students page is immediately visible here - the "Admission number not
found" problem is gone.

Requires: Flask, psycopg[binary], Werkzeug.

INTEGRATE (already done in app.py):
    from auth_system import register_auth
    register_auth(app)

Render environment variables:
    DATABASE_URL    (same value app.py uses - Render sets it for you)
    SECRET_KEY      (permanent random secret; keep it private)
    ADMIN_USERNAME  (e.g. admin)
    ADMIN_PASSWORD  (strong password)

Admin pages:
    /admin/teachers  -> create teacher logins, or reset a teacher password
    /admin/students  -> set / reset a student password (by admission number)
Login:
    /login
Students use their admission number as the username.

Protect your own routes with:
    @login_required
or:
    @roles_required("admin", "teacher")
Admin automatically has access to every protected role area.
"""

import os
from functools import wraps

import psycopg
from flask import (Blueprint, abort, flash, redirect, render_template_string,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from db import connect as db_connect
from db import ensure_schema

auth = Blueprint("auth", __name__)

# The login page is public, so it carries the app name and the search-engine
# metadata too. Both are optional: without them the defaults below are used.
APP_NAME = os.environ.get("APP_NAME", "Exam Script")
GOOGLE_SITE_VERIFICATION = (
    os.environ.get("GOOGLE_SITE_VERIFICATION") or "").strip()

STYLE = """
<style>
body{margin:0;background:#0b1220;color:#edf2ff;font:15px Arial;min-height:100vh;
     display:grid;place-items:center;padding:22px}
.card{width:min(640px,100%);background:#142039;padding:28px;border:1px solid #30415f;border-radius:16px}
h1{margin-top:0}h3{margin:22px 0 8px}
p{color:#b7c5dc;line-height:1.5}
label{display:block;margin:15px 0 6px}
input,select{width:100%;box-sizing:border-box;padding:12px;border-radius:8px;
             border:1px solid #405475;background:#0c1729;color:white}
button{width:100%;margin-top:18px;padding:12px;border:0;border-radius:8px;
       background:#4778f5;color:white;font-weight:bold;cursor:pointer}
a{color:#9dbaff}
.msg{padding:10px;background:#3b301e;border-radius:8px}
.msg.ok{background:#123a2b}
.muted{color:#8fa3c0;font-size:13px}
table{width:100%;border-collapse:collapse;margin-top:10px;font-size:14px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid #26364f}
th{color:#8fa3c0;font-size:11px;text-transform:uppercase;letter-spacing:.04em}
.tag{font-size:11px;padding:2px 7px;border-radius:999px}
.tag.ok{background:#123a2b;color:#6ee7b7}
.tag.bad{background:#3b1e1e;color:#fca5a5}
</style>
"""

# Set by init_auth_db() the first time it runs in this process.
_admin_seeded = False


def _connect():
    """A connection to the same PostgreSQL database app.py uses."""
    return db_connect()


def init_auth_db():
    """Make sure the login tables/columns exist, then seed the admin.

    Non-destructive: no existing student, exam, subject, schedule or marks
    data is ever deleted or overwritten.
    """
    global _admin_seeded
    ensure_schema()

    if _admin_seeded:
        return
    username = (os.environ.get("ADMIN_USERNAME") or "admin").strip() or "admin"
    password = os.environ.get("ADMIN_PASSWORD")
    if password:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO auth_admins(username, password_hash)
                       VALUES(%s, %s)
                       ON CONFLICT (username) DO UPDATE
                       SET password_hash = EXCLUDED.password_hash""",
                    (username, generate_password_hash(password)),
                )
    _admin_seeded = True


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


# --------------------------------------------------------------------------
#  login / logout
# --------------------------------------------------------------------------
@auth.route("/login", methods=["GET", "POST"])
def login():
    try:
        init_auth_db()
    except Exception as exc:                       # noqa: BLE001
        flash(f"Database problem: {exc}")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "").strip()
        record = None

        with _connect() as conn:
            with conn.cursor() as cur:
                if role == "admin":
                    cur.execute(
                        "SELECT id, username, password_hash FROM auth_admins"
                        " WHERE lower(btrim(username)) = lower(btrim(%s))",
                        (username,))
                elif role == "teacher":
                    cur.execute(
                        "SELECT id, username, full_name, password_hash"
                        " FROM teachers"
                        " WHERE lower(btrim(username)) = lower(btrim(%s))",
                        (username,))
                elif role == "student":
                    # Admission numbers are matched ignoring case and spaces,
                    # so "adm 101", "ADM101" and "adm101" all work.
                    cur.execute(
                        """SELECT id, admission_no AS username,
                                  name AS full_name, password_hash
                           FROM students
                           WHERE lower(btrim(admission_no)) = lower(btrim(%s))""",
                        (username,))
                record = cur.fetchone()

        if record is None:
            if role == "student":
                flash("No student has that admission number. Ask the admin to "
                      "check the admission number on the Students page.")
            else:
                flash("No such account for the selected account type.")
        elif not record.get("password_hash"):
            flash("This account has no password yet. Ask the admin to set one "
                  "on the Student passwords page.")
        elif not check_password_hash(record["password_hash"], password):
            flash("Wrong password.")
        else:
            session.clear()
            session.update(user_id=record["id"],
                           username=record["username"],
                           display_name=record.get("full_name")
                           or record["username"],
                           role=role)
            target = request.args.get("next", "")
            if not target.startswith("/") or target.startswith("//"):
                target = "/student" if role == "student" else "/"
            return redirect(target)

    return render_template_string(
        """<!doctype html><html lang="en"><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{{ app_name }} · Log in</title>
        <meta name="description" content="{{ app_name }} — school examination
        management: students, exams, marks entry and results.">
        {% if verification %}<meta name="google-site-verification"
        content="{{ verification }}">{% endif %}
        </head><body>""" + STYLE + """
        <main class="card"><h1>{{ app_name }}</h1>
        <p>School examination management — sign in to your account.</p>
        {% for m in get_flashed_messages() %}<p class="msg">{{ m }}</p>{% endfor %}
        <form method="post">
        <label>Account type</label>
        <select name="role">
          <option value="student">Student</option>
          <option value="teacher">Teacher</option>
          <option value="admin">Admin</option>
        </select>
        <label>Username / Admission number</label>
        <input name="username" required autofocus autocomplete="username">
        <label>Password</label>
        <input type="password" name="password" required autocomplete="current-password">
        <button>Sign in</button></form>
        <p class="muted">Students: use your admission number. Ask the admin to
        set your password (admin menu &rarr; Student passwords).</p></main>
        </body></html>""",
        app_name=APP_NAME, verification=GOOGLE_SITE_VERIFICATION)


@auth.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


# --------------------------------------------------------------------------
#  admin: teacher accounts
# --------------------------------------------------------------------------
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
                with _connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """INSERT INTO teachers(username, full_name,
                                                    password_hash)
                               VALUES(%s, %s, %s)
                               ON CONFLICT (username) DO UPDATE
                               SET full_name = EXCLUDED.full_name,
                                   password_hash = EXCLUDED.password_hash""",
                            (username, name, generate_password_hash(password)))
                flash(f"Teacher account '{username}' saved "
                      f"(created, or password reset).")
            except psycopg.errors.UniqueViolation:
                flash("That username already exists.")

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT username, full_name FROM teachers"
                        " ORDER BY full_name")
            rows = cur.fetchall()

    return render_template_string(
        """<!doctype html><title>Teacher Accounts</title>""" + STYLE + """
        <main class="card"><h1>Teacher accounts</h1>
        {% for m in get_flashed_messages() %}<p class="msg">{{ m }}</p>{% endfor %}
        <form method="post">
        <label>Teacher full name</label><input name="full_name" required>
        <label>Username</label><input name="username" required>
        <label>Password (8+ characters)</label>
        <input type="password" name="password" minlength="8" required>
        <button>Create teacher / reset password</button></form>
        <h3>Current teachers ({{ rows|length }})</h3>
        {% if rows %}
        <table><thead><tr><th>Name</th><th>Username</th></tr></thead><tbody>
        {% for r in rows %}<tr><td>{{ r.full_name }}</td>
            <td>{{ r.username }}</td></tr>{% endfor %}
        </tbody></table>
        {% else %}<p class="muted">No teacher accounts yet.</p>{% endif %}
        <p class="muted"><a href="/">App home</a> ·
           <a href="/admin/students">Student passwords</a> ·
           <a href="/logout">Logout</a></p></main>""")


# --------------------------------------------------------------------------
#  admin: student passwords
# --------------------------------------------------------------------------
@auth.route("/admin/students", methods=["GET", "POST"])
@roles_required("admin")
def student_passwords():
    if request.method == "POST":
        admission = request.form.get("admission_no", "").strip()
        password = request.form.get("password", "")
        if not admission:
            flash("Enter the student's admission number.")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.")
        else:
            with _connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """UPDATE students SET password_hash = %s
                           WHERE lower(btrim(admission_no)) = lower(btrim(%s))
                           RETURNING admission_no, name""",
                        (generate_password_hash(password), admission))
                    found = cur.fetchone()
                conn.commit()
            if found:
                flash(f"Password saved for {found['name']} "
                      f"({found['admission_no']}).")
            else:
                flash(f"Admission number '{admission}' was not found in the "
                      f"students table. Check the list below - the number must "
                      f"match exactly.")

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT admission_no, name, class_name, section,
                          (password_hash IS NOT NULL) AS has_password
                   FROM students
                   ORDER BY class_name, admission_no
                   LIMIT 500""")
            rows = cur.fetchall()
            cur.execute("SELECT COUNT(*) AS c FROM students")
            total = cur.fetchone()["c"]

    return render_template_string(
        """<!doctype html><title>Student Login Setup</title>""" + STYLE + """
        <main class="card"><h1>Student login setup</h1>
        <p>Set or reset the password a student uses with their admission
           number.</p>
        {% for m in get_flashed_messages() %}<p class="msg">{{ m }}</p>{% endfor %}
        <form method="post">
        <label>Admission number</label>
        <input name="admission_no" list="admission-list" required
               placeholder="type or pick from the list">
        <datalist id="admission-list">
          {% for r in rows %}<option value="{{ r.admission_no }}">{{ r.name }}</option>{% endfor %}
        </datalist>
        <label>New password (8+ characters)</label>
        <input type="password" name="password" minlength="8" required>
        <button>Save password</button></form>

        <h3>Students in the database ({{ total }}{% if total > rows|length %},
            showing first {{ rows|length }}{% endif %})</h3>
        {% if rows %}
        <table><thead><tr><th>Admission No</th><th>Name</th><th>Class</th>
              <th>Password</th></tr></thead><tbody>
        {% for r in rows %}
          <tr><td>{{ r.admission_no }}</td><td>{{ r.name }}</td>
              <td>{{ r.class_name }}{% if r.section %} - {{ r.section }}{% endif %}</td>
              <td>{% if r.has_password %}<span class="tag ok">set</span>
                  {% else %}<span class="tag bad">not set</span>{% endif %}</td></tr>
        {% endfor %}
        </tbody></table>
        {% else %}
        <p class="msg">The students table is empty. Add students on the
           <a href="/students">Students</a> page first.</p>
        {% endif %}
        <p class="muted"><a href="/">App home</a> ·
           <a href="/admin/teachers">Teacher accounts</a> ·
           <a href="/logout">Logout</a></p></main>""", rows=rows, total=total)


# --------------------------------------------------------------------------
#  registration
# --------------------------------------------------------------------------
def register_auth(app, get_db=None):
    """Attach the login blueprint to the Flask app.

    get_db is accepted for backwards compatibility; this module gets its
    connections from db.py, i.e. from the same DATABASE_URL as app.py.
    """
    if not app.secret_key:
        app.secret_key = os.environ.get("SECRET_KEY")
    if not app.secret_key:
        raise RuntimeError("Set SECRET_KEY in Render > Environment.")

    # Secure cookies need https. Render serves https, so this is on there;
    # for local http testing set SESSION_COOKIE_SECURE=0.
    secure = os.environ.get("SESSION_COOKIE_SECURE")
    if secure is None:
        secure = "0" if not os.environ.get("RENDER") else "1"
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=str(secure).lower() not in ("0", "false", "no"),
    )

    app.register_blueprint(auth)

    with app.app_context():
        try:
            init_auth_db()
        except Exception as exc:                   # noqa: BLE001
            app.logger.error("Login tables could not be prepared yet: %s", exc)
