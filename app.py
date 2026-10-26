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
import csv
import io
import os
import secrets
import sqlite3
import traceback
from datetime import datetime

from flask import (Flask, Response, abort, flash, g, redirect,
                   render_template, render_template_string, request, session,
                   url_for)
from jinja2 import DictLoader

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH") or os.path.join(BASE_DIR, "exam_manager.db")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "").strip()
SCHOOL_NAME = os.environ.get("SCHOOL_NAME", "Examination Management System")


# ==========================================================================
#  BUILT-IN ASSETS
#  Templates, stylesheet and icon live inside this file so that the app
#  is exactly ONE file to deploy - no templates/ or static/ folder that
#  can go missing during an upload.
# ==========================================================================
TEMPLATES = {
    'base.html':
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>{% block title %}Dashboard{% endblock %} · {{ school_name }}</title>\n<link rel="stylesheet" href="{{ url_for(\'static\', filename=\'style.css\') }}">\n<link rel="icon" href="{{ url_for(\'static\', filename=\'icon.png\') }}">\n</head>\n<body>\n<div class="shell">\n  <aside class="sidebar">\n    <div class="brand">\n      <div class="badge">EX</div>\n      <div class="brand-text">\n        <strong>Exam Manager</strong>\n        <span>{{ school_name }}</span>\n      </div>\n    </div>\n    <nav>\n      <a href="{{ url_for(\'dashboard\') }}" class="{{ \'active\' if request.endpoint == \'dashboard\' }}">Dashboard</a>\n      <a href="{{ url_for(\'students\') }}" class="{{ \'active\' if request.endpoint and request.endpoint.startswith(\'student\') }}">Students</a>\n      <a href="{{ url_for(\'exams\') }}" class="{{ \'active\' if request.endpoint and request.endpoint.startswith(\'exam\') }}">Exams</a>\n      <a href="{{ url_for(\'subjects\') }}" class="{{ \'active\' if request.endpoint and request.endpoint.startswith(\'subject\') }}">Subjects</a>\n      <a href="{{ url_for(\'schedule\') }}" class="{{ \'active\' if request.endpoint and request.endpoint.startswith(\'schedule\') }}">Exam schedule</a>\n      <a href="{{ url_for(\'marks\') }}" class="{{ \'active\' if request.endpoint == \'marks\' }}">Marks entry</a>\n      <a href="{{ url_for(\'results\') }}" class="{{ \'active\' if request.endpoint and request.endpoint.startswith(\'results\') }}">Results</a>\n    </nav>\n    <div class="sidebar-foot">\n      {% if auth_enabled %}<a href="{{ url_for(\'logout\') }}">Log out</a>{% endif %}\n      <span>SQLite · v3.0</span>\n    </div>\n  </aside>\n\n  <main>\n    {% if no_password %}\n    <div class="banner">\n      <strong>No password set.</strong> Anyone with this link can open student\n      data. Add an environment variable <code>APP_PASSWORD</code> on your host\n      to switch on the login screen.\n    </div>\n    {% endif %}\n    {% with messages = get_flashed_messages(with_categories=true) %}\n      {% for category, message in messages %}\n        <div class="flash {{ category }}">{{ message }}</div>\n      {% endfor %}\n    {% endwith %}\n    {% block content %}{% endblock %}\n  </main>\n</div>\n</body>\n</html>\n',
    'login.html':
        '{% extends "base.html" %}\n{% block title %}Log in{% endblock %}\n{% block content %}\n<div class="login-wrap">\n  <form class="card login" method="post">\n    <h1>Log in</h1>\n    <p class="muted">{{ school_name }} · examination module</p>\n    <label>Password\n      <input type="password" name="password" autofocus required>\n    </label>\n    <button class="btn primary" type="submit">Open dashboard</button>\n  </form>\n</div>\n{% endblock %}\n',
    'dashboard.html':
        '{% extends "base.html" %}\n{% block title %}Dashboard{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div>\n    <h1>Dashboard</h1>\n    <p>{{ today }} · a quick view of your examination data</p>\n  </div>\n</header>\n\n<div class="tiles">\n  <div class="tile"><i class="bar indigo"></i><b>{{ stats.students }}</b><span>Students</span></div>\n  <div class="tile"><i class="bar sky"></i><b>{{ stats.exams }}</b><span>Exams</span></div>\n  <div class="tile"><i class="bar green"></i><b>{{ stats.subjects }}</b><span>Subjects</span></div>\n  <div class="tile"><i class="bar amber"></i><b>{{ stats.papers }}</b><span>Papers scheduled</span></div>\n</div>\n\n<div class="two-col">\n  <section class="card">\n    <div class="card-head">\n      <h2>Recent admissions</h2>\n      <a class="btn ghost small" href="{{ url_for(\'students\') }}">All students</a>\n    </div>\n    <div class="table-wrap">\n      <table class="grid">\n        <thead><tr><th>Admission No</th><th>Name</th><th>Class</th><th>Admitted on</th></tr></thead>\n        <tbody>\n        {% for s in recent %}\n          <tr><td>{{ s.admission_no }}</td><td>{{ s.name }}</td>\n              <td>{{ s.class_name }}</td><td>{{ disp_date(s.admission_date) }}</td></tr>\n        {% else %}\n          <tr><td colspan="4" class="empty">No students yet.</td></tr>\n        {% endfor %}\n        </tbody>\n      </table>\n    </div>\n  </section>\n\n  <section class="card">\n    <div class="card-head">\n      <h2>Exams</h2>\n      <a class="btn ghost small" href="{{ url_for(\'exams\') }}">All exams</a>\n    </div>\n    <div class="table-wrap">\n      <table class="grid">\n        <thead><tr><th>Exam type</th><th>Class</th><th>Starts</th><th>Status</th></tr></thead>\n        <tbody>\n        {% for e in exams %}\n          <tr><td>{{ e.exam_type or e.exam_name }}</td><td>{{ e.class_name }}</td>\n              <td>{{ disp_date(e.start_date) }}</td><td>{{ e.status }}</td></tr>\n        {% else %}\n          <tr><td colspan="4" class="empty">No exams yet.</td></tr>\n        {% endfor %}\n        </tbody>\n      </table>\n    </div>\n  </section>\n</div>\n{% endblock %}\n',
    'students.html':
        '{% extends "base.html" %}\n{% block title %}Students{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div>\n    <h1>Students</h1>\n    <p>Admission details and student master data</p>\n  </div>\n  <div class="actions">\n    <a class="btn ghost" href="{{ url_for(\'students_csv\') }}">Export CSV</a>\n  </div>\n</header>\n\n<section class="card">\n  <details {{ \'open\' if editing }}>\n    <summary>{{ \'Edit student\' if editing else \'Add a student\' }}</summary>\n    <form class="form-grid" method="post" action="{{ url_for(\'student_save\') }}">\n      <input type="hidden" name="id" value="{{ editing.id if editing else \'\' }}">\n      <label>Admission No *<input name="admission_no" required value="{{ editing.admission_no if editing else \'\' }}"></label>\n      <label>Roll No *<input name="roll_no" required value="{{ editing.roll_no if editing else \'\' }}"></label>\n      <label>Student name *<input name="name" required value="{{ editing.name if editing else \'\' }}"></label>\n      <label>Class *<input name="class_name" required value="{{ editing.class_name if editing else \'\' }}"></label>\n      <label>Section\n        <select name="section">\n          <option value=""></option>\n          {% for s in sections %}<option {{ \'selected\' if editing and editing.section == s }}>{{ s }}</option>{% endfor %}\n        </select>\n      </label>\n      <label>Date of birth<input name="dob" placeholder="dd/mm/yyyy" value="{{ disp_date(editing.dob) if editing else \'\' }}"></label>\n      <label>Gender\n        <select name="gender">\n          <option value=""></option>\n          {% for g in genders %}<option {{ \'selected\' if editing and editing.gender == g }}>{{ g }}</option>{% endfor %}\n        </select>\n      </label>\n      <label>Date of admission *<input name="admission_date" placeholder="dd/mm/yyyy" required value="{{ disp_date(editing.admission_date) if editing else \'\' }}"></label>\n      <label>Father\'s name<input name="father_name" value="{{ editing.father_name if editing else \'\' }}"></label>\n      <label>Mother\'s name<input name="mother_name" value="{{ editing.mother_name if editing else \'\' }}"></label>\n      <label>Phone<input name="phone" value="{{ editing.phone if editing else \'\' }}"></label>\n      <label>Email<input name="email" value="{{ editing.email if editing else \'\' }}"></label>\n      <label class="span-2">Address<input name="address" value="{{ editing.address if editing else \'\' }}"></label>\n      <label>Status\n        <select name="status">\n          {% for st in statuses %}<option {{ \'selected\' if (editing and editing.status == st) or (not editing and st == \'Active\') }}>{{ st }}</option>{% endfor %}\n        </select>\n      </label>\n      <div class="form-actions">\n        <button class="btn primary" type="submit">{{ \'Update student\' if editing else \'Save student\' }}</button>\n        {% if editing %}<a class="btn ghost" href="{{ url_for(\'students\') }}">Cancel</a>{% endif %}\n      </div>\n    </form>\n  </details>\n</section>\n\n<section class="card">\n  <div class="card-head">\n    <h2>All students <span class="pill">{{ students|length }}</span></h2>\n    <form class="search" method="get">\n      <input name="q" value="{{ q }}" placeholder="Search name, roll no, admission no, class">\n      <button class="btn ghost" type="submit">Search</button>\n      {% if q %}<a class="btn ghost" href="{{ url_for(\'students\') }}">Reset</a>{% endif %}\n    </form>\n  </div>\n  <div class="table-wrap">\n    <table class="grid">\n      <thead>\n        <tr><th>Admission No</th><th>Roll</th><th>Name</th><th>Class</th><th>Section</th>\n            <th>Admitted</th><th>DOB</th><th>Phone</th><th>Status</th><th></th></tr>\n      </thead>\n      <tbody>\n      {% for s in students %}\n        <tr>\n          <td>{{ s.admission_no }}</td><td>{{ s.roll_no }}</td><td>{{ s.name }}</td>\n          <td>{{ s.class_name }}</td><td>{{ s.section or \'\' }}</td>\n          <td>{{ disp_date(s.admission_date) }}</td><td>{{ disp_date(s.dob) }}</td>\n          <td>{{ s.phone or \'\' }}</td><td>{{ s.status }}</td>\n          <td class="row-actions">\n            <a class="btn ghost small" href="{{ url_for(\'students\', edit=s.id) }}">Edit</a>\n            <form method="post" action="{{ url_for(\'student_delete\', sid=s.id) }}"\n                  onsubmit="return confirm(\'Delete {{ s.name }} and every mark linked to them?\')">\n              <button class="btn danger small" type="submit">Delete</button>\n            </form>\n          </td>\n        </tr>\n      {% else %}\n        <tr><td colspan="10" class="empty">No students found.</td></tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n{% endblock %}\n',
    'exams.html':
        '{% extends "base.html" %}\n{% block title %}Exams{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div>\n    <h1>Exams</h1>\n    <p>The exam type is the exam\'s name — no separate exam name is needed</p>\n  </div>\n</header>\n\n<section class="card">\n  <details {{ \'open\' if editing }}>\n    <summary>{{ \'Edit exam\' if editing else \'Create an exam\' }}</summary>\n    <form class="form-grid" method="post" action="{{ url_for(\'exam_save\') }}">\n      <input type="hidden" name="id" value="{{ editing.id if editing else \'\' }}">\n      <label>Exam type *\n        <input name="exam_type" list="exam-types" required\n               value="{{ (editing.exam_type or editing.exam_name) if editing else \'\' }}">\n        <datalist id="exam-types">\n          {% for t in exam_types %}<option value="{{ t }}">{% endfor %}\n        </datalist>\n      </label>\n      <label>Academic year<input name="academic_year" value="{{ editing.academic_year if editing else \'2026-27\' }}"></label>\n      <label>Class<input name="class_name" value="{{ editing.class_name if editing else \'\' }}"></label>\n      <label>Start date<input name="start_date" placeholder="dd/mm/yyyy" value="{{ disp_date(editing.start_date) if editing else \'\' }}"></label>\n      <label>End date<input name="end_date" placeholder="dd/mm/yyyy" value="{{ disp_date(editing.end_date) if editing else \'\' }}"></label>\n      <label>Status\n        <select name="status">\n          {% for st in statuses %}<option {{ \'selected\' if editing and editing.status == st or (not editing and st == \'Scheduled\') }}>{{ st }}</option>{% endfor %}\n        </select>\n      </label>\n      <label class="span-2">Remarks<input name="remarks" value="{{ editing.remarks if editing else \'\' }}"></label>\n      <div class="form-actions">\n        <button class="btn primary" type="submit">{{ \'Update exam\' if editing else \'Save exam\' }}</button>\n        {% if editing %}<a class="btn ghost" href="{{ url_for(\'exams\') }}">Cancel</a>{% endif %}\n      </div>\n    </form>\n  </details>\n</section>\n\n<section class="card">\n  <div class="card-head"><h2>All exams <span class="pill">{{ exams|length }}</span></h2></div>\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr><th>Exam type</th><th>Academic year</th><th>Class</th><th>Start</th>\n                 <th>End</th><th>Status</th><th>Remarks</th><th></th></tr></thead>\n      <tbody>\n      {% for e in exams %}\n        <tr>\n          <td>{{ e.exam_type or e.exam_name }}</td><td>{{ e.academic_year }}</td>\n          <td>{{ e.class_name }}</td><td>{{ disp_date(e.start_date) }}</td>\n          <td>{{ disp_date(e.end_date) }}</td><td>{{ e.status }}</td>\n          <td class="muted">{{ e.remarks or \'\' }}</td>\n          <td class="row-actions">\n            <a class="btn ghost small" href="{{ url_for(\'exams\', edit=e.id) }}">Edit</a>\n            <form method="post" action="{{ url_for(\'exam_delete\', eid=e.id) }}"\n                  onsubmit="return confirm(\'Delete this exam with its schedule and marks?\')">\n              <button class="btn danger small" type="submit">Delete</button>\n            </form>\n          </td>\n        </tr>\n      {% else %}\n        <tr><td colspan="8" class="empty">No exams yet.</td></tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n{% endblock %}\n',
    'subjects.html':
        '{% extends "base.html" %}\n{% block title %}Subjects{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Subjects</h1><p>Subject master used by the exam schedule</p></div>\n  <div class="actions">\n    <form method="post" action="{{ url_for(\'subject_defaults\') }}">\n      <button class="btn ghost" type="submit">Load defaults</button>\n    </form>\n  </div>\n</header>\n\n<section class="card">\n  <details {{ \'open\' if editing }}>\n    <summary>{{ \'Edit subject\' if editing else \'Add a subject\' }}</summary>\n    <form class="form-grid" method="post" action="{{ url_for(\'subject_save\') }}">\n      <input type="hidden" name="id" value="{{ editing.id if editing else \'\' }}">\n      <label>Subject code *<input name="subject_code" required value="{{ editing.subject_code if editing else \'\' }}"></label>\n      <label>Subject name *<input name="subject_name" required value="{{ editing.subject_name if editing else \'\' }}"></label>\n      <label>Class (blank = all)<input name="class_name" value="{{ editing.class_name if editing else \'\' }}"></label>\n      <div class="form-actions">\n        <button class="btn primary" type="submit">{{ \'Update subject\' if editing else \'Save subject\' }}</button>\n        {% if editing %}<a class="btn ghost" href="{{ url_for(\'subjects\') }}">Cancel</a>{% endif %}\n      </div>\n    </form>\n  </details>\n</section>\n\n<section class="card">\n  <div class="card-head"><h2>All subjects <span class="pill">{{ subjects|length }}</span></h2></div>\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr><th>Code</th><th>Subject name</th><th>Class</th><th></th></tr></thead>\n      <tbody>\n      {% for s in subjects %}\n        <tr>\n          <td>{{ s.subject_code }}</td><td>{{ s.subject_name }}</td><td>{{ s.class_name or \'\' }}</td>\n          <td class="row-actions">\n            <a class="btn ghost small" href="{{ url_for(\'subjects\', edit=s.id) }}">Edit</a>\n            <form method="post" action="{{ url_for(\'subject_delete\', sid=s.id) }}"\n                  onsubmit="return confirm(\'Delete {{ s.subject_name }}?\')">\n              <button class="btn danger small" type="submit">Delete</button>\n            </form>\n          </td>\n        </tr>\n      {% else %}\n        <tr><td colspan="4" class="empty">No subjects yet — use “Load defaults”.</td></tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n{% endblock %}\n',
    'schedule.html':
        '{% extends "base.html" %}\n{% block title %}Exam schedule{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Exam schedule</h1><p>One paper per subject — date, time, hall and marks</p></div>\n</header>\n\n<section class="card">\n  <details open>\n    <summary>Add a paper</summary>\n    {% if not exams or not subjects %}\n      <p class="muted">Create at least one exam and one subject first.</p>\n    {% else %}\n    <form class="form-grid" method="post" action="{{ url_for(\'schedule_save\') }}">\n      <label>Exam *\n        <select name="exam_id" required>\n          <option value="">— choose —</option>\n          {% for e in exams %}<option value="{{ e.id }}">{{ exam_label(e) }}</option>{% endfor %}\n        </select>\n      </label>\n      <label>Subject *\n        <select name="subject_id" required>\n          <option value="">— choose —</option>\n          {% for s in subjects %}<option value="{{ s.id }}">{{ s.subject_name }} ({{ s.subject_code }})</option>{% endfor %}\n        </select>\n      </label>\n      <label>Exam date<input name="exam_date" placeholder="dd/mm/yyyy"></label>\n      <label>Start time<input name="start_time" placeholder="09:00"></label>\n      <label>Duration (minutes)<input name="duration" value="180"></label>\n      <label>Room / hall<input name="room"></label>\n      <label>Invigilator<input name="invigilator"></label>\n      <label>Max marks<input name="max_marks" value="100"></label>\n      <label>Pass marks<input name="pass_marks" value="33"></label>\n      <div class="form-actions"><button class="btn primary" type="submit">Add paper</button></div>\n    </form>\n    {% endif %}\n  </details>\n</section>\n\n<section class="card">\n  <div class="card-head"><h2>Scheduled papers <span class="pill">{{ papers|length }}</span></h2></div>\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr><th>Exam</th><th>Subject</th><th>Date</th><th>Time</th><th>Duration</th>\n                 <th>Room</th><th>Invigilator</th><th>Max</th><th>Pass</th><th></th></tr></thead>\n      <tbody>\n      {% for p in papers %}\n        <tr>\n          <td>{{ exam_label(p) }}</td><td>{{ p.subject_name }}</td>\n          <td>{{ disp_date(p.exam_date) }}</td><td>{{ p.start_time }}</td>\n          <td>{{ p.duration }}</td><td>{{ p.room or \'\' }}</td>\n          <td>{{ p.invigilator or \'\' }}</td>\n          <td class="num">{{ fmt_num(p.max_marks) }}</td>\n          <td class="num">{{ fmt_num(p.pass_marks) }}</td>\n          <td class="row-actions">\n            <form method="post" action="{{ url_for(\'schedule_delete\', pid=p.id) }}"\n                  onsubmit="return confirm(\'Remove this paper and its marks?\')">\n              <button class="btn danger small" type="submit">Delete</button>\n            </form>\n          </td>\n        </tr>\n      {% else %}\n        <tr><td colspan="10" class="empty">No papers scheduled yet.</td></tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n{% endblock %}\n',
    'marks.html':
        '{% extends "base.html" %}\n{% block title %}Marks entry{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Marks entry</h1><p>Pick an exam and a subject, then fill the marks</p></div>\n</header>\n\n<section class="card">\n  <form class="form-grid" method="get">\n    <label>Exam\n      <select name="exam_id" onchange="this.form.submit()">\n        <option value="">— choose —</option>\n        {% for e in exams %}\n          <option value="{{ e.id }}" {{ \'selected\' if exam_id == e.id|string }}>{{ exam_label(e) }}</option>\n        {% endfor %}\n      </select>\n    </label>\n    <label>Subject\n      <select name="subject_id" onchange="this.form.submit()">\n        <option value="">— choose —</option>\n        {% for s in subjects %}\n          <option value="{{ s.id }}" {{ \'selected\' if subject_id == s.id|string }}>{{ s.subject_name }} ({{ s.subject_code }})</option>\n        {% endfor %}\n      </select>\n    </label>\n    <noscript><div class="form-actions"><button class="btn ghost" type="submit">Load sheet</button></div></noscript>\n  </form>\n</section>\n\n{% if info %}<p class="info">{{ info }}</p>{% endif %}\n\n{% if sheet %}\n<section class="card">\n  <form method="post">\n    <input type="hidden" name="exam_id" value="{{ exam_id }}">\n    <input type="hidden" name="subject_id" value="{{ subject_id }}">\n    <div class="table-wrap">\n      <table class="grid">\n        <thead><tr><th>Roll</th><th>Name</th><th>Marks (max {{ fmt_num(ctx.max_marks) }})</th>\n                   <th>Result</th><th>Remarks</th></tr></thead>\n        <tbody>\n        {% for row in sheet %}\n          {% set m = row.mark %}\n          <tr>\n            <td>{{ row.student.roll_no }}</td>\n            <td>{{ row.student.name }}</td>\n            <td class="num">\n              <input class="mark-input" type="number" step="0.5" min="0"\n                     max="{{ ctx.max_marks }}" name="marks_{{ row.student.id }}"\n                     value="{{ fmt_num(m.marks_obtained) if m and m.marks_obtained is not none else \'\' }}">\n            </td>\n            <td>\n              {% if m and m.marks_obtained is not none %}\n                {% if m.marks_obtained >= ctx.pass_marks %}\n                  <span class="tag ok">Pass</span>\n                {% else %}\n                  <span class="tag bad">Fail</span>\n                {% endif %}\n              {% else %}<span class="muted">—</span>{% endif %}\n            </td>\n            <td><input name="remarks_{{ row.student.id }}" value="{{ m.remarks if m and m.remarks else \'\' }}"></td>\n          </tr>\n        {% endfor %}\n        </tbody>\n      </table>\n    </div>\n    <div class="form-actions">\n      <button class="btn primary" type="submit">Save all marks</button>\n    </div>\n  </form>\n</section>\n{% endif %}\n{% endblock %}\n',
    'results.html':
        '{% extends "base.html" %}\n{% block title %}Results{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Results</h1><p>Totals, percentage, grade, rank and pass / fail</p></div>\n  {% if results %}\n  <div class="actions">\n    <a class="btn ghost" href="{{ url_for(\'results_csv\', exam_id=exam_id, class_name=class_name) }}">Export CSV</a>\n  </div>\n  {% endif %}\n</header>\n\n<section class="card">\n  <form class="form-grid" method="get">\n    <label>Exam\n      <select name="exam_id" onchange="this.form.submit()">\n        <option value="">— choose —</option>\n        {% for e in exams %}\n          <option value="{{ e.id }}" {{ \'selected\' if exam_id == e.id|string }}>{{ exam_label(e) }}</option>\n        {% endfor %}\n      </select>\n    </label>\n    <label>Class\n      <input name="class_name" value="{{ class_name }}" placeholder="e.g. 8">\n    </label>\n    <div class="form-actions"><button class="btn primary" type="submit">Generate</button></div>\n  </form>\n</section>\n\n{% if info %}<p class="info">{{ info }}</p>{% endif %}\n\n{% if results %}\n<section class="card">\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr><th>Rank</th><th>Roll</th><th>Admission No</th><th>Name</th>\n                 <th>Obtained</th><th>Max</th><th>%</th><th>Grade</th>\n                 <th>Failed</th><th>Result</th></tr></thead>\n      <tbody>\n      {% for r in results %}\n        <tr>\n          <td>{{ r.rank }}</td><td>{{ r.roll_no }}</td><td>{{ r.admission_no }}</td>\n          <td>{{ r.name }}</td><td class="num">{{ fmt_num(r.obtained) }}</td>\n          <td class="num">{{ fmt_num(r.total_max) }}</td>\n          <td class="num">{{ \'%.2f\'|format(r.percentage) }}</td>\n          <td>{{ r.grade }}</td><td class="num">{{ r.failed_subjects }}</td>\n          <td>{% if r.result == \'Pass\' %}<span class="tag ok">Pass</span>\n              {% else %}<span class="tag bad">Fail</span>{% endif %}</td>\n        </tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n{% endif %}\n{% endblock %}\n',
}

