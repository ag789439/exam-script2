"""
==========================================================================
 EXAM MANAGER  -  web edition  (Flask + PostgreSQL)
--------------------------------------------------------------------------
 The same examination module as before, but every record - students,
 exams, subjects, schedule, marks AND logins - now lives in ONE
 PostgreSQL database, the one DATABASE_URL points at.

 Pages
   Dashboard   counts, recent admissions, exams
   Students    admission + student master data
   Exams       exam master (the exam type is the exam's name)
   Subjects    subject master
   Schedule    one paper per subject with max / pass marks
   Marks       per-student entry, with absent (AB) and exempt (EX)
   Results     total, percentage, grade, rank, pass/fail + CSV export
   My results  what a student sees after logging in
   Accounts    /admin/students and /admin/teachers (admin only)

 Logins (see auth_system.py)
   Admin    ADMIN_USERNAME / ADMIN_PASSWORD from the environment
   Teacher  created by an admin on /admin/teachers
   Student  admission number + the password an admin set on
            /admin/students

 Environment variables
   DATABASE_URL    PostgreSQL connection string (Render sets this itself
                   when the Postgres service is attached)
   SECRET_KEY      session signing key - set it in production
   SCHOOL_NAME     name shown in the header
   ADMIN_USERNAME  admin login name (default: admin)
   ADMIN_PASSWORD  admin password - set it in production

 Run locally
   pip install -r requirements.txt
   export DATABASE_URL=postgresql://user:pass@localhost:5432/exampro
   python app.py            ->  http://127.0.0.1:5000
==========================================================================
"""

import base64
import csv
import io
import os
import secrets
import traceback
from contextlib import contextmanager
from datetime import datetime

from flask import (Flask, Response, abort, flash, g, redirect,
                   render_template, render_template_string, request, session,
                   url_for)
from jinja2 import DictLoader

import db as pgdb

APP_NAME = os.environ.get("APP_NAME", "ExamSetu")
SCHOOL_NAME = os.environ.get("SCHOOL_NAME", "Examination Management System")


