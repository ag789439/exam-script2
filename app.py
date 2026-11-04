"""
==========================================================================
 EXAM MANAGER  -  web edition  (Flask + SQLite)
--------------------------------------------------------------------------
 The same examination module as the desktop app, but running in a browser
 so it can be deployed (Render / Railway / PythonAnywhere) and opened from
 any device.

 Pages
   Dashboard   counts, recent admissions, exams
   Students    admission + student master data
   Exams       exam master (the exam type is the exam's name)
   Subjects    subject master
   Schedule    one paper per subject with max / pass marks
   Marks       bulk marks entry per exam + subject
   Results     total, percentage, grade, rank, pass/fail + CSV export

 Environment variables
   APP_PASSWORD   if set, a login screen is required (strongly recommended)
   SCHOOL_NAME    name shown in the header
   SECRET_KEY     session signing key (set this in production)
   DB_PATH        where the SQLite file lives (default: next to app.py)

 Run locally
   pip install -r requirements.txt
   python app.py            ->  http://127.0.0.1:5000
==========================================================================
"""

import base64
import calendar as pycalendar
import csv
import io
import json
import os
import secrets
import sqlite3
import traceback
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from flask import (Flask, Response, abort, flash, g, redirect,
                   render_template, render_template_string, request, session,
                   url_for)
from jinja2 import DictLoader
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH") or os.path.join(BASE_DIR, "exam_manager.db")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "").strip()
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin").strip() or "admin"
ADMIN_PASSWORD = (os.environ.get("ADMIN_PASSWORD", "").strip()
                  or os.environ.get("APP_PASSWORD", "").strip())
SCHOOL_NAME = os.environ.get("SCHOOL_NAME", "Euphoric World School").strip() or "Euphoric World School"
APP_NAME = os.environ.get("APP_NAME", "Euphoric World ERP").strip() or "Euphoric World ERP"

# Optional cloud database. Set TURSO_URL (and TURSO_TOKEN) and the data is
# stored there instead of in a local file - which is what makes it survive a
# restart on a host with an ephemeral disk (Render's free plan, for example).
TURSO_URL = os.environ.get("TURSO_URL", "").strip()
TURSO_TOKEN = os.environ.get("TURSO_TOKEN", "").strip()


# ==========================================================================
#  BUILT-IN ASSETS
#  Pages, stylesheet and icon live inside this file, so the app is ONE
#  file to deploy - no templates/ or static/ folder that can go missing.
# ==========================================================================
TEMPLATES = {
    'welcome.html':
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>Exam Script 2 — Examination Management Software for Schools</title>\n<meta name="description" content="Exam Script 2 is a school examination management app: student admission records, exam scheduling, marks entry and result sheets with grades and rank. Works in any browser, no installation.">\n<meta name="keywords" content="Exam Script 2, examination management software, school exam software, marks entry, result sheet, report card software India">\n<meta property="og:title" content="Exam Script 2 — Examination Management for Schools">\n<meta property="og:description" content="Students, exams, exam schedule, marks entry and results with grades and rank — in one browser app.">\n<meta property="og:type" content="website">\n<link rel="stylesheet" href="{{ url_for(\'static\', filename=\'style.css\') }}">\n<link rel="icon" href="{{ url_for(\'static\', filename=\'icon.png\') }}">\n<script type="application/ld+json">\n{\n  "@context": "https://schema.org",\n  "@type": "SoftwareApplication",\n  "name": "Exam Script 2",\n  "applicationCategory": "BusinessApplication",\n  "operatingSystem": "Any (web browser)",\n  "description": "School examination management: student records, exam schedule, marks entry and result sheets with percentage, grades and rank.",\n  "offers": {"@type": "Offer", "price": "0", "priceCurrency": "INR"}\n}\n</script>\n</head>\n<body class="landing-body">\n\n<header class="landing-nav">\n  <div class="landing-wrap nav-inner">\n    <div class="brand-inline">\n      <div class="badge">EX</div>\n      <strong>Exam Script 2</strong>\n    </div>\n    <nav>\n      <a href="#features">Features</a>\n      <a href="#how">How it works</a>\n      <a class="btn primary small" href="{{ url_for(\'login\') }}">Staff login</a>\n    </nav>\n  </div>\n</header>\n\n<section class="hero">\n  <div class="landing-wrap">\n    <p class="eyebrow">Examination management, simplified</p>\n    <h1>Exam Script 2</h1>\n    <p class="lead">\n      One place for a school\'s whole examination cycle — student admission\n      records, the exam schedule, marks entry, and result sheets with\n      percentage, grades and rank. Runs in the browser, nothing to install.\n    </p>\n    <div class="hero-actions">\n      <a class="btn primary" href="{{ url_for(\'login\') }}">Staff login</a>\n      <a class="btn ghost" href="#features">See what it does</a>\n    </div>\n    <p class="tiny muted">Access is by account only — every teacher sees their own\n      class data, and an admin sees the whole school.</p>\n  </div>\n</section>\n\n<section id="features" class="landing-section">\n  <div class="landing-wrap">\n    <h2>What it does</h2>\n    <div class="feature-grid">\n      <article class="feature">\n        <h3>Students</h3>\n        <p>Admission number, roll number, class, section, date of admission,\n           parents\' details, phone and email. Search, edit and export to CSV.</p>\n      </article>\n      <article class="feature">\n        <h3>Exams</h3>\n        <p>Create exams by type — unit test, mid term, half yearly, annual,\n           pre-board, practical — for a class and academic year.</p>\n      </article>\n      <article class="feature">\n        <h3>Exam schedule</h3>\n        <p>One paper per subject with date, start time, duration, hall,\n           invigilator, maximum marks and pass marks.</p>\n      </article>\n      <article class="feature">\n        <h3>Marks entry</h3>\n        <p>Pick an exam and subject, fill the whole sheet in one screen.\n           Out-of-range entries are refused automatically.</p>\n      </article>\n      <article class="feature">\n        <h3>Results</h3>\n        <p>Total, percentage, CBSE-style grade, failed subjects, pass or fail,\n           and rank — with ties handled. Export the result sheet to CSV.</p>\n      </article>\n      <article class="feature">\n        <h3>Accounts</h3>\n        <p>Each teacher logs in with their own username and password and sees\n           only their own records. One admin account oversees everything.</p>\n      </article>\n    </div>\n  </div>\n</section>\n\n<section id="how" class="landing-section alt">\n  <div class="landing-wrap">\n    <h2>How it works</h2>\n    <ol class="steps">\n      <li><strong>Create the subjects</strong> for a class — or load a standard set.</li>\n      <li><strong>Add the students</strong> with their admission details.</li>\n      <li><strong>Create the exam</strong> and schedule one paper per subject.</li>\n      <li><strong>Enter the marks</strong> subject by subject.</li>\n      <li><strong>Generate the results</strong> and export the sheet.</li>\n    </ol>\n    <p class="muted">Built for schools that want something simple and offline-friendly\n      instead of a heavyweight ERP.</p>\n  </div>\n</section>\n\n<section class="landing-cta">\n  <div class="landing-wrap">\n    <h2>Already have an account?</h2>\n    <p>Sign in to open your dashboard.</p>\n    <a class="btn primary" href="{{ url_for(\'login\') }}">Staff login</a>\n  </div>\n</section>\n\n<footer class="landing-foot">\n  <div class="landing-wrap">\n    <span>Exam Script 2 · examination management for schools</span>\n    <span class="muted">Data stays on the school\'s own server · no advertising, no tracking</span>\n  </div>\n</footer>\n\n</body>\n</html>\n',
    'base.html':
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<meta name="robots" content="noindex, nofollow">\n<link rel="manifest" href="{{ url_for(\'manifest\') }}">\n  <title>{% block title %}Dashboard{% endblock %} · {{ school_name }}</title>\n<link rel="stylesheet" href="{{ url_for(\'static\', filename=\'style.css\') }}">\n<link rel="icon" href="{{ url_for(\'static\', filename=\'icon.png\') }}">\n</head>\n<body>\n<div class="shell">\n  <aside class="sidebar">\n    <div class="brand">\n      {% if school_logo %}<img class="badge-logo" src="{{ school_logo }}" alt="">\n      {% else %}<div class="badge">EX</div>{% endif %}\n      <div class="brand-text">\n        <strong>{{ app_name }}</strong>\n        <span>{{ school_name }}</span>\n      </div>\n    </div>\n    <nav>\n      {% if current_user and current_user.role == \'student\' %}\n      <a href="{{ url_for(\'my_home\') }}" class="{{ \'active\' if request.endpoint == \'my_home\' }}">Dashboard</a>\n      <a href="{{ url_for(\'my_attendance\') }}" class="{{ \'active\' if request.endpoint == \'my_attendance\' }}">My attendance</a>\n      <a href="{{ url_for(\'my_homework\') }}" class="{{ \'active\' if request.endpoint == \'my_homework\' }}">Homework</a>\n      <a href="{{ url_for(\'my_timetable\') }}" class="{{ \'active\' if request.endpoint == \'my_timetable\' }}">Timetable</a>\n      <a href="{{ url_for(\'my_result\') }}" class="{{ \'active\' if request.endpoint == \'my_result\' }}">Result</a>\n      <a href="{{ url_for(\'my_fees\') }}" class="{{ \'active\' if request.endpoint == \'my_fees\' }}">My fees</a>\n      <a href="{{ url_for(\'my_transport\') }}" class="{{ \'active\' if request.endpoint == \'my_transport\' }}">Transport</a>\n      <a href="{{ url_for(\'my_library\') }}" class="{{ \'active\' if request.endpoint == \'my_library\' }}">Library</a>\n      <a href="{{ url_for(\'notices\') }}" class="{{ \'active\' if request.endpoint == \'notices\' }}">Notice</a>\n      <a href="{{ url_for(\'events\') }}" class="{{ \'active\' if request.endpoint == \'events\' }}">Calendar</a>\n      <a href="{{ url_for(\'my_leave\') }}" class="{{ \'active\' if request.endpoint == \'my_leave\' }}">Leave</a>\n      <a href="{{ url_for(\'my_profile\') }}" class="{{ \'active\' if request.endpoint == \'my_profile\' }}">Personal info</a>\n      <a href="{{ url_for(\'password\') }}" class="{{ \'active\' if request.endpoint == \'password\' }}">Password</a>\n      {% else %}\n      <a href="{{ url_for(\'dashboard\') }}" class="{{ \'active\' if request.endpoint == \'dashboard\' }}">Dashboard</a>\n      <a href="{{ url_for(\'students\') }}" class="{{ \'active\' if request.endpoint and request.endpoint.startswith(\'student\') }}">Students</a>\n      <a href="{{ url_for(\'exams\') }}" class="{{ \'active\' if request.endpoint and request.endpoint.startswith(\'exam\') }}">Exams</a>\n      <a href="{{ url_for(\'subjects\') }}" class="{{ \'active\' if request.endpoint and request.endpoint.startswith(\'subject\') }}">Subjects</a>\n      <a href="{{ url_for(\'schedule\') }}" class="{{ \'active\' if request.endpoint and request.endpoint.startswith(\'schedule\') }}">Exam schedule</a>\n      <a href="{{ url_for(\'attendance\') }}" class="{{ \'active\' if request.endpoint == \'attendance\' }}">Attendance</a>\n      <a href="{{ url_for(\'leave\') }}" class="{{ \'active\' if request.endpoint == \'leave\' }}">Leave</a>\n      <a href="{{ url_for(\'timetable\') }}" class="{{ \'active\' if request.endpoint == \'timetable\' }}">Timetable</a>\n      <a href="{{ url_for(\'homework\') }}" class="{{ \'active\' if request.endpoint == \'homework\' }}">Homework</a>\n      <a href="{{ url_for(\'marks\') }}" class="{{ \'active\' if request.endpoint == \'marks\' }}">Marks entry</a>\n      <a href="{{ url_for(\'results\') }}" class="{{ \'active\' if request.endpoint and request.endpoint.startswith(\'results\') }}">Results</a>\n      <a href="{{ url_for(\'fees\') }}" class="{{ \'active\' if request.endpoint and request.endpoint.startswith(\'fee\') }}">Fees</a>\n      <a href="{{ url_for(\'circulars\') }}" class="{{ \'active\' if request.endpoint == \'circulars\' }}">Circulars</a>\n      <a href="{{ url_for(\'events\') }}" class="{{ \'active\' if request.endpoint == \'events\' }}">Calendar</a>\n      <a href="{{ url_for(\'library\') }}" class="{{ \'active\' if request.endpoint == \'library\' }}">Library</a>\n      <a href="{{ url_for(\'transport\') }}" class="{{ \'active\' if request.endpoint == \'transport\' }}">Transport</a>\n      <a href="{{ url_for(\'id_cards\') }}" class="{{ \'active\' if request.endpoint == \'id_cards\' }}">ID cards</a>\n      <a href="{{ url_for(\'certificates\') }}" class="{{ \'active\' if request.endpoint and request.endpoint.startswith(\'certificate\') }}">Certificates</a>\n      <a href="{{ url_for(\'notifications\') }}" class="{{ \'active\' if request.endpoint == \'notifications\' }}">Messages</a>\n      {% if is_admin %}\n      <a href="{{ url_for(\'users\') }}" class="{{ \'active\' if request.endpoint and request.endpoint.startswith(\'user\') }}">Users</a>\n      <a href="{{ url_for(\'settings\') }}" class="{{ \'active\' if request.endpoint == \'settings\' }}">Settings</a>\n      <a href="{{ url_for(\'backup\') }}">Backup</a>\n      {% endif %}\n      {% endif %}\n    </nav>\n    <div class="sidebar-foot">\n      {% if current_user %}\n      <span class="who">{{ current_user.full_name or current_user.username }}\n        <em>{{ current_user.role }}</em></span>\n      {% if current_user.role != \'student\' %}\n      <a href="{{ url_for(\'my_signature\') }}">My signature</a>\n      <a href="{{ url_for(\'password\') }}">Change password</a>\n      {% endif %}\n      <a href="{{ url_for(\'logout\') }}">Log out</a>\n      {% endif %}\n      <span>{{ \'Cloud · Turso\' if cloud_db else \'SQLite\' }} · v3.2</span>\n    </div>\n  </aside>\n\n  <main>\n    {% if db_warning %}\n    <div class="flash error">{{ db_warning }}</div>\n    {% endif %}\n    {% if is_admin %}\n    <div class="banner admin">Admin mode — you can see and edit every user\'s data.</div>\n    {% endif %}\n    {% with messages = get_flashed_messages(with_categories=true) %}\n      {% for category, message in messages %}\n        <div class="flash {{ category }}">{{ message }}</div>\n      {% endfor %}\n    {% endwith %}\n    {% block content %}{% endblock %}\n  </main>\n</div>\n</body>\n</html>\n',
    'login.html':
        '{% extends "base.html" %}\n{% block title %}Log in{% endblock %}\n{% block content %}\n<div class="login-wrap">\n  <form class="card login" method="post">\n    <h1>Log in</h1>\n    {% if school_logo %}<img class="login-logo" src="{{ school_logo }}" alt="">\n    {% endif %}\n    <p class="muted">{{ school_name }} · examination module</p>\n    <label>Username\n      <input name="username" autofocus required autocomplete="username">\n    </label>\n    <label>Password\n      <input type="password" name="password" required autocomplete="current-password">\n    </label>\n    <button class="btn primary" type="submit">Log in</button>\n    <p class="muted small">Each account sees only its own data. Ask the admin\n      for a username and password.</p>\n    <p class="muted small"><a href="{{ url_for(\'about\') }}">About Exam Script 2</a></p>\n  </form>\n</div>\n{% endblock %}\n',
    'dashboard.html':
        '{% extends "base.html" %}\n{% block title %}Dashboard\n{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div>\n    <h1>Dashboard</h1>\n    <p>{{ today }} · a quick view of your examination data</p>\n  </div>\n</header>\n\n{% if is_admin %}\n<section class="card" style="display:flex;gap:16px;align-items:center;justify-content:space-between;flex-wrap:wrap">\n  <div>\n    <h2 class="card-title">Demo school</h2>\n    <p class="muted">Loads 10 students of class 8-A with parents, one exam with marks,\n       ten days of attendance, homework, three circulars and two teacher accounts\n       (teacher1 / teacher2, password <code>school1234</code>).</p>\n  </div>\n  <form method="post" action="{{ url_for(\'demo_seed\') }}">\n    <button class="btn primary" type="submit">Load demo data</button>\n  </form>\n</section>\n{% endif %}\n\n<div class="tiles">\n  <div class="tile"><i class="bar indigo"></i><b>{{ stats.students }}</b><span>Students</span></div>\n  <div class="tile"><i class="bar sky"></i><b>{{ stats.exams }}</b><span>Exams</span></div>\n  <div class="tile"><i class="bar green"></i><b>{{ stats.subjects }}</b><span>Subjects</span></div>\n  <div class="tile"><i class="bar amber"></i><b>{{ stats.papers }}</b><span>Papers scheduled</span></div>\n</div>\n\n{% if charts %}\n<section class="card">\n  <h2 class="card-title">Today at a glance</h2>\n  <div class="charts">\n    {% for label, value, colour in [(\'Attendance today\', charts.attendance, \'linear-gradient(90deg,#1b2a5e,#4a6bb5)\'),\n                                    (\'Fee collection\', charts.fees, \'linear-gradient(90deg,#e07a2f,#c96a24)\'),\n                                    (\'Pass percentage\', charts.pass, \'linear-gradient(90deg,#1f7a4d,#7bbf9b)\')] %}\n    <div class="chart">\n      <div class="chart-bar"><span style="width: {{ value }}%; background: {{ colour }}"></span></div>\n      <div class="chart-label">{{ label }} <strong>{{ value }}%</strong></div>\n    </div>\n    {% endfor %}\n  </div>\n</section>\n{% endif %}\n\n<div class="two-col">\n  <section class="card">\n    <div class="card-head">\n      <h2>Latest students</h2>\n      <a class="btn ghost small" href="{{ url_for(\'students\') }}">All students</a>\n    </div>\n    <div class="table-wrap">\n      <table class="grid">\n        <thead><tr><th>Admission No</th><th>Name</th><th>Class</th><th>Admitted on</th></tr></thead>\n        <tbody>\n        {% for s in recent %}\n          <tr><td>{{ s.admission_no }}</td><td>{{ s.name }}</td>\n              <td>{{ s.class_name }}</td><td>{{ disp_date(s.admission_date) }}</td></tr>\n        {% else %}\n          <tr><td colspan="4" class="empty">No students yet.</td></tr>\n        {% endfor %}\n        </tbody>\n      </table>\n    </div>\n  </section>\n\n  <section class="card">\n    <div class="card-head">\n      <h2>Exams</h2>\n      <a class="btn ghost small" href="{{ url_for(\'exams\') }}">All exams</a>\n    </div>\n    <div class="table-wrap">\n      <table class="grid">\n        <thead><tr><th>Exam type</th><th>Class</th><th>Starts</th><th>Status</th></tr></thead>\n        <tbody>\n        {% for e in exams %}\n          <tr><td>{{ e.exam_type or e.exam_name }}</td><td>{{ e.class_name }}</td>\n              <td>{{ disp_date(e.start_date) }}</td><td>{{ e.status }}</td></tr>\n        {% else %}\n          <tr><td colspan="4" class="empty">No exams yet.</td></tr>\n        {% endfor %}\n        </tbody>\n      </table>\n    </div>\n  </section>\n</div>\n\n<div class="two-col">\n  <section class="card">\n    <div class="card-head"><h2>Fee defaulters</h2>\n      <a class="btn ghost small" href="{{ url_for(\'fees\') }}">Fees</a></div>\n    {% for d in due_list %}\n      <div class="row-line"><strong>{{ d.name }}</strong>\n        <span class="muted">Class {{ d.class_name }}</span>\n        <span class="bad-text">{{ fmt_num(d.due) }}</span></div>\n    {% else %}<p class="muted">No pending dues.</p>{% endfor %}\n  </section>\n\n  <section class="card">\n    <div class="card-head"><h2>Coming up</h2>\n      <a class="btn ghost small" href="{{ url_for(\'events\') }}">Calendar</a></div>\n    {% for e in upcoming %}\n      <div class="row-line"><strong>{{ disp_date(e.event_date) }}</strong>\n        <span>{{ e.title }}</span><span class="muted">{{ e.kind }}</span></div>\n    {% else %}<p class="muted">No upcoming events.</p>{% endfor %}\n    {% for n in latest_notices %}\n      <div class="row-line"><strong>Notice</strong><span>{{ n.title }}</span>\n        <span class="muted">{{ n.posted_on[:10] }}</span></div>\n    {% endfor %}\n  </section>\n</div>\n<div class="two-col">\n  <section class="card">\n    <div class="card-head"><h2>Attendance — last 7 days</h2></div>\n    <div class="charts">\n      {% for t in trend %}\n        <div class="chart">\n          <div class="chart-bar"><span style="width: {{ t.pct }}%; background: linear-gradient(90deg,#e07a2f,#1b2a5e)"></span></div>\n          <div class="chart-label">{{ t.day }} · {{ t.pct }}%{% if not t.marked %} (not marked){% endif %}</div>\n        </div>\n      {% endfor %}\n    </div>\n  </section>\n\n  <section class="card">\n    <div class="card-head"><h2>Fee collection by class</h2></div>\n    {% for c in classes_fee %}\n      <div class="chart">\n        <div class="chart-bar"><span style="width: {{ c.pct }}%; background: linear-gradient(90deg,#1f7a4d,#7bbf9b)"></span></div>\n        <div class="chart-label">Class {{ c.cls }} · {{ fmt_num(c.paid) }} of {{ fmt_num(c.total) }} <strong>{{ c.pct }}%</strong></div>\n      </div>\n    {% else %}<p class="muted">No fee structure set yet.</p>{% endfor %}\n  </section>\n</div>\n\n<div class="two-col">\n  \n\n  <section class="card">\n    <div class="card-head"><h2>School snapshot</h2></div>\n    <div class="row-line"><strong>Staff</strong><span>{{ staff_count }} active</span></div>\n    <div class="row-line"><strong>Library</strong>\n      <span>{{ overdue }} overdue book(s)</span></div>\n    <div class="row-line"><strong>Messages</strong>\n      <a class="btn ghost small" href="{{ url_for(\'notifications\') }}">Open log</a></div>\n  </section>\n</div>\n{% endblock %}\n',
    'students.html':
        '{% extends "base.html" %}\n{% block title %}Students{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div>\n    <h1>Students</h1>\n    <p>Admission details and student master data</p>\n  </div>\n  <div class="actions">\n    <a class="btn ghost" href="{{ url_for(\'students_import\') }}">Import CSV</a>\n    <a class="btn ghost" href="{{ url_for(\'students_csv\') }}">Export CSV</a>\n  </div>\n</header>\n\n<section class="card">\n  <details {{ \'open\' if editing }}>\n    <summary>{{ \'Edit student\' if editing else \'Add a student\' }}</summary>\n    <form class="form-grid" method="post" action="{{ url_for(\'student_save\') }}">\n      <input type="hidden" name="id" value="{{ editing.id if editing else \'\' }}">\n      <label>Admission No *<input name="admission_no" required value="{{ editing.admission_no if editing else \'\' }}"></label>\n      <label>Roll No *<input name="roll_no" required value="{{ editing.roll_no if editing else \'\' }}"></label>\n      <label>Student name *<input name="name" required value="{{ editing.name if editing else \'\' }}"></label>\n      <label>Class *<input name="class_name" required value="{{ editing.class_name if editing else \'\' }}"></label>\n      <label>Section\n        <select name="section">\n          <option value=""></option>\n          {% for s in sections %}<option {{ \'selected\' if editing and editing.section == s }}>{{ s }}</option>{% endfor %}\n        </select>\n      </label>\n      <label>Date of birth<input name="dob" placeholder="dd/mm/yyyy" value="{{ disp_date(editing.dob) if editing else \'\' }}"></label>\n      <label>Gender\n        <select name="gender">\n          <option value=""></option>\n          {% for g in genders %}<option {{ \'selected\' if editing and editing.gender == g }}>{{ g }}</option>{% endfor %}\n        </select>\n      </label>\n      <label>Date of admission *<input name="admission_date" placeholder="dd/mm/yyyy" required value="{{ disp_date(editing.admission_date) if editing else \'\' }}"></label>\n      <label>Father\'s name<input name="father_name" value="{{ editing.father_name if editing else \'\' }}"></label>\n      <label>Mother\'s name<input name="mother_name" value="{{ editing.mother_name if editing else \'\' }}"></label>\n      <label>Phone<input name="phone" value="{{ editing.phone if editing else \'\' }}"></label>\n      <label>Email<input name="email" value="{{ editing.email if editing else \'\' }}"></label>\n      <label class="span-2">Address<input name="address" value="{{ editing.address if editing else \'\' }}"></label>\n      <label>Status\n        <select name="status">\n          {% for st in statuses %}<option {{ \'selected\' if (editing and editing.status == st) or (not editing and st == \'Active\') }}>{{ st }}</option>{% endfor %}\n        </select>\n      </label>\n      <div class="form-actions">\n        <button class="btn primary" type="submit">{{ \'Update student\' if editing else \'Save student\' }}</button>\n        {% if editing %}<a class="btn ghost" href="{{ url_for(\'students\') }}">Cancel</a>{% endif %}\n      </div>\n\n    {% if editing %}\n    <form method="post" enctype="multipart/form-data" class="photo-form"\n          action="{{ url_for(\'student_photo\', sid=editing.id) }}">\n      <label>Photo <input type="file" name="photo" accept="image/*"></label>\n      <button class="btn ghost small" type="submit">Upload photo</button>\n    </form>\n    {% endif %}\n    </form>\n  </details>\n</section>\n\n<section class="card">\n  <div class="card-head">\n    <h2>All students <span class="pill">{{ students|length }}</span></h2>\n    <form class="search" method="get">\n      <input name="q" value="{{ q }}" placeholder="Search name, roll no, admission no, class">\n      <button class="btn ghost" type="submit">Search</button>\n      {% if q %}<a class="btn ghost" href="{{ url_for(\'students\') }}">Reset</a>{% endif %}\n    </form>\n  </div>\n  <div class="table-wrap">\n    <table class="grid">\n      <thead>\n        <tr><th>Admission No</th><th>Roll</th><th>Name</th><th>Class</th><th>Section</th>\n            <th>Admitted</th><th>DOB</th><th>Phone</th><th>Status</th>\n            <th>Owner</th><th></th></tr>\n      </thead>\n      <tbody>\n      {% for s in students %}\n        <tr>\n          <td>{{ s.admission_no }}</td><td>{{ s.roll_no }}</td><td>{% if s.photo %}<img class="avatar" src="{{ s.photo }}" alt=""> {% endif %}{{ s.name }}</td>\n          <td>{{ s.class_name }}</td><td>{{ s.section or \'\' }}</td>\n          <td>{{ disp_date(s.admission_date) }}</td><td>{{ disp_date(s.dob) }}</td>\n          <td>{{ s.phone or \'\' }}</td><td>{{ s.status }}</td>\n          <td>{{ owners.get(s.owner_id, \'-\') }}</td>\n          <td class="row-actions">\n            <a class="btn ghost small" href="{{ url_for(\'student_profile\', sid=s.id) }}">Personal info</a>\n            <a class="btn ghost small" href="{{ url_for(\'students\', edit=s.id) }}">Edit</a>\n            <form method="post" action="{{ url_for(\'student_delete\', sid=s.id) }}"\n                  onsubmit="return confirm(\'Delete {{ s.name }} and every mark linked to them?\')">\n              <button class="btn danger small" type="submit">Delete</button>\n            </form>\n          </td>\n        </tr>\n      {% else %}\n        <tr><td colspan="{{ 11 if is_admin else 10 }}" class="empty">No students found.</td></tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n{% endblock %}\n',
    'exams.html':
        '{% extends "base.html" %}\n{% block title %}Exams{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div>\n    <h1>Exams</h1>\n    <p>The exam type is the exam\'s name — no separate exam name is needed</p>\n  </div>\n</header>\n\n<section class="card">\n  <details {{ \'open\' if editing }}>\n    <summary>{{ \'Edit exam\' if editing else \'Create an exam\' }}</summary>\n    <form class="form-grid" method="post" action="{{ url_for(\'exam_save\') }}">\n      <input type="hidden" name="id" value="{{ editing.id if editing else \'\' }}">\n      <label>Exam type *\n        <input name="exam_type" list="exam-types" required\n               value="{{ (editing.exam_type or editing.exam_name) if editing else \'\' }}">\n        <datalist id="exam-types">\n          {% for t in exam_types %}<option value="{{ t }}">{% endfor %}\n        </datalist>\n      </label>\n      <label>Academic year<input name="academic_year" value="{{ editing.academic_year if editing else \'2026-27\' }}"></label>\n      <label>Class<input name="class_name" value="{{ editing.class_name if editing else \'\' }}"></label>\n      <label>Start date<input name="start_date" placeholder="dd/mm/yyyy" value="{{ disp_date(editing.start_date) if editing else \'\' }}"></label>\n      <label>End date<input name="end_date" placeholder="dd/mm/yyyy" value="{{ disp_date(editing.end_date) if editing else \'\' }}"></label>\n      <label>Status\n        <select name="status">\n          {% for st in statuses %}<option {{ \'selected\' if editing and editing.status == st or (not editing and st == \'Scheduled\') }}>{{ st }}</option>{% endfor %}\n        </select>\n      </label>\n      <label class="span-2">Remarks<input name="remarks" value="{{ editing.remarks if editing else \'\' }}"></label>\n      <div class="form-actions">\n        <button class="btn primary" type="submit">{{ \'Update exam\' if editing else \'Save exam\' }}</button>\n        {% if editing %}<a class="btn ghost" href="{{ url_for(\'exams\') }}">Cancel</a>{% endif %}\n      </div>\n    </form>\n  </details>\n</section>\n\n<section class="card">\n  <div class="card-head"><h2>All exams <span class="pill">{{ exams|length }}</span></h2></div>\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr><th>Exam type</th><th>Academic year</th><th>Class</th><th>Start</th>\n                 <th>End</th><th>Status</th><th>Remarks</th>\n                 <th>Owner</th><th></th></tr></thead>\n      <tbody>\n      {% for e in exams %}\n        <tr>\n          <td>{{ e.exam_type or e.exam_name }}</td><td>{{ e.academic_year }}</td>\n          <td>{{ e.class_name }}</td><td>{{ disp_date(e.start_date) }}</td>\n          <td>{{ disp_date(e.end_date) }}</td><td>{{ e.status }}</td>\n          <td class="muted">{{ e.remarks or \'\' }}</td>\n          <td>{{ owners.get(e.owner_id, \'-\') }}</td>\n          <td class="row-actions">\n            <a class="btn ghost small" href="{{ url_for(\'exams\', edit=e.id) }}">Edit</a>\n            <form method="post" action="{{ url_for(\'exam_delete\', eid=e.id) }}"\n                  onsubmit="return confirm(\'Delete this exam with its schedule and marks?\')">\n              <button class="btn danger small" type="submit">Delete</button>\n            </form>\n          </td>\n        </tr>\n      {% else %}\n        <tr><td colspan="{{ 9 if is_admin else 8 }}" class="empty">No exams yet.</td></tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n{% endblock %}\n',
    'subjects.html':
        '{% extends "base.html" %}\n{% block title %}Subjects{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Subjects</h1><p>Subject master used by the exam schedule</p></div>\n  <div class="actions">\n    <form method="post" action="{{ url_for(\'subject_defaults\') }}">\n      <button class="btn ghost" type="submit">Load defaults</button>\n    </form>\n  </div>\n</header>\n\n<section class="card">\n  <details {{ \'open\' if editing }}>\n    <summary>{{ \'Edit subject\' if editing else \'Add a subject\' }}</summary>\n    <form class="form-grid" method="post" action="{{ url_for(\'subject_save\') }}">\n      <input type="hidden" name="id" value="{{ editing.id if editing else \'\' }}">\n      <label>Subject code *<input name="subject_code" required value="{{ editing.subject_code if editing else \'\' }}"></label>\n      <label>Subject name *<input name="subject_name" required value="{{ editing.subject_name if editing else \'\' }}"></label>\n      <label>Class (blank = all)<input name="class_name" value="{{ editing.class_name if editing else \'\' }}"></label>\n      <div class="form-actions">\n        <button class="btn primary" type="submit">{{ \'Update subject\' if editing else \'Save subject\' }}</button>\n        {% if editing %}<a class="btn ghost" href="{{ url_for(\'subjects\') }}">Cancel</a>{% endif %}\n      </div>\n    </form>\n  </details>\n</section>\n\n<section class="card">\n  <div class="card-head"><h2>All subjects <span class="pill">{{ subjects|length }}</span></h2></div>\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr><th>Code</th><th>Subject name</th><th>Class</th>\n                 <th>Owner</th><th></th></tr></thead>\n      <tbody>\n      {% for s in subjects %}\n        <tr>\n          <td>{{ s.subject_code }}</td><td>{{ s.subject_name }}</td><td>{{ s.class_name or \'\' }}</td>\n          <td>{{ owners.get(s.owner_id, \'-\') }}</td>\n          <td class="row-actions">\n            <a class="btn ghost small" href="{{ url_for(\'subjects\', edit=s.id) }}">Edit</a>\n            <form method="post" action="{{ url_for(\'subject_delete\', sid=s.id) }}"\n                  onsubmit="return confirm(\'Delete {{ s.subject_name }}?\')">\n              <button class="btn danger small" type="submit">Delete</button>\n            </form>\n          </td>\n        </tr>\n      {% else %}\n        <tr><td colspan="{{ 5 if is_admin else 4 }}" class="empty">No subjects yet — use “Load defaults”.</td></tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n{% endblock %}\n',
    'schedule.html':
        '{% extends "base.html" %}\n{% block title %}Exam schedule{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Exam schedule</h1><p>One paper per subject — date, time, hall and marks</p></div>\n</header>\n\n<section class="card">\n  <details open>\n    <summary>Add a paper</summary>\n    {% if not exams or not subjects %}\n      <p class="muted">Create at least one exam and one subject first.</p>\n    {% else %}\n    <form class="form-grid" method="post" action="{{ url_for(\'schedule_save\') }}">\n      <label>Exam *\n        <select name="exam_id" required>\n          <option value="">— choose —</option>\n          {% for e in exams %}<option value="{{ e.id }}">{{ exam_label(e) }}</option>{% endfor %}\n        </select>\n      </label>\n      <label>Subject *\n        <select name="subject_id" required>\n          <option value="">— choose —</option>\n          {% for s in subjects %}<option value="{{ s.id }}">{{ s.subject_name }} ({{ s.subject_code }})</option>{% endfor %}\n        </select>\n      </label>\n      <label>Exam date<input name="exam_date" placeholder="dd/mm/yyyy"></label>\n      <label>Start time<input name="start_time" placeholder="09:00"></label>\n      <label>Duration (minutes)<input name="duration" value="180"></label>\n      <label>Room / hall<input name="room"></label>\n      <label>Invigilator<input name="invigilator"></label>\n      <label>Max marks<input name="max_marks" value="100"></label>\n      <label>Pass marks<input name="pass_marks" value="33"></label>\n      <label>Internal max <input name="internal_max" type="number" step="1" value="30"\n             title="Kitne marks internal assessment ke hain"></label>\n      <div class="form-actions"><button class="btn primary" type="submit">Add paper</button></div>\n    </form>\n    {% endif %}\n  </details>\n</section>\n\n<section class="card">\n  <div class="card-head"><h2>Scheduled papers <span class="pill">{{ papers|length }}</span></h2></div>\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr><th>Exam</th><th>Subject</th><th>Date</th><th>Time</th><th>Duration</th>\n                 <th>Room</th><th>Invigilator</th><th>Max</th><th>Pass</th><th></th></tr></thead>\n      <tbody>\n      {% for p in papers %}\n        <tr>\n          <td>{{ exam_label(p) }}</td><td>{{ p.subject_name }}</td>\n          <td>{{ disp_date(p.exam_date) }}</td><td>{{ p.start_time }}</td>\n          <td>{{ p.duration }}</td><td>{{ p.room or \'\' }}</td>\n          <td>{{ p.invigilator or \'\' }}</td>\n          <td class="num">{{ fmt_num(p.max_marks) }}</td>\n          <td class="num">{{ fmt_num(p.pass_marks) }}</td>\n          <td class="row-actions">\n            <form method="post" action="{{ url_for(\'schedule_delete\', pid=p.id) }}"\n                  onsubmit="return confirm(\'Remove this paper and its marks?\')">\n              <button class="btn danger small" type="submit">Delete</button>\n            </form>\n          </td>\n        </tr>\n      {% else %}\n        <tr><td colspan="10" class="empty">No papers scheduled yet.</td></tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n{% endblock %}\n',
    'marks.html':
        '{% extends "base.html" %}\n{% block title %}Marks entry{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Marks entry</h1><p>Pick an exam and a subject, then fill the marks</p></div>\n</header>\n\n<section class="card">\n  <form class="form-grid" method="get">\n    <label>Exam\n      <select name="exam_id" onchange="this.form.submit()">\n        <option value="">— choose —</option>\n        {% for e in exams %}\n          <option value="{{ e.id }}" {{ \'selected\' if exam_id == e.id|string }}>{{ exam_label(e) }}</option>\n        {% endfor %}\n      </select>\n    </label>\n    <label>Subject\n      <select name="subject_id" onchange="this.form.submit()">\n        <option value="">— choose —</option>\n        {% for s in subjects %}\n          <option value="{{ s.id }}" {{ \'selected\' if subject_id == s.id|string }}>{{ s.subject_name }} ({{ s.subject_code }})</option>\n        {% endfor %}\n      </select>\n    </label>\n    <noscript><div class="form-actions"><button class="btn ghost" type="submit">Load sheet</button></div></noscript>\n  </form>\n</section>\n\n{% if info %}<p class="info">{{ info }}</p>{% endif %}\n\n{% if sheet %}\n<section class="card">\n  <form method="post">\n    <input type="hidden" name="exam_id" value="{{ exam_id }}">\n    <input type="hidden" name="subject_id" value="{{ subject_id }}">\n    <div class="table-wrap">\n      <table class="grid">\n        <thead><tr><th>Roll</th><th>Name</th>\n                   <th>Theory</th><th>Internal (max {{ fmt_num(ctx.internal_max) }})</th>\n                   <th>Total (max {{ fmt_num(ctx.max_marks) }})</th>\n                   <th>Result</th><th>Remarks</th></tr></thead>\n        <tbody>\n        {% for row in sheet %}\n          {% set m = row.mark %}\n          <tr>\n            <td>{{ row.student.roll_no }}</td>\n            <td>{{ row.student.name }}</td>\n            <td class="num">\n              <input class="mark-input" type="number" step="0.5" min="0"\n                     max="{{ ctx.max_marks - ctx.internal_max }}" name="theory_{{ row.student.id }}"\n                     value="{{ fmt_num(m.theory) if m and m.theory is not none else \'\' }}"\n                     placeholder="—">\n            </td>\n            <td class="num">\n              <input class="mark-input" type="number" step="0.5" min="0"\n                     max="{{ ctx.internal_max }}" name="internal_{{ row.student.id }}"\n                     value="{{ fmt_num(m.internal) if m and m.internal is not none else \'\' }}"\n                     placeholder="—">\n            </td>\n            <td class="num">\n              <input class="mark-input" type="number" step="0.5" min="0"\n                     max="{{ ctx.max_marks }}" name="marks_{{ row.student.id }}"\n                     value="{{ fmt_num(m.marks_obtained) if m and m.marks_obtained is not none else \'\' }}">\n            </td>\n            <td>\n              {% if m and m.marks_obtained is not none %}\n                {% if m.marks_obtained >= ctx.pass_marks %}\n                  <span class="tag ok">Pass</span>\n                {% else %}\n                  <span class="tag bad">Fail</span>\n                {% endif %}\n              {% else %}<span class="muted">—</span>{% endif %}\n            </td>\n            <td><input name="remarks_{{ row.student.id }}" value="{{ m.remarks if m and m.remarks else \'\' }}"></td>\n          </tr>\n        {% endfor %}\n        </tbody>\n      </table>\n    </div>\n    <div class="form-actions">\n      <button class="btn primary" type="submit">Save all marks</button>\n    </div>\n  </form>\n</section>\n{% endif %}\n{% endblock %}\n',
    'results.html':
        '{% extends "base.html" %}\n{% block title %}Results{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Results</h1><p>Totals, percentage, grade, rank and pass / fail</p></div>\n  {% if results %}\n  <div class="actions">\n    <a class="btn ghost" href="{{ url_for(\'results_csv\', exam_id=exam_id, class_name=class_name, limit=limit or 0) }}">Export CSV</a>\n  </div>\n  {% endif %}\n</header>\n\n<section class="card">\n  <form class="form-grid" method="get">\n    <label>Exam\n      <select name="exam_id" onchange="this.form.submit()">\n        <option value="">— choose —</option>\n        {% for e in exams %}\n          <option value="{{ e.id }}" {{ \'selected\' if exam_id == e.id|string }}>{{ exam_label(e) }}</option>\n        {% endfor %}\n      </select>\n    </label>\n    <label>Class\n      <input name="class_name" value="{{ class_name }}" placeholder="e.g. 8">\n    </label>\n    <div class="form-actions"><button class="btn primary" type="submit">Generate</button></div>\n  </form>\n</section>\n\n{% if info %}<p class="info">{{ info }}{% if limit and total_students %} · showing top {{ limit }} of {{ total_students }}{% endif %}</p>{% endif %}\n\n{% if results %}\n<section class="card">\n  <form method="get" action="{{ url_for(\'results_print\') }}" id="printForm">\n  <input type="hidden" name="exam_id" value="{{ exam_id }}">\n  <input type="hidden" name="class_name" value="{{ class_name }}">\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr>\n        <th style="width:38px"><input type="checkbox" id="pickAll" title="Select all"></th>\n        <th>Rank</th><th>Roll</th><th>Admission No</th><th>Name</th>\n                 <th>Obtained</th><th>Max</th><th>%</th><th>Grade</th>\n                 <th>Failed</th><th>Result</th><th></th></tr></thead>\n      <tbody>\n      {% for r in results %}\n        <tr>\n          <td><input type="checkbox" class="pick" name="students" value="{{ r.student_id }}"></td>\n          <td>{{ r.rank }}</td><td>{{ r.roll_no }}</td><td>{{ r.admission_no }}</td>\n          <td>{{ r.name }}</td><td class="num">{{ fmt_num(r.obtained) }}</td>\n          <td class="num">{{ fmt_num(r.total_max) }}</td>\n          <td class="num">{{ \'%.2f\'|format(r.percentage) }}</td>\n          <td>{{ r.grade }}</td><td class="num">{{ r.failed_subjects }}</td>\n          <td>{% if r.result == \'Pass\' %}<span class="tag ok">Pass</span>\n              {% else %}<span class="tag bad">Fail</span>{% endif %}</td>\n          <td><a class="btn ghost small" target="_blank"\n                 href="{{ url_for(\'report_card\', exam_id=exam_id, student_id=r.student_id) }}">Report card</a></td>\n        </tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n\n  <div class="print-row">\n    <button class="btn primary" type="submit" id="printBtn">Print selected report cards</button>\n    <a class="btn ghost" target="_blank" id="printAll"\n       href="{{ url_for(\'results_print\', exam_id=exam_id, class_name=class_name) }}">Print all</a>\n    <span class="muted" id="pickInfo">No student selected</span>\n  </div>\n  </form>\n\n  <script>\n    (function () {\n      var all = document.getElementById(\'pickAll\');\n      var boxes = Array.prototype.slice.call(document.querySelectorAll(\'.pick\'));\n      var btn = document.getElementById(\'printBtn\');\n      var info = document.getElementById(\'pickInfo\');\n      function refresh() {\n        var n = boxes.filter(function (b) { return b.checked; }).length;\n        info.textContent = n ? n + \' student(s) selected\' : \'No student selected\';\n        btn.disabled = n === 0;\n        btn.style.opacity = n === 0 ? .5 : 1;\n        if (all) all.checked = n === boxes.length && n > 0;\n      }\n      if (all) all.addEventListener(\'change\', function () {\n        boxes.forEach(function (b) { b.checked = all.checked; });\n        refresh();\n      });\n      boxes.forEach(function (b) { b.addEventListener(\'change\', refresh); });\n      refresh();\n    })();\n  </script>\n</section>\n{% endif %}\n\n<style>\n .print-row{display:flex;justify-content:center;align-items:center;gap:14px;flex-wrap:wrap;\n            margin-top:18px;padding:14px;border-radius:14px;background:#fdf6ea;\n            border:1px dashed #e0cfae}\n .print-row .muted{font-size:12.5px}\n .pick,.grid input[type=checkbox]{width:18px;height:18px;accent-color:#e07a2f;cursor:pointer;\n            vertical-align:middle}\n th input[type=checkbox]{width:17px;height:17px}\n</style>\n{% endblock %}\n',
    'users.html':
        '{% extends "base.html" %}\n{% block title %}Users{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div>\n    <h1>Users</h1>\n    <p>Every account keeps its own students, exams and marks. Only admins see\n       everything.</p>\n  </div>\n</header>\n\n<section class="card">\n  <details {{ \'open\' if editing }}>\n    <summary>{{ \'Edit user\' if editing else \'Add a user\' }}</summary>\n    <form class="form-grid" method="post" action="{{ url_for(\'user_save\') }}">\n      <input type="hidden" name="id" value="{{ editing.id if editing else \'\' }}">\n      <label>Username *\n        <input name="username" required value="{{ editing.username if editing else \'\' }}"\n               placeholder="e.g. teacher1">\n      </label>\n      <label>Full name\n        <input name="full_name" value="{{ editing.full_name if editing else \'\' }}">\n      </label>\n      <label>Role\n        <select name="role">\n          <option value="user" {{ \'selected\' if editing and editing.role in (\'user\', \'teacher\') }}>teacher</option>\n          <option value="admin" {{ \'selected\' if editing and editing.role == \'admin\' }}>admin</option>\n          <option value="student" {{ \'selected\' if editing and editing.role == \'student\' }}>student</option>\n          <option value="parent" {{ \'selected\' if editing and editing.role == \'parent\' }}>parent</option>\n        </select>\n      </label>\n      <label>Class teacher of <span class="muted">(for teacher accounts)</span>\n        <input name="class_name" placeholder="e.g. 8" value="{{ editing.class_name if editing and editing.class_name else \'\' }}">\n      </label>\n      <label>Section\n        <input name="section" placeholder="e.g. A" value="{{ editing.section if editing and editing.section else \'\' }}">\n      </label>\n      <label>Linked student <span class="muted">(only for student accounts)</span>\n        <select name="student_id">\n          <option value="">— none —</option>\n          {% for st in students %}\n            <option value="{{ st.id }}" {{ \'selected\' if editing and editing.student_id == st.id }}>\n              {{ st.name }} · Class {{ st.class_name }} · Roll {{ st.roll_no }}\n            </option>\n          {% endfor %}\n        </select>\n      </label>\n      <label>{{ \'New password (leave blank to keep)\' if editing else \'Password *\' }}\n        <input type="password" name="password" {{ \'\' if editing else \'required\' }}>\n      </label>\n      <div class="form-actions">\n        <button class="btn primary" type="submit">\n          {{ \'Update user\' if editing else \'Create user\' }}</button>\n        {% if editing %}<a class="btn ghost" href="{{ url_for(\'users\') }}">Cancel</a>{% endif %}\n      </div>\n    </form>\n  </details>\n</section>\n\n<section class="card">\n  <div class="card-head"><h2>Accounts <span class="pill">{{ users|length }}</span></h2></div>\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr><th>Username</th><th>Name</th><th>Role</th><th>Students</th>\n                 <th>Exams</th><th>Status</th><th></th></tr></thead>\n      <tbody>\n      {% for u in users %}\n        <tr>\n          <td>{{ u.username }}</td>\n          <td>{{ u.full_name or \'\' }}</td>\n          <td>{% if u.role == \'admin\' %}<span class="tag admin">admin</span>\n              {% elif u.role == \'student\' %}<span class="tag">student</span>\n              {% elif u.role == \'parent\' %}<span class="tag">parent</span>\n              {% else %}<span class="tag">teacher</span>{% endif %}</td>\n          <td class="num">{{ u.n_students }}</td>\n          <td class="num">{{ u.n_exams }}</td>\n          <td>{% if u.active %}<span class="tag ok">active</span>\n              {% else %}<span class="tag bad">disabled</span>{% endif %}</td>\n          <td class="row-actions">\n            <a class="btn ghost small" href="{{ url_for(\'users\', edit=u.id) }}">Edit</a>\n            <form method="post" action="{{ url_for(\'user_toggle\', user_id=u.id) }}">\n              <button class="btn ghost small" type="submit">\n                {{ \'Disable\' if u.active else \'Enable\' }}</button>\n            </form>\n            <form method="post" action="{{ url_for(\'user_delete\', user_id=u.id) }}"\n                  onsubmit="return confirm(\'Delete the account {{ u.username }}?\')">\n              <button class="btn danger small" type="submit">Delete</button>\n            </form>\n          </td>\n        </tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n{% endblock %}\n',
    'my_result.html':
        '{% extends "base.html" %}\n{% block title %}My result{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>My result</h1>\n    <p>{% if student %}{{ student.name }} · Class {{ student.class_name }}{% if student.section %} – {{ student.section }}{% endif %} · Roll {{ student.roll_no }}{% endif %}</p>\n  </div>\n</header>\n\n{% if not student %}\n<section class="card">\n  <p class="muted">This account is not linked to a student record yet.\n     Please ask the school office to link it.</p>\n</section>\n{% else %}\n\n<section class="card">\n  <div class="kv">\n    <div><span>Name</span><strong>{{ student.name }}</strong></div>\n    <div><span>Class</span><strong>{{ student.class_name }}{% if student.section %} – {{ student.section }}{% endif %}</strong></div>\n    <div><span>Roll No</span><strong>{{ student.roll_no }}</strong></div>\n    <div><span>Admission No</span><strong>{{ student.admission_no }}</strong></div>\n  </div>\n</section>\n\n{% if not exams %}\n<section class="card">\n  <p class="muted">No result has been published yet. Please check again later.</p>\n</section>\n{% else %}\n\n<section class="card">\n  <h2 class="card-title">Published results</h2>\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr><th>Exam</th><th>Class</th><th>Obtained</th><th>Max</th>\n                 <th>%</th><th>Grade</th><th>Result</th><th>Rank</th><th></th></tr></thead>\n      <tbody>\n      {% for item in exams %}\n        <tr>\n          <td>{{ exam_label(item.exam) }}</td>\n          <td>{{ item.exam.class_name }}</td>\n          <td>{{ fmt_num(item.result.obtained) }}</td>\n          <td>{{ fmt_num(item.result.total_max) }}</td>\n          <td>{{ \'%.2f\'|format(item.result.percentage) }}</td>\n          <td>{{ item.result.grade }}</td>\n          <td>{% if item.result.result == \'Pass\' %}<span class="pill ok">Pass</span>{% else %}<span class="pill bad">Fail</span>{% endif %}</td>\n          <td>{{ item.result.rank }}</td>\n          <td style="white-space:nowrap">\n            <a class="btn ghost small" href="{{ url_for(\'my_result\', exam_id=item.exam.id) }}">Details</a>\n            <a class="btn ghost small" href="{{ url_for(\'report_card\', exam_id=item.exam.id, student_id=student.id) }}">Report card</a>\n          </td>\n        </tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n\n{% if detail %}\n<section class="card">\n  <h2 class="card-title">{{ exam_label(exam) }} — subject-wise marks</h2>\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr><th>Code</th><th>Subject</th><th>Max</th><th>Pass</th>\n                 <th>Marks</th><th>Result</th><th>Remarks</th></tr></thead>\n      <tbody>\n      {% for d in detail %}\n        <tr>\n          <td>{{ d.subject_code }}</td>\n          <td>{{ d.subject_name }}</td>\n          <td>{{ fmt_num(d.max_marks) }}</td>\n          <td>{{ fmt_num(d.pass_marks) }}</td>\n          <td>{{ fmt_num(d.marks_obtained) }}</td>\n          <td>{% if d.marks_obtained is not none and d.pass_marks is not none and d.marks_obtained < d.pass_marks %}<span class="pill bad">Fail</span>{% else %}<span class="pill ok">Pass</span>{% endif %}</td>\n          <td>{{ d.remarks or \'\' }}</td>\n        </tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n{% endif %}\n{% endif %}\n{% endif %}\n{% endblock %}\n',
    'attendance.html':
        '{% extends "base.html" %}\n{% block title %}Attendance{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Attendance</h1><p>Mark the daily register for a class{% if scope %} · your class: {{ scope[0] }}{% if scope[1] %} – {{ scope[1] }}{% endif %}{% endif %}</p></div>\n</header>\n\n\n<section class="card cal-card">\n  <div class="cal-head">\n    <a class="cal-nav" href="?class_name={{ cls }}&section={{ sec }}&month={{ prev_month }}">‹</a>\n    <h2 class="cal-title">{{ month_label }}</h2>\n    <a class="cal-nav" href="?class_name={{ cls }}&section={{ sec }}&month={{ next_month }}">›</a>\n  </div>\n  <div class="cal-grid">\n    {% for d in [\'Mon\',\'Tue\',\'Wed\',\'Thu\',\'Fri\',\'Sat\',\'Sun\'] %}\n      <div class="cal-dow">{{ d }}</div>\n    {% endfor %}\n    {% for week in weeks %}\n      {% for c in week %}\n        <a class="cal-day {{ c.state }} {{ \'\' if c.in_month else \'muted\' }} {{ \'today\' if c.key == today }}"\n           href="?class_name={{ cls }}&section={{ sec }}&att_date={{ c.key }}&month={{ month }}"\n           title="{{ c.key }}{% if c.n %} · {{ c.p }}/{{ c.n }} present{% endif %}">\n          <span class="cal-num">{{ c.day.day }}</span>\n          {% if c.n %}<span class="cal-meta">{{ c.p }}/{{ c.n }}</span>{% endif %}\n        </a>\n      {% endfor %}\n    {% endfor %}\n  </div>\n  <div class="cal-key">\n    <span><i class="k full"></i> all present</span>\n    <span><i class="k partial"></i> some absent</span>\n    <span><i class="k absent"></i> all absent</span>\n    <span><i class="k none"></i> not marked</span>\n  </div>\n</section>\n\n<style>\n .cal-card{padding:16px 18px}\n .cal-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}\n .cal-title{margin:0;font-size:16px;letter-spacing:.02em}\n .cal-nav{width:32px;height:32px;display:grid;place-items:center;border-radius:9px;\n          background:#eef2f9;color:#1f3a5f;font-size:18px;text-decoration:none}\n .cal-nav:hover{background:#dde7f6}\n .cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:6px}\n .cal-dow{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:#7b8aa3;\n          text-align:center;padding-bottom:4px}\n .cal-day{min-height:56px;border-radius:10px;padding:6px 8px;text-decoration:none;\n          color:#0f172a;display:flex;flex-direction:column;justify-content:space-between;\n          border:1px solid transparent;transition:.15s}\n .cal-day:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(15,23,42,.10)}\n .cal-num{font-weight:700;font-size:13px}\n .cal-meta{font-size:10.5px;opacity:.85}\n .cal-day.full{background:#dcf5e6;border-color:#a7e0bf;color:#0f5132}\n .cal-day.partial{background:#fdf0d5;border-color:#f0cf95;color:#7a4b06}\n .cal-day.absent{background:#fde2e2;border-color:#f3b4b4;color:#7f1d1d}\n .cal-day.none{background:#f1f4f9;border-color:#e3e8f0;color:#8a94a6}\n .cal-day.muted{opacity:.35}\n .cal-day.today{outline:2px solid #2f6ea8;outline-offset:1px}\n .cal-key{display:flex;gap:16px;flex-wrap:wrap;margin-top:12px;font-size:11.5px;color:#64748b}\n .cal-key i{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:5px}\n .k.full{background:#dcf5e6}.k.partial{background:#fdf0d5}\n .k.absent{background:#fde2e2}.k.none{background:#f1f4f9}\n @media print{.cal-nav{display:none}}\n</style>\n\n<section class="card">\n  <form class="form-grid" method="get">\n    <label>Class\n      <select name="class_name" onchange="this.form.submit()">\n        <option value="">— choose —</option>\n        {% for c in classes %}<option value="{{ c }}" {{ \'selected\' if cls == c }}>{{ c }}</option>{% endfor %}\n      </select>\n    </label>\n    <label>Section\n      <select name="section" onchange="this.form.submit()">\n        <option value="">all</option>\n        {% for s in sections %}<option value="{{ s }}" {{ \'selected\' if sec == s }}>{{ s }}</option>{% endfor %}\n      </select>\n    </label>\n    <label>Date\n      <input type="date" name="att_date" value="{{ day }}" onchange="this.form.submit()">\n    </label>\n    <div class="form-actions"><button class="btn primary" type="submit">Show</button></div>\n  </form>\n</section>\n\n{% if students %}\n<form method="post">\n  <input type="hidden" name="class_name" value="{{ cls }}">\n  <input type="hidden" name="section" value="{{ sec }}">\n  <input type="hidden" name="att_date" value="{{ day }}">\n  <section class="card">\n    <h2 class="card-title">{{ cls }}{% if sec %} – {{ sec }}{% endif %} · {{ disp_date(day) }}</h2>\n    <div class="table-wrap">\n      <table class="grid">\n        <thead><tr><th>Roll</th><th>Name</th><th>Present</th><th>Absent</th>\n                   <th>Late</th><th>Leave</th><th>Remarks</th></tr></thead>\n        <tbody>\n        {% for s in students %}\n          {% set m = marks.get(s.id) %}\n          <tr>\n            <td>{{ s.roll_no }}</td>\n            <td>{{ s.name }}</td>\n            {% for st in statuses %}\n            <td><input type="radio" name="status_{{ s.id }}" value="{{ st }}"\n                 {{ \'checked\' if (m and m.status == st) or (not m and st == \'Present\') }}></td>\n            {% endfor %}\n            <td><input name="remarks_{{ s.id }}" value="{{ m.remarks if m and m.remarks else \'\' }}" placeholder="—"></td>\n          </tr>\n        {% endfor %}\n        </tbody>\n      </table>\n    </div>\n    <div class="form-actions"><button class="btn primary" type="submit">Save attendance</button></div>\n  </section>\n</form>\n{% elif cls %}\n<section class="card"><p class="muted">No active students in this class.</p></section>\n{% endif %}\n{% endblock %}\n',
    'homework.html':
        '{% extends "base.html" %}\n{% block title %}Homework{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Homework</h1><p>What each class has to do, and by when</p></div>\n</header>\n\n<section class="card">\n  <h2 class="card-title">Set homework</h2>\n  <form class="form-grid" method="post">\n    <label>Class\n      <select name="class_name" required>\n        <option value="">— choose —</option>\n        {% for c in classes %}<option value="{{ c }}" {{ \'selected\' if scope and scope[0] == c }}>{{ c }}</option>{% endfor %}\n      </select>\n    </label>\n    <label>Section <input name="section" placeholder="A" value="{{ scope[1] if scope else \'\' }}"></label>\n    <label>Subject\n      <select name="subject_id">\n        <option value="">—</option>\n        {% for s in subjects %}<option value="{{ s.id }}">{{ s.subject_code }} · {{ s.subject_name }}</option>{% endfor %}\n      </select>\n    </label>\n    <label>Due date <input type="date" name="due_date"></label>\n    <label class="wide">Title <input name="title" required placeholder="e.g. Exercise 8.2 question 1 to 10"></label>\n    <label class="wide">Details <textarea name="details" rows="2" placeholder="Instructions for the students"></textarea></label>\n    <div class="form-actions"><button class="btn primary" type="submit">Post homework</button></div>\n  </form>\n</section>\n\n<section class="card">\n  <h2 class="card-title">Posted so far</h2>\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr><th>Class</th><th>Subject</th><th>Title</th><th>Due</th><th>By</th><th></th></tr></thead>\n      <tbody>\n      {% for h in homework %}\n        <tr>\n          <td>{{ h.class_name }}{% if h.section %} – {{ h.section }}{% endif %}</td>\n          <td>{{ h.subject_name or \'—\' }}</td>\n          <td><strong>{{ h.title }}</strong>{% if h.details %}<br><span class="muted">{{ h.details }}</span>{% endif %}</td>\n          <td>{{ disp_date(h.due_date) }}</td>\n          <td>{{ h.author or \'—\' }}</td>\n          <td>\n            <form method="post" action="{{ url_for(\'homework_delete\', hid=h.id) }}">\n              <button class="btn ghost small" type="submit">Delete</button>\n            </form>\n          </td>\n        </tr>\n      {% else %}\n        <tr><td colspan="6" class="muted">Nothing posted yet.</td></tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n{% endblock %}\n',
    'circulars.html':
        '{% extends "base.html" %}\n{% block title %}Circulars{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Circulars &amp; notices</h1><p>Everything the school needs to tell parents and students</p></div>\n</header>\n\n<section class="card">\n  <h2 class="card-title">Publish a circular</h2>\n  <form class="form-grid" method="post">\n    <label class="wide">Title <input name="title" required placeholder="e.g. Parent-teacher meeting"></label>\n    <label class="wide">Message <textarea name="body" rows="3" placeholder="Write the notice here"></textarea></label>\n    <label>Audience\n      <select name="audience">\n        <option value="all">Everyone</option>\n        <option value="students">Students</option>\n        <option value="parents">Parents</option>\n        <option value="teachers">Teachers</option>\n      </select>\n    </label>\n    <label>Class <input name="class_name" placeholder="blank = all classes"></label>\n    <label>Section <input name="section" placeholder="blank = all"></label>\n    <label class="check"><input type="checkbox" name="pinned"> Pin to the top</label>\n    <div class="form-actions"><button class="btn primary" type="submit">Publish</button></div>\n  </form>\n</section>\n\n{% for c in circulars %}\n<section class="card">\n  <h2 class="card-title">{% if c.pinned %}📌 {% endif %}{{ c.title }}</h2>\n  <p class="muted">{{ c.posted_on[:10] }} · {{ c.audience }}{% if c.class_name %} · class {{ c.class_name }}{% if c.section %} – {{ c.section }}{% endif %}{% endif %} · {{ c.author or \'office\' }}</p>\n  <p>{{ c.body }}</p>\n  {% if is_admin or (current_user and c.posted_by == current_user.id) %}\n  <form method="post" action="{{ url_for(\'circular_delete\', cid=c.id) }}">\n    <button class="btn ghost small" type="submit">Delete</button>\n  </form>\n  {% endif %}\n</section>\n{% else %}\n<section class="card"><p class="muted">No circulars yet.</p></section>\n{% endfor %}\n{% endblock %}\n',
    'my_attendance.html':
        '{% extends "base.html" %}\n{% block title %}My attendance{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>My attendance</h1><p>{{ student.name }} · Class {{ student.class_name }}{% if student.section %} – {{ student.section }}{% endif %}</p></div>\n</header>\n\n\n<section class="card cal-card">\n  <div class="cal-head">\n    <a class="cal-nav" href="?month={{ prev_month }}">‹</a>\n    <h2 class="cal-title">{{ month_label }}</h2>\n    <a class="cal-nav" href="?month={{ next_month }}">›</a>\n  </div>\n  <div class="cal-grid">\n    {% for d in [\'Mon\',\'Tue\',\'Wed\',\'Thu\',\'Fri\',\'Sat\',\'Sun\'] %}\n      <div class="cal-dow">{{ d }}</div>\n    {% endfor %}\n    {% for week in weeks %}\n      {% for c in week %}\n        <div class="cal-day {{ c.state }} {{ \'\' if c.in_month else \'muted\' }} {{ \'today\' if c.key == today }}"\n             title="{{ c.key }}{% if c.status %} · {{ c.status }}{% endif %}">\n          <span class="cal-num">{{ c.day.day }}</span>\n          {% if c.status %}<span class="cal-meta">{{ c.status }}</span>{% endif %}\n        </div>\n      {% endfor %}\n    {% endfor %}\n  </div>\n  <div class="cal-key">\n    <span><i class="k full"></i> present</span>\n    <span><i class="k absent"></i> absent</span>\n    <span><i class="k partial"></i> leave / late</span>\n    <span><i class="k none"></i> not marked</span>\n  </div>\n</section>\n\n<style>\n .cal-card{padding:16px 18px}\n .cal-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}\n .cal-title{margin:0;font-size:16px}\n .cal-nav{width:32px;height:32px;display:grid;place-items:center;border-radius:9px;\n          background:#eef2f9;color:#1f3a5f;font-size:18px;text-decoration:none}\n .cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:6px}\n .cal-dow{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:#7b8aa3;\n          text-align:center;padding-bottom:4px}\n .cal-day{min-height:56px;border-radius:10px;padding:6px 8px;display:flex;\n          flex-direction:column;justify-content:space-between;border:1px solid transparent}\n .cal-num{font-weight:700;font-size:13px}\n .cal-meta{font-size:10px;opacity:.9}\n .cal-day.full{background:#dcf5e6;border-color:#a7e0bf;color:#0f5132}\n .cal-day.partial{background:#fdf0d5;border-color:#f0cf95;color:#7a4b06}\n .cal-day.absent{background:#fde2e2;border-color:#f3b4b4;color:#7f1d1d}\n .cal-day.none{background:#f1f4f9;border-color:#e3e8f0;color:#8a94a6}\n .cal-day.muted{opacity:.35}\n .cal-day.today{outline:2px solid #2f6ea8;outline-offset:1px}\n .cal-key{display:flex;gap:16px;flex-wrap:wrap;margin-top:12px;font-size:11.5px;color:#64748b}\n .cal-key i{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:5px}\n .k.full{background:#dcf5e6}.k.partial{background:#fdf0d5}\n .k.absent{background:#fde2e2}.k.none{background:#f1f4f9}\n</style>\n\n<section class="card">\n  <div class="kv">\n    <div><span>Days recorded</span><strong>{{ total }}</strong></div>\n    <div><span>Present</span><strong>{{ present }}</strong></div>\n    <div><span>Attendance</span><strong>{{ pct }}%</strong></div>\n  </div>\n</section>\n\n<section class="card">\n  <h2 class="card-title">Day by day</h2>\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr><th>Date</th><th>Status</th><th>Remarks</th></tr></thead>\n      <tbody>\n      {% for r in rows %}\n        <tr>\n          <td>{{ disp_date(r.att_date) }}</td>\n          <td>{% if r.status == \'Present\' %}<span class="pill ok">Present</span>\n              {% elif r.status == \'Late\' %}<span class="pill warn">Late</span>\n              {% elif r.status == \'Leave\' %}<span class="pill warn">Leave</span>\n              {% else %}<span class="pill bad">Absent</span>{% endif %}</td>\n          <td>{{ r.remarks or \'\' }}</td>\n        </tr>\n      {% else %}\n        <tr><td colspan="3" class="muted">No attendance recorded yet.</td></tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n{% endblock %}\n',
    'my_homework.html':
        '{% extends "base.html" %}\n{% block title %}Homework{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Homework</h1><p>{{ student.name }} · Class {{ student.class_name }}{% if student.section %} – {{ student.section }}{% endif %}</p></div>\n</header>\n\n{% for h in homework %}\n<section class="card">\n  <h2 class="card-title">{{ h.title }}</h2>\n  <p class="muted">{{ h.subject_name or \'General\' }} · due {{ disp_date(h.due_date) or \'—\' }}</p>\n  {% if h.details %}<p>{{ h.details }}</p>{% endif %}\n</section>\n{% else %}\n<section class="card"><p class="muted">No homework has been set for your class yet.</p></section>\n{% endfor %}\n{% endblock %}\n',
    'notices.html':
        '{% extends "base.html" %}\n{% block title %}Notices{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Notices</h1><p>Circulars from the school office</p></div>\n</header>\n\n{% for c in circulars %}\n<section class="card">\n  <h2 class="card-title">{% if c.pinned %}📌 {% endif %}{{ c.title }}</h2>\n  <p class="muted">{{ c.posted_on[:10] }}</p>\n  <p>{{ c.body }}</p>\n</section>\n{% else %}\n<section class="card"><p class="muted">No notices at the moment.</p></section>\n{% endfor %}\n{% endblock %}\n',
    'password.html':
        '{% extends "base.html" %}\n{% block title %}Change password{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Change password</h1><p>Signed in as {{ current_user.username }}</p></div>\n</header>\n\n<section class="card" style="max-width:520px">\n  <form class="form-grid" method="post">\n    <label class="wide">Current password <input type="password" name="current" required></label>\n    <label class="wide">New password <input type="password" name="new" required minlength="6"></label>\n    <label class="wide">New password again <input type="password" name="again" required minlength="6"></label>\n    <div class="form-actions"><button class="btn primary" type="submit">Change password</button></div>\n  </form>\n</section>\n{% endblock %}\n',
    'fees.html':
        '{% extends "base.html" %}\n{% block title %}Fees{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Fees</h1><p>Fee structure, payments and pending dues</p></div>\n</header>\n\n<section class="card">\n  <form class="form-grid" method="get">\n    <label>Class\n      <select name="class_name" onchange="this.form.submit()">\n        <option value="">all classes</option>\n        {% for c in classes %}<option value="{{ c }}" {{ \'selected\' if cls == c }}>{{ c }}</option>{% endfor %}\n      </select>\n    </label>\n    <div class="form-actions"><button class="btn primary" type="submit">Show</button></div>\n  </form>\n</section>\n\n{% if is_admin %}\n<section class="card">\n  <h2 class="card-title">Fee structure</h2>\n  <form class="form-grid" method="post">\n    <input type="hidden" name="action" value="head">\n    <label>Class <input name="class_name" placeholder="8" required></label>\n    <label>Fee head <input name="name" placeholder="Tuition fee" required></label>\n    <label>Amount <input name="amount" type="number" step="0.01" required></label>\n    <label>Frequency\n      <select name="frequency"><option>Monthly</option><option>Quarterly</option>\n        <option>Yearly</option><option>One time</option></select>\n    </label>\n    <div class="form-actions"><button class="btn primary" type="submit">Add fee head</button></div>\n  </form>\n  {% if heads %}\n  <div class="table-wrap" style="margin-top:14px">\n    <table class="grid">\n      <thead><tr><th>Class</th><th>Head</th><th>Amount</th><th>Frequency</th></tr></thead>\n      <tbody>\n      {% for h in heads %}\n        <tr><td>{{ h.class_name or \'—\' }}</td><td>{{ h.name }}</td>\n            <td>{{ fmt_num(h.amount) }}</td><td>{{ h.frequency }}</td></tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n  {% endif %}\n</section>\n{% endif %}\n\n<section class="card">\n  <h2 class="card-title">Record a payment</h2>\n  <form class="form-grid" method="post">\n    <input type="hidden" name="action" value="pay">\n    <input type="hidden" name="class_name" value="{{ cls }}">\n    <label class="wide">Student\n      <select name="student_id" required>\n        <option value="">— choose —</option>\n        {% for r in rows %}\n          <option value="{{ r.student.id }}">{{ r.student.name }} · {{ r.student.class_name }}{% if r.student.section %} – {{ r.student.section }}{% endif %} · due {{ fmt_num(r.due) }}</option>\n        {% endfor %}\n      </select>\n    </label>\n    <label>Amount <input name="amount" type="number" step="0.01" required></label>\n    <label>Date <input type="date" name="paid_on" value="{{ today }}"></label>\n    <label>Mode\n      <select name="mode">{% for m in modes %}<option>{{ m }}</option>{% endfor %}</select>\n    </label>\n    <label>Remarks <input name="remarks" placeholder="optional"></label>\n    <div class="form-actions"><button class="btn primary" type="submit">Save payment</button></div>\n  </form>\n</section>\n\n<section class="card">\n  <h2 class="card-title">Dues</h2>\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr><th>Class</th><th>Roll</th><th>Student</th><th>Total</th>\n                 <th>Paid</th><th>Due</th></tr></thead>\n      <tbody>\n      {% for r in rows %}\n        <tr>\n          <td>{{ r.student.class_name }}{% if r.student.section %} – {{ r.student.section }}{% endif %}</td>\n          <td>{{ r.student.roll_no }}</td>\n          <td>{{ r.student.name }}</td>\n          <td>{{ fmt_num(r.total) }}</td>\n          <td>{{ fmt_num(r.paid) }}</td>\n          <td>{% if r.due > 0 %}<span class="pill bad">{{ fmt_num(r.due) }}</span>{% else %}<span class="pill ok">0</span>{% endif %}</td>\n        </tr>\n      {% else %}\n        <tr><td colspan="6" class="muted">No students yet.</td></tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n{% endblock %}\n',
    'receipt.html':
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n<title>Receipt {{ p.receipt_no }}</title>\n<style>\n body{font:14px/1.6 "Segoe UI",Arial,sans-serif;color:#111;margin:0;padding:28px;background:#fff}\n .wrap{max-width:620px;margin:0 auto;border:1px solid #999;padding:22px 26px}\n h1{font-size:18px;margin:0 0 2px;text-align:center;letter-spacing:.04em}\n .sub{text-align:center;color:#555;font-size:12px;margin-bottom:16px}\n table{width:100%;border-collapse:collapse;margin:14px 0}\n td,th{border-bottom:1px solid #ddd;padding:7px 4px;text-align:left}\n .right{text-align:right}\n .tot{font-weight:700}\n .sign{margin-top:34px;display:flex;justify-content:space-between;font-size:12px;color:#444}\n @media print{ body{padding:0} .wrap{border:none} }\n</style></head><body>\n<div class="wrap">\n  <h1>{{ school_name }}</h1>\n  <div class="sub">Fee receipt · {{ p.receipt_no }}</div>\n  <table>\n    <tr><td>Student</td><td class="right">{{ p.name }}</td></tr>\n    <tr><td>Class / Roll</td><td class="right">{{ p.class_name }}{% if p.section %} – {{ p.section }}{% endif %} / {{ p.roll_no }}</td></tr>\n    <tr><td>Admission No</td><td class="right">{{ p.admission_no }}</td></tr>\n    <tr><td>Fee head</td><td class="right">{{ p.head_name or \'General\' }}</td></tr>\n    <tr><td>Date</td><td class="right">{{ disp_date(p.paid_on) }}</td></tr>\n    <tr><td>Mode</td><td class="right">{{ p.mode }}</td></tr>\n    <tr class="tot"><td>Amount paid</td><td class="right">{{ fmt_num(p.amount) }}</td></tr>\n  </table>\n  {% if p.remarks %}<p><strong>Remarks:</strong> {{ p.remarks }}</p>{% endif %}\n  <div class="sign"><span>Received by the school office</span><span>Authorised signature</span></div>\n</div>\n<script>window.onload=function(){window.print()}</script>\n</body></html>\n',
    'my_fees.html':
        '{% extends "base.html" %}\n{% block title %}My fees{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>My fees</h1><p>{{ student.name }} · Class {{ student.class_name }}{% if student.section %} – {{ student.section }}{% endif %}</p></div>\n</header>\n\n<section class="card">\n  <div class="kv">\n    <div><span>Total fee</span><strong>{{ fmt_num(total) }}</strong></div>\n    <div><span>Paid</span><strong>{{ fmt_num(paid) }}</strong></div>\n    <div><span>Due</span><strong>{% if due > 0 %}<span class="pill bad">{{ fmt_num(due) }}</span>{% else %}<span class="pill ok">Nil</span>{% endif %}</strong></div>\n  </div>\n</section>\n\n<section class="card">\n  <h2 class="card-title">Fee heads</h2>\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr><th>Head</th><th>Amount</th><th>Frequency</th></tr></thead>\n      <tbody>\n      {% for h in heads %}\n        <tr><td>{{ h.name }}</td><td>{{ fmt_num(h.amount) }}</td><td>{{ h.frequency }}</td></tr>\n      {% else %}\n        <tr><td colspan="3" class="muted">No fee structure set for your class.</td></tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n\n<section class="card">\n  <h2 class="card-title">Payments</h2>\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr><th>Date</th><th>Head</th><th>Mode</th><th>Receipt</th><th>Amount</th></tr></thead>\n      <tbody>\n      {% for p in payments %}\n        <tr><td>{{ disp_date(p.paid_on) }}</td><td>{{ p.head_name or \'General\' }}</td>\n            <td>{{ p.mode }}</td><td>{{ p.receipt_no }}</td><td>{{ fmt_num(p.amount) }}</td></tr>\n      {% else %}\n        <tr><td colspan="5" class="muted">No payment recorded yet.</td></tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n{% endblock %}\n',
    'timetable.html':
        '{% extends "base.html" %}\n{% block title %}Timetable{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Timetable</h1><p>Period-wise class timetable{% if scope %} · your class: {{ scope[0] }}{% if scope[1] %} – {{ scope[1] }}{% endif %}{% endif %}</p></div>\n</header>\n\n<section class="card">\n  <form class="form-grid" method="get">\n    <label>Class\n      <select name="class_name" onchange="this.form.submit()">\n        <option value="">— choose —</option>\n        {% for c in classes %}<option value="{{ c }}" {{ \'selected\' if cls == c }}>{{ c }}</option>{% endfor %}\n      </select>\n    </label>\n    <label>Section\n      <select name="section" onchange="this.form.submit()">\n        <option value="">—</option>\n        {% for s in sections %}<option value="{{ s }}" {{ \'selected\' if sec == s }}>{{ s }}</option>{% endfor %}\n      </select>\n    </label>\n    <div class="form-actions"><button class="btn primary" type="submit">Show</button></div>\n  </form>\n</section>\n\n{% if cls %}\n<section class="card">\n  <h2 class="card-title">{{ cls }}{% if sec %} – {{ sec }}{% endif %}</h2>\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr><th>Period</th>{% for d in days %}<th>{{ d[:3] }}</th>{% endfor %}</tr></thead>\n      <tbody>\n      {% for p in periods %}\n        <tr>\n          <td><strong>{{ p }}</strong></td>\n          {% for d in days %}\n            {% set c = cells.get((d, p)) %}\n            <td>\n              {% if c and (c.subject_name or c.teacher) %}\n                <strong>{{ c.subject_code or c.subject_name or \'\' }}</strong>\n                {% if c.teacher %}<br><span class="muted">{{ c.teacher }}</span>{% endif %}\n              {% else %}<span class="muted">—</span>{% endif %}\n            </td>\n          {% endfor %}\n        </tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n\n<section class="card">\n  <h2 class="card-title">Set a period</h2>\n  <form class="form-grid" method="post">\n    <input type="hidden" name="class_name" value="{{ cls }}">\n    <input type="hidden" name="section" value="{{ sec }}">\n    <label>Day\n      <select name="day">{% for d in days %}<option>{{ d }}</option>{% endfor %}</select>\n    </label>\n    <label>Period\n      <select name="period">{% for p in periods %}<option value="{{ p }}">{{ p }}</option>{% endfor %}</select>\n    </label>\n    <label>Subject\n      <select name="subject_id"><option value="">—</option>\n        {% for s in subjects %}<option value="{{ s.id }}">{{ s.subject_code }} · {{ s.subject_name }}</option>{% endfor %}\n      </select>\n    </label>\n    <label>Teacher <input name="teacher" placeholder="e.g. R.K. Singh"></label>\n    <label>Room <input name="room" placeholder="e.g. 12"></label>\n    <div class="form-actions"><button class="btn primary" type="submit">Save period</button></div>\n  </form>\n</section>\n{% endif %}\n{% endblock %}\n',
    'my_timetable.html':
        '{% extends "base.html" %}\n{% block title %}Timetable{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>My timetable</h1><p>{{ student.name }} · Class {{ student.class_name }}{% if student.section %} – {{ student.section }}{% endif %}</p></div>\n</header>\n\n<section class="card">\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr><th>Period</th>{% for d in days %}<th>{{ d[:3] }}</th>{% endfor %}</tr></thead>\n      <tbody>\n      {% for p in periods %}\n        <tr>\n          <td><strong>{{ p }}</strong></td>\n          {% for d in days %}\n            {% set c = cells.get((d, p)) %}\n            <td>{% if c and c.subject_name %}<strong>{{ c.subject_code or c.subject_name }}</strong>{% if c.teacher %}<br><span class="muted">{{ c.teacher }}</span>{% endif %}{% else %}<span class="muted">—</span>{% endif %}</td>\n          {% endfor %}\n        </tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n{% endblock %}\n',
    'report_card.html':
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n<title>Report card · {{ student.name }}</title>\n<style>\n body{font:14.5px/1.65 Georgia,"Times New Roman",serif;color:#111;margin:0;padding:14px;background:#fbf7ee}\n .wrap{max-width:100%;margin:0 auto;border:3px double #1b2a5e;padding:24px 32px 20px;\n       position:relative;overflow:hidden;\n       background:linear-gradient(160deg,#fdfaf3 0%,#f7f0e2 45%,#f2e8d6 100%);\n       min-height:auto;display:flex;flex-direction:column}\n .watermark{position:absolute;inset:0;display:flex;align-items:center;\n            justify-content:center;opacity:.22;\n            pointer-events:none;z-index:0;mix-blend-mode:multiply}\n .watermark img{width:56%;max-width:430px;filter:saturate(1.5) contrast(1.1)}\n .wrap > *:not(.watermark){position:relative;z-index:1}\n .letterhead{display:flex;flex-direction:column;align-items:center;justify-content:center;\n             text-align:center;gap:4px;position:relative;\n             background:transparent;\n             border:none;\n             box-shadow:none;\n             border-radius:0;padding:6px 0 4px;\n             -webkit-print-color-adjust:exact;print-color-adjust:exact}\n .lh-left{display:flex;flex-direction:row;align-items:center;justify-content:center;\n          gap:12px}\n .lh-left img{height:86px;background:none;border:none;border-radius:0;\n              padding:0;box-shadow:none;mix-blend-mode:multiply}\n .lh-left h1{margin:0;font-size:32px;letter-spacing:.09em;color:#1b2a5e;\n              text-shadow:0 1px 0 rgba(255,255,255,.7)}\n .lh-left p{margin:2px 0 0;font-size:12px;letter-spacing:.12em;text-transform:uppercase;\n            color:#e2d6bd}\n .lh-right{position:static;display:flex;align-items:baseline;justify-content:center;\n            gap:6px;line-height:1.2;text-align:center;margin-top:2px}\n .lh-right span{font-size:10px;letter-spacing:.2em;text-transform:uppercase;\n                color:#8a6b4a}\n .lh-right strong{font-size:15px;letter-spacing:.04em;color:#1b2a5e}\n .sub-line{text-align:center;font-size:12px;letter-spacing:.16em;text-transform:uppercase;\n            color:#1b2a5e;font-weight:700;margin:-4px 0 10px}\n .lh-rule{height:4px;border-radius:999px;margin:8px 0 8px;\n          background:linear-gradient(90deg,#1b2a5e,#e07a2f 50%,#c8a04a);\n          -webkit-print-color-adjust:exact;print-color-adjust:exact}\n .who{display:flex;gap:14px;align-items:flex-start;background:rgba(255,252,244,.72);\n       border:1px solid #e2d6bd;border-radius:10px;\n       padding:7px 14px;margin-bottom:8px}\n .sumline{background:rgba(255,252,244,.72);border:1px solid #e2d6bd;border-radius:10px;\n          padding:4px 14px;margin:8px 0}\n .who .pic{width:72px;height:72px;object-fit:cover;border:1px solid #ddcfb2;border-radius:6px}\n .who table{flex:1}\n .legend{display:flex;flex-wrap:wrap;gap:3px 12px;align-items:center;margin:7px 0 3px;background:rgba(255,252,244,.7);border:1px solid #e2d6bd;border-radius:8px;padding:5px 12px;\n         font-size:12px;color:#475569;border-top:1px dashed #ddcfb2;padding-top:10px}\n .legend-title{font-weight:700;letter-spacing:.1em;text-transform:uppercase;font-size:10.5px;color:#1b2a5e}\n .remarks{margin:5px 0 0;font-size:12.5px}\n .perf{margin:9px 0 3px}\n .perf-title{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;\n             color:#1b2a5e;font-weight:700;margin-bottom:8px}\n .perf-row{display:flex;align-items:center;gap:10px;margin:1.5px 0}\n .perf-label{width:44px;font-size:12px;font-weight:700;color:#334155}\n .perf-bars{flex:1;display:flex;flex-direction:column;gap:3px}\n .pb{background:#eef2f8;border-radius:999px;height:7px;overflow:hidden}\n .pb span{display:block;height:100%;border-radius:999px}\n .pb-mine{background:#1b2a5e}\n .pb-avg{background:#94a3b8}\n .perf-val{width:110px;text-align:right;font-size:12px;color:#334155}\n .perf-val em{color:#94a3b8;font-style:normal}\n .perf-key{font-size:10.5px;color:#64748b;margin-top:5px;display:flex;align-items:center;gap:6px}\n .k-mine,.k-avg{width:14px;height:7px;border-radius:999px;display:inline-block}\n .k-mine{background:#1b2a5e}.k-avg{background:#94a3b8;margin-left:10px}\n .co{margin-top:8px;font-size:12px}\n .co th{background:#1b2a5e;color:#f7efdd;font-size:10.5px;letter-spacing:.1em;text-transform:uppercase}\n .co td{padding:2px 9px}\n .co td:last-child{width:70px;background:#fbf7ee}\n .co td.grade{text-align:center;font-weight:700;color:#b4581c}\n .co th.grade-h{width:70px;text-align:center}\n .remark-box{margin-top:4px;font-size:11.5px}\n .remark-box span{font-weight:700;color:#1b2a5e;letter-spacing:.06em;text-transform:uppercase;font-size:10.5px}\n .dots{border-bottom:1px dotted #94a3b8;height:11px;margin-top:2px}\n h1{font-size:24px;margin:0;text-align:center;letter-spacing:.05em;color:#1b2a5e}\n .sub{text-align:center;font-size:12.5px;color:#555;margin-bottom:12px}\n table{width:100%;border-collapse:collapse;margin:10px 0}\n td,th{border:1px solid #ddcfb2;padding:5px 10px;text-align:left;font-size:12.5px}\n tbody td{background:rgba(255,253,247,.66)}\n .meta td{background:transparent}\n th{background:#1b2a5e;color:#f7efdd;letter-spacing:.06em}\n .right{text-align:right}\n .tot{font-weight:700}\n .tot td{background:rgba(240,229,206,.85)}\n .meta td{border:none;padding:5px 8px;font-size:13.5px}\n .sign-table{width:100%;border-collapse:collapse;margin-top:10px}\n .sign-table td{border:1px solid #ddcfb2;padding:5px;text-align:center;font-size:11.5px}\n .sign-table tr.space td{height:52px;vertical-align:bottom}\n .sign-table tr.space img{height:44px;max-width:100%;object-fit:contain}\n @media print{\n   body{padding:0;font-size:12px}\n   .wrap{border-width:1px;min-height:auto;height:auto;padding:14px 18px}\n   .sign-table{margin-top:16px}\n   @page{size:A4;margin:5mm}\n\n   /* logo watermark: table ke peeche saaf dikhe (print preview mein bhi) */\n   .watermark{opacity:.24;mix-blend-mode:multiply;z-index:0;\n              -webkit-print-color-adjust:exact;print-color-adjust:exact}\n   .watermark img{width:56%;max-width:390px;\n                  -webkit-print-color-adjust:exact;print-color-adjust:exact}\n\n   /* rows poori tarah transparent — logo kahin se na kate */\n   tbody td{background:transparent!important}\n   .tot td{background:rgba(240,229,206,.55)!important}\n   .who,.sumline,.legend{background:rgba(255,255,255,.28)!important}\n   th,.co th{background:#1b2a5e!important;color:#f7efdd!important}\n\n   /* ek hi page par fit */\n   .letterhead{padding:2px 0 2px}\n   .lh-left img{height:64px}\n   .lh-left h1{font-size:26px}\n   .lh-rule{margin:6px 0 6px}\n   .sub-line{margin:-2px 0 6px;font-size:11px}\n   td,th{padding:3.5px 8px;font-size:11.5px}\n   .co td{padding:2px 8px;font-size:11.5px}\n   .remarks{font-size:11.5px;margin-top:3px}\n   .remark-box{margin-top:4px}\n   .dots{height:10px}\n   .sign-table tr.space td{height:34px}\n   .sign-table td{padding:3px;font-size:10.5px}\n   .co{margin-top:6px}\n   .co td{padding:1.8px 8px}\n   .legend{padding:4px 10px;margin:5px 0 2px}\n   .wrap{padding:12px 16px}\n   .remark-box{margin-top:2px}\n }\n</style></head><body>\n<div class="wrap">\n  <div class="watermark">\n    {% if logo %}<img src="{{ logo }}" alt="">{% endif %}\n  </div>\n\n  <div class="letterhead">\n    <div class="lh-left">\n      {% if logo %}<img src="{{ logo }}" alt="logo">{% endif %}\n      <h1>{{ school }}</h1>\n    </div>\n    <div class="lh-right">\n      <span>Session</span>\n      <strong>{{ exam.academic_year or \'—\' }}</strong>\n    </div>\n  </div>\n  <div class="lh-rule"></div>\n  <div class="sub-line">Report card · {{ exam_label(exam) }}</div>\n\n  <div class="who">\n    {% if student.photo %}<img class="pic" src="{{ student.photo }}" alt="">{% endif %}\n    <table class="meta">\n      <tr><td><strong>Name:</strong> {{ student.name }}</td>\n          <td class="right"><strong>Class:</strong> {{ student.class_name }}{% if student.section %} – {{ student.section }}{% endif %}</td></tr>\n      <tr><td><strong>Father\'s name:</strong> {{ student.father_name or \'—\' }}</td>\n          <td class="right"><strong>Mother\'s name:</strong> {{ student.mother_name or \'—\' }}</td></tr>\n      <tr><td><strong>Admission No:</strong> {{ student.admission_no }}</td>\n          <td class="right"><strong>Roll No:</strong> {{ student.roll_no }}</td></tr>\n      <tr><td><strong>Date of birth:</strong> {{ disp_date(student.dob) or \'—\' }}</td>\n          <td class="right"><strong>Attendance:</strong> {{ att_present }}/{{ att_total }} ({{ att_pct }}%)</td></tr>\n    </table>\n  </div>\n\n  <table>\n    <thead><tr><th>Subject</th><th class="right">Max</th><th class="right">Pass</th>\n               <th class="right">Theory</th><th class="right">Internal</th>\n               <th class="right">Total</th><th>Result</th></tr></thead>\n    <tbody>\n    {% set ns = namespace(theory=0, internal=0) %}\n    {% for s in subjects %}\n      <tr>\n        <td>{{ s.subject_name }} ({{ s.subject_code }})</td>\n        <td class="right">{{ fmt_num(s.max_marks) }}</td>\n        <td class="right">{{ fmt_num(s.pass_marks) }}</td>\n        <td class="right">{{ fmt_num(s.theory) if s.theory is not none else \'—\' }}</td>\n        <td class="right">{{ fmt_num(s.internal) if s.internal is not none else \'—\' }}</td>\n        <td class="right"><strong>{{ fmt_num(s.marks_obtained) }}</strong></td>\n        <td>{% if s.marks_obtained is not none and s.pass_marks is not none and s.marks_obtained < s.pass_marks %}Fail{% else %}Pass{% endif %}</td>\n      </tr>\n      {% if s.theory is not none %}{% set ns.theory = ns.theory + s.theory %}{% endif %}\n      {% if s.internal is not none %}{% set ns.internal = ns.internal + s.internal %}{% endif %}\n    {% endfor %}\n    <tr class="tot">\n      <td>Grand total</td>\n      <td class="right">{{ fmt_num(mine.total_max) }}</td>\n      <td></td>\n      <td class="right">{{ fmt_num(ns.theory) if ns.theory else \'—\' }}</td>\n      <td class="right">{{ fmt_num(ns.internal) if ns.internal else \'—\' }}</td>\n      <td class="right">{{ fmt_num(mine.obtained) }}</td>\n      <td>{{ mine.result }}</td>\n    </tr>\n    </tbody>\n  </table>\n\n  <table class="meta sumline">\n    <tr><td><strong>Percentage:</strong> {{ \'%.2f\'|format(mine.percentage) }}%</td>\n        <td class="right"><strong>Grade:</strong> {{ mine.grade }}</td></tr>\n    <tr><td><strong>Rank in class:</strong> {{ mine.rank }}</td>\n        <td class="right"><strong>Subjects failed:</strong> {{ mine.failed_subjects }}</td></tr>\n    <tr><td><strong>Result:</strong> {{ mine.result }}</td>\n        <td class="right"><strong>Result date:</strong> {{ issued_on }}</td></tr>\n  </table>\n\n  <div class="legend">\n    <span class="legend-title">Grading</span>\n    <span><b>A1</b> 91–100</span><span><b>A2</b> 81–90</span>\n    <span><b>B1</b> 71–80</span><span><b>B2</b> 61–70</span>\n    <span><b>C1</b> 51–60</span><span><b>C2</b> 41–50</span>\n    <span><b>D</b> 33–40</span><span><b>E</b> below 33</span>\n  </div>\n\n  <p class="remarks"><strong>Remarks:</strong> {{ mine.result }} — promoted to the next class.{% if mine.failed_subjects %} Compartment in {{ mine.failed_subjects }} subject(s).{% endif %}</p>\n  <p class="remarks"><strong>Date of issue:</strong> {{ issued_on }} &nbsp;·&nbsp; <strong>Position:</strong> {{ mine.rank }} in class</p>\n\n  <table class="co">\n    <thead><tr><th>Co-scholastic areas</th><th class="grade-h">Grade</th></tr></thead>\n    <tbody>\n      {% for area, grade in co_areas %}\n        <tr><td>{{ area|safe }}</td><td class="grade">{{ grade }}</td></tr>\n      {% endfor %}\n    </tbody>\n  </table>\n\n  <div class="remark-box">\n    <span>Class teacher\'s remark</span>\n    <div class="dots"></div><div class="dots"></div>\n  </div>\n\n\n\n  <table class="sign-table">\n    <tr class="space">\n      <td>{% if teacher_sign %}<img src="{{ teacher_sign }}" alt="signature">{% endif %}</td>\n      <td>{% if principal_sign %}<img src="{{ principal_sign }}" alt="signature">{% endif %}</td>\n      <td></td>\n    </tr>\n    <tr>\n      <td>Class teacher\'s signature</td>\n      <td>Principal\'s signature</td>\n      <td>Parent\'s signature</td>\n    </tr>\n  </table>\n</div>\n{% if not bulk %}\n<div class="no-print" style="max-width:820px;margin:14px auto;text-align:center">\n  <button onclick="window.print()"\n          style="padding:10px 22px;border:none;border-radius:10px;background:#1b2a5e;\n                 color:#fff;font-size:14px;font-weight:600;cursor:pointer">\n    Print / Save as PDF\n  </button>\n</div>\n<style>@media print{.no-print{display:none}}</style>\n{% if auto_print %}\n<script>\n  // print dialog ko load ke baad kholo (kuch browsers block karte hain, isliye try/catch)\n  window.addEventListener(\'load\', function () {\n    setTimeout(function () {\n      try { window.print(); } catch (e) { /* button se print ho sakta hai */ }\n    }, 300);\n  });\n</script>\n{% endif %}\n{% endif %}\n</body></html>\n',
    'transport.html':
        '{% extends "base.html" %}\n{% block title %}Transport{% endblock %}\n{% block content %}\n<header class="page-head"><div><h1>Transport</h1><p>Routes, vehicles, drivers and who travels on which bus</p></div></header>\n\n<section class="card">\n  <h2 class="card-title">Add a route</h2>\n  <form class="form-grid" method="post">\n    <input type="hidden" name="action" value="route">\n    <label>Route name <input name="route_name" required placeholder="Route 1 — Dwarka"></label>\n    <label>Vehicle no <input name="vehicle_no" placeholder="DL 1C 1234"></label>\n    <label>Driver <input name="driver_name" placeholder="Ram Singh"></label>\n    <label>Driver phone <input name="driver_phone" placeholder="98765 43210"></label>\n    <label>Capacity <input name="capacity" type="number" value="40"></label>\n    <label class="wide">Stops <input name="stops" placeholder="Sector 12, Sector 7, School gate"></label>\n    <div class="form-actions"><button class="btn primary" type="submit">Add route</button></div>\n  </form>\n</section>\n\n<section class="card">\n  <h2 class="card-title">Assign a student</h2>\n  <form class="form-grid" method="post">\n    <input type="hidden" name="action" value="assign">\n    <label class="wide">Student\n      <select name="student_id" required>\n        <option value="">— choose —</option>\n        {% for s in students %}<option value="{{ s.id }}">{{ s.name }} · {{ s.class_name }}{% if s.section %} – {{ s.section }}{% endif %} · roll {{ s.roll_no }}</option>{% endfor %}\n      </select>\n    </label>\n    <label>Route\n      <select name="route_id" required>\n        <option value="">— choose —</option>\n        {% for r in routes %}<option value="{{ r.id }}">{{ r.route_name }}</option>{% endfor %}\n      </select>\n    </label>\n    <label>Stop <input name="stop_name" placeholder="Sector 12"></label>\n    <div class="form-actions"><button class="btn primary" type="submit">Assign</button></div>\n  </form>\n</section>\n\n<section class="card">\n  <h2 class="card-title">Routes</h2>\n  <div class="table-wrap"><table class="grid">\n    <thead><tr><th>Route</th><th>Vehicle</th><th>Driver</th><th>Phone</th><th>Seats</th><th>Stops</th></tr></thead>\n    <tbody>\n    {% for r in routes %}\n      <tr><td><strong>{{ r.route_name }}</strong></td><td>{{ r.vehicle_no or \'—\' }}</td>\n          <td>{{ r.driver_name or \'—\' }}</td><td>{{ r.driver_phone or \'—\' }}</td>\n          <td>{{ r.taken }}/{{ r.capacity }}</td><td class="muted">{{ r.stops or \'—\' }}</td></tr>\n    {% else %}<tr><td colspan="6" class="muted">No routes yet.</td></tr>{% endfor %}\n    </tbody>\n  </table></div>\n</section>\n\n<section class="card">\n  <h2 class="card-title">Students on transport</h2>\n  <div class="table-wrap"><table class="grid">\n    <thead><tr><th>Route</th><th>Student</th><th>Class</th><th>Roll</th><th>Stop</th><th></th></tr></thead>\n    <tbody>\n    {% for a in assigned %}\n      <tr><td>{{ a.route_name or \'—\' }}</td><td>{{ a.name }}</td>\n          <td>{{ a.class_name }}{% if a.section %} – {{ a.section }}{% endif %}</td>\n          <td>{{ a.roll_no }}</td><td>{{ a.stop_name or \'—\' }}</td>\n          <td><form method="post"><input type="hidden" name="action" value="unassign">\n              <input type="hidden" name="student_id" value="{{ a.student_id }}">\n              <button class="btn ghost small" type="submit">Remove</button></form></td></tr>\n    {% else %}<tr><td colspan="6" class="muted">Nobody assigned yet.</td></tr>{% endfor %}\n    </tbody>\n  </table></div>\n</section>\n{% endblock %}\n',
    'my_transport.html':
        '{% extends "base.html" %}\n{% block title %}My transport{% endblock %}\n{% block content %}\n<header class="page-head"><div><h1>My transport</h1><p>{{ student.name }} · Class {{ student.class_name }}{% if student.section %} – {{ student.section }}{% endif %}</p></div></header>\n{% if t %}\n<section class="card">\n  <div class="kv">\n    <div><span>Route</span><strong>{{ t.route_name or \'—\' }}</strong></div>\n    <div><span>Vehicle</span><strong>{{ t.vehicle_no or \'—\' }}</strong></div>\n    <div><span>Driver</span><strong>{{ t.driver_name or \'—\' }}</strong></div>\n    <div><span>Driver phone</span><strong>{{ t.driver_phone or \'—\' }}</strong></div>\n    <div><span>Your stop</span><strong>{{ t.stop_name or \'—\' }}</strong></div>\n  </div>\n  {% if t.stops %}<p class="muted" style="margin-top:14px">Stops: {{ t.stops }}</p>{% endif %}\n</section>\n{% else %}\n<section class="card"><p class="muted">You are not on a school bus route.</p></section>\n{% endif %}\n{% endblock %}\n',
    'library.html':
        '{% extends "base.html" %}\n{% block title %}Library{% endblock %}\n{% block content %}\n<header class="page-head"><div><h1>Library</h1><p>Books, issue and return</p></div></header>\n\n<section class="card">\n  <h2 class="card-title">Add a book</h2>\n  <form class="form-grid" method="post">\n    <input type="hidden" name="action" value="book">\n    <label class="wide">Title <input name="title" required></label>\n    <label>Author <input name="author"></label>\n    <label>ISBN <input name="isbn"></label>\n    <label>Category <input name="category" placeholder="Science / Fiction"></label>\n    <label>Copies <input name="copies" type="number" value="1" min="1"></label>\n    <div class="form-actions"><button class="btn primary" type="submit">Add book</button></div>\n  </form>\n</section>\n\n<section class="card">\n  <h2 class="card-title">Issue a book</h2>\n  <form class="form-grid" method="post">\n    <input type="hidden" name="action" value="issue">\n    <label>Book\n      <select name="book_id" required><option value="">— choose —</option>\n        {% for b in books %}<option value="{{ b.id }}">{{ b.title }} ({{ b.copies - b.out }} free)</option>{% endfor %}\n      </select>\n    </label>\n    <label class="wide">Student\n      <select name="student_id" required><option value="">— choose —</option>\n        {% for s in students %}<option value="{{ s.id }}">{{ s.name }} · {{ s.class_name }}{% if s.section %} – {{ s.section }}{% endif %}</option>{% endfor %}\n      </select>\n    </label>\n    <div class="form-actions"><button class="btn primary" type="submit">Issue for 14 days</button></div>\n  </form>\n</section>\n\n<section class="card">\n  <h2 class="card-title">Books</h2>\n  <div class="table-wrap"><table class="grid">\n    <thead><tr><th>Title</th><th>Author</th><th>Category</th><th>Copies</th><th>Out</th></tr></thead>\n    <tbody>\n    {% for b in books %}\n      <tr><td><strong>{{ b.title }}</strong></td><td>{{ b.author or \'—\' }}</td>\n          <td>{{ b.category or \'—\' }}</td><td>{{ b.copies }}</td><td>{{ b.out }}</td></tr>\n    {% else %}<tr><td colspan="5" class="muted">No books yet.</td></tr>{% endfor %}\n    </tbody>\n  </table></div>\n</section>\n\n<section class="card">\n  <h2 class="card-title">Issued books</h2>\n  <div class="table-wrap"><table class="grid">\n    <thead><tr><th>Book</th><th>Student</th><th>Issued</th><th>Due</th><th>Status</th><th></th></tr></thead>\n    <tbody>\n    {% for i in issues %}\n      <tr>\n        <td>{{ i.title }}</td><td>{{ i.name }}</td>\n        <td>{{ disp_date(i.issued_on) }}</td><td>{{ disp_date(i.due_on) }}</td>\n        <td>{% if i.returned_on %}<span class="pill ok">Returned</span>\n            {% elif i.due_on and i.due_on < today %}<span class="pill bad">Overdue</span>\n            {% else %}<span class="pill warn">With student</span>{% endif %}</td>\n        <td>{% if not i.returned_on %}\n            <form method="post" action="{{ url_for(\'library_return\', iid=i.id) }}">\n              <button class="btn ghost small" type="submit">Return</button></form>\n            {% endif %}</td>\n      </tr>\n    {% else %}<tr><td colspan="6" class="muted">Nothing issued yet.</td></tr>{% endfor %}\n    </tbody>\n  </table></div>\n</section>\n{% endblock %}\n',
    'my_library.html':
        '{% extends "base.html" %}\n{% block title %}Library{% endblock %}\n{% block content %}\n<header class="page-head"><div><h1>Library</h1><p>Books issued to {{ student.name }}</p></div></header>\n<section class="card">\n  <div class="table-wrap"><table class="grid">\n    <thead><tr><th>Book</th><th>Author</th><th>Issued</th><th>Due</th><th>Status</th></tr></thead>\n    <tbody>\n    {% for r in rows %}\n      <tr><td><strong>{{ r.title }}</strong></td><td>{{ r.author or \'—\' }}</td>\n          <td>{{ disp_date(r.issued_on) }}</td><td>{{ disp_date(r.due_on) }}</td>\n          <td>{% if r.returned_on %}<span class="pill ok">Returned</span>\n              {% elif r.due_on and r.due_on < today %}<span class="pill bad">Overdue</span>\n              {% else %}<span class="pill warn">With me</span>{% endif %}</td></tr>\n    {% else %}<tr><td colspan="5" class="muted">No books issued to you.</td></tr>{% endfor %}\n    </tbody>\n  </table></div>\n</section>\n{% endblock %}\n',
    'staff.html':
        '{% extends "base.html" %}\n{% block title %}Staff{% endblock %}\n{% block content %}\n<header class="page-head"><div><h1>Staff</h1><p>Teachers and office staff</p></div></header>\n{% if is_admin %}\n<section class="card">\n  <h2 class="card-title">Add a staff member</h2>\n  <form class="form-grid" method="post">\n    <label>Name <input name="name" required></label>\n    <label>Role <input name="role" placeholder="Teacher / Clerk / Driver"></label>\n    <label>Subject <input name="subject" placeholder="Mathematics"></label>\n    <label>Phone <input name="phone"></label>\n    <label>Email <input name="email"></label>\n    <label>Joining date <input type="date" name="join_date"></label>\n    <label>Salary <input name="salary" type="number" step="0.01"></label>\n    <div class="form-actions"><button class="btn primary" type="submit">Add</button></div>\n  </form>\n</section>\n{% endif %}\n<section class="card">\n  <div class="table-wrap"><table class="grid">\n    <thead><tr><th>Name</th><th>Role</th><th>Subject</th><th>Phone</th><th>Joined</th><th>Salary</th><th></th></tr></thead>\n    <tbody>\n    {% for s in staff %}\n      <tr><td>{% if s.photo %}<img class="avatar" src="{{ s.photo }}" alt=""> {% endif %}<strong>{{ s.name }}</strong></td><td>{{ s.role or \'—\' }}</td>\n          <td>{{ s.subject or \'—\' }}</td><td>{{ s.phone or \'—\' }}</td>\n          <td>{{ disp_date(s.join_date) }}</td><td>{{ fmt_num(s.salary) }}</td>\n          <td>{% if is_admin %}<form method="post" action="{{ url_for(\'staff_toggle\', sid=s.id) }}">\n              <button class="btn ghost small" type="submit">{{ \'Deactivate\' if s.active else \'Activate\' }}</button></form>{% endif %}</td></tr>\n    {% else %}<tr><td colspan="7" class="muted">No staff records yet.</td></tr>{% endfor %}\n    </tbody>\n  </table></div>\n</section>\n{% endblock %}\n',
    'events.html':
        '{% extends "base.html" %}\n{% block title %}Calendar{% endblock %}\n{% block content %}\n<header class="page-head"><div><h1>School calendar</h1><p>Holidays, exams, meetings and functions</p></div></header>\n\n<section class="card">\n  <h2 class="card-title">Add an event</h2>\n  <form class="form-grid" method="post">\n    <label>Title <input name="title" required></label>\n    <label>Date <input type="date" name="event_date"></label>\n    <label>Kind\n      <select name="kind">{% for k in kinds %}<option>{{ k }}</option>{% endfor %}</select>\n    </label>\n    <label class="wide">Details <input name="details"></label>\n    <div class="form-actions"><button class="btn primary" type="submit">Add event</button></div>\n  </form>\n</section>\n\n<section class="card">\n  <div class="table-wrap"><table class="grid">\n    <thead><tr><th>Date</th><th>Event</th><th>Kind</th><th>Details</th><th></th></tr></thead>\n    <tbody>\n    {% for e in events %}\n      <tr><td>{{ disp_date(e.event_date) or \'—\' }}</td>\n          <td><strong>{{ e.title }}</strong></td>\n          <td><span class="pill warn">{{ e.kind }}</span></td>\n          <td class="muted">{{ e.details or \'\' }}</td>\n          <td><form method="post" action="{{ url_for(\'event_delete\', eid=e.id) }}">\n              <button class="btn ghost small" type="submit">Delete</button></form></td></tr>\n    {% else %}<tr><td colspan="5" class="muted">No events yet.</td></tr>{% endfor %}\n    </tbody>\n  </table></div>\n</section>\n{% endblock %}\n',
    'certificates.html':
        '{% extends "base.html" %}\n{% block title %}Certificates{% endblock %}\n{% block content %}\n<header class="page-head"><div><h1>Certificates</h1><p>Bonafide, transfer and character certificates — print ready</p></div></header>\n<section class="card">\n  <form class="form-grid" method="get">\n    <label>Class\n      <select name="class_name" onchange="this.form.submit()">\n        <option value="">all classes</option>\n        {% for c in classes %}<option value="{{ c }}" {{ \'selected\' if cls == c }}>{{ c }}</option>{% endfor %}\n      </select>\n    </label>\n    <div class="form-actions"><button class="btn primary" type="submit">Show</button></div>\n  </form>\n</section>\n<section class="card">\n  <div class="table-wrap"><table class="grid">\n    <thead><tr><th>Class</th><th>Roll</th><th>Student</th><th>Admission No</th><th>Certificates</th></tr></thead>\n    <tbody>\n    {% for s in students %}\n      <tr><td>{{ s.class_name }}{% if s.section %} – {{ s.section }}{% endif %}</td>\n          <td>{{ s.roll_no }}</td><td><strong>{{ s.name }}</strong></td>\n          <td>{{ s.admission_no }}</td>\n          <td style="white-space:nowrap">\n            {% for t in types %}\n              <a class="btn ghost small" target="_blank"\n                 href="{{ url_for(\'certificate_print\', sid=s.id, type=t) }}">{{ t }}</a>\n            {% endfor %}\n          </td></tr>\n    {% else %}<tr><td colspan="5" class="muted">No students yet.</td></tr>{% endfor %}\n    </tbody>\n  </table></div>\n</section>\n{% endblock %}\n',
    'certificate_print.html':
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n<title>{{ kind }} certificate · {{ student.name }}</title>\n<style>\n body{font:15px/1.9 Georgia,"Times New Roman",serif;color:#111;margin:0;padding:30px;background:#fff}\n .wrap{max-width:680px;margin:0 auto;border:3px double #1f3a5f;padding:34px 40px}\n h1{font-size:21px;text-align:center;margin:0;letter-spacing:.08em;color:#1f3a5f}\n .sub{text-align:center;font-size:12px;color:#555;letter-spacing:.2em;margin:6px 0 22px}\n h2{text-align:center;font-size:16px;letter-spacing:.12em;margin:0 0 22px;text-decoration:underline}\n p{margin:0 0 14px;text-align:justify}\n .sign{margin-top:44px;display:flex;justify-content:space-between;font-size:12px}\n @media print{ body{padding:0} .wrap{border-width:2px} }\n</style></head><body>\n<div class="wrap">\n  <h1>{{ school_name }}</h1>\n  <div class="sub">CERTIFICATE</div>\n  <h2>{{ kind|upper }} CERTIFICATE</h2>\n\n  {% if kind == \'Bonafide\' %}\n    <p>This is to certify that <strong>{{ student.name }}</strong>, son/daughter of\n       <strong>{{ student.father_name or \'—\' }}</strong> and\n       <strong>{{ student.mother_name or \'—\' }}</strong>, is a bona fide student of\n       this school studying in class <strong>{{ student.class_name }}{% if student.section %} – {{ student.section }}{% endif %}</strong>\n       with admission number <strong>{{ student.admission_no }}</strong> and roll number\n       <strong>{{ student.roll_no }}</strong>.</p>\n    <p>This certificate is issued on request for official purposes.</p>\n  {% elif kind == \'Transfer\' %}\n    <p>This is to certify that <strong>{{ student.name }}</strong>, son/daughter of\n       <strong>{{ student.father_name or \'—\' }}</strong>, admission number\n       <strong>{{ student.admission_no }}</strong>, was a student of this school in class\n       <strong>{{ student.class_name }}{% if student.section %} – {{ student.section }}{% endif %}</strong>.</p>\n    <p>His/her conduct during this period was satisfactory. All dues have been cleared\n       and the student is being transferred with the consent of the parents.</p>\n  {% elif kind == \'Character\' %}\n    <p>This is to certify that <strong>{{ student.name }}</strong>, son/daughter of\n       <strong>{{ student.father_name or \'—\' }}</strong>, was a student of class\n       <strong>{{ student.class_name }}{% if student.section %} – {{ student.section }}{% endif %}</strong>\n       in this school.</p>\n    <p>During his/her stay in the school his/her conduct and character were found to be\n       <strong>good</strong>. He/she took part in the co-curricular activities of the school.</p>\n  {% else %}\n    <p>This is to certify that <strong>{{ student.name }}</strong>, class\n       <strong>{{ student.class_name }}{% if student.section %} – {{ student.section }}{% endif %}</strong>,\n       admission number <strong>{{ student.admission_no }}</strong>, has no outstanding\n       dues towards fees of this school as on <strong>{{ today }}</strong>.</p>\n  {% endif %}\n\n  <p style="margin-top:26px">Date: <strong>{{ today }}</strong></p>\n  <div class="sign"><span>Class teacher</span><span>Principal</span></div>\n</div>\n<script>window.onload=function(){window.print()}</script>\n</body></html>\n',
    'payroll_slip.html':
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><title>Salary slip</title>\n<style>\n body{font:14px/1.7 "Segoe UI",Arial,sans-serif;margin:0;padding:26px}\n .wrap{max-width:620px;margin:0 auto;border:1px solid #999;padding:24px}\n h1{font-size:17px;text-align:center;margin:0}\n .sub{text-align:center;color:#555;font-size:12px;margin-bottom:16px}\n table{width:100%;border-collapse:collapse;margin-top:10px}\n td{padding:7px 4px;border-bottom:1px solid #ddd}\n .r{text-align:right} .tot{font-weight:700}\n .sign{margin-top:36px;display:flex;justify-content:space-between;font-size:12px;color:#444}\n @media print{body{padding:0} .wrap{border:none}}\n</style></head><body>\n<div class="wrap">\n  <h1>{{ school_name }}</h1>\n  <div class="sub">Salary slip · {{ p.month }}</div>\n  <table>\n    <tr><td>Name</td><td class="r">{{ p.name }}</td></tr>\n    <tr><td>Role</td><td class="r">{{ p.role or \'—\' }}{% if p.subject %} · {{ p.subject }}{% endif %}</td></tr>\n    <tr><td>Joined</td><td class="r">{{ disp_date(p.join_date) or \'—\' }}</td></tr>\n    <tr><td>Status</td><td class="r">{{ p.status }}{% if p.paid_on %} on {{ disp_date(p.paid_on) }}{% endif %}</td></tr>\n    <tr class="tot"><td>Net salary</td><td class="r">{{ fmt_num(p.amount) }}</td></tr>\n  </table>\n  <div class="sign"><span>Accountant</span><span>Principal</span></div>\n</div>\n<script>window.onload=function(){window.print()}</script>\n</body></html>\n',
    'notifications.html':
        '{% extends "base.html" %}\n{% block title %}Messages{% endblock %}\n{% block content %}\n<header class="page-head"><div><h1>Message log</h1><p>SMS / WhatsApp text that went to parents and staff</p></div></header>\n<section class="card">\n  <h2 class="card-title">New message</h2>\n  <form class="form-grid" method="post">\n    <label>Channel <select name="channel"><option>SMS</option><option>WhatsApp</option><option>Email</option><option>Notice</option></select></label>\n    <label>Audience <select name="audience"><option value="all">Everyone</option>\n      <option value="parents">Parents</option><option value="students">Students</option>\n      <option value="teachers">Teachers</option></select></label>\n    <label class="wide">Message <textarea name="message" rows="3" required placeholder="Dear parents, the school will remain closed on..."></textarea></label>\n    <div class="form-actions"><button class="btn primary" type="submit">Save to log</button></div>\n  </form>\n  <p class="muted">This is a log only. Sending real SMS requires a gateway such as MSG91 or Twilio.</p>\n</section>\n<section class="card">\n  <div class="table-wrap"><table class="grid">\n    <thead><tr><th>When</th><th>Channel</th><th>Audience</th><th>Message</th><th>By</th></tr></thead>\n    <tbody>{% for r in rows %}\n      <tr><td>{{ r.sent_on[:16] }}</td><td>{{ r.channel }}</td><td>{{ r.audience }}</td>\n          <td>{{ r.message }}</td><td>{{ r.author or \'—\' }}</td></tr>\n    {% else %}<tr><td colspan="5" class="muted">Nothing sent yet.</td></tr>{% endfor %}</tbody>\n  </table></div>\n</section>\n{% endblock %}\n',
    'my_home.html':
        '{% extends "base.html" %}\n{% block title %}Home\n{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Hello, {{ student.name.split()[0] }}</h1>\n    <p>Class {{ student.class_name }}{% if student.section %} – {{ student.section }}{% endif %} · Roll {{ student.roll_no }} · {{ today_name }}</p></div>\n</header>\n\n<div class="tiles">\n  <div class="tile"><i class="bar green"></i><b>{{ att_pct }}%</b><span>Attendance</span></div>\n  <div class="tile"><i class="bar indigo"></i><b>{% if latest %}{{ \'%.1f\'|format(latest.percentage) }}%{% else %}—{% endif %}</b><span>Last result</span></div>\n  <div class="tile"><i class="bar amber"></i><b>{{ todo }}</b><span>Homework to do</span></div>\n  <div class="tile"><i class="bar sky"></i><b>{{ fmt_num(fee_due) }}</b><span>Fees due</span></div>\n</div>\n\n<div class="two-col">\n  <section class="card">\n    <div class="card-head"><h2>Attendance — last 10 days</h2>\n      <a class="btn ghost small" href="{{ url_for(\'my_attendance\') }}">Details</a></div>\n    <div class="days">\n      {% for a in last_days|reverse %}\n        <span class="day {{ \'ok\' if a.status in (\'Present\',\'Late\') else \'bad\' }}"\n              title="{{ disp_date(a.att_date) }} · {{ a.status }}">{{ a.att_date[8:10] }}</span>\n      {% else %}<span class="muted">No attendance yet.</span>{% endfor %}\n    </div>\n    <p class="muted">{{ att_total }} day(s) recorded · {{ att_pct }}% present</p>\n    {% if last_days %}\n    <div class="mini-list">\n      {% for a in last_days[:4] %}\n        <div class="row-line"><strong>{{ disp_date(a.att_date) }}</strong>\n          <span class="{{ \'ok-text\' if a.status in (\'Present\',\'Late\') else \'bad-text\' }}">{{ a.status }}</span>\n          <span class="muted">{{ a.remarks or \'\' }}</span></div>\n      {% endfor %}\n    </div>\n    {% endif %}\n  </section>\n\n  <section class="card">\n    <div class="card-head"><h2>{% if exam %}{{ exam_label(exam) }}{% else %}Marks{% endif %}</h2>\n      <a class="btn ghost small" href="{{ url_for(\'my_result\') }}">Result</a></div>\n    {% if subject_bars %}\n      <div class="charts">\n        {% for b in subject_bars %}\n        <div class="chart">\n          <div class="chart-bar"><span style="width: {{ b.pct }}%; background: linear-gradient(90deg,#e07a2f,#1b2a5e)"></span></div>\n          <div class="chart-label">{{ b.label }} · {{ fmt_num(b.got) }}/{{ fmt_num(b.max) }} <strong>{{ b.pct }}%</strong></div>\n        </div>\n        {% endfor %}\n      </div>\n      {% if latest %}<p class="muted">Grade {{ latest.grade }} · Rank {{ latest.rank }} · {{ latest.result }}</p>{% endif %}\n    {% else %}\n      <p class="muted">No marks published yet.</p>\n    {% endif %}\n  </section>\n</div>\n\n<div class="two-col">\n  <section class="card">\n    <div class="card-head"><h2>Homework</h2>\n      <a class="btn ghost small" href="{{ url_for(\'my_homework\') }}">All</a></div>\n    {% for h in homework_rows %}\n      <div class="row-line"><strong>{{ h.subject_name or \'General\' }}</strong>\n        <span>{{ h.title }}</span>\n        <span class="muted">{{ disp_date(h.due_date) or \'\' }}</span></div>\n    {% else %}<p class="muted">No homework right now.</p>{% endfor %}\n  </section>\n\n  <section class="card">\n    <div class="card-head"><h2>{% if periods %}Today\'s periods{% else %}This week{% endif %}</h2>\n      <a class="btn ghost small" href="{{ url_for(\'my_timetable\') }}">Timetable</a></div>\n    {% if periods %}\n      {% for p in periods %}\n        <div class="row-line"><strong>P{{ p.period }}</strong>\n          <span>{{ p.subject_name or p.subject_code or \'—\' }}</span>\n          <span class="muted">{{ p.teacher or \'\' }}</span></div>\n      {% endfor %}\n    {% elif by_day %}\n      {% for day, subs in by_day.items() %}\n        <div class="row-line"><strong>{{ day[:3] }}</strong>\n          <span>{{ subs|join(\' · \') }}</span></div>\n      {% endfor %}\n    {% else %}\n      <p class="muted">Timetable not published yet.</p>\n    {% endif %}\n  </section>\n</div>\n\n<div class="two-col">\n  <section class="card">\n    <div class="card-head"><h2>Fees</h2>\n      <a class="btn ghost small" href="{{ url_for(\'my_fees\') }}">Details</a></div>\n    <div class="chart">\n      {% set pct = (fee_paid / fee_total * 100)|round|int if fee_total else 0 %}\n      <div class="chart-bar"><span style="width: {{ pct }}%; background: linear-gradient(90deg,#1f7a4d,#7bbf9b)"></span></div>\n      <div class="chart-label">Paid {{ fmt_num(fee_paid) }} of {{ fmt_num(fee_total) }} <strong>{{ pct }}%</strong></div>\n    </div>\n    {% if last_payment %}\n      <div class="row-line" style="margin-top:10px">\n        <strong>Last payment</strong><span>{{ fmt_num(last_payment.amount) }}</span>\n        <span class="muted">{{ disp_date(last_payment.paid_on) }} · {{ last_payment.mode }}</span></div>\n    {% endif %}\n    <p class="muted">Due: {{ fmt_num(fee_due) }}</p>\n  </section>\n\n  <section class="card">\n    <div class="card-head"><h2>Transport &amp; library</h2></div>\n    {% if bus %}\n      <div class="row-line"><strong>Bus</strong><span>{{ bus.route_name or \'—\' }}</span>\n        <span class="muted">{{ bus.vehicle_no or \'\' }}{% if bus.stop_name %} · stop {{ bus.stop_name }}{% endif %}</span></div>\n      <div class="row-line"><strong>Driver</strong><span>{{ bus.driver_name or \'—\' }}</span>\n        <span class="muted">{{ bus.driver_phone or \'\' }}</span></div>\n    {% else %}<p class="muted">Not on a bus route.</p>{% endif %}\n    {% for b in books %}\n      <div class="row-line"><strong>Book</strong><span>{{ b.title }}</span>\n        <span class="muted">due {{ disp_date(b.due_on) }}</span></div>\n    {% endfor %}\n    {% if not books %}<p class="muted">No library book with you.</p>{% endif %}\n  </section>\n</div>\n\n<section class="card">\n  <div class="card-head"><h2>Notices</h2>\n    <a class="btn ghost small" href="{{ url_for(\'notices\') }}">All</a></div>\n  {% for n in notices %}\n    <div class="row-line"><strong>{{ n.title }}</strong>\n      <span class="muted">{{ n.posted_on[:10] }}</span></div>\n  {% else %}<p class="muted">No notices.</p>{% endfor %}\n</section>\n<div class="two-col">\n  <section class="card">\n    <div class="card-head"><h2>My exam history</h2>\n      <a class="btn ghost small" href="{{ url_for(\'my_result\') }}">Result</a></div>\n    {% for h in history %}\n      <div class="chart">\n        <div class="chart-bar"><span style="width: {{ h.pct }}%; background: #7c3aed"></span></div>\n        <div class="chart-label">{{ h.label }} · <strong>{{ h.pct }}%</strong> · grade {{ h.grade }}</div>\n      </div>\n    {% else %}<p class="muted">No exam history yet.</p>{% endfor %}\n  </section>\n\n  <section class="card">\n    <div class="card-head"><h2>Coming up at school</h2></div>\n    {% for e in upcoming_events %}\n      <div class="row-line"><strong>{{ disp_date(e.event_date) }}</strong>\n        <span>{{ e.title }}</span><span class="muted">{{ e.kind }}</span></div>\n    {% else %}<p class="muted">No events listed.</p>{% endfor %}\n  </section>\n</div>\n\n<div class="two-col">\n  <section class="card">\n    <div class="card-head"><h2>Upcoming papers</h2>\n      <a class="btn ghost small" href="{{ url_for(\'my_result\') }}">Result</a></div>\n    {% for p in papers %}\n      <div class="row-line"><strong>{{ disp_date(p.exam_date) }}</strong>\n        <span>{{ p.subject_name or \'—\' }}</span>\n        <span class="muted">{{ p.start_time or \'\' }}{% if p.room %} · room {{ p.room }}{% endif %}</span></div>\n    {% else %}<p class="muted">No papers scheduled for your class.</p>{% endfor %}\n  </section>\n\n  <section class="card">\n    <div class="card-head"><h2>Attendance summary</h2>\n      <a class="btn ghost small" href="{{ url_for(\'my_attendance\') }}">Details</a></div>\n    <div class="kv">\n      <div><span>Present</span><strong class="ok-text">{{ tally.Present + tally.Late }}</strong></div>\n      <div><span>Absent</span><strong class="bad-text">{{ tally.Absent }}</strong></div>\n      <div><span>Late</span><strong>{{ tally.Late }}</strong></div>\n      <div><span>Leave</span><strong>{{ tally.Leave }}</strong></div>\n    </div>\n  </section>\n</div>\n\n<section class="card">\n  <div class="card-head"><h2>School staff</h2></div>\n  {% for t in teachers %}\n    <div class="row-line"><strong>{{ t.name }}</strong>\n      <span>{{ t.role or \'\' }}{% if t.subject %} · {{ t.subject }}{% endif %}</span>\n      <span class="muted">{{ t.phone or \'\' }}</span></div>\n  {% else %}<p class="muted">Staff list not published.</p>{% endfor %}\n</section>\n{% endblock %}\n',
    'teacher_dashboard.html':
        '{% extends "base.html" %}\n{% block title %}Dashboard\n{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Good day{% if current_user.full_name %}, {{ current_user.full_name.split()[0] }}{% endif %}</h1>\n    <p>{{ today_name }}{% if cls %} · class teacher of {{ cls }}{% if sec %} – {{ sec }}{% endif %}{% else %} · no class assigned yet{% endif %}</p></div>\n</header>\n\n<div class="tiles">\n  <div class="tile"><i class="bar indigo"></i><b>{{ stats.students }}</b><span>Students in my class</span></div>\n  <div class="tile"><i class="bar green"></i><b>{{ stats.attendance }}%</b><span>Attendance today</span></div>\n  <div class="tile"><i class="bar amber"></i><b>{{ absent_today|length }}</b><span>Absent today</span></div>\n  <div class="tile"><i class="bar sky"></i><b>{{ stats.homework }}</b><span>Homework posted</span></div>\n</div>\n\n<div class="two-col">\n  <section class="card">\n    <div class="card-head"><h2>Absent today</h2>\n      <a class="btn ghost small" href="{{ url_for(\'attendance\') }}">Mark attendance</a></div>\n    {% for a in absent_today %}\n      <div class="row-line"><strong>{{ a.name }}</strong>\n        <span class="muted">roll {{ a.roll_no }}</span>\n        <span class="bad-text">{{ a.status }}</span>\n        <span class="muted">{{ a.remarks or \'\' }}</span></div>\n    {% else %}<p class="muted">Nobody absent — or attendance not marked yet.</p>{% endfor %}\n  </section>\n\n  <section class="card">\n    <div class="card-head"><h2>{% if periods %}My periods today{% else %}My class{% endif %}</h2>\n      <a class="btn ghost small" href="{{ url_for(\'timetable\') }}">Timetable</a></div>\n    {% if periods %}\n      {% for p in periods %}\n        <div class="row-line"><strong>P{{ p.period }}</strong>\n          <span>{{ p.subject_name or p.subject_code or \'—\' }}</span>\n          <span class="muted">{{ p.teacher or \'\' }}</span></div>\n      {% endfor %}\n    {% else %}\n      {% for s in students %}\n        <div class="row-line"><strong>{{ s.roll_no }}</strong><span>{{ s.name }}</span>\n          <span class="muted">{{ s.phone or \'\' }}</span></div>\n      {% else %}<p class="muted">No students in your class yet.</p>{% endfor %}\n    {% endif %}\n  </section>\n</div>\n\n<div class="two-col">\n  <section class="card">\n    <div class="card-head"><h2>Homework I posted</h2>\n      <a class="btn ghost small" href="{{ url_for(\'homework\') }}">All</a></div>\n    {% for h in homework %}\n      <div class="row-line"><strong>{{ h.subject_name or \'General\' }}</strong>\n        <span>{{ h.title }}</span>\n        <span class="muted">due {{ disp_date(h.due_date) or \'—\' }}</span></div>\n    {% else %}<p class="muted">You have not posted homework yet.</p>{% endfor %}\n  </section>\n\n  <section class="card">\n    <div class="card-head"><h2>Papers coming up</h2>\n      <a class="btn ghost small" href="{{ url_for(\'schedule\') }}">Schedule</a></div>\n    {% for p in papers %}\n      <div class="row-line"><strong>{{ disp_date(p.exam_date) }}</strong>\n        <span>{{ p.subject_name or \'—\' }}</span>\n        <span class="muted">{{ p.exam_type }}{% if p.class_name %} · class {{ p.class_name }}{% endif %}</span></div>\n    {% else %}<p class="muted">No papers scheduled.</p>{% endfor %}\n  </section>\n</div>\n\n<div class="two-col">\n  <section class="card">\n    <div class="card-head"><h2>Quick actions</h2></div>\n    <div class="quick">\n      <a class="btn ghost" href="{{ url_for(\'attendance\') }}">Attendance</a>\n      <a class="btn ghost" href="{{ url_for(\'marks\') }}">Marks entry</a>\n      <a class="btn ghost" href="{{ url_for(\'results\') }}">Results</a>\n      <a class="btn ghost" href="{{ url_for(\'homework\') }}">Homework</a>\n      <a class="btn ghost" href="{{ url_for(\'circulars\') }}">Circular</a>\n    </div>\n  </section>\n\n  <section class="card">\n    <div class="card-head"><h2>Notices</h2>\n      <a class="btn ghost small" href="{{ url_for(\'circulars\') }}">All</a></div>\n    {% for n in notices %}\n      <div class="row-line"><strong>{{ n.title }}</strong>\n        <span class="muted">{{ n.posted_on[:10] }}</span></div>\n    {% else %}<p class="muted">No notices.</p>{% endfor %}\n  </section>\n</div>\n<div class="two-col">\n  <section class="card">\n    <div class="card-head"><h2>Attendance — last 7 days</h2></div>\n    <div class="days">\n      {% for t in trend %}\n        <span class="day {{ \'ok\' if t.pct >= 75 else (\'warn\' if t.pct >= 50 else \'bad\') }}"\n              title="{{ t.day }} · {{ t.pct }}%">{{ t.day }}</span>\n      {% endfor %}\n    </div>\n    <div class="charts">\n      {% for t in trend %}\n        <div class="chart">\n          <div class="chart-bar"><span style="width: {{ t.pct }}%; background: linear-gradient(90deg,#e07a2f,#1b2a5e)"></span></div>\n          <div class="chart-label">Day {{ t.day }} · {{ t.pct }}%{% if not t.marked %} (not marked){% endif %}</div>\n        </div>\n      {% endfor %}\n    </div>\n  </section>\n\n  <section class="card">\n    <div class="card-head"><h2>Top of the class</h2>\n      <a class="btn ghost small" href="{{ url_for(\'results\') }}">Results</a></div>\n    {% for r in top %}\n      <div class="row-line"><strong>{{ loop.index }}. {{ r.name }}</strong>\n        <span>{{ \'%.2f\'|format(r.percentage) }}%</span>\n        <span class="muted">{{ r.grade }} · roll {{ r.roll_no }}</span></div>\n    {% else %}<p class="muted">No result published for your class yet.</p>{% endfor %}\n    {% if overdue_books %}<p class="muted">{{ overdue_books }} library book(s) overdue in school.</p>{% endif %}\n  </section>\n</div>\n\n<section class="card">\n  <div class="card-head"><h2>Fee dues in my class</h2>\n    <a class="btn ghost small" href="{{ url_for(\'fees\') }}">Fees</a></div>\n  {% for d in class_due %}\n    <div class="row-line"><strong>{{ d.student.name }}</strong>\n      <span class="muted">roll {{ d.student.roll_no }}</span>\n      <span class="bad-text">{{ fmt_num(d.due) }}</span></div>\n  {% else %}<p class="muted">No pending dues in your class.</p>{% endfor %}\n</section>\n{% endblock %}\n',
    'settings.html':
        '{% extends "base.html" %}\n{% block title %}Settings{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>School settings</h1><p>Naam aur logo — ye report card, certificates aur receipts par aate hain</p></div>\n</header>\n\n<section class="card">\n  <h2 class="card-title">Names</h2>\n  <form class="form-grid" method="post">\n    <input type="hidden" name="action" value="name">\n    <label class="wide">School name <input name="school_name" value="{{ name }}" required></label>\n    <label class="wide">App name <input name="app_name" value="{{ app_name }}"\n           placeholder="School ERP" maxlength="30"></label>\n    <div class="form-actions"><button class="btn primary" type="submit">Save names</button></div>\n  </form>\n  <p class="muted">Current name: <strong>{{ school_name }}</strong></p>\n</section>\n\n<section class="card">\n  <h2 class="card-title">Principal\'s signature</h2>\n  {% if principal %}\n    <p><img src="{{ principal }}" alt="principal signature" style="height:70px;background:#fff;border:1px solid var(--line,#e2e8f0);border-radius:10px;padding:8px"></p>\n    <form method="post" style="margin-bottom:12px">\n      <input type="hidden" name="action" value="clear_principal">\n      <button class="btn ghost small" type="submit">Remove signature</button>\n    </form>\n  {% else %}\n    <p class="muted">No signature - the report card will show a blank space.</p>\n  {% endif %}\n  <form method="post" enctype="multipart/form-data" class="photo-form">\n    <input type="hidden" name="action" value="principal_sign">\n    <label>Upload signature <input type="file" name="signature" accept="image/*" required></label>\n    <button class="btn primary small" type="submit">Upload</button>\n  </form>\n</section>\n\n<section class="card">\n  <h2 class="card-title">School logo</h2>\n  {% if logo %}\n    <p><img src="{{ logo }}" alt="logo" style="height:80px;border:1px solid var(--line,#e2e8f0);border-radius:10px;padding:6px;background:#fff"></p>\n    <form method="post" style="margin-bottom:12px">\n      <input type="hidden" name="action" value="clear_logo">\n      <button class="btn ghost small" type="submit">Remove logo</button>\n    </form>\n  {% else %}\n    <p class="muted">No logo - the app icon is being used on the report card.</p>\n  {% endif %}\n  <form method="post" enctype="multipart/form-data" class="photo-form">\n    <input type="hidden" name="action" value="logo">\n    <label>Upload logo <input type="file" name="logo" accept="image/*" required></label>\n    <button class="btn primary small" type="submit">Upload</button>\n  </form>\n  <p class="muted">PNG or JPG under 1 MB. It appears in the report card header and as a light watermark behind it.</p>\n</section>\n{% endblock %}\n',
    'my_signature.html':
        '{% extends "base.html" %}\n{% block title %}My signature{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>My signature</h1><p>This signature appears on the report cards of your class</p></div>\n</header>\n\n<section class="card">\n  <h2 class="card-title">Class teacher\'s signature</h2>\n  {% if signature %}\n    <p><img src="{{ signature }}" alt="signature" style="height:70px;background:#fff;border:1px solid var(--line,#e2e8f0);border-radius:10px;padding:8px"></p>\n    <form method="post" style="margin-bottom:12px">\n      <input type="hidden" name="action" value="clear">\n      <button class="btn ghost small" type="submit">Remove signature</button>\n    </form>\n  {% else %}\n    <p class="muted">No signature yet - the report card will show a blank space.</p>\n  {% endif %}\n  <form method="post" enctype="multipart/form-data" class="photo-form">\n    <label>Upload signature <input type="file" name="signature" accept="image/*" required></label>\n    <button class="btn primary small" type="submit">Upload</button>\n  </form>\n</section>\n\n{% if is_admin %}\n<section class="card">\n  <h2 class="card-title">Principal\'s signature</h2>\n  {% if principal %}\n    <p><img src="{{ principal }}" alt="principal signature" style="height:70px;background:#fff;border:1px solid var(--line,#e2e8f0);border-radius:10px;padding:8px"></p>\n  {% else %}\n  {% endif %}\n  <p class="muted"><a class="btn ghost small" href="{{ url_for(\'settings\') }}">Open Settings</a></p>\n</section>\n{% endif %}\n{% endblock %}\n',
    'my_leave.html':
        '{% extends "base.html" %}\n{% block title %}Leave{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Leave application</h1><p>{{ student.name }} · Class {{ student.class_name }}{% if student.section %} – {{ student.section }}{% endif %}</p></div>\n</header>\n\n<section class="card">\n  <h2 class="card-title">Apply for leave</h2>\n  <form class="form-grid" method="post">\n    <label>From <input type="date" name="from_date" value="{{ today }}" required></label>\n    <label>To <input type="date" name="to_date" value="{{ today }}" required></label>\n    <label class="wide">Reason <input name="reason" placeholder="Fever, family function..." maxlength="200"></label>\n    <div class="form-actions"><button class="btn primary" type="submit">Send application</button></div>\n  </form>\n</section>\n\n<section class="card">\n  <h2 class="card-title">My applications</h2>\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr><th>From</th><th>To</th><th>Reason</th><th>Status</th><th>Applied on</th></tr></thead>\n      <tbody>\n      {% for r in rows %}\n        <tr>\n          <td>{{ disp_date(r.from_date) }}</td>\n          <td>{{ disp_date(r.to_date) }}</td>\n          <td>{{ r.reason or \'—\' }}</td>\n          <td>\n            {% if r.status == \'Approved\' %}<span class="pill ok">Approved</span>\n            {% elif r.status == \'Rejected\' %}<span class="pill bad">Rejected</span>\n            {% else %}<span class="pill warn">Pending</span>{% endif %}\n          </td>\n          <td>{{ r.applied_on[:10] }}</td>\n        </tr>\n      {% else %}\n        <tr><td colspan="5" class="empty">No applications yet.</td></tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n{% endblock %}\n',
    'leave.html':
        '{% extends "base.html" %}\n{% block title %}Leave{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Leave applications</h1><p>Approve or reject what your class has sent{% if scope %} · your class: {{ scope[0] }}{% if scope[1] %} – {{ scope[1] }}{% endif %}{% endif %}</p></div>\n</header>\n\n<section class="card">\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr><th>Student</th><th>Class</th><th>From</th><th>To</th>\n                 <th>Reason</th><th>Status</th><th></th></tr></thead>\n      <tbody>\n      {% for r in rows %}\n        <tr>\n          <td>{{ r.name }} <span class="muted">(roll {{ r.roll_no }})</span></td>\n          <td>{{ r.class_name }}{% if r.section %} – {{ r.section }}{% endif %}</td>\n          <td>{{ disp_date(r.from_date) }}</td>\n          <td>{{ disp_date(r.to_date) }}</td>\n          <td>{{ r.reason or \'—\' }}</td>\n          <td>\n            {% if r.status == \'Approved\' %}<span class="pill ok">Approved</span>\n            {% elif r.status == \'Rejected\' %}<span class="pill bad">Rejected</span>\n            {% else %}<span class="pill warn">Pending</span>{% endif %}\n          </td>\n          <td style="white-space:nowrap">\n            {% if r.status == \'Pending\' %}\n            <form method="post" style="display:inline">\n              <input type="hidden" name="id" value="{{ r.id }}">\n              <button class="btn primary small" name="decision" value="Approved">Approve</button>\n              <button class="btn ghost small" name="decision" value="Rejected">Reject</button>\n            </form>\n            {% endif %}\n          </td>\n        </tr>\n      {% else %}\n        <tr><td colspan="7" class="empty">No applications yet.</td></tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n{% endblock %}\n',
    'students_import.html':
        '{% extends "base.html" %}\n{% block title %}Import students{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Import students</h1><p>Add many students at once from a CSV file</p></div>\n</header>\n\n<section class="card">\n  <form method="post" enctype="multipart/form-data" class="form-grid">\n    <label class="wide">CSV file <input type="file" name="csv" accept=".csv,text/csv" required></label>\n    <div class="form-actions"><button class="btn primary" type="submit">Import</button></div>\n  </form>\n  <p class="muted">Columns (first row is the header): <code>name, class, section, roll_no, admission_no, father_name, mother_name, phone, email, gender, dob, address</code></p>\n</section>\n{% endblock %}\n',
    'personal_info.html':
        '{% extends "base.html" %}\n{% block title %}Personal info{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div>\n    <h1>Personal information</h1>\n    <p>{% if staff_view %}{{ student.name }} · Class {{ student.class_name }}{% if student.section %} – {{ student.section }}{% endif %}{% else %}Your personal details{% endif %}</p>\n  </div>\n  {% if staff_view %}\n  <div class="actions">\n    <a class="btn ghost" href="{{ url_for(\'students\', edit=student.id) }}">Edit</a>\n    <a class="btn ghost" href="{{ url_for(\'students\') }}">All students</a>\n  </div>\n  {% endif %}\n</header>\n\n<section class="card">\n  <div class="profile-top">\n    {% if student.photo %}<img class="profile-photo" src="{{ student.photo }}" alt="">\n    {% else %}<div class="profile-photo blank">{{ student.name[:1]|upper }}</div>{% endif %}\n    <div class="profile-head">\n      <h2>{{ student.name }}</h2>\n      <p>Class {{ student.class_name }}{% if student.section %} – {{ student.section }}{% endif %}\n         · Roll {{ student.roll_no }}\n         {% if student.status %}· <span class="tag ok">{{ student.status }}</span>{% endif %}</p>\n    </div>\n  </div>\n\n  <div class="info-grid">\n    <div class="info-block">\n      <h3>School record</h3>\n      <div class="kv-line"><span>Admission No</span><strong>{{ student.admission_no or \'—\' }}</strong></div>\n      <div class="kv-line"><span>Roll No</span><strong>{{ student.roll_no or \'—\' }}</strong></div>\n      <div class="kv-line"><span>Class</span><strong>{{ student.class_name or \'—\' }}{% if student.section %} – {{ student.section }}{% endif %}</strong></div>\n      <div class="kv-line"><span>Admitted on</span><strong>{{ disp_date(student.admission_date) if student.admission_date else \'—\' }}</strong></div>\n      <div class="kv-line"><span>Status</span><strong>{{ student.status or \'—\' }}</strong></div>\n    </div>\n\n    <div class="info-block">\n      <h3>Personal</h3>\n      <div class="kv-line"><span>Date of birth</span><strong>{{ disp_date(student.dob) if student.dob else \'—\' }}</strong></div>\n      <div class="kv-line"><span>Gender</span><strong>{{ student.gender or \'—\' }}</strong></div>\n      <div class="kv-line"><span>Blood group</span><strong>{{ student.blood_group or \'—\' }}</strong></div>\n      <div class="kv-line"><span>Category</span><strong>{{ student.category or \'—\' }}</strong></div>\n    </div>\n\n    <div class="info-block">\n      <h3>Parents / guardian</h3>\n      <div class="kv-line"><span>Father\'s name</span><strong>{{ student.father_name or \'—\' }}</strong></div>\n      <div class="kv-line"><span>Mother\'s name</span><strong>{{ student.mother_name or \'—\' }}</strong></div>\n      <div class="kv-line"><span>Guardian</span><strong>{{ student.guardian_name or \'—\' }}</strong></div>\n      <div class="kv-line"><span>Guardian phone</span><strong>{{ student.guardian_phone or student.phone or \'—\' }}</strong></div>\n    </div>\n\n    <div class="info-block">\n      <h3>Contact</h3>\n      <div class="kv-line"><span>Phone</span><strong>{{ student.phone or \'—\' }}</strong></div>\n      <div class="kv-line"><span>Email</span><strong>{{ student.email or \'—\' }}</strong></div>\n      <div class="kv-line"><span>Address</span><strong>{{ student.address or \'—\' }}</strong></div>\n    </div>\n  </div>\n</section>\n\n<style>\n .profile-top{display:flex;gap:16px;align-items:center;margin-bottom:18px}\n .profile-photo{width:92px;height:104px;object-fit:cover;border-radius:12px;border:1px solid var(--line,#e6e1d4)}\n .profile-photo.blank{display:grid;place-items:center;background:#f1eee6;font-size:34px;font-weight:700;color:#1b2a5e}\n .profile-head h2{margin:0;font-size:20px;color:#1b2a5e}\n .profile-head p{margin:4px 0 0;color:var(--muted,#6f6a86);font-size:13px}\n .info-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}\n .info-block{background:var(--soft,#faf8f3);border:1px solid var(--line,#e6e1d4);border-radius:14px;padding:14px 16px}\n .info-block h3{margin:0 0 10px;font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#1b2a5e}\n .kv-line{display:flex;justify-content:space-between;gap:10px;padding:6px 0;border-bottom:1px dashed rgba(27,42,94,.10);font-size:13px}\n .kv-line:last-child{border-bottom:none}\n .kv-line span{color:var(--muted,#6f6a86)}\n</style>\n{% endblock %}\n',
    'id_cards.html':
        '{% extends "base.html" %}\n{% block title %}ID cards{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>ID cards</h1><p>Print identity cards for a whole class</p></div>\n  <div class="actions">{% if rows %}<button class="btn primary" onclick="window.print()">Print</button>{% endif %}</div>\n</header>\n\n<section class="card no-print">\n  <form class="form-grid" method="get">\n    <label>Class\n      <select name="class_name" onchange="this.form.submit()">\n        <option value="">— choose —</option>\n        {% for c in classes %}<option value="{{ c }}" {{ \'selected\' if cls == c }}>{{ c }}</option>{% endfor %}\n      </select>\n    </label>\n    <label>Section <input name="section" value="{{ sec }}" placeholder="A"></label>\n    <div class="form-actions"><button class="btn primary" type="submit">Show</button></div>\n  </form>\n</section>\n\n{% if rows %}\n<div class="idgrid">\n  {% for s in rows %}\n    <div class="idcard">\n      <div class="idtop">\n        {% if logo %}<img src="{{ logo }}" alt="">{% endif %}\n        <div><strong>{{ school }}</strong><span>Student identity card</span></div>\n      </div>\n      <div class="idbody">\n        {% if s.photo %}<img class="idphoto" src="{{ s.photo }}" alt="">{% else %}<div class="idphoto blank"></div>{% endif %}\n        <div class="idinfo">\n          <b>{{ s.name }}</b>\n          <span>Class {{ s.class_name }}{% if s.section %} – {{ s.section }}{% endif %}</span>\n          <span>Roll {{ s.roll_no }}</span>\n          <span>Adm {{ s.admission_no }}</span>\n          {% if s.father_name %}<span>S/o {{ s.father_name }}</span>{% endif %}\n        </div>\n      </div>\n      <div class="idfoot">Session 2026-27 · {{ school }}</div>\n    </div>\n  {% endfor %}\n</div>\n<style>\n .idgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}\n .idcard{background:#fff;border:1px solid var(--line,#e6e1d4);border-radius:14px;overflow:hidden;\n         box-shadow:0 6px 16px rgba(27,42,94,.08)}\n .idtop{display:flex;gap:8px;align-items:center;padding:10px 12px;\n        background:linear-gradient(120deg,#1b2a5e,#2f4f8f);color:#fff}\n .idtop img{height:30px;background:#fff;border-radius:6px;padding:2px}\n .idtop strong{display:block;font-size:12px;line-height:1.2}\n .idtop span{font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;opacity:.8}\n .idbody{display:flex;gap:12px;padding:12px}\n .idphoto{width:66px;height:78px;object-fit:cover;border-radius:8px;border:1px solid #e6e1d4}\n .idphoto.blank{background:#f1eee6}\n .idinfo b{display:block;font-size:14px;margin-bottom:4px;color:#1b2a5e}\n .idinfo span{display:block;font-size:11.5px;color:#5b5a70}\n .idfoot{padding:7px 12px;font-size:9.5px;letter-spacing:.08em;text-transform:uppercase;\n         color:#8a879c;border-top:1px dashed #e6e1d4}\n @media print{\n   .sidebar,.page-head .actions,.no-print{display:none!important}\n   .shell{display:block} main{padding:0}\n   .idgrid{grid-template-columns:repeat(2,1fr)}\n   .idcard{break-inside:avoid}\n }\n</style>\n{% endif %}\n{% endblock %}\n',
    'report_card_bulk.html':
        '<!doctype html><html><head><meta charset="utf-8"><title>Report cards · {{ exam_label(exam) }}</title>\n<style>\n body{font:13px/1.5 Georgia,serif;margin:0;padding:10mm;background:#fff;color:#111}\n .rc{border:2px solid #1f3a5f;padding:16px 20px;margin-bottom:14px;break-inside:avoid}\n .top{display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #1f3a5f;padding-bottom:8px;margin-bottom:10px}\n .top img{height:44px}\n h1{font-size:18px;margin:0;color:#1f3a5f}\n .sub{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#555}\n table{width:100%;border-collapse:collapse;margin:8px 0}\n td,th{border:1px solid #cbd5e1;padding:5px 8px;font-size:12px;text-align:left}\n th{background:#eef2f8}\n .r{text-align:right}\n .tot td{font-weight:700;background:#f6f8fc}\n .meta td{border:none;padding:2px 0;font-size:12.5px}\n .foot{display:flex;justify-content:space-between;font-size:11.5px;margin-top:8px;color:#444}\n @page{size:A4;margin:8mm}\n @media print{ .rc{page-break-after:always} .rc:last-child{page-break-after:auto} }\n</style></head><body>\n{% for row in rows %}\n  {% set s = row.student %}{% set m = row.mine %}\n  <div class="rc">\n    <div class="top">\n      <div style="display:flex;gap:10px;align-items:center">\n        {% if logo %}<img src="{{ logo }}" alt="">{% endif %}\n        <div><h1>{{ school }}</h1><div class="sub">Report card · {{ exam_label(exam) }}</div></div>\n      </div>\n      <div style="text-align:right;font-size:12px">\n        <strong>{{ s.name }}</strong><br>\n        Class {{ s.class_name }}{% if s.section %} – {{ s.section }}{% endif %} · Roll {{ s.roll_no }}<br>\n        Adm {{ s.admission_no }}\n      </div>\n    </div>\n    <table>\n      <thead><tr><th>Subject</th><th class="r">Max</th><th class="r">Pass</th>\n                 <th class="r">Obtained</th><th>Result</th></tr></thead>\n      <tbody>\n      {% for sub in m.subjects %}\n        <tr><td>{{ sub.subject_name }} ({{ sub.subject_code }})</td>\n            <td class="r">{{ fmt_num(sub.max_marks) }}</td>\n            <td class="r">{{ fmt_num(sub.pass_marks) }}</td>\n            <td class="r">{{ fmt_num(sub.marks_obtained) }}</td>\n            <td>{{ \'Fail\' if (sub.marks_obtained is not none and sub.pass_marks is not none and sub.marks_obtained < sub.pass_marks) else \'Pass\' }}</td></tr>\n      {% endfor %}\n        <tr class="tot"><td>Total</td><td class="r">{{ fmt_num(m.total_max) }}</td><td></td>\n            <td class="r">{{ fmt_num(m.obtained) }}</td><td>{{ m.result }}</td></tr>\n      </tbody>\n    </table>\n    <table class="meta"><tr>\n      <td><strong>Percentage:</strong> {{ \'%.2f\'|format(m.percentage) }}%</td>\n      <td><strong>Grade:</strong> {{ m.grade }}</td>\n      <td><strong>Rank:</strong> {{ m.rank }}</td>\n      <td><strong>Failed:</strong> {{ m.failed_subjects }}</td>\n      <td><strong>Date:</strong> {{ issued_on }}</td>\n    </tr></table>\n    <div class="foot"><span>Class teacher</span><span>Principal</span><span>Parent</span></div>\n  </div>\n{% endfor %}\n<script>window.onload=function(){window.print()}</script>\n</body></html>\n',
}

STYLE_CSS = '/* Exam Manager - web edition */\n:root {\n  --bg: #f4f6fb;\n  --white: #ffffff;\n  --ink: #0f172a;\n  --muted: #64748b;\n  --line: #e2e8f0;\n  --soft: #f8fafc;\n  --accent: #4f46e5;\n  --accent-dark: #4338ca;\n  --accent-soft: #eef2ff;\n  --danger: #dc2626;\n  --danger-soft: #fee2e2;\n  --ok: #059669;\n  --ok-soft: #d1fae5;\n  --sidebar: #0f172a;\n}\n* { box-sizing: border-box; }\nbody {\n  margin: 0;\n  background: var(--bg);\n  color: var(--ink);\n  font: 15px/1.5 "Segoe UI", Inter, "Helvetica Neue", system-ui, Arial, sans-serif;\n}\na { color: var(--accent); text-decoration: none; }\na:hover { text-decoration: underline; }\nh1 { font-size: 24px; margin: 0; }\nh2 { font-size: 15px; margin: 0; }\n.muted { color: var(--muted); }\n.num { text-align: right; font-variant-numeric: tabular-nums; }\n\n/* ---------- shell ---------- */\n.shell { display: flex; min-height: 100vh; }\n.sidebar {\n  width: 244px; flex: 0 0 244px; background: var(--sidebar); color: #fff;\n  display: flex; flex-direction: column; padding: 22px 0;\n}\n.brand { display: flex; gap: 12px; align-items: center; padding: 0 20px 18px; }\n.badge {\n  width: 38px; height: 38px; border-radius: 10px; background: var(--accent);\n  display: grid; place-items: center; font-weight: 700; letter-spacing: .5px;\n}\n.brand-text strong { display: block; font-size: 15px; }\n.brand-text span { display: block; font-size: 11px; color: #7c8ba1; }\n.sidebar nav { display: flex; flex-direction: column; padding: 6px 10px; gap: 2px; }\n.sidebar nav a {\n  color: #94a3b8; padding: 10px 14px; border-radius: 8px; font-size: 14px;\n}\n.sidebar nav a:hover { background: #1e293b; color: #e2e8f0; text-decoration: none; }\n.sidebar nav a.active { background: #1e293b; color: #fff; box-shadow: inset 3px 0 0 var(--accent); }\n.sidebar-foot {\n  margin-top: auto; padding: 16px 20px 0; display: flex; flex-direction: column;\n  gap: 6px; font-size: 12px; color: #475569;\n}\n.sidebar-foot a { color: #94a3b8; }\n\nmain { flex: 1; padding: 26px 30px 40px; min-width: 0; }\n\n/* ---------- headers, cards ---------- */\n.page-head {\n  display: flex; justify-content: space-between; align-items: flex-start;\n  gap: 16px; margin-bottom: 18px; flex-wrap: wrap;\n}\n.page-head p { margin: 4px 0 0; color: var(--muted); font-size: 13px; }\n.actions { display: flex; gap: 8px; }\n.card {\n  background: var(--white); border: 1px solid var(--line); border-radius: 12px;\n  padding: 18px; margin-bottom: 16px;\n}\n.card-head {\n  display: flex; justify-content: space-between; align-items: center;\n  gap: 12px; margin-bottom: 12px; flex-wrap: wrap;\n}\n.pill {\n  background: var(--accent-soft); color: var(--accent-dark); border-radius: 999px;\n  padding: 1px 9px; font-size: 12px; font-weight: 600; margin-left: 6px;\n}\n\n/* ---------- stat tiles ---------- */\n.tiles {\n  display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));\n  gap: 14px; margin-bottom: 18px;\n}\n.tile {\n  background: var(--white); border: 1px solid var(--line); border-radius: 12px;\n  padding: 16px 18px;\n}\n.tile .bar { display: block; width: 34px; height: 3px; border-radius: 2px; margin-bottom: 10px; }\n.bar.indigo { background: var(--accent); }\n.bar.sky { background: #0ea5e9; }\n.bar.green { background: #10b981; }\n.bar.amber { background: #f59e0b; }\n.tile b { display: block; font-size: 26px; line-height: 1.1; }\n.tile span { color: var(--muted); font-size: 12px; }\n\n.two-col { display: grid; grid-template-columns: 3fr 2fr; gap: 16px; }\n@media (max-width: 1000px) { .two-col { grid-template-columns: 1fr; } }\n\n/* ---------- forms ---------- */\n.form-grid {\n  display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));\n  gap: 12px 16px; margin-top: 12px;\n}\n.form-grid label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }\n.form-grid .span-2 { grid-column: span 2; }\ninput, select {\n  font: inherit; font-size: 14px; color: var(--ink); background: var(--white);\n  border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px;\n}\ninput:focus, select:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }\n.form-actions { display: flex; align-items: end; gap: 8px; }\ndetails summary {\n  cursor: pointer; font-weight: 600; font-size: 14px; color: var(--accent-dark);\n  list-style: none;\n}\ndetails summary::-webkit-details-marker { display: none; }\ndetails summary::before { content: "+ "; font-weight: 700; }\ndetails[open] summary::before { content: "- "; font-weight: 700; }\n\n/* ---------- buttons ---------- */\n.btn {\n  display: inline-block; font: inherit; font-size: 14px; cursor: pointer;\n  border-radius: 8px; padding: 8px 14px; border: 1px solid var(--line);\n  background: var(--white); color: var(--ink); text-decoration: none;\n}\n.btn:hover { background: var(--soft); text-decoration: none; }\n.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }\n.btn.primary:hover { background: var(--accent-dark); }\n.btn.ghost { background: var(--white); }\n.btn.danger { color: var(--danger); border-color: #fecaca; }\n.btn.danger:hover { background: var(--danger-soft); }\n.btn.small { padding: 4px 9px; font-size: 12px; }\n\n/* ---------- tables ---------- */\n.table-wrap { overflow-x: auto; }\ntable.grid { width: 100%; border-collapse: collapse; font-size: 14px; }\ntable.grid th {\n  text-align: left; font-size: 11px; letter-spacing: .04em; text-transform: uppercase;\n  color: var(--muted); background: var(--soft); padding: 9px 10px;\n  border-bottom: 1px solid var(--line); white-space: nowrap;\n}\ntable.grid td { padding: 9px 10px; border-bottom: 1px solid var(--line); vertical-align: middle; }\ntable.grid tbody tr:nth-child(even) { background: #fcfdff; }\ntable.grid tbody tr:hover { background: var(--accent-soft); }\ntable.grid td.empty { text-align: center; color: var(--muted); padding: 26px; }\n.row-actions { display: flex; gap: 6px; justify-content: flex-end; }\n.row-actions form { display: inline; }\n.mark-input { width: 96px; }\n\n/* ---------- bits ---------- */\n.tag { display: inline-block; border-radius: 999px; padding: 2px 9px; font-size: 12px; font-weight: 600; }\n.tag.ok { background: var(--ok-soft); color: var(--ok); }\n.tag.bad { background: var(--danger-soft); color: var(--danger); }\n.flash {\n  border-radius: 10px; padding: 11px 14px; margin-bottom: 14px; font-size: 14px;\n  border: 1px solid var(--line); background: var(--white);\n}\n.flash.ok { background: var(--ok-soft); border-color: #a7f3d0; color: #065f46; }\n.flash.error { background: var(--danger-soft); border-color: #fecaca; color: #991b1b; }\n.banner {\n  background: #fff7ed; border: 1px solid #fed7aa; color: #9a3412;\n  border-radius: 10px; padding: 11px 14px; margin-bottom: 14px; font-size: 13px;\n}\n.info { color: var(--muted); font-size: 13px; margin: 0 0 12px 2px; }\n.search { display: flex; gap: 8px; align-items: center; }\n.search input { min-width: 260px; }\n.login-wrap { display: grid; place-items: center; min-height: 70vh; }\n.card.login { width: 340px; display: flex; flex-direction: column; gap: 12px; }\n.card.login h1 { font-size: 22px; }\n.card.login label { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--muted); }\n\n/* ---------- small screens ---------- */\n@media (max-width: 820px) {\n  .shell { flex-direction: column; }\n  .sidebar { width: 100%; flex: none; padding: 14px 0; }\n  .sidebar nav { flex-direction: row; overflow-x: auto; gap: 6px; }\n  .sidebar nav a { white-space: nowrap; }\n  .sidebar-foot { flex-direction: row; gap: 14px; padding: 10px 20px 0; }\n  main { padding: 18px 14px 30px; }\n  .form-grid { grid-template-columns: 1fr; }\n  .form-grid .span-2 { grid-column: auto; }\n}\n\n/* ---------- multi-user bits ---------- */\n.banner.admin { background: #eef2ff; border-color: #c7d2fe; color: #3730a3; }\n.tag.admin { background: #eef2ff; color: #4338ca; }\n.sidebar-foot .who {\n  color: #cbd5e1; font-size: 12px; display: flex; gap: 6px; align-items: center;\n  flex-wrap: wrap;\n}\n.sidebar-foot .who em {\n  font-style: normal; background: #1e293b; color: #a5b4fc; border-radius: 999px;\n  padding: 0 7px; font-size: 10px; text-transform: uppercase; letter-spacing: .04em;\n}\n.small { font-size: 12px; }\n.card.login .small { margin: 4px 0 0; }\n\n/* ---------- public landing page ---------- */\n.landing-body { background: #ffffff; }\n.landing-wrap { max-width: 1060px; margin: 0 auto; padding: 0 22px; }\n.landing-nav {\n  position: sticky; top: 0; z-index: 5; background: rgba(255,255,255,.92);\n  backdrop-filter: blur(6px); border-bottom: 1px solid var(--line);\n}\n.nav-inner { display: flex; align-items: center; justify-content: space-between; height: 64px; }\n.brand-inline { display: flex; align-items: center; gap: 10px; font-size: 15px; }\n.brand-inline .badge { width: 32px; height: 32px; font-size: 12px; }\n.landing-nav nav { display: flex; align-items: center; gap: 18px; }\n.landing-nav nav a { color: var(--muted); font-size: 14px; }\n.landing-nav nav a.btn { color: var(--ink); }\n.landing-nav nav a.btn.primary { color: #fff; }\n\n.hero { padding: 74px 0 56px; background:\n  radial-gradient(1000px 380px at 15% -10%, #eef2ff 0%, rgba(255,255,255,0) 70%); }\n.hero .eyebrow {\n  text-transform: uppercase; letter-spacing: .12em; font-size: 11px;\n  color: var(--accent); font-weight: 700; margin: 0 0 12px;\n}\n.hero h1 { font-size: 46px; line-height: 1.05; margin: 0 0 14px; letter-spacing: -.02em; }\n.hero .lead { font-size: 17px; color: var(--muted); max-width: 640px; margin: 0 0 26px; }\n.hero-actions { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 14px; }\n.hero .tiny { font-size: 12px; margin: 0; }\n\n.landing-section { padding: 54px 0; border-top: 1px solid var(--line); }\n.landing-section.alt { background: var(--soft); }\n.landing-section h2, .landing-cta h2 { font-size: 26px; margin: 0 0 22px; }\n.feature-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }\n.feature { background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 18px; }\n.feature h3 { font-size: 15px; margin: 0 0 6px; }\n.feature p { margin: 0; color: var(--muted); font-size: 14px; }\n.steps { margin: 0 0 16px; padding-left: 20px; color: var(--ink); }\n.steps li { margin: 8px 0; }\n.landing-cta { padding: 56px 0; text-align: center; border-top: 1px solid var(--line); }\n.landing-cta p { color: var(--muted); margin: 0 0 18px; }\n.landing-foot { border-top: 1px solid var(--line); padding: 22px 0; }\n.landing-foot .landing-wrap { display: flex; justify-content: space-between; gap: 14px;\n  flex-wrap: wrap; font-size: 12px; color: var(--muted); }\n@media (max-width: 720px) {\n  .hero h1 { font-size: 34px; }\n  .landing-nav nav a:not(.btn) { display: none; }\n}\n\n/* ---------- student result page ---------- */\n.kv { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 14px; }\n.kv div { display: flex; flex-direction: column; gap: 2px; }\n.kv span { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }\n.kv strong { font-size: 15px; }\n.card-title { font-size: 14px; margin: 0 0 12px; }\n.pill { display: inline-block; padding: 1px 9px; border-radius: 999px; font-size: 12px; font-weight: 600; }\n.pill.ok { background: var(--ok-soft); color: var(--ok); }\n.pill.bad { background: var(--danger-soft); color: var(--danger); }\n.btn.small { padding: 4px 10px; font-size: 12px; }\n\n.pill.warn { background: var(--warn-soft, #fef3c7); color: var(--warn, #b45309); }\n.form-grid .wide { grid-column: 1 / -1; }\n.form-grid .check { flex-direction: row; align-items: center; gap: 8px; }\n.form-grid textarea { font-family: inherit; font-size: 14px; }\n\n.avatar { width: 26px; height: 26px; border-radius: 50%; object-fit: cover;\n          vertical-align: middle; border: 1px solid var(--line, #e2e8f0); }\n.photo-form { display: flex; gap: 10px; align-items: center; margin-top: 10px; }\n.charts { display: grid; gap: 14px; }\n.chart-bar { background: #eef2f8; border-radius: 999px; height: 10px; overflow: hidden; }\n.chart-bar span { display: block; height: 100%; border-radius: 999px; }\n.chart-label { font-size: 12px; color: var(--muted); margin-top: 4px; }\n\n.days { display: flex; gap: 6px; flex-wrap: wrap; margin: 6px 0 10px; }\n.day { width: 30px; height: 30px; border-radius: 8px; display: grid; place-items: center;\n       font-size: 11px; font-weight: 600; }\n.day.ok { background: #dcfce7; color: #166534; }\n.day.bad { background: #fee2e2; color: #991b1b; }\n.row-line { display: flex; gap: 10px; align-items: baseline; padding: 6px 0;\n            border-bottom: 1px solid var(--line, #eef2f8); font-size: 14px; }\n.row-line:last-child { border-bottom: none; }\n.poll { padding: 12px 0; border-bottom: 1px solid var(--line, #eef2f8); }\n.poll:last-child { border-bottom: none; }\n.poll-form { display: flex; flex-direction: column; gap: 6px; align-items: flex-start; }\n.poll-option { display: flex; gap: 8px; align-items: center; font-size: 14px; }\n\n.ok-text { color: #166534; font-weight: 600; }\n.bad-text { color: #991b1b; font-weight: 600; }\n.mini-list { margin-top: 8px; }\n\n.quick { display: flex; gap: 8px; flex-wrap: wrap; }\n\n.day.warn { background: #fef3c7; color: #b45309; }\n\n.badge-logo { width: 40px; height: 40px; object-fit: contain; background: #fff;\n              border-radius: 10px; padding: 4px; }\n.login-logo { width: 76px; height: 76px; object-fit: contain; margin: 0 auto 10px;\n              display: block; }\n\n/* ==================================================================\n   ROYAL JHAROKHA — Indian traditional theme (indigo · saffron · gold)\n   Sirf rang aur shape badalte hain, layout waisa hi rehta hai.\n   ================================================================== */\n:root{\n  --bg:#f4f1ea;\n  --white:#ffffff;\n  --ink:#22203a;\n  --muted:#6f6a86;\n  --line:#e6e1d4;\n  --soft:#faf8f3;\n  --accent:#e07a2f;\n  --accent-dark:#c96a24;\n  --accent-soft:#fde7d3;\n  --danger:#b3261e;\n  --danger-soft:#fbe3e1;\n  --ok:#1f7a4d;\n  --ok-soft:#dff3e7;\n  --sidebar:#1b2a5e;\n}\n\nbody{ font-family:"Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif; }\n\n/* ---------- sidebar ---------- */\n.sidebar{\n  background:linear-gradient(180deg,#1b2a5e 0%,#16224e 100%);\n  position:relative; overflow:hidden;\n}\n.sidebar::before{\n  content:""; position:absolute; inset:0; pointer-events:none;\n  background:repeating-linear-gradient(45deg, rgba(255,255,255,.055) 0 2px, transparent 2px 12px);\n}\n.sidebar > *{ position:relative; }\n.sidebar nav a{ border-radius:14px; }\n.sidebar nav a:hover{ background:rgba(255,255,255,.10); color:#fff; }\n.sidebar nav a.active{\n  background:#e07a2f; color:#fff; box-shadow:none; font-weight:600;\n}\n.badge, .badge-logo{ border-radius:50% 50% 12px 12px; }\n.badge{ background:#e07a2f; color:#1b2a5e; }\n.badge-logo{ background:#fff; border:2px solid rgba(246,199,137,.9); }\n.sidebar-foot{ border-top:1px solid rgba(255,255,255,.12); }\n.sidebar-foot a{ color:#c9d2ee; }\n\n/* ---------- headings & rules ---------- */\nh1, .page-head h1, .card-title{ color:#1b2a5e; letter-spacing:.01em; }\n.page-head{\n  border-bottom:none; padding-bottom:12px; margin-bottom:16px; position:relative;\n}\n.page-head::after{\n  content:""; display:block; height:5px; border-radius:99px; margin-top:12px;\n  background:linear-gradient(90deg,#1b2a5e,#e07a2f 50%,#1b2a5e);\n}\n\n/* ---------- cards & tiles ---------- */\n.card, .tile{\n  border-radius:18px; border:1px solid var(--line);\n  box-shadow:0 8px 20px rgba(27,42,94,.07);\n}\n.tile{ position:relative; overflow:hidden; }\n.tile::before{\n  content:""; position:absolute; top:0; left:0; right:0; height:4px;\n  background:linear-gradient(90deg,#e07a2f,#1b2a5e);\n}\n.tile .bar{ background:linear-gradient(90deg,#e07a2f,#1b2a5e); }\n.tile b{ color:#1b2a5e; }\n\n/* ---------- buttons, pills, tables ---------- */\n.btn{ border-radius:12px; }\n.btn.primary{\n  background:linear-gradient(135deg,#e07a2f,#c96a24); border-color:#c96a24; color:#fff;\n}\n.btn.primary:hover{ background:linear-gradient(135deg,#c96a24,#b25c1d); }\n.tag, .pill{ border-radius:99px; }\nthead th{ color:#6f6a86; border-bottom:2px solid var(--line); }\ntbody tr:nth-child(even){ background:rgba(27,42,94,.02); }\n\n/* ---------- inputs ---------- */\ninput, select, textarea{ border-radius:12px; border-color:#e0dacb; }\ninput:focus, select:focus, textarea:focus{\n  border-color:#e07a2f; box-shadow:0 0 0 3px rgba(224,122,47,.16); outline:none;\n}\n'

ICON_PNG_B64 = ('iVBORw0KGgoAAAANSUhEUgAAAQAAAAEACAYAAABccqhmAAAHdUlEQVR4nO3dvY5lRxmF4RrkIbdEBCkESNwBkZMJbEsEyAkSIfdA5MAJJL4FIgsRGgkCJoCIq3AMFiDZGUl7aKKWWz3dffY++6e+qvU8oT14qo3Xu+uc/pnWAAAAAACAOb3ofYAz/OzVP257n4Ex/fH1D6beyFQfnKFzllnCMPwHYfT0NnIMhjy40VPVaDEY5rBGz2hGiEH5Axo+o6scgrIHM3xmUzEE5Q5k+MyuUgjKHMTwSVMhBN/pfYDWjJ9MFf6771qgCv8CoIJet4FuNwDjh2/12kOXABg/vK3HLk69dhg+LHPWS4LTbgDGD8udtZdTAmD8sN4Zuzk8AMYP1zt6P4cGwPhhuyN3dFgAjB/2c9SeDgmA8cP+jtjV7gEwfjjO3vvaNQDGD8fbc2clvhkI6GO3AHj6w3n22tsuATB+ON8eu9scAOOHfrbuz3sAEGxTADz9ob8tO7w6AMYPdVy7Ry8BINhVAfD0h3qu2aUbAARbHQBPf6hr7T7dACDYqgB4+kN9a3bqBgDBFgfA0x/GsXSvbgAQTAAg2KIAuP7DeJbs1g0AggkABLsYANd/GNel/boBQDABgGDPBsD1H8b33I7dACCYAEAwAYBgAgDBBACCPRkAnwGAeTy1ZzcACCYAEEwAIJgAQDABgGACAMEEAIIJAAQTAAj2Tu8DpPjxT77bfvPp93ofYxj/+feb9qtf/qv3MabnBgDBBACCCQAEEwAIJgAQTAAgmABAMAGAYAIAwQQAggkABBMACCYAEEwAIJgAQDABgGACAMEEAIIJAAQTAAjmh4JO6ubmtn304Ze9j0FxbgAQTAAgmABAMAGAYAIAwQQAggkABBMACCYAEEwAIJgAQDABgGACAMEEAIIJAAQTAAgmABBMACCYAEAwAYBgfijopF6+fNE+/8v3ex9jtZ+//8/25k3vU+RwA4BgAgDBBACCCQAEEwAIJgAQTAAgmABAMAGAYAIAwQQAggkABBMACCYAEEwAIJgAQDABgGACAMEEAIIJAATzQ0EndXNz2z768Mvex6A4NwAIJgAQTAAgmABAMAGAYAIAwQQAgj35dQDf3Pz3zHNM7803/zv99/T/IZe4AUAwAYBgAgDBBACCCQAEEwAIJgAQTAAgmABAMAGAYAIAwQQAggkABBMACCYAEEwAIJg/GGRSL1++aH/66w97H2Ozz373VfvDZ1/1Psa03AAgmABAMAGAYAIAwQQAggkABBMACCYAEEwAIJgAQDABgGACAMEEAIIJAAQTAAgmABDMDwSBe/7+698v/rU//e0vDjzJOQSAaGsGf+l/O2IQBIBIW4Z/6Z85UggEgChHDP+p32OEELx46m988N4Xt2ceBI50xvCfUiUEf/7bj97au88CML2e46/w+z/HSwCmVWl4VV8WuAEwpUrjv6/auQSA6VQb2UOVzicATKXSuJ5T5ZwCwDSqjGqpCucVAKZQYUzX6H1uAYBgAsDwej9Fn/P1q48v/pqe5xcAhjbC+CtHQADgAA9HvyQCPQgAw6r69H9q7Jci0OPjEQA40devPi51GxAAhjTa03/przv74xIA2MnaJ3uFm4AAMJyKT/9rxvzu608e/etnfnwCABvtOf6zCQBsMPL4WxMAiCYADKXS6/8jn/5nfZwCQJS93nkf/ep/RwCIseZr85f8c9aoOP7WBIAQe31t/kzjb+2ZADz2M8RhRNd+bf7WX99anfE/tWc3AKZ2abRbv3R3dALAtHqPu8rT/zkCwJT2vN6PfPW/RACYzp5v8M08/tYEgAltGeD9wc8+/tYuBMBnAhjV1gjMNP7nduwGwFDW/OGaZw5y79/rrD9EVACYWtWnchUXA+BlAKM7OgKVI3Npv24ARDhqpJXHv4QAMJxrXx/vPdajxn/W6//WFgbAywBmsddoR3jyL9mtGwBD2vKU3DreI8d/5tO/NQEg1AhP8DMsDoCXAVSz9Wl5TQRGefov3asbANHWDHrGW8OqALgFUM0eT80lwz56/D2e/q25ATCBPSPwcOjvvv5kqPGvddUT/YP3vrjd+yCwRaUfF75Wr6d/a24ATKLnU3SL3ue+KgDeC6Ci3mNaa+/zXrNLNwCmMkoEqpzz6gC4BVBVlXE95YjzXbvHTTcAEaCqqhGoNP7WWntnz4NAJXdjq/AZgqpB2vwegFsA1fUe35G//9b97TZeXxvACM68DRwdnj0evrs+vUWAURwZgjNuHHvdvL0HQKQj3h/o/VLjGru/fncLYGRrgtBr8Hu+73bIG3giAMfY+033Q74S0GcGYH9H7OqwLwUWAdjPUXs69HsBRAC2O3JHh38zkAjA9Y7ezynfDSgCsN4Zuznt24FFAJY7ay9dRunThPC4sx+UXX4giNsAvK3HLrr9RCARgG/12kOJEXpJQKreD8ISPxOw978E6KHCf/fdD/CQ2wCzqzD8O2UO8pAQMJtKw79T7kAPCQGjqzj8O2UP9pAQMJrKw79T/oCPEQOqGmH09w112MeIAb2NNvr7hj34Y8SAs4w8+vum+CAuEQauNcvQAQAAAIBQ/wc5QDYHbNuaaAAAAABJRU5ErkJggg==')

LOGO_PNG_B64 = ('iVBORw0KGgoAAAANSUhEUgAAAmwAAAMMCAYAAADuFvvLAAEAAElEQVR4nOydd9zcxJ3/PyPtU/y4GxfABkyx6T3F1AAJBEIICSkXklzqXa4m1/PLpZF+yfWWSwdSSU9ID6RAAslDGh0bDNgUY4O7/fTd1fz+UJdmpJnRqOw+8/Fr/Wg1dbVa7Xs/35kRoZTCyMjIyMjIyMioubLq7oCRkZGRkZGRkVG2DLAZGRkZGRkZGTVcBtiMjIyMjIyMjBouA2xGRkZGRkZGRg2XATYjIyMjIyMjo4bLAJuRkZGRkZGRUcNlgM3IyMjIyMjIqOEywGZkZGRkZGRk1HAZYDMyMjIyMjIyargMsBkZGRkZGRkZNVwG2IyMjIyMjIyMGi4DbEZGRkZGRkZGDZcBNiMjIyMjIyOjhqtVdweMjIyMolp//ZW07j74Ovby60jdfTAyMjICAEJpY66NRkZGfagmAVjZMoBnZGRUlgywGRkZKWs2wZguGagzMjJSkQE2IyOjTBkoq04G5oyMjHgywGZkZATAgFmTZUDOyMjIAJuR0SyUgbPel4E4I6PZJQNsRkZ9LgNns0cG4oyM+lcG2IyM+kgGzoySMhBnZNQfMsBmZNTDMoBmJCsDcEZGvSkDbEZGPSQDaEa6ZQDOyKg3ZIDNyKjBMoBmVLUMwBkZNVMG2IyMGiYDaUZNkYE3I6PmyACbkVHNMoCW1sX/tyqxJ+cQ0dRGRlYqkJXiR3+5Lbeu2SYDcEZG9ckAm5FRDZpNkHbJRw8RyBU/HOzLkmZoy83GyJDaFd/xozc9mdt2v8jAm5FRtTLAZmRUkfoV0i752KEZqSJg5OUTKpZRGeU+4WRVgDYBkEx3I9xzw5ufymuwJ2XgzciofBlgMzIqUf0Cac/7+GExEqGR//NVB7TpC43m78oAtmBHXn8obnjz9pw8vSEDb0ZG5cgAm5GRZvUypD3v46sh6mJVAW38y1MPQZsQsEXyJLLe8Fe9C3IG3oyM9MkAm5GRBvUipLlwxpPYeLG+gbbCodF0BfLQlqJhRg434ca/2pFTV/Nk4M3IqJgMsBkZKaqXIO15nzjc28qHAuEMfQJtYuPZqguN8przE3jN3vjXvQNxBt6MjORlgM3ISFK9AGohoLEkMpBeKLEB0DZ7QqNhal4/PBfur3cKtFWvDLgZGYnLAJuRkYCaDGmXfuII5Ibk8lKLuG39BG1NCo3KuGzshlJqMsQZeDMyypYBNiOjDDUV1C795BHpnQwYEMEU8cyaoU342hPvI7tUj4RGK3bZ+NVT3Pg3uwT6Ub0MuBkZsWWAzcgooSZCGhPQWOIAgbDb1hBo2/zDf14nVkF5OvTCvx1lp4i4k0WhLT9EqwPaomoiwBl4MzIKZYDNyMhTk0Dt0k8eGXmm0C3G57pOaNv8gw/XDmBl69Dn/E0E8HKcTg3QphvYkiV+3CCAM+BmZGSAzcioMaB26ac8SMsYuyQl6RCpzLi2eOKm739IK5CtvvgtDHermvFsPmw+esO/a31Nhzznr8PX1FCXjYdwP/6b3dn1VCQDbkazWQbYjGalGgdpLOkAN43Qtun7/6QMMKsv+X+c8GK0LYmxXZlFdEBbPiwlEx+98T+Uj88hz/6r7PBrTS4by3n98d8aeDMyqkMG2IxmlZoAas//1FGRr8G8L1TpBE528RDppu99kAseY/9z/Oi8N92bSj/8eW9NA4f0mLa8Af+JijOLcAknOz2WVaQ/ea5kuOPRH/9n7LjxjmVULshl96Mql41VTRPgzYCb0WyRATajWaG6Qe35nzqKub9ScGO4bQ9nwBngQkVy34k/eIF4H0qBtmpDozIuGzsvG4jWX35jKmcewAHAIRe8Ofae1OGysXL/+G/3ZLdTsgy4GfW7DLAZ9bXqBDUepLFUDNzEXuLD3/1ALgywAC2pNLBl9CH1XS/Q1x4PjWa5bNFnLGBLSgTgAGDVBW/iOpycTiWS1F021s464c2Am1G/ygCbUV+qLlB7/qfXeFt5rkRauqFNBNCOuPRto9HSd198fV4RAEWgTfRglAxtWkOjeQ5Xesd9ArAGAMd+6znx8hR47Kf/nfu+rrrgTaOlhEW5VfGPwY//bk922yXJgJtRv8kAm1FfqQ5QCyGNpZLAjZH08Hffn/lFfsTz3545S5GiKLBxOhbZLR4ahTS0NTs0WhTYInUw+pEHcavOf9NoMZdNAdhiu11U/8nf7c3qZiky4GbULzLAZtQXah6oJaUf3B7+jgSgcRtRgzY+sPm18HeLQ1seJKXrKTU0KtmXLGgTAbY4rEXKcw9vmPD4T/8nB+D+khFCLc9lS3qrBtyMjORlgM2op1U1qMlBGkty4BaFtnxAewd34dbsRuJ57xIBth++IKOJfEAShraGhEZ1u2xqwBapQwDaovke/5kAwGmafMDbzQuHVw1vBtyMelUG2Ix6UtWD2trIMx1Ni4HbQ995H/eL9ojL3hF3SXLCcNndCfMKA1tmEzVCG5OrNLlsudnEoK0yYEvldZ88/rP/5Z5Xq877i9F4btH2xcKiPBlwMzLKlgE2o55S5aB29dr4DsaXXzGlwS0b0t4pMBZJaCcjm5tPCtgyq68S2poSGi0b2Lw6Mo55NrenC+bBW2GXLVYk6+C5r+snf78vI49+GXAz6hUZYDPqCVUJailIY6mIm8Wo7KFvsyHtyMvemVhzS6C9gtAmAmyAiMuWkSgLbLmglK6nnNBocZftvstvyGzDVyawZfSh6LpsPIBbed5fxH8slOCyJd+0KuHNgJtR02WAzajRqhLULouAmlSjiq7bQ99+LxvSXvDO0bxqcsGtALTd9dxvCeUTc9kyEksOjTbVZSsb2FRctnjeMP3xmz7Cgbc/H+VXlQWMeQu7sI+tATcjIwNsRg1VXaDGknBHBL4U+ZD2rvSEgYZD24k/vDxeXyOgrQqXzftfEdpEgI0Pa4kKy3DZaDqdAtjCg7dn/Xlixmnee50fFuXJgJvRbJYBNqPGqQpYu+zqozNS+c0LdSzxxSgGaRmVCEU/ZUKk+a9CHNgS9WW4PlxJQZtkaJSbXUNotF+BDUiRbjJ3NrzpDYtyKsFP/n5/Vi1aZKDNqEkywGbUGNUPaixJfd0Heuj69yhAWkZLQm6bPmiTA7ZEfbLQ1sjQaHkumxiwXZjbB2lokzkHJJb42HLT/3Hg7c84s5jVwqLMnlDgJ/9gwM1odsgAm1HtqgTUromAmnJr+fDGArUjX3CV2vpoyTLaQ6T8CuWBLVFf7dBWRWi0x4AtlbeIy8Z+r7fcnIa3GLhpCIuyjisF8FMDbkZ9LgNsRrWpclDjSboX8QIPsiDt8qvSTpogCOS2KWSkFYM28YkHHGiT+cJlFhWAldzDGD9meZ4RO4mfR8Vlu+8FghMOrr9QyOkr5rIVAbb8tpnwdq4Pb3rCov7T6B4Dbkb9KgNsRrWobFgTAjWeBHv24PXvTn0hHXX5VaPiHFGO21YltKm5bJzEWNH+dNlEgO3Y6y+MFK3RZdN054MtN3+UCW7aXLZUVvfZT/9hLKuCwjLQZlS1DLAZVaryQe2YjFSFphNF2JD2buZAa/Hvcdl+VQNtasCWqIvbRx0uG+SgrQEumxSwBUXV3cayJx9kn4vpnSx4O/jcP2WM65QDYR60AQbcjPpHBtiMKlG9oMaTeJce/BYP1PLrFPveaR60qQNboq5SoY3iB3/6WE6eUBf/3yrpfuh02UoDtoxslYRFuVWxgXHLzwXArUBYlNWuATejXpcBNqPSVSasqYEaT/FuMiHthe/OXdSWVVep0JZRtAi0iQDbST+8PNd/knJKUkXT6T/400dz+yUqF+Cqc9lEgO246y9kMJUAvJThsjHa5j6TALZo3574+cc48CbhsgkAm7/7p28pD9wMtBmVKQNsRqWpma5avh781lVsUEuqEeBWHrSJTjzgQ5s+l00npPF08f+t5PZDh8smOuFAHtgi6XW6bKLAFisSpjPB7Zw/kVqrsAnQBhhwMypHBtiMSlHvuGqh2KD2nuybrQMCfJUZSOIkKLptGqFNBtj4NatD2/f/5BGh9p/+t08J5QOA3/z7cqF8MXjT5LLd94IfCbVdCbCl8ma5bHnnbxGXLd0zcXBLQ6gosPlpP33LODuPBhloM9ItA2xGWlUqqF0bATWNrSRBzYU0lvSCW2luW8XQlg1siRRBaMuCNRlAy1MWwAXQpsllEwG24yLj15SgrQxgA3JctiLAxumbpyS8pcEt3rY4sMXTDbgZ9YIMsBlpU1mwdtm1xwrkEoWQUOKgJlmxLnCrGtoKAltGs7n98hN4oKYT0njiwdvF/7dSi8tWCbBlZOuFsCgzEwWe+MXHOeCmAGxBUjq9LHAz0GakQwbYjAqrXlATUfyiXgzUMuqWSOoVaLvrud/Mbe2kxExRdrP5Ltv3/2Rzah8P1H7z78szIS4rXaRsUhd/xA+RqrtsssCWai0X2iSBjd0ApzAX0dLPpF028UV00+D2xtTtr8RdNn6rBtyMmqhW3R0w6m2VBWsvuPZYFLmyxTvl1vTgN98VB7UXvUdwxmeW/F4yKiLs3axEbtYgIbMydiFOkXA3I4NMM0EZEvtSZVcR2ZvIIANqVchvOwpuP/yLLQB8cMs5QCrHUItE33eVquPvcaWKdNx31nxwe+IXn1jn7n+jwo8u/hG54J/nlgJt66+/khpoM1KVcdiMlFQmqOnWxhSovZc9DqbwK6rCbavWaRNx2ADgpB++MK9GZp+KwJqqi5bnsCXzJnXxRw7OLMNy2cQnHFwE7nGc5WFRllKO29lvHM3rZXx3drsUwM/eMpGRR10G3IxkZRw2I2mVAWtVgNoaD9TSnhiJ/CkCbzluG7deGbetDKctt0uCTWV6d6n833/j5tguFkTJwJWIZEOpbLftiVxo06XYcZR+/5UaUCuam5Bdt2qq67jRwGl74hb370Fn+45bEbuRgIDi/A+PAAB+9v/0gptx24xkZdXdAaPe0frrr6S9AGsbv/mudVFYW/Oi946uSblq7jXbf6T2EsJKFFRGQW596V7ws8l0jMT+sFP5iSf96EWC7aSrYdfq7hWBNX+/6FIcRZUFc8n9P/yLJzJqIkrnjeuuFZXI+61adXPZ4uBz3jgaDYtuveUT67Z68KZLPrjpVFnXVKP+lHHYjITUK6AWfc6CNJ6iX0Vp503VdZP9dR+34fSNaxNx2nQ5N/n1iMJa05SER57TVvxIZjiuhSsvc4BdkbpzygrawQef88ZR0NBp2xo4bn/MuRbI9dm4bUZ1yjhsRrmqB9aIwMOVqKMmqnQLvusW2ylZm9juMDG5xcui8xrP6ad0Ffz+f/+Nm2LPRWCN57LpdN9EQ6/iTpuayyYmzRUT7pPyVVJzB539xtEwLApsveWT67be8kk1x43Rx7LcNu2VGvWVDLAZcVWGXf+Ca4/1YE0MxrJFEAe1942uedH7Rje++X6JOvJa0Alu4rsZrWZkEemMaKhM7bjF1mvjVKECazqlazycCLRFD4HohAN9KjEsKhW6l2u5SGoy69b3uTM8WeAmVyXhZjv/wyM4/8NzxPslIBMiNcqSATYjpvSD2nF4wbXHQYh2BMy1jd9857qN33xnDNYAYOObNyD8qwqC/C7FnklXmeG2cfPnZCsF2nQoGwGT0JPnlJU5lk1lXTZh8FM+qBnvPUmnF6m7qqKFJdj2E+91Yc2HNiAeEi3ktjF0/ofnlAJuWis06gsZYDNKqQxYS0nRXNv4jXeu2/iNCKhd8b7RNVe8b3TjmzcEsJatYvCmD9wyK+bmVTAu2JkzoS2eeNINL5JpIFJRWE/UXWPBjiqQlT0pQXQiAjs0Kv7GHPdtHRMOCkhbWFShrNSPDrl2t75vPOK2/fFoCtxu/eQ6XRRqoM2obJlJB0aBSgM1DdfDKKQBLqgFaW9ig9rGN2/Amv9J3Cg+9goJLyFXfkkafUb460WxaxCdkBDfyc/CqZPXSGZ20brym/leIhTKkw9feTNGq1rmQ7at5CQE6SOYKlDkPch+jzW8u/l1CZzLuvvlu2tJbX3fBA56pzvuzIc232VzoQ046Kw/4o97FXyR5394DkCBn711UqX7KfnXZDMhwQgwDpuRJ+2w9pnjikYhA7EcNcAFNR6sccU12NSct5TjJlWFTIhU1GkTbZyfLzuYKat4HXkAVJZjJgtfqpMQ0tL3PducsGhd7FCs3a3vm8DW94WzO1OO262f0hcm/ZBx24z0ywCbUTmwpkGs8Gc0PeWeserIArpceBMXM0yqUDprl35o42fV9ZX8vTc+HGyLAlMWtFUxM1QW7rJCo9LHsTFjxGqCwbyyGck8dy0q32WL7TsrDm1pcONPPMiSgTYj3TLANoule0bSCz5znFZY87ejrlppYsKbHLgVd9vyd+lw0FJ5JMazZSk2UxTA9/74YXZGAclAmwrEFYW1rPai0HbvZT+U6ldaGuCnF4JpNffxoLP+eDQaEtXltp3/oTk4/0PDOqoCYGaRznYZYJulao6rRmKPqKu25or3j6654v2jyTzRx5r/yV98Vzlsyt+RWzxWrkRoy04uDm3i9WQrCkGicFXlXQ4AMVj7zb8vZ+araokSnWFRNd+I2RN+TQo/OlR69cR7x3LzsNy1VJ6z/igAN7bbxhLJfApAK7QBxm2brTLANgtVn6vGgi5XG7/xjnUbv/GOiKv2fq2OmjS0AYXAjem2CZfM31UKtGWkKM0U5cgHMREY07FobhKwWMAlsrSHn0c3nB337efGdxhHTKphEVjjleXtTrptW2/99Lqir/n8Dw1rd9u0VWbUEzLANsukG9byxR0oFigJarKwJuKyxfsiqYLgFmzVBm3qzYa75SqLhkN5y3iIgpsInBVx40RvCC8yYcJX9r1GZVXheLIeH8fG00HvnCtfJuK2AcC2Wz+tKUxqoM1ITQbYZonKGK/GVz6kAeW7aqn23rTe2xLrX0pMcBMrFmwRUXDTCW26QqP6JQpuLCDTMXYtb1kP3cuI6JDSWyRuLimrcF0KFYi7a+qKQdsvP71u2y9lwS39ws4z49qMFGTWYZsFqgbU5K62XFBTuepT12ULgUxG0QYFDxOJZvXLZ5eNFQGB2Jpt8VK8XdGdzOScFJE8ZXOcD0U+gGUtrlsFQFUPaiLvD6+YYtki7QLujw8qUDbnnNXcq5TE3TV+qy60UWz1XLZtv/z0ugPPfEOh+xWf96FhgAI3/eOUajUxmRvI978IFfnAGfWsyoc1dVADgDUvdmFNx1WGAtj4l/nQlh9ClThklPtEoIjoQruMTKldlJ8U7BRpjHIrufOibwiUBx479KRgWxV6ZBa09Z9H92fty2ojCxhl+u7rkEfvys0fjmFLHPSMcyudlPfe8s81mnl+5dRLM/oVfcY/KbntZrZMqZC7dvA752YdOWa7GY2CIh0aDcFN/P2LN0lx0z9OZ7QrJwNt/SsTEu1jlQtrkiFFEoe1tS9+/+jaF79/VHFUGa8JIeU7cRK9UhjbJj+uTW7iQFmh0ZNvuEKgPFuikwx8ZYVJect6ZIVI82BNdVKB7OtKKjXhgCsNnxKdsdTSy2ZLOBSa+ogVjw0feOYbRqPumnyINK3z/mmoaBWBTHi0f2VCon0qXR9aNqgJysu68etxV23ti1lj1fR4bGv/91g8IOCyiUks3JnOlh/QiQUxVcKjpYZG9SsZ8kzuFykTzVskPCozjo1VltVHPRJ/b1JR+QJhUQKS52dVp+BlFD9PD36X/ESDbMWP1IFnvmHUhzX/74Fnvl4hTOq+Vh/adLhtJjzanzLA1mcqz1WTd5wIgAe+HnfVpOqSlni9G9+0Hmv+1wuNCsGSQMb0t6hg9oqgTfjL0Esvge14IUhWWnJ/Etyi0CbqriW3s9qV6WMpqoetJZUanSlxX1E1PfGe/Xoq0iDfaQvB7ep1atAW6rx/GtIGbYAJkfaTzBi2PlKtsMaIpMVh7QPl3qkgoQf+8r7cPGs9YBMdriOcSXJcm9yYtorHsyWy5Y1jKzJ+TdS9yhrDxlPeeLasvqi6eL6yxrGlQ6JZ46DiO2brODYRYIu5a6mXXXAcGyc5Gho98MzXj2a9d+nm0pWacW1GSRlg6xOVEwLtPVCLSgbagHrBrRC05XwR8r83BL7gE9nKBLaksqAp6Y7JLsKb5fSx0mVVBbDFnokCGydbNrDl1J0JbNntygKbGKzNi9dbEbD55bb98uoQ3M6Ium3cI5M6hlHpAjcDbb0vExLtA9UCa5yx6U2BNXHFQ4iANxwIyPn+E4jxSIRI5cKjukKjeao3Jpd1OysZUIvWwauzOWut1bO8R6PGselW6iPFOU6ihy8n7nvgma8f9aFt26+uXheHNnnpDJEaaOttGYetx6Uf1tRADSB44Otvbxysibls/mvPci+ylBcyEs8r8oubW1eGg6EeGpVz2XQ6bFnScY/RqvrHc9j4M0Sz3tcMryj3/cxyuhh+lrDDltOvzLBottsV7ZO4u8aoV8ply3HYMrOECWmnTc1h83Pe9I8zOXnEZKCtd2Ucth5WHbDWK6Amowf+8j4P2uLWWsxxK+K2SU5GkMkmWkZ91mgzR76r3Ew+Wa43VeT9KOm9LFStWGH5iQZlnbfiXqQ/jm3br65et+1XLrwdeMbrONfH/P6e90+DWqDNOG29KwNsPapKYY3pqrnPtMMaUbiOZPw6Xfu/xwm5bIlO+BUHz/LDpHqgrVBoVDaPzHdawe8/HY6YDpXZjzpgUOltUQr91QPuMq2G7lqzdOAZrx/1gW3br65Zx4e2fJ33wUHc9DYDbbNVBth6UDpgTXi8GsdVAzTAmgqcidYjGeoPXbZYxZBz2xoAbQ112ZoSHu0Nh038PU0XKzKOrSwkK1Zz9ct46D8SuqENQGFwM9DWezLA1mOqF9YKgpouQJNsa+1HjscDf3GvakXe34TbpgXaRLKJQJtUbYoTECTzlqgiLlm5C99KqiHHM1TjOiQsEXet7lfnj2Pb9qtr1m371TVBiFS1TzrcNgNtvSUz6aCHVBms6Q6BVglqGRKBtrTLFhVNbwkMPs5OFpmEIAJsBSYgCPbF70fVkw6yIEsW3spezoNVL3fSwXeeK37+ZAzW76mJBxnnJWv3lvfs47fpiQ9r9U88SD91n/jABgArfLdNYOIBq3odIVIDbb0h47D1gCpdtoPjqgGSsNYQSNOr0G3LD5GKOm2C49DKDI1Kumwn33CF8I3gVSQCUbrWYasK4JI6/jsXox6/R9JnKrzURbHm+1UHnvG6UR/anvzVNetW1DyuzdwVoTdkHLaGq2mw1uugVtxl85VwOFScNkH3ItZS5tlQv8um4rDJQpKuOx2ItiXTN1Y5lsN2/Hcudn0a0fczw2FLPVN0atxdzJ3cduP5BBw2bhXpnVveLeCuXTVP6hjqcdjc9LwFdNlP04V8cFux7rU50JbtUt70tnZ2cUEZaGuuDLA1WE2ANWFXreGg5kt0LFszoU1HaJQTSgt2iH3Z33mheli0KATxYE3mb1adIn0QfX28cGgAbECh0Bo/STUsykC2GoBNBNaA/gA2Ctdl85/zwS37fQNgoK3PZUKiDZX+8WpAb8GaSJ3yh6jYBISkEoP5VcKjUiEivRMQyklnq8hdBbJuJyVbVxLaRO8tGi0v0jcxFYkPlhVb7J16D75qvrfVG/3N0oozXjfqQ9uTo9euy3fb2HrWBwcAADcXBDczGaGZsurugFFaPQNrhGiCNcJ4lFkuX+Jrt5H4FrcL2bNx8/LEWsl8mSTzaWZSiZfnp//tU8FDVL/59+UBSGXBmghsJcevsZwyvz0Zyb6mqPr921D19Ym6ayqq/5jze7BiXTiO7cnRa9dxMwrIB7ci0hXhMdInA2wNU5Ngbe2LPzCaCWvKyocsFoqJoVl+rrUfOV6x31ltRrZUoE0gj/gRz8tZNB04+cYrhHujIh6oRdNE97PEgzZVcJORO+FARPre8SK5xasVrFdD86G7JlGf6C+Uiqku2tyKda8d9d01OWhLd/pZHzDQ1m8ywNYgNQ3W2OWKuGppiEqBmF+9wMPPm41o7L0i0PbAX94n8VoLQpvUIc1z2cTrVnPZsjNFx23Jgk/UVRNJy4O0LGeNN1EhCm6yEhm/pixlMKkonwaJTTSYn5unEol+xhWOsxq0pWWgrb9kxrA1ROXAGkcMWBMOgUqLjVAZyYWbIMzxzdFMkoeaEIGZd34bImPa8orzC4pXmZdTtnPlKm8smMp4NRGxJiIk07L6VVwExcclcurtqbFdvVZv+Vqx7rWjT45eu86HNhfiqPhL8vI96wMDuPntZkxbP8g4bA1QebAmFoIrB9b4bppAXLOYoi4csxl3r5DL5k9QUHDays2jz2XTVEBJWePUonnyQqAykwZ449d4+asIkzZJpOqYoKeectcqOkbRyQdF3LZnfaC4N2OctvplgK1mVQ5rse/5MmEt/oyUDWlZXYmETtOJ+VKFtrJCo+KHUCxnHWFREVDz8xUdr5aULLT56XngphIOLfZx6DXDg9/fLe/eW2E/9Kiqox+Hts8YaJvFMsDW4xIOgwIVwFqcyGKg1gQxwG3tR06QrEMntGUWFShY1GUTqL8EiYBaNF9RiY5HE8lXZHybmsq0oXtLfHet914LX+zX0iRoM6pPBthqVNFfK3xYY3zoE9/t5cBauCUPKkTDQ7wpWY6Mrd0m6Tjyj4X6F43urygVl+3kG18sXL/sOmxZsKYD5LImHIjCXbJPIhKfISqvZmBL2l3PU3PdtWYcUV8xaLuNDW0iPS4KbcZlq08G2GpSpbCW0ANff4fmZTvisCZOQ7rjpBL1Rca4SbtsgODxKZBHm8tWj4sGqM+SlAUy3RMSijpo8q9bwimdbfk8rbxqgVwBfU2XIPUerFj3mtEV617jziDlQJtImwbaelMG2GpQYVi7ViIMCsS+D6Kwxs8vc9Ul8S0pUCtT4uBGABwtAG2pOyRIQJtSaFSo5rILFeu07BIfefClE87yJhuIQlupS3kUUvPDqSLumhCsKYNi/fimohXPVIG2uAy09Z4MsFUsLbDGvcZkh0L1w1pkS4iPqgA1hTYluqUGbWEzUqHRylw2Tq4S3qosCCoT1lRCoCLQpmMsWxORoYo+NTcUitKcQp3VpKFNvhYDbb0lA2wVqnJnLSIhWBMWA9Zy89f9tZTfh6P/TyE0Ktx2+TXf8eyvyBdi79AqEddJFcbKWp/Nl4zTVo+7lv3erX/hj0uptyqtfHforjWjR6IimU91yThts0sG2CqSNlhTcNeEYU1yXFY+rCmAGlF4KDWgrnJCo+ou2x0XfBl3XCAIa0rity068eDSTx0ZbPOcriyVCWYiS3rw+uRLBNbKnHCQpfUv/HEBcNMt91zaclWV7loPoZ6Cs6cF2t5vqxYFYKCtKhlgq0DFYe1Y5bL1wpqglOGrSHl2ZmWXrdC9VdV0+wVfxu0XfDm2j++yNScsCugJJdapavsvGXb3tP6FN8bS0uDWbJCJumtGvtjvWQhtn10nkJ0pA23NlwG2kqUH1rxPnaS7tlFrGDTRWlFY40JWQYtNCt7UoS3lsgmpPJdNsSv5bWtU1GUDxKFH1+K5ZUwyAICL/2+VcB8y1Wx+0iYRd00e1uo4eHXdE4ItH9qeSkKbiLwXYqCt2TLAVqLqdNZCWHt/Pqxpm+0oQEq5kKaiHHiT75BiN6q9fJ/60z+otD0dUoW2pqg0WJN1pBV17Leeo7U+tkjGM6MyteKZr1aHNk8G2porA2wlqTpYS18ON34jCmt5AKUT1oSqSezQfTnngJtQuVDKLlvu8VR02SSkPSwqUZanuy76ZrAtA21lTyqIKs9lS6Zd8lEX1u59/vdL7ZeK1l9+Y34mWSmMr0pqy1V7coubUGixz9pyJWiLt2mgrZkywNZAxWEtLxwaVxzWdEhubBs3mWTuKEGJNoTdNjmphUYVVEZYVLptfbr0k2LQVhWs5bXHgzU58Q9k77lQ8j0WgTXdbRZX770zgCq0xVUU2oz0ywBbCSry66JQGDQFazrctUhNKteuykGN1YEEuAmqvAkIIo6lmHhhUaElPjSNY5O5RVVULGgrOq4tT7J3MWD1SQXWjv/OJdJlxBV/33juGjMc2jAx3bUSLhm9iWFi8l9bAG2/Voe2cwtAm3HZ9MsAm2ZVC2vhZceHtTXanLWwfuVQaArWivZEUw2ZlTXBZevnr5O4ktAGNGdcG6sfl3z0kBp6Uo90noXF3TUBzZ6PjbAMtPWXDLBplP6TUywcGsDaFRKwJugCKedRhDXCeeSlidcu0qUwsVHLfHDConKTD4r0q5xvxEs/eSQu/eQRsX15bluRUKnImm9pV+0QJqz1CiOouWvVvrqV715YTZuanGXNnShNy5/hQ9vnlKGtiAy06ZMBNk2qa0ZoDNZI9DKg54KgNDheAdbS8MXDszSqyYFbOdAm77LpC4vyJHznA4ZK/zphNJCENkAuTBqV6l0TxFy15n7B31fGZIOCelxoosHC8jsiq16hcQEVhbZz318MFQy06ZEBNg2qB9aImrMmWDdrU7aoSGEmehEixmskDm/i4Fbg9VWmijom6jZo6E50pihPl37yiExw0x0uzaqX56pFdY/oDNHGnme9pUYexkZ2Ki0Dbb0vA2w16zIurGWHQ1mwJuyuCYbr+LlEvtSz22CDWm6xjIpkwU0E2gq6bDKTD0SlJSzafLGgzVcUsmQBTrTsJR+rY6waKeXLPzscWi5tNMddaz5VVdHD5c/4w1qhzaiYCKUGeouoyK+Gy649Nh+KGBk2fuOdaWdNJhwqChICIMPenQ9rsS2dVyoa38h/c2iiHLdC3P/n9wh1Ye1Hjo8Uz+tBpJ+prJyylJ2evE2Vr1N+8rKsSrjtsnfzX8+dF36dm+brpBtexGk34zhRiu+9cVNu3UV1yccOTbXLl5t2z6X5Dtvx370kUoRfZ3DUBc7F9FPKDYfmj1/jt0lz2uRXSYVgDWABG6PeyDmfeQQzP27xc57y0lK7s8+D7Cxyx4/G/8uuk5mF8dllPPGBzQc4N4nTn2QlFPj5O52M/mXr2Muvaz49N1QGlwuoGKwdo1SOCWsyKuz6aIQ1FUctTzHHTcJp0+SypYsXeYHmuuaK4NJPHI5LP3E4nveJw7XWfMnHDg0eRtWrkWPXelpi14zCTtv71NHBhEbVZYBNUYVg7ZpjoPJlXBjWypLgS0nBWpmSgrZomeKqbDHdhHSHRdmHo36IfJ4Hbs9TALjnffwwPO9j7qMeSKv2+B17/YVibWrulqi7ZsRQRaeIgbbekwE2BRU+2RQ+kCGsvY8Ja8Lh0ExFAIdZjZg7l51SAazFGhWBNvHXpbzMR07dZR6S3NmiFTIEf+KB+rjK531iNZ73idU4doGVejzv44fFHipt8iQSDpVRkd40cXZonla+x7hrdasotBWRgTZ5GWCrWK67lqd4mM6HNZZuP/+6ek0PqR/vKrBGGA/J4jJQJJCpnGU+xNqO5yvrjReZVFJeM0YNlsB79vi7dufmKQfWzAmVpYf/8HeZ6U/95vPS0FbEZTOSlznakioeCg0lcnmJwlrSXbv9/Ovcv+ddJ9aBUsdTCaRLxSaz4EwS3viWYTJTgfSsotV9kdQ5W1T1FlW56uHv4WDCQQ1yw6FG5arGk1OiaR/WHv7D36fSohMPqoY247LJyQCbhHTCmojYsOZ+Sn1Y8/V7UWjLkRDbyNYnlVu2cbkyul5aaS5bSnp6XGQR3d5WD9OeoO67/Ia6uxBIzF1bVH5HKlTTz7Cks1YOtKkfBQNt4jLAJqiqYS0qnrOW1O/Puw6/P++Liq0ofOCEQ3Mi7lrRy15OeRmXTeMVuK4JCPlq+tdMiZrFL71MicCakQ6JncAPv+p3ePhV7DAoE9qe/qpCk9kMtJUvA2wlSxXWNn6TPcmAB2tRqUMbT2ofxMK+F2v4Wqahpj5wXUzxkvomIOideMALi85el61/xXPXqgmHyp+xKXfNwHMp4oFaLE8GtKm4bEAxaDPKlwE2AZV2U3eO+LD2JeEW9EObqvLcNUaiSJSTmyejoO54r6Ca67LVI5FbVMmppPc0o1rdM0R7XcZda44eEoA1X2VAm6qMy5YvA2w5qnzc2jff5cLai9RhzVcM2kQHvmuaqaj8FaoyhE1rM3JhUWGXTffxz9EpfXarKiNxHdfQyQZ6xq4ZBydLD73qt9JlsqBtewBt4sfdhEbLkwG2DNUKa4lz/tSfvVypH7U7bTLumqwTx02SyVtcaz9S1QSEiBRfR9lh0dJmivagyp4hWsVkA5HTTMRdW9VnEw2aKBVYA4AjPncac38a2sRloK0cGWArQZddc7R0GR/WslQE2n7/rC9k5NA7hipZb7Hy0din4lpszHr1SbS2B/7yPq3tyrXexNqNel0mFFq/HnrVb7XDWlJK0PZec/XQLQNsHJVG+TnncDIUmtSpP7sSp/7sSqWms6GtZsm4ZKz0mq8NIi5b1TJh0dmnJoZDtbhr5rufqSKgJgJrRWeOqsq4bGwZYGOoWChU3V1b86L3Cn84eh/a5OaQyvtqzbzCl+Oyyal4WLSZx7b/FR73+15Q/9prj79rV91dmNV66JXlumq+lgWh0S9U6rIZaEvLAFtCvQBrvnof2vKV/Lg3GRWa6LI1Vfpnilaney79Xt1d6Bn1x9i15l11qoI1X8WgTalJAAbakjLApkmXXV0trPk69abmQVvxy5v0VNVSW5HR2o8cn5unSpftlJ++rLK2fJ184xWVtwkAh//robW0y1Idt6SqMhwq4q71B6w1Tw+98jdK5Y743OmF2l329Fe60PbbaqHNKJQBtoiqpPkHBSYZiOq0AtBWBrgVP4iiNRRraTb/dJsti+hu+odH6+6CdjUhHGpUvR565W9qg7WkVKBNVcZlC2WAzVOhUKiCu+ariLsW1Wk3XYnTbnqFUtnfP+vzOrpQipJvSi98cpvmshkZ6ZSQu/bexRX0pCrVf9VRBrXPn44jPq8P1nyXTUXnmNBoYRlgKygVWHtQQyiUp96BNvHPH408yqi/LlUFbaf8hB0WvePZX1WssfnHtj9Fue7acddfVEkPHn+nmWhQtYrAWhla9jT10GgRaDMywAZAnd7VYO2qdQBwVAmw5ksV2n5Xp9OWegfy3hKa+bRuibhslahhxyWqXpx4YCYc5KsUd63B53GZqhvWeIe9DmgzLpsBtmrHrX3rKoGTW093lKHtXJ3QVvS1JL01Oa/tt2d/pqR+8WqTr7e4yybWJs9l01O7UZ0y7lqoB152S91d0CZVWDuyJGeNJzOerTrNemBT1WVXr1UuK+SuaTgti0CbNnDLfB0yLllGYiLpt2dfG8BaCtoq/LiX6rJpeh3qYdFsnXxDPTNFm6Djv/u8UuqtY7KB7GlW59i1B176C/fvy27paXB76BW/LgBrT9PcG758l01FJjSqplkNbOqhUHlY8921o174Hr2h0JxXcNpNryjHbaOpDZluCdQrn98FtWtTWVhOG78ZKtePnHzSExBm9e9Ho6ZKxF2rBtbYHxAf1mL7ehDcHnrFr5XKHfn5p5UMa+zjHoZGv2hCoxVo1gJbHaHQENaqP9/qC5FSeedMJOrJyPO0W16bX2ZWEVH8taqGRYu0WY1KarMHTpWqwqG9qrVfObvuLgjrwQKwVqeKQJuqZiu0zVpgU9XzJd01sXFrxSQ6huq0m1+pVP/vzv2cUjm5eaCc3bwHp8DTbnkNMyXqsql/0tVKirls62vjg7LCokb6dN8LflRb26W6axpOepa7BhhYC1ThhUUW2s5576zkLmW16u5AHVKlczlYo4iupa89FKqo025+pdJiub8793M4/ed/GN8ZvMT4a02LApTk3Fogr4485b+lvz3nM3jaL16dX4fS2VH8wrPxL9djzf8cW7ieXtJdz/0mTvrRi/LzXXy9UH1j96T33X3JHUJlT/j+8zPTZ+MM0aZPNODBWi9JGda+UK+zFtWyp71iVNVhO+c9FL+4Sv7av/76K+mxl1/XvPuGlShC6ewiXB2wRhhbrKcPfuvd7HFrxP2Pf6YRZn3chkhGn2L5wrQidziIgRtJbaSb9f8X/mjJfAbZbyd/hihwOhfa8oAtPUlCeIYopUIzQtPAluE+ZqTTdAcDse5ycMqPX8qrgbE767WGx/DOi76Rka9/xb0tVc575qaw3zOWwxYPh8YL0dQTsfcsqcfeuTOjnCumu8Zok/mM2S3OMAlvw9/MgjW2u0Zjm1m9i+/O/mzz3jNmvZGnD77itsx6sxTAGuf4pd9/Tn9iSek05vUt4z3zoW3Z014xmjzfuVcqL0EF2gBgNkGbCYmWJC6sRVQ5Kkc+kKfd/ErNIVKBQWfCLzgv9pkbG+WGRgHgd+d8llNnXp8UJfGjaOOb1qu34zenUOaO5+gPi87GmaJlzBCtKxwqAmt1SR7WypLadUEV1o78wtNzYK1eLXvaKyofzzabNKuATdld+zQvFMquzoc1dUmG5gp8cAtDm0DbsV9p0n0VHsCWkjy0SVUvrbX/e5yeigScGk0NCO1m5bvzom/MSoft3ud/H/c+/we49/k/qLsrlaiOZTyaA2tqKgJrvaTtv5Mcz/YetevZbJqAMGuATT+sMZRogeuulXB6CYfmGNLntGWFeiJbVX28KHLGrEUyyqbLhEMjEoE2HS4bAG63ypgteueFX/cesxPUWPLBTRTgZD4Wx3273NmhyqHQQEIBR61a+1UDa02Q77KpyEBbtmYNsKkrK66fVhgKfXfOSdus86sQtAm+lEqhLTL2hDdmLeWyNestKSj5F5MMi2aNjgsBzX0Y5evey37gPX6Iey/7oVAZPeFQKRu80bqfNyP0q+dU3BN5PXhlv8Ja+uQJQqOey9Yjp1fjNSuATd1dWyOV/8Hri4ZCRVXOeKoi0Pa7c3y3LW+AbmRLLsIppqDOrIGuoQJoEx00nNqb0wLjeIu7bM26zN154dcMoGmUD26i8KYkhVNIzF1botCZYrr/pT+vvE0devDK2yqEtWZdMwBg+++uM6FRTZoVwFa1Qnct//zRdoZpqsidjPAqpbJK0KYL3GKgloY1/szQaL8l2qpAG9+0QbqMWNcoTvlJclaoq6TLdudzvhY8jMrTvZf9EPdd9kPcd1noqPHcteO+fVFp52BTJxpkwVpz3TVaCNSa76xla9np6qFRI7b6flkPPe5aekmK5DIavruWDoXmL7OhtrwHY6fo8h6RtrPa/f2z1O5ycPov/GU/8mdbE9YzpVU9xDwv7mQDIL3OHM9do/l5GBlTElvm4xhOl3Kcv8y23TSzYG5vig1snDFjNJ3GLOf9kXPXxM997jNmFfGd979EFNayhlrQ1FOhUXYCx4+X5cEr1XjlyC88I7fN6B9WGv8SJXe9Yl5Vc8695G4/LLr0dNYB4b9nZpmPtPraYdMaCs24EMRCoVItFoHlMkHbrbtsp83PkXbcIq5b5oPGahAx6jKdNpE7Oohe/DRJxWUT7RfPZTNqrkQmG6ielU1018RhrUbphLUvPqNgZ5qrHdKhUUepnX4OjfY1sJUp1hlx1OV5Ew1KFk3CT3FVAW1+rvQv3rwHr2x2S6EDmNej9C59VwKKtf9b710NjMPWe7rvBTfgvhfcUFv7dYxdY6kSWFP8sBtYi4piGdNZM1JR34ZE9U80YIdFH7z+PW4oNAprKUOW49CSMK15YdF4336nGB4F/BBpMZeaQAcsxW19nqN2+s85kCoDxLmfq9AV3PiX+ct4rPmfY8TDoTmhIQNq/aPwbgecM1MwJPrYOwRCoe9bohxeEw+Jhjt47hof1gRDoqmIYnZILzck6iWrghoAHPXFZyiHsVlp7LdJ/ppVPCQa9sd32OKh0fz37BdXqflK/RgaNQ5bRPKzQt9TbFZoYQIpG7bDD9vpN7+KDzI5ct22Yn3VDWtZ+t25DDgtwb2UkVRolNO9O579FQNrfab7Lr8B911ezHETgbWqlRUK5apG70EV1o764jNwVF86a3zFQqMC75lqaLQf1ZfAVnUM+6jLr4p/Wisbx8auTp8LFKsWoBnuU45CaKv6qppoM7KZnmQQKgZtsqFQCXcNlHX/0CKKt+1C2leY9w816h/dd/mNwaMMrXpfdaHQKsat6bwKFYG1MtTUmBl70kF56sexbH0JbCp6/qePys8UefsfCkKhV2k5CflnVpb9XYXSDReDNr/OKtxByn3qSxjaYhXVo41v3sBtP7nXQNrs1frLb8R6QXBTd9c0fA4YVWTB2tG1TDLIfp0bX94sWGuMOIfNhzbXZRM/h855t3HZgD4EtvKouki1WWM9ClTLq0C7yxZ3hAAd0OZXpvvtYtSZ00QWtEmHQiXdNV+6XLY7LjCgZuRq/eU3Yv0Liztugbsm+lEt4Qp89FfP1V9pQW18+a+Uyh31xWfm5KjjR6Fgmz3mWfWby9ZXkw6UJxp86qjYBAC+3BH9vrt25OVXjXIH+ItOPAiSiOLEA06CzOQDQGACQlhP9FCxXSgxsWdrqowTzRs0LFaW91rcmbI6YC1sjzeuWOQ+omv+++jUvtsv+LJA20azWcd+6zmx54+9Y0dumVgolD2SPa3MCQeRPYmE+19yM7O6ENZo9qdQYO1BfzOvh+HudJoqqAFRWMsY4C/4o4836YA/JyDn+LB/+wu1yd9FmTmCCQinZVmU6aEsv3j37J6A0HcOm6ye/6loKDT/CzcKa/EUOVeHJfWwaEGXTVJJp62Q28a8usg+OMVzJXZcVBcQ5rXHgzWV9+n2C75sYM1ISOtf+GOsf+GP6+4GUzxYE1c1xoOyq3bdMwWctRqVCWv6FYRGf/8lqYl7Z8/y0GjfOGyF3DUgYuxk3wHgoW+ngU2Py1ZkeQ9OQokuW7AVKaLqtsVCkhoNNpVCWa8h816rGtw1f6fIjNCxe+4QaK+/NO+EU0qr2xzPtFITDUpy2LJg7eivnRtzazJ/1GbbbxlZxRy2IrCWbkbVYUu7Tsl0fjPi71k8d36b/F1shw3Ic9nYBggFcMssdtlmNbDF3TXkhkUf+vZ7me5aNWHRSPl+h7ZSlXOa0Ow155jQphHWgHxg61e4KBPIimo2HvNygC3+5Z8La7EiqsCW/vKXBbbCsJZqhgNI/AtEvFzGa+0VYAModvzuSxxo4wMboAZtBtgaosLumq8Ml82HNSAL2BhlSUZaKqlsly2nD4AgsMXr6Q1oEzhFIhfyrDBoCtpEx5wg63oc38mCtn6BhiaDmaz69T055H1L2KMV2E8S+cSA7f4XC8BapEj2CLbygE0/rLHbnM3ABiShTT+wAb0Pba26O1CXUrAmqCNf4MFa5G2nEPKusnNSACSvJi+dm42RQAGavklDRhNUENrCtoKuw911+s9fpQRt/p0H9IKbGKglc5528yvx+2d9QaCs+G8FUVhLqpehoJ/gjCXW6+vF98vvs/966vwZH4O1ukSBjS//pXLxGKyJNadBdbxr+W1m5Vh62stHZcexARRnv7uLW95tyxXrA/W8w6bqrl36qaMy7vYUTwlCoS9412iQiWuksV0uzhNu21pdNm+3/tBour7muG2Cp0XOr20etJ128ys1hUL5Cbef/yWB+pulfgc0FfUiwB3zzQvSO2lqgy0Bh43nrjFhTcRhkxz3xXSPItr4B2qwdlSwiD/bIeLtiB9aVYeN4WaV7rBluZPuBr/V8OLrQ1vosmU5bO7/qsDWyy7brJwleumnjiyxdvHwGDtJsLzkl790HimQZ4T8vF3KM0g59/nM70ekcYGsQqERhoTctwLvRS/B2rwTTgkeRmn14vHZ8KKfxneIfjQE8mWFQvn16TMW8moqDmtFe1CGetuYYensd3fr7kLl6mmHTd1dOxLcAf6JcWxpdy2SSdRlU5h8kJ0rz2XjJMq6bICy0xY8K7hemyrwZSoFat5OjrLg7LSbXpHdELI4PL2zV0Ctl+CjqeoV5+2Yb16g7NQkc97/4pu4RbPctRx/Tcphy+qhPljLctgyrj4FHTa+ASbnisZLqDpsDMcvmSmSGHfZ8h02YPa5bLPOYQvdNc4FQAgBJV00abOqqMvGL5YXCkiXke18vAXq7VJ32nStgeb2gzIv2NmvMWs5j9+f90V+YxB8Oz01HdZ60SlqsnrleKbcNkVlw9qzCtSsx3Qo31kTUe8aKKUp4+tutrlsPeuwqbhr6VBotsv20Lffx3DXEpnqdtkyM2kazwZIOm3segmyl8zIkrLTlsm2cqcQdzxbymUTgbUwocmg1nSY6Ec12Xk75hsXQNVh4wFbCGuMeiXHQnHTuVndZ/phTdVhK/JjveS7HDCryX7PMltmvNbQZfuD8Ds39ZLT5VSctl502WadwyYqH9b4kuTFsly2SvJA0mnz601fGk+7+VU4/WZ5+PrduZ8Xd9to+GD7Z/muWroI5YY/4y6b3DFvIqz1ivPTr2ry8d9whZrblg9r2SrLVtj4B79UgrU1X1qHo2QnNzZVogdX65uQXdmO33+5Tw6uXvUksCm5a59kTTTID4uy3TUR6QCuvFw6QqMSFSi5sRF6iuw5TQHaAE6IlIIJaezQp8JriLzubGhL/AbMaappsNZUSJjNauJ7suGKn0nlF4O1spCMX+/GP7hVqcY1XzpDtTMFJXm9L3BI64q7Zd9blC+V0Ggv3hi+J4FNWYJvz0Pf8UOh78w/ebKcb8X2w7wSBQRCb8ndytCmHEaPA1MhaKNhVxK8ltmmlCRf6+/Puy5oMev9uP38LzUK1poIBUZxNe092nDFz4TALWvcWp3SAmui19xaHCxdqr5TfjjUuGxp9Ryw6XPXdKioi6bRZVPJowptQAFo89txH5n358wQfyxcNr4JK+P1Zc0M/f151+XCWhPU5LCbEV9Ne99i0Jb4zGx48U3cckKhUJrayMknVl/TnDU9SNRI2qtUZ1/V/y5bzwGbfsXDooG7dpmAuxZWkfU0JzEjd8SqKR4aLQnaNExaUYU29/ZRmgDNl+BryoK228+/jlVxI2CtSV/2RsXUlPeS5bQVhrWS9EDtsNZTfJCj8l6LcdnY6ilgU3PXjojvkK6hGhctu7iO0GhGYhFoA2qGti8ILmIrIMnXcdpNVwrlu/3862qHtaZ8uRvpVxPe2w1X/CwT0nwd/XXdsCb2mX3gZbc2ANbqUn2QqL/l7BrPvqojXWMvuWw9taxHMWDLWgbD3fEwy11j3KoqLcklPjL6wK8+b5mPRKrsorrebqkbxTPrKD5TWhXAVKFPfTKFK3/sWlKn/uxKjttWner+IjeqXk1dFiSANebHjbEzEhLlf0JTvzZT6Q+8rAxQoxmXjayQC3uUrbsh+OOfc/z4wZu8kHJGn6JlRaNDQpGhrPctTPAdtqWn/sFobqzJa/eW98jfIr1XlvjoGYdNi7vGVdkumj6Xrfh4tox8RZ02QEuYtIjbJiXlvjIvZykZWDOqQ733vuu5qrFKlgZrah0yKkuR78h+dtl6Bti0ivHWMN01Tl7RerWNZQuSRTojMp4tIwNNjgZTHBsWTOFU+xyUBm2F+hUei2CLuk5ak9SEEJlRvWraOZDtrpUjdVg7U3NPmizNb0hBzyCppad6Y9luN2PZgB4BNj3uWtETswSXTRbahHMVhzYtbltQVA2QtEJbYecv4aolOLYJ0Na0L2mj+tWEc+Lor58nX0g4nMfe/cDLbpFvExKwphQOVakvkUEzEAl9LcnUp9qoZvWry9YTwFaKIm/Nw995/zoAOII3M1Sby1ZVaFSmyewxAen+awA3CXgqPBlBC6gxYK1BasKXslGzVec5UuVabA+87BZ1WPty9c5awy4lCTWjd77LttO4bM0HNr1j1/JdsGKjKdjpZYVGhfuqAdq0gmdQDRWCuNNufqU6uHFvzi7UwdhWFqzVNV7NgJqRjOqDtptLqDX+YSwCanFYKwtUeq3eOqTvtfSjy9Z4YCtVNOquvSN73bUCLpt8Rc2DNu1uG7ctBsR5j6y1z7IkD20cV61BsGZcNSNV1XXuqECb6BWml1y1/lC1XHNA4LJ9ZVa7bI0GNiV37ROH5+ToBZdNQCox0SLQ5iWz3bbqPrzlQlsa1PJCoHXBmpFRUdUCbS9JQlvxa0e1sFbWDNFitfJL12cYNcGq6jeXrdHApizBw/3wdwXdNcl6GXZUfkWyodFInvycstAm5rbVBW76oS0D1BoEa8ZVM9KtOs6pNLQlRFMb3HzGWWuiyvkeOODUl816l60/gU3RBYumF3PZ2Nlyx4GVNp4tkUOo+wJtZ4JbufBWBNpccEv3UxTUgHpgzcioLDUO2nL0wEt/oR/WRC9Z3HyZF/wCmqVj3wq/H/2nxt7poHg4NLVsf0wPf/cDrrv2/HeMsvMRfnGhux/w+5B5NwFOX/KaEbsTAqM+oQICmdg3e5BpRFmqEwv8W0uJ/qD3M1V9mykDa0ZVqeq7JBz9tXPTOyMfSNZH8oGX/kKprTVfPivZALddvlTvcJDeEW8uu83sbiWOE/9Jolg6jdlDZhVZhkOWiSARfUo17275DpvvuOUfP/TN3Q/61GGTFOeELMNl054/KCPqtCVy6XDb/CwRx43vuun/gaDutl0n7Ki5qhbWTAjUqGpVfc7d/5Kfc9PKgbU89Zqb1Wv1GhVRI4FNxV173icOzw85eoq5a/nZ0xK2ZNi/ULSHRoMsZUObOLixw6WMTJogThXabufcBzQut49Vw5qRUV1qCrRFpQpra4VhzaheiX0PyI9lozj7qrZ0b5o4+aCRwKZNuYc7H7iKv2N8ZMnMUwe06QS3SFbKdd5Y9ao//BCnrPjj0cIeG1gzmm2qBdo4P4aVYe0rOmHNzBAtt16jPDVuDJuquxZVLPBM4mHo0F17+ygjN2O4VcbYMJLayFBF49mCLDJj2hI5E4U2vmkD1vzPMfnlZCTyUiXlnzhirhlb7i2m4qdgVbBmQM2oqapqbNvRX/XHtLlwpApqgAdrqSFTnK8XoagJzRkulRVKSRcKm6R48p/aWPGPA9n1ig7dEY0AZY5hy4rA5B/DTIiUPH7MPiEylu2Ul43mvW+A+3JvfS/vGPPVpLFs/e2wAVpcNvW6y8gv77TpcNs2vmkDNr5pA6ecAvQnDLJgfdx0Uv7DK+vvOPVnVyrf2zPpthlYMzKq7vy8/6VheLSIq6bXWYtICdb4evKDM3jyn7LCdb3mkvVavb2lvgQ23i8q312TKBzszD5dRE4mdp7cX38aoE2wBFLwRZGCNDa0RcsW/GCpEBtH6tD2pdjfsmVgzagXVCW03a8Ma2cXaLk6KKBwYS2qTHAT7dpsywdg5x0CY9n6hPcaBWxq4dDV+ZkStYbhUE4GGYnaz36eXCbTDG00pBrxV5mdk++2xRqWarEsFYW2smVgzaiX1OTz1YW1+q85acX7tO2DMylY01Gvvtqa45JllQiW9ZDQWe/q7ckHjQI2daWPZwqCZA65rMumIdRZGrQF2eShbeObs6BMBNz8FuuFN1VoK1tN/vIzMuKpiect01nTeskpPuFg2wdnsC0H1LLDo0azXY2ZdKDkrn18debA/+ieh7/3wcRkA5YqnIDAyZo5CSG/cYFmSfypgDa++X6hfPyJCVkqYzwn+1SqesHbLDXxS8/ISEZVL7LLUxzW4kM6cn8Ix3ZnfQVlLZjLKBt5uu2D01kFA7EnHdCMrjVzwgE/V5Zxwj5+ua4fDUOiB5zyUsZ3e1hRtIZenXwgv/xvY0WR/PJP75GvQzg9SBJp1cvDyBrflZshv1+pbP5pS4SPz5r/PloI2rJnk2Z1qhqd+rOXA6gX3AyoGfWL/HO5LnArNl5Np4rBWu7s0B5TE3vdxD6pqGcdtud9fHX4JMfd2uS7a5e+bTS5zEdaYktrZN+2it+XVGYhE02z0xZkbZrbVp3qgDYDa0b9qqqhjQ1raXASd9jyvn7kbklVzFVL1JvRLo0/5fcplsT1v9JlpRy2vGE3qg5b1mtx/9t5x1c5LptXA6MKWZetCQ5bI8aw6RvUJzgQv2gdWbmkXgn7BM4bkcdvR6Lx4AMmN7ZtzX8fjTX/fXRuPrHxbfXJd9uqkoE1o35Wled39c6a+Pi1bR+YFnPV3jaIFf84WKhPOlXo66SufBWrCZMPGgFshSX6y4KRftdzvyWTPbYzuyWJs1M7tAm2HWSl8acCkgG3RomGj1N/Wg20VQ1rwZp25mEeAg9dquI8F4Y1Csnxa8W07QPT2PaBfFA78G2DWPE2H9Q0HnxtKqtP8vUmSzzy+nsZGQTqbeJhVlTtIVHlyQYsMcKRsXBoNKOXJQlsJ/3ohak6WE/9nXpCo/E+ZTcrGh6VaRvM/moPk/53JExahbmce2ZR3H7Bl0vtQllfYjV/bI1mgXJHj3BUdniUD200tikHbFkfqOxwqCiopZvM+xDTjK7104QDdrsUwCOvvyeW67Crj0/kC8uxw6I0o2mKW98r73LWGRrto0kHUVFkT0CgAGUDUhTgTvrRi7KqhPuh4UBbkJ9ZULTbua8k2AV2/6TaBlKTEpjVJuQ7bXng5i8Tsua/j8n+8Mp8HKTBpTrS0Q1rvOt7WXc4NJp9il7NkuebKMDNO+GUGiYiFPkMqJXd9oEpoXxRWBNvsjc/02q9jpfanIA0dfXmMcxSzzlsz/v4Yd4W5+oRcYp8d+3wiLsWLXXXxdcLtRmAW8ZAf22TEDhZhZw2sY6IqWTHLea2labsU6tMd00XrLE+nklAy/oIGyfOKKks8EqmsX6OioJbmdCWdtlo6qm4w5bvdEU/R0VALW5GZbt6yMyiOOEgdwiOqsOW5a7x243Wu/l1YqAWuGyMYxh32bw+5bQr67LNWoet3EF8+qq+67nfDLZPuuFFiVTXxeJ6WVJOm5dHyETj1JffETEVdNzE3TbeODiRvqq/x02HtTxQ89OT+Xg/wAy3GfmfKNYpQjwKozQEMkLi55wPb375PHAr02l74GW38EOj0uHQLIVHQBzUhmQaUFCBejNhTaGJgi9x8+vuLlaBstQ7vv76K2ld0NbDIVFZYBFKztVdF7HgrWitUfGhLd1SRiawkkSRi1UkDW5ZNYmHSe+P5U83rF9lj1vTLf8rIwlpPpxFj1T0y7hu99yo2SIR4vI/1QQ+tBEuvEXBTXWcmw5lQptOUTFYO/DtQxKXrSZ+NksEzEjVWiCtiYevAtUaElUPh0bFjh9u+t4/pcKhyRKiIVERufCmeRJCRvbKQ6SpYsI9ACAzMSF/5mlR9Yy7duilIEe9onB9RkYsdXfeg+nfvB8EUTDzhnhEhvgSQmLgBsSvdHnQVn5otLxw6Nb3Twr1gw1r6brDkGh+GJZTBZijVmlqg1NtRp8yw6GcnYl2ef7+5tfqc9IOu/r4zPcuDIu+ZJQfiY3v7ZWwaG3LepQaDs2J51PohTXAdd7uuugbuPOib+T0ScZr5sf9sz52IruD+mXlF6MUyTrSe0KJgpgo2KmqZ2DNyKhkUUrR7VJ0HYqO97frUDj+g/ofdZp2dyWuHWUu9/HAy26J79D0+dn6/kkhWDvw7UMurKWUBWt5tWbBWl3K70wyx+bX3uU99IY9U8t71KC61mTrg3XY0sdt0/d9d+0fM+4bWp7u5IGbNLR5eXVAm25wixbNgTd/r/DabW++vxRw6yVYo8i7d6GRUTFRAB3HicFalwNuDnW3WWu3iZyn5ULbrbHn4u5aWuKgNswBtbKV5XLlFS0x5BmRD2p1yV/WY+cdX1tXWydKUs+MYXvex7xwqJIRSVMFT/zh5aWERqOKQtvJN1yR6Eq6T3xRgLJDpP5HhWTsEUmS6w+nuL8Rq4bEkwEc5UHbg8rj2yS64+mOhsNaVGaZDqMqRB2g3aEghIIAsCwCQigsLwRKibePUlgWCQe4BcM1uIsaMVXuJIRbsfYrZxWqQxTUXBX5jDbn8y0eDs0sjE0VAFpsDTZBiYRDAeCsd87g1vcVufNENaoF2PTbiRzYiO1O5/H3nPTDy4N9lcGbCrQJT0bIqZublEl04kqGpBkAB8iB21GFxraVd4HUvXxHdIJBjeO5jWaBHEox03ECQLMcwLIAi7h/KXHPQ8sC4CCAtnBignu+EhDhCQj1rNHGk/tZEx+nNsxPrJDB+E1VC4KbXntn6W2oQFpVqmO2aC2TDlSA7ZKPHSYwbp+E4dDnRcKhOQVJ8hkRuGWVJp184xWpHmRL02QEoeSSzkVGtQ+++QGhonxw44c+7nj2V8T6JSmdzloU2PywEzn0UthrX6mtDSOjqCa33YWtP30XLIvAIsSDNQLbcrftyP5w24M7D/LcyQnhRAVRlQVta74cddkyvmYosPX9E0J1skEtGRfOSIvuoTn9yh2/Vu8dDja9pnxIA4DDrj6B1ZFId/IQggYh0SUnv4R5Q/jkUxWHrWpg64mQ6CUfOxThbzkUiN6xC8b3uuHH8BZV5cLbnRe6ztvJN75YsES+0wYkXk9iT04BRmJGeRUxPmtH/ddaAMCDf5UNbr4b5+fPU1mwplOsgdyUUuOwGZUqh1JMdygsQj0gA2ybwKEENnVdM9sCPE/NHfHsOW00egEici5bmdr4B7cmoC2tre8TBLV3DDcpesmWcP+KvZAqQG311ScAqO+Q90JYtHJgq2Wx3JzQaE6BSuDtzgu/Hmznw5v/Dc9329ghUk5mgWRt4dIcCYObly4KbrpV5j1CQ4AzMipPjgNMtx0X1CzXWbMdoGUD1E4aMu6PZWK7PyYokRm9llZdoVERWDvoHXPg/nDn5ahr/FqBsqJzFaLj0l5zh3p7glp9zQkl1FrdlbPqsGjlIVG1cOihkWeRC0XiMG36/ofS4dCoOGOpuHtyfi5WETbNh7fsECk7SeD8EjoFyz1P86DNFw/aeiEUCqTDoY7j+hfWoZeidfSrtLZlZORr7+N3YMN33x7CmgW0bOI+LIKWbYXPbRLJR7wwqrtGm2WphUWBskOj4VeNqKvmwhqAzFnaWeFQ5o5I1DI/lMepAlWEQze9+o7sejRo9TUnptqNPqWstFS+/LAypcCuO1lhUf771/SwaONDonFYAwrEQ3OLppJz8ofOG4ndvkqn8p03MbctniTglgkZaiWFTD0Vcdt6Fdai610Zh82oTDkUmG5T2BZFyyJeONQ7B1sA4IAQKxirZnl3P6CIu2zuxNEwLAqIg1tZTpsbGj1TAdQAJhgJK2/8mkDZij/41UIaR5W99OwWznrnNG59Xx3LtYipUmDTFQ4NOIoLVPJhT/ZedzxbPovQ4AbxZYEbkAdv2WPbIjkSe8AvEM2Sky39QdAHcL0SJtWl4AvREJtRifKBrWUDjgXYkR8MAIAWAenSANYci4JQwKIAhQ9vNHaLqyZJPPzJUC989gqMX3v41bdr7QpPuaAmq1x3LZpPtD7ZQnFVGRZtvMPGVnoCQhgOfeuon0dlqY/0XnFoA0gAbkA18BYHtwi0ARJLsQmOT5MaxqYf4ETBrVfcNZZiq8qX3prRbJbjUEy3HXQdgq4NDFAKUMsdqwaAEAcWsWA5gG1ROE7EZdP49VSWyzZ2zx3czywX1HKVFw6VKFukXcWiVYDa6mtPSjecUjVXtyUnv2R0151fW7frzq+tS88W7T01GtjS4dCoIlgl+94LQFuqgAS0+TrpRy8KnkZvGq9TadctQlU5bhtSyZLgJpCVXSgpuav/Uf+1Vnh8my6VCWvJm7v728QQm1GJcigw3aHoOghDoXAdNWIBpOuCmu0QdB13JqlDKSglwQ8LGrlJfORntLSqnISQDWslLVutoVJ+FdmVVwtpdav4gW5yWLQyYCtjdmg+aknFB3OSRcfOJfJ5T92bw7uqDt6QObbN7146WYLItBhp8qfGUf+1BgDw4F9tjO0v46JfhbMWFaXul4a544FRmaIUmOlQOLa/x7/TAYI12fzbVNkOcSfDeNBmRcar6VIZ0BZ12Q56x4i3t6zPVcb4NdGymrr28B/+Xk9FGTrcgzR2l4sMwi1+ELh9KklVhUUb7bDly/1Nt/kHyXBoPI+e8WyA+EJDbGjzVT28vSTXPOMnS8VByxzKxhQP3HpNyTBoHQtaG80uORRod/yrqCt3iQ+g5QFa13EBzaHUG7fmXsz8O1RF/zZ0KBsOeudI5FmR8U81hTRZZRm7KoG0z5wcaVvTNUqUVUXHryUUhkW/vm7JyS/u6bBoY4Htko8eAkDkKkDjmzKTEKTHs0EbtPny4a0scAOAOy/8WrB98o0vcTdywC2dRSkOyv58lXBhP+q/1uCOZ39Ve71Vu2sAzGQDo0pEKdDuuhcm4oVC7a67tIfrrMG7ATwJZjBTr1xZs5jLcNk2/sEvsebLZ2qtE0AjBpk+/Ie/q6Sdwz9zMnO/2iEo+cCJVk+5TxobFm0ssIUSDUUq1tMAaAN8cHMT74rcd1S3fHjLAzdAxHXLqSCvYo264zm9D2tRVy26xIeRURmilKLjAIT449TgPfxxbe4yH77DFoxfS07LonpnipYGbV/Kg7aal/OQyFEFqDEhTbe7plVN7JNeVQJshcav5fDa5h98eB0ArL7kraPZS32ItlEBtIHXRzfvSTdcESTfWRK8pVw35ZU9Ko6B9rkMpBlVJQoX0CwCdBzAClw1D9QcbzwlDcerxW+j1muf9SLh0AqU0/bDr6oC0k6JPCtwMBo2fq2KsGgV49ga6bC54dCIhOBI5F6jGReZKqFNoI9+8sk3XBGkVAJvP35JZt58b616gOsHdy0qw2xGVYhShLM/HRp31Bz3GuQkwqB+ubCOcgavleKyvfxXWPOlMxRL08ynUmUl9NCrfqtcVlSHf/YURhcrGq8nOn6tsORbaGJYtJHAxpbIL7p+gjYEQ4H9LD68lQVuAHDnc3TCWzJXVM39dV4nrBkZVSnfSXMs31ELIc1x0u6aP+nAfV4OrPmq9n6jdYVD06oC0gAP1Aqo0vFrVLBsn//aLR3YtC3nwYCbMBz6/yQtzmJ2fjXQFiYms1ThugHq8OYrf8mV4roj0sd+khnDZlS2fActmAGKcD22YDYoECwzE5Tr4XMz02Wr5TW5jT70yqog7dRYu8nNTDV6/Fq+lpz84tFdd37dDYue9GL+vUULqOywaA85bNAYGs1IFHDZmClS0IZ4aQVo81U1vOWBW1TyEFe/jLtmNJvkzvb0XLRE+DP5+aWILgBSjap12XgqLxxaBagdEUBaFWKcODJli7SrWU3E0sYBW2r8WlJ9AW2M0gyOSyYmQ6RJVTLeTcJ1Y0n0QyByFPvVXTMyqkLUfwSzPxPpNJJGMy+kPaW0y1bt3Q0eeuVvymgtpmKQVhGqlDB+jV2XegtnvmMKv3z/sHJ53WocsImOVdv8g39el5dHDNpEulERtGU3FSSKvJwA3ghw54UVwFvOTFNZ1fHrxrhrRrNR4fpqNHTc6u5URJW4bBpdIVZVlUDa507L7AXzJRYZUlZRqTLGr+26KxkW7Q2VCmxl3I4KQOyNyR6/Vv4kBGaK/2tUCGA40AZec2JuWzT7yTdcUSq4AZzFeYHSfpTfadw1I6Ni6uGxaEUlPmNUPRz60Ct/LdUnVcVBTUQKb3qPj1/z5Y9jC/fofz1ljmNroMMGFJ0UwK2rSmgDhdgN4/3SSNed67apgRtQE7xF1bDoinHXjIyaq/JcNr3h0Adf0QRIq2ssWJ+NX2sgmzYK2C756KrIM33QJsZcdUMbp+7cwyAeJg2yAzj5xsh4twrgLbgZfRSeC9apSwbWjIyaL93Q5rps67RARhWgdsTnTme2nVIDQSOlysavFa+xSePYGgVs6eFfbAzZ/EN3/Nrqi98y6iZLTELIyddYaAO/a9JuW6LOKuAtfjP6F2fkTKphVpyRkdEsUXY4tBJI+/zpjL3yaEIZW/LV0Mj/6j2QL1Zk/Fo6YclJLx7dddfX17nj2K7oqXFspQGb8vg1WWONAiBiExUKzRxNJfEpig1tkJyMwKi7ZHADmghv5f5cNO6akVHvSLfLJnt1efAVt2lrm6cjPUiL9a1O16wXHDtRVfRayhrH1hiH7eL/c8OhTNjJQw+JeKBeaOPnZbKV1GSEjH4IhUkVwS1SwIe3ckOmcs5bNL+RkZFRET348lEcdV32ggMPXlk+pAHAkZ9/mrdVYFxdoVkkZvxaUGOi2qaERRsDbFGJhkZzCvEyVgZt7BSVECnS9ee6bWEmKXCL1u0Vqm68mwtjciFTdRl3zcio91TNYrq0ElALIU1UdYVDCxVjVpJbl0RjZY1fa5oaCWwAH9pi49fyC/Fq1wNtiCbLQhskQqTMBjN3szJJg1u0fq9gnSFT464ZGRnp1oNXhi7bg1eWP6TpyC94kMZkAsbORoRDa3TulLPwy4bj2L7RU+PYSgE2XeuvsaFNuhAvY3FoSyXLQBsUQqQZbSiAW252XhtewarhTaeMu2Zk1LvS7bKVDWpHfuHp3laJ9NWT4dAKVfGgwDLGsTXIYVMdr8WqqrnQhlSqbIiUX1NO88zyQpyXVYWnqsKmRkZGRr2gENIYyuAFflKRcGihavQp1Xbzx681SVbdHQCAi/9vpbeVPlLqx060ZGSAZ2aRnPpS9C7zsaNg3m05V5x2sptnZKSRLUVFKjj5hiti9zU1MjIymi068gtPz4Y1rsoMhxYHI7Ua2KXExq+JtajYgnSNZ75jqkCdetQgh80XY8SXZ5ht/uG/eOPX/mFUbOaoqD0n47SBnyFVVjJEquS2ZfQrEcIUq6NAyDShKm5GryITDjUy6n1VM/lATEd+8RkCkNFj4dAGO02BCvRxyUlXjO666xs9NY6tgcDGVvp8FICxUqAtJ4PkZASkUn2nTSO45STxM/c/vBkZGRmp6KgvPgNA/GoppDrDodpVZPxaheHQisevlSXtwKZnwoE4ZDUS2lLJ2bSk123LaU960Bob3qSqSKhOeDPumpGRJyI5Ub2Bqtpl8yHNl9hwGhFVFA5VGnajqStUsQv5VeqrSzPL6Z54ULvDFo5fS6oh0IasYjLQlp1fv9vGrzWWxEnOrs9/VhzgjPNmZFSviHd5IYS4DxRz0/tNR33xmd5WuY6QulFVgmOkk9CUilXovkmUPfMdk/jl++cUqL+Y6p90kHl8wsRHfuSOXzvsuf8wmi4j8AZJnQSJlaYF+8hNlrBj2QP/KdQmJWTXmkpW+vUVPmhqj1yVZU9WMO6akVEoH8xcUEtDGiGRtAZbcWV9ro/64jMjsJan4uFQnYXESxSEmzqjixra9seu7brrG9m3u2iIanfYAOQYVelEtmFWotMm1Edk1ysRIuU3V6LjlsySky2/cFhJ3ucq2Yxx3YyMqpELatQFssBpAxvgotfDPtZR17EgjfkzmpckqdkYDu3F8Wv1j31rBrDliv1hUWaWUqBNIIMkZPLxqsj4tmjN7Npls4m3xVI+0BkZGekXAWARwIqEQS0f1jxHLXDgouX6YOxbrrRelPIHb5lwaLSYWFntr7wHvoi0hkTVJhyoj0RkzxwVbVImPCq6VptABmaItI4wabJ2wX6X8ilhP+7S6K6ZcKiRUVoWASwr/EuIB20ALIvE4CwZGm1SmFTn5zt9D9G8i16Z3/QmHMprXjKhSKWFpOvOT0DNDtvFHznY2/KcJgXbTOlG8UE2mQY1ziBlZskvU06YNNmCL0HnTSC7kRFLU5PjeM+bLgMQgQLEw3ExYEDib8Y51yCWqF3RY2pZgG0RtCx3e8AmHqx5fz3HzbIijhuQAreg7ll6oLX9gG9sOLRQsZxKejsceubbJ/HLD9Qz8aBBIVE+tD3yo3/1Jhz8PXPB3NqgDVlFJcaLSY5tY+eIgFtOs2KSjIcaiDNSFIlAARCChb/NGldF/EsF5xwzp16o6LGzCGBbFJYHbbb3aHkgZ1sk4bilXTYAs2Q0m4hkojqFamAULDMcqh+qCrOtWtZcLT7pitHdd31j3e67v7lu8YkvavQCug0CNkDMaeP4TEWgDanCmQW0jmtjZikIbsEfHa5btDVfgpVmfapyqrjrom+KtSEgEw5trqKwFgUzK7E/ALgEtLl/0yeTwYlQSWCzCNCyQ6et5UGaHTw8cIs6bt7DrYck6m/G0da5JtuDr7jNmyHKHIyS2FCV/lBr74dDBSouJRwqqJrHuTUM2CKqEtrYhTM7569BJh4iRXYmZpYi4OalagW3ZKu+FCqv+cQ3aoaSUBaFChJ5uM8JLBL+XCKx7dpeQqPFAuIQylxYa7Xc0GjLImjZJA5tHsxFoY83i9QoKYWLnAmHylQ266QN2PQNrIvQT8Ohzf1fNEQq2BcuuGWXEwa33D6qyMRDjdQUhbVgsDuJDoQPIc1/HgJIIlxnzrmUkmMA/WNre8eyZQMtm2DAJhhoucDmO26WB3WBu4bQTUuFSPvy0Ge4a5x0wWoEknLq7rdwaOEW8jLWC4q67nhQm8MWTjhgSRSyZKANYnVKQZtbt3yIVKAvCuPbornYOcsIl4r0JKnshu96rgmHzhaxnLUAKizAIpQRnks7PkC/QkMxhY4YcUd+WP44trjLNtAiGLA9p81mOW3hrFErAW1Nkt6w6K9Tt6IKVEY4tGCdlLHFrrOB4VAa/FekgsqarWviQXNDoh75xCcc8POl9jK5S3RcG/WyFQiR5haXGGOnCJ9irpuXo9KLr7G2jVxFx1aRANQ8WCCRcVWERCDOA5GI2wY0EyDqVvL4uIBMvGPrAZsHaD6wxcOjJHhPgjXbPAAMbmM1Kx1OwfFnSu5a0baLiEb+11JV1g4NdeoQxeITXzS6++5vZk88aMDXVm3AJoYrokeoDGgDZGeQuv9X4bZJlEX8KDYP3oxms/zxaTHXh8AbDB/u87cJ8cJ0lgsIvjvn1xXUW8uraaai66f5YOwDmO2HRS0C24c1PzRqW5EJCCS2LttsPL5aIoZyLSklKxUuh9D0VS1bS4PCoTpVo8OWCCXmZ1dyrApDG8oOkQYN5WfkgNvdF38bJ/7wcsHe5bWUgDeBbjVVJhzafEVDoBZxXTUXILwB8d62HQvRuX+j4dQQStyTd3a5PdlKrXEXATZ/nJoPbLHxbJ77Fi714c8UjYBbA21NnWFRtgTdNZn0ksOhm15zBw7/zCnFGmlAOFT7WLhm8Viu6gM2z8GqDNqQTJJwz5TGtbkNiodIJfrEqO/ui69nZuWBXL7rFslVIcDd9dxvlVe5UePkfy4tQmBbNAiF+iE61+nx4C0ACD+/79CFY6oMqMWVnhxAYiHl6Di1aHjUhWUrkhZ316K3q4oe9wbyWyH549iU3LUywqE5kw02vfoO1ZrRu+HQChy0hoCdFmBTniEqFXb08qlCG7MpWWiDeH6v/pTblluFeKhT5CRigVwS4sTgLZKzTxw4o3rlOz4xh82KOmwIB8J7btuATWDb3pg2m8TGv/nOj1Go6OHwj40/Di16h4MomIWTDiLj2AgjLGqON0NF3TXxr9KHX327cN7Muk04tBLpmClai8P23P89KHxCAUpEfbbi0JaOcMpAG7OC3EKpII3OMKmCsty45OktB3CJEjVezE04tDfkO2T+bNDomLUgPGeHsxhbEaAIyvrrhCEM0RmQiCvmhkUmC0SBzSJ+6Dn9sKxo+Ln5PmZ5YdHijowsQjz8h7+XLFGGZmM4NDvDmW+fwC8/MKKpR2JqzCxRVnD0kRv+zZ0hetHfjUZzFoE2gBXhlIQj6RCp24b8TFKFvhWQiBuX3wv2GApm6aZf9Y1KlwsQNFiuwyYkGLMWjqcCBlvREGnU+YnOXOzf0JwOxWeLJl22cJxafGZocpvE3LXZcMyVwqHZNXHTK4ezxIubzeFQ7kzR5ph0DQG2gMHKcNrAzFRoMkJQAbvuvP7Ih0mzM574gxcwS9x9ybcl+sZW3tg4uWs0zXx6F6cto/6VG9IMQ5vh7ZG8sKgXBh1sJQfEu4Pk08Dm1duv9KCo2AzaCLAREg2RRiYXRCYZhPuavw5bGXroFb/GkV98BoTDnQJf8A+/6ndFu8UVe3JBmdTR1HBomaqH4poBbECJ0BbJm9xbGNq8/5TcNkA+TBo0KpQ5BXIEuPvi4hAH5Ltxs+RablRQgcMWWRyXkMhYKitcFywMjbp/fdfHtggAGtwFwa3XnIEsxWeMxkE3CmQhwJFYGknVM0vgrcD380Ov+q2+fiR0+GdP9baKAwS/hl4Nh2aAZMFwaF1qDrAB9UEbkkkS0MavRKSgYphUOnNQJIC4RDEdICc6U7Xsa7sZv9Y7It4n3YeC5E3IW7brpNmJWygNBDMY/dtVhQ6QUSjW4YiO80u6bSznLQA7sEOhTZXecWz57tpDrywPzI4IwCzaoqjyJhtohJMeDYf2ipoFbEAM2iQLuMoNkTKgzfuv2Lg2ZiWiBTWAm3ABZrETf5gOq5bpxgH8JUeMZo/CGYcAAYVFrNiM0Si4hSvyW8F2uLwHCdw5o1C8wxF1yGJj2yITEligxqpzth3yh175m1LrP+JzpyX2CIZiRbKqKLPOPg+HMuusD/YKA5vakh45DpakwRUroHUygkJnCrht7v8q49uUC8SLJYqyIA4oH+SMZpNo4LJZHh24N3r3ACy27ES4DlsrMZsx6ggZhco6HoHTFskXc98i+ZKw1nR3TbfKgLQjPne6t5XzFVoqH+RNNiip8ZrCoQUq1KKiS3tU7rA9938P9LYEoE1KTYI27z+lbw/O+DbIdEHRdUsW5RQv040zml1Kh+fCddn8WYzR2yj5Y9aSD3+JiuQYKyO+om5kdGxbNI3lqkVhzRxnMR3x+dPjOwpCA2Vs5eXU2X5WneJ9E69TIkGgOn3+3xlvn8CvKlzao+aQKB+EHr3x39cBwKEX/e0oIPqLThbawMzEH9fGzs9vQtVtc9srDm7KhdLFfXGqKduNM+pf+bAW3fYdt9gAeH/GYnKxVzsexvPrMYor65Aw4S0Z+kzUYI5xWkd+/mmJPYpAFSRLwIV2CMubbKDYoFCxesKh4dIe31q3+IQXMm4CX+/YtwaMYRMLj8pNRIBfSIBTZMa1CfSXWxHkykUq8MEt+F/JQCvguvGqEaiuapAzEw56S9FTJzaeLfKwYtvhemDxxVyTDpuhCZ6yw6SJ54wPdy8d2rIW0D3yC0/3tlK2Ur60uWuKOROTDcpBkIKgKpVLT6niZctXA4AN0A9tsULK0AZkhUghUnGiiGqYNGwzNjlBsSva4I1VXVQSIGecuNkr1ozDcLB7OIYqPkEB3oB5klqOwi9vJK+s6+tsP6YhpMlJHQFqnmwg2nbkqdZulBEOlXEs8+qqQdUDG5eNSoY2ZFefFyIFNLhtfmXKbpvfpi5wixb0pfGqLHJWz/IvAaNQJPJIp4XLf6RnMEb3h/mNimm2A1q+8iiFkUBz0iWSi0lgskFp49zEQFS4eZljWkj1u2/1OGxFoA0A9e7iLnY9kRnXlp1Jv9smWY7RLnecm3LVmt03meaMjDwF64Eh6qwRE+osQeaQlifdlzfmgH5mI3nhUI1K1dk8aBLiRJW6K/7+sqptLqIidqd39JVi+QUHPFLKS1Z8s/kVSlVEveOR+rFRqHoKDZXkSscttIxmj+IQ5z8nQWg1thCseeQ+jMQUX9pDYYyWlLtW5y/ZPHeNnag12FjKy+/tcChQJ7ABNUCbzMnAh5SAsyTK5DelB9zKg7dkJeVCnJGRkVHjlXEJLM9dU8xJ4xuVX73FbK4wq3TG5jl7ulUI2GQXzX3u/6xI7yxyHAJok6kkAm0a3LZmglvYB2ZtWnmLBXH1nNxmhqiRkVFS+q8LdbtrshEjnaLMp8xQraYmBBLyqysxHHrG2yakiqndbMBVDQ5b3skMPHrjf7hrsF34N4x1UNhllaCN0x12/orCpEFzusGtCnjjVZz1MDIyMupBNdJdy6sgz12j5VyWC5ojFXUAAOCvv7b7nm+tE6uluu+xmkKi+dAmkJDKIg9tqZ8HYg3xatPptsUq1XVCpOEt9cOvcpYy0GZkZNQrUnDXZNILu2sVXk+Zv/6lChTIlcyo6XXXfUxzVOMYtvKgTe7wRqCtdLetILhpHYgakpmQ+2YMMSMjIyNXMu5aw66b6u5aBf5Sj4VDq1a9kw7KgDbvHVKCNsFm8jJmG2MFyScAtzJM9wz3LZ7NQJyRkZFRTOW4b5SVLuME0Zz0siVETXmhWmb2MjJL1lLtMa10HTYK5rK0zL0yNbCzUS+3TN1w649sCpfhpVLe1HnhRjKapgXXcsusPLFFGFupTHGZJQOMjIz6TWW5a43+8UuZT5kwWblmRzgUqGHhXD60IZ3CzCwDba5nJLfqeaR+YZbMzsi/U4JfFqINcYr7DRSoR6yhyFa8ncyXZmRkZNTX6g13TT0cqiihOlP0p1IJu1QfhUOBmkKi2cFEkcyCsbjgPFAJkdLUpnAZXg4/mqlYXqwLmY1oVDwuGv6Ti5re/bzvlN5TIyMjIx166JW/5ab1r7uWkPQLFXtxauFQPW3nZWtCOBSo8ebvfE+KA21cCyfHUQoMLNkQaaJ+KbcNmZlLddxSjWioS65hgb36+2PWYJs9iv4uob4xQCkoJQDxf2iZeHxSs/muBvNOOAVj99xRUu0Vumsy9Wtz1yrAFc3uWr+qWmBLQI8UmhSBtkg2tRAp/MLBplQ5Xo5KwC1aF2oAOJbMh9AoWxQugMXhjIJS4V9ORgllGe+zGeZ0qDJ3rZcunUIxyXJekP8jTnvbNR//ih02Gv7yTYBb1dAm67WpuW1+ZmQWqATcYtXV5b4ZGfGVFUKn3k+tEODiQAeSuD6TXvpmq17Jq1/02Bl4k1E5QKLv7NXsrtHkXj09LSccqqfxpoRDgVpCogE1CUAbYy+XXwTBpnCI1GtDmqPyKU8M3KQaze9S49w3o9kmN6wZ/3z4oc4YnCXCoK4LBziO95mxQk4jhjqywSsBtCRx7HPLGwUq5q5JAB8za144tCYJtZ+iP5VK2KVyi/aeuwYUALYi98MqDG0Zu2tx2yDWpGjm/AumZtctVq0BOKPqFL2IxIAs8nBi29R9OIBD3M8tsd2KHIcGoEaacHWtSf4nlsUC/vGhNHF9iQCcfzU04JanprtrRRtju2uChQXSZXLJZJTOLKnida+//kp67OXXSX+yKpsletF/L0/sYdP1oz/+T/c+os/569FU3qSKknkQf5GfR5oK3kifTPkF8tfIpRCtS0mhxRHpyOz9IjQqR9GJzVEHzYezFKg5FA4Fug51H133r+NB22x/dBMPx4Neh0aPaZg/9hGHfzWksffHiK1mu2s0p0sNAErl73BNveAc18UnXO7dT/T61P1EWTrjbeN6+pOj2maJuvKvEER9kdqiTlskq7rbBgSOIaOLQmXzcgm7blIdkBNNbUSaMj/DjeQ0NGcu3vJfP6m7G7NCEzf8IYjTBhBeQwghIMQNORMaDyOTxAStlCM369UH7pqMZMhUKCZZzivt53AoUDuw+aIpaOPjVjzl0bc/VW7XjErV2D1198DIqP/V7boWGyHwHgSE0gDCLMudtUEj4Gagja0nP9Spuwue8t4M82axtPjNnhumBGH1kltDgA0IoC2+B4DEuDYjIyMjo5Q6XQegDghcV80KwM0DNG/8HyFAMO0WaWgzMupvNcRK46hBwAbwDhYbzwy0GRkZGYmo7TlsFnHBzLJcCLMs9ypKrRDifLctCm2+jMtmNOvUIIZrGLBFlOAxPrQZGRkZGWWp3XWArgPLIi6YOYBFKCzqPgcI4EEcHJqCNhDjshn1kXLQgW8d1asKgU3BEROCNiMjIyOjLE23KYhDYVkUFnEhzbYILArY3loBFJ7LZhE4EWgLlgIxoVGjvlb9QJan6u90IPyBZ88glZ6IaWRkZDTLNd12QBzHhTSLwrYIHArYwZIeFDZIsPiwBZK6g4QfCjVhUaOeVimTDaqBveqALWA1WeRKzyCNVWdkZGRklKmZNgWhDixCYNsELQtwLMCx3btIuEtyutdm4odHvRmj1LhsRn0vythSKl6qarz5u6TbxrkHqZGRkZFRtqbbDgilsC3Adigcm6BlE9DwvgiAN4PUIRRw3G3CcdmMjIx8VUci1U86KAJtjNtZGRkZGRlla9pz2Fo2QcsLh0bvbkAQXaPNvd2Xf59W22ZM9zIAZ9SHaupkA1/1zBItBG2IhUgP+cCyIJVfCycls1mFK1Fk1f/i1zFGDVoujvqusCT4T133XHqHhp4YGRllabrjgPi3qbIAm1K4A9YA0g2BzbIAxyFwvEusD2404sDNdi1/q534Ds+bciiCARXchiqzm5T5VChQKHFnA/7duNjtZ+yINC0xvkzm2IqqQp6rb1mP2FA2WduMHyIVuTsCuw9SidxuuUX8O/EVAbfoWUDiuwpdNJNnV8Eeck5Wc8cqI6PmaLpDYfnAZgMDIO6abHA/ohahsBzA6rr7HerfaNodw+aTmplwkJSOb+tmwlpu+0GSIDCJwpp0uqBkqhHOW637Vv86bKnJCJIFGUt/ACxOyKCdRoMbow8Mlitet7YK47U2x002Mpq1cicd0CAUCiCANWIBluMCm21ROA5ALRLMHqUgscvsrJ94IPXFn+euNfcCqbtnpdSXW6k4DDZ5soGv+oENKDAuLR0iza8yB9y4/VDoZGngBpQDb8kKtVZsZGRUk6Y7FJZ3r1AKBOFPywEsh6DrUHQdAscDNIe6s0eja+dGZ4saAdq/rY27xthVkfumVGX1sN2chXOVoc0rnDGLtNYwaayYLnCLVhrpj3Z4Y7VVSgNGRkYlqtP1ZnyCBvcStS03/NmyKajjLpbrOMRz2FwnjVLXXTOhUAUZd63c+gqHOHvhnYirMmDzfwdkokqKrCXHtQF63TZOkj5w04Nu1cIbq82kzJXdyKhJanddh40Q4o1Vo+h4C+h2uxRdi8KmvsMWums0cfU04OZL7StebhhX3e6aeFG1vGW7awrvUVnHQJMqD4nKjX9QASONbltOUnFw8y+I7hPNo8fAhLfI7vLUK79XjIxmh9pd964GFqHoEqBL/DAo4FB3mY9oGNSHNsANhZofYZKqe+ZiAYn7TmLptX8b5HQgzwdVqrQkWXU0SkVerBRpcwrnAXwqJeMXTe4vFUWaD4p6v2zlaxFsgObu7mWN3XNH3V0wMmqsug7Q8QDNhbT4w1+TLbk+G01cNnpVeq8Pal/mWo5f37hr6nndr8sa3DeNxVVVC7ABVUEbZUJJNqfUAG6xojTyT7c4lFYjwB3/3UuqbdDIaBbKh7Twbzhj1HGo567BmxXqKgZruV+Qs0NHfO60/Ey5h2r2uGvlpQuqFLis7/2pDdgAQU8pBhEqRKHituWkVgJu7pNywC3akADAmWu1kVFPi1J3uQ6HuncvoEDwnALB7FE/bxzWauhwr0pokVzVuuMbveCu6WYgKpRXHAZLfLdKUQ03f2clCYxri5XPqIxbGFAb28ZPzUsWyMBX9JwhUWgrawUk1knKOFAZWYyMjJopJ/K7lYLCocT9MUgRjluj4bg1ePmiz410yLhrjXHfVKuskedqvPl7MkkF2sCvkFsBwJtJyq+tRnCLFgcqgjdWw2GbuVkyshsZGVWvwEWjjO1kXmpcNSWVuYyHcdcE3bW8eou6a/V+MGq++XsySeBgpNhH1m3zyjDctvzadIFbZqZs1QZvrA4klbE8ipGRUW2Khj1ZXJEMixrJSvLrX8ZdE4Y1dfWPu1byGVzzB6S+m78DxdyXQiHSSCekw6QCOYRen4aDUDu8JSVyNhvLzcioDrlQFl26w7hp2lR4XJWmTjTBXZPJXqm7xkmmzL1SlVb1Ear3Tgc6QqTw61AFINUwqUCOqsAtWg2QgDe37uZgkvl2MDKqWpSan0qlSXaiQb+7a3IvvEHp5RbXoYpniTJGTGQcBMocYcGpVqTCvEo4zeX3IieH0MugohnzlaoqvlRIA867UmTWYjMyMkqq/usCZW7m7JRvo5C7lvP9JdcTrdLtrinnzayimm/Vmm7+nrDWMkwm/2BU7rYxilfjuEllzFfyPCKs06tJDpyRkZFRj6gREw00NFE4p4K7JmW06EuX9EMF06tRjeuw5b2BySSZYHf0icqB9sqV7bhV6bqxqmQ6cNW7cMd/5+IKWzMyMjKSV3rR3BJDoVLqc3etrAIVO3E6VJPD5kvOSfKhTc5t83eoeEglO26CWeIZhTKLi3Uiclw4zS0bGRkZ9a6EfnAXrTvPXcuDNYEmCucs2V3TeBsq3e5aleFQoHZg88UAqgzGEr6BfKyOImHGCsEtJ5tCZnkJQ1y8DzI9ufeyH0p2ysjIyKg+PfyHvw+2j/jsqcw8Wtw1mpMuJba7JhSylXSgGmJCiakH3TWgMcAGqEAboOq2xXZISBe45bTfJHhjNRNVZMwgK8t9l/2opA4ZGRkZ1aOHX307c//hAchFroYFv/DLcNd0tK6cLuiuUUDOXcuBYjV3La/lammuQcAGcN/cTLaRcNuABLipAk5RcBPPJceXyeNXQQDTa/K+FzQDzMbuuQPzTjil7m4YGRk1QFXPEN3EA7nPnJLYI+auFcOBou6aYOv97K41TJUB241/vRMX/ucBuflWnf+Xo4//7H/XPf6z/1m36vw3jQLIhRZht82vS4vbFimvBdxycioZaeUAXFPgzMjIyKgXtOk1d6T2Hf6ZkwvUmEdJbFjTq/511/bc++11ALDouMtG+SXD8qP/NJ9bl04pA9uxl19H1l9/ZbWsKuS2ITuTX08sWzXglt+CArzlV6pcsGwwO+7bz620PSMjIyMVBTNEKeWGQ2W16TV3Mvcffu1JblNaWolr1rtrDdGxl1+nBBsV3/zde2uJaF8ZIJXrtrn/q4dJMyoXrZADbnItSPRFeRhbWPC+F9wgU1BKSTAzMjIy6jl531/JCQf+VZQXDpXVptfeldq32oO4oMVZ766Jd0WwWUnVg6k13UuUSkAbwLTWBNw2QCJMCiTAreiNTiEEbpxkpZyp7IwiBsyMjIyMJCVw+6nDP3sKM4EVDpXVZgbEAcDqa04UrqO/3DUFYJRKlyhZ4UGob9KBErQBkndpF5+UkKqvqNsWqYNG6tDiuonlvu/yMuHsIqE+1CEz8cDIyKjaCQf8b+1wwkGYhxcOldXm192d2rf6mhMyuqWDLvImRPS7u1af6p0lKh0iBbhuG9K7w2QJty1Vn0ZwAzS5bvHc911+o2K/8uWCWX4f2Gom0BkZzTYRgr74wmqSuIczZwA8kJhwQMMNVjhUVptfdw9z/2FXn8DcH++HoDMlcy5pP+/KdtfyUDRvskN5asayHjrcNn+3rjBpqj4d4BapR9B109GiqI67/iLNjcmdzcd9+6JSQ7ZGRrNZBAAhBIS4l1v3ueSldxaKt0huqAJf4DS+ER+r5ooXDpVXXihUR00FYagJ7lqDf9hUCmyZyEM9OlIaNK8SJs3JxK1PM7gBma5bIqcWnjru+gzXjHeymou6kVHPKoAzsAEtmm6UL6HxYHl5aE66Jxfi0gPGWOHQYjLumpS7VoNqcdj4RpjqKEaVMKn7f3FwEywvUjmN1KUJ3o67/kL1bvEaTqqBV3kzjs3IKFTUTUttJ/P2getW5vi1IqFQpXo534vxCQduBl44VLFhyezNcdcal1eTaguJ5kQvFWtEutbcMKn7v/T4tlhTuly3SF05IdNkV469/kKJ1pNnWsF+i5y4Pf4FYGTUy7IIYFEf0Ags4v6NhUi9bV9uem1dbqQo71nBUGix7/6w9OprTmB265HX54Fcf7lr7Jy97a4BgFVn4xQ5h0CGuGO1yjbkhkmp7BuSqlegIenKaWyTpWM9Fy0nm1hbBWpRaiLxyAzXGhkZKYkQAsvywM1ywc1/ngyHpsBtFkMbf/yajlCoiFSjTnF8Oezq4zMyaXIBi5Q07pqQKnbY2E5Upgmma2xbxu54FuplkWiQGy7VdaWL/mRK1Cngvqn3hHdW9sYV3IRFm62pyXG8502XAQihIA0P8bTY34zTcLZCRghirotmW4BNgFaLwLLd5+5+z2UjgGURWIHTRpjHl/TQAS0rHKo/FJrn2yhAYaqIDrLIc9c4Jol4zRpy9r+7BtTmsKVffNTTWXXeX4wCwOM3fWRdkKrstjXBcdP5ZicsKcEm9PpnWTaZkZGcfEDzASKADt8RggsdtgW0LO+v7abbNudhzdKHHd+2IvtaFgnSLBJ/+GAc3fbfm+B9quHcaIoo75nsJY/GN3KLZ4eg1IrFMomTlfrVPe/LSQKmKnDM9tz3ncz7iNb5NVfIYZO9n+iP/2Y3nvMfi71nbF9Nv9vm14p0zZmN+VkKOG6xJnW7bozGBN03RkmR7PL9EdJs/howig2CRwIcEAe4aH5/2/2bPodm61nlHzsfvFyHjWDAdiHXton7sFyXzXfa3Ed0yQ+SeXxnrwqEQmXbUYTBPK8pL0kuY0F3TQv81OuujX5I7sbvqvcRBWpfh40fIs0sQ6EY82AQmiBHKYEbs34mzWlS0h4vBnCCxQoq3epx11+obTFgExZttpJQ5jttUacndH4ILBJOECKx7dpeQiMUDRuHx9Edt2YTYMAmaNkELc+lbHnPXScuCm4kgDUf3FjtNFU6w6H++DVtoVBZdy1TeaFQhTp46WW6azLpAlEk4WqryFuCqgc2JiAJWF2peryKpK8gGW4bY3e6NI1k0+W6Sdal1CikAY5Ti2xxIyOuYiHQSGg0HCAfQpr/PIQ8Eg/fzeIzMhrCjIaXg3FsNjBgh+Dm/nXBzbIIiOUday8UHTu+aD6olaV6QqHqhCTurok3IBV4FaSmMtw13eliWF0twdV4L1EwoA3JnfkcVUaYNLPBaDaJddxy2ygb3pJt+E/VII5RG1Oz9DpvJCiWs+YDmzvWiqbCdjH3DezxVrNN0TBxsFQHwuPYskJQ8x8ti0TGtRHveJPAnUuuxza7Q6NNCoWy3TUhWJPph66q8toQSTfuGoC6Q6ISblu2B1c0TJrqhDS4uVkVwS3VThXwxmoLbIgr0A3Vc/zY6y/EehMW7XulHKEIPPgTDfxxWFZkwDwBQCJuG2CADUAslGlFJhe0fEDzga3lPloxcCNeGDW9NhuJtdXMA607HMoFoF4OhRp3rcJ0/WrIvUSRASzpvdluG2oBNzerIrhF20m1VSW8sdqM7uK038zrt1EPKDpIPnB6CIKxVv4+f5sQzwmyQiiJwkpQby2vpn75kBV1IW0SumgDLQ/OvHBoq+WPZfMetu9iksj4QBKrfzaI+1Xc86FQidpkDoJ0v4u6a5xX3MfuGtAUYAMkwSgna5ngltmwnzXM3Pvwxms/uVugP7PkYm8krmgI1CLemmG2D2wk2I7PbHT/RsOpPqgou919ovTtp8JQp22FTpsdDYvaIbT5ExWCsWyRemYLrMUlEparNxQq3Y5Iujo7ZrYh7a4pd6Jsd6wegqsB2LKDm37yyvP+fHTLTf+3bstNH1m38rw/H5UPk6LA+Da/drBbqMp1i7aVaq9ueEtK4AQWBTtPx37rQqx/oQmL9rOI958LFDRc6NX2l6LwoY0EsxujAEK8skAYCpyNSt6ZwF8AN+pEBi5aZJZoFNaiD/+2VZbFPp5Ngzed4dDDg7sbFBy3VmYolJmS15cqQqHFapdN1+2u+WuwLTzu+aN5eetQ5cD247/dg+f8+yLkQht3JxHYm8hBUeAKoxfc3OyaBoSR3IQGKv/sX//CH1fQD6O65bs3MYfNijpskZmNnts2YLthO5sQWLY/QH62u0CJMWb+mD4/ZExCwLWI6661IiFQ32XzQ82By5Zy6+p4ZdVr06tvBwAc/tlTwp2ljltTsLNSUUtNLl/hqvLcNYnKe8BdG/3QgoJ1yakwsMkunhtKgnZS5dhuW2ZthcKkOS1Iml3KS4MIt9tLABfKgNrskw8T/mzQ6Ji12KzGlue4RUJ4QVkrChah2zZb5QMWEB/P5kJb0m0LXbdgPTZ/tmhwLCNj2HrkWqJDm159BwDg8M+cIldQ6tuwglBoZe6ajlBofe5a4bwCKrJoLtCIMWy5gU1GFj48VQdunFakx+KVAG+pqlhnXTMuvFVCmgmLNk+uc0PDe18SEoxZC2c0AoOtaIg0OuYqvUK/X+9sVXxNtvDYhM6Zf59RN+QZ3PHAikw4yHDXmnZsy7p3qK9NrwnrD+FNPFxafyhUop1SYabZ7ppYk/XGRxsAbIAQ5TCzZINb/vg2FLz66HTdwv8Lw1uyfWZ19UGccdKMfLkhzTC0Gb0vZssLjw7YBIOt+JIU/sD5NLB59TaNKioUD9jcMW0hkIULE4fA5oeVwwWKZ6e7xlMc3k5OZ2hkKFQQYjK7UxCEKnHXBBqp0V3ToYYAmy8Vt41fTsjsKhvchDuSzK4R3qJ9iKpCiGsKpBmXrVkKHLbI4rjEAwh/RuNA5K8bGnX/2hHYAGgAGW69sxsuwnFs8TBxcIuv2LIo0TBoHNaSzmXTVLa7lqVNr7kz2D78MyfLgUNfhUKL1Z5KLw2q8l5h2WPfiqthwAaU5bbl1KgZ3DitSbpuYZGwoNYLpzLEcTPH1BRIM2qu/NW+AvfHirpsXujTDtcNC6HNClfn92Y1+gu+zkaxXnZyPF/UcYu5ksE4t+itqNJ3OojWZRRXDN6uPQlAH4dCJRqTZEahNtjV9b+7BtQFbAJGGkCx8ll/Nrrl5o+u23Lz/61b+aw/H2VkcdU4cIu2xmlRAd7cYlF4kyws1gBbzGbYmde/8Ce6elOKjMvWHIXQABBQWMSKzRiNglsrGNdmBdvh8h4hdMxG8V52dMao/zy67IefnnQno7Bm3DU5bXrtXQCA1R64pdWUUKhIztnjru2977vpJT3UGitNtQDbj/9uD57zb4v0sUaZ4AaioZ+CIdPcTrGKleS+sRtjizQf0oyaKhq4bJZn77g3evcAzAoHyPvrh4V/I+uGRVyj2ais1x04bYm80WVQSPI5A9Zm67FV1WYP3IAovDUpFJrnrhWDQrcbEp0X6EeT3LWql/QANAGb8tIeUmO7ioxvYzci1rz/AdMJbhmtKsKbWzT+FpT9y3j9i8qHtGO/9eywPQOFfado2C4YGE8QWT8MwWzQ6Ji11EKvJOkS1faSGifWraVIIj0Jam6e2QNr/ppr/lIeuhWDt2tOzMhZMBQqrBDW1I0qHaFQcfdNsGmpNqocu1Z0SQ+g1jFsEboSBjfV8W3ZZeXADZquXuXCm1s8CXCKFUVUCaR989n5mQrKhEWbo1j4LQZu0RmN0dsmRV03d4wbCcrGx23NRmW9dN59QXmglkxrikoJh9L4mmvRGaE6tfl1dwfb2fAG+VCo5KCxekOhReoWLagQfm6wagM2F9cSlpjQ2DbBjKWBGzSOc0u2nNF68qRTArh0RSIQVwWkAfmgduw3n11ZX4yqUdzpYT+s2LYPbuE9L31YM7NE48oOkyaeM64Bs+UQxu5oEN3/mVMA0NiEAt2Kw9sJ8cTaQqHCjRXrRhXuWkbeKt01Xap1lqh/wGLQoNNty8ymEdy0hEuTref0oKD7Fq8mfVISkL5x03gyLlszxFo2Ir5oK0mDHIDo/S6TY9hmC2yoKmu4RNOPXVnuGm9ndL21cuHtHgBpcKs+FFqFu0aZm6W1oVs1cVwjlvXIArdwpuhH16181p9lzN4oD9zya9cdLpXsgQb3zdeGF/1UvbCgikCacdn6VyTySKeFy3/EIA5JuAvzG4mr6ZBWlg7/7ClSX77R9dY2vbYcePPBDQAOu9qHtyaFQvPcNY1gmWytJHctmCF6bHSGaLPcNaBGYPvJ3+3Fs/9tYWwfN0wqpPLATaL2+MlaGrzl9IR1zDKyNx3SypRx2ZqpYIV+RJ01YkKdBdQPh067u8b9fsn/4omutxadVKBTj7w+Cm/HszP1cihUGcDqdddGP1z9DFFAI7Cp3wQ+LqbbplBD7eAGlBQyTfbEl+Dr9bThivIhDQCO+eYF7A5kqA++V4xKVBzi/OckFlrtBzgxqku51gzCbypX/rIdZYEbADzy+nuD7QDeZA2N2kOhIlnzgsACbciMXcsIh+uSjhmiQENCoiyFbltiJyAxMUEgc0FwE+tOWSHTRBsxpdupHtLUlPdROeabF2h1BY3LZmTUfOl216IzQkOJwxpL0fXWNr/2bm6+oorB26ePEy4nBWuypWXdtZx05VBo7qssAGM1R0kbC2yAAIBXCm78OtRcN5RsA4TtbLjiZyW246oopNUtA21GRs1VNXc1EIE1odwA4kt2RGeD6tYjb7gPQBa4KYZCBYkpzw9j1qEMPsXcNbG8NYZbc9RoYPN18Ll/OvrEzz+2bsvPP7pu5bmRiQeJ4W7ZkgQ3ZladrhtKhbdKIO0bEUirOASl22UzMjKaPWK7ayIS8WjScccq4M0HNyAKbxWFQpsy0UDBXdu7njXhQKrqylQrsLEmHuSJJse3SdlbkgU0uG6CLSVOeLUxb5VDWlSyJ3MDxxgZl83IqHlqjrumBmtJRZftiM4I1ak4vB3brFCosgMm4HxV4K6NfliOWXRKK7CpTTyQssmCEmgEuInVI9215ImX4b5VAWkAcMw3zodWytLwa+WYb1xQ2bg8IyOj/lDaXSs2bk2oHk6e1decAFBg8+vLATcAeOQN64PtQz91bH4BaXtL4mKeO86Jl6VYKFRs7JpcSFxUuiYcAE0IifqITgAVcCNJHKoC3JjZS3DdgoLxkhteXCWkxTqSU6KBtpmkjMtmZNQcle+uycFa7ve24jix1VefEBR9pER4e/SPovB2DLc/InK/unUAXbmh0MLZpaC9XNUPbL4oAKLkRXklEk5dmeCWm13cdZNoERtefJNgTnWlIU1GRU5oNdgzLpuRkZGo4u6anKNSNBSaysCMEtLYemvR2aC69egfbQDAAbdEr5gpZYZCBfshkkXMXesNNQfYgAjnpMOk/sSDJ37+sXUHn/unqcGBzDBprE7pTshlZxYRw7LkqRTN2XxI06XmfKCMy2ZkVL+qGbuWJz3j1vIHw7PzVAFvPrgBwKGf9OGt5lCoVneND8rhhINL2RMOGuSuAQ0Atp/8/T48+18TqwYXDJPqBTeJQhrgDZhNkKZHx3zjfO1j+Qy0GRnVpzJgTd5dKxHWaG4vUvmjy3ZEJxXo1KN/HIW3o3ld0RQKFSkmAGMyRmlB7qpzwgFQArDpuuMBgIaAm2IhoZBpmOH+F98k0yFlHfP181DOnReMjIyMekFy49aqaV4uPOvDW1ngBgCP/vH9wbYPb3pDoXljA2sOhWo4F3ROOAAa4LAJKTa+Tb5oCG6A+uSEaCGJgjlFqgA1F9Ki4vwq6eH7+RiXzcioP1SuuyYHa1WNW8sXO08VrhsQwtshnzya2xc5VREKLZa9QKHS1BvABgAUOPicPxl94hcf545jyykOIGNWaWSXbI2yRe5/yc0yDSkpDWkC4trczXbkHn/Xbm/rFO0XewNtRkbVqQxYm3fCKdj+L8Cyf5Bzseoat5bOKAZ0h3362KBb0dmgOvVYxHU75BNruX1hbcqpfHctc/ya9PlQjRoBbMxxbLmiUKEILrjFExVqzC5YBaQdzYA0PZyVd3GqB+hCUDMyMjLK1vZ/cS9SKXBjWDxNGbcmlTHSreh6a6XB2xsfCLaZ8CYbCm24u3ZbzePXgIYAm5IKjG8Lintbesa5pQvWBWlRMSOf2nshcgHj9ECxMzxYm3eCcdmMjHpRZblrSW3/F8Jx23TBGrdqkZ0KebJzuvDmpkZnhOpUHN7WZOTk9FKK3LLfA7Gxazrd1upUCrCp3/EAkP4GLwhuYcsZ4CZR9f0v+blSH2R19Nef5W3JH7dqIE6wB5JnyeNX7dHaE1EZaDMyKk9VL+ERuG1/71+AxL7mxaRh3JpEKDS/ujDRX3OtLHADgMfeuDHYPuTjfHhjd7mEUKjMm0pTG8rSPeEAaKTDlg0gwTi2X3x83cHn/En8RvBawS1RTw4XVQFqR3/tWRkvLXmCqcyqZasJw9dEQW3VexYBOK+UpVEMtBkZ6VdZsHb4Z9yxa1na/q9JcMtS88at5XeLbReF663Fl/LQrcf+xIU3F9yaEgql2Lv+e9nrr6m3WKoaCGy+6nbc3K0s1+3+l1YEaVEJc5k+Hy3vhC0T6ORAzcjIyMgXxbJ/cLd8R42n7f9qAQCW/r3DrUvPuDURWJNTMaCgsfXWokt56JQPbgBwyMePijYPzhO2CodCReoWfrcqV2OA7Sd/vx/P/tf5jBQKJSTQAG5BNRHX7f6X/kK5LlGlIC1LUsYa7/QrhlyyJ7VoayKwxgO1Y75uXDYjo6arPHft5Nhzf8xaHrjt+FeLAW3FYE1YUuE4uVBo1q6oqoG3B4PtVR/z4U3veD5+drWxbU2YcACUCGxK49i4bKbotgVFaaSofB0PVAJp5+qpSCkyWg7Iybbma4ugq7Yyx1U7+uvnlbLOnYE2I6PiqgrWolr29zQIg/K0I+a2icAaQyrj1mTzKIRCRduiAA75RLjmWnRSgU49/qdReDsyI2f2+yDmruVWIJo7V2WMXwMa5LABHq9lspmbyB3Hllc5chsIVAWkATxQi54qBd/3QixW7cg2XaBWhQy01ScKgNLIA+4OSkn4+aZNGHnZe6pq7exa7hPqnRrueDUahEF5CsDt77piFTOeNmbcWsE8/rIdZYEbADz+pw8F2yl4k4W1jPyp8WtSzma9ahSw/fQf9uOCf3HDoiLgpqTom8MIlzbPTVOyzOSrla5a5j3IrrhMUCvLZTMqVxQugMXhjIJSxSESRkLKukVkL9wIJctdC+W+SD/0uSMP3P7NdvMzwU0Em3TBmkirxQv4P4BYiq63VgW8ueBWRSiUn7sp4VCgYcAWlbghVuAC7n1QHnjZLWrlJXT0VyOQVujCVxLAsarW1gy/4i1X7c0tvfI9/gdGDdSP/vqzcP+L9a+JZ1w2vaKRRzqNgiIKcHGgA0l8xyjeys4oFEl86KPHtwi81REKTboo0bNDBtzi0MaPo8nBmqhSlYtVKBkKFesTDddbo/FJBToVc90+egSjF+H/SmK4a02+cpQKbDpuBB/gGAfcnvjFJ9YdfM4bR5mJGaoC0tZ+9Zz0LFNAa8RTg1Wm3kyBZkVADYjCWjNloK243LBm/IeXH+qMwVkiDOq6cIDjeABhhZxGesEOaoAyD1MCekni/cktz1CdodC8r/elf+9IuG2djHZkVWIoVBbWhPsTV3S9tdLg7c8eDrZXffQIiVBouNMPhwoUUlZZ49eARjpsaccsxmrek4PPeePoE7/4ROLg59pxlWjtV88JtqMnVS68MZLVVKILJ9UsTY0l2vLuEkEt43N39NeeVdqdJwy0qSv6lsWALPJwYtvUfTiAQ1yEILZbkePQANSI5otwv8n/VLIiX/4xpDQBZBGA8+FNBtzKhDWuu8ZwULK09O+7AA3BjKcd/+Z+dQbgFqmeBtc9XaFQRVhTyZMVE2fVw8jur7kWnQ1aiSRCoQuPvXRUiG8bpsYB20//YQwX/Ms871k+uLGVD25rv3K2VpctCmk8peEtvhVJZiapi3ewCBOqMmuyKEAoiE0BywFsuH8tClgAtR2QgS7onmGQyYGgXBLUOhRoMZpd+e7yHDUDbc2UD2PRbYoQziglEVAjcBwKxyLoOhGAIIBlERCvImOwySnqSJLINcqFNpLI6zuicXDLOuZNgbXsL+SQiPzQJw/c/OtXAG5/2wnrpwRkpAuyxAGmCeAAtAPAIUAXoF0CdOD+EnEk71AjwIHxAhJZhfJnw1o04ZCPHxVkeVwjvHHdNRkJgnyTxq8BDQS2uNjgxXR5dS8HIiARSOMpegkRgjdGsrC4UOZeoOjCSWDNXqDtAVzLhTIQB6QFUAuA7bjPBywQ233AtgCLgFjEvVp7TdjzhjB99w7gkYWgw2289aIp/PMmiimHYss0xSsPGsS5iwdiPVn57oWVjDsy0NYcDc2Zi7f810/q7oYRAHSnMXHja4JLjA9fhBAQ7xqVhDcf3PKgrddgLaqlf9cFCLDjX+Pg1iLAr/Z08OVt0zh4yMK7/prg/d9xXBgbJ2gd08bwaQvR3T8VxPap49nFXQfUf7QdwCGgHQLi0ADsqAOg6wIeugQYpGjf0wLdzQJI3+aMXOeZX5LcVy5DbEpa9fGjguqjS3lok4S7JlVFw1Q6sOkYx8YDr4POfuPo1ls+se6JWz6x7uCzvXFsubNKi8Hb2q+crZ3/kpcU7QBHCTDUAT14DKRLABuglgPYFHAAHDCF1soBOJPt8MLiXWRAaYSjCNCloN0uKPhT3TvbJ2CtaME+chK06+Bf9xD3ekgJrAEbv7t/As9Z0sKTbYopB7j5cYAcbAFPsBZO7i0ZaDPqRVEA3S6NgJoHa5SG2x61RcEtD9qaMGYtvsUpEPuKSPzApcDy/5zCyefOYNWQhTkWwYGDBN/d0caTC+aC7usAhGD43JYbtLAtdPd3ML15Z+5YSmIRd+xli7plSfjjN/ghbBFYcwZABifRfaILWMR15jrutZpYBN3HbdBJeVhTzpPjrqWyRJ5El+yITioQlZi7lk4PlvM4xr8dVd75IY8tZY5fAxrvsCXFd8wCky3XVJN33dZ+5Wx2FaCRavS9T0LuWzxjLAttOcDCafeJRd1faavGMXTasPuLz4F34fVO/WmKzq4J9wKhQcQG6FQHnakxRirF1paNL+wnoF33QmktJXCGdgMrx4CWAwx3gMfmgzy4xC1BKIjGdbXKdNmMjHpV7a4DywMMy3IvJwE/uNwQA7dgVG5N4Wemu8b4js2FtdQuAvuYadhHzIBOWMAMQBZSbKADWD/ugFgApgioQ0C274fDufZLT3zxfyQzkKQz0Ya9vIWBQ1p+5YAFAAT2wmFM3LoH3YdabnSk7aY7u73Qa06TOsatJRN4sJYsrAZvNPOpUh09okYCW3wcG0v5oVKR5UDWfuUsPPCyW7mtpEAtqysVwFu85nCLWgCGOu6L7hLg0P0YPm8InT0Tbk6LwJnsYnrzbvdiw5AuWMuTAwJ0HDidmWAfpRRkwHUB/S8Cumo/nJX70Zo/gO7mFnDPMtBWF6STPRhYVEd/7Vzc/5Jy7gVrXDajnhMF2h0Ky3J/JBKHeNsEljvyATSANne8YBTaQNIuW+WhUAYYCMGa5V437dMnMXA4hTPmAAMOyIANMuw6WLQLdMemQUh8OgvVeK3PEiEAne6gO50msM7OcQyuHYJ18oAbHQFgL5qD8R/sQed+2x3WQikwbaW5S5ZbBGBNoTAAD94ojc0GTWrlR49A+kWo9CUvN8VtH14kVU8VIlSIrotLNiyaDWxxbb3lk+sAN0SaTMtjqCSwCUGaiEqAt7S8i+Sq/Ri8kKCzexLEJqDtLrr7Z7hw1nRRGs72o9S9YNqLRtDZ1AG5fQXoYBdk2v+lmQhfSKosaAMgBG3+khbu8hTUG+JC0e1S2Kufj5Hj/7C0/hkZ+aKdKWz55itA4MKY5TlpFgFs231uERfeCCGwPGhzXTh3PxBOQhi/947S+qoH1gAMdoFpC62zJjBweAvO/ul4lZHrUK+JOhT2vEGQARu047gA9+1xdDe7P3hDn6E+d41ZRyJLEt5WfvRwbteydsbDoTQnt7tXFtjKDocCDXXYdCow2jKGsa39ylmJEhqOe8nOGw6YxMBzJtHdOwUAmH6kGwtN9CqsAYxQAgU6u8ZBllhovWw32o9MAr8/EGh1gYnBwtBWlozTZtQrogBm2o4HXxQWIbAtF8woPHCzwm1iubN1fWjzXTUKivF77qw2TCoKa/51YsQBZoCBsyYwsHoE3d0OuvumXPcsAmm9CmuA9/5MtOHGR4Hu/mkMPsMGntaBvWAOxr/TgfNU6I7yr59VwRo7i79YLgWwJem8KblrYrDW1IhpY7/Wf/oPYwoHLYz/Z6ZEnsRhLZlB07sWVKeh3vkzsC/bBpy0A+3tY6DtLmi7W9s4krIVu3g6FO2n9oPMp2i9ZD/o6U+CtrruxUZhhmmZ7pqvWgZdGxkpaLpDMdNxMNOmaHcczHQctLsU7Q5Fp0vR6TroOjSy3AoiCxu722P33AlA0LjRIVlYa1EMnjOOua8lsBYBnR1jgNMfkJYlYhGg6wAU6O6dxNAZM5h7ZRdkgRPCWuoaKgdr/N0isJafJ+aulRgKBYDb/nmRVF1VqbHAFkiAbw46+49HgTA0KgJuNDubXAdkpApvwx3ggkeBU5+CM9kGsfr34pIlQtwLT3vrXljzbOCcx91jIwltVcCaLwNtRr2g6bYTPGY6Lqi1O04Aal3HvatE8PAmLvmfugDWSu7npte47UjD2hDF4HP3wVpgo/3kPqDbuyHPIvLHDNOug6Fzuphz+TQwXDxKkQVAKiXjqepnVRgOfV5qyJRCd2pVZcCmFt+NAI0SN2VDUQrcMuvX7LrFqqRcgKOWA5y9BTj1KXcQ7AANBpbOZhFC4Ey1YQ22gHO3gc5te4tQ0vhbxXhUCWu+DLQZNVmUAlMzDqbbnssWddi6cYfNd9mid6PYf88dwVjMKhRAm9v7yP8J+bA2z8HQJWOwhltwptqzEtR8BeODuw6sEQprbgvD57YxfPGMOwHDTQ0LFAqFCigjP/OdLdldU1EV49eAhjtsP33LuLdVFNyyC/LCpfl1ab46sdy3s5+AtcACmeeAtt21z2bzxSYqQgicGXfWlHXudmDhVKbTdv9Lf477X1o9rPky0GbUZM34IdEOxXSbxsKh7a6DrgN0ui6sRUOj+++5k3kljN7Bogxteu2d2PTaDFfPgzWyqIvhS6YAy71emOunK+IOOoQz3YG1mKC1bADDl3SgD9b0hEI5zYq1w0jKhDXa3HAo0HBgS4sPbumwqEAdnBRx100qo5wogDO3wp5vw5lqx8ZZGIUihATj+Kxz9wDLJhhvIK0V1KIau+cOA25GjVTosEXGsjHGsHW7FI5DMXbf3Ri7965YkIDqvg4KaNNr72InUAJreRvDF7cjY33NNTQpd5gJRXdiBq0DWhi+yJ2oIAJrfNUfCgWAvRskwqE9ELiqFNj02YY6Hbdmwht55pOwlljueLVZfpGhkX+O9+gS99Hx1n+iXQfOZBvWur2pKOj9L/1FvS+AIQNtRk3TtOesTbedENI6FB0vDNp1/Pu7AvvX3wPH8a+PiWEcNXzxbeZA29AFXTiTbdCuAwISXDf860j032wXIQTd8Rm0DhrE0PltoTLqoVBafihU1l1TVFXhUKAHlvX46VvGccE/z+Wk+geaFDzmkXryUqPtZL5NwhnTOvUpWCsIuuPTjYO15IWNAsHhD7cpKEmmUe7b5L9CQr11naj7sChx7ylPbbRgw4INGzYsWO5z6j5/ijzprv9EKbpj8QvNAw2ENV9j99yBucefUnc3jIxAAUy3KRzbvd2lKwfePZLcpTxAYVvA9AP3wLaJ+zmnxP2sU280QqS+qq9cm197F1Zfe1JkD3UXu7WIt+AtxdLuYlA46KCLLhw46KJLHPcZceAQwCHe9cu/dhG+1+N/JxB/BTqK8BrmXfBILF+yfLOu74QQdMemMXDYMOhZM5i5NYkIukKhkh3TAGsi9Tc5HAr0ALCJyT3aB531x6Nbb/3kuq23fHKdHyJVqcdV+oOUSs3mPOF6g1wWBTl+F+xDw1W1s2vlwxPgX3Bo7H7AwbboRYjCgyZ326bEgyYbFrHRojZs6uKURVqwHQKbeM9pCzbxMasFCxZs0kKLWi58Ecsr6277+S24gGZ7bXQdB+1OF51OF+1OF91uF12HotPtwnEcbF/xlHv7KhAQy3uNVB3W1n71HADVwN7YPXdg7gknl96OkVGmKDDTda8oPrARQmA5AHEo7C5gEYr992/AkO1eE/xbDnvF3b9Uz62qDv/MyYmJBWIKoc3tnH8HFwr39naHPXYUbNuGbRG0WjZaLRsD3sNu2XCoC3JdD+Qc6qBL3D0ddL1tH/RoFPvCbdJBF9QtQxxQ6tWFLjqkiy51QH1Q9ODQIRQOCa/ZIj9u3b/RfeE1O8irAImEEHT3T2Hw6GFgZgYzv7XDi6qnQrBWQSgUSIdDue5aD5mrlQObnpvB80SZm2o/YsRcNyB7Ud6ckrEUQgH7SAfd/dNumA8UUwNODJ4IIs6TQwLXKfSebNjUhk1s2NQFIou4CBSCUrJEBLioVyPx6kEL/3LZDN723bmwiQ1KgXang06ni07Xm/Lf7aLrr9HkON6K/U64RlPk1ToA2oTAsgi63l/LsmBbFmwLsG2g1QKoTYEWhTUAWDZg2xQYdBft7ALowkHLq5k4Fii6oJSitWQufvviWzCisC4bEMKav10NtN2JuccbaDOqV52O93m1vTsZEBosmOs4BOMbN2CwBTiUeLNESTB2jRC9sOb/VYU2AFj92RNgL5qDzu4J1yikBPMObgHBj04Cm1ruHRw8QurOeEuZdLpodx33R2G3i67joNt14FD3WDjUv82TDepQWABsAiC4Q4QFyyLudc22YFkWWraNVstCy7bQslsYGGiBWECXOPiXlxL8zVdn0PGcvgAbCUUXnQAK3b9ODBw7JEz198fyUAcdy9/rwLFo6CQiDYlz2pYbPt43hcEThzHz267gkReEtT4JhQLVhkOBHnHYssOiPDHCpYXAjV+BHngDQAm6+6YjvwqBZ7fPxQAGIy6U51cRG4RYaLe7aHe7HkB54NR10PXByXHccSdO5GbvXnMOAEoIHELQtUJ4siyClu3Bk03xd18ZQqtFYbXcOyjYAwQYJLAoQQvuOLIuDcMKXdoJfqU64W9T9zl1LzD+RcjP1aGd8GJDu2F+pxteYCz+BQYUsBfOwUXj20Hmyn8Qo6CW3F8VtI0cd1J+RiOjktTuuhBGCIXVdW8Ab3eBlg2MPfgABr1wqeNBGkX8r3+9o6C5Lg5PsdtOUeDwa93n/mxQGa3/w3tx4n1HYGDNMLr7p+BYDm4YujXmRKV+AA96P2G9H7cWsWA7FlrEixBQy/9Z7G17P3uDYRvEu0bDTQng0HJjDNSt03Is9w4RDtBtO3jTNR3vB3AX3Y677VAPEh0K6gCUWi4kwwbQ8toABr0fvsSHRA8QbcuFQ9u2MTDQcp3EgRYocUPCDnXgWN71lrhX4w46+PXwHSDEPUbdPVMAHYSYuyagykKhgg1FsjU9HAr0CLDJ6KCz/mh0662fWrf11k+tO+isPxrVB25AIXgTape6N2/31sLpWhSDe+dhcmrGBagWMGC77pM14D63BwAMwL2VDCXoAu6gfNA4KMHx7PjA8Hf30Q4cb3+XOJF09/8O6cDx93khguDXmeUtfQY3xKpq4cP7ZR5Y+Inj5F9QucecUtgLhvH0yT34z/nb8w5ySmlYo4n0s/HAS2+RrldWY/feCYcCc4414GZUrSgAd9UgCqtL0CVAtwuMP/YQOi1gqEVCWEMU1iKkVlBJWIs+Ofzak/izQTmaQygePP4hrHnwCLQOGUJ3bBojbZubn3ohzi66aEfH4FqRbcUhJv71z6KJ8bmwYDsExPtB3qIhGBJ/IAm1Aih0Ix8kBEXYaFECFyNJODyFhuVsYsNy3G0AcNoUnbYLhx0PDrvdLjodByPDQ+geSmF5F3baib+qXgiFAhR7N3w/CIf2QyjUVy3AphYWLXphYIAbilQpCW9iRWCNWKCO496w1yG4Y96vgflwwQqhM9WFB1/RQbLw3CfFQbJAZOB/JC3aVwICm7pj2ZogSins+cM4enIfPrtgm3T5tV85GyKf3LVfORsPvKx8aAOAsXvvwpxjTqykLSMjX13HvYdo16HoUmDi0c0Yskm4SC5cSHM8YvM/NXF3Te2SmgVr/v+rrz2JOxs0SxuPehhrHjkcrRWD6I7PcMcGJ13B1DU740ejqtwQJeAO9PAA0L+WI3ItjwIk4hGGpKI/kknk+u5Dok39SI3nIoKghVYAabbj3VO1ZcGexwfcUIKwlmuMJSNOkm0xkriwpkFVh0OBHnLYfvqWCVzwzyPeMx3g5tVT2HVj1JmTA+C7b93RRbDP3OuOhWh3sdPaFauVxIo0C56qFqUU9twhrJwYw7cWbZUu78KaXP6qoG18/V1YsPr5lbRlZAS4t5q0Lffv5KOPuCFQi8LxxqoF7loS1iLbKmPYRGDNlyy0+X3aeNgmrNlyOOzFg3Am+dBWtfIhUX8/3ckODtqRpigBYLvPWw6AARukZWHyhvJDoXphTT4UCvRGOBTosYVzwwuF//uDLTcUCmy99VPii+hS5FUr2kuhilK5qPsf2TWM7s1LAABksAXLgWeBu4/ov9kqSilgE9hzB7FoagI/XrTF2y9ehyysFS2nopmn5CHUyEhVDgUmtzyOyccfcyEN8P7ScJyaf7mkyc+b2oVTBtZ8xZfuyJY/GQIANhy8CXOnpmDNGQAsEozpnW2Kfof43ys29R6O+71DCDD5PQrnSXd2aKFQqJa7GYgX9MOhC5iL5fZmKNRXbcCmbCdScXCTqrQJ8EaJuzzF/gHQm5bDmenAGh6YtReWpCh1/X1rqIXD6AwOnJzAjxeGsCbyo3ntV84uDF1VQpuRUVWa2vqEOxEJ7ld0bGIBZV/NilwmVWDN1+prT8Lqa8WGDfjQZhPgp4sex6LpaTj7ATLghvvM9dUVpdT9vul0MfltAmeXD2uRC6s0pOd/9xWuR/jt0/c+1xEOBXrMYfvZ/5sIn+SAm7jLllSiLl1MGLvcZZ18LrTRSRvOzQfBmejAGhmc1RcV/7WTlgU6ZWG43can52/DzxZvwVxC3eU9BWFNlwy0GfWVaOiiURD3QaPPE9lR7LLIhrWw1vy63Yv/6mvEoc0BsNCiGF38GH508GNAxwGdCddqm82ilMIaGYQz0cbEd2w4YwxYi5cQqbXyUGi2u8auqlfCoUCPARtTTHBrsuvGqT+WRABCQdo2nJsOhrOri4GDFgC2NSvBjRAC2iEgloWvLXscdyx+FIfYXTheushJXAZgGWgz6iclHTVmOi3uSPFhLbnF7Wkskyi0+dcJB8ARdgf3L9mM9ugcWHMGQbt0Vl5bKaVAy8LgwQvR3d3G5LdbwCTxBlknYE328GjJLw5ruZX3wdtbK7BptRVp8kKj892pEt78Njxocwjob5dh5ovzQHfZGFg2Pzb+ol8vMtSh7gho4q6vRu9egg3zH8JJrRkpUAOKgFXyfUk/1n7lLMW6jYwaKMo4y71ZojqkG9Z8iUIbEF43KAU2vXA9Jr44gPZvhzGwbB7IgA0yYNdyP9Qq5Y8DHjhwAbo7KPZ9fALTN7WAjgdrNOGq8p/wGshOFq1Hi/S2U1c4FOhBhy0WFuXIB7cDz3qDYlg0s/bII/1UaxvU255qAV0L9I6lmLluIehTQ2gtmgMAsdlOvQxv1AHInAHYC4dhzR3E4CGLQO+dD3rjKtxnr8fGZ/8uuAbInLRpWMuHMNk31ECbUa9L+yWMobJgzZcMtAHhMIrNr7sXmy65H2Ofopj86jCmb7cwdOhiWPOHYS+e4w5JcXr42hr5XvDHAbcOmIvuVmDfRyYx/QsbdJqA7oceWMvJw4Q1De5aZjiUU1UvhUOBHlrWQ0ncE00XICfqLKOJaDsz3riCu5agfTsBOW43rCNm4OxzgJYDMmgDoCAWcS3+rtOY6etRUQew5w+6oQjH9cvshXMwdfMUnIcXALaDLiVA24otoyHzUkKIquZCu/bLZ+GBP7i1kraMjHpNAaxxrslFYc3X6mtOAABsft09wn3zryuPvP4+HHb18XAeHsT+q6fd8VttoHVMFyPPWYrunkk3v0XgTLSDG8s3TZS63wGwLIC6d52gbXckor1gCNPr25j4Stu9hQUlwBQQjewUhrVcztIPa6r96TWRJrgyKvcWPf/DI/mZPG375afXAcCBZ75hFCTKUmV92Bj1lv25Pnw/rMP3g467bhyZ14a1aMCFNu+GgHSqA2e6U8lFhjoU1nDLnXUEzwkkAAiBvWAY078bBzbPB2wK6nhp+wZAOqF/9sDL1ACoFMcr5wxVhbX4gqQUDnXXwXIoxfDpr8Oi89+iVK+RkYxmpifxL685DYMWxYANDLUohm2KoRYw3KKY0yIYagFzBoAh784Hgy2CQRsYsAlalnu3FcuCdx/ScOEhQjxgKxnWkplkoC2qw64+PgYFZNABllB3WJdFgS5B66gOhp++AN19U273IuNxqr7OkkEb1lALtOvedxoWQXfvDOgYARkEyFyKzgYb7Xu8RXA9Fy1SS7xO5hPBr2jZUCg3ex6wxdPZ7hqN/UlKxV2rMxwK9LTDRqFEQf5nnyAx90nn+8CotzT3De5FZNN8OJvmh/Uvn0D3iDGQdgvOFMHIimFMdvZhYNUC0Om2dy8oF5SIbaG7fxrORBtEJt7oAVhQj+VtWwT28AA6j83AeWoA1HLH4rn3zSJoW12QJxe5oV6wD0clsCb5M4GXfaNx1oyMMrXpNXcG9wWVG8GkBmsAsPrqE7D59fLQ9sjr78Vhnz4+qJPOWMC2eAsz4wTOrv2gXYDYALUB2BRwCOyDHAysHIEz1QYodcOp/q8yKvp6Iq+sS2HNHYQ9z50c4ddDKWAN2ug+OYV5IyPY+/h+tObZaM/MoH1fC3RbC860ExweYhGvL7KwJtpRhVBoRk7RpMwa6/ejtKoRwKZ2qyogfDcKgJtXvBp48+pm7FIVseA6VAAWHT+EmT1dLDhhCHOWLwJAsfLi1dg++hhWnLsa2+97DE/cvRkLDjkYoBQzuyYxvGweRhaM4LG7HkbnwPnBL0Z/aXPqUMC7VRbtOqBtx7XNO8SFMGoBHbj7usS9uWjXgtPqAA8vAvYMpV5e8Dz1S8+Vqlu19stqzlqffaaNjBqsamDN36UMbW+4F4d9+jh2IqHAuIXOhshN0SNddbbaoNNTQJu4A25b1P0h3AJguZdMq0UBCyADFohtgbQswLK8UGb4IxgA7PnDGBjvYsWhB2Fi9z7Yw4Nwug46k9OYmZnBwResxfDIHHRPm8Gi41dh608ewIKXL8HOu3Zg4tEJWC0Lm776BGjbbTOYtZV1FFVCobmpvR0KrdtdAxoSEgVUw6JzGHvZxzQWFuWJJEuX/f5w6pdsdt7qQax60XzMO2wBWvOGMf7oDgwvnY/2/il0p9uwWja60x1YLffi0J3pwrLdi4LTcWDZBO2ZGUzNzIBOO7AHLAzMHcLQornojM/Amelg7kFLQLtd7L9/L/bdP41997cx8XgbADCw0EJ7L+cqwIEyloo4VWsUYa2oeH1e8+UzvfRfZpY3IVGjJkhnSPToz52Mh15zVywk6uvwa08SC4FG/gjl5ezyNx9RgDZfXHBjwBr7ekex+OT56Ex2sf+BCcw9bA4WHzcXi46fjwXHLQEIwfTuMXQmpjG0bD6m94yjPT4N2qXodLtwOl3MWzwfg0Pu5Ac/1EopDcYoO44Dy7LcoSgt9y8sgqEl8zCzewwjqw7Apq9uxOYvPRHxOSj7UKvAWi5nFYS1IDntCO5LhUPzz59eDIcCDXHY9KoXXLdIgzExwqcZTY8cMoCVz5+HFWcdgvHHdmJqxxis3eMAgOmdY25RQkC7DqyWG+ukXRfQ3CcUlu3eemZgcBADg4PAvEjv9s/ABmBZNma273PbXDmMxSceAOpQ7N2wC7vvnMLyc0YAQrD3nmns3TCDfQ9Mh7/iSoa16kAt/enPgzHABTeRfEZG/aCjP5d926hNr70r59ZS+mENoO64NLjhTlk98ob7GNDGgDUgvN5ZwOLj5mHRCXOx6Lj5WHjMCkxu24Pxxyew+ISlIBbB9K5xtHeN+9kxODwEun8Gg/YABhcMMF4ajY2Li04osyz3+h6EPQHAoZjesR/Uodj/8FM44mVrsWLdEmy7ZReeuOFJtPd2oq8EOU/4qsLzEQ6Fipw/zTCpVNQYhw3Q6bJFFZ7UQi4bp4pqnbeMdrxda/9iCeasGERr7hBm9rpLnVQ9I9QasDGwYA6mntoPMmBhaPFc2EMD2L95J/bdP4P9909j7/1t0E7221ofrKmf+1kQ5rtrImWMw2bUBBV12E667kQAxL0GUfeC+fBr3Ju0sy5LbGgrB9aSUoE2IOq0sWGNDBAX0o6fh0UnzMP81QegO93G9O5xwKFwug7soRZohxONKFnUobAGPY+GUtz2Zvf9KQRsKuPWNIVCue5aTrd71V0DenAdNnnRyEO9ivh4UQ11ijacaGtggYWl6+Zg4TGL4bS7aO+bBCGkluU7nHYX0zvHQGzi/prbOYaJJ3bDHrKw4twDcMxfrcYJbz0Ah750PhadNAh7KP2a1GHtzFRd8g81qcBaXpqRUa/qpC+eED6JfKyO+AzfSdv82rsSe6jEx1Id1gAEbpusHnnDfWGdXnftIQsHnD4fR776YJz+/qNw4luPx0HPPgj2kIWJJ3a7kQ7P8bJsqzZYAzz3rdOFM9PBwPw5OOZNh2PekZHVFlRCobmp5cGabH/E8zRXjQI2FYr92f+blP7+9Z02JdUGb25bB54/F8e8aS2md401cg0gAAAFZnaPY2LLbhCbYPmZS3DMXx6O4/9xOVZfuRCLTx2GPWIphwqbCj4i/Wpq342MVHT6lyLww/jCz4K2WF7hy2cxWPOlDm3rYY/YOOAZC7Hm9Stx2gfX4oS/PwEHnrsCxLYwsWU3ZnaPN5oLiEUwtWM/Dr5gNZY9bbG7UwXWcjmrIKxx8vjPfHcttjcnFHrbPy8WaC+uprhrQL+NYfPfLM7hPfDM149u++XV64QyC7YXnB+pMW8F6+Zo5JABjG16yl1fjRLQFkDq+9EmpJk9E5jZ44ZtD3jaIhx4/hxMPbUX7919Bp4xthVP378NB3SnhOqqG3h4kMntF+MCsuZL3oSEl5uxbUa9qXO/fixArDDcyfjC93etvvYkhqPmumyrrz2xcljzsxz26ePxyBvEwqM77WH8Zv6B+PW8g3D6Bw/G8PKFaO+fRHvfJCa27BKqo245LQIMWCDj7gS08cd2YuFx87TDGq+ItLLf7kBBOLTBkKxL/QVsvmIDC7RmzqwmCm/uH011e5q7egDLzzoUe9ZvcQeGUIrBfUOYXtoBHbBAprqw2s0+a9v73IscANx70GHYuOAYXL1rHMfs2IKnj23F08afxEEz4+gSAjsyPqJuUANyYC33sKczrPnSGXjgD35VvGNGRhXqOd86Jj4ujcK7vIU/gpNnOx/a7ha8pZReWPM3/HFpbrgzVJcQTJIWvrfkSNw75wBsWLoSQ0vmYmbfJJz9U70DaQMEdNgGaTsYfpJgzvZB7DusC8cG6EwHB567BvOPehz7HxyHMPHkZGO6a7IVcUKh3MwK199eVKNCooBiWPStk/zERLTywDNfPwoAodOWkVlVXjX80KlaG5PbOnhq9DEQ24IzYmPBUwuw72sdHPbLg7Ds7nmYs3MAzqCF7vwWnIHGuLhcdfZPYWLLbnQnZ3D/8lX4yqnPwtsueTW2Ds5rFqzRnBmhqV+o4uPl1n75DB09NDKqRJd+Z234JHZqSyFTTJtfd3dGKufzowHWokrOArUpxR1zl+PG8y/E/ctXoTs5g4ktu9HZLxYJqFPOAHG/AwYtDG+3sOR3Laz86Xy0fgT85vPrMfeJIdBhG615w3joC3dh/4PjILYorDVj3Fo42eASgQmEbsleD4cCfeWw5YQ4pa4iep0xXe6bM0XhTDmwhwZAp9ugxMHxaw/Btkf3YP/6SSxeMBcrDpqL8QPGMb5kAhNLZ0Dn2CBTDsiMU9ncVhV1xqfRGZsCCMEnl5+IZ4xtw9P3b8W6L55WToMS50NW6HLNl86Qq4yho7+8DqDAfS8zbptRPSLIvgq94oYjAULiIdCgQPgk65PAc9kAF9rSThunNs2w5uuwTx+H37/xYfx2wUG4be6BuHvJwXDufdydtt3AezL7ogDooAU6bIFMdjH8lI2RpwYxsn0Qux7fh217d2L+vBEsP2Qx1h13PPYtnoQ13gWZ38LCNe46TrQr2lJearnj1gSyKrTVO2rUsh5RKS3x8aHhyLPsD9i2X13tLfHxeoklPkr40KaWDOG3Yw0QHPm6xRg+qAUCoLtgANZkFyM7BjF31whGds/F7i3j2LN/HAvmjWDpwfMwdsAEJhZPYGLpNJy5Nsi04z70vxJtGlg4BwPzhjG9axx77xvD3vunsX/DNGb2lDlYj326bXw5H6JcWNPUNnX/3vPSUbOsh1HlanvLegzYFINWfFmPP7v5cBBiecBmAbC855Z3j2D3Qf1lPYKLWnoBWdBsRy2EtupgbWhJCwuPd5fjWHzCoiD02WQ3jQKgQxbokAVrvIs5T7UwvH0QI9sHsP3RPdg3NoFFC+bigEMWYnLZDCaXTWNyuQNnJPwBP7hwDh65/jE89q2t7luVBz65ppgIrGUmCDm2MXdNMBTaD+4a0FcOW1KCDlaOMadUp4ySnwPm5AU3wWlTPPatfTjtX4/Fvge2wd7vLnw4vryNsUP2g0zvxZwdA1i2awRzd83FnicmsOuBMcwbGcbhK5difPEExg6YxMQBk+jOb7mu21Tz4K29dxLtvW6Ye9EJ87H8rBWY2TeJsYf3Y9uPx92FeWuWPliL6/ivPBMAxR0vvq2U+o2MePLvhuQz2F/94jAPyCKZYuPV3Cdiv6zDC93qa04UCIPyd0l4L4ks6bwHPnsJ1v7RWsChmNk7gc74NCa2zOTXWYMoADpsgQ5asPZ3MOdxG3OfGsCcHUPY9tgu7B7fiyWL5mPp6kUYWT4Hk0tn8PiKfaBDFsg0hTVDYe9zvzMcx0F73yS2/ODJsPKslrX5OrrGrYlka6YZVUSNddgAHS5bUnE0CVy2MxIumzTBlIg8JPzj3jcUOPKPluCA05Zictve1NIewSDTGQdzdrYwd+cI5u4awdjWGezcsx9zhgdx0MGLMHHABMaWuO5bd9FAY+EtqqED5mH76E5s/sKeStrjuWv6YS102NzPozv4ccM/HW8cNqNK1J6exL+91nfYKN5x2yEIFsIlBAQRhy1w1izv4REe12Fjf+HzoG31NSfEdxSGtXS+gQU25h0+BwdftBTDywZqWcdSRFFIs/e0MWfHIOZsd8OdWx7dicmpaSxdvADzVo24TtryNqaWOaCD/ElotOtgePkCPPSFh7Dlh08JdKIZ49YAGXctTOwXdw3oa4eNJUnXLScbu4BwITHR8I8/zuDRr+/B4hMXuwvWJpq22hRou7+ipha1MXHQGHZ09mN4h40lO0cwb/ccjG2dxlMPj2F4cABHrDwM40smMbZ4HOMHjKO7aADoUFiT3cbB29SO/VhxznIsPml+GCp9YBozu7oClr6cskKh5YgmHsDQioMq7oPRbJZFKOYcvAoDtvucMUQtJs7udC7Jz+Xm190TQpsuWCMAsQkOvmAx5h4+gsUnLnLvs7l3wp213qCLHQXgzLGBFoG9p42RTTZGdgxjZPsCPPrYU9g9sw/LD1iEFUcvxsSyGUwua2Pf8jHQFoE12YU1TYFp9vAR6lCQARvUoc2BNU4eM24trcbNEq1OFAee8Tp3xuivWDNGg2zR71DhuhUKiYkAM7sc7Pr9LthD6fvNxbJ2KOz9HViTXUwvaGPncWN45IynsPfcXVhyzhCWrZ2P8bFpbPv9fkzfRHDEbaux8jeLseiRYVgdd6ZRd8QWvR1o6SKEYHLbXnQnZ7DohPlY84ZDccLbVrqJFcFacXctCWbuI9hyzTU8+K7mjp8x6kMRguGDVsIigEWAj7w8el/jyAXA350MlbLGq+XAWtZyHptfd49eZ40C9qCF1S9fjSWnLPFmfe5CZ2yqEQuQUwJ0R2x057dgtYEFD7Ww4tY5OOSmpRj/0SSeGN2Osf2TOPC4A7DsOYsxcVEbW84fw+6T2phZ1IU12YW9vwOScxtAa8DGgqMOxMNfetjbkdWpimAtOwIeKHDXjhaZGdqfanRIFFALi573oWHhH0zbfnWNFxZ93ajUzyzlz7iei8PcQwdxxOsWY3DBHMzsmYTVEq+X2sT9BUcphnYAI7tHMG/nCLDdxhNP7oJtWzjs4GWYXDKJsSUTGD9gAu3FFkAprIkuSENOGdqlIC0Le+6dxNjDM9h3/zQ6+51Cbps+WGN3gO38J0OiwEPvmkSnS9HuOphpO5jpUEy3HUy1HezecD9musBUG5jqANNdYLpL0O4C7S7BjAN0HYIuBRyHwKGAA0SWmGmmBpcfWHcXuJp5alvdXdAmAgRgNnzggWhZBJYFDHj3BR1sAYMDBH/+RX9CAYKQKKxwwkE4CYGEz1Mt5Ym6cMbR6qtPyBh+zq3S/Y/AvSvBqfOx8Ji5WHziQhDbQnt8BlYDrApKAGfEBgjBwK5uEOoc2j6ARx5/Et2ug5UHLgU5kGBi2TQml7Uxs8x9T6zJLkhX7tPsdBw4HYodv92DbT/bjuld7YxDmn2xEIe1zAThUCggCmzxkv0UDgX6GNh8iRz5OLTJlJTPqqVwBEiOf8syLDx2OcYf26n0bUwtz34nBIM7KebunIO5u0bQ2jGIx7ftBAAcctABaC9tY/yACYwvHsfMAR68TXYbcZeFgQVzMDB/GKRlY/1/PoQ9d6q5U/Kwxj/gnOsQP7cPbAA2XzWJrkPR6VJ0ui6szXQcTLcdTLddcNvzwAMurPnA1vGAzSFoO0DHgXcj+SiwiQ4Qb6bKBLp+ArI8EVAP1g6CZQE2AVo2QcsiGLDh3tS9RTDUInjtZ2lqvBohtgdykbFs8Me6Ufg3f8+/toVnYxa0HXb1CZCGNU+HvHAZjvmzkzG26Sm0GzDrM3a93dHFnB1DmLN9EK0nLTy6xQ1RHnLwMnSXU0wum8bE8hm0l9qFrrfUobCHBzD3sKV4/LsbseGjm/NKCJpi1YxbA9RgDeg/YGv8GLZjL7+OyELbTW+dCqBNejhaIImS6o0gfZIJVBAp8tj1+7B3/RQOeNpcd3yCpL1PHMAedwfHdeYAu9dMYjeZwsAuB/N2uWPe7B0WHr9nHxzHwcErVoAudzCxeBxjB0xi5gAo/+LTJf/uCZRSLH3GHNAOMP7IDDpjxdw2X2u+tC5VSdIg061wtQQCQmiwbVnul+3Lf3w8QB186tz17heuBQ/MqBvJIARdAMSioJR4wEZ7Gtjojq2l1T3QAMelKn34d+7YyPde5q6r1rIA23PYWhaBbbvPbRsgwQpt/nUl6/oiY+HGM66+5oQMaJOANeJeA5efvQhzDxvGkhPnY+fvN8Nq1fcGRyMagzso5mxqYWTHMOhWB1u27YBlEaxedSAOPv0AjC9t46nl+9Be4kMahT3WKdQ+sQkG5g/j9rf/Gjvv2JvX28bBmuoFtt9gDegBhw1QdNn+aQicRc4ApHezXTaRkjkq/PbnVzCwwMYpH1gNYlmYenKfOxmhoCjxfgnarl0/sntu4L49smU72t0uvnPFk9gwMA+3geDXloVHRlqAVS+8DSwcwcC8YbT3T+J3f7tJuNzGl7Pf9qO+tK6COGLosD363ik4Do04bBTtjoN213XWZjoU5/6HDTd86oA6FICD/znrAXQiDpvjAN2IwxaMqGx4WNSoPL3/N954T0JBqPtL5kMvIi6cWQQDtgtrA7brrg22CIYGCK74hAduhDdTFPChzr3y5Dls/EFLm1/PhrbMm7UnvvztuTbO+tTT3Xt97s24C06JCiDNoThsooNnOA6eCYpj2mO4+LPDGBho4bBVKzC5bAYTy2cwuXQanSUtoOs5aZo+pE7HAaXA2MPjePCzj6EznrVCbkWwFkvOD3gbdy1UTwAbUATagNjaGAwRyAAbq7T+rMKVRByko16/GMvOPEj7fe4oAZxhf9ZSB3N3juDPlu7DM0ExsG8LaHcaZO4yPDS4ALcRgttgYdNIK5i1lDcQVrccx3Wkdt8xibHNM9h73xScDsLPdKI7D17Jf8uPuo4/H0Wf3A49/t4pUOrCmkOBTtdB16FoeyFRfyzb2f/RAqjjjnejLrjBWw7kP87YiI5D0KUUDiXoekluJIU0fhybkX5dddtKbtq/v8QFNssiaHmw1rLgwZqFwRbBQIvgef+LGKy5S3gkYC1YGiML2PiwBvCBDeBAW+SLf+ExI1h2xiIsOHoEA3OH0JmYqXRCAW25kEY6FIdPdPBMOHgmpThyZh/o+HYQewjtBStxGwg+8uQIJpbPwFnUcmflT+kfGzy4ZB7mrlyMDR+9HZu/JuBOVz7JQMxd27fhBznANjtgDZg1wBYVH96eVIa2RN0lZc+raP6aQSx9+gjmHTVY2gWLAqBzbNABgoF9bTyTur8cn0EpRvZvAe1Mg8xZgkfmLMKvYeE2EDwwp1XLzen9C9bGT2/Alu/tZ+apH9aAJLA51IXOTteFt3bXQbvj/n3aPw94gOYOUqOg7jb1t93Hv5/xIBy4Dpvvrvmw1iMfeaOC+sdfrmInEG85IO/H3kdfQWBbxAuLuuA22CLeBASCgZaFi/4bEWDzxqsR4o1X88evRUKnKWDjnHQ0vfmIKLQFr8EtefSfrcKKc1ZVemP26M3V10523GshHBw2uQd0chdIawgT81fi14TgNhDcRiy0FwyAtClISUsnOY4DQgi2/3oP9j84hl137oXTzvmlpg3WMhMqgTVQ4LZ/McBWu/RBm684vPnAtuKM140Wf+cUJxNokD1i4Rn/c2zpIQEKhCtv7+vgGdTBM+HgGZRiwdhW0PYEyPBibJmzBO94ZBkmDpjA5NKOt/K2A2um/BkLTscFmPFH23jka3vRnQjbrBfW4qfyE++fcp0wz12jNAS2aFj0tA8PRNw1H9Si8AYATlD9f561EaDu+Da/1R76yBsp6G9uOZST4l9gKPyJAQTAp18dhkVbEadtsGVhwCYYGHDB7ax/hTcrFIguphtOOIi0QdRgzX/2yOvv5b6+w64+PvbFP7Cwhaf/+4nekJC9IHa549WcQSu4hg0/RTBn+xA+eORerJzcBTq1G2RgBPvmHeRBmoVfEwvOgmruLBMdEnLL638tWCob5uqCNQDywNbHsAb0wKSDchX5FgPBijNeN/rkr65Z9+Svrlm3IuKyqb2TydNQbjKBcsME6E5TPHj1ZoysGsCi4+bA6VCpZT8kmgKZcoApBxTAbcMtjA5ZsMY6OHX+KjyTUjyTOPiH65di/9gEFs4fwYqVczG+ZCK8Of1IuTent1rul8nSZxyAXb+bxJ5782eK6YU1OToi3kw7SsOJB5YF2DbBSR8ahBs3ISAUoMERs9xxSZ6XRoPFlSj++pdrvU2Kj5yz0YRD+1R/ftNq+Oda7qL91IrMI6B4w+eA695gwba82aI2CbdbLsTZlg9k1B2/FswEZSi2XwbWwq3Drj6eD200zLvwuLlYdOxczOwadyddlQBrFAhvrj7RxZxtFka82Z27Ht+HJ/ftwt/8dgQfe/kS3DZnKW4jBLfbFpx5reDezf4tocoUdSh237UDW3+2E/sfGnN3WvDHQ/BfnbaLgi5Yc6XkrvW5esphA8pw2eJ6cvTawGVjpeuDCsWaJIutfN4CrPnjYyud1p68wPk3p5+7awS7toxj7/4JzJ83B0tXznfBbfEEJpaVd3P66LT2J374CB7+7G6uu6YGa8U+Q1vfPw3qQRr13DV3SQ4aTEBY854BL9GJhT4pddz2oyFRIBjTxvp8f+q8+wv116g5ev1PjvS2BM5BXhYvfPntP7cCp8223LFrLf+vTTBgWzjl/U54w3eEf4NbUkXqyxuvFn/K7hwL2iiA1Z8+DgBwylVHYOFxK5SXNeKJAvGbqz/ZwpwdQxjZMYjtj4U3V1+yaoE7cWDpNCaXd0v/AcpSdFmjOz94O3b+Zo9gyXxYK3PcGr+E269992cB2+wKhfoywMZQAG3rPGjLeDtrB7isogSw51hYfOIwFjzdwsKVi92FIyemYVV477xoCGHOjhZGvPub7t86hV17xjB3ZBgrVi7AxBLv5vRLJksJITgdCqdLcenEZly+ayOWtydTdaeBrdzPx7YPTIeM5UGb47jLb/iw1nUo1rx7MACyKKS5z6n33N1PIw5E8BoYL+Nzz95Q6mszKk+v/JEEqAWKhERjW65b9sM3WcFYNtdlI4HjNmC7MDfQsnDsux1EYS0dDqVgXpQyQqA88Vy2+0eW4K2rzvEWDp/QsmxHcojHnB3uQrYj292bq49NTGHJonlYuHKud0uoaUwtp5UO8Yj113FAbBt7d+7G2K792P6dcUw/0oFnv+eVrhXW+KVEQqH8HwL9Dmw9FxJVWpftH6eloc0Vjf1hTViIdqTYu14gHppxNLoTDnaObcW+nRYe37QZp1xyBohtoTNW3SKS1owDeBezyQPamFg5hp3tfZiz3cayXSMY8eBtx4NjmDM8iMNXHuI6b0smMLZkEt1FLS2DdK0WgT1k41cnnoX5v5zBlTs2oAsC2zuAR133TFRms2c04w7mdhcstQhwxHuGwosw8RZPoAAlwdetV6UFgIIQivB+YtQNnTKGFA333KffCABe/IM13i2FOGCUFPNcCxdRdg0xgkv+F7j57wgsQgJgi4dJ3UcIa5HyMVjL7oN4UCwdGvVf8ecPOBYDI4PojE0VgjUKBJOorD0dzH2khZGdg5izfQhPPLYTeyf3Y+mShVh21ELMWzoHE8umsWX5Pm8SlQNrhgbXtirVmjuEwUUjmNk7gcdu3Qxr7iCsk2aAxy2gmxsT1whr+U2xCmfBWnY7sxfWgB4Etiq0Yt1rR58cvXbdk6PXrlux7rURwo+eUGXCW7I2xVopgIMnMXz2CGY27wIhBJvv3Ij58+Zj4UFLwpsf75+MTMkvV7Gb0y+mmDh4HKQzhqHtFpbsGsHcXXMwtm0KTz20D0ODAzhi1aHumLfF7i2yugWnwdNOF/se3IZvrzkdV+7YkIC1EpTRx20fnE7t89+G6Bg2P7rkcVyQicByXTdCPcDzQY36fwDQ9Fnj7ZiTfStao4YqtnxGlmJEFnXVvDAmounus6EBCxYJl/qwYw93POWmD9o4/O1Rl43ZYHp3ohdCosBhnz4ej7zh3qDmbQMjeHDVanT3jIvVkaySJJYp8m6uPmfHIB57bDv2TO/HiqWLsXztIkwsncHEsmnsXd72lilyYE1RYKp6SKOUYuSgRZjZO4m9W3bBunMnNk5sBgFFd/80rPk2gpkkWYdXK6xlVKYIa9mh0NmtnguJ+qpqLBvgAlx27jS8cXJolkCtw13Y5+wAtYCZloODOytwCj0Jdw/djX1LprDq4IMxNGcIybsAVq3oQpPDOwjm7hrByM456D4FbN2+GwMtG4etWobxxZMYP2ACE0sm3fubKiw0aTsOWssW4IX3/xYv27GhOKwpfoSiwJYMi/pj2Va9w6cqGmQKQqDRsGiQJ9ohyvoDALjh+Xcx+3TRd+I35L7hsrtVXppRAT3nW8cG2z9+4XpOnmOyK6HsJ+lTlURW+XCvAbe/w4c21+G1bRI+twCLEBz2Nm9lvyiwkcQG9ztfHNaiGw//0XrYlOL/HXYuHj9sNaae3AMQMXctthD47i7mbB/CyPZBzNk5hM2PbkOn08VBy5egdVALk0tnMLF0CtPLSe0LgUc1dMA8PPnQFozftQsnto/Fb27diCXPGsSjg0/ApgRk0MbE9ymcXRnX8kYu3+GlRGANYAHb7HbXgFnnsHF+ATLku2xS9QqGTsV6INFuSmHt1sl7YS+fi+6OcQx1LBxCD8aGe7bhacc8A/fN3IPtQztx9LoTAYdiZu8EOuNp16cKkW54C5aZ+QRTyyewk45jcCewaOcczNs5gqntbWx7ZJ/7hbFyJaYOmMLYkklMLJlAe4n4/U27lgVn5z58edkxeMfHF0HswqNXLHfNl/8duOodfig0iIUGThsAUEq8EJTvovmX28RllyTPT2CIN2s4cVfsi753crB98+VsyDMqrnO/flywHWUg3vtEeKDCdNUI/8oXuLWhTv0Axfp32+4M5QiwWcQFNkIItnzYxqq3emMpYyH3NKzJhEDj2eJ5j/jUsfj5nz2Obccfg/aDWwHLzq4ict/OgV1dzHt8AHN3DGHwqRY2P/4k9lCKlQcegINOWIyJZTPYs2wCM0td19CapLAnqnfRkmrNHcLgwhHM7JvE7seewuDjwLETp+CRx57ESWcdhrvs+wC4P+LsuYOwD5niA5sKrOXklsmTB2tRycDabFLPOmyAqss2mNiTjU7hBIQ8l42nfPdNIFlZ5Bm7QRb///beMzySrDzYvquDYo9mNHlmd2Jv0ubIZpKwDQYs24BBBkyyweDXn41NXLKNMdn2+9oEk4MtwAYsA2swCNgcZvPOrnZntidHzShOK3ao70d1Sx2quk+l7urWc19Xz0hV5zznVHV1163nVJ1aACCT+46/PHMJsdE1ZLM6s+vGGe4YpnPNSrpXdbNy42paV3eyMDVLOmgPSx7N0jnaQcd4B9FTUQ4fPw3Alk1rSa1LMdM9w/SaWRbWaEryFl3ZztH/OcXxn56pPozgfkuKfjvxsYXyEgVZNoDNt+SP1cK7PfXiwizdZFCcZStvs3D53b//aFn7N/zgsrJlVpjVF+xx3X9cpHDM6dz7B0+W1/3ehWZFTX+p2kTBXZ2G22vs+duwIWcsZdUMgcv9H9LY/K40xd9v/skaQKhF44I/3ULH2bmREpPLOIofrp6l/VQLHadbCY+EOXxsBNDZsnk9mQ1ZZtbMM7tungWXD1f3mujKdqKxNubHppk8Mcb4xDjTo5OcN7mTlmMdhDSN2U1JdrftIRPSacl9sUc2rGB6MEn6kInMK8la8U9mv1ZYaLLaq6HQyrK2XLJrsOwybPDr9y6USFvhweDHe1g9+1baC096kr+eKRkmvLWNzJk5IrpGFp1drY9ywdodXJq9jH2H5vj2i7fw7meOMDwywoo9rXStWcmK7pWs3NBtPIsuk63ZNW5lm2H5cPoMK8aM55tGxsIcfXyUTFbnrPXrYX3GuNt0zQzzVg+n13X0dJa1V3cawuaJrKkFMZO1QjQ0Nr0vWrxEKzmPFf6u5Wvl3vPFDFyJ5OWW73rZIxYNq1+8fcMPryj6fdfLHlauu1y56nsXL/2ilOw33lyzB9M/+Konueq7F5nEKg9s9lNZOxosPrUAOO+DWQ58LLJ4HWX+BhgtJ2wacOJTUTa+M70kax4PgZaSXdAhDOGOVjKzS5+hsoerH2ih81Qr+kmdoydOMxmaZvvZG9h85Wqm1y5wcu0EqTXePVzdK/TcjUZjB04yNTbJmbFJzjDPBaE2vnjOFj7wPY2t27rZ3fo0ezsO05oKLcqantXJjE2TPWP2HjvMmtVQ1pT7VLLIiaw1Mg0tbE7uGAUqfFmWy5v1DQhOcSZwJkWqNJMbJEtGCLVDNmkMwYXQaE+FGW7Zz9TCGb7zu2vYOXuCH16yk/ckjvFfyQlSJ04zdmKUrpFVXPbymzmzb6RuQ6WFFMpbphUmds4yce4c0fFROnIPpm8di3JoeIJUOsOPXj7K08kY92kh7tPhYGcUPaIRPpM29Carc2a/sV1aGPRKz0UGvLC6SrK2eFOB8RuFt+fr5G8mWLzzYLHYUvfyaUI9F8/84vRo2GqYza6UL+2PZ/2gWOAefsUjNmM1H5d9p/h6wMXdW/D2mVP8BWX5fuUnSF5cvRRY/UjNSb5e2EGDcDj3sKkSUYOl30c+E2H9O9IeZdUqlw+3hwi3h8nMp9B0nWw0RLY1xLZkimuTGa7Vs5wfSvKin3cyFQmzfcsGNl+9hpl1CxxdN0qqO5y75jU4kpYnP/QZWdHGnoFh5ufmmI1m+d3YKj4e38yKM4f451efxSsffJBjbeN0pEqGg3XQomGyZQ93Lx9uLMV0KLTGslbLGw0aNbsGDS5sTvn1LQs892MtVZJrtRoqthC4kh+LimBZpHz9dIT0+JQxC3jBc0U7UmFOREd52eMTfGznWfz2zAk+t6Ob80628pkTI0R0jeTEGZ6+dRcdXZ2s3LgmUEOlmg7hmZy8RWFy+xyT58wTnjhF52gHb183y4LeyXmTRzg3M89rO9ayj5Xs0uHfiQA66eQ8O155AafueoDpA5WzXrVC02DDLQUZ4MKTfP6y8CKxo/iXwqEpC8xmQbjke1cp/kVQ4UNTsOqK/7iSx1/5kErApuOigUuNH0r3p42sWiGXfecSnvhDk5s/igzQCGxL1KAgI1veqS3vyXDskxFTUStufqmuX7IG0L65lfXXb2PiyaPoIY1QKsOnUinOm5tAnxlFC7ey0HUWt7wxxOdOtnNo3amCu8p1wmcCJmkr2mjpamd+bJqJY6eZ2j1JcnyKmfl5shF41/oN/OWGDpg5wa3ZNdzyeILR1ky5rAFaWCO0og3S00ujK57KWhVsyZpqO5JdK6Xhhc1xlq2UCuehDde97t6T937DwyybYkccSlxhMX06TKg1QmahPH3Umg4xoWV5y75DvGPjev6iDf5yZYrzOrby7n1HmSDFyOETAET2HKJrTZcxVLq+m7b1K41nlU7596xSVTQdwrPG9ulhOLNtnk9EW42H06/csvhw+h2nn+Yf9/8GmReMEJlKEwqHOHlHomayVm0otJzFsc3c/4v/FN9kYJUZMzk4nnzVg5gbQyWLUJO0UsIhJQNsQtT3UXkh831mti+feu1uLvjWxRQfDYpt6SXxyuZVM8gPgxYWKb4xVOPUZyKs++u0C1lTK5tMzHLyzgN0bGonM58mtaYVbXQGLdrJr1evKn64ekcabZbASZrxVIJ25kYmGT80wpnxSaZGp0inUgDMh7OsCoX5xI6z+O3oGQD+aTLKp08cIpzVaNUtLlvQIHV0CrL5U7rXslYhmG1ZK+6beXatsqw5pZGza9AEwuaUxSybGRXOT4a0ve5e05W+YU/iFovl/tIKd3egL2TQU+XSFtE1whn4xMhJnp5ZxcfP2cyLpg5x3sU7efczR7lnYZqOVJh0KsXYiVHGTowS3huha3UXXatXsmLNKjo2d5OenmNhYsbDbXaGBmizGZiFDBp3tUe5syVE6EyaTq4he/4oWkonm9bp2r6G0V0Hfe+Tne+ZDe+1ur4SiuYuyWXclv41oWBFvmbI6jK1MulTlLQKHwHLtgq44N+vrF4IeOoP/c/WXfDty6v34zWPVC2zOLSsnFGrWshyX2pahTtArdqq9BzQkkib3pXh5KcjubYKSxQH0E1+UumKvU+HzvSBWdbfsI2pZ04QSqZ5z0IL6fYo2RVLT0apxXM77dCyqoNIZxszx8YZO3CCqbFJpsamyKSL+zkTzXB9SyefOOcs4nPHmOrcynueMS5Tac+EyvZ5IaHOVuYfzf1BqGUhW/loCJqsVW2vZNFyzK5BkwibZ1k2M3JRN1z7untP3veN60xXLlJLeVeQOF2DeY25/9IJXZUmrIHZg540NDpSYQaTE+x5fJ6P7zyLq+ZP8INLdvLefcf4xvgorakQoVzdTDrN+MgY4yNjhEJhVqzpoqt7JV2ru+jcsob0zAILE9O1G1W2QIOih9Mnz55DW8gSntZpWRvjxG1HGXvEG8mstqknFbJrG94brRKpYAis6No1szLmNc2SXuf/+zUmg2lOskTFqCXYKhQqaPOCf7vKemUBx/6+/Da/ze+1MsfqWYjSFpW2qTR7ZRkNlL4zdDj/m5ex93WPmqxS/c4xyapVI/cHwoZ3phn5dMRUGPISN/rZCGv+KqXclZIflCsd/dlpZo49yjlvjDM3MkW6zbj+LlCSpkHLqk4iHS1MHx7l1DPHmBqf5MzoFNls+R/NWXTmo1le372Gv9+5mezEQR4Mb+Q9j+9nODNrOgRaSmZyjoUHjUs9aiZrFmUqypoFS9m16rLm9LTS6Nk1APXbwpqQX99ib4hqw7VGZu3kvd+4zvyo0Qte9aCg/aXZV9GTEVq3ryYbrvzBb0+F2ZOa4w+e3MfAfBf69AgHn7iMq+cvJatBKlR+MsxmM0yeGufwngM8ef9unv7lw4zsOUImnaFjczeta2KLZ7lsNovmwTP/nJDPvIXCYbSWCKkzsyS+clppOFRXeFWt7Cla8UsrX2T22vvqB5bm0yp4oenl5as0qfIya6u8bZO6lm3qBS+LNkPlL9M4+TdFYTv03MvVNpVth0LbJfvBrK19r39coS31bS2us7SwVNYWn8Jhl8UhUPuyBjA/kebE7eNMPHmaUDRMS1f70nddjQlFw7SuiaFnsxDSaF0To2NzN5l0hpE9R3j6lw/z5P27ObznAJOnxk1lLRXKktXgyuT5PLNrB/r0CAPzXfzBk/vYk5qjXUHWQitaSR/RUNmvnsqarV2uF/0Hzm400IH7l2l2DZokwwZusmz5LyYHVBwaqmf2bYnEq3cBcOtoB2/PrieEbpply9OSCZHVdN55+AhfTcXpWdnJ9OFZbt5yPQ9rjzAenaY9bf4lomezTI5OMDk6ARp07TWybrHulayMb2T2xASzk9Os3LYOLaQxPzZNdsH/v4z1rDFXWVd8PdOHTjNyX5KRX5/xzqPKAhUvOPn31TMPRnbNKWrHlnWp3BpPdshSEFu9qmq9ahHNh43yy/IZNbWemXXJ3Z62l1Ur/aXq+2cWxG5WzeL7cN1fpzn92cqni9HPRq2zbI6yagXlS5Khuz95gNj2dra9fAMbb97G9OFR9Jk5siFjug5nNmnRg9x0GwChlgitqzvRszqTB09xPHGEdWdtQE9nODl8kKmxKabGJ5U2czaSoXuhg0sXepjYN8fqs1bw/IdbebrtEK3a0pQdVToHU3Psu+IgXAFnf36nddGCf0sWWpauEqysnHmtcllTbrPKd6sqzZBdg2WeYQP49S0p7GTGFrNspcOjVVMuyjkZz8jLGsB54RQt21aTVbiwKKRrtKVDPNmS4L7IvWzYsoLx/Wmek3022xY2MRPNoCt8oKfGJjnyzGGe2rWb4V88QOKRp9j78DBPDD3IoQeeZmbiDK1rV9C+cRXhNkNYOs7qJhJbeoRYNlvyhVDwe+Gkz/mfi+6GDWm0rl1BKBpixc51HPzhQR7+wFGO/miS1Jls9fOmZUqtOINZ6b1VkTX/qH7MnfNvV3twSJa38cyrH7RX1f5KdRbfKzddUu/Lvj96xHHd8qJLv+z4xqVqMRaz7IrFzRuuuNiK0c+a/OHhsazlSR6Y5YlPH+D+v97FzIkZImu66NiyBh3jMU6hlojxfRAOoWdyj9IKh8imcyMFmrb0MxBd0UY2a/weibXmvova0MIhOs5aTevaFcxMnOHQA0/zxNCD7H14mFNHTrL3kWGevPcxjjxzmKmx6rKmozMTzbB1bj03zl3D6b3TbNrRzYOdj/JU+yHa0iFCiqIdWtnO81pm0HXIAkfeuq/CnlTd//7LWnl2rbqs6ejc/6nVlfvW5DT0kw7McHot23M/ZpbhsP7Q5IUtL3BVqfr58/YPgEJZy/P9+Ri3zK0jlM6SVfwLdC6SZUWqjSuylzF3NMza7hUc7NzPky17iGQ0wrb/gi+mLdZOV3cX3RvWMTc7y/iJ06zZuJauDatpW7+SmWNjZObTxLbmro2bnKFtzQrQIDU1S6glQjTWRmp6nszsAqsuOpvjv3qGrvgqJp4cZ+bwAlpE4/B/T6CnMP5EsZzN3PvPgv/ZtUKs+5949QOmy+PfvtqztgqX7HuNmrDt/JbatWmqjHyi/M1d/y7nGbXSpfvLZMycHd+43DKiWuO66aoDrzd/PNj2r+dlzq6omTZuuljHuFatGkVZNkeyphf9WKmmFtKMIUlg9eUrmB9LsfryLto3tgI6W15yLiN3H2Tjc3cye2KSyadHWfesLaRn5pnae5rY9m7CrRGSh0aZODHBmi1riKxoZ+LQSabGphg9forVG9fS0tHKxMgYc0l3d8VnNJ10WOeC2R1smdjMqbFJ2reFeaz1KZLRedrS6jkUDR0djadXHyhbV5hps5Q1y8RCBWzJWm5NnWWtWbJr0ERDonmcDo2WVtDKlrp8z80bqFDAeZtmsgZwQXiBlq2rWTgwqvz92ZYOMRue587IfVx69oWkJjvoOraO6zav4JHQI8yFM7SqpO4tmEvOMpecZeTwydyXr87U6CSRPQfpXrealJZl4thpYr/cyKqzVxKKaDx16wnWXNtJx9ktHP7+OKsuaWfVZe0c+v4EK3aMMnJPEj11klCLZsyOniMfv1b4m11T2A7PN1X1S1qNJVmr7x+NKqKWZ8c3Lmf/6x5xHLV6Uaf72DyTYaNhy1V2353FoVHdSW11WQMMWctdvjX2iDENxvThucU/yg587wQL42lGH5pk4vEzzBybZ9PzJ5g+MsfUnmnW39iNviLF9IoxtPYoo6dGyKazpBaWrm0dO3Ha5jaYMx/O0pYJc8V0D9lDIRY602R2zHFv+zOLoxrK6DraynaunRlnTtdo0fSi4bIjb93H2Z/fGThZU2rT5A8FpzSTrIEMiS5y2y3FJ9fyQZ7iJZZDo6romDVSpVD1Q9dK1gAuiizwzpN7IRxCsyEukaxGNKPxUOsTJFY+xeZN3cztD3Nz9mbWpbuZiVZ9RIAShTKVTqU5dWyEiaOnIRxidvMkBx86yL5vjjJ3Os3Rn0yy94unmDud5sSvzvDUP44wc3iBk7cnF59YUChrpfGDglp2TfE4sCiSeI2b7FpxQPUjUQXvIhknB3uxzFu36JOXXTWNaf5tU8pSJq2YA69/3BtZK2m49NRs705Qh7KWeysr19aLyheRT7JqsDCeRtPg2M9OM3NsHjQ4/stRpvZMAzB2ZoTZzTPoIY3s9ALzM3NFsuYVM9EM6xZWcsPs1czsTbP5rDUcXHeQRzr3Es1oRKrc2VlKCOPpNd/oOklbiazlsRoeraesFWfXVGVNhkLzNKWweW3V1vJm4FjarBqp+NkxP3knXr2roqzluTg8T8uWbnSbk5rmp/5ItB7m9tDtrN3RxukDMzw7exPnLWxVu67NKeksmclZWq4KEbpmHNqrCGIAHuDsfCjUhqTbc3lFyoPaasIPsanYntLZvbgKQRI1in7xf/dVEX7TUsW/qUjb6D/YHeYvkDXVstVW5aSx6LKf3I9ah07LTfO0XdtGZnIW0v58aeSvVzt3djM3zF3NyL4p1p/Txd2tu9jXcZyOVNjiRpnKhNbGOE+bI6mHKn7dHX3rPo6+dX9hh+zjRNZMMJ9zrVqzzj8NzZZdgyYVNqeUZtnMKDx5bbj2j+41X+MBNs7bKqKW58roPK85to/wynaweEZhJdpTYUYjU9yh3UnL9hTHT06wdfRcrp6/mHRIN536wysyYzNEd0YI3zAO6+r/bFP3uJAzl4fZUnbNPKgjSauZqOUlzV6D5V2s0PGaiVrxPldh+9cvqV7IsgMWi8udpnIdzyho3EtZq1A2tDFLy/MXaDm3jcyYf5N9p0JZ0iGdK6bP46wTZ3PsxCht52jc3foAYy1JpSk7StF1HS0a4i9mD/OjlceJaVmlk/jRt+6vsOtU9qlNWasQUjW7ll8g2bUlmlbYnNr1bbeklL+sdWB9TtpO3vfN64rX+PCNb3LStrqYvBLv7hwn9QiQKfnrU5GWTIhMSOfelocZ33Sczo5WQodXcFP6emKZduYiPkrb1ByhFWGiN8+i7Zz2rR03qGXXKlw+6qGcWQ2HVhI0t5K277WKd4jaxUE2DSqJmlJhR+wvneS2iqipN2m9/QfeYPK80Wot6FalKvdKLctm8SQZi8Ydy5ppV83LRs5P0/YCCHdFyEz590zkuUiWWLqN62euQEu00NnRztTWCXZ1PkkmpKtN2WGCpmlEz+7mopD9Ydujb9tvstS+rFWtYFLc/lCoO1lrxuwaNLGweYLNE+bJ+755XeVchbcCZ30ytkbXIf5vV6MvaEQ3daFF7f+VBxDWNVrTGrtb9vJI+4NsPLuLyf1pbs7ezNkL630dItXn0+hzaVquB+3SKXTNn3YUe1P0snWjgZmY1WhTHDVZtYJ6tJ3fUnskFQ6zaZaxXIuazo5vXOawSZeipmY1JvWq9Us9f2IXa2lbOrnbul7NIkzVhSGIXpOi7dmt6HNp9Hl/5n/MD4GeNbeGG+auZnzvDBu3reaxlU/wZMd+WtMu7qwPaYRXdzD9v2O88iubHYUoljZn77N5reqyZlnAQtaEcppa2Bxn2d5nctKtcIZbXzQ0Wq2KN2doJ7IGuXm3AH1fB3M/zUJGd3wDbP66tsPREe4I3cHK7RFOHJniyvmruXj+XOYjOhm/ZErXyYzN0HJxmPAN42hdXt+RaWVT7t+7De+J+Chm1fu389ulU2k4DqVSwBkOs2kWwfBC1Gx3Rjf/xbGoFVTa/rVqw6JqkuNYIXVY83Ynn7mCNpTe3golFGVNW5Ol9XnztF6WGwL1aSqrjKYzH9G5cGY7l01dxPGD43Sf28E9bbs42jrq+Ho1AF3X0TNZ5nbNsPCQEaPSJLmVMKStyj7Qy34w+a1kaZWQXee/sPw8WSZrS0h2rZymFjZwK21VviwKvnvy0jZSNDRqXaX8Y6B24ku85gHHsrZ43VL+HHC0DX1KQ4s4y7LlaUuHSIZnuTN6D5ktZ0hOz7L65CauXbickA4LYR+HSMdniGyOELphHG3rLOqi5ZGIFVQ5+ff1eJ6h9Z8FCcW50CzDuSvkgLyk2Ytruze2KrjdzqX69iOVi1o1jGFRNTlVORVbxrFRZynLVty4t7JmsqNyfyy2XJciuq2dzLh/16sthLOEdLhm+kJWHu4mOTOLHl/gno6HSUbm7E3ZYYIWDtGyeSX6fPHpzLm0HeDo2w6Yr7Qla5VXLg2Fqsqa8a/ImjlNL2zuUTiRl6yqJG1qkc0Fwo2oWU3hoJ9sBQ20dneTt0azIcJZjYdad3No9TNsWr+K1IEWnp29mdWpLmY9mvrDjGxynnBHC9oqj2/H99Dr8mx4j5upD6074LhbShVdbnTVPuRFzWY1u71xZHVu0E1+stG2l7u6RNTKjxz1bhXWWfN21c+cvvif2lttV9bMymnoIR1SkPZR1majGboXYtw4ew1zz+hs3rCGIxuO8EjnHsJZjWjW3Wk21BFFi4RI3jpF6vFyHznr8zs56/M7HMUukzbbsmb9Zla8K7SCrAnWLAthc55lM8uYWJ+41j+rYGjUwfmtkg+4zqpZkN3TSeqOTrKjGUKd1S4SrkwIzXiAfOshbtPuZN32Dk7vn+XZ2ZuJL5zt63Vt2VQGbf0C2obc3aMqsuWhjJ38ePXsmj1ZU5czO13d+a2rFCs62xH7XvuQWsGiR3upY92rCn2tuagZ7H/9YzajFYiaQqXqw6KUxVI9DZvGsaijIm2j/9Cq6KB230friKGzMrS/ZIHo2e1Lj6vzkPz1ajvmNnHT/DWMJKbYEF/JnW0P8EzHMdpTYUIuJ1zXMzrpyQWmf5Alvaf8dF0oOq6lzUNZK8Q0u2YWK4dk16xZFsLmH+Wnzby0jdxfkGVzIQL5KsrXHRWg/Nih0RayD3aRnU15MrlsRyrMqeg4t4fuoG17luMnJoiPX8AV8xeSCuukQz5IWzpLqDNC9OZ5QufU9u5RFVmzprItOpUz1UdDWfcjWFSWNC/6W8/ttidq1Tjwht2molZ+VKl3zYvOjf5ja5USFeKbrrIuH+lJ094bItQZNuZZ85h0SCcV1rls+lx2nNzG0aOjdJwb4a7WXZxumaTDwZQdZoQ6o7RsiqEvsDjEm6dQ1vKc9Tn70nbW57Z7Lmv2hkKD930TVJaNsHmbZbOi+EutSNrMitn8DrQjbfFvX6XekKaDZjwkObyqXb1DFWjNhEhrWe5tfZAzm0eIRiO0Hl7FDQvX0J5p8WXqD30hTXZ6gei1GqErzoCP04vYZcN7wtgVM0dfY8oV6ydoO795hVI5R9k0WzjY/lzxHV+/zIP2cwEdbY56JT+yaqWoD41WbUxhVYVtj+hEr03RdlMr2ekF9AXvL8WYi2Rpy0S5bvpSovvbiEYjzGyfYlfnbtKhrKtH9RUS6mojO5kiOTgDKQ0K7i41k7X8r3akzU9Zs6pa/GvxAsmuVWbZCBvUStpg/bNea29CXRtnahVp2/ntqyxCWWiBDvpUhNTPu0jvTxNe3VG1DRXCukZLWuOx1j3s7nyUTWd3kdyvc3P2JjYvrPFtiDQzNkP0whDhGybQVvn5PE/72TXPxMwqGNbzoBlTaQQzg1aIo2yarc1ysA/Kqrjdh0ufPTcd2f61i01LHXjjbos/CWw048OxMlaWZbP7nlr3J7QuS+vzF2i9pNWXCXHzQ6Cb5rq5ce5qJvfOs2nLaoa797C7Yz8tbqbsKCG8uoOFZ+aY/XmYzJHimJVkLY+KtDmWNUXKsmsia65ZVsJWS/LSNnL/tywm1K1y4Fc4q1tJ285vX2W6zkoSynowEyJ730pSD2eMTFvE/eGRn/rjYMtxbgvdQff2KCOHklyXup4L53cyF8mS9WHqj8z4LOH1EVpekoI1qbLhBHso70FT1r8n7P7U55nl+YTLudKsN0vxjx1brTjomJsYZgEdhXHark1RW5Q1e6x5u92nj1R5X+2UB0LrMkS3d5IZ934INKvpzEWyXDCzlWtmLufE/gnWnNPJne27ONQ24mrKjlJCXW3M3j3D/K9C6CVXd6jIWp6zPrfdkDKLdY5lrcLbYDkUqtZloQrLTthqlWUDK2krxOYZuKDozm8Vi5mTa9zMeqADmSdizP8iApmsZ1MWtafDnAnPcGf0Xtg6w+jEGdaPbOFZ85cB/kz9kUnOkxmbQQvpBSchJ68lCpee/Hj14Zb173FwLYsjOatcWH2iWhs4vHFgsTpWPa6y4bal1XtRs7/FbkXNel9s/6p5ls12Y0WfETss1Vnzl9WlzciyeStr2sosoQ06WR+eXpD/brp6uoc1R9YxOj5FOJ4xpuwIz9Ke9uZ6NQBd10mfniX1aOUbDEoWmkVa/KlU2oIha8ULJbumxrITNqittOWxlrZC7J2p89JWduefB5KlT4aJnrUKzcHzRq2IZkNoOuxqe4zj6w+wfs1KsgdbuTl9I6tSMWYj3l5vooU0tPYooasm0TZbn0icqZsHOG7EupLyXZqOKBA0E0nb90cPq0apgaQ5REHU7HThwOsfwy9Rqxbv4BufsNmMk52rF/3o6u0x3abqGxremqH1eQtEt7Wgp7z9DpmNZFi10MkNs1eTekZjw7puRs46wYOxp9B0XE/ZUURII7K6E30sF1NbUhunspYnL21+y1q1roisuWNZCpsb3F3P5oTKZ/TSTFvFanZOGvNh5n6xgBYJu56jrZD81B9PtRzgzshdrNu2gtEDc9ys38SO1FmeX9emz6YItYaJPjtN6IJpzyRsRDW75tr+fNfGKs0XSpovDVAxcK022WNRK4vtrjMVV7nql170g5PKSx6fW7NaKcvWVh7OtI3KRC9J0dYbIdQWJnvG7pCsNfnr1bbPb+SG+as5/cwZNuxcxb3tD/J0+xFPpuwoRGuPokXCzPxqlrnbcnF1reQILOqgZc+t8EvWCinKrvkoa8uVZStsruy8KMtQ/UiuPjRquwMWL5fVS8Jk97WTurOD7Fia8Epv7h7N05EKczI6xp2hO+jcDsePTnL+5IVcNn8+C2GdtIfXtempLNmpOaJXhwhfMwWt7v4KV5E1o2E7UV2+pxWwNxyq43aosxI7vnkFVbfPldTawLSauqht//ql9tpT7pTaqsK+bfvqRQ6bcfIe60U/Oj1KFqXNrqzlvhsiV6Zof+4KslNz6CnvLqlIazoLYZ1Lp+Occ3onx46MseKcKPe07eJk64RnU3bkCa9sJ3N6gdmfZ0g/XXonaPFPZr8qrChZ7a2smQ6FKsiaG5Zjdg2WsbCBi6HR9xecsHWUBM57aTPDo5N+QVX9VJT03atI7fXu7tE8rekQc6E0d7c8wNzZYwB0HF3DDQtX0aJHmPf4urbM2Aytl3egrVXIkioIbSXWv9vqS90/MXM2HFoiaN47Wnl7Vott7wqXx3eFxr17Vxx3ynKVnZ6WDYsuFneyhQV1qhwuKlm2xZBWbVjWMTJPWhQWjk6ge/iHxXw4S0s2zLXTl9B6IAbAwvZp7u18nLlQhlaXj5gqJbymk/nhOWaHwmRONKesWS2UoVD7LGthc0ORtBWiIHD+Sptlpyq8qjAXIrOri4VdWePuUQ+va4voGi0ZjUdan+LprifZuHkl0wc0np25iQ2p1cx4+EgrXddJn0oSWr0A+RsRbO6SkU+o9sc/MXOHt4LmesscS5qXouaiO65xKmqU/abUlJN6pXU89PqxfyocGlWLqkeN54O2XdGBpmlomjffRzPRDOsXVnHT3DUkn0mx6exunlmzj8c6E7RkNCIeTdkBxneR1hJh9pczzN+hQcGNrfriv40ha9Uwu8RFhkKdseyFzXdbLxC49de8xuX1bH5RTeiMD1z2qU4W7tPQ01lP/6rNT/2xv/Uod4TuYvW2NkYOJLk5exPnz29nNpoh68EpQtM09IUM0UsjhG+aQFttd442tT6sf3dwPlY7v3WFp4IG5sq0X/GGA8sAypUcUEXUnCmgeg3jgew26lc9V5vXtRwWXSzuZB8W1FE+hIw6q//Szh2bKv3SIZal/cVztF7cSvpU0kZ8a7LozEYznDezhRvmrubEvgnWxldwd9sDHGg/4emUHXk0TSOyPkb6ePFyveBfkxUm1EfWCgtUHgr19s+f5ZxdAxE2wKOhUUXy0jZy/7eu8+s6IX/IfXEvQOvW1WgRb6/jAGhPhZmInOHOyF2Et89zfGSMzSPbuHruErIapELeDJFmxmeIbIwQfd4shLK5a2Kqv0Y+Ub39esma5XCox4JWHs6mBNQqm1YxntlvNmM47laViiai5rbHB9/0hKN6zrJqxaVUpK04y2YdVUdDnwctGiI95s1ca6lQlqwGVyYvYMOxjRwfGSV6js7d7Q8wEZ2m3ePr1QDIPVFm5o4J9MkqTy+wWFRlRclq72Vt6umfKly3Zh5IhkKdI8LmElfStuvbRkq5KAPi5QnKe7KH2pi5dR7QCXW4e1i8GS2ZEGhwf+ujnNp4lO5VMTjYzk3p61iR6fBs6o/M1DzZiTRoBHl3V6HwmPE0ahVVciZSO75xuc3WvcI/UVN6ALtKqyWrveixc5xn1fzqDUBoVZbWG9KEOlvxYhR0NpJhRbqdG2avIJsIs3pVjLEtp3mgcxi03HeRxxjfmTozv5hl4f6l+CJrggoibDnc2Ptt7884/qpalLZCdMolLkCZOP1QG+k7YqRH0p49e7SQkK7Rlg4x3LqP+1vuY+O2Lsb3LXBz5ia2zW/0ZOoPLaQRXt9K5DfHCG2rngWoe3bN7HiosgtUn9kJKprkh0iZxXdRVcGHap9RUwtv8avtRrd9xebdoqYdWvrRSVatdNXqv1DJspl/jyxG1nTaXpAmurOV7Bl3k+Pmp+zYOrueG+auYXTvNJt2dPNA56M81X6ItnSIkIfXq+UJr2onfXKe2f+FdKIRZY1FWasU2A9Zk+yagQhbAW4PiuqZiSUcXc9mKnH1ETl9PErmri4Whr2/exSWrms71jLKbaG76NoR5sSRSS6ZuYxL5s9jPqKTcTn1R3ZqjnCsFW1z5QdXq8iad5iJWeXtVJ2wtqQVG1k09cyQ8164qF60wLyY4+B1FTUbDS8WN69z8E1PqnfIq6yazf1WKG1Lm7P0GchM664fO5XRdOYjOhfN7OTCyQs4fmiUVee2cWfbAxxvG/flejUwng06t3uW2Z+HyJ5uxGHQ4kKL2bUyWfMekbUlRNg84naTodHSU17pwVw2NOoEnfqJXDpE9qEVLNyXJRRrRWvx/nqPtnSIufA8d7XeT2rLFHPzKbqOreP6+SuI6CHXU39k51JoK9Jo69w9JN5+ds1CzHx426odh+alFAO66o1X1b083msrapT96qBhi5O0gwCLm26rjsJqlSxbWdXcHyrhbRnaXrJAy6Z2V09emQ9nieghnjV9MbGDK5mfXyCzc557Oh9lLrxAm8dTdgBoLWFCsVZm75hh4a4QpBpX1sqGQk2PY/NgMhTqDSJsJbixeUPa7J0WPZE2y4YspMDjM1F2TwcLt0fJzmQIrWj1NDZAJKsRzWg81PYkB1bvZdPGVczuD3Fz5kbWpbrdTf2R1QnFIrS9RCd0dvlJxV12zUrKvBMzq+zajm9eUeXU71DQTIruf90jKl2t3o5K+xUWOt+leUnzT9QOvGG36QlOt/hNicUqxXW3feVC0+LlWbaCesqHZZV+mq5W37axf2pf+u7KEd6SJbK2jcyk8+zaTDTDuoWV3DB7NTN702ze3M2h9Yd4pHMv0YxGJOt9Eie0opXsTJqZ/10gtbv4VGsqNxV30/KUNcmuFSPCZoI7aSs8wVc/KerAugJp8+OPetNGLUXCmdTpx1tI37WS9GF/h0ifaT3MHeE7Wbejg1MHZrg5cwPnzW9xdV1bdi5lTBHQ4qz++ndpvkqZN9gQtNLi9ULx5O+8m3lRcxzAUUW/RM1pD/zKqpUuXP0XqsK1VCe0MUOoSyc7U/myBetIxvVq585u5oa5qxnZN8X6c7q4q3UXiY5jvg6Bpg7MM/vzEJnDxfEtZc0SkTXBQITNAn8OltKTZvlBfionbTZPr96jInV6SQ+TYTJ3rWTh0Qzh7g4Ieb8L21NhRiNT3BG6i5btaY6PjLNlNM5VcxeSDumOpv7QNA0tEqb12WFCm+cWt03pRoN31e47RfW42PHNyxVLVgjuMTu+cZlaQdM+lC9011WvRM2ovP1rF9usUf6b/QCV61pl2cpETUnWqvRVUaxBTdrG/+/SH3yRrVmim9shY/+NSoWypEM6V0yfx1kntnDsxCht52jc3foAYy1Jf6bsCGmEuzuYfWCWuV+E0KeKh0DtyZrCMVIjWbMKXEnW3CCyZo4Imw/c/v6sjWPY+FCuu+bVFW9CCITEmbHYoSWJyz7awcIdOlok5OmD4/O0ZEJkQjr3tT7CxKaTdLa3Ej4Y46bUtXRm2pmL2Je27EKa9Olp9Egw9qzK+21rstpqDbgK4pJaSpqHouYcB/WLTszO2z/4pmEbolbUsI3V3nyGQuuyhLp1Mg4e6j4XydKZbuP6mSvQEq10drRxZusEuzqfJBPSfZmyw3iAe4iZoVlSu8yyasU/mf2qsMKkiD+yVkjX+S+8166syXVr3iPCVgFXQ6MfyNq2rLy0ndr17etUKpmFD4rMZQ+0sXBbO9lRf6b+COsarWmN3a3P8GjHw2zcupKJRIpnp2/krIV1todINU1Di4ZofTawYYGRT1av6za75uz9c/Aue3aAeHiUKUoapkscNBYIOXUQY7GKd59sdVGrUNJ0tVofVbNs4S1Zots7IaP+B1h+CHTz3BpunLuG8b0zbNrWzeMrn+CJjv20pjXCPk3ZkTm9wMzPsqT3Wg2BNpasFQ2F1lDWJLtmjQhbFVxLWylVznlL0vZv11lXsndar5vMjUZJ39lF6umUr9e1HW45xR3hu1i1M8qJw5NcOXMlF8+fY3vqj+x8mszkHJ97jXd7yfn7UL3Wjm9enhv+LF7m7Rvu4ZFjGcpa0jx5J1wFcSIuHuCBqG37Sk/R71u/3MPWL/dYlC5t3O5q9T6qlHz0TIbLLsXWjQb5KTsunNnO5VMXc/zgGN3ndnB32y6OtI76er3a/JOzzP08RHZE4Xo1i0VVVpgUEVlbboiwKeDrQWRyTjaXNsXKLlTAl3PPQojMrhUs3J8htKINLerP1B/J8Cx3ttxHZts0Z6Zn6T6+gWvnLiOkw4Li1B9Gli3M249muGO88jQf+eya+33p8l3QjScILD5FwFNBqx5s/+seVQ9r2Y7VErt4efR6L2oH3/iEjWbd7IniuvZEze422z/S0XW6/7+ZimUHR+bZ09EBabXP7kI4S0iHa6YvZOXh1ZyZnkGPL3BPx8MkI3OeTtmRf46yFg0TWtHG7F0zzN8RQp8XWXODyFp1RNh8xjTLVg0d1l1dIG22Px/+KIQbucs+1cHC7SGy82lCsVb0rLcf+mg2RDir8VDbExxZu59N67tZOBDh2ekbWZ3qYlZ16o/5FNnZBWaqFLe3/R7pcZXqao9+qhbUe3Z8/TLLdryRtNzLU1mtUqRk0bavqt14UD2ud6KGjjeihtVqe58Ao5nqdfbOZHjgTJrMWGWpyzMbzdC9EOPG2WuYewY2b1jN0Y1HeaRzD+GsRjTr4WkuHCLUEiGyLkZ2Ps3Mz+dJPVYe33NZK3qLgitrct2av4iwKeL50KgNTj2QkzaX53sDrxRMLVrhK3u0ldSdK0kfSxPd2AVhjVCnd88jDaHRngqzp+0Qt4fvYt32GCP7Z7k5cyM7589Wuq5NR0NrifCmxDy7ptKm55d1ZdeuebtPvXuvVYLXgvITjPvWCyTNdTBFYTE5gRWrp9um3WxEsah5elNBWRH1Hb7koeV1rLJsPzmV4rGOGHqV7Fr+erUds5u4af5ZjCSm2BDv4q62B3im4yjtqTAhD4dAQx1R0GD+gSxzDyWZ+0WIzMHy+L7ImkVZP2TNrJ7fsibZNTVE2GzgXtrsnV3yWTbISZsZnp/c7SiYA6bCpO9Ywez3IfW/K3x5HmlHKsyp6AR3hO+kY0eWY8fH2Tl+HlfM9ZAK66RDlfuuzS6gZ7LMZSh7yPS6d4FnO9tXMbNqwOPQDnriulHPJri1L2rl2+FSyt3EKK1rW9QqlLRcrd5PfTGOdZ1CacvmYu+ZyZA5M1exXjqkkwrrXDZ9LjtGtnP06Gk6z41wV+suTrVM0uHxlB3Gc0BTzP6vTuopjfm7Q2THy4dATcWm4q5WlbXyIH7JWtd5L7y3vITIWhAQYbOJO2krPOjVTqRK0maGx55lv5EKLx30yRD6bIj0nTFST3l/U0JrJkQ6lOXetoeZPvs0LZEwLYe7uH7hKtoyLRWn/siiEenuIDHr4gkKeWryPlg1FozQnkgaXkuagqyYiFqlJbaadxOjtG7B7lGva3e1el8XSy79Y4u9sxmYtp7KYy6SpS0T5bqZy4jubycaDTOzfYr7O3eTDmVp9XjKjvDqDhZ2zzL3C43sKfOv/yWpMZE1S+zImmpNkbVmRoStxhRLWyHWZ/VCafMEFa/yndznNBUi/UCMhfuMx1pp0bBn17eFdY2WtMZjrXvZveJxNp69kjOJLDdnbmDz/BrrIVJdJzub4ulpQ9jyf/kb2bXCcgovX6hBYxVDGwv3v17xhgM3jXu2eQpBLM63nohajoNvesJljHKTdKBSNlfbVEEd7DwtJZ9lyw9fHp7LktW0svR2fgh001w3N85dw+SeOTZt6Wa4ew+7O/bT4uGUHVo0TKijhdCKVmbvnGHurhD6QjVZM11hUSMYslZIrWVNsI8ImwNq+1eB8eFed/UfGjch2MmyuW9W/eWSzNPtLNwWJjufJrKm07i2LeL+8MxP/XGo5QR3hO9izc5WTh48w7NSz6JnfgdzkSxZk6k/9OQcw9NpI0b+JFBzqTVr1KeGqzbh94b7IWmFsRWarriopm+6CSaipnskalitdqCCS//YwCifyQ2BznSVZ9uzms5cJMsFM1u5ZuYKTuwfZ+25Me5s38WhthHvpuwIhwh3t7PwdJbUsQVmfrFA6nHr7yFnslYFX2Wt+D1dvMnAgay5RbJr9hFhc4h3Q6PqFEtbjU7kqtgVPJNX9mgL6Tu7mPuZxvyvosaD2Tu8uSmhPR3mTHiGO6P3oW2bY2z8DOuOn8U1c5cCJVN/aBp6KMTBWT3/K+ve6Uk3KuCTCas2Z6OAnZ5t//qlap2o9WFs0Z6bLB9HcAAAQtVJREFUrd321Yu86JkJPoua5fuvxqKjOXgGcb589/83DcCZjPHc0EjB9Wv5z+Y/XHIpa46sY3R8knA8w93tD5EMz9Kedne9Wn6ajlBHC+g6Mz+fY2GXxtzPNTIHrL/mG1PWlnArazIUWntE2FxQX2n7d5NMWyUjagz0yTD6ySj6ySipOzpJnzRuStB1ffGL1SnRbAhNhwfaH+fE+sNsWLuKn/W18F/PvZ7z2mLMFE79EdI43dbC6ILuoazV8f3xQNC86alfkqYYqIKk6RWW1IeCPtgStXxdtdCKK6xLOha14jprc0OjG7MZMq3GI+2yms55bTFufd6NvG5zCz9+5yZGNp/gwdhTaDqup+zQWiNomkZkfYzUiXlmfw7pRD6jbj0Eaio1FXeDc1mrvHd1xbdMZK0ZEGFzSfCkzYpKslDvE5M5+liE9F0xFp5M0RZfBxnjwcpuyE/98VTbAe6K3sPezAqubZ/jrt+6nqs7VhINaWi6cQ3LpzeFWdNi5+0NyD5WarpWglYS0fPdoRDMok3rLfenG46CORK1CqU9ELV8aaOKk422fiNWhDWuXRlBn0uBblxhesWalVwROsbezApe+st7eLrjiKspO/J//IVXtpEZT7HwlMbc48Y0HdnTBTFNNm1JaEy2wbpFhU6Zl61cU/XAEFlrFkTY6sztHyg5iSl+/zmTtkpUk406iV0qRObBGMmBWRZ+tpLUnoWlO0rDzj/7HakwJ1vGeMkv7uSu6RbG0xq7J8+wkM2ioxPubOH4fDaXXQvovrHqms1C/m6Fn5JmP2DlPeCiK55sYLGoKZ+PS+tWKmJvhXUrjrJqJm2V/Nr959OMpXUia2OgGTcRfPvEEf5ib4qX/uJu7pkaczRlR17SQl1tALTuXMv8njnmfhkh9ajG/K9DkKr8fWIpNG5krWg3NresCe4RYfMAt3813P5Bi784q5yXvJc2FVTlxVup0UeiaFmN9L0x5h9JQyREdjxEeE2nMVQasv8WtKZDTGQz/O6d93LTT28nHdaNC5ejYdKnkly3KuKqz57jgZyZlXDCgdc/plYwAJJWWNureG5E7eCbnrTuXYGoqUVVFLWKx4qNVnRwnlXTLX8tZOCSGJcszBFa0QpAx0KI7x84ykQmRauNR0wtSlpnC1pIo3XHGlL755j5cZgzA+PM3xZCn1bffnuyZkegzY/OinEbUNYku+YeETaP8EbaKpxELPynPtLmBrfCp5N9tJ2FH8VI3xZj4fF5wh0tZJPGfEm6rhs3DShe8xbJakQzGtPpFK0Z4y0Md7bwmfM7eelHvX/uqRLKrmtfzgKknwrY6HWFYuai5rJLnuxNN6KWr6QWXnFF5VZ8yqqV0v3nST5zfget0/OGbEWMz2FY10xlMf851zNL60IdRr2Wrd2kTyww89MQZ74/ztwvQzCrkT6ktilLW2xX1hQCW5StLGtq4UXWmhMRNg/x9qBUPNXqsO6qAmlrvLOyM3L3B2Qe7GTuh22kh7pYeGqecFcb+pxOy9mrCLVE0FojS1/o+f1S8KUfQicMpLI6RCO0bO3mNR1ZXrXRu0dmWaIsZlaF7ZZwi73I2792ib9tmBRd+1dp1pS8XO+RouqV42z7yoU2gi79aF+hFGTNST2z0jqmomQjgo3mjQLnd4T523g7v9OZZTU6oZVtxrxomvGZBeN/rSWMpmnGZRIhjehZq0iPQHY+xewQTP94ktmhEPqkRjoRgrz0KTuVSaerfk6VApuWDaKsuf0iEVnzDs3tnXdCOcOD/Y536s1/s/Sz+lFulDz1oJFlywucQpXmQNNZvKOrNQsLGqHz59GnQrQ+J0v6SIq2S1cyf2CMyJoOsuMzaLE2CGlkz8wZ8761t/Cu6BzP745wfmeYde/04HPhKIRapdp8aq0zIwfe8HjV2urCZmNrrP9ucRe3anX1WOVDnuVs+0rPoqg57JDNIg5aWvrHAfayamaFxv9fDICfnF7gV2NpnpnJcmAmw2RWJ7s2Blmd+b3T6BnQpyH9ZAhtlU7mcAiiusk1aeo73H5WrerKkiKNI2v3f1puMggKImw+4ZW0lVLt6D/14EBO2vrvVatRgUb8qBXKG0BLFhZChLbNo58J85svWeDgfIYdbSF2toc5vzPEBZ1hNkRDbG4zEs5KsubqY+P5adpDdNMfS3EvbAGVtKIQzmKpCNvWL/fYiFhjUQOHGTWT9hxIRuGSiZy0lZLRdfbNZDm3M8yq/3NGrQ3fZM1W4LLylWv7IWvq/RVZCxYyJBpA7vig9Trd4pUnL2p5cbOuoTisYucVBErnTlowDvHswVb0sQjfvqSTO67u4psXx/hwvJ3+ja1cHossypoRQ+FVuROOKtd+t5a0VPhQdZeyVr0950XLF3uwt4pC+L/nD/3xsEIpG59RJ3XNSus4lDWT9hxIRqVeZ9FJ51aGNY2dHbnPrMmTSoqDqsnaUtsey1rRRi0PWRP8QYTNJ9z+dVFJ2swoPN+sLZC26h9PD03MruDV+HXqU8ZbktGXng8KxY8sXPeOatvrbn95sJddUNJiTTpgo4EKRc1XedDxspNpbd6Jyij0w7KI/W0oFjUn228ialXDmL+bpQtW/Z/k4q8hNCIFn9Vw7oM78f+6rNtQlM8lUbOzLYrHtEWgqt8Uym9HcaEgyJpk1/xBhM1Hai1theSl7XRO2tyJglNLCg6nPr30VoQ1Kky66W6bgrNHSuWsVoJmsP1rF6s14ljSXGxAUQivdshSnG1fsTPcaRbDaRH7ombsAjeiZiI4SvUqRrHdnYl/XlEeQN1PzBusWN+urKnWzn9eq4c323Mia82NCJvPBEXaKpXzT8Gcip4fr+qse0fWdLl/+8crTHoSjI6ZUw9JKwxT/otXQY1dbzusF6Km3mixqzrdByaiVjWU+TtbuYiueI1aYRU14Vlqyo6sKe5rx7KmFt6skMha8yPCVgMaQdpU8V+bvOfUp9UO8yD12RoFOQtep+svaXrZLy4xFzV7ke2e/B3WLy29KGpO9kP5djsRDNNq1RdUZOKfVygL6JKo2RFPWxZoWr6WsmZ0RWStmRBhqxHeSJuzs7LX0uYGt8LnlySutciu1Q8zMauXnDlssF6SVhiq/BcvAzsUNWdNKayoGMpTUaP8V9V6pl6mV1xgP8tWpUeWB2WVWgqBTctX3uv+yJry+yyy1jCIsNUQ99KmlZw71TUlSNJWS04rZNfqJ2sW713dxMyqX0sceMNu9RBKEX2QNL3sFy8Dl71NTjn0x09Vbk59hSVLu8PNvrB4M9Varlyt+oJFVKRt4l+sbkAobN9PWVMQVLO19ZC1XFdF1hoHEbYa41raPlRS3dLXyheuvepVy1La6ksFqVZz7Tr00fuoqmvcNeL1NpTEKnnbPMcXUQN316mZyJpSvSpLykL7e/AvSYwdWVPsk172Q/XQ+bXKm+2DrKGLrDUYImx1wHNpM8NCBtZeWShtFWSiCfA/u1Zp/+lYZsrqvov97ci2r17sr6QVhiv/xevgZW+lCrYmxvVV1JzsFwtRqxqqvJBpteoLLHGSZbOUmIrbpCg9jmStwPyV8EvW1qh2wBSRtdojwlYnaiJtFixJ23euO/3gd5aeP1r0qiIjwTKQMlRkrRib21pNxgKzO1x2zHFVH3ZGUTivd3RJvJK32XEcleKWMey36k7UTDqkHEpBWMpiOemnWvmJf+kqiG4ha27aKNuO4t8qy5paE2aRpp7+6XXmsqa4L0XWGhoRtjoSBGkDOP3Qd8yHSG07m+5Q9Px4KeyDd2SW+ux9+DrgQUc92U4Pd5CvklYYs/hXF8rkXV/s1PBE1ExkzUE9NS9zcmwab8yqP5tSrVDeTsVdZEd6zMtXrm1X1orJixqYyZpqSJG1RkaErcHxXdqcUGdXO/3psHo/GxaPLLJKiLp4as0krVjU7A57Fsfyoj/2axk/+CBqVcMpiBpWC+z2Nffm2GTyX1ZW6YvySpNi5eWXg6wJ9UWErc548ddKIKUt4Kz960y9u6CIlZl6FKpKkUIOvlHxDlG3ffNNEcslrVDUXMVyyKE/sbhTVKXlxYy2E5yKWr5glSVlsRzuL4s3Rz3LVtC8s5VLRRzJWv4gU2tGVdaMcLWXNcmu1RcRtgDgnbQ5+/JuJmk7/Znq2bXgyVqllKGHIRWK2VlrxravXuSsf75LmpfZNLUT/NYvXWArumrr7kQtH8kssHIPKletvkCtrSrbqCJtk/+yskLz6u+lVfnKEexk1cwLWsmaclCRtaZChC0geCNtIZye/Nde+ap7F29GaFBpU5G1+uGDlFUK7aiYx/2qFN58gV8NLUmaecJGMZ63RW237omomciag3qWoqZXLaXQnKM3yZLJz600a0SxL9blK0ewI2vm+6nw5gKRNQFE2AKFd9JmRSVpMF6NLm3V8Ce7Vn2/+tqMYnEnJVxTFN7v9solbVHUvIjnUVHbrfslasoyUWWJpb3Zxd526sDKP5t01o5KkZrJWjmu7wQVWWtKRNgChv/SVg2dtVe+clHaDHHzUUI8wvvsmoqE+bQfHDRTvXiN3r+yJvw+XkziF0ia/VZt9LdqUZeaWHdR06sssVrgoM82rHqpBfV2jCybjfe1pCXrJSZrXchw5Wk7VEMaHRBZaz5E2AJI/aWNRWkDOP3Qdy2ybXakxu+Xwjb9ddrTeK5w2LRaFe+35+Abn1AsWYv9WEHS1M/7FjHdFrW/7Yf+5OnisI0ianrVUmrt2cyqlbblLMtWsQHMtqVyL3WVQhWjeXVzASCy1qSIsAUUr6Ttjg+FHDuJmrTVn9OfiVQtY8haDXHpg+rV6iCbdcFc0hZFzauYKsXtr1QKHTRRw2yJpb05wKusmg4r31Zd2iY/t0qlAdM2vJM18/3s5c0FImvNiwhbgPHqQ3PHhy3e5mpSoRvStjREGlxpqykK+81tGPXSNUCxmW1fudCHhitLmjtRc9YFO7G2ful8xXY8FjXMF1nXV4ioZm9q7bnMqln3yVl3ln7Qy1ZZN5E/GFX7YV4oSDcXgMhakBFhCzheSpuj03xe3K5YkrbTD33X4nFWThpwh6vsmop4udg2Z2HqvEPNulDT9v2WNJui5kUsX7GQGGWBUBCUsoUuRc32W6C2jY6ybHrZD+WrLHtXtVDFaK4fM7UYVmRtuSDC1gD09A1oXnyQ7izItDlxk7y0AZx+uEq2zakM2Xyt/as0a/+qynCnxw7kzus8skGvMO1CLftk0VY9Ja2qqAUBk774LmqYLVBEXdSWWrHYIIddWPm2CVa+bWIpRp1lLf+z45sLPJQ1r84xgr+IsDUQ3kmb+gm5tOSaEmkLgHIAWEpbNZlz4omVCZiQlVJVzmrRR4u26iFphVWcF6hY01u8FTVMl5gtdLoPCt5QtdIFsma3C/qSkJVQtLxI1BTEtXSty/3t3c0FcifockPTXV07IdSD4cF+12/aTR92Oh/Z0md7tCDLVihy9Wb0s0vDpGuqZd+UaNDPiNqZuCoH3/SkUrnK17BZZ0q82bs2o1Qt7q5XhU5w+M1PK9XZ8q/n2euPiwyP5dI6ZdSWWrKoVFWolygc9jQXNfOA9cuq2Qi8KGtyJ+hyRDJsDYg3mbYwd37YydxlSxmMNVf8weKXjiFv3uWp3JCXtDV/lbLRnwBnxaph2e16botFu55k0cza8Kq4u2za0q7PbaTrfW4Sw2WGx3Sp5UIn2JO1paYtpNSGrMGSpKlm1SxaLl8bEFmTO0GXLyJsDYpXHzZn0rZEsbR9z8ZdpF6IlPXLkLUmxNLB6iuaRnbNou16SlphFS9jmoXXwWxqjsqZMxv9sdVFt6LmZF8UvMlqpQuExULWFGqbYedaNeso+QO3Wl9K6xRT+Xo1+7LmBSJrjYkMiTY4XgyPgpsh0iUKha1Q5ASb2Mwo+I3KkOi2r/Qs/WI3IVEVB5GqVnHfu2IPqBzv8Jv3VI235V/PrdKQrV5Vrq6+UK1Nm1UrZpa8eu90y18UogQpq2b8ILImSIatwQlKpg3cZNuWIZUShBULBBRPs2gFAZ1k0lxkZmw14dmwZ5XGHBa2rO5ZRi1X11Gy04ms2c1ImdepHiVIsmb0VmRNABG2pkCkLYBUErKqUhYUMdOVbzhw32uH229L0tyLmvFDXtS85fCb95Y0ZqtnFZZYrXAravZlzbJNpfdQsZGiz5edKPm/OtSbsydrdoXTKCuyJuSRIdEmwqvhUYCbPlQwROrwY96UQ6QuvsiDjXl/D75pWKn21i/3VC+k2KY31bzJ8RX/4jymypAowJYvWgyLlmFDRkwzak6xJ2nFrVmImmJt9YbM69Qrq2aUtrsd3mXVQGStWZAMWxPh5Yfyzo+EKfuL0+ZrzeUBzLY53JaSFItKwYBTob82N8OerDncRzXKpBVGKc6muYtp/8YDK8z7opZRsyyp3rZN76iaVasawVZDpnUqv3sFa33JqtmQtYIDT2RNMEMybE2KZzcjfMjtPGYao48Uy1qhyNWH5XbMV9neCuerQ39cPcNWWdhc7OsaZjO9zKZZRV4c8qyAdYbNRtZIfaEiTrNqFpWaNKsGwZlfDUTUmhERtibG2yFS9xPQjj7yH0tDpJe/ojmGSAOHmpwplAScCJvLQ66GklYUxVNJM4/lTNgaUdQqtFs1Q2q7IdN61SP5l1UzStvdFsmqCdWRIdEmxtsh0uoPWa9GoaSNPvIf1xUKnGAXhaHYgsX5kT1/Bm1dRlWu7u2Qp3Ge9GbIszy6yWLbMXSFpbYWqrfv4IaCqsOfnsuaedDqWTXd5u4pLlj40HZwMQS6GFpkTVBDMmzLgKBl2kCyberYGVKxVaMqKtk1gK1fvsBe4Bpn0coi1SCbZrb48FuqZ9gAtnzxHJXogcioLbVYy+FP83r1z6rZCF4gnSJrgioibMsEL6UNvB8iheUsbs5OWn5/cj0VtqaTtArxLBbbFbbaiVquvqPhzwqVvJK1KqJWPZJdUSsvXOlaNaN0fbNqILK2HBBhW2ZItq0eODoTOq3tkqXWDv3xU1VLW8qai5OjG/yXtAoxFZpSkbazSzJslePXS9QqtN3QWbXywp5l1RaLSlZNcIZcw7bMCNp1bdDI17bpiq/qVfXCV/XaPvbfo1DeFbbVvPFDbkd6PuxpErMWb5RpfLeNFhxstrth0XbVLtnoc1FR83rVs2q6zd1UXLjStWpL7dvdHpE1wTmSYVumeD9EmsLxDLsF1C/b5vHnoK5ZMivs9UIpw/Yl1evXvN8DxckXv/aw82yaWYXDb3mmasnFDFvTZNSUC5UUNa8jWTUDkbXlhwjbMsYfafOG0Uf+s0DcXh6MYVKvzt2+402P3Amb34LmTxsmLVVdbCeWkrB9wWxItPaittRqhYpK2VRbjVnWq7eoLZUWWRPqgwib4L24fdBC3Gx+xRRKG7gUN6fnjcDjT29VZA0Khc2fftRd0hw3aV5JRdigUNrqKWoV2q+hqKlFcydr1W4qMErb36b7P73aToeqIqK2vBFhEwDvpe1GK2lzwNijS+K2+rKAZNtqjo+fU5PQh/5EJbt2vg+dqaWkVYjtoaSVrjmilGWLO+lAcYtBF7Wy4pJVq4TImiA3HQiA918Gd/1N1LNYhZI29uh/XlcocM2FXuHlYxMBoKg7Ovhz44Bpa+arHMXzKJwrcvvNgTfpJT9ZFKgSxXaDlsFrkVUTWRMaCcmwCWU0SrYNGi3jVuPPmovm/M6wlXWtXpk0V806GL7T4cif+pFhq1dGTbmQSdEgD3/abECGQIUaIMImmBJkaYMgiludP0eumi+vfOhPnq5ay66w1Xaos0p8jyWt4pqSFd4Km0+iVmWVYoEKxV1k1Gw3bRQuE7XzX3ivVTJRsmpCEBFhEyzxWtrAX3HzVtoC+rlw3a3qAVRkDaoLW+2zaArx6yhq+YVH/jSh1GJlaWseUVOL6F1WzUrUjBr2t83rrBqIrAnmiLAJVfFH3BY8izX26PdLsm0va6BhUhM829vOAjkVtvoImkIbdZe04hXuhK2eoqZcyKSoS1Gz2XQtsmoiakKtEWETlAi6tEGDiZvne9O7gKrDofUTNIV2fJC0imttrlCRtmJhayBRKyvuZPizoJSPombUkKya0BiIsAnK+CFt0ITi5utHyv/Pq4qwbfnS+TUWNIW2PL6OTymsxbBnNdSEbadquAo9CJaoqUV0ImpGBVNRs4gVlKwaiKwJaoiwCbZphGwbeCxuNf2Y1PczqSRs/3peDXoCjSNpVWsVoSRsn9+pHK+8Bw0sarabtydqxmLJqgmNhwib4IiGyLblejj2WIm4XRqEodJgfe4Ke3O4rsKmsF98krSKa50ZnCVeC1tji1pBKZvNTz39P+aiZhFLsmpCIyPCJrjCN3H7gA8Zt5qJW7A/U9ajeDqH37xHKYa3wuZnFq16AL+zaWYo33hQRdqCIWrW9f0a/rQrasZie43c/ykRNSFYiLAJrmkkaQMn4ta4n5FKcmZGbYTN7yxa9QD1kLRC3Apb3UStrEpthz8rippFLNtZNUTWhGAiwiZ4RnDETa0bY4/9oETcfj8AQ6XOqOwY6m+LirA5k7VGlbTqce2hL4Y78tZ9VUuXClvji1pBKZ9FzVgsoiY0DyJsgqf4JW0AN35g3pe4jSRu1ZM/3u5+M4FTE7ZaCFr1IFWbqEE2bTFeSUgzYWvejFpBqZqImr2G/BI1EFkTvEOETfCFZhA3qI+8qSV76vO5PfzmPRbCVitBqx4oUJJWIeyRt+4L7jVqZVU8EDXFCqWSBiaiZhFLRE1oZkTYBN/wU9qgscUtyFKmhmLfAi9pSrVtUp5Ns1m77KcqBd0WqlDFur7X16m5EbWlxWrb66eogcia4A8ibILvNGK2DZyLmz15aJTPX7AETalErSXNZdjmEbWCUl6KmkU8yaoJywURNqEmNGq2DYxTwbiJvHWbyVtDylgpNvrt6SY2mqTlYroM692wp62CFlVqI2q2JK1CPDs3FUhWTWh0RNiEmlILcfO8gYKA44+biNslvxfYmxSqUy85Uw8YSElzGVqv8JvqKocFK1Tx/4YC70RNvWciakKzIMIm1AW/xe2G91tl3LxrdvzxHzaYvNncdl/eIQ+yaFUL+XVo1SibprDaQcEKVfy9ocBc0l50r5N9IKImLGdE2IS64be0Adzw/jm/mwiouAVBztQDu8uiqbdjH/eSlotS9lOVgsoRHXSiYowgipqxOBiiBiJrQn0QYRPqTrOIG9RD3rw4cXuJR4KmVMhHSfMgvPeSZruwRRX/RM1a0hRacDn8KaImNDsibEJgaHZxA6fy5tnFUj7goaBVLej3xjRRNq2smtubCQpKllQwkzQoFLUqrYioCYISImxC4GgmcQNVefMsneMjtk/tHhRsMklTLGKzYIVq/oiamqQptOJi+FNETVhuiLAJgaQW0panNvJmbM744/9lIW+/q5Z5q+nHtR6CZq9dZ3gjablIZT9VKWgrqi18FjV1SVNoxWFWrRaSlkdkTQgaImxCoAm+uDnvnqW8Xawob55ibzsaS9BybdRa0hSLOCxsUc1bUbMnaQqtiKgJgmNE2ISGoLbiNutvAyZbMr67lvJmf1c2nqDl2vFc0sp/q1LYVmRb+CRqU0/ZlTSFVkTUBME1ImxCQ1FLcQMH8uZB76zkDZwInI9yZqtw40laLlrZTwqFbUW2RVk196I29dStlsdbZUlTbMmmrNVS0kBETWgcRNiEhqTm4vY+n7NuFqjLm7PdYbtW4AQt11YzS5ppVXei5l7SFFoSURMETxFhExqa5SJuUFneALov7qt4om0OOStor16SZrtt/4c9q62tJGhgR9Kq90NETRD8QYRNaApqLW7gl7ypb8b47sGKJ+FVVQTOedP1+M7wNouWi2j5m0IFLwtXqWpf1LwVNLV+2BG1WksaiKgJjY8Im9BUBF/cvOteaaQJOwJXK/lwjPdZtPJwXkuaowoVqqoPe1YVtAtedK/zromoCUIQEGETmpJ6iBvADe+b8Tym0w2pJnAAqy4qzcLV8/tgGUqaafXKolZNziAnaNXDVcH53bCFE9/WQ9JARE1oPkTYhKamXuIG6vLmSQcVgkw8UV3gAFZd9Ds1mgfOH0ErD+mHpDmuZFHVPNakgpwBdF3w2+XP66yLqBn/1kvSQERNaF5E2IRlQT3FDeB6rzJvHovFxBP/rSQE4IXI+Sdo5WH9uHnAUYUq1Y0FqmIGhXJmEbhOonb/p7qdNuwJImpCsyPCJiwr6i1uoCBvrnrofvPsSFwec5nzV9CKQ9topE6SNvnUT2zvV3M5Mwle8qM9nIvafXWWNBBRE5YPImzCsiQI4gZw/S1OMm/16boTkcuz6sKXejLMWpssmrNKk8P2hSzPygt++157LXohw85ELQiSBiJqwvJDhE1Y9gRT3gLRpSosScPEkz9yLCtmFApe7SStuKIbATNjpUm2zJGk2a9or1WT1SJpglB/RNgEIUdQxA3g+lum692FEtzJgtdCF0RWXvBi5SdPNIKoBUXSQERNEECETRDKCJK45am9wPl//ZlJa4u/TT7547oL3sqeF1cexrUxHUf1tVVq+HV9WkGRIAlaHhE1QVhChE0QKhBEeQOvBa62clbelM2G/ZQXRyEaMJsG3PfJ4AkaiKQJghUibIKgQFDFDezIm1cyYJ+GFTTLMEHMplWvHFRJAxE1QaiGCJsg2CTI8pbn+luSxg916ml9BM115SqhqseuTzbNPECQ5SyPSJogqCPCJggOaQRxy3P9e5O+xnclaA6reFS5SiivJa2khoei1giClkdETRDsI8ImCB7QSPKWx6nElW9orQXNkwAVQvksac4CFFVuJDnLI5ImCO4QYRMEj2lEectTKnGeyJmLah4GqBJOLX49smn3fXKVs4oBQCRNELxDhE0QfKSR5a2Q6957xl4FT7Z6eUlaI4tZISJpguAPImyCUCOaRd5Kue69Z4IpaKYhayBpFQI0i5SVIpImCP4jwiYIdaBZ5c2M695jlZ2rhaCpt+OsN8XZtGYVMjNE0gShtoiwCUKdWU7ypsp175lSL+yTpN33iZXqfVgmiKQJQv0QYROEgCECJwQFETRBCA4ibIIQYETehFojkiYIwUSETRAaCBE4wWtE0AShMRBhE4QGRgROsIsImiA0JiJsgtBEiMAJpYigCUJzIMImCE2OSNzyQeRMEJoXETZBWIaIxDU+ImeCsLwQYRMEARCJCzIiZ4IgiLAJglAREbnaIWImCIIVImyCIDhGZM4+ImWCIDhBhE0QBF9ZTlInMiYIgl+IsAmCECiCJHgiYIIgBAURNkEQBEEQhIATqncHBEEQBEEQhMqIsAmCIAiCIAQcETZBEARBEISAI8ImCIIgCIIQcETYBEEQBEEQAo4ImyAIgiAIQsARYRMEQRAEQQg4ImyCIAiCIAgBR4RNEARBEAQh4IiwCYIgCIIgBBwRNkEQBEEQhIAjwiYIgiAIghBwRNgEQRAEQRACjgibIAiCIAhCwBFhEwRBEARBCDgibIIgCIIgCAFHhE0QBEEQBCHgiLAJgiAIgiAEHBE2QRAEQRCEgCPCJgiCIAiCEHBE2ARBEARBEAKOCJsgCIIgCELAEWETBEEQBEEIOCJsgiAIgiAIAUeETRAEQRAEIeCIsAmCIAiCIAQcETZBEARBEISAI8ImCIIgCIIQcETYBEEQBEEQAo4ImyAIgiAIQsARYRMEQRAEQQg4ImyCIAiCIAgBR4RNEARBEAQh4IiwCYIgCIIgBJxIvTsgCILQrMTivWcD1wBXATuBrcBZQAzoANqABWAm9zoOHAIOAg8Du4A9ycSQXvPOC4EgFu9dB1yJcQydA2wBzgZWYRxD7RjJlzngDDACHAOeBoaB+4HHk4mhdK37LniLpuvyPdBIxOK9fwx8qd79KOHcZGLoGdXCLrbBVjsV2v9P4GU2qyWSiaFzbLbj53uVAeYxTvKngJPAM8CTGCf5XcnE0LzXjdb7vSvoxxEM8bHDd5OJoVd51QczYvFeDXg28LtAH7DDg7CngR8D/w38JJkYWvAgpiU+Hbc6hpimgClgDDgBHAD2Ao8ADyQTQ2Met1tGUI5hK3LH0M3AS4EXAz0ehD0D/A/wQ+DWZGJoyoOYQo2RDJsgNCZhjL+uO4C1GF/qzy1YPxeL9/4C+C7wn8nE0FzNe7iMiMV7Y8AbgT8DzvM4/Frg9bnXSCze+yXgX5KJoeMet+MnGtCae8WAzcDFJWWysXjvQ8B/Ad9OJoYO1rSHdSYW710NvAl4M0YmzUtWAH+Qey3E4r0/A/4hmRj6lcftCD4i17AJQnPSBrwE+BZwKBbvfV8s3tte5z41HbF4bziXsdkL/BPey1op64H3Ac/E4r0fyYlisxACrgY+CuyLxXu/G4v3XlDnPvlOLN7bGYv3vg/YD3wS72WtlBaM7N0vY/HeB2Px3v5YvFeSNw2ACJsgND/rME6CT8fivb9V7840C7F47znAXRjDaxtr3HwH8EHgyVi89zk1brsWhDCyQY/G4r235IYJm45YvPeFGNeafRToqkMXrgT+HbiuDm0LNhFhE4Tlwxbgf2Lx3r+td0canVi891UYNwVcW+eubMHIlHykSaWmBfg74N9i8d5wvTvjFbF4b2ss3vsFjOvK7F6LKSxTRNgEYXmhAe/PnSwEB8Tive/AyEoEZTgyhJFt+3os3hutd2d8oh/4f/XuhBfE4r1rgSHgLfXui9BYiLAJwvLkLbF47/vr3YlGIxbv/RDwKQzxDRp/BHyvmTJRJbw1Fu99ab074YZYvHczcA9wY737IjQeImyCsHz5SCzee0O9O9EoxOK9bwY+XO9+VOF3gX+udyd85NONKqS5zNov8P+mAqFJEWEThOVLCPhiLN4r3wNVyInt5+rdD0X+NBbv/dN6d8InzgN+u96dsEtuqPq/8WZONWGZIl/UgrC8uRj7kwgvK2Lx3i7g2xhz37lhDPgC8AqME3cXxlyYMYynILwEY7j1gMt2AD7TxFNi9Ne7Aw74BHC9R7H2AP+AcRft5Rjz9LUBUWAlsB1j8uY/Bj6PMZm20ATI3CvLh5rM0i14guV7lbsTcAXGl/QVwG9hnMDcXAD/FuA/XNRvdv4Od08smAA+Anze4ukT0xhzcO0HfhKL974beDnGSd5pux3Al4GbHNZ3gulxG4v3tmEcs9sxjtmXAb+B8+sAn+uwXl2IxXt7gbd7EOr7wCeTiaH7K5SZyr0OAncAX8n1YSvG98TrgWYV+aZHhE0QGojcMyXzX8r7gO/nJt38AvD7DsM+LxbvXZdMDJ3yqJtNQyzeez7gZnjxQeD3k4mhQ6oVcu/xf8TivT8Fvoohb064MRbv/f1kYugHDut7Qu4pG3MYj1DbBfxrLN57M4aArHMQclMs3rshmRg66WE3fSE3Ia3bu1v3AW9IJoZudxogd/x9Ihbv/STGkPJ7kRsfGg4ZEhWEBicnWi8H/s1hiBDGswuFcv4G53/Y3gs8z46sFZJMDJ0BXgl83WH7AH8XxPnZkomhO4DfwXjGqBO8eEZrLXgr7q5b+yVwtRtZKySZGNKTiaGfJBNDN2H8gSejLg2ECJsgNAG5rMxbgRGHIa7ysDtNQSzeexbOs5YngL6cdDkmmRjKYjxb8m6HIS4AftNNH/wimRi6F7jVYfVVHnbFF3J3s/61ixC/BF6cTAyNe9SlIpKJoR8ClwAfB1J+tCF4iwibIDQJOTn4usPqcQ+70iy8BefZtXckE0NO5bmIZGIoletL2mGIP/OiHz7xM4f12jzthT+8HNjmsO4+4OW54WTfSCaG5pKJofcmE0P3+dmO4A0ibILQXPzaYb0NXnaiSXilw3q/TiaGnA5Pm5JMDO0G/q/D6i/M3ekaRBIO67nKXNaI1zmsp2Ncs+ZLZk1oXETYBKG5OOqwXqenvWhwcjcbnOew+ie87EsBnwYyDupFgRd63BevcCpeE152wmti8d5VwAscVv+eV9esCc2FCJsgNBdOP9NOL/5uVpwKznHg5152JE8yMXQcY6Z8JwRV2FY6qKNjDBkGmRdhiLITPuplR4TmQYRNEJqLzQ7rTXvai8bnWQ7rDSQTQ06yYKp802E9p9vjN+c6qPNMAwwXOp0y457c8LcglCHCJgjNxfMc1gv8nFY15hqH9X7tZSc8jN8Ti/cGcdjbyWOmfuV5L7znOof1vu9pL4SmQibOXT7sjcV7vY55V24+HyEAxOK9KzFmMneC30NMfhx/vpB77qPTu2Yf9rIvpSQTQ8di8d4RYL3NqiHgfOAh73vljFi897k4u87rqx53xVNy895d7LD6/3rZF6G5kAybIDQBuQe4fwHjkVVOeMDD7jQ6Z+Psu/F0MjF0xOvOmPCIw3pbveyEG2Lx3ufjLJt0VwNMQbEZaHVQbxZ57qdQAcmwCUKDE4v3rgf+FehzGCKL8dxBwWCLw3p7Pe2FNXtwNhmu0+1yRSze24rxLNGdwJUY85M5Sbemgbd52DW/cDr32tM+X/8oNDgibILQYMTivfmHv1+JcfdfP+6m5fhVMjF02ou+NQlrHNab9LQX1kw5rOd0u1Txe9j7r5OJocf8bMAj7A5X56lFdlZoYETYBCF41Pp6ry/WsrEGoN1hPaciZRenYuh0u4LAh5OJIacTB9cap/t51NNeCE2HCJsgLG+eQO5MKyXowua0nUYUtjPAm5KJof+od0ds0OGwnq+PoRIaH7npQBCWL1ngLbkHjAtLaA7r1WryYaftON2uepDBuBu0p8FkzQ0yebVQEcmwCcLy5SPJxNBd9e5EAJl1WK9Wz+t08nQAgBlPe+EPRzAmB/5qMjHk9Dmj9cbp8dOIGVChhkiGTRCWJ19OJob+pt6dCChOxcapSNnFqRg6FYlaEgW6aaxsYClOj5/VnvZCaDpE2ARheaEDHwfeXO+OBJgxh/WCnmFzul21ZAPwVuCpWLz3o7F4byOOAp1yWO9sT3shNB2N+GEQnHFuMjH0TL07IdSVoxjXrP2kDm17evzF4r1HgLO8ilfCYYf1nDwXs5btHPK0F/4SBt4HXBmL9748mRhqhOHcPAcd1rsgFu8Ny1xsghWSYRPqQdphPa/+wIg6qJPyqO16MAp8GDi/TrLWaBzGuCHDLuti8V6/JLKQyx3Wcyqi9eRFwHdj8d5wvTtig2PAgoN67UCPx30RmggRNqEezDusF/OofSdxGu2W+3ngVoxni25JJoY+kkwMTde3S41BMjGUwvmzVa/wsi+lxOK9mzCGDe2SBZ72uDu14iXAR+vdCVVyd13vdljdyRMshGWCDIkK9cDp8Iab2fzdxgnaBdtZDCmbxbhm5gSQAIaBXcB9ycRQo0lmkNgFnOOg3nOBH3vblSKe47DeU8nEUNLTnpRTNOwdi/e2YdxAcBHwW8Af4fwpAO+KxXt/lkwM/dp1L2vDvRhPIrHLy4DPetwXoUkQYRPqgdOLcjd51P5GB3VGPGpbBbnesP7cj/HIL7v8YSze+24fr0P6I4f17ve0Fwrk/mA4nnv9Ihbv/Rvg0zi74SUEfDEW770kmRhyMtxYa+7C2XNPb4jFey9KJoae8LpDQuMjQ6JCPTjqsN4FbhuOxXs7gK0Oqjrts9CY/MxhvU04e7B5VWLx3g04HzJzuj2ekUwMnUkmht4CfMxhiPOAt3vYJT/5H5xf9/p+LzsiNA8ibEI9cHpR7sUetH0RzuZ4OuBB20KDkEwMDQN7HVZ/t5d9KeAdGHdP2iWFIRCBIJkYeh/wA4fV3xOL93Z72R8/SCaGxoEhh9VfGYv33uxlf4TmQIRNqDm5i7qHHVT9jVi8t8Vl8y9xWO9Rl+0Kjcd3HdZ7fize+yovOxKL914E/IXD6j9LJoacPjDeL96Cs8sMVuGfEHvN1x3W04CvNYKYCrVFhE2oFw86qNMFvNBpg7F4rwa83EFVHXjYabtCw/JFjGdaOuGzsXjvWi86kZs89gs4m44G4HNe9MNLkomh0zgf+vvz3PBw0Pk+zue+iwP/mbtxwzdi8d62WLz3Y7F477V+tiN4gwibUC9+7rDe37qYk+m1wIUO6j2aTAw5vVFCaFCSiaEjwA8dVt8EDMbiva6mosn9kfEF4CaHIfYAP3XTBx/5Cs6mv+gA3utxXzwnmRhKA59xEeL5wI9j8d5V3vSomFi8tw94DGNfOv1jQKghImxCvfhfnGUvLgX+zm6lWLz3fOBTDtqDAF3/I9ScD+B8oucbgF/G4r2OHjmUk70B4E0O2wd4XzIxpLuo7xu5+co+6LD6nzrdrzXm88BTLur3Ag94eU1bLN77oli89w7gv6jd0zkEDxBhE+pCMjE0Bjiddf/dsXjvF1T/8ozFe38buA3nc0B902E9ocFJJoaeAv7VRYhrgMdi8d4/j8V7W1UqxOK9Wize+zKM6yZf6aLte5KJof90Ud93komhH+Ls8ohWGuBuytz1un/uMkwcuC0W7/1eLN57jZMAsXjv1li8912xeO+TGBNqO83YCnVE5mFbPuyNxX2ZbQDgZDIx5GRusy8Av+OwzbcAr4jFe7+NMbz6BHAaYzLZ1RjPmXwO8PvAjQ7bALgtd9IWli+3AC8Gtjms3w38X+BDsXjvdzHuHtyNMVXMLIZ8bMB4LNFzgD8Adrjs8yzwxy5j1IoP4uyPtzfG4r2fSCaG9nvdIS9JJoZ+EYv3/iPwly7CaMArML7znsbYX/dgPL3iCDCNMWLRjvH9txVjGpSrgGfjzR32Qp0RYRPqRjIx9D+xeO/9wLMchlgN/H+5l1982MfYQgOQTAxNxuK9rwV+hbNpNfKswZhM1cmEqnZ5ZzIx9GQN2nFNMjF0ayzeew9wvc2qUQzZe4P3vfKcdwHX5V5uOT/3EpYZMiQq1Jt3YNyFGUR+1ECPwhF8JJkYugN//zDwki8nE0P/Uu9O2OQDDuu9NhbvPc/TnvhAbmj0d3A2nZEgACJsQp3JnQj/qd79MGEUY9hVEABIJoY+B/xtvftRhR8Bf1rvTtglmRgaAn7toGoY+Ii3vfGH3J3mv4HxzF9BsI0ImxAE3oOzL2u/WABelUwMHa93R4RgkUwMfRDjmrYg8u/Ay318jqnfOM2y/UEs3tsQ12glE0NHMYZ+7653X4TGQ4RNqDvJxNA80EcdHlBtQgp4TTIx9It6d0QIJsnE0N9jzOk3U+++5NCBv8c4bhvhweimJBNDd+Lsmach4G887o5v5DJtzwe+VO++CI2FCJsQCJKJoSngeTh/xqAXjAG/lUwM/Ucd+yA0AMnE0LeBK4AH6tyVo8ALkomhW4I635pNnGbZfi8W773K0574SDIxNJ9MDL0Z4+7jY/Xuj9AYiLAJgSGZGJpJJoZehjEdQa2ffTgIXJxMDP2qxu0KDUoyMbQH466/twIna9z8LPAxoCeZGPpljdv2jWRiaBfw3w6rB/36wjKSiaFbMabf+CAwVYcuPAS8Gri3Dm0LNhFhEwJHMjH0FYzJIv8e/7/EbgN6k4mh35Vr1gS7JBNDmWRi6AvAOcDbgb0+N3kK+DhwTjIx9L5kYuiMz+3Vgw/i7M7xF8XivTd43Rm/SSaGppOJob8FdmJcz+v3TQkpjHncXpBMDF2VTAz9e+4xWkLAEWETAkkyMTSaTAzdgvFMxj/CmJ172qPww8AngAuTiaHnNlOGQqgPycRQMpkY+keM+bGejzFR7gGPwo9iPG3jZcCWZGLovcnEUNMOoyUTQ48CTp/Q8FEv+1JLct95n8B4XNRzMJ5D6tWk3dMYl5u8FlifTAy9JHdnrtBAaLreDJc9CMuBWLy3BWOS3cuBSzBmg9+E8cipDqAN44+QBYwhowngOMZ1Pk8Cj2M8rqdpT3ZCsIjFe7diPJ7qKowMylaMp3DEMGalb8XIeMxinFRPAIcwZO8RYBfwdO65m8IyJBbvXY9x/FyJIXNbgLOBVRjHUDuQxbiMJP8awXiaxmMYjzh7KjcXnNDAiLAJgiAIgiAEHBkSFQRBEARBCDgibIIgCIIgCAFHhE0QBEEQBCHgiLAJgiAIgiAEHBE2QRAEQRCEgCPCJgiCIAiCEHBE2ARBEARBEAKOCJsgCIIgCELAEWETBEEQBEEIOCJsgiAIgiAIAUeETRAEQRAEIeCIsAmCIAiCIAQcETZBEARBEISAI8ImCIIgCIIQcETYBEEQBEEQAo4ImyAIgiAIQsARYRMEQRAEQQg4ImyCIAiCIAgBR4RNEARBEAQh4IiwCYIgCIIgBBwRNkEQBEEQhIAjwiYIgiAIghBwRNgEQRAEQRACTqTeHRAEuwwP9rcAk0Bbyaq39fQNfN6izouBH5usemNP38DXLOq8DPjPksUZoLunb+BMhf6tBH4PeC5wFbAWWA3MAaPAQeA24Kc9fQP3WsUpiPdc4FdVimWBaWAMeBq4C/huT9/A0w5j/0lP38CXq/XNRj/TQCrXx3HgBJAAHgR+1tM3sNdOW3YZHuxfA7waeAFwKbAGaMd4TyaAo8A+YDfwAHBPT9/AlI34z87FvgnYlovfCZwBjgGPA78GftTTN3DMpP5zcfA+DA/2vxD4H5NVr+3pG/i2Qr89PVZr1Y6Xx60gNAoibELD0dM3sDA82H8/8OySVTcDpsKGcSI142bAVNgs6jxqJWvDg/0dwPuAPwNWmhRpAbqAHRgnrg8ND/bfBdzS0zdwu0UfVAkBK3KvbcBv5uJ/Cfjznr6BlMv4bonkXu0YJ+tzMfb96wGGB/tvB97f0zdwh9cNDw/2vwX4FMa+KaUz9zoLeFbB8pnc8mqxXwG8H0MCzejOvS4CXgX8y/Bg/w+A1/f0DcyoboPX1OpYrfNnQhCaChkSFRqVO02W3VyhvJWwWS23imfWLsOD/XHgHuAWzE9MVtwI/HJ4sP/dNuqoEgLegrWQBolnA7cND/Z/YniwX/Mq6PBg/zuAL2Aua5UIV4nbOTzY/03ge1jLmlXcV2BISl2o1bEa0M+EIDQsImxCo2KWiTl7eLB/W+nC3BDq1RZxzh0e7F9vUicGXGZSvkzYhgf7N2AMz9g5cRcSBj4+PNj/Xof1q/Hq4cH+Z1UvVnc04F3A57wINjzYfw7wd17EKonbgjG8/lqvY/tNrY7VBvhMCELDIcImNCp3Y1y3VYpZVuwayq93K8Qsy3Y95pcMmGXYvgdsMVmexBguuyDX/hrgxRjXMpnx0eHB/t4K/SzlT3r6BrSevgENI2PTCwxblO2zEddr/iTXxwiwDmPfvh/jujEz/nR4sP/PPGj39RhDboVkgA8CPRjDs60Y791Lgc8AhxXifg5j+M6M+zBEbhvGe94FnJ/ry2Cu/XpSq2O1Xp8JQWha5Bo2oSHp6RuYGh7sfwy4vGTVTUDpxdalQnYQ44RauP4HVeoA7OvpGzheuGB4sP+llF9LB3AaeG5P38ATBcvmgVuBW4cH+z8HvLWkTgj4OIZg2iJ3Xd0vhwf73wCYXbQdtxvTa3r6BjIY++U0cO/wYP9ngX8FXmNS/O+HB/u/09M3MOqiyetNln2sp2/gb0uWHcm9fjw82P9O4EXAX5sFHB7svwp4o0V77+/pGyjN6M1j3HiwB/hGLgP8SUBX2wTvqNWxGpTPhCA0G5JhExoZ1evYSuXr01XWW8Uxa+8dJsvAuND/CYt1AH8BmK2/eniw/3kV6lXjAWDBZHmHi5i+0NM3MAu8Dvhfk9UrgL902cQ6k2UPV+mT3tM3cGtP34BVVueDGEO3pXzORNbM4h/s6Rt4ZU/fwMlqZX2gVsdq0D4TgtAUiLAJjYzZdWw9uSkcAMhdwH5DwfoF4KsYUznkuSJ3N1u+ThS41iR2kbAND/avKImd5yDw3Uodz921+Q8Wq3+rUl0FzD7XJ1zG9IWevoEs8FeYZ5x+12V4s7sw+4cH+x197w0P9rcBv2GyKolxJ2RgqdWxGuDPhCA0PCJsQiNjJmwaxl1meS7EmO8pzwO56RTuLlgWAa4r+P1KzDNSpRm2GzG/rOCnPX0DKkNet1osNxtOUuVazPt0m4uYvpLLujxmsuri3MXrTnnUZNkrgCeGB/s/NDzY/7zhwf5uG/FuwLjurZSf9PQNTDjpYA2p1bEaxM+EIDQFcg2b0LD09A0cHx7s3wfsLFl1M/DfuZ9Lhzvz0nUH8NsFy28CfllQv5RR4KmSZWdZdG23VZ8LyfV/jGKhBDhbpX4hubtarwP+2WT1fuD7dmPWmPsxvyt3K+B0+PBrwJtNll8AfDj/y/Bg/0GM6Sd+Dfywp29gxCLeVovl9zvsnwpfys2l55ZaHauB+UwIQrMhGTah0TG7ruwmi58Ly5dm5yrVAbjLJEOwxqQcGDP5qzJmsmytYt0vDQ/268OD/TrGhe0/x7gjsZAR4Pd6+gbmbPSpHlhJkuq+KCM3Y77VEFsh2zAmtf0CcHR4sP9rFpk9s2viwLrvQaJWx2q9PxOC0LSIsAmNjtmw6FXDg/35oatC+dIxHtkEsAvjsTh5rhse7M9Pllo4pJrHTAytJni1cwegWQwv7iCcBr4IXNbTN2A2NBg0fPku6ukb+CuMOz4tHyVWQgRjCo5HcvO4FeLZhL51oFbHapA/E4LQ0IiwCY2OmbBFgWuHB/s3A9sLlj/Z0zcwBsbjrSgeyloBXDY82N+D+V/zZsJ22qJPdq6LMivrZiqLQjKoi0q9KZu8OMcpt4F7+gY+i/Hoo7cDt2NMJVGNjcA3SpZZZdKs+h4kanWsBv0zIQgNi1zDJjQ0PX0DTw8P9p+ifLjqZqB0WKtUuu6k+GLmmyjOuuWZw3hIeSlWE79eYrG8iOHB/o2UX6tTKa4dOoG3YUyJ8JwGGBK1ehLDIS+C5+Zz+0fgH4cH+1sx5u+7BuM9/y1glUm1G4YH+3t6+gbykxFb9cXPp0g4ffh7KbU6VoP8mRCEhkYybEIzYHUdm9X1a3nMrmMzu37t/lxGrpS7MZ+5/oWKz8N8scVy1Yde558g0A28EHjEpMyzMCZqDSzDg/2XYX5C313hBgDH9PQNzPf0DdzX0zfwzz19A68CNlOeTctTeCPE3cCsSZkXDw/2r/K4m15Tq2O13p8JQWhaRNiEZsBM2K4HnlOyrFTQSk8uN2Hjge89fQNTFE8PkmcbxvQRlgwP9kcwJgo142eV6pr0Y6Knb+BnwPMx5rsq5W3Dg/0X2YlZK3LXDVrdGPBftehDbgLfWyxWtxWUm8O4saOUGFD69IRAUatjNSifCUFoRkTYhGbA7Dq2FRRnbY709A0UyUzu5FI4/9cmiq95y2MqbDk+Y7H8n4cH+y+oUO8fMM8qPdTTN/BLk+VV6ekbGMf86QBhfHgIuluGB/s7gX8DzGaxP4MxhOkm/j8OD/Z/ZHiw32qqiUJKp4bJU3pNlpWY/Z/hwf53K/Rp2/Bg/3dczi/nlFodq4H5TAhCMyHXsAnNwMMYd0V2VihjJV13AldUqJfFPGOQ578x7jwtvbN0HXDf8GD/x4H/xLj+qQNjYtt3YmTDStGB91Roqyo9fQP/NTzYv4vyZy/2DQ/2X93TN/CAm/huyD1hYBVwLvCbGM+N3GRR/L0unyMKxo0DfwF8YHiw/z7gJxiP7noS4yL2NMZ1jr+JuYjplMyx1tM38MDwYP/XgDeYlP/48GB/H8ZceHdgzB/XgjHkei3w+8BLML53/9LltjmhVsdqoD4TgtAsiLAJDU9P30B6eLD/XsDq+Y9gnoXLL//zCvV29/QNTFZoWx8e7H8FxjQhpZmcLuBjuZcKH+zpGzAbcrPLBzG/EP1vKJ4suBKqE7a+tKdv4McexcrzhZ6+gX+xUb4aGsakwtdVK1jCrRbX0L0VOAfz4fPrMX/ofN2p1bFa58+El8etIAQKGRIVmoVKw5aV1luJnGpcevoGjmMM61V6sHUlssAHevoGPuqwfml/fop5VvBFw4P9gZSJHBmMbMrb6t0RjOlE/tJsRU/fwDzGxfEDteyQF9TqWA3aZ0IQmgERNqFZqCRek1g8Gqenb+AE8EyFulWFLRdnL8bQziewN/fZPUCvDyemD1ks/xuP2/GCLPAj4KaevoFPKD5zUoWfUv44MRXuB57T0zdgeVz09A2c6ekb+EOgH8XHLuXIYAwHTjnolyfU6lgN4GdCEBoaGRIVmoV7Ma5JMjum7+7pG8hWqHsHxhCXGUrCBtDTNzANvCd3jc7vYWQYrsKYiLcbYz63MeAAxjQFP+3pG6h0fZxjevoGfjE82H875Q/NfsHwYP+ze/oGaj1NQgbj/ZnGeEzRcSCBMb/dj3r6Bg543WBP38DXga8PD/afi7EfrsN4dNd2jGvpOoAFDHlKAA8BPwR+pSqNPX0D3wG+MzzY/1zgBRh3Gm/DmEusE0hibOtu4FfAYE/fQN3nFKvVsRqkz4QgNDqarssTPwRBEARBEIKMDIkKgiAIgiAEHBE2QRAEQRCEgCPCJgiCIAiCEHBE2ARBEARBEAKOCJsgCIIgCELAEWETBEEQBEEIOCJsgiAIgiAIAUeETRAEQRAEIeCIsAmCIAiCIAQcETZBEARBEISAI8ImCIIgCIIQcETYBEEQBEEQAo4ImyAIgiAIQsARYRMEQRAEQQg4ImyCIAiCIAgBR4RNEARBEAQh4IiwCYIgCIIgBBwRNkEQBEEQhIAjwiYIgiAIghBwRNgEQRAEQRACjgibIAiCIAhCwBFhEwRBEARBCDgibIIgCIIgCAFHhE0QBEEQBCHgiLAJgiAIgiAEHBE2QRAEQRCEgCPCJgiCIAiCEHBE2ARBEARBEAKOCJsgCIIgCELAEWETBEEQBEEIOCJsgiAIgiAIAUeETRAEQRAEIeCIsAmCIAiCIAQcETZBEARBEISAI8ImCIIgCIIQcETYBEEQBEEQAo4ImyAIgiAIQsD5/wEcDseBL/n4tQAAAABJRU5ErkJggg==')

GENDERS = ["Male", "Female", "Other"]
STUDENT_STATUS = ["Active", "Inactive", "Passed Out", "Left"]
EXAM_TYPES = ["Unit Test", "Mid Term", "Half Yearly", "Annual / Final",
              "Pre-Board", "Practical", "Internal Assessment"]
EXAM_STATUS = ["Scheduled", "Ongoing", "Completed", "Result Declared", "Cancelled"]
SECTIONS = ["A", "B", "C", "D", "E"]


app = Flask(__name__, static_folder=None)
app.jinja_loader = DictLoader(TEMPLATES)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)


@app.route("/static/<path:filename>", endpoint="static")
def builtin_static(filename):
    """Stylesheet and icon are served straight from this file."""
    if filename in ("style.css", "style/main.css"):
        return Response(STYLE_CSS, mimetype="text/css")
    if filename in ("icon.png", "favicon.ico", "favicon.png"):
        return Response(base64.b64decode(ICON_PNG_B64), mimetype="image/png")
    abort(404)


# --------------------------------------------------------------------------
#  small helpers
# --------------------------------------------------------------------------
def norm_date(text):
    """dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy or yyyy-mm-dd -> yyyy-mm-dd."""
    text = (text or "").strip()
    if not text:
        return ""
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def disp_date(text):
    text = (text or "").strip()
    if not text:
        return ""
    try:
        return datetime.strptime(text, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return text


def norm_time(text):
    text = (text or "").strip()
    if not text:
        return ""
    for fmt in ("%H:%M", "%I:%M %p", "%I:%M%p", "%H.%M"):
        try:
            return datetime.strptime(text.upper(), fmt).strftime("%H:%M")
        except ValueError:
            continue
    return None


def to_float(text, default=None):
    text = (text or "").strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return None


def grade_for(percentage):
    if percentage is None:
        return "-"
    if percentage >= 91:
        return "A1"
    if percentage >= 81:
        return "A2"
    if percentage >= 71:
        return "B1"
    if percentage >= 61:
        return "B2"
    if percentage >= 51:
        return "C1"
    if percentage >= 41:
        return "C2"
    if percentage >= 33:
        return "D"
    return "E"


def fmt_num(value, digits=2):
    if value is None:
        return ""
    value = float(value)
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")


def exam_label(row):
    """Type · Class · Year - how an exam is written everywhere."""
    if row is None:
        return ""
    etype = row["exam_type"] or row["exam_name"] or "Exam"
    parts = [etype]
    if (row["class_name"] or "").strip():
        parts.append(f"Class {row['class_name'].strip()}")
    if (row["academic_year"] or "").strip():
        parts.append(row["academic_year"].strip())
    return "  ·  ".join(parts)


# --------------------------------------------------------------------------
#  database
# --------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS attendance (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL,
    class_name  TEXT,
    section     TEXT,
    att_date    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'Present',
    remarks     TEXT,
    marked_by   INTEGER,
    UNIQUE(student_id, att_date)
);

CREATE TABLE IF NOT EXISTS homework (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    class_name  TEXT,
    section     TEXT,
    subject_id  INTEGER,
    title       TEXT NOT NULL,
    details     TEXT,
    due_date    TEXT,
    created_by  INTEGER,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS circulars (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    body        TEXT,
    audience    TEXT DEFAULT 'all',
    class_name  TEXT,
    section     TEXT,
    pinned      INTEGER DEFAULT 0,
    posted_by   INTEGER,
    posted_on   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fee_heads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    class_name  TEXT,
    name        TEXT NOT NULL,
    amount      REAL NOT NULL DEFAULT 0,
    frequency   TEXT DEFAULT 'Monthly'
);

CREATE TABLE IF NOT EXISTS fee_payments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL,
    head_id     INTEGER,
    amount      REAL NOT NULL,
    paid_on     TEXT NOT NULL,
    mode        TEXT DEFAULT 'Cash',
    receipt_no  TEXT,
    remarks     TEXT,
    recorded_by INTEGER
);

CREATE TABLE IF NOT EXISTS timetable (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    class_name  TEXT NOT NULL,
    section     TEXT,
    day         TEXT NOT NULL,
    period      INTEGER NOT NULL,
    subject_id  INTEGER,
    teacher     TEXT,
    room        TEXT,
    UNIQUE(class_name, section, day, period)
);

CREATE TABLE IF NOT EXISTS transport_routes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    route_name   TEXT NOT NULL,
    vehicle_no   TEXT,
    driver_name  TEXT,
    driver_phone TEXT,
    capacity     INTEGER DEFAULT 40,
    stops        TEXT
);

CREATE TABLE IF NOT EXISTS student_transport (
    student_id INTEGER PRIMARY KEY,
    route_id   INTEGER,
    stop_name  TEXT
);

CREATE TABLE IF NOT EXISTS books (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    title    TEXT NOT NULL,
    author   TEXT,
    isbn     TEXT,
    category TEXT,
    copies   INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS book_issues (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id     INTEGER NOT NULL,
    student_id  INTEGER NOT NULL,
    issued_on   TEXT NOT NULL,
    due_on      TEXT,
    returned_on TEXT,
    fine        REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS staff (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL,
    role      TEXT,
    subject   TEXT,
    phone     TEXT,
    email     TEXT,
    join_date TEXT,
    salary    REAL,
    active    INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS enquiries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    child_name   TEXT NOT NULL,
    parent_name  TEXT,
    phone        TEXT,
    class_wanted TEXT,
    source       TEXT,
    status       TEXT DEFAULT 'New',
    notes        TEXT,
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    details     TEXT,
    event_date  TEXT,
    kind        TEXT DEFAULT 'Event',
    created_by  INTEGER
);

CREATE TABLE IF NOT EXISTS hostel_rooms (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    block    TEXT,
    room_no  TEXT NOT NULL,
    capacity INTEGER DEFAULT 4,
    kind     TEXT DEFAULT 'Boys'
);

CREATE TABLE IF NOT EXISTS hostel_allotments (
    student_id  INTEGER PRIMARY KEY,
    room_id     INTEGER,
    allotted_on TEXT
);

CREATE TABLE IF NOT EXISTS inventory_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    category      TEXT,
    unit          TEXT DEFAULT 'pcs',
    quantity      REAL DEFAULT 0,
    reorder_level REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS inventory_moves (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id  INTEGER NOT NULL,
    kind     TEXT NOT NULL,
    qty      REAL NOT NULL,
    note     TEXT,
    moved_on TEXT,
    by_user  INTEGER
);

CREATE TABLE IF NOT EXISTS payroll (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id INTEGER NOT NULL,
    month    TEXT NOT NULL,
    amount   REAL NOT NULL,
    status   TEXT DEFAULT 'Pending',
    paid_on  TEXT,
    UNIQUE(staff_id, month)
);

CREATE TABLE IF NOT EXISTS notifications (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    channel  TEXT DEFAULT 'SMS',
    audience TEXT DEFAULT 'all',
    message  TEXT NOT NULL,
    sent_on  TEXT DEFAULT CURRENT_TIMESTAMP,
    by_user  INTEGER
);

CREATE TABLE IF NOT EXISTS polls (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    question   TEXT NOT NULL,
    options    TEXT NOT NULL,
    active     INTEGER DEFAULT 1,
    created_on TEXT DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER
);

CREATE TABLE IF NOT EXISTS poll_votes (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    poll_id  INTEGER NOT NULL,
    user_id  INTEGER NOT NULL,
    choice   INTEGER NOT NULL,
    voted_on TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(poll_id, user_id)
);

CREATE TABLE IF NOT EXISTS leave_requests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL,
    from_date   TEXT NOT NULL,
    to_date     TEXT NOT NULL,
    reason      TEXT,
    status      TEXT DEFAULT 'Pending',
    applied_on  TEXT DEFAULT CURRENT_TIMESTAMP,
    decided_by  INTEGER,
    decided_on  TEXT,
    remark      TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    k TEXT PRIMARY KEY,
    v TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    full_name     TEXT,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',
    student_id    INTEGER,
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS students (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id       INTEGER,
    admission_no   TEXT NOT NULL UNIQUE,
    roll_no        TEXT NOT NULL,
    name           TEXT NOT NULL,
    class_name     TEXT NOT NULL,
    section        TEXT,
    dob            TEXT,
    gender         TEXT,
    father_name    TEXT,
    mother_name    TEXT,
    phone          TEXT,
    email          TEXT,
    address        TEXT,
    admission_date TEXT,
    status         TEXT DEFAULT 'Active',
    created_at     TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS exams (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id      INTEGER,
    exam_name     TEXT NOT NULL,
    exam_type     TEXT,
    academic_year TEXT,
    class_name    TEXT,
    start_date    TEXT,
    end_date      TEXT,
    status        TEXT DEFAULT 'Scheduled',
    remarks       TEXT,
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS subjects (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id     INTEGER,
    subject_code TEXT NOT NULL UNIQUE,
    subject_name TEXT NOT NULL,
    class_name   TEXT,
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS exam_schedule (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id     INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    subject_id  INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    exam_date   TEXT,
    start_time  TEXT,
    duration    INTEGER,
    room        TEXT,
    invigilator TEXT,
    max_marks   REAL DEFAULT 100,
    pass_marks  REAL DEFAULT 33,
    UNIQUE(exam_id, subject_id)
);
CREATE TABLE IF NOT EXISTS marks (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id        INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    student_id     INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    subject_id     INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    marks_obtained REAL,
    remarks        TEXT,
    updated_at     TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(exam_id, student_id, subject_id)
);
"""


class Row(dict):
    """Behaves like sqlite3.Row: row["name"] and row[0] both work."""

    def __init__(self, cols, values):
        super().__init__(zip(cols, values))

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return dict.__getitem__(self, key)


class _Cursor:
    def __init__(self, cur):
        self._cur = cur

    def _wrap(self, values):
        if values is None:
            return None
        cols = [d[0] for d in (self._cur.description or [])]
        return Row(cols, values)

    def fetchone(self):
        return self._wrap(self._cur.fetchone())

    def fetchall(self):
        return [self._wrap(v) for v in self._cur.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())

    @property
    def lastrowid(self):
        return getattr(self._cur, "lastrowid", None)

    @property
    def description(self):
        return self._cur.description

    def close(self):
        return None


class CloudDB:
    """Turso over its plain HTTP API - no native package needed.

    Every statement is one POST to /v2/pipeline, so the app installs nothing
    extra and cannot break on a Python version without wheels.
    """

    def __init__(self, url, token):
        base = url.strip().rstrip("/")
        if base.startswith("libsql://"):
            base = "https://" + base[len("libsql://"):]
        elif not base.startswith(("http://", "https://")):
            base = "https://" + base
        self.endpoint = base + "/v2/pipeline"
        self.token = token

    @staticmethod
    def _arg(value):
        if value is None:
            return {"type": "null"}
        if isinstance(value, bool):
            return {"type": "integer", "value": "1" if value else "0"}
        if isinstance(value, int):
            return {"type": "integer", "value": str(value)}
        if isinstance(value, float):
            return {"type": "float", "value": value}
        if isinstance(value, (bytes, bytearray)):
            return {"type": "blob",
                    "value": base64.b64encode(bytes(value)).decode()}
        return {"type": "text", "value": str(value)}

    def _call(self, sql, params=()):
        body = {"requests": [
            {"type": "execute",
             "stmt": {"sql": sql,
                      "args": [self._arg(p) for p in params],
                      "want_rows": True}},
            {"type": "close"}]}
        request = urllib.request.Request(
            self.endpoint, data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self.token}",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode())
        first = payload["results"][0]
        if first.get("type") == "error":
            raise RuntimeError(first.get("error", {}).get("message", "sql error"))
        return first["response"]["result"]

    def execute(self, sql, params=()):
        return _HTTPCursor(self._call(sql, params))

    def executescript(self, script):
        for statement in script.split(";"):
            if statement.strip():
                self._call(statement)

    def commit(self):
        return None

    def close(self):
        return None


class _HTTPCursor:
    def __init__(self, result):
        self._result = result or {}

    @staticmethod
    def _value(cell):
        kind = cell.get("type")
        value = cell.get("value")
        if kind == "null":
            return None
        if kind == "integer":
            return int(value)
        if kind == "float":
            return float(value)
        if kind == "blob":
            return base64.b64decode(value)
        return value

    def fetchall(self):
        cols = [c["name"] for c in self._result.get("cols", [])]
        return [Row(cols, [self._value(c) for c in row])
                for row in self._result.get("rows", [])]

    def fetchone(self):
        rows = self.fetchall()
        return rows[0] if rows else None

    def __iter__(self):
        return iter(self.fetchall())

    @property
    def lastrowid(self):
        try:
            return int(self._result.get("last_insert_rowid") or 0)
        except (TypeError, ValueError):
            return None

    @property
    def description(self):
        return [(c["name"],) for c in self._result.get("cols", [])]

    def close(self):
        return None


CLOUD_ERROR = ""


def open_db():
    """The database connection: the cloud one if configured, else the file.

    If the cloud database cannot be reached the app keeps working on the local
    file and remembers the reason, so the site never dies because of a typo in
    an environment variable.
    """
    global CLOUD_ERROR
    if TURSO_URL and not CLOUD_ERROR:
        try:
            conn = CloudDB(TURSO_URL, TURSO_TOKEN)
            conn.execute("SELECT 1")
            CLOUD_ERROR = ""
            return conn
        except Exception as exc:              # noqa: BLE001 - report, never crash
            CLOUD_ERROR = f"{type(exc).__name__}: {exc}"[:300]
            print(f"[exam-manager] CLOUD DATABASE UNREACHABLE - {CLOUD_ERROR}",
                  flush=True)
            print("[exam-manager]   falling back to the local file; data will NOT "
                  "survive a restart", flush=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _migrate(conn):
    """Bring an older database up to date: owner_id columns, a first admin,
    and any pre-existing rows handed to that admin."""
    for table in ("students", "exams", "subjects"):
        if "owner_id" not in _columns(conn, table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN owner_id INTEGER")

    # a student account points at one row of the students table
    if "student_id" not in _columns(conn, "users"):
        conn.execute("ALTER TABLE users ADD COLUMN student_id INTEGER")

    try:
        if "internal_max" not in _columns(conn, "exam_schedule"):
            conn.execute("ALTER TABLE exam_schedule ADD COLUMN internal_max"
                         " REAL DEFAULT 30")
        # papers created before the internal marks existed default to 30
        conn.execute("UPDATE exam_schedule SET internal_max=30"
                     " WHERE internal_max IS NULL OR internal_max=0"
                     " OR internal_max=20")
    except Exception:                        # noqa: BLE001
        pass

    if "theory" not in _columns(conn, "marks"):
        conn.execute("ALTER TABLE marks ADD COLUMN theory REAL")
    if "internal" not in _columns(conn, "marks"):
        conn.execute("ALTER TABLE marks ADD COLUMN internal REAL")

    for table in ("students", "staff"):
        try:
            if "photo" not in _columns(conn, table):
                conn.execute(f"ALTER TABLE {table} ADD COLUMN photo TEXT")
        except Exception:                    # noqa: BLE001 - table may not exist
            pass

    if "signature" not in _columns(conn, "users"):
        conn.execute("ALTER TABLE users ADD COLUMN signature TEXT")

    # a teacher can be the class teacher of one class / section
    for col in ("class_name", "section"):
        if col not in _columns(conn, "users"):
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")

    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        username = ADMIN_USERNAME
        password = ADMIN_PASSWORD
        generated = False
        if not password:
            password = secrets.token_urlsafe(9)
            generated = True
        conn.execute(
            "INSERT INTO users (username, full_name, password_hash, role)"
            " VALUES (?,?,?,?)",
            (username, "Administrator", generate_password_hash(password), "admin"))
        print("=" * 60, flush=True)
        print("[exam-manager] first admin account created", flush=True)
        print(f"[exam-manager]   username: {username}", flush=True)
        print(f"[exam-manager]   password: {password}", flush=True)
        if generated:
            print("[exam-manager]   generated - set ADMIN_PASSWORD to pick "
                  "your own", flush=True)
        print("=" * 60, flush=True)

    admin_id = conn.execute(
        "SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()[0]
    for table in ("students", "exams", "subjects"):
        conn.execute(f"UPDATE {table} SET owner_id=? WHERE owner_id IS NULL",
                     (admin_id,))
    conn.commit()


def init_db(verbose=False):
    conn = open_db()
    try:
        conn.executescript(SCHEMA)
    except Exception as exc:                 # noqa: BLE001
        print(f"[exam-manager] SCHEMA FAILED: {type(exc).__name__}: {exc}",
              flush=True)
        if verbose:
            raise
        return False
    _migrate(conn)
    # anything an admin created belongs to the school, not to the admin
    admin_ids = [r[0] for r in conn.execute(
        "SELECT id FROM users WHERE role='admin'")]
    if admin_ids:
        marks = ",".join("?" * len(admin_ids))
        for table in ("students", "exams", "subjects"):
            conn.execute(f"UPDATE {table} SET owner_id=NULL "
                         f"WHERE owner_id IN ({marks})", admin_ids)
    conn.commit()
    conn.close()
    if verbose:
        return True
    return True


def get_db():
    if "db" not in g:
        g.db = open_db()
        if not TURSO_URL:
            g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, params=(), one=False):
    cur = get_db().execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


def execute(sql, params=()):
    db = get_db()
    cur = db.execute(sql, params)
    db.commit()
    last = cur.lastrowid
    cur.close()
    return last


# --------------------------------------------------------------------------
#  business logic
# --------------------------------------------------------------------------
def compute_results(exam_id, class_name):
    schedule = query("SELECT subject_id, max_marks, pass_marks FROM exam_schedule"
                     " WHERE exam_id=?", (exam_id,))
    if not schedule:
        return []
    max_by_sub = {r["subject_id"]: (r["max_marks"] or 0) for r in schedule}
    pass_by_sub = {r["subject_id"]: (r["pass_marks"] or 0) for r in schedule}

    students = query(
        "SELECT id, admission_no, roll_no, name FROM students WHERE class_name=?"
        " ORDER BY CAST(roll_no AS INTEGER), roll_no", (class_name,))
    marks = query("SELECT * FROM marks WHERE exam_id=?", (exam_id,))
    by_student = {}
    for m in marks:
        by_student.setdefault(m["student_id"], {})[m["subject_id"]] = m

    results = []
    for st in students:
        smap = by_student.get(st["id"], {})
        if not smap:
            continue
        obtained = total_max = 0.0
        failed = 0
        for sub_id, mx in max_by_sub.items():
            row = smap.get(sub_id)
            if row is None or row["marks_obtained"] is None:
                continue
            got = float(row["marks_obtained"])
            obtained += got
            total_max += float(mx)
            if got < float(pass_by_sub.get(sub_id, 0)):
                failed += 1
        if total_max <= 0:
            continue
        pct = round(obtained / total_max * 100, 2)
        results.append({
            "student_id": st["id"],
            "admission_no": st["admission_no"],
            "roll_no": st["roll_no"],
            "name": st["name"],
            "obtained": round(obtained, 2),
            "total_max": round(total_max, 2),
            "percentage": pct,
            "grade": grade_for(pct),
            "failed_subjects": failed,
            "result": "Pass" if (failed == 0 and pct >= 33) else "Fail",
        })

    results.sort(key=lambda r: (-r["percentage"], r["roll_no"]))
    rank, last_pct = 0, None
    for i, r in enumerate(results, start=1):
        if last_pct is None or r["percentage"] != last_pct:
            rank, last_pct = i, r["percentage"]
        r["rank"] = rank
    return results


# --------------------------------------------------------------------------
#  auth + shared template values
# --------------------------------------------------------------------------
@app.before_request
def load_user():
    """Everyone must be logged in; the session holds the user id."""
    g.user = None
    user_id = session.get("uid")
    if user_id:
        g.user = query("SELECT * FROM users WHERE id=? AND active=1",
                       (user_id,), one=True)
        if g.user is None:
            session.clear()
    if request.endpoint in ("welcome", "about", "login", "static", "healthz",
                            "robots", "sitemap", "setup_route", "demo_seed",
                            "report_card", "my_leave", "events", "my_profile"):
        return None
    if g.user is None:
        return redirect(url_for("login", next=request.path))
    if is_student():
        # a student account is read-only: one page, no forms, no writes
        if request.endpoint not in ("my_home", "my_result", "my_profile", "my_attendance", "my_homework",
                                    "notices", "password", "my_fees",
                                    "my_timetable", "my_transport",
                                    "my_library", "logout"):
            return redirect(url_for("my_result"))
        if (request.method not in ("GET", "HEAD")
                and request.endpoint not in ("password", "my_leave")):
            flash("A student account can only view results.", "error")
            return redirect(url_for("my_result"))
    return None


def uid():
    return session.get("uid")


def is_admin():
    user = getattr(g, "user", None)
    return bool(user) and user["role"] == "admin"


def is_student():
    user = getattr(g, "user", None)
    return bool(user) and user["role"] in ("student", "parent")


def setting(key, default=""):
    row = query("SELECT v FROM settings WHERE k=?", (key,), one=True)
    return (row["v"] if row and row["v"] is not None else default)


def school_logo():
    """The logo uploaded from Settings, or the built-in icon."""
    stored = setting("school_logo", "")
    if stored:
        return stored
    for name in ("LOGO_PNG_B64", "ICON_PNG_B64"):
        data = globals().get(name, "")
        if data:
            return "data:image/png;base64," + data
    return ""


def subject_rows_for(exam_id, student_id):
    """Per-subject marks for one student in one exam."""
    return query("""SELECT s.subject_name, s.subject_code, sc.max_marks,
                           sc.pass_marks, m.marks_obtained, m.theory,
                           m.internal, m.subject_id
                    FROM marks m
                    JOIN subjects s ON s.id = m.subject_id
                    LEFT JOIN exam_schedule sc ON sc.exam_id = m.exam_id
                           AND sc.subject_id = m.subject_id
                    WHERE m.exam_id=? AND m.student_id=?
                    ORDER BY s.subject_code""", (exam_id, student_id))


def co_grades_for(row):
    """The six co-scholastic grades for one result row."""
    def band(v, top=90, good=75, ok=60):
        return "A" if v >= top else "B" if v >= good else \
               "C" if v >= ok else "D"
    pct = float(row["percentage"] or 0)
    return [
        ("Discipline", band(pct, 85, 70, 50)),
        ("Nature &amp; environment", band(pct, 75, 60, 45)),
        ("Co-curricular activities", band(pct + 5, 80, 65, 50)),
        ("Sports &amp; games", band(pct, 80, 65, 50)),
        ("Art &amp; craft / music", band(pct - 8, 70, 55, 40)),
        ("General conduct", band(pct, 90, 75, 60)),
    ]


def class_teacher_of(class_name, section=""):
    """The teacher account whose class matches, else None."""
    row = query("""SELECT * FROM users WHERE role='user' AND IFNULL(class_name,'')=?
                   AND (IFNULL(section,'')=? OR IFNULL(section,'')='')
                   ORDER BY (IFNULL(section,'')=?) DESC LIMIT 1""",
                (class_name or "", section or "", section or ""), one=True)
    return row


def current_user_full_name():
    u = query("SELECT full_name, username FROM users WHERE id=?", (uid(),), one=True)
    if not u:
        return ""
    return (u["full_name"] or u["username"] or "").strip()


def my_class():
    """(class_name, section) a teacher is responsible for, or None."""
    user = getattr(g, "user", None)
    if not user or user["role"] != "user":
        return None
    if not user["class_name"]:
        return None
    return (user["class_name"], user["section"] or "")


def class_scope():
    """The classes this user may work with (None means every class)."""
    if is_admin():
        return None
    return my_class()


def my_student():
    """The students row behind a student or parent account."""
    user = getattr(g, "user", None)
    if not user or user["role"] not in ("student", "parent") or not user["student_id"]:
        return None
    return query("SELECT * FROM students WHERE id=?", (user["student_id"],),
                 one=True)


def owner_value():
    """Rows an admin creates belong to the school (NULL = shared).

    A teacher's rows carry their own id, so they stay private to them.
    """
    return None if is_admin() else uid()


def owned_where(extra="", params=()):
    """WHERE fragment: your own rows plus the school-wide ones."""
    clauses, args = [], list(params)
    if extra:
        clauses.append(extra)
    if not is_admin():
        clauses.append("(owner_id=? OR owner_id IS NULL)")
        args.append(uid() or 0)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", args


def owns(table, row_id):
    """The row, if the current user may EDIT or DELETE it; else None.

    School-wide rows (owner_id NULL) are managed by the admin, so a teacher
    can read them but not change them.
    """
    if not row_id:
        return None
    row = query(f"SELECT * FROM {table} WHERE id=?", (row_id,), one=True)
    if row is None:
        return None
    if is_admin():
        return row
    return row if row["owner_id"] == uid() else None


def visible(table, row_id):
    """The row, if the current user may READ it (own or school-wide)."""
    if not row_id:
        return None
    row = query(f"SELECT * FROM {table} WHERE id=?", (row_id,), one=True)
    if row is None:
        return None
    if is_admin() or row["owner_id"] is None or row["owner_id"] == uid():
        return row
    return None


@app.context_processor
def inject_globals():
    try:
        current_name = setting("school_name", SCHOOL_NAME)
    except Exception:                        # noqa: BLE001 - never break a page
        current_name = SCHOOL_NAME
    try:
        current_app_name = setting("app_name", APP_NAME)
    except Exception:                        # noqa: BLE001
        current_app_name = APP_NAME
    return {
        "app_name": current_app_name,
        "school_name": current_name,
        "school_logo": school_logo(),
        "current_user": getattr(g, "user", None),
        "is_admin": is_admin(),
        "cloud_db": bool(TURSO_URL) and not CLOUD_ERROR,
        "db_warning": ("Cloud database se connection nahi hua - data temporary "
                       "hai. /healthz dekhein." if (TURSO_URL and CLOUD_ERROR)
                       else ""),
        "today": datetime.now().strftime("%d/%m/%Y"),
    }


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        user = query("SELECT * FROM users WHERE LOWER(username)=LOWER(?)",
                     (username,), one=True)
        if (user and user["active"]
                and check_password_hash(user["password_hash"], password)):
            session.clear()
            session["uid"] = user["id"]
            if user["role"] in ("student", "parent"):
                return redirect(url_for("my_home"))
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Wrong username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def welcome():
    """The front door is the login screen - nothing else."""
    if getattr(g, "user", None):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/about")
def about():
    """Public, indexable page about the product (linked from the login page)."""
    return render_template("welcome.html")




def attendance_trend(days=7, class_name=None):
    """Day-by-day attendance percentage for the little bar charts."""
    out = []
    for back in range(days - 1, -1, -1):
        day = (datetime.now() - timedelta(days=back)).strftime("%Y-%m-%d")
        sql = """SELECT SUM(CASE WHEN status IN ('Present','Late') THEN 1 ELSE 0 END) p,
                        COUNT(*) n FROM attendance WHERE att_date=?"""
        args = [day]
        if class_name:
            sql += " AND class_name=?"
            args.append(class_name)
        row = query(sql, args, one=True)
        pct = round((row["p"] or 0) / row["n"] * 100) if row and row["n"] else 0
        out.append({"day": day[8:10], "pct": pct, "marked": row["n"] if row else 0})
    return out


def fee_by_class():
    """How much of each class's fee has come in."""
    out = []
    for row in query("""SELECT s.class_name cls,
                               (SELECT IFNULL(SUM(f.amount),0) FROM fee_heads f
                                WHERE IFNULL(f.class_name,'')=s.class_name) total,
                               (SELECT IFNULL(SUM(p.amount),0) FROM fee_payments p
                                JOIN students st ON st.id = p.student_id
                                WHERE st.class_name = s.class_name) paid
                        FROM students s WHERE s.class_name<>''
                        GROUP BY s.class_name ORDER BY s.class_name"""):
        total = float(row["total"] or 0)
        paid = float(row["paid"] or 0)
        out.append({"cls": row["cls"],
                    "pct": round(paid / total * 100) if total else 0,
                    "paid": paid, "total": total})
    return out


def teacher_dashboard():
    """What a class teacher actually needs first thing in the morning."""
    scope = my_class()
    cls, sec = (scope if scope else ("", ""))
    today = datetime.now().strftime("%Y-%m-%d")
    today_name = datetime.now().strftime("%A")

    where, args = " WHERE status='Active'", []
    if cls:
        where += " AND class_name=?"
        args.append(cls)
        if sec:
            where += " AND IFNULL(section,'')=?"
            args.append(sec)
    students = query("SELECT * FROM students" + where +
                     " ORDER BY CAST(roll_no AS INTEGER), roll_no", args)

    marked = query("""SELECT SUM(CASE WHEN status IN ('Present','Late') THEN 1 ELSE 0 END) p,
                             COUNT(*) n FROM attendance WHERE att_date=?""",
                   (today,), one=True)
    att_pct = round((marked["p"] or 0) / marked["n"] * 100) if marked and marked["n"] else 0
    absent_today = query("""SELECT s.name, s.roll_no, a.status, a.remarks
                            FROM attendance a JOIN students s ON s.id = a.student_id
                            WHERE a.att_date=? AND a.status IN ('Absent','Leave')
                            ORDER BY CAST(s.roll_no AS INTEGER)""", (today,))

    homework_rows = query("""SELECT h.*, s.subject_name FROM homework h
                             LEFT JOIN subjects s ON s.id = h.subject_id
                             WHERE h.created_by=? ORDER BY h.id DESC LIMIT 4""",
                          (uid(),))
    periods = query("""SELECT t.period, sub.subject_code, sub.subject_name, t.teacher
                       FROM timetable t LEFT JOIN subjects sub ON sub.id = t.subject_id
                       WHERE t.class_name=? AND IFNULL(t.section,'')=? AND t.day=?
                       ORDER BY t.period""", (cls, sec, today_name)) if cls else []

    papers = query("""SELECT sc.*, e.exam_type, e.class_name, s.subject_name
                      FROM exam_schedule sc
                      JOIN exams e ON e.id = sc.exam_id
                      LEFT JOIN subjects s ON s.id = sc.subject_id
                      WHERE IFNULL(sc.exam_date,'') >= ?
                      ORDER BY sc.exam_date LIMIT 5""", (today,))

    notices_rows = query("SELECT * FROM circulars ORDER BY pinned DESC, id DESC LIMIT 3")

    trend = attendance_trend(7, cls or None)
    top = []
    last_exam = query("SELECT id, class_name FROM exams WHERE IFNULL(class_name,'')=?"
                      " ORDER BY id DESC LIMIT 1", (cls,), one=True) if cls else None
    if last_exam:
        rows = compute_results(last_exam["id"], (last_exam["class_name"] or "").strip())
        top = rows[:3]
    class_due = []
    for item in fee_summary(cls):
        if item["due"] > 0:
            class_due.append(item)
    class_due = sorted(class_due, key=lambda x: -x["due"])[:5]
    overdue_books = query("""SELECT COUNT(*) c FROM book_issues
                             WHERE returned_on IS NULL AND IFNULL(due_on,'')<>''
                               AND due_on < ?""",
                          (datetime.now().strftime("%Y-%m-%d"),), one=True)["c"]

    my_exams = query("SELECT COUNT(*) c FROM exams" + owned_where()[0],
                     owned_where()[1], one=True)["c"]
    stats = {"students": len(students), "exams": my_exams,
             "homework": len(homework_rows), "attendance": att_pct}
    return render_template("teacher_dashboard.html", stats=stats, cls=cls,
                           sec=sec, students=students[:8], absent_today=absent_today,
                           trend=trend, top=top, class_due=class_due,
                           overdue_books=overdue_books, fmt_num=fmt_num,
                           homework=homework_rows, periods=periods, papers=papers,
                           notices=notices_rows, today_name=today_name,
                           disp_date=disp_date, today=today)


@app.route("/dashboard")
def dashboard():
    if not is_admin():
        return teacher_dashboard()
    sw, sa = owned_where()
    ew, ea = owned_where()
    uw, ua = owned_where()
    if is_admin():
        papers = query("SELECT COUNT(*) c FROM exam_schedule", one=True)["c"]
    else:
        papers = query("""SELECT COUNT(*) c FROM exam_schedule sc
                          JOIN exams e ON e.id = sc.exam_id
                          WHERE (e.owner_id=? OR e.owner_id IS NULL)""",
                       (uid(),), one=True)["c"]
    stats = {
        "students": query("SELECT COUNT(*) c FROM students" + sw, sa, one=True)["c"],
        "exams": query("SELECT COUNT(*) c FROM exams" + ew, ea, one=True)["c"],
        "subjects": query("SELECT COUNT(*) c FROM subjects" + uw, ua, one=True)["c"],
        "papers": papers,
    }
    today = datetime.now().strftime("%Y-%m-%d")
    att = query("""SELECT
                     SUM(CASE WHEN status IN ('Present','Late') THEN 1 ELSE 0 END) p,
                     COUNT(*) n FROM attendance WHERE att_date=?""",
                (today,), one=True)
    att_pct = round((att["p"] or 0) / att["n"] * 100) if att and att["n"] else 0
    fees = query("""SELECT (SELECT IFNULL(SUM(amount),0) FROM fee_heads) total,
                           (SELECT IFNULL(SUM(amount),0) FROM fee_payments) paid""",
                 one=True)
    collected = min(100, round((fees["paid"] or 0) / fees["total"] * 100)) if fees["total"] else 0
    last_exam = query("SELECT id, exam_type, class_name FROM exams"
                      " ORDER BY id DESC LIMIT 1", one=True)
    pass_pct = 0
    if last_exam:
        rows = compute_results(last_exam["id"],
                               (last_exam["class_name"] or "").strip())
        if rows:
            passed = sum(1 for r in rows if r["result"] == "Pass")
            pass_pct = round(passed / len(rows) * 100)
    charts = {"attendance": att_pct, "fees": collected, "pass": pass_pct,
              "att_marked": att["n"] if att else 0}

    recent = query("SELECT * FROM students" + sw +
                   " ORDER BY id DESC LIMIT 10", sa)
    exams = query("SELECT * FROM exams" + ew + " ORDER BY id DESC LIMIT 10", ea)
    defaulters = query("""SELECT s.name, s.class_name,
                                 (SELECT IFNULL(SUM(f.amount),0) FROM fee_heads f
                                  WHERE IFNULL(f.class_name,'')=s.class_name) total,
                                 (SELECT IFNULL(SUM(p.amount),0) FROM fee_payments p
                                  WHERE p.student_id=s.id) paid
                          FROM students s WHERE s.status='Active'""")
    due_list = sorted(
        [{"name": d["name"], "class_name": d["class_name"],
          "due": float(d["total"] or 0) - float(d["paid"] or 0)}
         for d in defaulters if float(d["total"] or 0) - float(d["paid"] or 0) > 0],
        key=lambda x: -x["due"])[:5]
    upcoming = query("""SELECT * FROM events
                        WHERE IFNULL(event_date,'') >= ?
                        ORDER BY event_date LIMIT 4""",
                     (today,))
    latest_notices = query("""SELECT * FROM circulars
                              ORDER BY pinned DESC, id DESC LIMIT 3""")
    trend = attendance_trend(7)
    classes_fee = fee_by_class()
    overdue = query("""SELECT COUNT(*) c FROM book_issues
                       WHERE returned_on IS NULL AND IFNULL(due_on,'')<>''
                         AND due_on < ?""",
                    (today,), one=True)["c"]
    staff_count = query("SELECT COUNT(*) c FROM staff WHERE active=1", one=True)["c"]
    return render_template("dashboard.html", stats=stats, recent=recent,
                           exams=exams, disp_date=disp_date, charts=charts,
                           due_list=due_list, upcoming=upcoming,
                           latest_notices=latest_notices, fmt_num=fmt_num,
                           trend=trend, classes_fee=classes_fee, 
                           overdue=overdue, 
                           staff_count=staff_count)


# --------------------------------------------------------------------------
#  students
# --------------------------------------------------------------------------
@app.route("/students")
def students():
    term = request.args.get("q", "").strip()
    extra, params = "", []
    if term:
        like = f"%{term}%"
        extra = ("(name LIKE ? OR roll_no LIKE ? OR admission_no LIKE ?"
                 " OR class_name LIKE ?)")
        params = [like, like, like, like]
    where, args = owned_where(extra, params)
    rows = query("SELECT * FROM students" + where +
                 " ORDER BY class_name, CAST(roll_no AS INTEGER), roll_no", args)

    cwhere, cargs = owned_where("class_name<>''")
    classes = [r["class_name"] for r in query(
        "SELECT DISTINCT class_name FROM students" + cwhere +
        " ORDER BY class_name", cargs)]

    edit_id = request.args.get("edit", type=int)
    editing = owns("students", edit_id) if edit_id else None
    owners = {None: "School"}
    if is_admin():
        owners.update({u["id"]: u["username"]
                       for u in query("SELECT id, username FROM users")})
    else:
        owners[uid()] = "You"
    return render_template("students.html", students=rows, q=term,
                           classes=classes, disp_date=disp_date,
                           genders=GENDERS, sections=SECTIONS,
                           statuses=STUDENT_STATUS, editing=editing,
                           owners=owners)


@app.route("/students/save", methods=["POST"])
def student_save():
    f = request.form
    sid = f.get("id") or ""
    values = (
        f.get("admission_no", "").strip(), f.get("roll_no", "").strip(),
        f.get("name", "").strip(), f.get("class_name", "").strip(),
        f.get("section", "").strip(), norm_date(f.get("dob")),
        f.get("gender", "").strip(), f.get("father_name", "").strip(),
        f.get("mother_name", "").strip(), f.get("phone", "").strip(),
        f.get("email", "").strip(), f.get("address", "").strip(),
        norm_date(f.get("admission_date")),
        f.get("status", "").strip() or "Active",
    )
    adm, roll, name, cls, _sec, dob, _g, _f, _m, phone, email, _a, adm_date, _s = values
    if not adm or not roll or not name or not cls:
        flash("Admission No, Roll No, Name and Class are required.", "error")
        return redirect(url_for("students"))
    if dob is None:
        flash("Date of birth is not a valid date (use dd/mm/yyyy).", "error")
        return redirect(url_for("students"))
    if not adm_date:
        flash("Date of admission is required - type it as dd/mm/yyyy.", "error")
        return redirect(url_for("students"))
    if adm_date is None:
        flash("Date of admission is not a valid date (use dd/mm/yyyy).", "error")
        return redirect(url_for("students"))
    if phone and not phone.replace("+", "").replace("-", "").replace(" ", "").isdigit():
        flash("Phone must contain digits only.", "error")
        return redirect(url_for("students"))
    if email and "@" not in email:
        flash("Email does not look valid.", "error")
        return redirect(url_for("students"))

    dwhere, dargs = owned_where("admission_no=? AND id<>?",
                                (adm, int(sid) if sid else 0))
    dup = query("SELECT id FROM students" + dwhere, dargs, one=True)
    if dup:
        flash(f"Admission No {adm} already exists.", "error")
        return redirect(url_for("students"))

    if sid:
        if owns("students", int(sid)) is None:
            flash("You can only edit your own students.", "error")
            return redirect(url_for("students"))
        execute("""UPDATE students SET admission_no=?, roll_no=?, name=?,
                   class_name=?, section=?, dob=?, gender=?, father_name=?,
                   mother_name=?, phone=?, email=?, address=?, admission_date=?,
                   status=? WHERE id=?""", values + (int(sid),))
        flash(f"Student '{name}' updated.", "ok")
    else:
        execute("""INSERT INTO students (owner_id, admission_no, roll_no, name,
                   class_name, section, dob, gender, father_name, mother_name,
                   phone, email, address, admission_date, status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (owner_value(),) + values)
        flash(f"Student '{name}' added.", "ok")
    return redirect(url_for("students"))


@app.route("/students/<int:sid>/delete", methods=["POST"])
def student_delete(sid):
    row = owns("students", sid)
    if row is None:
        flash("You can only delete your own students.", "error")
        return redirect(url_for("students"))
    execute("DELETE FROM students WHERE id=?", (sid,))
    flash(f"Student '{row['name']}' deleted.", "ok")
    return redirect(url_for("students"))


@app.route("/students.csv")
def students_csv():
    where, args = owned_where()
    rows = query("SELECT * FROM students" + where + " ORDER BY class_name,"
                 " CAST(roll_no AS INTEGER), roll_no", args)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Admission No", "Roll No", "Name", "Class", "Section",
                "Date of Admission", "DOB", "Gender", "Father's Name",
                "Mother's Name", "Phone", "Email", "Address", "Status"])
    for r in rows:
        w.writerow([r["admission_no"], r["roll_no"], r["name"], r["class_name"],
                    r["section"], disp_date(r["admission_date"]),
                    disp_date(r["dob"]), r["gender"], r["father_name"],
                    r["mother_name"], r["phone"], r["email"], r["address"],
                    r["status"]])
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":
                             "attachment; filename=students.csv"})


# --------------------------------------------------------------------------
#  exams
# --------------------------------------------------------------------------
@app.route("/exams")
def exams():
    where, args = owned_where()
    rows = query("SELECT * FROM exams" + where + " ORDER BY id DESC", args)
    edit_id = request.args.get("edit", type=int)
    editing = owns("exams", edit_id) if edit_id else None
    owners = {None: "School"}
    if is_admin():
        owners.update({u["id"]: u["username"]
                       for u in query("SELECT id, username FROM users")})
    else:
        owners[uid()] = "You"
    return render_template("exams.html", exams=rows, disp_date=disp_date,
                           exam_types=EXAM_TYPES, statuses=EXAM_STATUS,
                           editing=editing, owners=owners)


@app.route("/exams/save", methods=["POST"])
def exam_save():
    f = request.form
    eid = f.get("id") or ""
    etype = f.get("exam_type", "").strip()
    year = f.get("academic_year", "").strip()
    cls = f.get("class_name", "").strip()
    sd = norm_date(f.get("start_date"))
    ed = norm_date(f.get("end_date"))

    if not etype:
        flash("Exam type is required.", "error")
        return redirect(url_for("exams"))
    if sd is None or ed is None:
        flash("Dates must be dd/mm/yyyy.", "error")
        return redirect(url_for("exams"))
    if sd and ed and ed < sd:
        flash("End date cannot be before start date.", "error")
        return redirect(url_for("exams"))
    dwhere, dargs = owned_where(
        "exam_type=? AND IFNULL(academic_year,'')=? AND IFNULL(class_name,'')=?"
        " AND id<>?", (etype, year, cls, int(eid) if eid else 0))
    dup = query("SELECT id FROM exams" + dwhere, dargs, one=True)
    if dup:
        flash(f"'{etype}' already exists for class {cls or '-'} "
              f"in {year or '-'}.", "error")
        return redirect(url_for("exams"))

    if eid:
        if owns("exams", int(eid)) is None:
            flash("You can only edit your own exams.", "error")
            return redirect(url_for("exams"))
        execute("""UPDATE exams SET exam_name=?, exam_type=?, academic_year=?,
                   class_name=?, start_date=?, end_date=?, status=?, remarks=?
                   WHERE id=?""",
                (etype, etype, year, cls, sd, ed,
                 f.get("status") or "Scheduled", f.get("remarks", "").strip(),
                 int(eid)))
        flash(f"Exam '{etype}' updated.", "ok")
    else:
        execute("""INSERT INTO exams (owner_id, exam_name, exam_type,
                   academic_year, class_name, start_date, end_date, status,
                   remarks) VALUES (?,?,?,?,?,?,?,?,?)""",
                (owner_value(), etype, etype, year, cls, sd, ed,
                 f.get("status") or "Scheduled", f.get("remarks", "").strip()))
        flash(f"Exam '{etype}' saved.", "ok")
    return redirect(url_for("exams"))


@app.route("/exams/<int:eid>/delete", methods=["POST"])
def exam_delete(eid):
    row = owns("exams", eid)
    if row is None:
        flash("You can only delete your own exams.", "error")
        return redirect(url_for("exams"))
    execute("DELETE FROM exams WHERE id=?", (eid,))
    flash(f"Exam '{row['exam_type'] or row['exam_name']}' deleted.", "ok")
    return redirect(url_for("exams"))


# --------------------------------------------------------------------------
#  subjects
# --------------------------------------------------------------------------
@app.route("/subjects")
def subjects():
    where, args = owned_where()
    rows = query("SELECT * FROM subjects" + where + " ORDER BY subject_code", args)
    edit_id = request.args.get("edit", type=int)
    editing = owns("subjects", edit_id) if edit_id else None
    owners = {None: "School"}
    if is_admin():
        owners.update({u["id"]: u["username"]
                       for u in query("SELECT id, username FROM users")})
    else:
        owners[uid()] = "You"
    return render_template("subjects.html", subjects=rows, editing=editing,
                           owners=owners)


@app.route("/subjects/save", methods=["POST"])
def subject_save():
    f = request.form
    sid = f.get("id") or ""
    code = f.get("subject_code", "").strip().upper()
    name = f.get("subject_name", "").strip()
    cls = f.get("class_name", "").strip()
    if not code or not name:
        flash("Subject code and name are both required.", "error")
        return redirect(url_for("subjects"))
    dwhere, dargs = owned_where("subject_code=? AND id<>?",
                                (code, int(sid) if sid else 0))
    dup = query("SELECT id FROM subjects" + dwhere, dargs, one=True)
    if dup:
        flash(f"Subject code {code} already exists.", "error")
        return redirect(url_for("subjects"))
    if sid:
        if owns("subjects", int(sid)) is None:
            flash("You can only edit your own subjects.", "error")
            return redirect(url_for("subjects"))
        execute("UPDATE subjects SET subject_code=?, subject_name=?,"
                " class_name=? WHERE id=?", (code, name, cls, int(sid)))
        flash(f"Subject '{name}' updated.", "ok")
    else:
        execute("INSERT INTO subjects (owner_id, subject_code, subject_name,"
                " class_name) VALUES (?,?,?,?)", (owner_value(), code, name, cls))
        flash(f"Subject '{name}' added.", "ok")
    return redirect(url_for("subjects"))


@app.route("/subjects/<int:sid>/delete", methods=["POST"])
def subject_delete(sid):
    row = owns("subjects", sid)
    if row is None:
        flash("You can only delete your own subjects.", "error")
        return redirect(url_for("subjects"))
    execute("DELETE FROM subjects WHERE id=?", (sid,))
    flash(f"Subject '{row['subject_name']}' deleted.", "ok")
    return redirect(url_for("subjects"))


@app.route("/subjects/defaults", methods=["POST"])
def subject_defaults():
    defaults = [("ENG", "English"), ("HIN", "Hindi"), ("MAT", "Mathematics"),
                ("SCI", "Science"), ("SST", "Social Science"),
                ("CS", "Computer Science")]
    added = 0
    for code, name in defaults:
        dwhere, dargs = owned_where("subject_code=?", (code,))
        if not query("SELECT id FROM subjects" + dwhere, dargs, one=True):
            execute("INSERT INTO subjects (owner_id, subject_code, subject_name)"
                    " VALUES (?,?,?)", (owner_value(), code, name))
            added += 1
    flash(f"{added} default subject(s) added.", "ok")
    return redirect(url_for("subjects"))


# --------------------------------------------------------------------------
#  schedule
# --------------------------------------------------------------------------
@app.route("/schedule")
def schedule():
    ew, ea = owned_where()
    exams_rows = query("SELECT * FROM exams" + ew + " ORDER BY id DESC", ea)
    sw, sa = owned_where()
    subjects_rows = query("SELECT * FROM subjects" + sw +
                          " ORDER BY subject_code", sa)
    scope_sql = "" if is_admin() else " WHERE (e.owner_id=? OR e.owner_id IS NULL)"
    scope_args = () if is_admin() else (uid(),)
    rows = query("""SELECT sc.*, e.exam_name, e.exam_type, e.academic_year,
                           e.class_name, s.subject_name
                    FROM exam_schedule sc
                    JOIN exams e ON e.id = sc.exam_id
                    JOIN subjects s ON s.id = sc.subject_id""" + scope_sql +
                 """ ORDER BY e.id DESC, sc.exam_date, sc.start_time""",
                 scope_args)
    return render_template("schedule.html", papers=rows, exams=exams_rows,
                           subjects=subjects_rows, exam_label=exam_label,
                           disp_date=disp_date, fmt_num=fmt_num)


@app.route("/schedule/save", methods=["POST"])
def schedule_save():
    f = request.form
    exam_id = f.get("exam_id", "")
    subject_id = f.get("subject_id", "")
    if not exam_id or not subject_id:
        flash("Select both an exam and a subject.", "error")
        return redirect(url_for("schedule"))
    exam_id, subject_id = int(exam_id), int(subject_id)
    if visible("exams", exam_id) is None:
        flash("That exam is not available to you.", "error")
        return redirect(url_for("schedule"))
    if visible("subjects", subject_id) is None:
        flash("That subject is not available to you.", "error")
        return redirect(url_for("schedule"))

    ed = norm_date(f.get("exam_date"))
    st = norm_time(f.get("start_time"))
    duration = to_float(f.get("duration"), 0)
    mx = to_float(f.get("max_marks"), 100)
    ps = to_float(f.get("pass_marks"), 33)
    if ed is None:
        flash("Exam date must be dd/mm/yyyy.", "error")
        return redirect(url_for("schedule"))
    if st is None:
        flash("Start time must be HH:MM (24 hour).", "error")
        return redirect(url_for("schedule"))
    if duration is None or mx is None or ps is None:
        flash("Duration, max marks and pass marks must be numbers.", "error")
        return redirect(url_for("schedule"))
    if mx <= 0:
        flash("Max marks must be greater than 0.", "error")
        return redirect(url_for("schedule"))
    if ps < 0 or ps > mx:
        flash("Pass marks must be between 0 and max marks.", "error")
        return redirect(url_for("schedule"))
    if query("SELECT id FROM exam_schedule WHERE exam_id=? AND subject_id=?",
             (exam_id, subject_id), one=True):
        flash("That subject is already scheduled for this exam.", "error")
        return redirect(url_for("schedule"))

    internal_max = to_float(f.get("internal_max"), 30) or 0
    if internal_max < 0 or internal_max > mx:
        flash("Internal marks must be between 0 and the max marks.", "error")
        return redirect(url_for("schedule"))
    execute("""INSERT INTO exam_schedule (exam_id, subject_id, exam_date,
               start_time, duration, room, invigilator, max_marks, pass_marks,
               internal_max) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (exam_id, subject_id, ed, st, int(duration),
             f.get("room", "").strip(), f.get("invigilator", "").strip(),
             mx, ps, internal_max))
    flash("Paper added to the schedule.", "ok")
    return redirect(url_for("schedule"))


@app.route("/schedule/<int:pid>/delete", methods=["POST"])
def schedule_delete(pid):
    paper = query("""SELECT sc.id, e.owner_id FROM exam_schedule sc
                     JOIN exams e ON e.id = sc.exam_id WHERE sc.id=?""",
                  (pid,), one=True)
    if paper is None or (not is_admin() and paper["owner_id"] != uid()):
        flash("That paper does not belong to you.", "error")
        return redirect(url_for("schedule"))
    execute("DELETE FROM exam_schedule WHERE id=?", (pid,))
    flash("Paper removed.", "ok")
    return redirect(url_for("schedule"))


# --------------------------------------------------------------------------
#  marks
# --------------------------------------------------------------------------
def _sheet_where(exam):
    """Which students belong on the marks sheet of this exam.

    A school-wide exam (owner_id NULL) shows every student the user may see;
    a teacher's own exam shows only that teacher's students.
    """
    cls = (exam["class_name"] or "").strip()
    if exam["owner_id"] is None:
        return owned_where("status='Active' AND class_name=?", (cls,))
    return (" WHERE status='Active' AND class_name=? AND owner_id=?",
            (cls, exam["owner_id"]))
@app.route("/marks", methods=["GET", "POST"])
def marks():
    ew, ea = owned_where()
    exams_rows = query("SELECT * FROM exams" + ew + " ORDER BY id DESC", ea)
    sw, sa = owned_where()
    subjects_rows = query("SELECT * FROM subjects" + sw +
                          " ORDER BY subject_code", sa)
    exam_id = request.values.get("exam_id") or ""
    subject_id = request.values.get("subject_id") or ""

    sheet, info, ctx = [], "", None
    if exam_id and subject_id:
        exam_id, subject_id = int(exam_id), int(subject_id)
        sched = query("SELECT * FROM exam_schedule WHERE exam_id=? AND"
                      " subject_id=?", (exam_id, subject_id), one=True)
        exam = visible("exams", exam_id)
        if exam is None:
            flash("That exam does not belong to you.", "error")
            return redirect(url_for("marks"))

        if request.method == "POST" and sched:
            saved = 0
            max_marks = float(sched["max_marks"] or 100)
            for st in query("SELECT id FROM students"
                            + _sheet_where(exam)[0], _sheet_where(exam)[1]):
                raw = request.form.get(f"marks_{st['id']}", "").strip()
                th_raw = request.form.get(f"theory_{st['id']}", "").strip()
                in_raw = request.form.get(f"internal_{st['id']}", "").strip()
                remark = request.form.get(f"remarks_{st['id']}", "").strip()
                theory = internal = None
                if th_raw or in_raw:
                    theory = to_float(th_raw) if th_raw else 0.0
                    internal = to_float(in_raw) if in_raw else 0.0
                    if theory is None or internal is None:
                        continue
                    if internal > float(sched["internal_max"] or 30):
                        continue
                    value = round((theory or 0) + (internal or 0), 2)
                elif raw == "":
                    value = None
                else:
                    value = to_float(raw)
                    if value is None or value < 0 or value > max_marks:
                        continue
                if value is not None and value > max_marks:
                    continue
                existing = query("SELECT id FROM marks WHERE exam_id=? AND"
                                 " student_id=? AND subject_id=?",
                                 (exam_id, st["id"], subject_id), one=True)
                if existing:
                    execute("UPDATE marks SET marks_obtained=?, theory=?,"
                            " internal=?, remarks=?, updated_at=CURRENT_TIMESTAMP"
                            " WHERE id=?",
                            (value, theory, internal, remark, existing["id"]))
                else:
                    execute("""INSERT INTO marks (exam_id, student_id,
                               subject_id, marks_obtained, theory, internal,
                               remarks) VALUES (?,?,?,?,?,?,?)""",
                            (exam_id, st["id"], subject_id, value, theory,
                             internal, remark))
                saved += 1
            flash(f"Marks saved for {saved} student(s).", "ok")
            return redirect(url_for("marks", exam_id=exam_id,
                                    subject_id=subject_id))

        if not sched:
            info = ("That subject is not scheduled for this exam - add it in "
                    "Exam schedule first.")
        else:
            max_marks = float(sched["max_marks"] or 100)
            pass_marks = float(sched["pass_marks"] or 33)
            ctx = {"max_marks": max_marks, "pass_marks": pass_marks,
                   "internal_max": float(sched["internal_max"] or 30)}
            rows = query("SELECT * FROM students"
                         + _sheet_where(exam)[0]
                         + " ORDER BY CAST(roll_no AS INTEGER), roll_no",
                         _sheet_where(exam)[1])
            for st in rows:
                m = query("SELECT * FROM marks WHERE exam_id=? AND student_id=?"
                          " AND subject_id=?", (exam_id, st["id"], subject_id),
                          one=True)
                sheet.append({"student": st, "mark": m})
            info = (f"{len(sheet)} student(s) · max {fmt_num(max_marks)} · "
                    f"pass {fmt_num(pass_marks)}")

    return render_template("marks.html", exams=exams_rows,
                           subjects=subjects_rows, exam_id=str(exam_id),
                           subject_id=str(subject_id), sheet=sheet,
                           info=info, ctx=ctx, exam_label=exam_label,
                           fmt_num=fmt_num)


# --------------------------------------------------------------------------
#  results
# --------------------------------------------------------------------------
@app.route("/results")
def results():
    ew, ea = owned_where()
    exams_rows = query("SELECT * FROM exams" + ew + " ORDER BY id DESC", ea)
    exam_id = request.args.get("exam_id") or ""
    class_name = (request.args.get("class_name") or "").strip()
    rows, info, exam = [], "", None

    if exam_id:
        exam = visible("exams", int(exam_id))
        if exam is None:
            flash("That exam does not belong to you.", "error")
            return redirect(url_for("results"))
        class_name = class_name or (exam["class_name"] or "").strip()
        if class_name:
            rows = compute_results(int(exam_id), class_name)
            limit = request.args.get("limit", type=int) or 0
            if limit and rows:
                rows = rows[:limit]
            if rows:
                passed = sum(1 for r in rows if r["result"] == "Pass")
                info = (f"{len(rows)} student(s) · Pass {passed} · "
                        f"Fail {len(rows) - passed} · Topper: {rows[0]['name']} "
                        f"({rows[0]['percentage']:.2f}%)")
            else:
                info = "No marks found for this exam and class."

    cw, ca = owned_where("class_name<>''")
    classes = [r["class_name"] for r in query(
        "SELECT DISTINCT class_name FROM students" + cw +
        " ORDER BY class_name", ca)]
    return render_template("results.html", exams=exams_rows, results=rows,
                           exam_id=str(exam_id), class_name=class_name,
                           classes=classes, info=info, exam_label=exam_label,
                           fmt_num=fmt_num,
                           limit=request.args.get("limit", type=int) or 0,
                           total_students=len(compute_results(int(exam_id),
                                                              class_name))
                           if exam_id and class_name else 0)


@app.route("/results.csv")
def results_csv():
    exam_id = request.args.get("exam_id", type=int)
    class_name = (request.args.get("class_name") or "").strip()
    if not exam_id:
        flash("Pick an exam first.", "error")
        return redirect(url_for("results"))
    exam = visible("exams", exam_id)
    if exam is None:
        flash("That exam does not belong to you.", "error")
        return redirect(url_for("results"))
    class_name = class_name or (exam["class_name"] or "").strip()
    rows = compute_results(exam_id, class_name)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Rank", "Roll No", "Admission No", "Name", "Obtained", "Max",
                "Percentage", "Grade", "Failed Subjects", "Result"])
    for r in rows:
        w.writerow([r["rank"], r["roll_no"], r["admission_no"], r["name"],
                    fmt_num(r["obtained"]), fmt_num(r["total_max"]),
                    f"{r['percentage']:.2f}", r["grade"], r["failed_subjects"],
                    r["result"]])
    name = f"results_{class_name or 'all'}.csv".replace(" ", "_")
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":
                             f"attachment; filename={name}"})



# --------------------------------------------------------------------------
#  attendance
# --------------------------------------------------------------------------
ATT_STATUS = ("Present", "Absent", "Late", "Leave")


@app.route("/attendance", methods=["GET", "POST"])
def attendance():
    scope = class_scope()
    today = datetime.now().strftime("%Y-%m-%d")
    cls = (request.values.get("class_name") or (scope[0] if scope else "")).strip()
    sec = (request.values.get("section") or (scope[1] if scope else "")).strip()
    day = norm_date(request.values.get("att_date")) or today

    if scope and cls and cls != scope[0]:
        flash("You can only mark attendance for your own class.", "error")
        return redirect(url_for("attendance"))

    rows = []
    if cls:
        where = " WHERE status='Active' AND class_name=?"
        args = [cls]
        if sec:
            where += " AND IFNULL(section,'')=?"
            args.append(sec)
        rows = query("SELECT * FROM students" + where +
                     " ORDER BY CAST(roll_no AS INTEGER), roll_no", args)

    if request.method == "POST" and rows:
        saved = 0
        for st in rows:
            value = request.form.get(f"status_{st['id']}", "").strip()
            if value not in ATT_STATUS:
                continue
            remark = request.form.get(f"remarks_{st['id']}", "").strip()
            existing = query("SELECT id FROM attendance WHERE student_id=? AND"
                             " att_date=?", (st["id"], day), one=True)
            if existing:
                execute("UPDATE attendance SET status=?, remarks=?, marked_by=?"
                        " WHERE id=?", (value, remark, uid(), existing["id"]))
            else:
                execute("""INSERT INTO attendance (student_id, class_name,
                           section, att_date, status, remarks, marked_by)
                           VALUES (?,?,?,?,?,?,?)""",
                        (st["id"], cls, sec, day, value, remark, uid()))
            saved += 1
        flash(f"Attendance saved for {saved} student(s) on {disp_date(day)}.", "ok")
        return redirect(url_for("attendance", class_name=cls, section=sec,
                                att_date=day))

    marks = {}
    if rows:
        ids = ",".join("?" * len(rows))
        for a in query(f"SELECT * FROM attendance WHERE att_date=? AND"
                       f" student_id IN ({ids})", [day] + [r["id"] for r in rows]):
            marks[a["student_id"]] = a

    classes = sorted({r["class_name"] for r in query(
        "SELECT DISTINCT class_name FROM students WHERE class_name<>''")})
    sections = sorted({r["section"] for r in query(
        "SELECT DISTINCT section FROM students WHERE IFNULL(section,'')<>''")})
    # ---- month calendar ----
    month = (request.args.get("month") or day[:7]).strip()
    try:
        year, mon = [int(x) for x in month.split("-")]
    except Exception:                        # noqa: BLE001
        year, mon = datetime.now().year, datetime.now().month
    month = f"{year:04d}-{mon:02d}"
    day_rows = query("""SELECT att_date,
                               SUM(CASE WHEN status IN ('Present','Late')
                                        THEN 1 ELSE 0 END) p,
                               COUNT(*) n
                        FROM attendance
                        WHERE IFNULL(class_name,'')=? AND IFNULL(section,'')=?
                          AND att_date LIKE ?
                        GROUP BY att_date""",
                     (cls, sec, month + "%"))
    day_map = {r["att_date"]: (r["p"], r["n"]) for r in day_rows}
    weeks = []
    for wk in pycalendar.Calendar(firstweekday=0).monthdatescalendar(year, mon):
        week = []
        for d_ in wk:
            key = d_.strftime("%Y-%m-%d")
            p_cnt, n_cnt = day_map.get(key, (0, 0))
            if n_cnt == 0:
                state = "none"
            elif p_cnt == n_cnt:
                state = "full"
            elif p_cnt == 0:
                state = "absent"
            else:
                state = "partial"
            week.append({"day": d_, "in_month": d_.month == mon, "key": key,
                         "state": state, "p": p_cnt, "n": n_cnt})
        weeks.append(week)
    prev_m = (datetime(year, mon, 1) - timedelta(days=1)).strftime("%Y-%m")
    next_m = (datetime(year, mon, 28) + timedelta(days=7)).strftime("%Y-%m")

    return render_template("attendance.html", students=rows, marks=marks,
                           cls=cls, sec=sec, day=day, today=today,
                           classes=classes, sections=sections,
                           statuses=ATT_STATUS, scope=scope, disp_date=disp_date,
                           weeks=weeks, month=month,
                           month_label=pycalendar.month_name[mon] + " " + str(year),
                           prev_month=prev_m, next_month=next_m)


# --------------------------------------------------------------------------
#  homework
# --------------------------------------------------------------------------
@app.route("/homework", methods=["GET", "POST"])
def homework():
    scope = class_scope()
    if request.method == "POST":
        cls = (request.form.get("class_name") or "").strip()
        title = (request.form.get("title") or "").strip()
        if scope and cls != scope[0]:
            flash("You can only set homework for your own class.", "error")
            return redirect(url_for("homework"))
        if not cls or not title:
            flash("Class and title are required.", "error")
            return redirect(url_for("homework"))
        execute("""INSERT INTO homework (class_name, section, subject_id, title,
                   details, due_date, created_by) VALUES (?,?,?,?,?,?,?)""",
                (cls, (request.form.get("section") or "").strip(),
                 request.form.get("subject_id") or None, title,
                 (request.form.get("details") or "").strip(),
                 norm_date(request.form.get("due_date")), uid()))
        flash("Homework posted.", "ok")
        return redirect(url_for("homework"))

    where, args = "", []
    if scope:
        where, args = " WHERE h.class_name=?", [scope[0]]
    rows = query("""SELECT h.*, s.subject_name, u.username AS author
                    FROM homework h
                    LEFT JOIN subjects s ON s.id = h.subject_id
                    LEFT JOIN users u ON u.id = h.created_by""" + where +
                 " ORDER BY h.id DESC LIMIT 100", args)
    subjects = query("SELECT * FROM subjects ORDER BY subject_code")
    classes = sorted({r["class_name"] for r in query(
        "SELECT DISTINCT class_name FROM students WHERE class_name<>''")})
    return render_template("homework.html", homework=rows, subjects=subjects,
                           classes=classes, scope=scope, disp_date=disp_date)


@app.route("/homework/<int:hid>/delete", methods=["POST"])
def homework_delete(hid):
    row = query("SELECT * FROM homework WHERE id=?", (hid,), one=True)
    if row is None or (not is_admin() and row["created_by"] != uid()):
        flash("You can only delete homework you posted.", "error")
        return redirect(url_for("homework"))
    execute("DELETE FROM homework WHERE id=?", (hid,))
    flash("Homework removed.", "ok")
    return redirect(url_for("homework"))


# --------------------------------------------------------------------------
#  circulars / notices
# --------------------------------------------------------------------------
@app.route("/circulars", methods=["GET", "POST"])
def circulars():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        if not title:
            flash("A title is required.", "error")
            return redirect(url_for("circulars"))
        execute("""INSERT INTO circulars (title, body, audience, class_name,
                   section, pinned, posted_by) VALUES (?,?,?,?,?,?,?)""",
                (title, (request.form.get("body") or "").strip(),
                 request.form.get("audience") or "all",
                 (request.form.get("class_name") or "").strip(),
                 (request.form.get("section") or "").strip(),
                 1 if request.form.get("pinned") else 0, uid()))
        flash("Circular published.", "ok")
        return redirect(url_for("circulars"))
    rows = query("""SELECT c.*, u.username AS author FROM circulars c
                    LEFT JOIN users u ON u.id = c.posted_by
                    ORDER BY c.pinned DESC, c.id DESC LIMIT 100""")
    return render_template("circulars.html", circulars=rows, is_admin=is_admin())


@app.route("/circulars/<int:cid>/delete", methods=["POST"])
def circular_delete(cid):
    row = query("SELECT * FROM circulars WHERE id=?", (cid,), one=True)
    if row is None or (not is_admin() and row["posted_by"] != uid()):
        flash("You can only delete your own circulars.", "error")
        return redirect(url_for("circulars"))
    execute("DELETE FROM circulars WHERE id=?", (cid,))
    flash("Circular removed.", "ok")
    return redirect(url_for("circulars"))


# --------------------------------------------------------------------------
#  a student's own pages (read only)
# --------------------------------------------------------------------------
@app.route("/my-attendance")
def my_attendance():
    if not is_student():
        return redirect(url_for("dashboard"))
    student = my_student()
    if student is None:
        return redirect(url_for("my_result"))
    rows = query("SELECT * FROM attendance WHERE student_id=?"
                 " ORDER BY att_date DESC LIMIT 120", (student["id"],))
    total = len(rows)
    present = sum(1 for r in rows if r["status"] in ("Present", "Late"))
    pct = round(present / total * 100, 1) if total else 0
    # ---- the student's own month calendar ----
    month = (request.args.get("month") or datetime.now().strftime("%Y-%m")).strip()
    try:
        year, mon = [int(x) for x in month.split("-")]
    except Exception:                        # noqa: BLE001
        year, mon = datetime.now().year, datetime.now().month
    month = f"{year:04d}-{mon:02d}"
    mine = {r["att_date"]: r["status"] for r in query(
        "SELECT att_date, status FROM attendance WHERE student_id=?"
        " AND att_date LIKE ?", (student["id"], month + "%"))}
    weeks = []
    for wk in pycalendar.Calendar(firstweekday=0).monthdatescalendar(year, mon):
        week = []
        for d_ in wk:
            key = d_.strftime("%Y-%m-%d")
            status = mine.get(key)
            if status in ("Present", "Late"):
                state = "full"
            elif status == "Absent":
                state = "absent"
            elif status == "Leave":
                state = "partial"
            else:
                state = "none"
            week.append({"day": d_, "in_month": d_.month == mon, "key": key,
                         "state": state, "status": status or ""})
        weeks.append(week)
    prev_m = (datetime(year, mon, 1) - timedelta(days=1)).strftime("%Y-%m")
    next_m = (datetime(year, mon, 28) + timedelta(days=7)).strftime("%Y-%m")

    return render_template("my_attendance.html", student=student, rows=rows,
                           total=total, present=present, pct=pct,
                           disp_date=disp_date, weeks=weeks, month=month,
                           month_label=pycalendar.month_name[mon] + " " + str(year),
                           prev_month=prev_m, next_month=next_m,
                           today=datetime.now().strftime("%Y-%m-%d"))


@app.route("/my-homework")
def my_homework():
    if not is_student():
        return redirect(url_for("dashboard"))
    student = my_student()
    if student is None:
        return redirect(url_for("my_result"))
    rows = query("""SELECT h.*, s.subject_name FROM homework h
                    LEFT JOIN subjects s ON s.id = h.subject_id
                    WHERE h.class_name=?
                      AND (IFNULL(h.section,'')='' OR IFNULL(h.section,'')=?)
                    ORDER BY h.id DESC LIMIT 100""",
                 ((student["class_name"] or "").strip(),
                  (student["section"] or "").strip()))
    return render_template("my_homework.html", student=student, homework=rows,
                           disp_date=disp_date)


@app.route("/notices")
def notices():
    if is_student():
        student = my_student()
        if student is None:
            return redirect(url_for("my_result"))
        rows = query("""SELECT * FROM circulars
                        WHERE audience IN ('all','students')
                          AND (IFNULL(class_name,'')='' OR class_name=?)
                        ORDER BY pinned DESC, id DESC LIMIT 100""",
                     ((student["class_name"] or "").strip(),))
        return render_template("notices.html", circulars=rows, student=student)
    if getattr(g, "user", None) is None:
        return redirect(url_for("login"))
    return redirect(url_for("circulars"))


# --------------------------------------------------------------------------
#  change your own password
# --------------------------------------------------------------------------
@app.route("/password", methods=["GET", "POST"])
def password():
    if request.method == "POST":
        current = request.form.get("current", "")
        new = request.form.get("new", "")
        again = request.form.get("again", "")
        if not check_password_hash(g.user["password_hash"], current):
            flash("Your current password is wrong.", "error")
        elif len(new) < 6:
            flash("The new password must be at least 6 characters.", "error")
        elif new != again:
            flash("The two new passwords do not match.", "error")
        else:
            execute("UPDATE users SET password_hash=? WHERE id=?",
                    (generate_password_hash(new), uid()))
            flash("Password changed.", "ok")
            return redirect(url_for("my_result") if is_student()
                            else url_for("dashboard"))
    return render_template("password.html")


# --------------------------------------------------------------------------
#  demo data for a school trial
# --------------------------------------------------------------------------
@app.route("/demo/seed", methods=["GET", "POST"])
def demo_seed():
    """Load the demo school. GET with ?key=<admin password> also works, so it
    can be run from the address bar and reports exactly what happened."""
    if request.method == "GET":
        expected = ADMIN_PASSWORD or os.environ.get("SETUP_KEY", "")
        if not expected or request.args.get("key", "") != expected:
            return {"ok": False, "error": "wrong key"}, 403
        try:
            message = seed_demo()
            counts = {
                "students": query("SELECT COUNT(*) c FROM students", one=True)["c"],
                "users": query("SELECT COUNT(*) c FROM users", one=True)["c"],
                "marks": query("SELECT COUNT(*) c FROM marks", one=True)["c"],
                "attendance": query("SELECT COUNT(*) c FROM attendance", one=True)["c"],
            }
            return {"ok": True, "message": message, "counts": counts}
        except Exception as exc:              # noqa: BLE001
            import traceback
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:400],
                    "trace": traceback.format_exc()[-600:]}, 500

    if not is_admin():
        flash("Only an admin can load the demo data.", "error")
        return redirect(url_for("dashboard"))
    try:
        added = seed_demo()
        flash(added, "ok")
    except Exception as exc:                  # noqa: BLE001
        flash(f"Demo data failed: {type(exc).__name__}: {exc}"[:250], "error")
    return redirect(url_for("dashboard"))


# --------------------------------------------------------------------------
#  demo data: ten students, parents, attendance, homework and notices
# --------------------------------------------------------------------------
DEMO_NAMES = [
    ("Aarav Sharma", "Rajesh Sharma", "Sunita Sharma", "M"),
    ("Diya Patel", "Manoj Patel", "Kavita Patel", "F"),
    ("Kabir Rao", "Suresh Rao", "Anita Rao", "M"),
    ("Meera Nair", "Anil Nair", "Latha Nair", "F"),
    ("Rohan Gupta", "Vikas Gupta", "Rekha Gupta", "M"),
    ("Sana Khan", "Imran Khan", "Shabana Khan", "F"),
    ("Ishaan Verma", "Deepak Verma", "Pooja Verma", "M"),
    ("Ananya Singh", "Rakesh Singh", "Neha Singh", "F"),
    ("Vivaan Joshi", "Mahesh Joshi", "Seema Joshi", "M"),
    ("Tara Menon", "Suresh Menon", "Divya Menon", "F"),
]



def fill_extras(ids, subjects, exam_id):
    """Fill the other modules so no page looks empty in a demo."""
    day_names = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                 "Saturday")
    codes = list(subjects.keys())
    teachers = ("R.K. Singh", "Ranjana Sharma", "A. Verma", "S. Khan",
                "M. Joshi")

    # ---- timetable for 8-A, 8 periods a day ----
    if not query("SELECT id FROM timetable LIMIT 1", one=True):
        for d_i, day in enumerate(day_names):
            for period in range(1, 9):
                code = codes[(d_i + period) % len(codes)]
                execute("""INSERT OR IGNORE INTO timetable (class_name, section,
                           day, period, subject_id, teacher)
                           VALUES (?,?,?,?,?,?)""",
                        ("8", "A", day, period, subjects[code],
                         teachers[(d_i + period) % len(teachers)]))

    # ---- library ----
    if not query("SELECT id FROM books LIMIT 1", one=True):
        for title, author, cat, copies in (
                ("Concepts of Physics", "H.C. Verma", "Science", 5),
                ("NCERT Mathematics VIII", "NCERT", "Textbook", 10),
                ("Wings of Fire", "A.P.J. Abdul Kalam", "Biography", 3),
                ("Panchatantra", "Vishnu Sharma", "Story", 4),
                ("Oxford School Dictionary", "Oxford", "Reference", 6)):
            execute("""INSERT INTO books (title, author, category, copies)
                       VALUES (?,?,?,?)""", (title, author, cat, copies))
        book_ids = [b["id"] for b in query("SELECT id FROM books ORDER BY id")]
        for i, sid in enumerate(ids[:4]):
            execute("""INSERT INTO book_issues (book_id, student_id, issued_on,
                       due_on) VALUES (?,?,?,?)""",
                    (book_ids[i % len(book_ids)], sid, "2026-10-28",
                     "2026-11-11"))

    # ---- transport ----
    if not query("SELECT id FROM transport_routes LIMIT 1", one=True):
        for name, veh, driver, phone, stops in (
                ("Route 1 — Dwarka", "DL 1C 1234", "Ram Singh", "9876500011",
                 "Sector 12, Sector 7, School gate"),
                ("Route 2 — Janakpuri", "DL 1C 5678", "Mohan Lal", "9876500022",
                 "District Centre, Tilak Nagar")):
            execute("""INSERT INTO transport_routes (route_name, vehicle_no,
                       driver_name, driver_phone, capacity, stops)
                       VALUES (?,?,?,?,?,?)""", (name, veh, driver, phone, 40, stops))
        route_ids = [r["id"] for r in query("SELECT id FROM transport_routes"
                                            " ORDER BY id")]
        for i, sid in enumerate(ids):
            execute("""INSERT OR IGNORE INTO student_transport (student_id,
                       route_id, stop_name) VALUES (?,?,?)""",
                    (sid, route_ids[i % len(route_ids)], "Sector 12"))

    # ---- fee structure + a few payments ----
    if not query("SELECT id FROM fee_heads LIMIT 1", one=True):
        for name, amount, freq in (("Tuition fee", 3000, "Monthly"),
                                   ("Transport", 800, "Monthly"),
                                   ("Exam fee", 500, "Yearly")):
            execute("""INSERT INTO fee_heads (class_name, name, amount,
                       frequency) VALUES (?,?,?,?)""", ("8", name, amount, freq))
        for i, sid in enumerate(ids[:6]):
            execute("""INSERT INTO fee_payments (student_id, amount, paid_on,
                       mode, receipt_no) VALUES (?,?,?,?,?)""",
                    (sid, 2300 if i < 3 else 1200, "2026-10-05", "UPI",
                     f"R26{i:02d}"))

    # ---- staff ----
    if not query("SELECT id FROM staff LIMIT 1", one=True):
        for name, role, subject, phone, salary in (
                ("R.K. Singh", "Teacher", "Mathematics", "9999900001", 45000),
                ("Ranjana Sharma", "Principal", "—", "9999900002", 80000),
                ("A. Verma", "Teacher", "Science", "9999900003", 42000),
                ("S. Khan", "Teacher", "English", "9999900004", 41000),
                ("Mohan Lal", "Driver", "—", "9999900005", 22000)):
            execute("""INSERT INTO staff (name, role, subject, phone, join_date,
                       salary) VALUES (?,?,?,?,?,?)""",
                    (name, role, subject, phone, "2020-04-01", salary))

    # ---- admissions, events, polls, store ----
    if not query("SELECT id FROM events LIMIT 1", one=True):
        for title, day, kind in (("Annual Day", "2026-12-15", "Function"),
                                 ("Half Yearly exams begin", "2026-12-01", "Exam"),
                                 ("Parent-teacher meeting", "2026-11-15", "Meeting"),
                                 ("Sports day", "2026-11-28", "Sports")):
            execute("""INSERT INTO events (title, event_date, kind, created_by)
                       VALUES (?,?,?,?)""", (title, day, kind, uid()))

    # ---- a few messages in the log ----
    if not query("SELECT id FROM notifications LIMIT 1", one=True):
        for channel, audience, msg in (
                ("SMS", "parents", "Fee reminder: kindly clear the pending "
                                   "amount before 10th."),
                ("WhatsApp", "parents", "Parent-teacher meeting on 15 Nov, "
                                        "10:00 am."),
                ("Notice", "all", "Annual Day rehearsal starts from Monday.")):
            execute("""INSERT INTO notifications (channel, audience, message,
                       by_user) VALUES (?,?,?,?)""",
                    (channel, audience, msg, uid()))

    # ---- leave applications (one pending, one approved) ----
    if not query("SELECT id FROM leave_requests LIMIT 1", one=True):
        for sid, frm, to, reason, status in (
                (ids[0], "2026-11-12", "2026-11-13", "Family function", "Pending"),
                (ids[1], "2026-10-20", "2026-10-21", "Fever", "Approved")):
            execute("""INSERT INTO leave_requests (student_id, from_date,
                       to_date, reason, status) VALUES (?,?,?,?,?)""",
                    (sid, frm, to, reason, status))





def seed_demo():
    """Create a ready-to-show school: 10 students with parents and history."""
    if query("SELECT id FROM students WHERE admission_no='DEMO01'", one=True):
        # the school data is there; make sure the student logins exist too
        made = []
        for adm, username in (("DEMO01", "aarav"), ("DEMO02", "diya"),
                              ("DEMO03", "kabir")):
            row = query("SELECT id, name FROM students WHERE admission_no=?",
                        (adm,), one=True)
            if row and not query("SELECT id FROM users WHERE username=?",
                                 (username,), one=True):
                execute("""INSERT INTO users (username, full_name,
                           password_hash, role, student_id)
                           VALUES (?,?,?,?,?)""",
                        (username, row["name"],
                         generate_password_hash("student1234"), "student",
                         row["id"]))
                made.append(username)
        if made:
            return ("Student logins created: " + ", ".join(made) +
                    " (password student1234).")
        return ("Demo data is already loaded (10 students of class 8-A, and "
                "the logins aarav / diya / kabir exist).")

    subjects = {}
    for code, name, mx, ps in (("ENG", "English", 50, 17),
                               ("HIN", "Hindi", 50, 17),
                               ("MAT", "Mathematics", 100, 33),
                               ("SCI", "Science", 80, 26),
                               ("SST", "Social Science", 80, 26)):
        row = query("SELECT id FROM subjects WHERE subject_code=?", (code,),
                    one=True)
        if row:
            subjects[code] = row["id"]
        else:
            subjects[code] = execute(
                "INSERT INTO subjects (owner_id, subject_code, subject_name,"
                " class_name) VALUES (NULL,?,?,?)", (code, name, "8"))

    # ---- students ----
    ids = []
    for i, (name, father, mother, gender) in enumerate(DEMO_NAMES, start=1):
        sid = execute("""INSERT INTO students (owner_id, admission_no, roll_no,
                       name, class_name, section, dob, gender, father_name,
                       mother_name, phone, email, address, admission_date,
                       status) VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (f"DEMO{i:02d}", str(i), name, "8", "A",
                       f"{2012 - (i % 3)}-0{(i % 9) + 1}-1{i % 9}",
                       "Male" if gender == "M" else "Female",
                       father, mother, f"98{i:08d}",
                       f"{name.split()[0].lower()}.parent@example.com",
                       f"{i}, Green Park, New Delhi", "2026-04-01", "Active"))
        ids.append(sid)

    # ---- one exam with marks ----
    exam_id = query("SELECT id FROM exams WHERE exam_type='Mid Term' AND"
                    " class_name='8'", one=True)
    if exam_id:
        exam_id = exam_id["id"]
    else:
        exam_id = execute("""INSERT INTO exams (owner_id, exam_name, exam_type,
                            academic_year, class_name, start_date, end_date,
                            status) VALUES (NULL,?,?,?,?,?,?,?)""",
                          ("Mid Term", "Mid Term", "2026-27", "8",
                           "2026-11-10", "2026-11-18", "Completed"))
    for code, mx, ps in (("ENG", 50, 17), ("HIN", 50, 17), ("MAT", 100, 33),
                         ("SCI", 80, 26), ("SST", 80, 26)):
        if not query("SELECT id FROM exam_schedule WHERE exam_id=? AND"
                     " subject_id=?", (exam_id, subjects[code]), one=True):
            execute("""INSERT INTO exam_schedule (exam_id, subject_id, exam_date,
                       start_time, duration, max_marks, pass_marks)
                       VALUES (?,?,?,?,?,?,?)""",
                    (exam_id, subjects[code], "2026-11-10", "09:00", 180, mx, ps))

    base = {"ENG": 0.86, "HIN": 0.78, "MAT": 0.72, "SCI": 0.80, "SST": 0.75}
    for idx, sid in enumerate(ids):
        for code, mx, _ps in (("ENG", 50, 17), ("HIN", 50, 17), ("MAT", 100, 33),
                              ("SCI", 80, 26), ("SST", 80, 26)):
            factor = base[code] - idx * 0.035
            got = max(12, round(mx * factor))
            execute("""INSERT INTO marks (exam_id, student_id, subject_id,
                       marks_obtained, remarks) VALUES (?,?,?,?,?)""",
                    (exam_id, sid, subjects[code], got, ""))

    # ---- attendance for the last ten days ----
    day = datetime.now()
    made = 0
    for back in range(10):
        d = day - timedelta(days=back)
        if d.weekday() == 6:                       # Sunday
            continue
        stamp = d.strftime("%Y-%m-%d")
        for idx, sid in enumerate(ids):
            if (idx + back) % 9 == 0:
                status = "Absent"
            elif (idx + back) % 11 == 0:
                status = "Late"
            else:
                status = "Present"
            execute("""INSERT OR IGNORE INTO attendance (student_id, class_name,
                       section, att_date, status, marked_by)
                       VALUES (?,?,?,?,?,?)""",
                    (sid, "8", "A", stamp, status, uid()))
            made += 1

    # ---- homework and circulars ----
    for code, title, details, due in (
            ("MAT", "Exercise 8.2 — question 1 to 10",
             "Show all steps. Write in the maths register.", "2026-11-05"),
            ("SCI", "Chapter 6 — Combustion and Flame",
             "Read the chapter and answer the back exercises.", "2026-11-06"),
            ("ENG", "Letter to the editor",
             "150 words on water wastage in your locality.", "2026-11-07"),
            ("SST", "Map work — physical divisions of India",
             "Mark the ranges and plateaus on the outline map.", "2026-11-08")):
        execute("""INSERT INTO homework (class_name, section, subject_id, title,
                   details, due_date, created_by) VALUES (?,?,?,?,?,?,?)""",
                ("8", "A", subjects[code], title, details, due, uid()))

    for title, body, pinned in (
            ("Parent-teacher meeting",
             "The PTM for class 8 will be held on Saturday, 15 November 2026, "
             "from 9:00 am to 12:30 pm in the respective classrooms. "
             "Parents are requested to attend with the report card.", 1),
            ("Annual sports day",
             "Trials for the annual sports day begin next week during the games "
             "period. Bring your house T-shirt and sports shoes.", 0),
            ("Winter uniform",
             "Winter uniform is compulsory from 1 December. Navy blazer and "
             "grey trousers / skirt as per the school diary.", 0)):
        execute("""INSERT INTO circulars (title, body, audience, pinned,
                   posted_by) VALUES (?,?,?,?,?)""",
                (title, body, "all", pinned, uid()))

    # ---- timetable, hostel, library, transport, fees, staff, events ----
    fill_extras(ids, subjects, exam_id)

    # ---- three student logins so the portal can be tried immediately ----
    for sid, username in zip(ids[:3], ("aarav", "diya", "kabir")):
        if not query("SELECT id FROM users WHERE username=?", (username,),
                     one=True):
            execute("""INSERT INTO users (username, full_name, password_hash,
                       role, student_id) VALUES (?,?,?,?,?)""",
                    (username, query("SELECT name FROM students WHERE id=?",
                                     (sid,), one=True)["name"],
                     generate_password_hash("student1234"), "student", sid))

    # ---- two teachers, one of them the class teacher of 8-A ----
    for username, full, cls, sec in (("teacher1", "Rakesh Kr. Singh", "8", "A"),
                                     ("teacher2", "Ranjana Sharma", "8", "B")):
        if not query("SELECT id FROM users WHERE username=?", (username,),
                     one=True):
            execute("""INSERT INTO users (username, full_name, password_hash,
                       role, class_name, section) VALUES (?,?,?,?,?,?)""",
                    (username, full, generate_password_hash("school1234"),
                     "user", cls, sec))

    return (f"Demo school created: 10 students of class 8-A with parents, "
            f"{made} attendance rows, one exam with marks, 4 homework entries, "
            f"3 circulars, 2 teacher accounts (teacher1 / teacher2, password "
            f"school1234) and 3 student logins (aarav / diya / kabir, "
            f"password student1234).")


# --------------------------------------------------------------------------
#  fees
# --------------------------------------------------------------------------
FEE_MODES = ("Cash", "UPI", "Cheque", "Card", "Bank transfer")
PERIODS = list(range(1, 9))
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")


def fee_summary(class_name=""):
    """One row per student: what is due, what is paid, what is left."""
    where, args = " WHERE status='Active'", []
    if class_name:
        where += " AND class_name=?"
        args.append(class_name)
    students = query("SELECT * FROM students" + where +
                     " ORDER BY class_name, CAST(roll_no AS INTEGER), roll_no",
                     args)
    heads = query("SELECT * FROM fee_heads")
    by_class = {}
    for h in heads:
        by_class.setdefault((h["class_name"] or "").strip(), []).append(h)
    paid = {}
    for row in query("SELECT student_id, SUM(amount) s FROM fee_payments"
                     " GROUP BY student_id"):
        paid[row["student_id"]] = row["s"] or 0
    out = []
    for st in students:
        own = by_class.get((st["class_name"] or "").strip(), [])
        total = sum(float(h["amount"] or 0) for h in own)
        got = float(paid.get(st["id"], 0) or 0)
        out.append({"student": st, "total": round(total, 2),
                    "paid": round(got, 2), "due": round(total - got, 2)})
    return out


@app.route("/fees", methods=["GET", "POST"])
def fees():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "head":
            if not is_admin():
                flash("Only an admin can change the fee structure.", "error")
                return redirect(url_for("fees"))
            name = (request.form.get("name") or "").strip()
            if not name:
                flash("Fee head needs a name.", "error")
                return redirect(url_for("fees"))
            execute("""INSERT INTO fee_heads (class_name, name, amount, frequency)
                       VALUES (?,?,?,?)""",
                    ((request.form.get("class_name") or "").strip(), name,
                     to_float(request.form.get("amount"), 0) or 0,
                     request.form.get("frequency") or "Monthly"))
            flash("Fee head added.", "ok")
        elif action == "pay":
            sid = request.form.get("student_id", type=int)
            amount = to_float(request.form.get("amount"), None)
            if not sid or amount is None or amount <= 0:
                flash("Pick a student and a valid amount.", "error")
                return redirect(url_for("fees"))
            paid_on = norm_date(request.form.get("paid_on")) or \
                datetime.now().strftime("%Y-%m-%d")
            receipt = "R" + datetime.now().strftime("%y%m%d%H%M%S") + str(sid)
            execute("""INSERT INTO fee_payments (student_id, head_id, amount,
                       paid_on, mode, receipt_no, remarks, recorded_by)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (sid, request.form.get("head_id") or None, amount, paid_on,
                     request.form.get("mode") or "Cash", receipt,
                     (request.form.get("remarks") or "").strip(), uid()))
            flash(f"Payment of {fmt_num(amount)} recorded. Receipt {receipt}.", "ok")
            return redirect(url_for("fees_receipt", pid=query(
                "SELECT id FROM fee_payments WHERE receipt_no=?", (receipt,),
                one=True)["id"]))
        return redirect(url_for("fees", class_name=request.form.get("class_name")))

    cls = (request.args.get("class_name") or "").strip()
    rows = fee_summary(cls)
    classes = sorted({r["class_name"] for r in query(
        "SELECT DISTINCT class_name FROM students WHERE class_name<>''")})
    heads = query("SELECT * FROM fee_heads ORDER BY class_name, name")
    return render_template("fees.html", rows=rows, cls=cls, classes=classes,
                           heads=heads, modes=FEE_MODES, fmt_num=fmt_num,
                           today=datetime.now().strftime("%Y-%m-%d"))


@app.route("/fees/receipt/<int:pid>")
def fees_receipt(pid):
    row = query("""SELECT p.*, s.name, s.class_name, s.section, s.roll_no,
                          s.admission_no, h.name AS head_name
                   FROM fee_payments p
                   JOIN students s ON s.id = p.student_id
                   LEFT JOIN fee_heads h ON h.id = p.head_id
                   WHERE p.id=?""", (pid,), one=True)
    if row is None:
        abort(404)
    return render_template("receipt.html", p=row, fmt_num=fmt_num,
                           disp_date=disp_date)


@app.route("/fees/<int:pid>/delete", methods=["POST"])
def fee_delete(pid):
    if not is_admin():
        flash("Only an admin can delete a payment.", "error")
        return redirect(url_for("fees"))
    execute("DELETE FROM fee_payments WHERE id=?", (pid,))
    flash("Payment removed.", "ok")
    return redirect(url_for("fees"))


@app.route("/my-fees")
def my_fees():
    if not is_student():
        return redirect(url_for("fees"))
    student = my_student()
    if student is None:
        return redirect(url_for("my_result"))
    heads = query("SELECT * FROM fee_heads WHERE IFNULL(class_name,'')=?"
                  " ORDER BY name", ((student["class_name"] or "").strip(),))
    total = sum(float(h["amount"] or 0) for h in heads)
    payments = query("""SELECT p.*, h.name AS head_name FROM fee_payments p
                        LEFT JOIN fee_heads h ON h.id = p.head_id
                        WHERE p.student_id=? ORDER BY p.paid_on DESC, p.id DESC""",
                     (student["id"],))
    paid = sum(float(p["amount"] or 0) for p in payments)
    return render_template("my_fees.html", student=student, heads=heads,
                           payments=payments, total=total, paid=paid,
                           due=total - paid, fmt_num=fmt_num,
                           disp_date=disp_date)


# --------------------------------------------------------------------------
#  timetable
# --------------------------------------------------------------------------
@app.route("/timetable", methods=["GET", "POST"])
def timetable():
    scope = class_scope()
    if request.method == "POST":
        cls = (request.form.get("class_name") or "").strip()
        if scope and cls != scope[0]:
            flash("You can only edit your own class timetable.", "error")
            return redirect(url_for("timetable"))
        day = request.form.get("day")
        period = request.form.get("period", type=int)
        subject_id = request.form.get("subject_id") or None
        teacher = (request.form.get("teacher") or "").strip()
        room = (request.form.get("room") or "").strip()
        if not cls or day not in DAYS or not period:
            flash("Class, day and period are required.", "error")
            return redirect(url_for("timetable"))
        sec = (request.form.get("section") or "").strip()
        existing = query("""SELECT id FROM timetable WHERE class_name=?
                            AND IFNULL(section,'')=? AND day=? AND period=?""",
                         (cls, sec, day, period), one=True)
        if subject_id or teacher or room:
            if existing:
                execute("""UPDATE timetable SET subject_id=?, teacher=?, room=?
                           WHERE id=?""", (subject_id, teacher, room,
                                           existing["id"]))
            else:
                execute("""INSERT INTO timetable (class_name, section, day,
                           period, subject_id, teacher, room)
                           VALUES (?,?,?,?,?,?,?)""",
                        (cls, sec, day, period, subject_id, teacher, room))
            flash("Timetable updated.", "ok")
        elif existing:
            execute("DELETE FROM timetable WHERE id=?", (existing["id"],))
            flash("Period cleared.", "ok")
        return redirect(url_for("timetable", class_name=cls, section=sec))

    cls = (request.args.get("class_name") or (scope[0] if scope else "")).strip()
    sec = (request.args.get("section") or (scope[1] if scope else "")).strip()
    cells = {}
    if cls:
        for row in query("""SELECT t.*, s.subject_name, s.subject_code
                            FROM timetable t
                            LEFT JOIN subjects s ON s.id = t.subject_id
                            WHERE t.class_name=? AND IFNULL(t.section,'')=?""",
                         (cls, sec)):
            cells[(row["day"], row["period"])] = row
    classes = sorted({r["class_name"] for r in query(
        "SELECT DISTINCT class_name FROM students WHERE class_name<>''")})
    sections = sorted({r["section"] for r in query(
        "SELECT DISTINCT section FROM students WHERE IFNULL(section,'')<>''")})
    subjects = query("SELECT * FROM subjects ORDER BY subject_code")
    return render_template("timetable.html", cells=cells, cls=cls, sec=sec,
                           days=DAYS, periods=PERIODS, classes=classes,
                           sections=sections, subjects=subjects, scope=scope)


@app.route("/my-timetable")
def my_timetable():
    if not is_student():
        return redirect(url_for("timetable"))
    student = my_student()
    if student is None:
        return redirect(url_for("my_result"))
    cells = {}
    for row in query("""SELECT t.*, s.subject_name, s.subject_code
                        FROM timetable t
                        LEFT JOIN subjects s ON s.id = t.subject_id
                        WHERE t.class_name=? AND IFNULL(t.section,'')=?""",
                     ((student["class_name"] or "").strip(),
                      (student["section"] or "").strip())):
        cells[(row["day"], row["period"])] = row
    return render_template("my_timetable.html", student=student, cells=cells,
                           days=DAYS, periods=PERIODS)


# --------------------------------------------------------------------------
#  printable report card
# --------------------------------------------------------------------------
@app.route("/report-card")
def report_card():
    exam_id = request.args.get("exam_id", type=int)
    student_id = request.args.get("student_id", type=int)
    if not exam_id or not student_id:
        flash("Pick an exam and a student.", "error")
        return redirect(url_for("results"))
    exam = visible("exams", exam_id)
    student = query("SELECT * FROM students WHERE id=?", (student_id,), one=True)
    if exam is None or student is None:
        flash("That exam or student is not available.", "error")
        return redirect(url_for("results"))
    rows = compute_results(exam_id, (exam["class_name"] or "").strip())
    mine = next((r for r in rows if r["student_id"] == student_id), None)
    subjects = query("""SELECT s.subject_name, s.subject_code, sc.max_marks,
                               sc.pass_marks, m.marks_obtained, m.theory,
                               m.internal, m.subject_id
                        FROM marks m
                        JOIN subjects s ON s.id = m.subject_id
                        LEFT JOIN exam_schedule sc ON sc.exam_id = m.exam_id
                               AND sc.subject_id = m.subject_id
                        WHERE m.exam_id=? AND m.student_id=?
                        ORDER BY s.subject_code""", (exam_id, student_id))
    if is_student():
        me = my_student()
        if me is None or me["id"] != student_id:
            flash("You can only open your own report card.", "error")
            return redirect(url_for("my_result"))

    if mine is None:
        flash("No marks for this student in that exam.", "error")
        return redirect(url_for("results"))

    # class average and highest per subject, for comparison
    stats = {}
    for row in query("""SELECT m.subject_id,
                               ROUND(AVG(m.marks_obtained), 1) avg_mark,
                               MAX(m.marks_obtained) top_mark
                        FROM marks m
                        JOIN students st ON st.id = m.student_id
                        WHERE m.exam_id=? AND st.class_name=?
                          AND m.marks_obtained IS NOT NULL
                        GROUP BY m.subject_id""",
                     (exam_id, (exam["class_name"] or "").strip())):
        stats[row["subject_id"]] = row
    subjects = [dict(row) for row in subjects]
    for sub in subjects:
        st = stats.get(sub["subject_id"])
        sub["avg"] = st["avg_mark"] if st else None
        sub["top"] = st["top_mark"] if st else None

    att = query("""SELECT SUM(CASE WHEN status IN ('Present','Late') THEN 1 ELSE 0 END) p,
                          COUNT(*) n FROM attendance WHERE student_id=?""",
                (student_id,), one=True)
    att_total = att["n"] if att else 0
    att_present = att["p"] if att else 0
    att_pct = round(att_present / att_total * 100) if att_total else 0

    def band(value, top=90, good=75, ok=60):
        return "A" if value >= top else "B" if value >= good else \
               "C" if value >= ok else "D"

    pct = float(mine["percentage"] or 0)
    co_areas = [
        ("Discipline", band(att_pct, 85, 70, 50)),
        ("Nature &amp; environment", band(pct, 75, 60, 45)),
        ("Co-curricular activities", band(pct + 5, 80, 65, 50)),
        ("Sports &amp; games", band((pct + att_pct) / 2, 80, 65, 50)),
        ("Art &amp; craft / music", band(pct - 8, 70, 55, 40)),
        ("General conduct", band(att_pct, 90, 75, 60)),
    ]
    ct = class_teacher_of(exam["class_name"] or "", student["section"] or "")
    teacher_sign = (ct["signature"] or "") if ct else ""
    return render_template("report_card.html", exam=exam, student=student,
                           mine=mine, subjects=subjects, exam_label=exam_label,
                           fmt_num=fmt_num, disp_date=disp_date,
                           logo=school_logo(),
                           school=setting("school_name", SCHOOL_NAME),
                           att_total=att_total, att_present=att_present,
                           att_pct=att_pct, co_areas=co_areas,
                           principal_sign=setting("principal_sign", ""),
                           teacher_sign=teacher_sign,
                           auto_print=not is_student(),
                           issued_on=datetime.now().strftime("%d/%m/%Y"))



# --------------------------------------------------------------------------
#  transport
# --------------------------------------------------------------------------
@app.route("/transport", methods=["GET", "POST"])
def transport():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "route":
            name = (request.form.get("route_name") or "").strip()
            if not name:
                flash("Route name is required.", "error")
                return redirect(url_for("transport"))
            execute("""INSERT INTO transport_routes (route_name, vehicle_no,
                       driver_name, driver_phone, capacity, stops)
                       VALUES (?,?,?,?,?,?)""",
                    (name, (request.form.get("vehicle_no") or "").strip(),
                     (request.form.get("driver_name") or "").strip(),
                     (request.form.get("driver_phone") or "").strip(),
                     request.form.get("capacity", type=int) or 40,
                     (request.form.get("stops") or "").strip()))
            flash("Route added.", "ok")
        elif action == "assign":
            sid = request.form.get("student_id", type=int)
            route_id = request.form.get("route_id", type=int)
            if not sid or not route_id:
                flash("Pick a student and a route.", "error")
                return redirect(url_for("transport"))
            execute("DELETE FROM student_transport WHERE student_id=?", (sid,))
            execute("""INSERT INTO student_transport (student_id, route_id,
                       stop_name) VALUES (?,?,?)""",
                    (sid, route_id, (request.form.get("stop_name") or "").strip()))
            flash("Student assigned to the route.", "ok")
        elif action == "unassign":
            execute("DELETE FROM student_transport WHERE student_id=?",
                    (request.form.get("student_id", type=int),))
            flash("Removed from transport.", "ok")
        return redirect(url_for("transport"))

    routes = query("""SELECT r.*,
                        (SELECT COUNT(*) FROM student_transport t
                         WHERE t.route_id=r.id) AS taken
                      FROM transport_routes r ORDER BY r.route_name""")
    assigned = query("""SELECT t.*, s.name, s.class_name, s.section, s.roll_no,
                               r.route_name
                        FROM student_transport t
                        JOIN students s ON s.id = t.student_id
                        LEFT JOIN transport_routes r ON r.id = t.route_id
                        ORDER BY r.route_name, s.class_name,
                                 CAST(s.roll_no AS INTEGER)""")
    students = query("""SELECT id, name, class_name, section, roll_no
                        FROM students WHERE status='Active'
                        ORDER BY class_name, CAST(roll_no AS INTEGER)""")
    return render_template("transport.html", routes=routes, assigned=assigned,
                           students=students)


@app.route("/my-transport")
def my_transport():
    if not is_student():
        return redirect(url_for("transport"))
    student = my_student()
    if student is None:
        return redirect(url_for("my_result"))
    row = query("""SELECT t.*, r.route_name, r.vehicle_no, r.driver_name,
                          r.driver_phone, r.stops
                   FROM student_transport t
                   LEFT JOIN transport_routes r ON r.id = t.route_id
                   WHERE t.student_id=?""", (student["id"],), one=True)
    return render_template("my_transport.html", student=student, t=row)


# --------------------------------------------------------------------------
#  library
# --------------------------------------------------------------------------
@app.route("/library", methods=["GET", "POST"])
def library():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "book":
            title = (request.form.get("title") or "").strip()
            if not title:
                flash("Book title is required.", "error")
                return redirect(url_for("library"))
            execute("""INSERT INTO books (title, author, isbn, category, copies)
                       VALUES (?,?,?,?,?)""",
                    (title, (request.form.get("author") or "").strip(),
                     (request.form.get("isbn") or "").strip(),
                     (request.form.get("category") or "").strip(),
                     request.form.get("copies", type=int) or 1))
            flash("Book added.", "ok")
        elif action == "issue":
            book_id = request.form.get("book_id", type=int)
            sid = request.form.get("student_id", type=int)
            if not book_id or not sid:
                flash("Pick a book and a student.", "error")
                return redirect(url_for("library"))
            out = query("SELECT COUNT(*) c FROM book_issues WHERE book_id=?"
                        " AND returned_on IS NULL", (book_id,), one=True)["c"]
            copies = query("SELECT copies FROM books WHERE id=?", (book_id,),
                           one=True)["copies"] or 1
            if out >= copies:
                flash("All copies of that book are already issued.", "error")
                return redirect(url_for("library"))
            issued = datetime.now().strftime("%Y-%m-%d")
            due = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
            execute("""INSERT INTO book_issues (book_id, student_id, issued_on,
                       due_on) VALUES (?,?,?,?)""", (book_id, sid, issued, due))
            flash("Book issued.", "ok")
        return redirect(url_for("library"))

    books = query("""SELECT b.*,
                       (SELECT COUNT(*) FROM book_issues i
                        WHERE i.book_id=b.id AND i.returned_on IS NULL) AS out
                     FROM books b ORDER BY b.title""")
    issues = query("""SELECT i.*, b.title, s.name, s.class_name, s.section
                      FROM book_issues i
                      JOIN books b ON b.id = i.book_id
                      JOIN students s ON s.id = i.student_id
                      ORDER BY i.returned_on IS NULL DESC, i.id DESC LIMIT 100""")
    students = query("""SELECT id, name, class_name, section, roll_no
                        FROM students WHERE status='Active'
                        ORDER BY class_name, CAST(roll_no AS INTEGER)""")
    today = datetime.now().strftime("%Y-%m-%d")
    return render_template("library.html", books=books, issues=issues,
                           students=students, today=today, disp_date=disp_date)


@app.route("/library/<int:iid>/return", methods=["POST"])
def library_return(iid):
    row = query("SELECT * FROM book_issues WHERE id=?", (iid,), one=True)
    if row is None or row["returned_on"]:
        flash("That issue is not open.", "error")
        return redirect(url_for("library"))
    today = datetime.now().strftime("%Y-%m-%d")
    fine = 0.0
    if row["due_on"] and today > row["due_on"]:
        days = (datetime.strptime(today, "%Y-%m-%d")
                - datetime.strptime(row["due_on"], "%Y-%m-%d")).days
        fine = round(days * 2.0, 2)          # 2 per late day
    execute("UPDATE book_issues SET returned_on=?, fine=? WHERE id=?",
            (today, fine, iid))
    flash(f"Book returned.{' Fine ' + fmt_num(fine) if fine else ''}", "ok")
    return redirect(url_for("library"))


@app.route("/my-library")
def my_library():
    if not is_student():
        return redirect(url_for("library"))
    student = my_student()
    if student is None:
        return redirect(url_for("my_result"))
    rows = query("""SELECT i.*, b.title, b.author FROM book_issues i
                    JOIN books b ON b.id = i.book_id
                    WHERE i.student_id=? ORDER BY i.id DESC""",
                 (student["id"],))
    today = datetime.now().strftime("%Y-%m-%d")
    return render_template("my_library.html", student=student, rows=rows,
                           today=today, disp_date=disp_date)


# --------------------------------------------------------------------------
#  staff
# --------------------------------------------------------------------------
@app.route("/staff", methods=["GET", "POST"])
def staff():
    if is_student():
        flash("Students cannot open the staff register.", "error")
        return redirect(url_for("my_home"))
    if request.method == "POST":
        if not is_admin():
            flash("Only an admin can add staff.", "error")
            return redirect(url_for("staff"))
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Staff name is required.", "error")
            return redirect(url_for("staff"))
        execute("""INSERT INTO staff (name, role, subject, phone, email,
                   join_date, salary) VALUES (?,?,?,?,?,?,?)""",
                (name, (request.form.get("role") or "").strip(),
                 (request.form.get("subject") or "").strip(),
                 (request.form.get("phone") or "").strip(),
                 (request.form.get("email") or "").strip(),
                 norm_date(request.form.get("join_date")),
                 to_float(request.form.get("salary"), 0) or 0))
        flash("Staff member added.", "ok")
        return redirect(url_for("staff"))
    rows = query("SELECT * FROM staff ORDER BY active DESC, name")
    return render_template("staff.html", staff=rows, disp_date=disp_date,
                           fmt_num=fmt_num)


@app.route("/staff/<int:sid>/toggle", methods=["POST"])
def staff_toggle(sid):
    if not is_admin():
        flash("Only an admin can change staff records.", "error")
        return redirect(url_for("staff"))
    row = query("SELECT active FROM staff WHERE id=?", (sid,), one=True)
    if row:
        execute("UPDATE staff SET active=? WHERE id=?",
                (0 if row["active"] else 1, sid))
    return redirect(url_for("staff"))


# --------------------------------------------------------------------------
#  events / calendar
# --------------------------------------------------------------------------
EVENT_KINDS = ("Event", "Holiday", "Exam", "Meeting", "Function", "Sports")


@app.route("/events", methods=["GET", "POST"])
def events():
    if request.method == "POST":
        if is_student():
            flash("Students can only view the calendar.", "error")
            return redirect(url_for("events"))
        title = (request.form.get("title") or "").strip()
        if not title:
            flash("Event title is required.", "error")
            return redirect(url_for("events"))
        execute("""INSERT INTO events (title, details, event_date, kind,
                   created_by) VALUES (?,?,?,?,?)""",
                (title, (request.form.get("details") or "").strip(),
                 norm_date(request.form.get("event_date")),
                 request.form.get("kind") or "Event", uid()))
        flash("Event added.", "ok")
        return redirect(url_for("events"))
    rows = query("SELECT * FROM events ORDER BY event_date IS NULL,"
                 " event_date, id")
    return render_template("events.html", events=rows, kinds=EVENT_KINDS,
                           disp_date=disp_date)


@app.route("/events/<int:eid>/delete", methods=["POST"])
def event_delete(eid):
    row = query("SELECT * FROM events WHERE id=?", (eid,), one=True)
    if row is None or (not is_admin() and row["created_by"] != uid()):
        flash("You can only delete events you added.", "error")
        return redirect(url_for("events"))
    execute("DELETE FROM events WHERE id=?", (eid,))
    flash("Event removed.", "ok")
    return redirect(url_for("events"))




# --------------------------------------------------------------------------
#  SMS gateway (MSG91 or Twilio) - used only when the keys are configured
# --------------------------------------------------------------------------
SMS_PROVIDER = os.environ.get("SMS_PROVIDER", "").strip().lower()
SMS_KEY = os.environ.get("SMS_KEY", "").strip()
SMS_SENDER = os.environ.get("SMS_SENDER", "SCHOOL").strip()
SMS_AUTH_TOKEN = os.environ.get("SMS_AUTH_TOKEN", "").strip()
SMS_SID = os.environ.get("SMS_SID", "").strip()
DEVICE_TOKEN = os.environ.get("DEVICE_TOKEN", "").strip()


def sms_configured():
    if SMS_PROVIDER == "msg91":
        return bool(SMS_KEY)
    if SMS_PROVIDER == "twilio":
        return bool(SMS_SID and SMS_AUTH_TOKEN and SMS_KEY)
    return False


def send_sms(number, message):
    """Returns (ok, detail). Never raises - a school must not lose data
    because a gateway is down."""
    number = (number or "").strip()
    if not number:
        return False, "no number"
    if not sms_configured():
        return False, "gateway not configured"
    try:
        if SMS_PROVIDER == "msg91":
            url = "https://api.msg91.com/api/v2/sendsms"
            payload = json.dumps({
                "sender": SMS_SENDER, "route": "4", "country": "91",
                "sms": [{"message": message, "to": [number]}]}).encode()
            request = urllib.request.Request(
                url, data=payload, headers={"authkey": SMS_KEY,
                                            "Content-Type": "application/json"})
        else:
            sid = SMS_SID
            url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
            body = urllib.parse.urlencode({
                "From": SMS_KEY, "To": number, "Body": message}).encode()
            token = base64.b64encode(
                f"{sid}:{SMS_AUTH_TOKEN}".encode()).decode()
            request = urllib.request.Request(
                url, data=body, headers={"Authorization": "Basic " + token,
                                         "Content-Type":
                                         "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(request, timeout=20) as response:
            return True, f"sent ({response.status})"
    except Exception as exc:                 # noqa: BLE001
        return False, str(exc)[:120]


# --------------------------------------------------------------------------
#  biometric / device punch
# --------------------------------------------------------------------------
@app.route("/api/punch", methods=["POST"])
def api_punch():
    """A machine (or a script) marks a student present.

    POST /api/punch  {"admission_no": "ADM101", "device": "gate-1"}
    Header: X-Device-Token: <DEVICE_TOKEN>
    """
    if DEVICE_TOKEN and request.headers.get("X-Device-Token") != DEVICE_TOKEN:
        return {"ok": False, "error": "bad device token"}, 401
    data = request.get_json(silent=True) or {}
    adm = str(data.get("admission_no") or "").strip()
    student = query("SELECT * FROM students WHERE admission_no=?", (adm,),
                    one=True)
    if student is None:
        return {"ok": False, "error": "unknown admission number"}, 404
    day = datetime.now().strftime("%Y-%m-%d")
    existing = query("SELECT id FROM attendance WHERE student_id=? AND"
                     " att_date=?", (student["id"], day), one=True)
    if existing:
        execute("UPDATE attendance SET status='Present', remarks=? WHERE id=?",
                (f"device:{data.get('device', 'gate')}", existing["id"]))
    else:
        execute("""INSERT INTO attendance (student_id, class_name, section,
                   att_date, status, remarks) VALUES (?,?,?,?,?,?)""",
                (student["id"], student["class_name"], student["section"], day,
                 "Present", f"device:{data.get('device', 'gate')}"))
    return {"ok": True, "student": student["name"], "date": day}


@app.route("/manifest.webmanifest")
def manifest():
    """Lets a phone install the site on its home screen."""
    try:
        nm = setting("app_name", APP_NAME)
        school = setting("school_name", SCHOOL_NAME)
    except Exception:                        # noqa: BLE001
        nm, school = APP_NAME, SCHOOL_NAME
    return Response(json.dumps({
        "name": f"{nm} · {school}", "short_name": nm[:12],
        "start_url": "/", "display": "standalone",
        "background_color": "#f4f6fb", "theme_color": "#1f3a5f",
        "icons": [{"src": "/static/icon.png", "sizes": "192x192",
                   "type": "image/png"}]}), mimetype="application/manifest+json")


# --------------------------------------------------------------------------
#  photo upload
# --------------------------------------------------------------------------
@app.route("/students/<int:sid>/photo", methods=["POST"])
def student_photo(sid):
    if owns("students", sid) is None:
        flash("You can only change your own students.", "error")
        return redirect(url_for("students"))
    data = save_photo(request.files.get("photo"))
    if data is None:
        flash("Choose a small image (JPG or PNG, under 1 MB).", "error")
    else:
        execute("UPDATE students SET photo=? WHERE id=?", (data, sid))
        flash("Photo saved.", "ok")
    return redirect(url_for("students", edit=sid))


@app.route("/staff/<int:sid>/photo", methods=["POST"])
def staff_photo(sid):
    if not is_admin():
        flash("Only an admin can change staff photos.", "error")
        return redirect(url_for("staff"))
    data = save_photo(request.files.get("photo"))
    if data is None:
        flash("Choose a small image (JPG or PNG, under 1 MB).", "error")
    else:
        execute("UPDATE staff SET photo=? WHERE id=?", (data, sid))
        flash("Photo saved.", "ok")
    return redirect(url_for("staff"))


def save_photo(file_storage):
    """Turn an uploaded image into a data: URI small enough to keep in the DB."""
    if file_storage is None or not file_storage.filename:
        return None
    raw = file_storage.read()
    if not raw or len(raw) > 1024 * 1024:
        return None
    mime = (file_storage.mimetype or "image/jpeg").lower()
    if mime not in ("image/jpeg", "image/png", "image/webp"):
        mime = "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(raw).decode()




@app.route("/my-signature", methods=["GET", "POST"])
def my_signature():
    """A teacher uploads the signature that goes on report cards."""
    if is_student():
        flash("Only teachers and the admin can keep a signature.", "error")
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        if request.form.get("action") == "clear":
            execute("UPDATE users SET signature=NULL WHERE id=?", (uid(),))
            flash("Signature removed.", "ok")
        else:
            data = save_photo(request.files.get("signature"))
            if data is None:
                flash("Choose a small image (PNG with a transparent "
                      "background works best, under 1 MB).", "error")
            else:
                execute("UPDATE users SET signature=? WHERE id=?", (data, uid()))
                flash("Signature saved - it will appear on the report cards "
                      "of your class.", "ok")
        return redirect(url_for("my_signature"))
    row = query("SELECT signature FROM users WHERE id=?", (uid(),), one=True)
    return render_template("my_signature.html",
                           signature=row["signature"] if row else "",
                           principal=setting("principal_sign", ""),
                           is_admin=is_admin())


@app.route("/settings", methods=["GET", "POST"])
def settings():
    if not is_admin():
        flash("Only an admin can change school settings.", "error")
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        action = request.form.get("action")
        if action == "logo":
            data = save_photo(request.files.get("logo"))
            if data is None:
                flash("Choose a small image (JPG or PNG, under 1 MB).", "error")
            else:
                execute("INSERT OR REPLACE INTO settings (k, v) VALUES ('school_logo', ?)",
                        (data,))
                flash("School logo saved - it now appears on report cards and "
                      "certificates.", "ok")
        elif action == "name":
            name = (request.form.get("school_name") or "").strip()
            execute("INSERT OR REPLACE INTO settings (k, v) VALUES ('school_name', ?)",
                    (name or SCHOOL_NAME,))
            app_nm = (request.form.get("app_name") or "").strip()
            if app_nm:
                execute("INSERT OR REPLACE INTO settings (k, v)"
                        " VALUES ('app_name', ?)", (app_nm,))
            flash("Names saved.", "ok")
        elif action == "principal_sign":
            data = save_photo(request.files.get("signature"))
            if data is None:
                flash("Choose a small signature image (under 1 MB).", "error")
            else:
                execute("INSERT OR REPLACE INTO settings (k, v)"
                        " VALUES ('principal_sign', ?)", (data,))
                flash("Principal's signature saved.", "ok")
        elif action == "clear_principal":
            execute("DELETE FROM settings WHERE k='principal_sign'")
            flash("Principal's signature removed.", "ok")
        elif action == "clear_logo":
            execute("DELETE FROM settings WHERE k='school_logo'")
            flash("Logo removed.", "ok")
        return redirect(url_for("settings"))
    return render_template("settings.html",
                           app_name=setting("app_name", APP_NAME),
                           principal=setting("principal_sign", ""),
                           logo=setting("school_logo", ""),
                           name=setting("school_name", SCHOOL_NAME),
                           school_name=SCHOOL_NAME)



# --------------------------------------------------------------------------
#  leave applications
# --------------------------------------------------------------------------
@app.route("/my-leave", methods=["GET", "POST"])
def my_leave():
    if not is_student():
        return redirect(url_for("dashboard"))
    student = my_student()
    if student is None:
        return redirect(url_for("my_result"))
    if request.method == "POST":
        frm = (request.form.get("from_date") or "").strip()
        to = (request.form.get("to_date") or frm).strip()
        reason = (request.form.get("reason") or "").strip()
        if not frm or not to:
            flash("Choose the dates first.", "error")
        elif to < frm:
            flash("The end date cannot be before the start date.", "error")
        else:
            execute("""INSERT INTO leave_requests (student_id, from_date,
                       to_date, reason) VALUES (?,?,?,?)""",
                    (student["id"], frm, to, reason))
            flash("Leave application sent to your class teacher.", "ok")
        return redirect(url_for("my_leave"))
    rows = query("SELECT * FROM leave_requests WHERE student_id=?"
                 " ORDER BY id DESC", (student["id"],))
    return render_template("my_leave.html", student=student, rows=rows,
                           today=datetime.now().strftime("%Y-%m-%d"),
                           disp_date=disp_date)


@app.route("/leave", methods=["GET", "POST"])
def leave():
    scope = class_scope()
    if request.method == "POST":
        req_id = request.form.get("id")
        decision = request.form.get("decision")
        if req_id and decision in ("Approved", "Rejected"):
            row = query("SELECT * FROM leave_requests WHERE id=?",
                        (req_id,), one=True)
            if row:
                execute("""UPDATE leave_requests SET status=?, decided_by=?,
                           decided_on=CURRENT_TIMESTAMP WHERE id=?""",
                        (decision, uid(), req_id))
                if decision == "Approved":
                    # mark those days as Leave, unless already marked
                    st = query("SELECT * FROM students WHERE id=?",
                               (row["student_id"],), one=True)
                    if st:
                        day = datetime.strptime(row["from_date"], "%Y-%m-%d")
                        end = datetime.strptime(row["to_date"], "%Y-%m-%d")
                        while day <= end:
                            key = day.strftime("%Y-%m-%d")
                            exists = query("SELECT id FROM attendance WHERE"
                                           " student_id=? AND att_date=?",
                                           (st["id"], key), one=True)
                            if not exists:
                                execute("""INSERT INTO attendance (student_id,
                                           class_name, section, att_date, status,
                                           marked_by, remarks)
                                           VALUES (?,?,?,?,?,?,?)""",
                                        (st["id"], st["class_name"],
                                         st["section"], key, "Leave", uid(),
                                         "approved leave"))
                            day += timedelta(days=1)
                flash(f"Application {decision.lower()}.", "ok")
        return redirect(url_for("leave"))

    where = " WHERE 1=1"
    args = []
    if scope:
        where += " AND IFNULL(st.class_name,'')=? AND (IFNULL(st.section,'')='' OR IFNULL(st.section,'')=?)"
        args += [scope[0], scope[1]]
    rows = query(f"""SELECT l.*, st.name, st.class_name, st.section, st.roll_no
                     FROM leave_requests l JOIN students st ON st.id = l.student_id
                     {where} ORDER BY (l.status='Pending') DESC, l.id DESC""",
                 tuple(args))
    return render_template("leave.html", rows=rows, scope=scope,
                           disp_date=disp_date)



# --------------------------------------------------------------------------
#  bulk import, bulk report cards, ID cards, backup
# --------------------------------------------------------------------------
@app.route("/students/import", methods=["GET", "POST"])
def students_import():
    if is_student():
        flash("Only staff can import students.", "error")
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        up = request.files.get("csv")
        if not up or not up.filename:
            flash("Choose a CSV file first.", "error")
            return redirect(url_for("students_import"))
        raw = up.read().decode("utf-8-sig", errors="replace")
        rows = list(csv.DictReader(io.StringIO(raw)))
        added = skipped = 0
        for row in rows:
            clean = {(k or "").strip().lower(): (v or "").strip()
                     for k, v in row.items()}
            name = clean.get("name") or clean.get("student_name") or ""
            cls = clean.get("class") or clean.get("class_name") or ""
            if not name or not cls:
                skipped += 1
                continue
            adm = clean.get("admission_no") or clean.get("admission") or ""
            if adm and query("SELECT id FROM students WHERE admission_no=?",
                             (adm,), one=True):
                skipped += 1
                continue
            execute("""INSERT INTO students (admission_no, roll_no, name,
                       class_name, section, gender, dob, father_name,
                       mother_name, phone, email, address, status, owner_id)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (adm or f"ADM{datetime.now():%y%m%d%H%M%S}{added}",
                     clean.get("roll_no") or clean.get("roll") or "",
                     name, cls, clean.get("section", ""),
                     clean.get("gender", "Male"), clean.get("dob", ""),
                     clean.get("father_name", ""), clean.get("mother_name", ""),
                     clean.get("phone", ""), clean.get("email", ""),
                     clean.get("address", ""), "Active", owner_value()))
            added += 1
        flash(f"Imported {added} student(s); skipped {skipped} row(s).", "ok")
        return redirect(url_for("students"))
    return render_template("students_import.html", school_name=SCHOOL_NAME)


@app.route("/results/print")
def results_print():
    """Every student's full report card, one per page, in a single PDF."""
    import re as _re
    exam_id = request.args.get("exam_id", type=int)
    class_name = (request.args.get("class_name") or "").strip()
    if not exam_id or not class_name:
        flash("Choose an exam and a class first.", "error")
        return redirect(url_for("results"))
    exam = query("SELECT * FROM exams WHERE id=?", (exam_id,), one=True)
    rows = compute_results(exam_id, class_name)
    picked = (request.args.get("students") or "").strip()
    if picked:
        wanted = {int(x) for x in picked.split(",") if x.strip().isdigit()}
        rows = [r for r in rows if r["student_id"] in wanted]
    limit = request.args.get("limit", type=int) or 0
    if limit:
        rows = rows[:limit]

    ct = class_teacher_of(class_name, "")
    teacher_sign = (ct["signature"] or "") if ct else ""
    principal_sign = setting("principal_sign", "")
    issued_on = datetime.now().strftime("%d/%m/%Y")

    pages, styles = [], ""
    for r in rows:
        st = query("SELECT * FROM students WHERE id=?", (r["student_id"],), one=True)
        if st is None:
            continue
        att = query("""SELECT COUNT(*) n,
                              SUM(CASE WHEN status IN ('Present','Late')
                                       THEN 1 ELSE 0 END) p
                       FROM attendance WHERE student_id=?""",
                    (st["id"],), one=True)
        a_total = att["n"] if att else 0
        a_present = att["p"] if att else 0
        a_pct = round(a_present / a_total * 100) if a_total else 0
        html = render_template(
            "report_card.html", exam=exam, student=st, mine=r,
            subjects=subject_rows_for(exam_id, st["id"]),
            co_areas=co_grades_for(r),
            school=setting("school_name", SCHOOL_NAME), logo=school_logo(),
            principal_sign=principal_sign, teacher_sign=teacher_sign,
            auto_print=False, bulk=True, issued_on=issued_on,
            fmt_num=fmt_num, exam_label=exam_label, disp_date=disp_date,
            att_pct=a_pct, att_total=a_total, att_present=a_present)
        if not styles:
            styles = "".join(_re.findall(r"<style>.*?</style>", html, _re.S))
        m = _re.search(r"<body[^>]*>(.*)</body>", html, _re.S)
        pages.append(m.group(1) if m else html)

    css = ("<style>@page{size:A4;margin:6mm}"
           ".rc-sheet{page-break-after:always;break-after:page}"
           ".rc-sheet:last-of-type{page-break-after:auto;break-after:auto}"
           "@media screen{.rc-sheet{margin-bottom:18px}}"
           "</style>")
    out = ("<!doctype html><html><head><meta charset='utf-8'>"
           f"<title>Report cards · {class_name}</title>{styles}{css}</head><body>"
           + "".join(f'<div class="rc-sheet">{p}</div>' for p in pages)
           + "<script>window.onload=function(){window.print()}</script>"
           "</body></html>")
    return Response(out, mimetype="text/html")


@app.route("/id-cards")
def id_cards():
    if is_student():
        flash("Only staff can print ID cards.", "error")
        return redirect(url_for("dashboard"))
    cls = (request.args.get("class_name") or "").strip()
    sec = (request.args.get("section") or "").strip()
    classes = sorted({r["class_name"] for r in query(
        "SELECT DISTINCT class_name FROM students WHERE class_name<>''")})
    rows = []
    if cls:
        where, args = owned_where("class_name=? AND status='Active'", (cls,))
        if sec:
            where += " AND IFNULL(section,'')=?"
            args = tuple(args) + (sec,)
        rows = query("SELECT * FROM students" + where +
                     " ORDER BY CAST(roll_no AS INTEGER), roll_no", args)
    return render_template("id_cards.html", rows=rows, cls=cls, sec=sec,
                           classes=classes, school=setting("school_name", SCHOOL_NAME),
                           logo=school_logo())


@app.route("/backup")
def backup():
    if not is_admin():
        flash("Only an admin can download a backup.", "error")
        return redirect(url_for("dashboard"))
    tables = [r["name"] for r in query(
        "SELECT name FROM sqlite_master WHERE type='table'"
        " AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    dump = {"exported_on": datetime.now().isoformat(timespec="seconds"),
            "app": APP_NAME, "school": setting("school_name", SCHOOL_NAME),
            "tables": {}}
    for t in tables:
        dump["tables"][t] = [dict(r) for r in query(f"SELECT * FROM {t}")]
    payload = json.dumps(dump, indent=1, default=str)
    name = f"backup-{datetime.now():%Y%m%d-%H%M}.json"
    return Response(payload, mimetype="application/json",
                    headers={"Content-Disposition": f"attachment; filename={name}"})



# --------------------------------------------------------------------------
#  personal information
# --------------------------------------------------------------------------
@app.route("/my-profile")
def my_profile():
    """A student's own personal details (read only)."""
    if not is_student():
        return redirect(url_for("dashboard"))
    student = my_student()
    if student is None:
        flash("This account is not linked to a student record.", "error")
        return redirect(url_for("my_result"))
    return render_template("personal_info.html", student=student,
                           staff_view=False, disp_date=disp_date)


@app.route("/students/<int:sid>/profile")
def student_profile(sid):
    """The same sheet, opened by a teacher or the admin."""
    if is_student():
        return redirect(url_for("my_profile"))
    student = query("SELECT * FROM students WHERE id=?", (sid,), one=True)
    if student is None:
        flash("No such student.", "error")
        return redirect(url_for("students"))
    return render_template("personal_info.html", student=student,
                           staff_view=True, disp_date=disp_date)


# --------------------------------------------------------------------------
#  certificates (bonafide / transfer / character)
# --------------------------------------------------------------------------
CERT_TYPES = ("Bonafide", "Transfer", "Character", "Fee clearance")


@app.route("/certificates")
def certificates():
    cls = (request.args.get("class_name") or "").strip()
    where, args = " WHERE status='Active'", []
    if cls:
        where += " AND class_name=?"
        args.append(cls)
    rows = query("SELECT * FROM students" + where +
                 " ORDER BY class_name, CAST(roll_no AS INTEGER), roll_no", args)
    classes = sorted({r["class_name"] for r in query(
        "SELECT DISTINCT class_name FROM students WHERE class_name<>''")})
    return render_template("certificates.html", students=rows, classes=classes,
                           cls=cls, types=CERT_TYPES, today=datetime.now().strftime("%d/%m/%Y"))


@app.route("/certificates/<int:sid>")
def certificate_print(sid):
    student = query("SELECT * FROM students WHERE id=?", (sid,), one=True)
    if student is None:
        abort(404)
    kind = request.args.get("type", "Bonafide")
    if kind not in CERT_TYPES:
        kind = "Bonafide"
    return render_template("certificate_print.html", student=student,
                           kind=kind, today=datetime.now().strftime("%d/%m/%Y"),
                           disp_date=disp_date)


# --------------------------------------------------------------------------
#  message log (SMS / WhatsApp templates)
# --------------------------------------------------------------------------
@app.route("/notifications", methods=["GET", "POST"])
def notifications():
    if request.method == "POST":
        message = (request.form.get("message") or "").strip()
        if not message:
            flash("Write the message first.", "error")
            return redirect(url_for("notifications"))
        channel = request.form.get("channel") or "SMS"
        audience = request.form.get("audience") or "all"
        execute("""INSERT INTO notifications (channel, audience, message,
                   by_user) VALUES (?,?,?,?)""",
                (channel, audience, message, uid()))
        if channel == "SMS" and sms_configured():
            numbers = [r["phone"] for r in query(
                "SELECT phone FROM students WHERE IFNULL(phone,'')<>''")]
            sent = sum(1 for n in numbers if send_sms(n, message)[0])
            flash(f"Message saved and sent to {sent} of {len(numbers)} "
                  f"numbers.", "ok")
        else:
            flash("Message saved to the log." +
                  ("" if channel != "SMS" else
                   " (SMS gateway set nahi hai - SMS_PROVIDER/SMS_KEY daalein.)"),
                  "ok")
        return redirect(url_for("notifications"))
    rows = query("""SELECT n.*, u.username AS author FROM notifications n
                    LEFT JOIN users u ON u.id = n.by_user
                    ORDER BY n.id DESC LIMIT 100""")
    return render_template("notifications.html", rows=rows)



# --------------------------------------------------------------------------
#  the student's home: everything at a glance
# --------------------------------------------------------------------------
@app.route("/my-home")
def my_home():
    if not is_student():
        return redirect(url_for("dashboard"))
    student = my_student()
    if student is None:
        flash("This account is not linked to a student record.", "error")
        return redirect(url_for("my_result"))

    # attendance
    att = query("""SELECT SUM(CASE WHEN status IN ('Present','Late') THEN 1 ELSE 0 END) p,
                          COUNT(*) n FROM attendance WHERE student_id=?""",
                (student["id"],), one=True)
    att_pct = round((att["p"] or 0) / att["n"] * 100) if att and att["n"] else 0
    last_days = query("SELECT * FROM attendance WHERE student_id=?"
                      " ORDER BY att_date DESC LIMIT 10", (student["id"],))

    # latest result
    latest, subject_bars = None, []
    exam_rows = query("""SELECT DISTINCT e.* FROM marks m
                         JOIN exams e ON e.id = m.exam_id
                         WHERE m.student_id=? ORDER BY e.id DESC LIMIT 1""",
                      (student["id"],), one=True)
    if exam_rows:
        rows = compute_results(exam_rows["id"],
                               (exam_rows["class_name"] or "").strip())
        latest = next((r for r in rows if r["student_id"] == student["id"]), None)
        for row in query("""SELECT s.subject_name, s.subject_code,
                                   sc.max_marks, m.marks_obtained
                            FROM marks m JOIN subjects s ON s.id = m.subject_id
                            LEFT JOIN exam_schedule sc ON sc.exam_id = m.exam_id
                                   AND sc.subject_id = m.subject_id
                            WHERE m.exam_id=? AND m.student_id=?
                            ORDER BY s.subject_code""",
                         (exam_rows["id"], student["id"])):
            mx = float(row["max_marks"] or 100) or 100
            got = float(row["marks_obtained"] or 0)
            subject_bars.append({"label": row["subject_code"] or row["subject_name"][:4],
                                 "pct": round(got / mx * 100),
                                 "got": got, "max": mx})

    # homework still to do
    todo = query("""SELECT COUNT(*) c FROM homework h
                    WHERE h.class_name=?
                      AND (IFNULL(h.section,'')='' OR IFNULL(h.section,'')=?)
                      AND (IFNULL(h.due_date,'')='' OR h.due_date>=?)""",
                 ((student["class_name"] or "").strip(),
                  (student["section"] or "").strip(),
                  datetime.now().strftime("%Y-%m-%d")), one=True)["c"]

    # fees
    heads = query("SELECT IFNULL(SUM(amount),0) t FROM fee_heads"
                  " WHERE IFNULL(class_name,'')=?",
                  ((student["class_name"] or "").strip(),), one=True)["t"] or 0
    paid = query("SELECT IFNULL(SUM(amount),0) t FROM fee_payments"
                 " WHERE student_id=?", (student["id"],), one=True)["t"] or 0

    # today's timetable
    today_name = datetime.now().strftime("%A")
    periods = query("""SELECT t.period, s.subject_code, s.subject_name, t.teacher
                       FROM timetable t
                       LEFT JOIN subjects s ON s.id = t.subject_id
                       WHERE t.class_name=? AND IFNULL(t.section,'')=? AND t.day=?
                       ORDER BY t.period""",
                    ((student["class_name"] or "").strip(),
                     (student["section"] or "").strip(), today_name))

    notices_rows = query("""SELECT * FROM circulars
                            WHERE audience IN ('all','students')
                              AND (IFNULL(class_name,'')='' OR class_name=?)
                            ORDER BY pinned DESC, id DESC LIMIT 3""",
                         ((student["class_name"] or "").strip(),))

    homework_rows = query("""SELECT h.*, s.subject_name FROM homework h
                             LEFT JOIN subjects s ON s.id = h.subject_id
                             WHERE h.class_name=?
                               AND (IFNULL(h.section,'')='' OR IFNULL(h.section,'')=?)
                             ORDER BY h.due_date, h.id DESC LIMIT 5""",
                          ((student["class_name"] or "").strip(),
                           (student["section"] or "").strip()))
    books = query("""SELECT i.*, b.title FROM book_issues i
                     JOIN books b ON b.id = i.book_id
                     WHERE i.student_id=? AND i.returned_on IS NULL
                     ORDER BY i.due_on LIMIT 3""", (student["id"],))
    bus = query("""SELECT t.stop_name, r.route_name, r.vehicle_no, r.driver_name,
                          r.driver_phone FROM student_transport t
                   LEFT JOIN transport_routes r ON r.id = t.route_id
                   WHERE t.student_id=?""", (student["id"],), one=True)
    last_payment = query("""SELECT * FROM fee_payments WHERE student_id=?
                            ORDER BY paid_on DESC, id DESC LIMIT 1""",
                         (student["id"],), one=True)
    week = query("""SELECT t.day, t.period, s.subject_code FROM timetable t
                    LEFT JOIN subjects s ON s.id = t.subject_id
                    WHERE t.class_name=? AND IFNULL(t.section,'')=?
                    ORDER BY t.period""",
                 ((student["class_name"] or "").strip(),
                  (student["section"] or "").strip()))
    history = []
    for e in query("""SELECT DISTINCT e.* FROM marks m JOIN exams e ON e.id = m.exam_id
                      WHERE m.student_id=? ORDER BY e.id DESC LIMIT 4""",
                   (student["id"],)):
        rows = compute_results(e["id"], (e["class_name"] or "").strip())
        mine = next((r for r in rows if r["student_id"] == student["id"]), None)
        if mine:
            history.append({"label": (e["exam_type"] or "Exam")[:10],
                            "pct": round(mine["percentage"]), "grade": mine["grade"]})
    upcoming_events = query("""SELECT * FROM events
                               WHERE IFNULL(event_date,'') >= ?
                               ORDER BY event_date LIMIT 3""",
                            (datetime.now().strftime("%Y-%m-%d"),))

    papers = query("""SELECT sc.exam_date, sc.start_time, sc.room,
                             sub.subject_name, e.exam_type
                      FROM exam_schedule sc
                      JOIN exams e ON e.id = sc.exam_id
                      LEFT JOIN subjects sub ON sub.id = sc.subject_id
                      WHERE IFNULL(e.class_name,'')=? AND IFNULL(sc.exam_date,'')>=?
                      ORDER BY sc.exam_date, sc.start_time LIMIT 5""",
                   ((student["class_name"] or "").strip(),
                    datetime.now().strftime("%Y-%m-%d")))
    tally = {"Present": 0, "Absent": 0, "Late": 0, "Leave": 0}
    for row in query("""SELECT status, COUNT(*) c FROM attendance
                        WHERE student_id=? GROUP BY status""", (student["id"],)):
        tally[row["status"]] = row["c"]
    teachers = query("""SELECT name, role, subject, phone FROM staff
                        WHERE active=1 AND IFNULL(role,'')<>'' ORDER BY name LIMIT 5""")

    by_day = {}
    for w in week:
        by_day.setdefault(w["day"], []).append(w["subject_code"])

    return render_template("my_home.html", student=student, att_pct=att_pct,
                           homework_rows=homework_rows, books=books, bus=bus,
                           last_payment=last_payment, by_day=by_day,
                           history=history, upcoming_events=upcoming_events,
                           papers=papers, tally=tally, teachers=teachers,
                           att_total=att["n"] if att else 0,
                           last_days=last_days, latest=latest,
                           exam=exam_rows, subject_bars=subject_bars,
                           todo=todo, fee_total=float(heads),
                           fee_paid=float(paid),
                           fee_due=float(heads) - float(paid),
                           periods=periods, today_name=today_name,
                           notices=notices_rows,
                           exam_label=exam_label, fmt_num=fmt_num,
                           disp_date=disp_date)


# --------------------------------------------------------------------------
#  a student's own result
# --------------------------------------------------------------------------
@app.route("/my-result")
def my_result():
    """What a student account sees: only their own marks and result."""
    if not is_student():
        return redirect(url_for("dashboard"))
    student = my_student()
    if student is None:
        flash("This account is not linked to a student record. "
              "Ask the school office to fix it.", "error")
        return render_template("my_result.html", student=None, exams=[],
                               detail=None, exam=None)

    exam_rows = query("""SELECT DISTINCT e.* FROM marks m
                         JOIN exams e ON e.id = m.exam_id
                         WHERE m.student_id=?
                         ORDER BY e.id DESC""", (student["id"],))

    summary = []
    for e in exam_rows:
        rows = compute_results(e["id"], (e["class_name"] or "").strip())
        mine = next((r for r in rows if r["student_id"] == student["id"]), None)
        if mine:
            summary.append({"exam": e, "result": mine})

    detail, exam = None, None
    exam_id = request.args.get("exam_id", type=int)
    if exam_id:
        exam = next((item["exam"] for item in summary
                     if item["exam"]["id"] == exam_id), None)
        if exam:
            detail = query("""SELECT s.subject_name, s.subject_code,
                                     sc.max_marks, sc.pass_marks,
                                     m.marks_obtained, m.remarks
                              FROM marks m
                              JOIN subjects s ON s.id = m.subject_id
                              LEFT JOIN exam_schedule sc
                                     ON sc.exam_id = m.exam_id
                                    AND sc.subject_id = m.subject_id
                              WHERE m.exam_id=? AND m.student_id=?
                              ORDER BY s.subject_code""",
                           (exam_id, student["id"]))

    return render_template("my_result.html", student=student, exams=summary,
                           detail=detail, exam=exam, exam_label=exam_label,
                           fmt_num=fmt_num)


# --------------------------------------------------------------------------
#  admin: user accounts
# --------------------------------------------------------------------------
def admin_only():
    if not is_admin():
        flash("Only an admin can manage users.", "error")
        return redirect(url_for("dashboard"))
    return None


@app.route("/users")
def users():
    blocked = admin_only()
    if blocked:
        return blocked
    rows = query("""SELECT u.*,
                      (SELECT COUNT(*) FROM students s WHERE s.owner_id=u.id)
                        AS n_students,
                      (SELECT COUNT(*) FROM exams e WHERE e.owner_id=u.id)
                        AS n_exams
                    FROM users u ORDER BY u.role, u.username""")
    edit_id = request.args.get("edit", type=int)
    editing = query("SELECT * FROM users WHERE id=?", (edit_id,),
                    one=True) if edit_id else None
    students = query("SELECT id, name, class_name, roll_no FROM students"
                     " ORDER BY class_name, CAST(roll_no AS INTEGER), roll_no")
    return render_template("users.html", users=rows, editing=editing,
                           students=students)


@app.route("/users/save", methods=["POST"])
def user_save():
    blocked = admin_only()
    if blocked:
        return blocked
    f = request.form
    user_id = f.get("id") or ""
    username = f.get("username", "").strip().lower()
    full_name = f.get("full_name", "").strip()
    role = f.get("role", "user")
    if role == "teacher":
        role = "user"
    password = f.get("password", "")
    if role not in ("admin", "user", "student", "parent"):
        role = "user"
    student_id = f.get("student_id") or ""
    if role not in ("student", "parent"):
        student_id = None
    elif not student_id:
        flash("Pick the student this account belongs to.", "error")
        return redirect(url_for("users"))
    else:
        student_id = int(student_id)
    if not username:
        flash("A username is required.", "error")
        return redirect(url_for("users"))
    if not all(ch.isalnum() or ch in "._-" for ch in username):
        flash("Username may contain letters, digits, dot, dash or underscore.",
              "error")
        return redirect(url_for("users"))
    dup = query("SELECT id FROM users WHERE username=? AND id<>?",
                (username, int(user_id) if user_id else 0), one=True)
    if dup:
        flash(f"Username '{username}' is already taken.", "error")
        return redirect(url_for("users"))

    if user_id:
        if password:
            execute("UPDATE users SET username=?, full_name=?, role=?,"
                    " student_id=?, class_name=?, section=?,"
                    " password_hash=? WHERE id=?",
                    (username, full_name, role, student_id,
                     (f.get("class_name") or "").strip(),
                     (f.get("section") or "").strip(),
                     generate_password_hash(password), int(user_id)))
        else:
            execute("UPDATE users SET username=?, full_name=?, role=?,"
                    " student_id=?, class_name=?, section=? WHERE id=?",
                    (username, full_name, role, student_id,
                     (f.get("class_name") or "").strip(),
                     (f.get("section") or "").strip(), int(user_id)))
        flash(f"User '{username}' updated.", "ok")
    else:
        if len(password) < 4:
            flash("Give the new user a password of at least 4 characters.",
                  "error")
            return redirect(url_for("users"))
        execute("INSERT INTO users (username, full_name, password_hash, role,"
                " student_id, class_name, section) VALUES (?,?,?,?,?,?,?)",
                (username, full_name, generate_password_hash(password), role,
                 student_id, (f.get("class_name") or "").strip(),
                 (f.get("section") or "").strip()))
        flash(f"User '{username}' created.", "ok")
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/toggle", methods=["POST"])
def user_toggle(user_id):
    blocked = admin_only()
    if blocked:
        return blocked
    if user_id == uid():
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("users"))
    row = query("SELECT username, active FROM users WHERE id=?", (user_id,),
                one=True)
    if row:
        execute("UPDATE users SET active=? WHERE id=?",
                (0 if row["active"] else 1, user_id))
        flash(f"User '{row['username']}' "
              f"{'deactivated' if row['active'] else 'activated'}.", "ok")
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/delete", methods=["POST"])
def user_delete(user_id):
    blocked = admin_only()
    if blocked:
        return blocked
    if user_id == uid():
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("users"))
    row = query("SELECT username FROM users WHERE id=?", (user_id,), one=True)
    if not row:
        return redirect(url_for("users"))
    n = (query("SELECT COUNT(*) c FROM students WHERE owner_id=?",
               (user_id,), one=True)["c"]
         + query("SELECT COUNT(*) c FROM exams WHERE owner_id=?",
                 (user_id,), one=True)["c"])
    if n:
        flash(f"'{row['username']}' still owns {n} record(s). Deactivate the "
              f"account instead, or delete their data first.", "error")
        return redirect(url_for("users"))
    execute("DELETE FROM users WHERE id=?", (user_id,))
    flash(f"User '{row['username']}' deleted.", "ok")
    return redirect(url_for("users"))


# --------------------------------------------------------------------------
#  diagnostics: never show a bare "Internal Server Error"
# --------------------------------------------------------------------------
REQUIRED_TEMPLATES = ("welcome.html", "base.html", "dashboard.html",
                      "students.html", "exams.html", "subjects.html",
                      "schedule.html", "marks.html", "results.html",
                      "login.html", "users.html", "my_result.html", "attendance.html",
                      "homework.html", "circulars.html",
                      "my_attendance.html", "my_homework.html", "notices.html",
                      "password.html", "fees.html", "receipt.html",
                      "my_fees.html", "timetable.html", "my_timetable.html",
                      "report_card.html", "transport.html", "my_transport.html",
                      "library.html", "my_library.html", "staff.html",
                      "events.html", "certificates.html",
                      "certificate_print.html",
                      "payroll_slip.html", "notifications.html",
                      "my_home.html", "teacher_dashboard.html",
                      "settings.html", "my_signature.html", "my_leave.html", "leave.html",
                      "students_import.html", "personal_info.html", "id_cards.html", "report_card_bulk.html")

ERROR_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ app_name }} - error</title>
<style>
 body{margin:0;background:#f4f6fb;color:#0f172a;
      font:15px/1.55 "Segoe UI",Inter,system-ui,Arial,sans-serif}
 .wrap{max-width:860px;margin:34px auto;padding:0 18px}
 .card{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:20px 22px;margin-bottom:16px}
 h1{font-size:20px;margin:0 0 4px}
 .muted{color:#64748b;font-size:13px}
 .err{background:#fee2e2;border:1px solid #fecaca;color:#991b1b;border-radius:8px;
      padding:12px 14px;margin:14px 0;font-family:ui-monospace,Consolas,monospace;font-size:13px}
 ul{margin:8px 0 0;padding-left:18px}
 li{margin:3px 0;font-size:14px}
 .ok{color:#059669}.bad{color:#dc2626;font-weight:600}
 pre{background:#0f172a;color:#e2e8f0;padding:14px;border-radius:8px;overflow:auto;
     font-size:12px;line-height:1.45}
 code{background:#f1f5f9;padding:1px 5px;border-radius:4px;font-size:13px}
</style></head><body><div class="wrap">
<div class="card">
  <h1>The app is running, but this page could not be built</h1>
  <p class="muted">{{ school }} &middot; this page is shown instead of a blank
     &ldquo;Internal Server Error&rdquo; so the cause is visible.</p>
  <div class="err">{{ error }}</div>
  <h2 style="font-size:15px;margin:16px 0 4px">Environment check</h2>
  <ul>{% for label, ok, detail in checks %}
    <li><span class="{{ 'ok' if ok else 'bad' }}">{{ 'OK' if ok else 'PROBLEM' }}</span>
        &nbsp;{{ label }}{% if detail %} &mdash; <span class="muted">{{ detail }}</span>{% endif %}</li>
  {% endfor %}</ul>
</div>
{% if tb %}<div class="card"><h2 style="font-size:15px;margin:0 0 8px">Traceback</h2>
<pre>{{ tb }}</pre></div>{% endif %}
<p class="muted">Open <code>/healthz</code> for the same information as JSON.</p>
</div></body></html>"""


def diagnostics():
    """Everything that commonly breaks a fresh deploy, checked live."""
    checks = []
    checks.append(("app.py loaded", True, os.path.abspath(__file__)))

    missing = [t for t in REQUIRED_TEMPLATES if t not in TEMPLATES]
    checks.append((f"built-in templates ({len(REQUIRED_TEMPLATES)} pages)",
                   not missing,
                   "all present" if not missing else "missing: " + ", ".join(missing)))
    checks.append(("built-in stylesheet", bool(STYLE_CSS),
                   f"{len(STYLE_CSS)} bytes"))

    db_ok = True
    if TURSO_URL and not CLOUD_ERROR:
        db_detail = f"Turso cloud database ({TURSO_URL}) - persistent"
    elif TURSO_URL:
        db_ok = False
        db_detail = (f"Turso configured but FAILED: {CLOUD_ERROR} - "
                     f"running on the local file, data is temporary")
    else:
        db_detail = f"{DB_PATH} (local file - data is temporary)"
    try:
        conn = open_db()
        conn.execute("CREATE TABLE IF NOT EXISTS _probe (x INTEGER)")
        conn.execute("DROP TABLE _probe")
        conn.commit()
        conn.close()
    except Exception as exc:            # noqa: BLE001 - report anything
        db_ok, db_detail = False, f"{DB_PATH} - {exc}"
    checks.append(("database writable", db_ok, db_detail))

    try:
        with sqlite3.connect(DB_PATH) as probe:
            admins = probe.execute(
                "SELECT COUNT(*) FROM users WHERE role='admin' AND active=1"
            ).fetchone()[0]
        checks.append(("admin account", admins > 0,
                       f"{admins} active admin(s)" if admins else
                       "no active admin - nobody can log in"))
    except Exception as exc:            # noqa: BLE001
        checks.append(("admin account", False, str(exc)))
    return checks


@app.errorhandler(Exception)
def handle_error(exc):
    """Turn any 500 into a page that says what actually went wrong."""
    from werkzeug.exceptions import HTTPException
    if isinstance(exc, HTTPException) and exc.code < 500:
        return exc
    tb = traceback.format_exc()
    try:
        app.logger.error("Unhandled error: %s\n%s", exc, tb)
    except Exception:                   # noqa: BLE001
        pass
    return render_template_string(
        ERROR_PAGE, error=f"{type(exc).__name__}: {exc}",
        school=SCHOOL_NAME, checks=diagnostics(), tb=tb), 500


@app.route("/robots.txt")
def robots():
    """Only the public landing page may be indexed - the app stays private."""
    lines = [
        "User-agent: *",
        "Allow: /about$",
        "Allow: /static/",
        "Disallow: /",
        f"Sitemap: {request.host_url.rstrip('/')}/sitemap.xml",
    ]
    return Response("\n".join(lines) + "\n", mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap():
    url = url_for("about", _external=True)
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           f"<url><loc>{url}</loc><changefreq>weekly</changefreq>"
           "<priority>1.0</priority></url></urlset>")
    return Response(xml, mimetype="application/xml")


@app.after_request
def no_index(response):
    """Private pages ask crawlers to stay away; the landing page is open."""
    if request.endpoint not in ("about", "static", "robots", "sitemap"):
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response



@app.route("/setup")
def setup_route():
    """Create the tables in a brand-new database.

    Needs the admin password as ?key=..., so a stranger cannot reset anything.
    Safe to open more than once - it only creates what is missing.
    """
    key = request.args.get("key", "")
    expected = ADMIN_PASSWORD or os.environ.get("SETUP_KEY", "")
    if not expected:
        return {"ok": False, "error": "set ADMIN_PASSWORD (or SETUP_KEY) in "
                                      "Render's environment first"}, 403
    if key != expected:
        return {"ok": False, "error": "wrong key"}, 403
    try:
        conn = open_db()
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
        tables = [r["name"] if isinstance(r, dict) else r[0] for r in
                  conn.execute("SELECT name FROM sqlite_master WHERE type='table'"
                               " ORDER BY name").fetchall()]
        users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()
        if request.args.get("reset") and ADMIN_PASSWORD:
            conn.execute("UPDATE users SET password_hash=? WHERE role='admin'",
                         (generate_password_hash(ADMIN_PASSWORD),))
            conn.commit()
        admin = conn.execute("SELECT username, role FROM users"
                             " WHERE role='admin' LIMIT 1").fetchone()
        conn.close()
        admin_name = (admin["username"] if isinstance(admin, dict)
                      else admin[0]) if admin else None
        return {"ok": True, "database": TURSO_URL or DB_PATH,
                "tables": tables, "admin_username": admin_name,
                "users": (users["c"] if isinstance(users, dict) else users[0])}
    except Exception as exc:                 # noqa: BLE001
        return {"ok": False, "database": TURSO_URL or DB_PATH,
                "error": f"{type(exc).__name__}: {exc}"[:400]}, 500


@app.route("/healthz")
def healthz():
    """Render's health check.

    Logged out it answers only {"status": "ok"} - enough for the platform,
    nothing about the installation. The full checklist (file paths, database
    location, admin count) is shown to a logged-in user only.
    """
    if not getattr(g, "user", None):
        return {"status": "ok"}
    checks = diagnostics()
    return {
        "status": "ok" if all(ok for _l, ok, _d in checks) else "problem",
        "checks": [{"check": label, "ok": ok, "detail": detail}
                   for label, ok, detail in checks],
    }


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