STYLE_CSS = '/* Exam Manager - web edition */\n:root {\n  --bg: #f4f6fb;\n  --white: #ffffff;\n  --ink: #0f172a;\n  --muted: #64748b;\n  --line: #e2e8f0;\n  --soft: #f8fafc;\n  --accent: #4f46e5;\n  --accent-dark: #4338ca;\n  --accent-soft: #eef2ff;\n  --danger: #dc2626;\n  --danger-soft: #fee2e2;\n  --ok: #059669;\n  --ok-soft: #d1fae5;\n  --sidebar: #0f172a;\n}\n* { box-sizing: border-box; }\nbody {\n  margin: 0;\n  background: var(--bg);\n  color: var(--ink);\n  font: 15px/1.5 "Segoe UI", Inter, "Helvetica Neue", system-ui, Arial, sans-serif;\n}\na { color: var(--accent); text-decoration: none; }\na:hover { text-decoration: underline; }\nh1 { font-size: 24px; margin: 0; }\nh2 { font-size: 15px; margin: 0; }\n.muted { color: var(--muted); }\n.num { text-align: right; font-variant-numeric: tabular-nums; }\n\n/* ---------- shell ---------- */\n.shell { display: flex; min-height: 100vh; }\n.sidebar {\n  width: 244px; flex: 0 0 244px; background: var(--sidebar); color: #fff;\n  display: flex; flex-direction: column; padding: 22px 0;\n}\n.brand { display: flex; gap: 12px; align-items: center; padding: 0 20px 18px; }\n.badge {\n  width: 38px; height: 38px; border-radius: 10px; background: var(--accent);\n  display: grid; place-items: center; font-weight: 700; letter-spacing: .5px;\n}\n.brand-text strong { display: block; font-size: 15px; }\n.brand-text span { display: block; font-size: 11px; color: #7c8ba1; }\n.sidebar nav { display: flex; flex-direction: column; padding: 6px 10px; gap: 2px; }\n.sidebar nav a {\n  color: #94a3b8; padding: 10px 14px; border-radius: 8px; font-size: 14px;\n}\n.sidebar nav a:hover { background: #1e293b; color: #e2e8f0; text-decoration: none; }\n.sidebar nav a.active { background: #1e293b; color: #fff; box-shadow: inset 3px 0 0 var(--accent); }\n.sidebar-foot {\n  margin-top: auto; padding: 16px 20px 0; display: flex; flex-direction: column;\n  gap: 6px; font-size: 12px; color: #475569;\n}\n.sidebar-foot a { color: #94a3b8; }\n\nmain { flex: 1; padding: 26px 30px 40px; min-width: 0; }\n\n/* ---------- headers, cards ---------- */\n.page-head {\n  display: flex; justify-content: space-between; align-items: flex-start;\n  gap: 16px; margin-bottom: 18px; flex-wrap: wrap;\n}\n.page-head p { margin: 4px 0 0; color: var(--muted); font-size: 13px; }\n.actions { display: flex; gap: 8px; }\n.card {\n  background: var(--white); border: 1px solid var(--line); border-radius: 12px;\n  padding: 18px; margin-bottom: 16px;\n}\n.card-head {\n  display: flex; justify-content: space-between; align-items: center;\n  gap: 12px; margin-bottom: 12px; flex-wrap: wrap;\n}\n.pill {\n  background: var(--accent-soft); color: var(--accent-dark); border-radius: 999px;\n  padding: 1px 9px; font-size: 12px; font-weight: 600; margin-left: 6px;\n}\n\n/* ---------- stat tiles ---------- */\n.tiles {\n  display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));\n  gap: 14px; margin-bottom: 18px;\n}\n.tile {\n  background: var(--white); border: 1px solid var(--line); border-radius: 12px;\n  padding: 16px 18px;\n}\n.tile .bar { display: block; width: 34px; height: 3px; border-radius: 2px; margin-bottom: 10px; }\n.bar.indigo { background: var(--accent); }\n.bar.sky { background: #0ea5e9; }\n.bar.green { background: #10b981; }\n.bar.amber { background: #f59e0b; }\n.tile b { display: block; font-size: 26px; line-height: 1.1; }\n.tile span { color: var(--muted); font-size: 12px; }\n\n.two-col { display: grid; grid-template-columns: 3fr 2fr; gap: 16px; }\n@media (max-width: 1000px) { .two-col { grid-template-columns: 1fr; } }\n\n/* ---------- forms ---------- */\n.form-grid {\n  display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));\n  gap: 12px 16px; margin-top: 12px;\n}\n.form-grid label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }\n.form-grid .span-2 { grid-column: span 2; }\ninput, select {\n  font: inherit; font-size: 14px; color: var(--ink); background: var(--white);\n  border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px;\n}\ninput:focus, select:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }\n.form-actions { display: flex; align-items: end; gap: 8px; }\ndetails summary {\n  cursor: pointer; font-weight: 600; font-size: 14px; color: var(--accent-dark);\n  list-style: none;\n}\ndetails summary::-webkit-details-marker { display: none; }\ndetails summary::before { content: "+ "; font-weight: 700; }\ndetails[open] summary::before { content: "- "; font-weight: 700; }\n\n/* ---------- buttons ---------- */\n.btn {\n  display: inline-block; font: inherit; font-size: 14px; cursor: pointer;\n  border-radius: 8px; padding: 8px 14px; border: 1px solid var(--line);\n  background: var(--white); color: var(--ink); text-decoration: none;\n}\n.btn:hover { background: var(--soft); text-decoration: none; }\n.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }\n.btn.primary:hover { background: var(--accent-dark); }\n.btn.ghost { background: var(--white); }\n.btn.danger { color: var(--danger); border-color: #fecaca; }\n.btn.danger:hover { background: var(--danger-soft); }\n.btn.small { padding: 4px 9px; font-size: 12px; }\n\n/* ---------- tables ---------- */\n.table-wrap { overflow-x: auto; }\ntable.grid { width: 100%; border-collapse: collapse; font-size: 14px; }\ntable.grid th {\n  text-align: left; font-size: 11px; letter-spacing: .04em; text-transform: uppercase;\n  color: var(--muted); background: var(--soft); padding: 9px 10px;\n  border-bottom: 1px solid var(--line); white-space: nowrap;\n}\ntable.grid td { padding: 9px 10px; border-bottom: 1px solid var(--line); vertical-align: middle; }\ntable.grid tbody tr:nth-child(even) { background: #fcfdff; }\ntable.grid tbody tr:hover { background: var(--accent-soft); }\ntable.grid td.empty { text-align: center; color: var(--muted); padding: 26px; }\n.row-actions { display: flex; gap: 6px; justify-content: flex-end; }\n.row-actions form { display: inline; }\n.mark-input { width: 96px; }\n\n/* ---------- bits ---------- */\n.tag { display: inline-block; border-radius: 999px; padding: 2px 9px; font-size: 12px; font-weight: 600; }\n.tag.ok { background: var(--ok-soft); color: var(--ok); }\n.tag.bad { background: var(--danger-soft); color: var(--danger); }\n.flash {\n  border-radius: 10px; padding: 11px 14px; margin-bottom: 14px; font-size: 14px;\n  border: 1px solid var(--line); background: var(--white);\n}\n.flash.ok { background: var(--ok-soft); border-color: #a7f3d0; color: #065f46; }\n.flash.error { background: var(--danger-soft); border-color: #fecaca; color: #991b1b; }\n.banner {\n  background: #fff7ed; border: 1px solid #fed7aa; color: #9a3412;\n  border-radius: 10px; padding: 11px 14px; margin-bottom: 14px; font-size: 13px;\n}\n.info { color: var(--muted); font-size: 13px; margin: 0 0 12px 2px; }\n.search { display: flex; gap: 8px; align-items: center; }\n.search input { min-width: 260px; }\n.login-wrap { display: grid; place-items: center; min-height: 70vh; }\n.card.login { width: 340px; display: flex; flex-direction: column; gap: 12px; }\n.card.login h1 { font-size: 22px; }\n.card.login label { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--muted); }\n\n/* ---------- small screens ---------- */\n@media (max-width: 820px) {\n  .shell { flex-direction: column; }\n  .sidebar { width: 100%; flex: none; padding: 14px 0; }\n  .sidebar nav { flex-direction: row; overflow-x: auto; gap: 6px; }\n  .sidebar nav a { white-space: nowrap; }\n  .sidebar-foot { flex-direction: row; gap: 14px; padding: 10px 20px 0; }\n  main { padding: 18px 14px 30px; }\n  .form-grid { grid-template-columns: 1fr; }\n  .form-grid .span-2 { grid-column: auto; }\n}\n'