# ==========================================================================
#  BUILT-IN ASSETS
#  Templates, stylesheet and icon live inside this file so that the app
#  is exactly ONE file to deploy - no templates/ or static/ folder that
#  can go missing during an upload.
# ==========================================================================
TEMPLATES = {
    'base.html':
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>{% block title %}Dashboard{% endblock %} · {{ app_name }}</title>\n<meta name="description" content="{{ app_name }} is a school examination management system: student records, exam schedules, marks entry, and results with grades and ranks.">\n<meta name="keywords" content="ExamSetu, exam management system, school exam software, marks entry software, exam result software, report card, student examination management, India">\n<meta name="application-name" content="{{ app_name }}">\n<meta name="apple-mobile-web-app-title" content="{{ app_name }}">\n<meta name="theme-color" content="#0f172a">\n<meta name="robots" content="index, follow">\n<link rel="canonical" href="{{ request.url_root }}">\n<meta property="og:site_name" content="{{ app_name }}">\n<meta property="og:type" content="website">\n<meta property="og:title" content="{% block og_title %}{{ app_name }} — school examination management{% endblock %}">\n<meta property="og:description" content="Students, exams, subjects, schedules, marks entry and results in one place.">\n<meta property="og:url" content="{{ request.url_root }}">\n<meta name="twitter:card" content="summary">\n<meta name="twitter:title" content="{{ app_name }}">\n<meta name="twitter:description" content="School examination management: students, exams, marks and results.">\n<link rel="stylesheet" href="{{ url_for(\'static\', filename=\'style.css\') }}">\n<link rel="icon" href="{{ url_for(\'static\', filename=\'icon.png\') }}">\n<script type="application/ld+json">\n{\n  "@context": "https://schema.org",\n  "@type": "SoftwareApplication",\n  "name": "{{ app_name }}",\n  "alternateName": "ExamSetu examination management",\n  "applicationCategory": "BusinessApplication",\n  "operatingSystem": "Web",\n  "url": "{{ request.url_root }}",\n  "description": "School examination management system for student records, exam schedules, marks entry and results.",\n  "offers": { "@type": "Offer", "price": "0", "priceCurrency": "INR" }\n}\n</script>\n</head>\n<body>\n<div class="shell">\n  <aside class="sidebar">\n    <div class="brand">\n      <div class="badge">ES</div>\n      <div class="brand-text">\n        <strong>{{ app_name }}</strong>\n        <span>{{ school_name }}</span>\n      </div>\n    </div>\n    <nav>\n      <a href="{{ url_for(\'dashboard\') }}" class="{{ \'active\' if request.endpoint == \'dashboard\' }}">Dashboard</a>\n      <a href="{{ url_for(\'students\') }}" class="{{ \'active\' if request.endpoint and request.endpoint.startswith(\'student\') }}">Students</a>\n      <a href="{{ url_for(\'exams\') }}" class="{{ \'active\' if request.endpoint and request.endpoint.startswith(\'exam\') }}">Exams</a>\n      <a href="{{ url_for(\'subjects\') }}" class="{{ \'active\' if request.endpoint and request.endpoint.startswith(\'subject\') }}">Subjects</a>\n      <a href="{{ url_for(\'schedule\') }}" class="{{ \'active\' if request.endpoint and request.endpoint.startswith(\'schedule\') }}">Exam schedule</a>\n      {% if session.get(\'role\') == \'admin\' %}\n      <a href="/admin/students">Student passwords</a>\n      <a href="/admin/teachers">Teacher accounts</a>\n      {% endif %}\n      <a href="{{ url_for(\'marks\') }}" class="{{ \'active\' if request.endpoint == \'marks\' }}">Marks entry</a>\n      <a href="{{ url_for(\'results\') }}" class="{{ \'active\' if request.endpoint and request.endpoint.startswith(\'results\') }}">Results</a>\n    </nav>\n    <div class="sidebar-foot">\n      {% if auth_enabled %}<a href="{{ url_for(\'auth.logout\') }}">Log out</a>{% endif %}\n      <span>PostgreSQL · v4.2</span>\n    </div>\n  </aside>\n\n  <main>\n    {% if no_password %}\n    <div class="banner">\n      <strong>No password set.</strong> Anyone with this link can open student\n      data. Add an environment variable <code>APP_PASSWORD</code> on your host\n      to switch on the login screen.\n    </div>\n    {% endif %}\n    {% with messages = get_flashed_messages(with_categories=true) %}\n      {% for category, message in messages %}\n        <div class="flash {{ category }}">{{ message }}</div>\n      {% endfor %}\n    {% endwith %}\n    {% block content %}{% endblock %}\n  </main>\n</div>\n</body>\n</html>\n',
    'login.html':
        '{% extends "base.html" %}\n{% block title %}Log in{% endblock %}\n{% block content %}\n<div class="login-wrap">\n  <form class="card login" method="post">\n    <span class="hero-eyebrow">{{ app_name }}</span>\n    <h1>School examination management</h1>\n    <p class="muted">Students, exams, marks and results — in one place.</p>\n    <label>Password\n      <input type="password" name="password" autofocus required>\n    </label>\n    <button class="btn primary" type="submit">Open dashboard</button>\n    <p class="muted small">{{ school_name }}</p>\n  </form>\n</div>\n{% endblock %}\n',
    'dashboard.html':
        '{% extends "base.html" %}\n{% block title %}Dashboard{% endblock %}\n{% block content %}\n<section class="hero">\n  <div class="hero-text">\n    <span class="hero-eyebrow">{{ app_name }} · {{ today }}</span>\n    <h1>Welcome back</h1>\n    <p>Your exams, marks and results at a glance.</p>\n    <div class="hero-actions">\n      <a class="btn primary" href="{{ url_for(\'marks\') }}">Enter marks</a>\n      <a class="btn ghost" href="{{ url_for(\'schedule\') }}">Exam schedule</a>\n      <a class="btn ghost" href="{{ url_for(\'results\') }}">Results</a>\n    </div>\n  </div>\n  <div class="hero-ring">\n    <svg viewBox="0 0 120 120" class="donut" role="img"\n         aria-label="{{ progress.pct }} percent of marks entered">\n      <circle class="donut-track" cx="60" cy="60" r="52"></circle>\n      <circle class="donut-value" cx="60" cy="60" r="52"\n              stroke-dasharray="{{ progress.dash }} 326.7"\n              transform="rotate(-90 60 60)"></circle>\n      <text class="donut-num" x="60" y="58" text-anchor="middle">{{ progress.pct }}%</text>\n      <text class="donut-cap" x="60" y="77" text-anchor="middle">marks in</text>\n    </svg>\n    <p class="muted small">{{ progress.entered }} of {{ progress.expected }} entries</p>\n  </div>\n</section>\n\n<div class="tiles">\n  <div class="tile"><i class="bar indigo"></i><b>{{ stats.students }}</b><span>Students</span>\n    <span class="cap">{{ stats.classes }} class{{ \'\' if stats.classes == 1 else \'es\' }}</span></div>\n  <div class="tile"><i class="bar sky"></i><b>{{ stats.exams }}</b><span>Exams</span>\n    <span class="cap">{{ stats.papers }} papers scheduled</span></div>\n  <div class="tile"><i class="bar green"></i><b>{{ stats.marks }}</b><span>Marks entered</span>\n    <span class="cap">{{ stats.absent }} absent · {{ stats.exempt }} exempt</span></div>\n  <div class="tile"><i class="bar amber"></i><b>{{ stats.subjects }}</b><span>Subjects</span>\n    <span class="cap">across all classes</span></div>\n</div>\n\n<div class="two-col">\n  <section class="card">\n    <div class="card-head">\n      <h2>Marks entered by class</h2>\n      <a class="btn ghost small" href="{{ url_for(\'marks\') }}">Open marks entry</a>\n    </div>\n    <div class="class-progress">\n      {% for c in classes %}\n        <div class="progress-row">\n          <span class="progress-label">Class {{ c.class_name }}</span>\n          <span class="progress-track"><span class="progress-fill"\n                style="width: {{ c.pct }}%"></span></span>\n          <span class="progress-num">{{ c.entered }}/{{ c.expected }}</span>\n        </div>\n      {% else %}\n        <p class="muted">No students or papers yet — start with students and\n           one exam.</p>\n      {% endfor %}\n    </div>\n  </section>\n\n  <section class="card">\n    <div class="card-head"><h2>Quick actions</h2></div>\n    <div class="quick-actions">\n      <a class="quick" href="{{ url_for(\'students\') }}"><b>Students</b>\n         <span>Admissions and records</span></a>\n      <a class="quick" href="{{ url_for(\'exams\') }}"><b>Exams</b>\n         <span>Create and manage</span></a>\n      <a class="quick" href="{{ url_for(\'schedule\') }}"><b>Schedule</b>\n         <span>Papers, halls, maxima</span></a>\n      <a class="quick" href="{{ url_for(\'results\') }}"><b>Results</b>\n         <span>Grades, ranks, CSV</span></a>\n    </div>\n  </section>\n</div>\n\n<div class="two-col">\n  <section class="card">\n    <div class="card-head">\n      <h2>Recent admissions</h2>\n      <a class="btn ghost small" href="{{ url_for(\'students\') }}">All students</a>\n    </div>\n    <div class="table-wrap">\n      <table class="grid">\n        <thead><tr><th>Admission No</th><th>Name</th><th>Class</th><th>Admitted on</th></tr></thead>\n        <tbody>\n        {% for s in recent %}\n          <tr><td>{{ s.admission_no }}</td><td>{{ s.name }}</td>\n              <td>{{ s.class_name }}</td><td>{{ disp_date(s.admission_date) }}</td></tr>\n        {% else %}\n          <tr><td colspan="4" class="empty">No students yet.</td></tr>\n        {% endfor %}\n        </tbody>\n      </table>\n    </div>\n  </section>\n\n  <section class="card">\n    <div class="card-head">\n      <h2>Exams</h2>\n      <a class="btn ghost small" href="{{ url_for(\'exams\') }}">All exams</a>\n    </div>\n    <div class="table-wrap">\n      <table class="grid">\n        <thead><tr><th>Exam type</th><th>Class</th><th>Starts</th><th>Status</th></tr></thead>\n        <tbody>\n        {% for e in exams %}\n          <tr><td>{{ e.exam_type or e.exam_name }}</td><td>{{ e.class_name }}</td>\n              <td>{{ disp_date(e.start_date) }}</td>\n              <td><span class="chip {{ \'chip-ok\' if e.status in (\'Completed\', \'Result Declared\') else \'chip-live\' if e.status == \'Ongoing\' else \'chip-idle\' }}">{{ e.status }}</span></td></tr>\n        {% else %}\n          <tr><td colspan="4" class="empty">No exams yet.</td></tr>\n        {% endfor %}\n        </tbody>\n      </table>\n    </div>\n  </section>\n</div>\n{% endblock %}\n',
    'students.html':
        '{% extends "base.html" %}\n{% block title %}Students{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div>\n    <h1>Students</h1>\n    <p>Admission details and student master data</p>\n  </div>\n  <div class="actions">\n    <a class="btn ghost" href="{{ url_for(\'students_csv\') }}">Export CSV</a>\n  </div>\n</header>\n\n<section class="card">\n  <details {{ \'open\' if editing }}>\n    <summary>{{ \'Edit student\' if editing else \'Add a student\' }}</summary>\n    <form class="form-grid" method="post" action="{{ url_for(\'student_save\') }}">\n      <input type="hidden" name="id" value="{{ editing.id if editing else \'\' }}">\n      <label>Admission No *<input name="admission_no" required value="{{ editing.admission_no if editing else \'\' }}"></label>\n      <label>Roll No *<input name="roll_no" required value="{{ editing.roll_no if editing else \'\' }}"></label>\n      <label>Student name *<input name="name" required value="{{ editing.name if editing else \'\' }}"></label>\n      <label>Class *<input name="class_name" required value="{{ editing.class_name if editing else \'\' }}"></label>\n      <label>Section\n        <select name="section">\n          <option value=""></option>\n          {% for s in sections %}<option {{ \'selected\' if editing and editing.section == s }}>{{ s }}</option>{% endfor %}\n        </select>\n      </label>\n      <label>Date of birth<input name="dob" placeholder="dd/mm/yyyy" value="{{ disp_date(editing.dob) if editing else \'\' }}"></label>\n      <label>Gender\n        <select name="gender">\n          <option value=""></option>\n          {% for g in genders %}<option {{ \'selected\' if editing and editing.gender == g }}>{{ g }}</option>{% endfor %}\n        </select>\n      </label>\n      <label>Date of admission *<input name="admission_date" placeholder="dd/mm/yyyy" required value="{{ disp_date(editing.admission_date) if editing else \'\' }}"></label>\n      <label>Father\'s name<input name="father_name" value="{{ editing.father_name if editing else \'\' }}"></label>\n      <label>Mother\'s name<input name="mother_name" value="{{ editing.mother_name if editing else \'\' }}"></label>\n      <label>Phone<input name="phone" value="{{ editing.phone if editing else \'\' }}"></label>\n      <label>Email<input name="email" value="{{ editing.email if editing else \'\' }}"></label>\n      <label class="span-2">Address<input name="address" value="{{ editing.address if editing else \'\' }}"></label>\n      <label>Status\n        <select name="status">\n          {% for st in statuses %}<option {{ \'selected\' if (editing and editing.status == st) or (not editing and st == \'Active\') }}>{{ st }}</option>{% endfor %}\n        </select>\n      </label>\n      <div class="form-actions">\n        <button class="btn primary" type="submit">{{ \'Update student\' if editing else \'Save student\' }}</button>\n        {% if editing %}<a class="btn ghost" href="{{ url_for(\'students\') }}">Cancel</a>{% endif %}\n      </div>\n    </form>\n  </details>\n</section>\n\n<section class="card">\n  <div class="card-head">\n    <h2>All students <span class="pill">{{ students|length }}</span></h2>\n    <form class="search" method="get">\n      <input name="q" value="{{ q }}" placeholder="Search name, roll no, admission no, class">\n      <button class="btn ghost" type="submit">Search</button>\n      {% if q %}<a class="btn ghost" href="{{ url_for(\'students\') }}">Reset</a>{% endif %}\n    </form>\n  </div>\n  <div class="table-wrap">\n    <table class="grid">\n      <thead>\n        <tr><th>Admission No</th><th>Roll</th><th>Name</th><th>Class</th><th>Section</th>\n            <th>Admitted</th><th>DOB</th><th>Phone</th><th>Status</th><th></th></tr>\n      </thead>\n      <tbody>\n      {% for s in students %}\n        <tr>\n          <td>{{ s.admission_no }}</td><td>{{ s.roll_no }}</td><td>{{ s.name }}</td>\n          <td>{{ s.class_name }}</td><td>{{ s.section or \'\' }}</td>\n          <td>{{ disp_date(s.admission_date) }}</td><td>{{ disp_date(s.dob) }}</td>\n          <td>{{ s.phone or \'\' }}</td><td>{{ s.status }}</td>\n          <td class="row-actions">\n            <a class="btn ghost small" href="{{ url_for(\'students\', edit=s.id) }}">Edit</a>\n            <form method="post" action="{{ url_for(\'student_delete\', sid=s.id) }}"\n                  onsubmit="return confirm(\'Delete {{ s.name }} and every mark linked to them?\')">\n              <button class="btn danger small" type="submit">Delete</button>\n            </form>\n          </td>\n        </tr>\n      {% else %}\n        <tr><td colspan="10" class="empty">No students found.</td></tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n{% endblock %}\n',
    'exams.html':
        '{% extends "base.html" %}\n{% block title %}Exams{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div>\n    <h1>Exams</h1>\n    <p>The exam type is the exam\'s name — no separate exam name is needed</p>\n  </div>\n</header>\n\n<section class="card">\n  <details {{ \'open\' if editing }}>\n    <summary>{{ \'Edit exam\' if editing else \'Create an exam\' }}</summary>\n    <form class="form-grid" method="post" action="{{ url_for(\'exam_save\') }}">\n      <input type="hidden" name="id" value="{{ editing.id if editing else \'\' }}">\n      <label>Exam type *\n        <input name="exam_type" list="exam-types" required\n               value="{{ (editing.exam_type or editing.exam_name) if editing else \'\' }}">\n        <datalist id="exam-types">\n          {% for t in exam_types %}<option value="{{ t }}">{% endfor %}\n        </datalist>\n      </label>\n      <label>Academic year<input name="academic_year" value="{{ editing.academic_year if editing else \'2026-27\' }}"></label>\n      <label>Class<input name="class_name" value="{{ editing.class_name if editing else \'\' }}"></label>\n      <label>Start date<input name="start_date" placeholder="dd/mm/yyyy" value="{{ disp_date(editing.start_date) if editing else \'\' }}"></label>\n      <label>End date<input name="end_date" placeholder="dd/mm/yyyy" value="{{ disp_date(editing.end_date) if editing else \'\' }}"></label>\n      <label>Status\n        <select name="status">\n          {% for st in statuses %}<option {{ \'selected\' if editing and editing.status == st or (not editing and st == \'Scheduled\') }}>{{ st }}</option>{% endfor %}\n        </select>\n      </label>\n      <label class="span-2">Remarks<input name="remarks" value="{{ editing.remarks if editing else \'\' }}"></label>\n      <div class="form-actions">\n        <button class="btn primary" type="submit">{{ \'Update exam\' if editing else \'Save exam\' }}</button>\n        {% if editing %}<a class="btn ghost" href="{{ url_for(\'exams\') }}">Cancel</a>{% endif %}\n      </div>\n    </form>\n  </details>\n</section>\n\n<section class="card">\n  <div class="card-head"><h2>All exams <span class="pill">{{ exams|length }}</span></h2></div>\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr><th>Exam type</th><th>Academic year</th><th>Class</th><th>Start</th>\n                 <th>End</th><th>Status</th><th>Remarks</th><th></th></tr></thead>\n      <tbody>\n      {% for e in exams %}\n        <tr>\n          <td>{{ e.exam_type or e.exam_name }}</td><td>{{ e.academic_year }}</td>\n          <td>{{ e.class_name }}</td><td>{{ disp_date(e.start_date) }}</td>\n          <td>{{ disp_date(e.end_date) }}</td><td>{{ e.status }}</td>\n          <td class="muted">{{ e.remarks or \'\' }}</td>\n          <td class="row-actions">\n            <a class="btn ghost small" href="{{ url_for(\'exams\', edit=e.id) }}">Edit</a>\n            <form method="post" action="{{ url_for(\'exam_delete\', eid=e.id) }}"\n                  onsubmit="return confirm(\'Delete this exam with its schedule and marks?\')">\n              <button class="btn danger small" type="submit">Delete</button>\n            </form>\n          </td>\n        </tr>\n      {% else %}\n        <tr><td colspan="8" class="empty">No exams yet.</td></tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n{% endblock %}\n',
    'subjects.html':
        '{% extends "base.html" %}\n{% block title %}Subjects{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Subjects</h1><p>Subject master used by the exam schedule</p></div>\n  <div class="actions">\n    <form method="post" action="{{ url_for(\'subject_defaults\') }}">\n      <button class="btn ghost" type="submit">Load defaults</button>\n    </form>\n  </div>\n</header>\n\n<section class="card">\n  <details {{ \'open\' if editing }}>\n    <summary>{{ \'Edit subject\' if editing else \'Add a subject\' }}</summary>\n    <form class="form-grid" method="post" action="{{ url_for(\'subject_save\') }}">\n      <input type="hidden" name="id" value="{{ editing.id if editing else \'\' }}">\n      <label>Subject code *<input name="subject_code" required value="{{ editing.subject_code if editing else \'\' }}"></label>\n      <label>Subject name *<input name="subject_name" required value="{{ editing.subject_name if editing else \'\' }}"></label>\n      <label>Class (blank = all)<input name="class_name" value="{{ editing.class_name if editing else \'\' }}"></label>\n      <div class="form-actions">\n        <button class="btn primary" type="submit">{{ \'Update subject\' if editing else \'Save subject\' }}</button>\n        {% if editing %}<a class="btn ghost" href="{{ url_for(\'subjects\') }}">Cancel</a>{% endif %}\n      </div>\n    </form>\n  </details>\n</section>\n\n<section class="card">\n  <div class="card-head"><h2>All subjects <span class="pill">{{ subjects|length }}</span></h2></div>\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr><th>Code</th><th>Subject name</th><th>Class</th><th></th></tr></thead>\n      <tbody>\n      {% for s in subjects %}\n        <tr>\n          <td>{{ s.subject_code }}</td><td>{{ s.subject_name }}</td><td>{{ s.class_name or \'\' }}</td>\n          <td class="row-actions">\n            <a class="btn ghost small" href="{{ url_for(\'subjects\', edit=s.id) }}">Edit</a>\n            <form method="post" action="{{ url_for(\'subject_delete\', sid=s.id) }}"\n                  onsubmit="return confirm(\'Delete {{ s.subject_name }}?\')">\n              <button class="btn danger small" type="submit">Delete</button>\n            </form>\n          </td>\n        </tr>\n      {% else %}\n        <tr><td colspan="4" class="empty">No subjects yet — use “Load defaults”.</td></tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n{% endblock %}\n',
    'schedule.html':
        '{% extends "base.html" %}\n{% block title %}Exam schedule{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Exam schedule</h1><p>One paper per subject — date, time, hall and marks</p></div>\n</header>\n\n<section class="card">\n  <details open>\n    <summary>Add a paper</summary>\n    {% if not exams or not subjects %}\n      <p class="muted">Create at least one exam and one subject first.</p>\n    {% else %}\n    <form class="form-grid" method="post" action="{{ url_for(\'schedule_save\') }}">\n      <label>Exam *\n        <select name="exam_id" required>\n          <option value="">— choose —</option>\n          {% for e in exams %}<option value="{{ e.id }}">{{ exam_label(e) }}</option>{% endfor %}\n        </select>\n      </label>\n      <label>Subject *\n        <select name="subject_id" required>\n          <option value="">— choose —</option>\n          {% for s in subjects %}<option value="{{ s.id }}">{{ s.subject_name }} ({{ s.subject_code }})</option>{% endfor %}\n        </select>\n      </label>\n      <label>Exam date<input name="exam_date" placeholder="dd/mm/yyyy"></label>\n      <label>Start time<input name="start_time" placeholder="09:00"></label>\n      <label>Duration (minutes)<input name="duration" value="180"></label>\n      <label>Room / hall<input name="room"></label>\n      <label>Invigilator<input name="invigilator"></label>\n      <label>Max marks<input name="max_marks" value="100"></label>\n      <label>Pass marks<input name="pass_marks" value="33"></label>\n      <div class="form-actions"><button class="btn primary" type="submit">Add paper</button></div>\n    </form>\n    {% endif %}\n  </details>\n</section>\n\n<section class="card">\n  <div class="card-head"><h2>Scheduled papers <span class="pill">{{ papers|length }}</span></h2></div>\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr><th>Exam</th><th>Subject</th><th>Date</th><th>Time</th><th>Duration</th>\n                 <th>Room</th><th>Invigilator</th><th>Max</th><th>Pass</th><th></th></tr></thead>\n      <tbody>\n      {% for p in papers %}\n        <tr>\n          <td>{{ exam_label(p) }}</td><td>{{ p.subject_name }}</td>\n          <td>{{ disp_date(p.exam_date) }}</td><td>{{ p.start_time }}</td>\n          <td>{{ p.duration }}</td><td>{{ p.room or \'\' }}</td>\n          <td>{{ p.invigilator or \'\' }}</td>\n          <td class="num">{{ fmt_num(p.max_marks) }}</td>\n          <td class="num">{{ fmt_num(p.pass_marks) }}</td>\n          <td class="row-actions">\n            <form method="post" action="{{ url_for(\'schedule_delete\', pid=p.id) }}"\n                  onsubmit="return confirm(\'Remove this paper and its marks?\')">\n              <button class="btn danger small" type="submit">Delete</button>\n            </form>\n          </td>\n        </tr>\n      {% else %}\n        <tr><td colspan="10" class="empty">No papers scheduled yet.</td></tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n</section>\n{% endblock %}\n',
    'marks.html':
        '{% extends "base.html" %}\n{% block title %}Marks entry{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Marks entry</h1><p>Pick an exam and a subject, then fill one row per student</p></div>\n</header>\n\n<section class="card">\n  <form class="form-grid" method="get">\n    <label>Exam\n      <select name="exam_id" onchange="this.form.submit()">\n        <option value="">— choose —</option>\n        {% for e in exams %}\n          <option value="{{ e.id }}" {{ \'selected\' if exam_id == e.id|string }}>{{ exam_label(e) }}</option>\n        {% endfor %}\n      </select>\n    </label>\n    <label>Subject\n      <select name="subject_id" onchange="this.form.submit()">\n        <option value="">— choose —</option>\n        {% for s in subjects %}\n          <option value="{{ s.id }}" {{ \'selected\' if subject_id == s.id|string }}>{{ s.subject_name }} ({{ s.subject_code }})</option>\n        {% endfor %}\n      </select>\n    </label>\n    <noscript><div class="form-actions"><button class="btn ghost" type="submit">Load sheet</button></div></noscript>\n  </form>\n</section>\n\n{% if info %}<p class="info">{{ info }}</p>{% endif %}\n\n{% if sheet %}\n<section class="card">\n  <form method="post" id="marks-form"\n        data-max="{{ ctx.max_marks }}" data-pass="{{ ctx.pass_marks }}">\n    <input type="hidden" name="exam_id" value="{{ exam_id }}">\n    <input type="hidden" name="subject_id" value="{{ subject_id }}">\n    <div class="table-wrap">\n      <table class="grid" id="marks-table">\n        <thead><tr><th>Roll</th><th>Name</th><th>Status</th>\n                   <th class="num">Marks (max {{ fmt_num(ctx.max_marks) }})</th>\n                   <th>Result</th><th>Remarks</th></tr></thead>\n        <tbody>\n        {% for row in sheet %}\n          <tr data-status="{{ row.status }}">\n            <td>{{ row.student.roll_no }}</td>\n            <td>{{ row.student.name }}</td>\n            <td>\n              <select class="status-select" name="status_{{ row.student.id }}">\n                <option value="ENTERED" {{ \'selected\' if row.status == \'ENTERED\' }}>Entered</option>\n                <option value="ABSENT"  {{ \'selected\' if row.status == \'ABSENT\' }}>Absent (AB)</option>\n                <option value="EXEMPT"  {{ \'selected\' if row.status == \'EXEMPT\' }}>Exempt (EX)</option>\n              </select>\n            </td>\n            <td class="num">\n              <input class="mark-input" type="number" step="0.5" min="0"\n                     max="{{ ctx.max_marks }}" inputmode="decimal"\n                     name="marks_{{ row.student.id }}" value="{{ row.value }}">\n            </td>\n            <td class="result-cell">\n              {% if row.status == \'ABSENT\' %}<span class="tag bad">Absent</span>\n              {% elif row.status == \'EXEMPT\' %}<span class="tag info">Exempt</span>\n              {% elif row.value == \'\' %}<span class="muted">—</span>\n              {% elif row.value|float >= ctx.pass_marks %}<span class="tag ok">Pass</span>\n              {% else %}<span class="tag bad">Fail</span>{% endif %}\n            </td>\n            <td><input name="remarks_{{ row.student.id }}" value="{{ row.remarks }}"></td>\n          </tr>\n        {% endfor %}\n        </tbody>\n      </table>\n    </div>\n    <div class="form-actions">\n      <button class="btn primary" type="submit">Save all marks</button>\n    </div>\n  </form>\n</section>\n\n<section class="card">\n  <div class="card-head"><h2>Sheet summary</h2></div>\n  <p class="muted" id="summary-line">{{ info }}</p>\n</section>\n\n<script>\n(function () {\n  var form = document.getElementById(\'marks-form\');\n  if (!form) return;\n  var MAX = parseFloat(form.getAttribute(\'data-max\')) || 100;\n  var PASS = parseFloat(form.getAttribute(\'data-pass\')) || 33;\n  var rows = Array.prototype.slice.call(\n    document.querySelectorAll(\'#marks-table tbody tr\'));\n  var line = document.getElementById(\'summary-line\');\n\n  function tag(cls, text) {\n    var s = document.createElement(\'span\');\n    s.className = \'tag \' + cls;\n    s.textContent = text;\n    return s;\n  }\n\n  function paint(tr) {\n    var sel = tr.querySelector(\'.status-select\');\n    var inp = tr.querySelector(\'.mark-input\');\n    var cell = tr.querySelector(\'.result-cell\');\n    var status = sel.value;\n    tr.setAttribute(\'data-status\', status);\n\n    var off = status !== \'ENTERED\';\n    inp.disabled = off;\n    inp.className = off ? \'mark-input is-off\' : \'mark-input\';\n\n    while (cell.firstChild) cell.removeChild(cell.firstChild);\n    if (status === \'ABSENT\') { cell.appendChild(tag(\'bad\', \'Absent\')); return; }\n    if (status === \'EXEMPT\') { cell.appendChild(tag(\'info\', \'Exempt\')); return; }\n\n    var raw = inp.value.trim();\n    if (raw === \'\') {\n      var dash = document.createElement(\'span\');\n      dash.className = \'muted\';\n      dash.textContent = \'—\';\n      cell.appendChild(dash);\n      return;\n    }\n    var v = parseFloat(raw);\n    if (isNaN(v)) { cell.appendChild(tag(\'bad\', \'Not a number\')); return; }\n    if (v < 0 || v > MAX) { cell.appendChild(tag(\'bad\', \'Out of range\')); return; }\n    cell.appendChild(v >= PASS ? tag(\'ok\', \'Pass\') : tag(\'bad\', \'Fail\'));\n  }\n\n  function summary() {\n    var entered = 0, absent = 0, exempt = 0, pending = 0;\n    var sum = 0, hi = null, lo = null;\n    rows.forEach(function (tr) {\n      var status = tr.getAttribute(\'data-status\');\n      if (status === \'ABSENT\') { absent += 1; return; }\n      if (status === \'EXEMPT\') { exempt += 1; return; }\n      var raw = tr.querySelector(\'.mark-input\').value.trim();\n      var v = raw === \'\' ? NaN : parseFloat(raw);\n      if (isNaN(v)) { pending += 1; return; }\n      entered += 1;\n      sum += v;\n      if (hi === null || v > hi) hi = v;\n      if (lo === null || v < lo) lo = v;\n    });\n    var parts = [rows.length + \' students\', entered + \' entered\',\n                 absent + \' absent\', exempt + \' exempt\', pending + \' pending\'];\n    if (entered) {\n      parts.push(\'average \' + (sum / entered).toFixed(2));\n      parts.push(\'highest \' + hi);\n      parts.push(\'lowest \' + lo);\n    }\n    line.textContent = parts.join(\'  ·  \');\n  }\n\n  rows.forEach(function (tr) {\n    tr.querySelector(\'.status-select\').addEventListener(\'change\', function () {\n      paint(tr); summary();\n    });\n    tr.querySelector(\'.mark-input\').addEventListener(\'input\', function () {\n      paint(tr); summary();\n    });\n    paint(tr);\n  });\n  summary();\n})();\n</script>\n{% endif %}\n\n{% if exam_id and subject_id and not sheet %}\n<section class="card">\n  <p class="muted">No students to show. Either nobody is enrolled yet, or the\n     exam has no class set. Check the roster on the\n     <a href="{{ url_for(\'students\') }}">Students</a> page, or set the exam\'s\n     class on the <a href="{{ url_for(\'exams\') }}">Exams</a> page.</p>\n</section>\n{% endif %}\n{% endblock %}\n',
    'results.html':
        '{% extends "base.html" %}\n{% block title %}Results{% endblock %}\n{% block content %}\n<header class="page-head">\n  <div><h1>Results</h1><p>Totals, percentage, grade, rank and pass / fail</p></div>\n  {% if results %}\n  <div class="actions">\n    <a class="btn ghost" href="{{ url_for(\'results_csv\', exam_id=exam_id, class_name=class_name) }}">Export CSV</a>\n  </div>\n  {% endif %}\n</header>\n\n<section class="card">\n  <form class="form-grid" method="get">\n    <label>Exam\n      <select name="exam_id" onchange="this.form.submit()">\n        <option value="">— choose —</option>\n        {% for e in exams %}\n          <option value="{{ e.id }}" {{ \'selected\' if exam_id == e.id|string }}>{{ exam_label(e) }}</option>\n        {% endfor %}\n      </select>\n    </label>\n    <label>Class\n      <input name="class_name" value="{{ class_name }}" placeholder="e.g. 8">\n    </label>\n    <div class="form-actions"><button class="btn primary" type="submit">Generate</button></div>\n  </form>\n</section>\n\n{% if info %}<p class="info">{{ info }}</p>{% endif %}\n\n{% if results %}\n<section class="card">\n  <div class="table-wrap">\n    <table class="grid">\n      <thead><tr><th>Rank</th><th>Roll</th><th>Admission No</th><th>Name</th>\n                 <th>Obtained</th><th>Max</th><th>%</th><th>Grade</th>\n                 <th>Failed</th><th>Result</th></tr></thead>\n      <tbody>\n      {% for r in results %}\n        <tr>\n          <td>{{ r.rank }}</td><td>{{ r.roll_no }}</td><td>{{ r.admission_no }}</td>\n          <td>{{ r.name }}</td><td class="num">{{ fmt_num(r.obtained) }}</td>\n          <td class="num">{{ fmt_num(r.total_max) }}</td>\n          <td class="num">{{ \'%.2f\'|format(r.percentage) }}</td>\n          <td>{{ r.grade }}</td><td class="num">{{ r.failed_subjects }}</td>\n          <td>{% if r.result == \'Pass\' %}<span class="tag ok">Pass</span>\n              {% elif r.result == \'Absent\' %}<span class="tag info">Absent</span>\n              {% else %}<span class="tag bad">Fail</span>{% endif %}\n              {% if r.absent_subjects %}<span class="muted small"> · {{ r.absent_subjects }} AB</span>{% endif %}\n              {% if r.exempt_subjects %}<span class="muted small"> · {{ r.exempt_subjects }} EX</span>{% endif %}</td>\n        </tr>\n      {% endfor %}\n      </tbody>\n    </table>\n  </div>\n  <p class="muted small">Absent (AB) and exempt (EX) papers are left out of the\n     total and the percentage, so they never count as zero.</p>\n</section>\n{% endif %}\n{% endblock %}\n',
    'landing.html':
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>{{ app_name }} — school examination management, marks entry and results</title>\n<meta name="description" content="{{ app_name }} is a school examination management system. Keep student records, exam schedules and subjects together, enter marks subject by subject with absent and exempt handling, and publish results with grades and ranks.">\n<meta name="keywords" content="ExamSetu, exam management system, school exam software, marks entry software, exam result software, report card software, student management India">\n<meta name="application-name" content="{{ app_name }}">\n<meta name="theme-color" content="#0f172a">\n<meta name="robots" content="index, follow">\n<link rel="canonical" href="{{ request.url_root }}">\n<meta property="og:site_name" content="{{ app_name }}">\n<meta property="og:type" content="website">\n<meta property="og:title" content="{{ app_name }} — school examination management">\n<meta property="og:description" content="Students, exams, schedules, marks entry and results in one place.">\n<meta property="og:url" content="{{ request.url_root }}">\n<meta name="twitter:card" content="summary">\n<link rel="stylesheet" href="{{ url_for(\'static\', filename=\'style.css\') }}">\n<link rel="icon" href="{{ url_for(\'static\', filename=\'icon.png\') }}">\n<script type="application/ld+json">\n{\n  "@context": "https://schema.org",\n  "@type": "SoftwareApplication",\n  "name": "{{ app_name }}",\n  "alternateName": "ExamSetu examination management",\n  "applicationCategory": "BusinessApplication",\n  "operatingSystem": "Web",\n  "url": "{{ request.url_root }}",\n  "description": "School examination management system for student records, exam schedules, marks entry and results.",\n  "offers": { "@type": "Offer", "price": "0", "priceCurrency": "INR" }\n}\n</script>\n<style>\n.landing-nav {\n  display: flex; justify-content: space-between; align-items: center;\n  padding: 16px 26px; max-width: 1080px; margin: 0 auto;\n}\n.landing-brand { display: flex; align-items: center; gap: 10px; font-size: 17px; }\n.landing-brand .badge {\n  width: 34px; height: 34px; border-radius: 9px; background: var(--accent);\n  color: #fff; display: grid; place-items: center; font-weight: 700;\n  font-size: 13px; letter-spacing: .5px;\n}\n.landing-hero {\n  display: flex; gap: 34px; align-items: center; flex-wrap: wrap;\n  max-width: 1080px; margin: 10px auto 40px; padding: 0 26px;\n}\n.landing-hero > div:first-child { flex: 1 1 420px; }\n.landing-hero h1 {\n  font-size: 36px; line-height: 1.2; margin: 10px 0 14px; color: #111827;\n}\n.landing-hero p { color: #475569; font-size: 16px; max-width: 540px; }\n.landing-card {\n  flex: 0 1 380px; background: #fff; border: 1px solid var(--line);\n  border-radius: 14px; padding: 16px; box-shadow: 0 18px 40px rgba(15, 23, 42, .10);\n}\n.landing-card h2 { font-size: 12px; text-transform: uppercase; letter-spacing: .08em;\n  color: var(--muted); margin-bottom: 10px; }\ntable.mini { width: 100%; border-collapse: collapse; font-size: 13px; }\ntable.mini th { text-align: left; color: var(--muted); font-weight: 600;\n  font-size: 11px; text-transform: uppercase; padding: 6px 8px;\n  border-bottom: 1px solid var(--line); }\ntable.mini td { padding: 7px 8px; border-bottom: 1px solid #f1f5f9; }\n.landing-features {\n  display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));\n  gap: 16px; max-width: 1080px; margin: 0 auto 44px; padding: 0 26px;\n}\n.landing-features article {\n  background: #fff; border: 1px solid var(--line); border-radius: 12px;\n  padding: 18px;\n}\n.landing-features h3 { font-size: 15px; margin: 0 0 6px; }\n.landing-features p { margin: 0; color: var(--muted); font-size: 13px; }\n.landing-foot {\n  border-top: 1px solid var(--line); padding: 18px 26px; text-align: center;\n  color: var(--muted); font-size: 12px; max-width: 1080px; margin: 0 auto;\n}\n@media (max-width: 700px) { .landing-hero h1 { font-size: 27px; } }\n</style>\n</head>\n<body>\n<header class="landing-nav">\n  <div class="landing-brand"><span class="badge">ES</span><strong>{{ app_name }}</strong></div>\n  <a class="btn primary" href="{{ url_for(\'auth.login\') }}">Log in</a>\n</header>\n\n<section class="landing-hero">\n  <div>\n    <span class="hero-eyebrow">School examination management</span>\n    <h1>{{ app_name }} keeps your exams, marks and results in one place</h1>\n    <p>Student records, exam schedules, subject-wise marks entry and results\n       with grades and ranks — for a whole school, in one simple web app.\n       Absent and exempt papers are handled properly instead of being counted\n       as zero.</p>\n    <div class="hero-actions">\n      <a class="btn primary" href="{{ url_for(\'auth.login\') }}">Log in</a>\n      <a class="btn ghost" href="#features">See what it does</a>\n    </div>\n  </div>\n  <div class="landing-card">\n    <h2>Marks entry</h2>\n    <table class="mini">\n      <tr><th>Roll</th><th>Student</th><th>Marks</th><th>Status</th></tr>\n      <tr><td>01</td><td>Aarav Menon</td><td>76</td><td><span class="tag ok">Pass</span></td></tr>\n      <tr><td>02</td><td>Diya Sharma</td><td>68</td><td><span class="tag ok">Pass</span></td></tr>\n      <tr><td>03</td><td>Kabir Rao</td><td>—</td><td><span class="tag bad">Absent</span></td></tr>\n      <tr><td>04</td><td>Meera Iyer</td><td>41</td><td><span class="tag ok">Pass</span></td></tr>\n    </table>\n  </div>\n</section>\n\n<section id="features" class="landing-features">\n  <article>\n    <h3>Students</h3>\n    <p>Admissions, roll numbers, class and section, guardian details and\n       student logins — all in one record.</p>\n  </article>\n  <article>\n    <h3>Exams and subjects</h3>\n    <p>Create exams by type and academic year, keep a subject master, and\n       schedule one paper per subject with its maximum and pass marks.</p>\n  </article>\n  <article>\n    <h3>Marks entry</h3>\n    <p>Pick an exam and a subject, then fill one row per student. Absent and\n       exempt rows are excluded from totals instead of scoring zero.</p>\n  </article>\n  <article>\n    <h3>Results</h3>\n    <p>Totals, percentage, grade, rank and pass / fail per class, with a CSV\n       export for the office.</p>\n  </article>\n  <article>\n    <h3>Student portal</h3>\n    <p>Each student signs in with their admission number to see only their own\n       marks and results.</p>\n  </article>\n  <article>\n    <h3>Built for Indian schools</h3>\n    <p>Class and section, roll numbers, pass marks and grade bands — the way\n       schools here actually record marks.</p>\n  </article>\n</section>\n\n<footer class="landing-foot">\n  {{ app_name }} · {{ school_name }} · examination management system\n</footer>\n</body>\n</html>\n',
}

STYLE_CSS = '/* Exam Manager - web edition */\n:root {\n  --bg: #f4f6fb;\n  --white: #ffffff;\n  --ink: #0f172a;\n  --muted: #64748b;\n  --line: #e2e8f0;\n  --soft: #f8fafc;\n  --accent: #4f46e5;\n  --accent-dark: #4338ca;\n  --accent-soft: #eef2ff;\n  --danger: #dc2626;\n  --danger-soft: #fee2e2;\n  --ok: #059669;\n  --ok-soft: #d1fae5;\n  --sidebar: #0f172a;\n}\n* { box-sizing: border-box; }\nbody {\n  margin: 0;\n  background: var(--bg);\n  color: var(--ink);\n  font: 15px/1.5 "Segoe UI", Inter, "Helvetica Neue", system-ui, Arial, sans-serif;\n}\na { color: var(--accent); text-decoration: none; }\na:hover { text-decoration: underline; }\nh1 { font-size: 24px; margin: 0; }\nh2 { font-size: 15px; margin: 0; }\n.muted { color: var(--muted); }\n.num { text-align: right; font-variant-numeric: tabular-nums; }\n\n/* ---------- shell ---------- */\n.shell { display: flex; min-height: 100vh; }\n.sidebar {\n  width: 244px; flex: 0 0 244px; background: var(--sidebar); color: #fff;\n  display: flex; flex-direction: column; padding: 22px 0;\n}\n.brand { display: flex; gap: 12px; align-items: center; padding: 0 20px 18px; }\n.badge {\n  width: 38px; height: 38px; border-radius: 10px; background: var(--accent);\n  display: grid; place-items: center; font-weight: 700; letter-spacing: .5px;\n}\n.brand-text strong { display: block; font-size: 15px; }\n.brand-text span { display: block; font-size: 11px; color: #7c8ba1; }\n.sidebar nav { display: flex; flex-direction: column; padding: 6px 10px; gap: 2px; }\n.sidebar nav a {\n  color: #94a3b8; padding: 10px 14px; border-radius: 8px; font-size: 14px;\n}\n.sidebar nav a:hover { background: #1e293b; color: #e2e8f0; text-decoration: none; }\n.sidebar nav a.active { background: #1e293b; color: #fff; box-shadow: inset 3px 0 0 var(--accent); }\n.sidebar-foot {\n  margin-top: auto; padding: 16px 20px 0; display: flex; flex-direction: column;\n  gap: 6px; font-size: 12px; color: #475569;\n}\n.sidebar-foot a { color: #94a3b8; }\n\nmain { flex: 1; padding: 26px 30px 40px; min-width: 0; }\n\n/* ---------- headers, cards ---------- */\n.page-head {\n  display: flex; justify-content: space-between; align-items: flex-start;\n  gap: 16px; margin-bottom: 18px; flex-wrap: wrap;\n}\n.page-head p { margin: 4px 0 0; color: var(--muted); font-size: 13px; }\n.actions { display: flex; gap: 8px; }\n.card {\n  background: var(--white); border: 1px solid var(--line); border-radius: 12px;\n  padding: 18px; margin-bottom: 16px;\n}\n.card-head {\n  display: flex; justify-content: space-between; align-items: center;\n  gap: 12px; margin-bottom: 12px; flex-wrap: wrap;\n}\n.pill {\n  background: var(--accent-soft); color: var(--accent-dark); border-radius: 999px;\n  padding: 1px 9px; font-size: 12px; font-weight: 600; margin-left: 6px;\n}\n\n/* ---------- stat tiles ---------- */\n.tiles {\n  display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));\n  gap: 14px; margin-bottom: 18px;\n}\n.tile {\n  background: var(--white); border: 1px solid var(--line); border-radius: 12px;\n  padding: 16px 18px;\n}\n.tile .bar { display: block; width: 34px; height: 3px; border-radius: 2px; margin-bottom: 10px; }\n.bar.indigo { background: var(--accent); }\n.bar.sky { background: #0ea5e9; }\n.bar.green { background: #10b981; }\n.bar.amber { background: #f59e0b; }\n.tile b { display: block; font-size: 26px; line-height: 1.1; }\n.tile span { color: var(--muted); font-size: 12px; }\n\n.two-col { display: grid; grid-template-columns: 3fr 2fr; gap: 16px; }\n@media (max-width: 1000px) { .two-col { grid-template-columns: 1fr; } }\n\n/* ---------- forms ---------- */\n.form-grid {\n  display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));\n  gap: 12px 16px; margin-top: 12px;\n}\n.form-grid label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }\n.form-grid .span-2 { grid-column: span 2; }\ninput, select {\n  font: inherit; font-size: 14px; color: var(--ink); background: var(--white);\n  border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px;\n}\ninput:focus, select:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }\n.form-actions { display: flex; align-items: end; gap: 8px; }\ndetails summary {\n  cursor: pointer; font-weight: 600; font-size: 14px; color: var(--accent-dark);\n  list-style: none;\n}\ndetails summary::-webkit-details-marker { display: none; }\ndetails summary::before { content: "+ "; font-weight: 700; }\ndetails[open] summary::before { content: "- "; font-weight: 700; }\n\n/* ---------- buttons ---------- */\n.btn {\n  display: inline-block; font: inherit; font-size: 14px; cursor: pointer;\n  border-radius: 8px; padding: 8px 14px; border: 1px solid var(--line);\n  background: var(--white); color: var(--ink); text-decoration: none;\n}\n.btn:hover { background: var(--soft); text-decoration: none; }\n.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }\n.btn.primary:hover { background: var(--accent-dark); }\n.btn.ghost { background: var(--white); }\n.btn.danger { color: var(--danger); border-color: #fecaca; }\n.btn.danger:hover { background: var(--danger-soft); }\n.btn.small { padding: 4px 9px; font-size: 12px; }\n\n/* ---------- tables ---------- */\n.table-wrap { overflow-x: auto; }\ntable.grid { width: 100%; border-collapse: collapse; font-size: 14px; }\ntable.grid th {\n  text-align: left; font-size: 11px; letter-spacing: .04em; text-transform: uppercase;\n  color: var(--muted); background: var(--soft); padding: 9px 10px;\n  border-bottom: 1px solid var(--line); white-space: nowrap;\n}\ntable.grid td { padding: 9px 10px; border-bottom: 1px solid var(--line); vertical-align: middle; }\ntable.grid tbody tr:nth-child(even) { background: #fcfdff; }\ntable.grid tbody tr:hover { background: var(--accent-soft); }\ntable.grid td.empty { text-align: center; color: var(--muted); padding: 26px; }\n.row-actions { display: flex; gap: 6px; justify-content: flex-end; }\n.row-actions form { display: inline; }\n.mark-input { width: 96px; }\n\n/* ---------- bits ---------- */\n.tag { display: inline-block; border-radius: 999px; padding: 2px 9px; font-size: 12px; font-weight: 600; }\n.tag.ok { background: var(--ok-soft); color: var(--ok); }\n.tag.bad { background: var(--danger-soft); color: var(--danger); }\n.flash {\n  border-radius: 10px; padding: 11px 14px; margin-bottom: 14px; font-size: 14px;\n  border: 1px solid var(--line); background: var(--white);\n}\n.flash.ok { background: var(--ok-soft); border-color: #a7f3d0; color: #065f46; }\n.flash.error { background: var(--danger-soft); border-color: #fecaca; color: #991b1b; }\n.banner {\n  background: #fff7ed; border: 1px solid #fed7aa; color: #9a3412;\n  border-radius: 10px; padding: 11px 14px; margin-bottom: 14px; font-size: 13px;\n}\n.info { color: var(--muted); font-size: 13px; margin: 0 0 12px 2px; }\n.search { display: flex; gap: 8px; align-items: center; }\n.search input { min-width: 260px; }\n.login-wrap { display: grid; place-items: center; min-height: 70vh; }\n.card.login { width: 340px; display: flex; flex-direction: column; gap: 12px; }\n.card.login h1 { font-size: 22px; }\n.card.login label { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--muted); }\n\n/* ---------- small screens ---------- */\n@media (max-width: 820px) {\n  .shell { flex-direction: column; }\n  .sidebar { width: 100%; flex: none; padding: 14px 0; }\n  .sidebar nav { flex-direction: row; overflow-x: auto; gap: 6px; }\n  .sidebar nav a { white-space: nowrap; }\n  .sidebar-foot { flex-direction: row; gap: 14px; padding: 10px 20px 0; }\n  main { padding: 18px 14px 30px; }\n  .form-grid { grid-template-columns: 1fr; }\n  .form-grid .span-2 { grid-column: auto; }\n}\n'

ICON_PNG_B64 = ('iVBORw0KGgoAAAANSUhEUgAAAQAAAAEACAYAAABccqhmAAAHdUlEQVR4nO3dvY5lRxmF4RrkIbdEBCkESNwBkZMJbEsEyAkSIfdA5MAJJL4FIgsRGgkCJoCIq3AMFiDZGUl7aKKWWz3dffY++6e+qvU8oT14qo3Xu+uc/pnWAAAAAACAOb3ofYAz/OzVP257n4Ex/fH1D6beyFQfnKFzllnCMPwHYfT0NnIMhjy40VPVaDEY5rBGz2hGiEH5Axo+o6scgrIHM3xmUzEE5Q5k+MyuUgjKHMTwSVMhBN/pfYDWjJ9MFf6771qgCv8CoIJet4FuNwDjh2/12kOXABg/vK3HLk69dhg+LHPWS4LTbgDGD8udtZdTAmD8sN4Zuzk8AMYP1zt6P4cGwPhhuyN3dFgAjB/2c9SeDgmA8cP+jtjV7gEwfjjO3vvaNQDGD8fbc2clvhkI6GO3AHj6w3n22tsuATB+ON8eu9scAOOHfrbuz3sAEGxTADz9ob8tO7w6AMYPdVy7Ry8BINhVAfD0h3qu2aUbAARbHQBPf6hr7T7dACDYqgB4+kN9a3bqBgDBFgfA0x/GsXSvbgAQTAAg2KIAuP7DeJbs1g0AggkABLsYANd/GNel/boBQDABgGDPBsD1H8b33I7dACCYAEAwAYBgAgDBBACCPRkAnwGAeTy1ZzcACCYAEEwAIJgAQDABgGACAMEEAIIJAAQTAAj2Tu8DpPjxT77bfvPp93ofYxj/+feb9qtf/qv3MabnBgDBBACCCQAEEwAIJgAQTAAgmABAMAGAYAIAwQQAggkABBMACCYAEEwAIJgAQDABgGACAMEEAIIJAAQTAAjmh4JO6ubmtn304Ze9j0FxbgAQTAAgmABAMAGAYAIAwQQAggkABBMACCYAEEwAIJgAQDABgGACAMEEAIIJAAQTAAgmABBMACCYAEAwAYBgfijopF6+fNE+/8v3ex9jtZ+//8/25k3vU+RwA4BgAgDBBACCCQAEEwAIJgAQTAAgmABAMAGAYAIAwQQAggkABBMACCYAEEwAIJgAQDABgGACAMEEAIIJAATzQ0EndXNz2z768Mvex6A4NwAIJgAQTAAgmABAMAGAYAIAwQQAgj35dQDf3Pz3zHNM7803/zv99/T/IZe4AUAwAYBgAgDBBACCCQAEEwAIJgAQTAAgmABAMAGAYAIAwQQAggkABBMACCYAEEwAIJg/GGRSL1++aH/66w97H2Ozz373VfvDZ1/1Psa03AAgmABAMAGAYAIAwQQAggkABBMACCYAEEwAIJgAQDABgGACAMEEAIIJAAQTAAgmABDMDwSBe/7+698v/rU//e0vDjzJOQSAaGsGf+l/O2IQBIBIW4Z/6Z85UggEgChHDP+p32OEELx46m988N4Xt2ceBI50xvCfUiUEf/7bj97au88CML2e46/w+z/HSwCmVWl4VV8WuAEwpUrjv6/auQSA6VQb2UOVzicATKXSuJ5T5ZwCwDSqjGqpCucVAKZQYUzX6H1uAYBgAsDwej9Fn/P1q48v/pqe5xcAhjbC+CtHQADgAA9HvyQCPQgAw6r69H9q7Jci0OPjEQA40devPi51GxAAhjTa03/przv74xIA2MnaJ3uFm4AAMJyKT/9rxvzu608e/etnfnwCABvtOf6zCQBsMPL4WxMAiCYADKXS6/8jn/5nfZwCQJS93nkf/ep/RwCIseZr85f8c9aoOP7WBIAQe31t/kzjb+2ZADz2M8RhRNd+bf7WX99anfE/tWc3AKZ2abRbv3R3dALAtHqPu8rT/zkCwJT2vN6PfPW/RACYzp5v8M08/tYEgAltGeD9wc8+/tYuBMBnAhjV1gjMNP7nduwGwFDW/OGaZw5y79/rrD9EVACYWtWnchUXA+BlAKM7OgKVI3Npv24ARDhqpJXHv4QAMJxrXx/vPdajxn/W6//WFgbAywBmsddoR3jyL9mtGwBD2vKU3DreI8d/5tO/NQEg1AhP8DMsDoCXAVSz9Wl5TQRGefov3asbANHWDHrGW8OqALgFUM0eT80lwz56/D2e/q25ATCBPSPwcOjvvv5kqPGvddUT/YP3vrjd+yCwRaUfF75Wr6d/a24ATKLnU3SL3ue+KgDeC6Ci3mNaa+/zXrNLNwCmMkoEqpzz6gC4BVBVlXE95YjzXbvHTTcAEaCqqhGoNP7WWntnz4NAJXdjq/AZgqpB2vwegFsA1fUe35G//9b97TZeXxvACM68DRwdnj0evrs+vUWAURwZgjNuHHvdvL0HQKQj3h/o/VLjGru/fncLYGRrgtBr8Hu+73bIG3giAMfY+033Q74S0GcGYH9H7OqwLwUWAdjPUXs69HsBRAC2O3JHh38zkAjA9Y7ezynfDSgCsN4Zuznt24FFAJY7ay9dRunThPC4sx+UXX4giNsAvK3HLrr9RCARgG/12kOJEXpJQKreD8ISPxOw978E6KHCf/fdD/CQ2wCzqzD8O2UO8pAQMJtKw79T7kAPCQGjqzj8O2UP9pAQMJrKw79T/oCPEQOqGmH09w112MeIAb2NNvr7hj34Y8SAs4w8+vum+CAuEQauNcvQAQAAAIBQ/wc5QDYHbNuaaAAAAABJRU5ErkJggg==')

GENDERS = ["Male", "Female", "Other"]
STUDENT_STATUS = ["Active", "Inactive", "Passed Out", "Left"]
EXAM_TYPES = ["Unit Test", "Mid Term", "Half Yearly", "Annual / Final",
              "Pre-Board", "Practical", "Internal Assessment"]
EXAM_STATUS = ["Scheduled", "Ongoing", "Completed", "Result Declared", "Cancelled"]
SECTIONS = ["A", "B", "C", "D", "E"]


# Marks entry: the status control, and the dimmed mark box that goes with
# an absent or exempt row.
STYLE_CSS += """
.tag.info { background: var(--accent-soft); color: var(--accent-dark); }
.status-select { padding: 6px 8px; font-size: 13px; }
.mark-input.is-off { background: var(--soft); color: var(--muted); }
tr[data-status="ABSENT"] td, tr[data-status="EXEMPT"] td { color: var(--muted); }
.small { font-size: 12px; }
"""

STYLE_CSS += """

/* ---------- dashboard hero ---------- */
.hero {
  background: linear-gradient(135deg, #1e1b4b 0%, #312e81 45%, #4f46e5 100%);
  color: #fff; border-radius: 16px; padding: 26px 28px; margin-bottom: 18px;
  display: flex; justify-content: space-between; align-items: center;
  gap: 24px; flex-wrap: wrap; box-shadow: 0 12px 30px rgba(49, 46, 129, .22);
}
.hero h1 { font-size: 27px; margin: 6px 0 6px; color: #fff; }
.hero p { margin: 0; color: #c7d2fe; font-size: 14px; }
.hero-eyebrow {
  font-size: 11px; letter-spacing: .12em; text-transform: uppercase;
  color: #a5b4fc; font-weight: 600;
}
.hero-actions { display: flex; gap: 10px; margin-top: 18px; flex-wrap: wrap; }
.hero .btn.primary { background: #fff; border-color: #fff; color: #312e81; }
.hero .btn.primary:hover { background: #e0e7ff; }
.hero .btn.ghost {
  background: rgba(255, 255, 255, .12); border-color: rgba(255, 255, 255, .28);
  color: #fff;
}
.hero .btn.ghost:hover { background: rgba(255, 255, 255, .22); }
.hero-ring { text-align: center; }
.hero-ring .muted { color: #a5b4fc; margin-top: 6px; }
.donut { width: 132px; height: 132px; }
.donut circle { fill: none; stroke-width: 11; }
.donut-track { stroke: rgba(255, 255, 255, .18); }
.donut-value { stroke: #34d399; stroke-linecap: round; }
.donut-num { fill: #fff; font-size: 25px; font-weight: 700; }
.donut-cap { fill: #a5b4fc; font-size: 11px; }

/* ---------- class progress ---------- */
.progress-row {
  display: grid; grid-template-columns: 88px 1fr 78px; gap: 10px;
  align-items: center; padding: 7px 0;
}
.progress-label { font-size: 13px; font-weight: 600; }
.progress-track {
  height: 9px; border-radius: 999px; background: var(--soft);
  overflow: hidden; border: 1px solid var(--line);
}
.progress-fill {
  display: block; height: 100%; border-radius: 999px;
  background: linear-gradient(90deg, #6366f1, #22d3ee);
}
.progress-num {
  font-size: 12px; color: var(--muted); text-align: right;
  font-variant-numeric: tabular-nums;
}

/* ---------- quick actions ---------- */
.quick-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.quick {
  display: block; padding: 12px 14px; border: 1px solid var(--line);
  border-radius: 10px; background: var(--soft);
}
.quick:hover {
  background: var(--accent-soft); border-color: #c7d2fe; text-decoration: none;
}
.quick b { display: block; font-size: 14px; }
.quick span { font-size: 12px; color: var(--muted); }
.tile .cap { display: block; font-size: 11px; color: var(--muted); margin-top: 4px; }

/* ---------- status chips ---------- */
.chip {
  display: inline-block; border-radius: 999px; padding: 2px 9px;
  font-size: 11px; font-weight: 600;
}
.chip-ok { background: var(--ok-soft); color: var(--ok); }
.chip-live { background: #fef3c7; color: #b45309; }
.chip-idle { background: var(--soft); color: var(--muted); border: 1px solid var(--line); }

@media (max-width: 700px) {
  .hero { padding: 20px; }
  .hero-ring { margin: 0 auto; }
  .quick-actions { grid-template-columns: 1fr; }
}
"""



app = Flask(__name__, static_folder=None)
app.jinja_loader = DictLoader(TEMPLATES)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
from auth_system import register_auth, login_required

register_auth(app)


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
#  database  (PostgreSQL - the single source of truth)
# --------------------------------------------------------------------------
#  Roll numbers are TEXT ("12", "A-4", "3B"), so sorting them needs care.
#  This expression sorts by the leading number first, then alphabetically,
#  and never fails on a roll number that has no digits at all.
ROLL_ORDER = ("NULLIF(substring(roll_no from '^[0-9]+'), '')::int"
              " NULLS LAST, roll_no")

# How a mark row can stand: entered, absent from the paper, or exempt
# from it (medical / board direction). Absent and exempt rows carry no
# mark, and are left out of totals rather than scored as zero.
MARKS_STATUSES = ("ENTERED", "ABSENT", "EXEMPT")


def get_db():
    """One connection per request, shared by every query in that request."""
    if "db" not in g:
        g.db = pgdb.connect()
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is None:
        return
    try:
        if _exc is not None:
            conn.rollback()
    except Exception:                       # noqa: BLE001 - closing anyway
        pass
    finally:
        conn.close()


def query(sql, params=(), one=False):
    """SELECT - returns a list of dict rows (or one dict / None)."""
    with get_db().cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


def execute(sql, params=()):
    """INSERT / UPDATE / DELETE - commits and returns the new id if any."""
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        new_id = cur.fetchone()["id"] if cur.description is not None else None
    conn.commit()
    return new_id


@contextmanager
def transaction():
    """Several statements that must all succeed or none of them."""
    conn = get_db()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    conn.commit()


def init_db():
    """Prepare the PostgreSQL schema. Safe to run on every start.

    Nothing is dropped, nothing is recreated: existing tables and rows are
    left exactly as they are, and only missing tables / columns / indexes
    are added.
    """
    try:
        pgdb.ensure_schema()
        return True, None
    except Exception as exc:                # noqa: BLE001 - never crash boot
        app.logger.error("Could not prepare the PostgreSQL schema: %s", exc)
        return False, str(exc)


# --------------------------------------------------------------------------
#  business logic
# --------------------------------------------------------------------------
def compute_results(exam_id, class_name):
    schedule = query("SELECT subject_id, max_marks, pass_marks FROM exam_schedule"
                     " WHERE exam_id=%s", (exam_id,))
    if not schedule:
        return []
    max_by_sub = {r["subject_id"]: (r["max_marks"] or 0) for r in schedule}
    pass_by_sub = {r["subject_id"]: (r["pass_marks"] or 0) for r in schedule}

    students = query(
        "SELECT id, admission_no, roll_no, name FROM students"
        " WHERE class_name=%s ORDER BY " + ROLL_ORDER, (class_name,))
    marks = query("SELECT * FROM marks WHERE exam_id=%s", (exam_id,))
    by_student = {}
    for m in marks:
        by_student.setdefault(m["student_id"], {})[m["subject_id"]] = m

    results = []
    for st in students:
        smap = by_student.get(st["id"], {})
        if not smap:
            continue
        obtained = total_max = 0.0
        failed = absent = exempt = 0
        for sub_id, mx in max_by_sub.items():
            row = smap.get(sub_id)
            if row is None:
                continue
            status = (row.get("status") or "ENTERED")
            if status == "ABSENT":
                absent += 1
                continue
            if status == "EXEMPT":
                exempt += 1
                continue
            if row["marks_obtained"] is None:
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
            "absent_subjects": absent,
            "exempt_subjects": exempt,
            # A student who missed a paper is not ranked against the class.
            "result": ("Absent" if absent else
                       "Pass" if (failed == 0 and pct >= 33) else "Fail"),
        })

    results.sort(key=lambda r: (r["result"] == "Absent",
                                -r["percentage"], r["roll_no"]))
    rank, last_pct = 0, None
    for i, r in enumerate(results, start=1):
        if r["result"] == "Absent":
            r["rank"] = "-"
            continue
        if last_pct is None or r["percentage"] != last_pct:
            rank, last_pct = i, r["percentage"]
        r["rank"] = rank
    return results


# --------------------------------------------------------------------------
#  auth + shared template values
# --------------------------------------------------------------------------
#  Pages a logged-in student is allowed to open. Everything else belongs to
#  the staff area, so a student is sent back to their own result page.
STUDENT_ALLOWED = {"student_portal", "static", "healthz",
                   "auth.logout", "auth.login"}


@app.before_request
def require_login():
    # Keeps the schema present even if the database was briefly unreachable
    # when the process started (ensure_schema() is a no-op once it has run).
    if request.endpoint != "static":
        try:
            pgdb.ensure_schema()
        except Exception:                   # noqa: BLE001 - reported elsewhere
            pass

    if request.endpoint in ("auth.login", "static", "healthz",
                            "robots_txt", "sitemap_xml", "dashboard"):
        return None
    if not (session.get("user_id") or session.get("auth")):
        return redirect(url_for("auth.login", next=request.path))
    if session.get("role") == "student" and request.endpoint not in STUDENT_ALLOWED:
        return redirect(url_for("student_portal"))
    return None


@app.context_processor
def inject_globals():
    return {
        "app_name": APP_NAME,
        "school_name": SCHOOL_NAME,
        "auth_enabled": True,
        "no_password": False,
        "today": datetime.now().strftime("%d/%m/%Y"),
    }


# --------------------------------------------------------------------------
#  dashboard
# --------------------------------------------------------------------------
@app.route("/")
def dashboard():
    # Anyone who is not signed in gets the public page: it is the only thing
    # a search engine can read, and it explains what the app is.
    if not (session.get("user_id") or session.get("auth")):
        return render_template("landing.html", disp_date=disp_date)
    stats = {
        "students": query("SELECT COUNT(*) AS c FROM students", one=True)["c"],
        "exams": query("SELECT COUNT(*) AS c FROM exams", one=True)["c"],
        "subjects": query("SELECT COUNT(*) AS c FROM subjects", one=True)["c"],
        "papers": query("SELECT COUNT(*) AS c FROM exam_schedule", one=True)["c"],
    }
    marks_row = query(
        "SELECT COUNT(*) FILTER (WHERE marks_obtained IS NOT NULL"
        "  AND COALESCE(status, 'ENTERED') = 'ENTERED') AS entered,"
        " COUNT(*) FILTER (WHERE status = 'ABSENT') AS absent,"
        " COUNT(*) FILTER (WHERE status = 'EXEMPT') AS exempt"
        " FROM marks", one=True) or {}
    stats["marks"] = marks_row.get("entered") or 0
    stats["absent"] = marks_row.get("absent") or 0
    stats["exempt"] = marks_row.get("exempt") or 0

    # How many mark rows the data implies: for every class, its active
    # students times the papers scheduled for that class's exams.
    expected = query(
        "SELECT COALESCE(SUM(s.n * p.n), 0) AS c FROM"
        " (SELECT class_name, COUNT(*) AS n FROM students"
        "   WHERE status='Active' AND COALESCE(class_name,'')<>''"
        "   GROUP BY class_name) s"
        " JOIN (SELECT e.class_name, COUNT(*) AS n FROM exams e"
        "   JOIN exam_schedule sc ON sc.exam_id = e.id"
        "   GROUP BY e.class_name) p ON p.class_name = s.class_name",
        one=True) or {}
    expected = expected.get("c") or 0

    classes = []
    for row in query(
            "SELECT st.class_name,"
            "  COUNT(DISTINCT st.id) AS students,"
            "  (SELECT COUNT(*) FROM exam_schedule sc JOIN exams e2"
            "     ON e2.id = sc.exam_id"
            "   WHERE e2.class_name = st.class_name) AS papers,"
            "  COUNT(m.id) AS entered"
            " FROM students st"
            " LEFT JOIN exams e ON e.class_name = st.class_name"
            " LEFT JOIN exam_schedule sc ON sc.exam_id = e.id"
            " LEFT JOIN marks m ON m.student_id = st.id AND m.exam_id = e.id"
            "   AND m.subject_id = sc.subject_id"
            "   AND m.marks_obtained IS NOT NULL"
            " WHERE st.status='Active' AND COALESCE(st.class_name,'')<>''"
            " GROUP BY st.class_name ORDER BY st.class_name LIMIT 8"):
        want = (row["students"] or 0) * (row["papers"] or 0)
        got = row["entered"] or 0
        classes.append({
            "class_name": row["class_name"],
            "entered": got,
            "expected": want,
            "pct": min(100, round(got / want * 100)) if want else 0,
        })
    stats["classes"] = len(classes)

    pct = min(100, round(stats["marks"] / expected * 100)) if expected else 0
    progress = {
        "entered": stats["marks"],
        "expected": expected,
        "pct": pct,
        "dash": round(pct * 326.7 / 100, 1),   # 2 * pi * r, r = 52
    }

    recent = query("SELECT * FROM students ORDER BY id DESC LIMIT 10")
    exams = query("SELECT * FROM exams ORDER BY id DESC LIMIT 10")
    return render_template("dashboard.html", stats=stats, recent=recent,
                           exams=exams, classes=classes, progress=progress,
                           disp_date=disp_date)


# --------------------------------------------------------------------------
#  search engines: name, robots and sitemap
# --------------------------------------------------------------------------
@app.route("/robots.txt")
def robots_txt():
    body = ("User-agent: *\nAllow: /\n"
            f"Sitemap: {request.url_root}sitemap.xml\n")
    return Response(body, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    body = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"  <url><loc>{request.url_root}</loc><changefreq>weekly</changefreq>"
            "<priority>1.0</priority></url>\n"
            f"  <url><loc>{url_for('auth.login', _external=True)}</loc>"
            "<changefreq>monthly</changefreq><priority>0.4</priority></url>\n"
            "</urlset>\n")
    return Response(body, mimetype="application/xml")


# --------------------------------------------------------------------------
#  students
# --------------------------------------------------------------------------
@app.route("/students")
def students():
    term = request.args.get("q", "").strip()
    if term:
        like = f"%{term}%"
        rows = query(
            "SELECT * FROM students WHERE name ILIKE %s OR roll_no ILIKE %s"
            " OR admission_no ILIKE %s OR class_name ILIKE %s"
            " ORDER BY class_name, " + ROLL_ORDER,
            (like, like, like, like))
    else:
        rows = query("SELECT * FROM students ORDER BY class_name, " + ROLL_ORDER)
    classes = [r["class_name"] for r in query(
        "SELECT DISTINCT class_name FROM students WHERE class_name<>''"
        " ORDER BY class_name")]
    edit_id = request.args.get("edit", type=int)
    editing = query("SELECT * FROM students WHERE id=%s", (edit_id,),
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

    dup = query("SELECT id FROM students WHERE admission_no=%s AND id<>%s",
                (adm, int(sid) if sid else 0), one=True)
    if dup:
        flash(f"Admission No {adm} already exists.", "error")
        return redirect(url_for("students"))

    if sid:
        execute("""UPDATE students SET admission_no=%s, roll_no=%s, name=%s,
                   class_name=%s, section=%s, dob=%s, gender=%s, father_name=%s,
                   mother_name=%s, phone=%s, email=%s, address=%s,
                   admission_date=%s, status=%s WHERE id=%s""",
                values + (int(sid),))
        flash(f"Student '{name}' updated.", "ok")
    else:
        execute("""INSERT INTO students (admission_no, roll_no, name, class_name,
                   section, dob, gender, father_name, mother_name, phone, email,
                   address, admission_date, status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id""", values)
        flash(f"Student '{name}' added.", "ok")
    return redirect(url_for("students"))


@app.route("/students/<int:sid>/delete", methods=["POST"])
def student_delete(sid):
    row = query("SELECT name FROM students WHERE id=%s", (sid,), one=True)
    execute("DELETE FROM students WHERE id=%s", (sid,))
    flash(f"Student '{row['name'] if row else sid}' deleted.", "ok")
    return redirect(url_for("students"))


@app.route("/students.csv")
def students_csv():
    rows = query("SELECT * FROM students ORDER BY class_name, " + ROLL_ORDER)
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
    editing = query("SELECT * FROM exams WHERE id=%s", (edit_id,),
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
    dup = query("""SELECT id FROM exams WHERE exam_type=%s
                   AND COALESCE(academic_year,'')=%s
                   AND COALESCE(class_name,'')=%s
                   AND id<>%s""", (etype, year, cls, int(eid) if eid else 0),
                one=True)
    if dup:
        flash(f"'{etype}' already exists for class {cls or '-'} "
              f"in {year or '-'}.", "error")
        return redirect(url_for("exams"))

    if eid:
        execute("""UPDATE exams SET exam_name=%s, exam_type=%s,
                   academic_year=%s, class_name=%s, start_date=%s, end_date=%s,
                   status=%s, remarks=%s WHERE id=%s""",
                (etype, etype, year, cls, sd, ed,
                 f.get("status") or "Scheduled", f.get("remarks", "").strip(),
                 int(eid)))
        flash(f"Exam '{etype}' updated.", "ok")
    else:
        execute("""INSERT INTO exams (exam_name, exam_type, academic_year,
                   class_name, start_date, end_date, status, remarks)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (etype, etype, year, cls, sd, ed,
                 f.get("status") or "Scheduled", f.get("remarks", "").strip()))
        flash(f"Exam '{etype}' saved.", "ok")
    return redirect(url_for("exams"))


@app.route("/exams/<int:eid>/delete", methods=["POST"])
def exam_delete(eid):
    row = query("SELECT exam_type FROM exams WHERE id=%s", (eid,), one=True)
    execute("DELETE FROM exams WHERE id=%s", (eid,))
    flash(f"Exam '{row['exam_type'] if row else eid}' deleted.", "ok")
    return redirect(url_for("exams"))


# --------------------------------------------------------------------------
#  subjects
# --------------------------------------------------------------------------
@app.route("/subjects")
def subjects():
    rows = query("SELECT * FROM subjects ORDER BY subject_code")
    edit_id = request.args.get("edit", type=int)
    editing = query("SELECT * FROM subjects WHERE id=%s", (edit_id,),
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
    dup = query("SELECT id FROM subjects WHERE subject_code=%s AND id<>%s",
                (code, int(sid) if sid else 0), one=True)
    if dup:
        flash(f"Subject code {code} already exists.", "error")
        return redirect(url_for("subjects"))
    if sid:
        execute("UPDATE subjects SET subject_code=%s, subject_name=%s,"
                " class_name=%s WHERE id=%s", (code, name, cls, int(sid)))
        flash(f"Subject '{name}' updated.", "ok")
    else:
        execute("INSERT INTO subjects (subject_code, subject_name, class_name)"
                " VALUES (%s,%s,%s) RETURNING id", (code, name, cls))
        flash(f"Subject '{name}' added.", "ok")
    return redirect(url_for("subjects"))


@app.route("/subjects/<int:sid>/delete", methods=["POST"])
def subject_delete(sid):
    row = query("SELECT subject_name FROM subjects WHERE id=%s", (sid,), one=True)
    execute("DELETE FROM subjects WHERE id=%s", (sid,))
    flash(f"Subject '{row['subject_name'] if row else sid}' deleted.", "ok")
    return redirect(url_for("subjects"))


@app.route("/subjects/defaults", methods=["POST"])
def subject_defaults():
    defaults = [("ENG", "English"), ("HIN", "Hindi"), ("MAT", "Mathematics"),
                ("SCI", "Science"), ("SST", "Social Science"),
                ("CS", "Computer Science")]
    added = 0
    for code, name in defaults:
        if not query("SELECT id FROM subjects WHERE subject_code=%s", (code,),
                     one=True):
            execute("INSERT INTO subjects (subject_code, subject_name)"
                    " VALUES (%s,%s) RETURNING id", (code, name))
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
    if query("SELECT id FROM exam_schedule WHERE exam_id=%s AND subject_id=%s",
             (exam_id, subject_id), one=True):
        flash("That subject is already scheduled for this exam.", "error")
        return redirect(url_for("schedule"))

    execute("""INSERT INTO exam_schedule (exam_id, subject_id, exam_date,
               start_time, duration, room, invigilator, max_marks, pass_marks)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (exam_id, subject_id, ed, st, int(duration),
             f.get("room", "").strip(), f.get("invigilator", "").strip(),
             mx, ps))
    flash("Paper added to the schedule.", "ok")
    return redirect(url_for("schedule"))


@app.route("/schedule/<int:pid>/delete", methods=["POST"])
def schedule_delete(pid):
    execute("DELETE FROM exam_schedule WHERE id=%s", (pid,))
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
        sched = query("SELECT * FROM exam_schedule WHERE exam_id=%s AND"
                      " subject_id=%s", (exam_id, subject_id), one=True)
        exam = query("SELECT * FROM exams WHERE id=%s", (exam_id,), one=True)
        class_name = (exam["class_name"] or "").strip() if exam else ""

        unscheduled = not sched
        roster_note = ""
        if unscheduled:
            # Not on the exam schedule yet. Rather than a dead end, carry on
            # with the usual maxima so marks can still be entered, and say
            # what is missing.
            sched = {"max_marks": 100, "pass_marks": 33}
        if sched:
            max_marks = float(sched["max_marks"] or 100)
            pass_marks = float(sched["pass_marks"] or 33)
            ctx = {"max_marks": max_marks, "pass_marks": pass_marks}
            students_rows = query(
                "SELECT id, roll_no, name FROM students WHERE status='Active'"
                " AND class_name=%s ORDER BY " + ROLL_ORDER, (class_name,))
            if class_name and not students_rows:
                # '8' vs 'Class 8' vs a trailing space - try a looser match
                # before deciding there is nobody to show.
                students_rows = query(
                    "SELECT id, roll_no, name FROM students"
                    " WHERE status='Active' AND class_name ILIKE %s"
                    " ORDER BY " + ROLL_ORDER, (f"%{class_name}%",))
            if not students_rows:
                students_rows = query(
                    "SELECT id, roll_no, name FROM students"
                    " WHERE status='Active' ORDER BY class_name, " + ROLL_ORDER)
                if students_rows:
                    roster_note = (
                        f"No student is in {class_name or 'the exam class'} -"
                        " showing every active student instead.")

            if request.method == "POST":
                # Validate the whole sheet before writing a single row: a
                # teacher saves all of it or none of it, so a typo on row 40
                # never leaves the class half-saved.
                problems, writes = [], []
                for st in students_rows:
                    status = (request.form.get(f"status_{st['id']}")
                              or "ENTERED").strip().upper()
                    if status not in MARKS_STATUSES:
                        status = "ENTERED"
                    raw = request.form.get(f"marks_{st['id']}", "").strip()
                    remark = request.form.get(f"remarks_{st['id']}", "").strip()
                    value = None
                    if status == "ENTERED" and raw:
                        value = to_float(raw)
                        if value is None:
                            problems.append(
                                f"Roll {st['roll_no']}: '{raw}' is not a number")
                            continue
                        if value < 0 or value > max_marks:
                            problems.append(
                                f"Roll {st['roll_no']}: {fmt_num(value)} is"
                                f" outside 0 to {fmt_num(max_marks)}")
                            continue
                    writes.append((st["id"], value, remark, status))

                if problems:
                    flash("Nothing was saved. " + "; ".join(problems[:6])
                          + (" and more" if len(problems) > 6 else ""), "error")
                    # Put exactly what was typed back on screen.
                    for st in students_rows:
                        sheet.append({
                            "student": st,
                            "value": request.form.get(f"marks_{st['id']}",
                                                      "").strip(),
                            "status": (request.form.get(f"status_{st['id']}")
                                       or "ENTERED"),
                            "remarks": request.form.get(
                                f"remarks_{st['id']}", "").strip(),
                        })
                else:
                    existing = {
                        m["student_id"]: m["id"] for m in query(
                            "SELECT id, student_id FROM marks WHERE exam_id=%s"
                            " AND subject_id=%s", (exam_id, subject_id))
                    }
                    counts = {"entered": 0, "absent": 0, "exempt": 0,
                              "pending": 0}
                    # One transaction for the whole class: fast and atomic.
                    with transaction() as conn:
                        with conn.cursor() as cur:
                            for student_id, value, remark, status in writes:
                                if student_id in existing:
                                    cur.execute(
                                        "UPDATE marks SET marks_obtained=%s,"
                                        " remarks=%s, status=%s,"
                                        " updated_at=CURRENT_TIMESTAMP"
                                        " WHERE id=%s",
                                        (value, remark, status,
                                         existing[student_id]))
                                else:
                                    cur.execute(
                                        "INSERT INTO marks (exam_id,"
                                        " student_id, subject_id,"
                                        " marks_obtained, remarks, status)"
                                        " VALUES (%s,%s,%s,%s,%s,%s)",
                                        (exam_id, student_id, subject_id,
                                         value, remark, status))
                                if status == "ABSENT":
                                    counts["absent"] += 1
                                elif status == "EXEMPT":
                                    counts["exempt"] += 1
                                elif value is None:
                                    counts["pending"] += 1
                                else:
                                    counts["entered"] += 1
                    flash(f"Saved. {counts['entered']} mark(s) entered,"
                          f" {counts['absent']} absent,"
                          f" {counts['exempt']} exempt,"
                          f" {counts['pending']} still blank.", "ok")
                    return redirect(url_for("marks", exam_id=exam_id,
                                            subject_id=subject_id))

            if not sheet:
                saved_marks = {
                    m["student_id"]: m for m in query(
                        "SELECT * FROM marks WHERE exam_id=%s AND subject_id=%s",
                        (exam_id, subject_id))
                }
                for st in students_rows:
                    m = saved_marks.get(st["id"])
                    got = m["marks_obtained"] if m else None
                    sheet.append({
                        "student": st,
                        "mark": m,
                        "value": fmt_num(got) if got is not None else "",
                        "status": ((m or {}).get("status") or "ENTERED"),
                        "remarks": (m.get("remarks") if m else "") or "",
                    })

            counts = {"entered": 0, "absent": 0, "exempt": 0, "pending": 0}
            for row in sheet:
                if row["status"] == "ABSENT":
                    counts["absent"] += 1
                elif row["status"] == "EXEMPT":
                    counts["exempt"] += 1
                elif str(row["value"]).strip() == "":
                    counts["pending"] += 1
                else:
                    counts["entered"] += 1
            info = (f"{len(sheet)} student(s) · max {fmt_num(max_marks)} ·"
                    f" pass {fmt_num(pass_marks)} · {counts['entered']} entered"
                    f" · {counts['absent']} absent · {counts['exempt']} exempt"
                    f" · {counts['pending']} pending")
            if unscheduled:
                info += ("  ·  this subject is not on the exam schedule, so"
                         " max 100 / pass 33 are being used")
            if roster_note:
                info += "  ·  " + roster_note

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
        exam = query("SELECT * FROM exams WHERE id=%s", (int(exam_id),), one=True)
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
    exam = query("SELECT * FROM exams WHERE id=%s", (exam_id,), one=True)
    class_name = class_name or (exam["class_name"] or "").strip()
    rows = compute_results(exam_id, class_name)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Rank", "Roll No", "Admission No", "Name", "Obtained", "Max",
                "Percentage", "Grade", "Failed Subjects", "Absent Subjects",
                "Exempt Subjects", "Result"])
    for r in rows:
        w.writerow([r["rank"], r["roll_no"], r["admission_no"], r["name"],
                    fmt_num(r["obtained"]), fmt_num(r["total_max"]),
                    f"{r['percentage']:.2f}", r["grade"], r["failed_subjects"],
                    r["absent_subjects"], r["exempt_subjects"], r["result"]])
    name = f"results_{class_name or 'all'}.csv".replace(" ", "_")
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":
                             f"attachment; filename={name}"})


