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
import gzip
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
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n<title>Report card · {{ student.name }}</title>\n<style>\n body{font:14.5px/1.65 Georgia,"Times New Roman",serif;color:#111;margin:0;padding:14px;background:#fbf7ee}\n .wrap{max-width:100%;margin:0 auto;border:3px double #1b2a5e;padding:24px 32px 20px;\n       position:relative;overflow:hidden;\n       background:linear-gradient(160deg,#fdfaf3 0%,#f7f0e2 45%,#f2e8d6 100%);\n       min-height:auto;display:flex;flex-direction:column}\n .watermark{position:absolute;inset:0;display:flex;align-items:center;\n            justify-content:center;opacity:.22;\n            pointer-events:none;z-index:0;mix-blend-mode:multiply}\n .watermark img{width:56%;max-width:430px;filter:saturate(1.5) contrast(1.1)}\n .wrap > *:not(.watermark){position:relative;z-index:1}\n /* saare boxes transparent — logo poora dikhe */\n .who,.sumline,.legend{background:transparent!important;border-color:rgba(226,214,189,.85)!important}\n tbody td{background:transparent!important}\n .tot td{background:rgba(240,229,206,.35)!important}\n th{background:rgba(27,42,94,.88)!important}\n .co th{background:rgba(27,42,94,.88)!important}\n .co td:last-child{background:transparent!important}\n .sign-table td{background:transparent!important}\n .letterhead{display:flex;flex-direction:column;align-items:center;justify-content:center;\n             text-align:center;gap:4px;position:relative;\n             background:transparent;\n             border:none;\n             box-shadow:none;\n             border-radius:0;padding:6px 0 4px;\n             -webkit-print-color-adjust:exact;print-color-adjust:exact}\n .lh-left{display:flex;flex-direction:row;align-items:center;justify-content:center;\n          gap:12px}\n .lh-left img{height:86px;background:none;border:none;border-radius:0;\n              padding:0;box-shadow:none;mix-blend-mode:multiply}\n .lh-left h1{margin:0;font-size:32px;letter-spacing:.09em;color:#1b2a5e;\n              text-shadow:0 1px 0 rgba(255,255,255,.7)}\n .lh-left p{margin:2px 0 0;font-size:12px;letter-spacing:.12em;text-transform:uppercase;\n            color:#e2d6bd}\n .lh-right{position:static;display:flex;align-items:baseline;justify-content:center;\n            gap:6px;line-height:1.2;text-align:center;margin-top:2px}\n .lh-right span{font-size:10px;letter-spacing:.2em;text-transform:uppercase;\n                color:#8a6b4a}\n .lh-right strong{font-size:15px;letter-spacing:.04em;color:#1b2a5e}\n .sub-line{text-align:center;font-size:12px;letter-spacing:.16em;text-transform:uppercase;\n            color:#1b2a5e;font-weight:700;margin:-4px 0 10px}\n .lh-rule{height:4px;border-radius:999px;margin:8px 0 8px;\n          background:linear-gradient(90deg,#1b2a5e,#e07a2f 50%,#c8a04a);\n          -webkit-print-color-adjust:exact;print-color-adjust:exact}\n .who{display:flex;gap:14px;align-items:flex-start;background:rgba(255,252,244,.72);\n       border:1px solid #e2d6bd;border-radius:10px;\n       padding:7px 14px;margin-bottom:8px}\n .sumline{background:rgba(255,252,244,.72);border:1px solid #e2d6bd;border-radius:10px;\n          padding:4px 14px;margin:8px 0}\n .who .pic{width:72px;height:72px;object-fit:cover;border:1px solid #ddcfb2;border-radius:6px}\n .who table{flex:1}\n .legend{display:flex;flex-wrap:wrap;gap:3px 12px;align-items:center;margin:7px 0 3px;background:rgba(255,252,244,.7);border:1px solid #e2d6bd;border-radius:8px;padding:5px 12px;\n         font-size:12px;color:#475569;border-top:1px dashed #ddcfb2;padding-top:10px}\n .legend-title{font-weight:700;letter-spacing:.1em;text-transform:uppercase;font-size:10.5px;color:#1b2a5e}\n .remarks{margin:5px 0 0;font-size:12.5px}\n .perf{margin:9px 0 3px}\n .perf-title{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;\n             color:#1b2a5e;font-weight:700;margin-bottom:8px}\n .perf-row{display:flex;align-items:center;gap:10px;margin:1.5px 0}\n .perf-label{width:44px;font-size:12px;font-weight:700;color:#334155}\n .perf-bars{flex:1;display:flex;flex-direction:column;gap:3px}\n .pb{background:#eef2f8;border-radius:999px;height:7px;overflow:hidden}\n .pb span{display:block;height:100%;border-radius:999px}\n .pb-mine{background:#1b2a5e}\n .pb-avg{background:#94a3b8}\n .perf-val{width:110px;text-align:right;font-size:12px;color:#334155}\n .perf-val em{color:#94a3b8;font-style:normal}\n .perf-key{font-size:10.5px;color:#64748b;margin-top:5px;display:flex;align-items:center;gap:6px}\n .k-mine,.k-avg{width:14px;height:7px;border-radius:999px;display:inline-block}\n .k-mine{background:#1b2a5e}.k-avg{background:#94a3b8;margin-left:10px}\n .co{margin-top:8px;font-size:12px}\n .co th{background:#1b2a5e;color:#f7efdd;font-size:10.5px;letter-spacing:.1em;text-transform:uppercase}\n .co td{padding:2px 9px}\n .co td:last-child{width:70px;background:#fbf7ee}\n .co td.grade{text-align:center;font-weight:700;color:#b4581c}\n .co th.grade-h{width:70px;text-align:center}\n .remark-box{margin-top:4px;font-size:11.5px}\n .remark-box span{font-weight:700;color:#1b2a5e;letter-spacing:.06em;text-transform:uppercase;font-size:10.5px}\n .dots{border-bottom:1px dotted #94a3b8;height:11px;margin-top:2px}\n h1{font-size:24px;margin:0;text-align:center;letter-spacing:.05em;color:#1b2a5e}\n .sub{text-align:center;font-size:12.5px;color:#555;margin-bottom:12px}\n table{width:100%;border-collapse:collapse;margin:10px 0}\n td,th{border:1px solid #ddcfb2;padding:5px 10px;text-align:left;font-size:12.5px}\n tbody td{background:rgba(255,253,247,.66)}\n .meta td{background:transparent}\n th{background:#1b2a5e;color:#f7efdd;letter-spacing:.06em}\n .right{text-align:right}\n .tot{font-weight:700}\n .tot td{background:rgba(240,229,206,.85)}\n .meta td{border:none;padding:5px 8px;font-size:13.5px}\n .sign-table{width:100%;border-collapse:collapse;margin-top:10px}\n .sign-table td{border:1px solid #ddcfb2;padding:5px;text-align:center;font-size:11.5px}\n .sign-table tr.space td{height:52px;vertical-align:bottom}\n .sign-table tr.space img{height:44px;max-width:100%;object-fit:contain}\n @media print{\n   body{padding:0;font-size:12px}\n   .wrap{border-width:1px;min-height:auto;height:auto;padding:14px 18px}\n   .sign-table{margin-top:16px}\n   @page{size:A4;margin:5mm}\n\n   /* logo watermark: table ke peeche saaf dikhe (print preview mein bhi) */\n   .watermark{opacity:.24;mix-blend-mode:multiply;z-index:0;\n              -webkit-print-color-adjust:exact;print-color-adjust:exact}\n   .watermark img{width:56%;max-width:390px;\n                  -webkit-print-color-adjust:exact;print-color-adjust:exact}\n\n   /* rows poori tarah transparent — logo kahin se na kate */\n   tbody td{background:transparent!important}\n   .tot td{background:rgba(240,229,206,.30)!important}\n   .who,.sumline,.legend{background:transparent!important}\n   .co td:last-child{background:transparent!important}\n   .sign-table td{background:transparent!important}\n   th,.co th{background:rgba(27,42,94,.88)!important;color:#f7efdd!important}\n\n   /* ek hi page par fit */\n   .letterhead{padding:2px 0 2px}\n   .lh-left img{height:64px}\n   .lh-left h1{font-size:26px}\n   .lh-rule{margin:6px 0 6px}\n   .sub-line{margin:-2px 0 6px;font-size:11px}\n   td,th{padding:3.5px 8px;font-size:11.5px}\n   .co td{padding:2px 8px;font-size:11.5px}\n   .remarks{font-size:11.5px;margin-top:3px}\n   .remark-box{margin-top:4px}\n   .dots{height:10px}\n   .sign-table tr.space td{height:34px}\n   .sign-table td{padding:3px;font-size:10.5px}\n   .co{margin-top:6px}\n   .co td{padding:1.8px 8px}\n   .legend{padding:4px 10px;margin:5px 0 2px}\n   .wrap{padding:12px 16px}\n   .remark-box{margin-top:2px}\n }\n</style></head><body>\n<div class="wrap">\n  <div class="watermark">\n    {% if logo %}<img src="{{ logo }}" alt="">{% endif %}\n  </div>\n\n  <div class="letterhead">\n    <div class="lh-left">\n      {% if logo %}<img src="{{ logo }}" alt="logo">{% endif %}\n      <h1>{{ school }}</h1>\n    </div>\n    <div class="lh-right">\n      <span>Session</span>\n      <strong>{{ exam.academic_year or \'—\' }}</strong>\n    </div>\n  </div>\n  <div class="lh-rule"></div>\n  <div class="sub-line">Report card · {{ exam_label(exam) }}</div>\n\n  <div class="who">\n    {% if student.photo %}<img class="pic" src="{{ student.photo }}" alt="">{% endif %}\n    <table class="meta">\n      <tr><td><strong>Name:</strong> {{ student.name }}</td>\n          <td class="right"><strong>Class:</strong> {{ student.class_name }}{% if student.section %} – {{ student.section }}{% endif %}</td></tr>\n      <tr><td><strong>Father\'s name:</strong> {{ student.father_name or \'—\' }}</td>\n          <td class="right"><strong>Mother\'s name:</strong> {{ student.mother_name or \'—\' }}</td></tr>\n      <tr><td><strong>Admission No:</strong> {{ student.admission_no }}</td>\n          <td class="right"><strong>Roll No:</strong> {{ student.roll_no }}</td></tr>\n      <tr><td><strong>Date of birth:</strong> {{ disp_date(student.dob) or \'—\' }}</td>\n          <td class="right"><strong>Attendance:</strong> {{ att_present }}/{{ att_total }} ({{ att_pct }}%)</td></tr>\n    </table>\n  </div>\n\n  <table>\n    <thead><tr><th>Subject</th><th class="right">Max</th><th class="right">Pass</th>\n               <th class="right">Theory</th><th class="right">Internal</th>\n               <th class="right">Total</th><th>Result</th></tr></thead>\n    <tbody>\n    {% set ns = namespace(theory=0, internal=0) %}\n    {% for s in subjects %}\n      <tr>\n        <td>{{ s.subject_name }} ({{ s.subject_code }})</td>\n        <td class="right">{{ fmt_num(s.max_marks) }}</td>\n        <td class="right">{{ fmt_num(s.pass_marks) }}</td>\n        <td class="right">{{ fmt_num(s.theory) if s.theory is not none else \'—\' }}</td>\n        <td class="right">{{ fmt_num(s.internal) if s.internal is not none else \'—\' }}</td>\n        <td class="right"><strong>{{ fmt_num(s.marks_obtained) }}</strong></td>\n        <td>{% if s.marks_obtained is not none and s.pass_marks is not none and s.marks_obtained < s.pass_marks %}Fail{% else %}Pass{% endif %}</td>\n      </tr>\n      {% if s.theory is not none %}{% set ns.theory = ns.theory + s.theory %}{% endif %}\n      {% if s.internal is not none %}{% set ns.internal = ns.internal + s.internal %}{% endif %}\n    {% endfor %}\n    <tr class="tot">\n      <td>Grand total</td>\n      <td class="right">{{ fmt_num(mine.total_max) }}</td>\n      <td></td>\n      <td class="right">{{ fmt_num(ns.theory) if ns.theory else \'—\' }}</td>\n      <td class="right">{{ fmt_num(ns.internal) if ns.internal else \'—\' }}</td>\n      <td class="right">{{ fmt_num(mine.obtained) }}</td>\n      <td>{{ mine.result }}</td>\n    </tr>\n    </tbody>\n  </table>\n\n  <table class="meta sumline">\n    <tr><td><strong>Percentage:</strong> {{ \'%.2f\'|format(mine.percentage) }}%</td>\n        <td class="right"><strong>Grade:</strong> {{ mine.grade }}</td></tr>\n    <tr><td><strong>Rank in class:</strong> {{ mine.rank }}</td>\n        <td class="right"><strong>Subjects failed:</strong> {{ mine.failed_subjects }}</td></tr>\n    <tr><td><strong>Result:</strong> {{ mine.result }}</td>\n        <td class="right"><strong>Result date:</strong> {{ issued_on }}</td></tr>\n  </table>\n\n  <div class="legend">\n    <span class="legend-title">Grading</span>\n    <span><b>A1</b> 91–100</span><span><b>A2</b> 81–90</span>\n    <span><b>B1</b> 71–80</span><span><b>B2</b> 61–70</span>\n    <span><b>C1</b> 51–60</span><span><b>C2</b> 41–50</span>\n    <span><b>D</b> 33–40</span><span><b>E</b> below 33</span>\n  </div>\n\n  <p class="remarks"><strong>Remarks:</strong> {{ mine.result }} — promoted to the next class.{% if mine.failed_subjects %} Compartment in {{ mine.failed_subjects }} subject(s).{% endif %}</p>\n  <p class="remarks"><strong>Date of issue:</strong> {{ issued_on }} &nbsp;·&nbsp; <strong>Position:</strong> {{ mine.rank }} in class</p>\n\n  <table class="co">\n    <thead><tr><th>Co-scholastic areas</th><th class="grade-h">Grade</th></tr></thead>\n    <tbody>\n      {% for area, grade in co_areas %}\n        <tr><td>{{ area|safe }}</td><td class="grade">{{ grade }}</td></tr>\n      {% endfor %}\n    </tbody>\n  </table>\n\n  <div class="remark-box">\n    <span>Class teacher\'s remark</span>\n    <div class="dots"></div><div class="dots"></div>\n  </div>\n\n\n\n  <table class="sign-table">\n    <tr class="space">\n      <td>{% if teacher_sign %}<img src="{{ teacher_sign }}" alt="signature">{% endif %}</td>\n      <td>{% if principal_sign %}<img src="{{ principal_sign }}" alt="signature">{% endif %}</td>\n      <td></td>\n    </tr>\n    <tr>\n      <td>Class teacher\'s signature</td>\n      <td>Principal\'s signature</td>\n      <td>Parent\'s signature</td>\n    </tr>\n  </table>\n</div>\n{% if not bulk %}\n<div class="no-print" style="max-width:820px;margin:14px auto;text-align:center">\n  <button onclick="window.print()"\n          style="padding:10px 22px;border:none;border-radius:10px;background:#1b2a5e;\n                 color:#fff;font-size:14px;font-weight:600;cursor:pointer">\n    Print / Save as PDF\n  </button>\n</div>\n<style>@media print{.no-print{display:none}}</style>\n{% if auto_print %}\n<script>\n  // print dialog ko load ke baad kholo (kuch browsers block karte hain, isliye try/catch)\n  window.addEventListener(\'load\', function () {\n    setTimeout(function () {\n      try { window.print(); } catch (e) { /* button se print ho sakta hai */ }\n    }, 300);\n  });\n</script>\n{% endif %}\n{% endif %}\n</body></html>\n',
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

ICON_PNG_B64 = ('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')

LOGO_PNG_B64 = ('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')

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

@app.after_request
def _gzip_response(resp):
    """Har HTML/CSS/JSON ko compress karke bhejo — page 5-8x chhota."""
    try:
        if (resp.status_code == 200
                and not resp.direct_passthrough
                and "Content-Disposition" not in resp.headers
                and "gzip" in (request.headers.get("Accept-Encoding") or "")
                and resp.mimetype in ("text/html", "text/css", "text/plain",
                                      "application/javascript",
                                      "text/javascript",
                                      "application/json", "image/svg+xml")):
            data = resp.get_data()
            if len(data) > 1024:
                packed = gzip.compress(data, 6)
                resp.set_data(packed)
                resp.headers["Content-Encoding"] = "gzip"
                resp.headers["Content-Length"] = str(len(packed))
                resp.headers["Vary"] = "Accept-Encoding"
    except Exception:                        # noqa: BLE001
        pass
    return resp


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


_SETTING_CACHE = {}
_SETTING_TTL = 120          # seconds


def setting(key, default=""):
    """Read a setting, with a short cache so pages stay fast."""
    import time as _t
    hit = _SETTING_CACHE.get(key)
    if hit and (_t.time() - hit[1]) < _SETTING_TTL:
        return hit[0]
    row = query("SELECT v FROM settings WHERE k=?", (key,), one=True)
    val = (row["v"] if row and row["v"] is not None else default)
    _SETTING_CACHE[key] = (val, _t.time())
    return val


def forget_setting(key=None):
    """Drop the cache after a setting is changed."""
    if key is None:
        _SETTING_CACHE.clear()
    else:
        _SETTING_CACHE.pop(key, None)


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
            forget_setting()
            flash("Names saved.", "ok")
        elif action == "principal_sign":
            data = save_photo(request.files.get("signature"))
            if data is None:
                flash("Choose a small signature image (under 1 MB).", "error")
            else:
                execute("INSERT OR REPLACE INTO settings (k, v)"
                        " VALUES ('principal_sign', ?)", (data,))
                forget_setting()
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