ICON_PNG_B64 = ('iVBORw0KGgoAAAANSUhEUgAAAQAAAAEACAYAAABccqhmAAAHdUlEQVR4nO3dvY5lRxmF4RrkIbdEBCkESNwBkZMJbEsEyAkSIfdA5MAJJL4FIgsRGgkCJoCIq3AMFiDZGUl7aKKWWz3dffY++6e+qvU8oT14qo3Xu+uc/pnWAAAAAACAOb3ofYAz/OzVP257n4Ex/fH1D6beyFQfnKFzllnCMPwHYfT0NnIMhjy40VPVaDEY5rBGz2hGiEH5Axo+o6scgrIHM3xmUzEE5Q5k+MyuUgjKHMTwSVMhBN/pfYDWjJ9MFf6771qgCv8CoIJet4FuNwDjh2/12kOXABg/vK3HLk69dhg+LHPWS4LTbgDGD8udtZdTAmD8sN4Zuzk8AMYP1zt6P4cGwPhhuyN3dFgAjB/2c9SeDgmA8cP+jtjV7gEwfjjO3vvaNQDGD8fbc2clvhkI6GO3AHj6w3n22tsuATB+ON8eu9scAOOHfrbuz3sAEGxTADz9ob8tO7w6AMYPdVy7Ry8BINhVAfD0h3qu2aUbAARbHQBPf6hr7T7dACDYqgB4+kN9a3bqBgDBFgfA0x/GsXSvbgAQTAAg2KIAuP7DeJbs1g0AggkABLsYANd/GNel/boBQDABgGDPBsD1H8b33I7dACCYAEAwAYBgAgDBBACCPRkAnwGAeTy1ZzcACCYAEEwAIJgAQDABgGACAMEEAIIJAAQTAAj2Tu8DpPjxT77bfvPp93ofYxj/+feb9qtf/qv3MabnBgDBBACCCQAEEwAIJgAQTAAgmABAMAGAYAIAwQQAggkABBMACCYAEEwAIJgAQDABgGACAMEEAIIJAAQTAAjmh4JO6ubmtn304Ze9j0FxbgAQTAAgmABAMAGAYAIAwQQAggkABBMACCYAEEwAIJgAQDABgGACAMEEAIIJAAQTAAgmABBMACCYAEAwAYBgfijopF6+fNE+/8v3ex9jtZ+//8/25k3vU+RwA4BgAgDBBACCCQAEEwAIJgAQTAAgmABAMAGAYAIAwQQAggkABBMACCYAEEwAIJgAQDABgGACAMEEAIIJAATzQ0EndXNz2z768Mvex6A4NwAIJgAQTAAgmABAMAGAYAIAwQQAgj35dQDf3Pz3zHNM7803/zv99/T/IZe4AUAwAYBgAgDBBACCCQAEEwAIJgAQTAAgmABAMAGAYAIAwQQAggkABBMACCYAEEwAIJg/GGRSL1++aH/66w97H2Ozz373VfvDZ1/1Psa03AAgmABAMAGAYAIAwQQAggkABBMACCYAEEwAIJgAQDABgGACAMEEAIIJAAQTAAgmABDMDwSBe/7+698v/rU//e0vDjzJOQSAaGsGf+l/O2IQBIBIW4Z/6Z85UggEgChHDP+p32OEELx46m988N4Xt2ceBI50xvCfUiUEf/7bj97au88CML2e46/w+z/HSwCmVWl4VV8WuAEwpUrjv6/auQSA6VQb2UOVzicATKXSuJ5T5ZwCwDSqjGqpCucVAKZQYUzX6H1uAYBgAsDwej9Fn/P1q48v/pqe5xcAhjbC+CtHQADgAA9HvyQCPQgAw6r69H9q7Jci0OPjEQA40devPi51GxAAhjTa03/przv74xIA2MnaJ3uFm4AAMJyKT/9rxvzu608e/etnfnwCABvtOf6zCQBsMPL4WxMAiCYADKXS6/8jn/5nfZwCQJS93nkf/ep/RwCIseZr85f8c9aoOP7WBIAQe31t/kzjb+2ZADz2M8RhRNd+bf7WX99anfE/tWc3AKZ2abRbv3R3dALAtHqPu8rT/zkCwJT2vN6PfPW/RACYzp5v8M08/tYEgAltGeD9wc8+/tYuBMBnAhjV1gjMNP7nduwGwFDW/OGaZw5y79/rrD9EVACYWtWnchUXA+BlAKM7OgKVI3Npv24ARDhqpJXHv4QAMJxrXx/vPdajxn/W6//WFgbAywBmsddoR3jyL9mtGwBD2vKU3DreI8d/5tO/NQEg1AhP8DMsDoCXAVSz9Wl5TQRGefov3asbANHWDHrGW8OqALgFUM0eT80lwz56/D2e/q25ATCBPSPwcOjvvv5kqPGvddUT/YP3vrjd+yCwRaUfF75Wr6d/a24ATKLnU3SL3ue+KgDeC6Ci3mNaa+/zXrNLNwCmMkoEqpzz6gC4BVBVlXE95YjzXbvHTTcAEaCqqhGoNP7WWntnz4NAJXdjq/AZgqpB2vwegFsA1fUe35G//9b97TZeXxvACM68DRwdnj0evrs+vUWAURwZgjNuHHvdvL0HQKQj3h/o/VLjGru/fncLYGRrgtBr8Hu+73bIG3giAMfY+033Q74S0GcGYH9H7OqwLwUWAdjPUXs69HsBRAC2O3JHh38zkAjA9Y7ezynfDSgCsN4Zuznt24FFAJY7ay9dRunThPC4sx+UXX4giNsAvK3HLrr9RCARgG/12kOJEXpJQKreD8ISPxOw978E6KHCf/fdD/CQ2wCzqzD8O2UO8pAQMJtKw79T7kAPCQGjqzj8O2UP9pAQMJrKw79T/oCPEQOqGmH09w112MeIAb2NNvr7hj34Y8SAs4w8+vum+CAuEQauNcvQAQAAAIBQ/wc5QDYHbNuaaAAAAABJRU5ErkJggg==')

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
CREATE TABLE IF NOT EXISTS students (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
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


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
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
def require_login():
    if not APP_PASSWORD:
        return None
    if request.endpoint in ("login", "static", "healthz"):
        return None
    if session.get("auth"):
        return None
    return redirect(url_for("login", next=request.path))


@app.context_processor
def inject_globals():
    return {
        "school_name": SCHOOL_NAME,
        "auth_enabled": bool(APP_PASSWORD),
        "no_password": not APP_PASSWORD,
        "today": datetime.now().strftime("%d/%m/%Y"),
    }


@app.route("/login", methods=["GET", "POST"])
def login():
    if not APP_PASSWORD:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        if request.form.get("password", "") == APP_PASSWORD:
            session["auth"] = True
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Wrong password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# --------------------------------------------------------------------------
#  dashboard
# --------------------------------------------------------------------------
@app.route("/")
def dashboard():
    stats = {
        "students": query("SELECT COUNT(*) c FROM students", one=True)["c"],
        "exams": query("SELECT COUNT(*) c FROM exams", one=True)["c"],
        "subjects": query("SELECT COUNT(*) c FROM subjects", one=True)["c"],
        "papers": query("SELECT COUNT(*) c FROM exam_schedule", one=True)["c"],
    }
    recent = query("SELECT * FROM students ORDER BY id DESC LIMIT 10")
    exams = query("SELECT * FROM exams ORDER BY id DESC LIMIT 10")
    return render_template("dashboard.html", stats=stats, recent=recent,
                           exams=exams, disp_date=disp_date)


# --------------------------------------------------------------------------
#  students
# --------------------------------------------------------------------------
@app.route("/students")
def students():
    term = request.args.get("q", "").strip()
    if term:
        like = f"%{term}%"
        rows = query(
            "SELECT * FROM students WHERE name LIKE ? OR roll_no LIKE ?"
            " OR admission_no LIKE ? OR class_name LIKE ?"
            " ORDER BY class_name, CAST(roll_no AS INTEGER), roll_no",
            (like, like, like, like))
    else:
        rows = query("SELECT * FROM students ORDER BY class_name,"
                     " CAST(roll_no AS INTEGER), roll_no")
    classes = [r["class_name"] for r in query(
        "SELECT DISTINCT class_name FROM students WHERE class_name<>''"
        " ORDER BY class_name")]
    edit_id = request.args.get("edit", type=int)
    editing = query("SELECT * FROM students WHERE id=?", (edit_id,),
                    one=True) if edit_id else None
    return render_template("students.html", students=rows, q=term,
                           classes=classes, disp_date=disp_date,
                           genders=GENDERS, sections=SECTIONS,
                           statuses=STUDENT_STATUS, editing=editing)


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

    dup = query("SELECT id FROM students WHERE admission_no=? AND id<>?",
                (adm, int(sid) if sid else 0), one=True)
    if dup:
        flash(f"Admission No {adm} already exists.", "error")
        return redirect(url_for("students"))

    if sid:
        execute("""UPDATE students SET admission_no=?, roll_no=?, name=?,
                   class_name=?, section=?, dob=?, gender=?, father_name=?,
                   mother_name=?, phone=?, email=?, address=?, admission_date=?,
                   status=? WHERE id=?""", values + (int(sid),))
        flash(f"Student '{name}' updated.", "ok")
    else:
        execute("""INSERT INTO students (admission_no, roll_no, name, class_name,
                   section, dob, gender, father_name, mother_name, phone, email,
                   address, admission_date, status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", values)
        flash(f"Student '{name}' added.", "ok")
    return redirect(url_for("students"))


@app.route("/students/<int:sid>/delete", methods=["POST"])
def student_delete(sid):
    row = query("SELECT name FROM students WHERE id=?", (sid,), one=True)
    execute("DELETE FROM students WHERE id=?", (sid,))
    flash(f"Student '{row['name'] if row else sid}' deleted.", "ok")
    return redirect(url_for("students"))


@app.route("/students.csv")
def students_csv():
    rows = query("SELECT * FROM students ORDER BY class_name,"
                 " CAST(roll_no AS INTEGER), roll_no")
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
    rows = query("SELECT * FROM exams ORDER BY id DESC")
    edit_id = request.args.get("edit", type=int)
    editing = query("SELECT * FROM exams WHERE id=?", (edit_id,),
                    one=True) if edit_id else None
    return render_template("exams.html", exams=rows, disp_date=disp_date,
                           exam_types=EXAM_TYPES, statuses=EXAM_STATUS,
                           editing=editing)


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
    dup = query("""SELECT id FROM exams WHERE exam_type=?
                   AND IFNULL(academic_year,'')=? AND IFNULL(class_name,'')=?
                   AND id<>?""", (etype, year, cls, int(eid) if eid else 0),
                one=True)
    if dup:
        flash(f"'{etype}' already exists for class {cls or '-'} "
              f"in {year or '-'}.", "error")
        return redirect(url_for("exams"))

    if eid:
        execute("""UPDATE exams SET exam_name=?, exam_type=?, academic_year=?,
                   class_name=?, start_date=?, end_date=?, status=?, remarks=?
                   WHERE id=?""",
                (etype, etype, year, cls, sd, ed,
                 f.get("status") or "Scheduled", f.get("remarks", "").strip(),
                 int(eid)))
        flash(f"Exam '{etype}' updated.", "ok")
    else:
        execute("""INSERT INTO exams (exam_name, exam_type, academic_year,
                   class_name, start_date, end_date, status, remarks)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (etype, etype, year, cls, sd, ed,
                 f.get("status") or "Scheduled", f.get("remarks", "").strip()))
        flash(f"Exam '{etype}' saved.", "ok")
    return redirect(url_for("exams"))


@app.route("/exams/<int:eid>/delete", methods=["POST"])
def exam_delete(eid):
    row = query("SELECT exam_type FROM exams WHERE id=?", (eid,), one=True)
    execute("DELETE FROM exams WHERE id=?", (eid,))
    flash(f"Exam '{row['exam_type'] if row else eid}' deleted.", "ok")
    return redirect(url_for("exams"))


# --------------------------------------------------------------------------
#  subjects
# --------------------------------------------------------------------------
@app.route("/subjects")
def subjects():
    rows = query("SELECT * FROM subjects ORDER BY subject_code")
    edit_id = request.args.get("edit", type=int)
    editing = query("SELECT * FROM subjects WHERE id=?", (edit_id,),
                    one=True) if edit_id else None
    return render_template("subjects.html", subjects=rows, editing=editing)


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
    dup = query("SELECT id FROM subjects WHERE subject_code=? AND id<>?",
                (code, int(sid) if sid else 0), one=True)
    if dup:
        flash(f"Subject code {code} already exists.", "error")
        return redirect(url_for("subjects"))
    if sid:
        execute("UPDATE subjects SET subject_code=?, subject_name=?,"
                " class_name=? WHERE id=?", (code, name, cls, int(sid)))
        flash(f"Subject '{name}' updated.", "ok")
    else:
        execute("INSERT INTO subjects (subject_code, subject_name, class_name)"
                " VALUES (?,?,?)", (code, name, cls))
        flash(f"Subject '{name}' added.", "ok")
    return redirect(url_for("subjects"))


@app.route("/subjects/<int:sid>/delete", methods=["POST"])
def subject_delete(sid):
    row = query("SELECT subject_name FROM subjects WHERE id=?", (sid,), one=True)
    execute("DELETE FROM subjects WHERE id=?", (sid,))
    flash(f"Subject '{row['subject_name'] if row else sid}' deleted.", "ok")
    return redirect(url_for("subjects"))


@app.route("/subjects/defaults", methods=["POST"])
def subject_defaults():
    defaults = [("ENG", "English"), ("HIN", "Hindi"), ("MAT", "Mathematics"),
                ("SCI", "Science"), ("SST", "Social Science"),
                ("CS", "Computer Science")]
    added = 0
    for code, name in defaults:
        if not query("SELECT id FROM subjects WHERE subject_code=?", (code,),
                     one=True):
            execute("INSERT INTO subjects (subject_code, subject_name)"
                    " VALUES (?,?)", (code, name))
            added += 1
    flash(f"{added} default subject(s) added.", "ok")
    return redirect(url_for("subjects"))


# --------------------------------------------------------------------------
#  schedule
# --------------------------------------------------------------------------
@app.route("/schedule")
def schedule():
    exams_rows = query("SELECT * FROM exams ORDER BY id DESC")
    subjects_rows = query("SELECT * FROM subjects ORDER BY subject_code")
    rows = query("""SELECT sc.*, e.exam_name, e.exam_type, e.academic_year,
                           e.class_name, s.subject_name
                    FROM exam_schedule sc
                    JOIN exams e ON e.id = sc.exam_id
                    JOIN subjects s ON s.id = sc.subject_id
                    ORDER BY e.id DESC, sc.exam_date, sc.start_time""")
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

    execute("""INSERT INTO exam_schedule (exam_id, subject_id, exam_date,
               start_time, duration, room, invigilator, max_marks, pass_marks)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (exam_id, subject_id, ed, st, int(duration),
             f.get("room", "").strip(), f.get("invigilator", "").strip(),
             mx, ps))
    flash("Paper added to the schedule.", "ok")
    return redirect(url_for("schedule"))


@app.route("/schedule/<int:pid>/delete", methods=["POST"])
def schedule_delete(pid):
    execute("DELETE FROM exam_schedule WHERE id=?", (pid,))
    flash("Paper removed.", "ok")
    return redirect(url_for("schedule"))


# --------------------------------------------------------------------------
#  marks
# --------------------------------------------------------------------------
@app.route("/marks", methods=["GET", "POST"])
def marks():
    exams_rows = query("SELECT * FROM exams ORDER BY id DESC")
    subjects_rows = query("SELECT * FROM subjects ORDER BY subject_code")
    exam_id = request.values.get("exam_id") or ""
    subject_id = request.values.get("subject_id") or ""

    sheet, info, ctx = [], "", None
    if exam_id and subject_id:
        exam_id, subject_id = int(exam_id), int(subject_id)
        sched = query("SELECT * FROM exam_schedule WHERE exam_id=? AND"
                      " subject_id=?", (exam_id, subject_id), one=True)
        exam = query("SELECT * FROM exams WHERE id=?", (exam_id,), one=True)

        if request.method == "POST" and sched:
            saved = 0
            max_marks = float(sched["max_marks"] or 100)
            for st in query("SELECT id FROM students WHERE class_name=?",
                            ((exam["class_name"] or "").strip(),)):
                raw = request.form.get(f"marks_{st['id']}", "").strip()
                remark = request.form.get(f"remarks_{st['id']}", "").strip()
                if raw == "":
                    value = None
                else:
                    value = to_float(raw)
                    if value is None or value < 0 or value > max_marks:
                        continue
                existing = query("SELECT id FROM marks WHERE exam_id=? AND"
                                 " student_id=? AND subject_id=?",
                                 (exam_id, st["id"], subject_id), one=True)
                if existing:
                    execute("UPDATE marks SET marks_obtained=?, remarks=?,"
                            " updated_at=CURRENT_TIMESTAMP WHERE id=?",
                            (value, remark, existing["id"]))
                else:
                    execute("""INSERT INTO marks (exam_id, student_id,
                               subject_id, marks_obtained, remarks)
                               VALUES (?,?,?,?,?)""",
                            (exam_id, st["id"], subject_id, value, remark))
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
            ctx = {"max_marks": max_marks, "pass_marks": pass_marks}
            rows = query("SELECT * FROM students WHERE status='Active'"
                         " AND class_name=? ORDER BY CAST(roll_no AS INTEGER),"
                         " roll_no", ((exam["class_name"] or "").strip(),))
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
    exams_rows = query("SELECT * FROM exams ORDER BY id DESC")
    exam_id = request.args.get("exam_id") or ""
    class_name = (request.args.get("class_name") or "").strip()
    rows, info, exam = [], "", None

    if exam_id:
        exam = query("SELECT * FROM exams WHERE id=?", (int(exam_id),), one=True)
        class_name = class_name or (exam["class_name"] or "").strip()
        if class_name:
            rows = compute_results(int(exam_id), class_name)
            if rows:
                passed = sum(1 for r in rows if r["result"] == "Pass")
                info = (f"{len(rows)} student(s) · Pass {passed} · "
                        f"Fail {len(rows) - passed} · Topper: {rows[0]['name']} "
                        f"({rows[0]['percentage']:.2f}%)")
            else:
                info = "No marks found for this exam and class."

    classes = [r["class_name"] for r in query(
        "SELECT DISTINCT class_name FROM students WHERE class_name<>''"
        " ORDER BY class_name")]
    return render_template("results.html", exams=exams_rows, results=rows,
                           exam_id=str(exam_id), class_name=class_name,
                           classes=classes, info=info, exam_label=exam_label,
                           fmt_num=fmt_num)


@app.route("/results.csv")
def results_csv():
    exam_id = request.args.get("exam_id", type=int)
    class_name = (request.args.get("class_name") or "").strip()
    if not exam_id:
        flash("Pick an exam first.", "error")
        return redirect(url_for("results"))
    exam = query("SELECT * FROM exams WHERE id=?", (exam_id,), one=True)
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
#  diagnostics: never show a bare "Internal Server Error"
# --------------------------------------------------------------------------
REQUIRED_TEMPLATES = ("base.html", "dashboard.html", "students.html",
                      "exams.html", "subjects.html", "schedule.html",
                      "marks.html", "results.html", "login.html")

ERROR_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Exam Manager - error</title>
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

    db_ok, db_detail = True, DB_PATH
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("CREATE TABLE IF NOT EXISTS _probe (x INTEGER)")
        conn.execute("DROP TABLE _probe")
        conn.commit()
        conn.close()
    except Exception as exc:            # noqa: BLE001 - report anything
        db_ok, db_detail = False, f"{DB_PATH} - {exc}"
    checks.append(("database writable", db_ok, db_detail))

    checks.append(("login password set", bool(APP_PASSWORD),
                   "yes" if APP_PASSWORD else
                   "no - anyone with the link can open the data"))
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


@app.route("/healthz")
def healthz():
    """Always 200 - Render's health check - plus a full diagnostic report."""
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