# --------------------------------------------------------------------------
#  the student's own page
# --------------------------------------------------------------------------
STUDENT_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>My results · {{ school_name }}</title>
<style>{{ css|safe }}</style></head>
<body><main>
<header class="page-head">
  <div>
    <h1>{{ me.name }}</h1>
    <p>Admission No {{ me.admission_no }} · Roll {{ me.roll_no }} ·
       Class {{ me.class_name }}{% if me.section %} · Section {{ me.section }}{% endif %}</p>
  </div>
  <div class="actions">
    <a class="btn ghost" href="{{ url_for('auth.logout') }}">Log out</a>
  </div>
</header>

{% for m in get_flashed_messages() %}<div class="flash">{{ m }}</div>{% endfor %}

{% if not exams %}
<section class="card"><p class="muted">No marks have been entered for you
   yet. Please check again later.</p></section>
{% endif %}

{% for e in exams %}
<section class="card">
  <div class="card-head">
    <h2>{{ e.label }}</h2>
    <span class="pill">{% if e.percentage is number %}{{ e.percentage }}% · {% endif %}{{ e.grade }} · {{ e.result }}</span>
  </div>
  <div class="table-wrap">
    <table class="grid">
      <thead><tr><th>Subject</th><th>Code</th><th class="num">Max</th>
                 <th class="num">Pass</th><th class="num">Obtained</th>
                 <th>Status</th></tr></thead>
      <tbody>
      {% for p in e.papers %}
        <tr>
          <td>{{ p.subject_name }}</td>
          <td>{{ p.subject_code }}</td>
          <td class="num">{{ fmt_num(p.max_marks) }}</td>
          <td class="num">{{ fmt_num(p.pass_marks) }}</td>
          <td class="num">{% if p.mark_status == 'ABSENT' %}AB
              {% elif p.mark_status == 'EXEMPT' %}EX
              {% else %}{{ fmt_num(p.marks_obtained) }}{% endif %}</td>
          <td>{% if p.mark_status == 'ABSENT' %}<strong>Absent</strong>
              {% elif p.mark_status == 'EXEMPT' %}<span class="muted">Exempt</span>
              {% elif p.marks_obtained is none %}<span class="muted">not entered</span>
              {% elif p.marks_obtained|float >= p.pass_marks|float %}Pass
              {% else %}<strong>Fail</strong>{% endif %}</td>
        </tr>
      {% endfor %}
        <tr>
          <td colspan="4"><strong>Total</strong></td>
          <td class="num"><strong>{{ fmt_num(e.obtained) }} / {{ fmt_num(e.total_max) }}</strong></td>
          <td><strong>{{ e.result }}</strong></td>
        </tr>
      </tbody>
    </table>
  </div>
</section>
{% endfor %}

<section class="card">
  <div class="card-head"><h2>My details</h2></div>
  <p class="muted">
    Date of birth: {{ disp_date(me.dob) or '-' }} &nbsp;·&nbsp;
    Gender: {{ me.gender or '-' }} &nbsp;·&nbsp;
    Father's name: {{ me.father_name or '-' }} &nbsp;·&nbsp;
    Mother's name: {{ me.mother_name or '-' }} &nbsp;·&nbsp;
    Phone: {{ me.phone or '-' }} &nbsp;·&nbsp;
    Email: {{ me.email or '-' }} &nbsp;·&nbsp;
    Admitted on: {{ disp_date(me.admission_date) or '-' }}
  </p>
  <p class="muted small">Wrong details or a forgotten password? Ask the school
     office / admin.</p>
</section>
</main></body></html>"""


@app.route("/student")
def student_portal():
    if session.get("role") != "student":
        return redirect(url_for("dashboard"))
    sid = session.get("user_id")
    me = query("SELECT * FROM students WHERE id=%s", (sid,), one=True)
    if me is None:
        session.clear()
        flash("Your student record could not be found. Please ask the admin.",
              "error")
        return redirect(url_for("auth.login"))

    rows = query("""SELECT m.exam_id, m.subject_id, m.marks_obtained,
                           COALESCE(m.status, 'ENTERED') AS mark_status,
                           e.exam_type, e.exam_name, e.academic_year,
                           e.class_name, s.subject_name, s.subject_code,
                           COALESCE(sc.max_marks, 100) AS max_marks,
                           COALESCE(sc.pass_marks, 33) AS pass_marks
                    FROM marks m
                    JOIN exams e    ON e.id = m.exam_id
                    JOIN subjects s ON s.id = m.subject_id
                    LEFT JOIN exam_schedule sc
                           ON sc.exam_id = m.exam_id
                          AND sc.subject_id = m.subject_id
                    WHERE m.student_id = %s
                    ORDER BY e.id DESC, s.subject_code""", (sid,))

    grouped = {}
    order = []
    for r in rows:
        if r["exam_id"] not in grouped:
            grouped[r["exam_id"]] = []
            order.append(r["exam_id"])
        grouped[r["exam_id"]].append(r)

    exams = []
    for exam_id in order:
        papers = grouped[exam_id]
        obtained = total = 0.0
        failed = 0
        for p in papers:
            if (p.get("mark_status") or "ENTERED") in ("ABSENT", "EXEMPT"):
                continue          # left out of the total, never scored as 0
            if p["marks_obtained"] is None:
                continue
            got = float(p["marks_obtained"])
            obtained += got
            total += float(p["max_marks"] or 0)
            if got < float(p["pass_marks"] or 0):
                failed += 1
        pct = round(obtained / total * 100, 2) if total > 0 else None
        head = papers[0]
        exams.append({
            "label": exam_label(head),
            "papers": papers,
            "obtained": round(obtained, 2),
            "total_max": round(total, 2),
            "percentage": pct if pct is not None else "-",
            "grade": grade_for(pct),
            "result": ("Pass" if (failed == 0 and pct is not None and pct >= 33)
                       else "Fail") if pct is not None else "-",
        })

    return render_template_string(
        STUDENT_PAGE, me=me, exams=exams, css=STYLE_CSS,
        disp_date=disp_date, fmt_num=fmt_num)


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

    try:
        info = pgdb.connection_info()
        checks.append(("DATABASE_URL set", True,
                       f"{info['host']}:{info['port']} / {info['database']}"))
    except Exception as exc:                # noqa: BLE001 - report anything
        checks.append(("DATABASE_URL set", False, str(exc)))
        checks.append(("PostgreSQL tables", False, "no database to check"))
        return checks

    try:
        counts = pgdb.table_counts()
        missing_tables = [t for t, c in counts.items() if c is None]
        detail = ", ".join(
            f"{t}={'MISSING' if c is None else c}" for t, c in counts.items())
        checks.append(("PostgreSQL tables and row counts",
                       not missing_tables, detail))
    except Exception as exc:                # noqa: BLE001
        checks.append(("PostgreSQL reachable", False, str(exc)))

    try:
        with pgdb.connect() as conn:
            conn.execute("SELECT 1")
        checks.append(("PostgreSQL accepts connections", True, "SELECT 1 OK"))
    except Exception as exc:                # noqa: BLE001
        checks.append(("PostgreSQL accepts connections", False, str(exc)))

    checks.append(("SECRET_KEY set", bool(os.environ.get("SECRET_KEY")),
                   "yes" if os.environ.get("SECRET_KEY") else
                   "no - everyone is logged out after each restart"))
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
    except Exception:                       # noqa: BLE001
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
