# ExamPro — moving everything to PostgreSQL (beginner's guide)

This guide takes you from "two databases that don't talk to each other" to
"one PostgreSQL database for the whole app", without losing a single student,
exam, subject, schedule row or mark.

Read the sections in order. Step 1 (backup) is the only one that must not be
skipped.

---

## 0. What was actually wrong

| Part of the app | Database it used | Where the data lived |
|---|---|---|
| `app.py` (students, exams, subjects, schedule, marks) | SQLite | a file called `exam_manager.db` on the server |
| `auth_system.py` (logins, student passwords) | PostgreSQL | the Render database, `DATABASE_URL` |

So when you added a student on the **Students** page it was written into the
SQLite *file*. When the admin tried to set that student's password, the login
system searched the *PostgreSQL* database, found nothing, and said
**"Admission number not found."**

Nothing was broken in your code logic — the two halves were simply writing to
different places. After this update there is only one place: PostgreSQL.

---

## 1. Files in this update

| File | What it is | Action |
|---|---|---|
| `db.py` | **New.** The single PostgreSQL connection + schema layer. Both other Python files import it, so they can never disagree about the database again. | add |
| `app.py` | Rewritten database layer; every query is now PostgreSQL. All pages, forms and features are unchanged. | replace |
| `auth_system.py` | Same logins, now on the same database; admission numbers are matched ignoring case/spaces; the admin page lists your students and shows who has a password. | replace |
| `migrate_sqlite_to_postgres.py` | **New.** Copies the old `exam_manager.db` records into PostgreSQL. Safe, repeatable, `--dry-run` and `--verify` built in. | add |
| `requirements.txt` | Unchanged packages (Flask, gunicorn, psycopg, Werkzeug) with a version floor on psycopg. | replace |
| `MIGRATION_GUIDE.md` | This file. | add |

Nothing else in the repository needs to change.

---

## 2. Back up first (5 minutes, do not skip)

**2a. Keep the old SQLite file.** Download `exam_manager.db` from your computer
(or wherever it lives) and keep a copy somewhere safe. It is the original copy
of your student data. The new app never opens or modifies it — the migration
script only *reads* it.

**2b. Back up the Render PostgreSQL database.** In the Render dashboard:

1. Open your **PostgreSQL** service.
2. Copy the **External Database URL** (Connections → External Database URL).
3. On your own computer (PostgreSQL tools installed), run:

```bash
pg_dump "PASTE_THE_EXTERNAL_DATABASE_URL_HERE" > exampro_backup_before_migration.sql
```

If you do not have `pg_dump`, any of these also work:

* Render dashboard → your database → **Backups** (paid plans have scheduled
  backups; on the free plan use `pg_dump`).
* Or simply continue — the migration script only ever *adds* tables, columns
  and rows. It never drops or overwrites anything. The dump is your safety net,
  not a requirement.

Keep the `.sql` file. It is how you undo everything in step 10.

---

## 3. Set the environment variables on Render

Open your **web service** (not the database) → **Environment**.

| Variable | Value | Notes |
|---|---|---|
| `DATABASE_URL` | *already there* | If you attached the Postgres service to the web service, Render fills this in. If it is missing: **Add Environment Variable → Add from database →** pick your database. Do not type it by hand. |
| `SECRET_KEY` | a long random string | Generate one: `python -c "import secrets;print(secrets.token_hex(32))"`. Without it, everybody is logged out after every restart. |
| `ADMIN_USERNAME` | `admin` | The admin login name. |
| `ADMIN_PASSWORD` | a strong password | The admin password. Change it here any time; the app re-syncs it on restart. |
| `SCHOOL_NAME` | *optional* | Shown in the header. |

You can delete `APP_PASSWORD` and `DB_PATH` if they are still there — they are
no longer used.

`DATABASE_URL` must be the **Internal Database URL** for a Render web service
(it is what Render sets automatically). The *External* URL is only for running
things from your own computer, e.g. the migration in step 5.

---

## 4. Put the files on GitHub

Easiest way, no git commands:

1. Open your repository: `https://github.com/ag789439/exam-script2`
2. **Add file → Upload files**
3. Drag in `db.py`, `app.py`, `auth_system.py`,
   `migrate_sqlite_to_postgres.py`, `requirements.txt`, `MIGRATION_GUIDE.md`.
4. Commit message: `Move the whole app to PostgreSQL`
5. **Commit changes**.

Uploading `app.py` replaces the old one — that is intended. The old version
stays in the repository history, so you can always get it back.

While you are there, you can delete the stray file named `app (1).py`. It is an
older draft (a "v3.1" with a `users` table) that Render never runs —
`gunicorn app:app` only ever loads `app.py`. If you later want that version
moved to PostgreSQL too, it is a copy of the same database layer.

---

## 5. Deploy on Render

Open the web service → **Settings**:

* **Build command:** `pip install -r requirements.txt`
* **Start command:**
  ```
  gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120
  ```
  (`--workers 2 --threads 4` keeps pages responsive on PostgreSQL, `--timeout
  120` gives the first request time to build the schema.)
* **Health check path:** `/healthz`

Then **Manual Deploy → Deploy latest commit**.

In the log you should see `Booting worker with pid ...` and no traceback.
If the schema could not be created you will see one clear line such as
`Could not prepare the PostgreSQL schema: ...` — the app still starts, and
`/healthz` tells you what is wrong.

Open `https://YOUR-APP.onrender.com/healthz`. You want:

```json
{"status": "ok", "checks": [ ... "PostgreSQL tables and row counts" ... ]}
```

The five tables are created automatically at this point (empty, or with the
records you already had). **No data is touched.**

---

## 6. Copy the old SQLite records into PostgreSQL

Do this from your own computer, using the **External Database URL**.

```bash
# 1. get the code and the packages
cd exam-script2
pip install -r requirements.txt

# 2. point at the Render database (use the EXTERNAL Database URL here)
#    macOS / Linux:
export DATABASE_URL="postgresql://user:password@host/dbname"
#    Windows (PowerShell):
$env:DATABASE_URL="postgresql://user:password@host/dbname"

# 3. put the old file next to the script (or pass --sqlite /path/to/exam_manager.db)

# 4. see what WOULD happen, without writing anything
python migrate_sqlite_to_postgres.py --dry-run

# 5. do it
python migrate_sqlite_to_postgres.py

# 6. compare both sides and run integrity checks
python migrate_sqlite_to_postgres.py --verify
```

A successful run looks like this:

```
table            in SQLite  inserted  skipped  note
--------------------------------------------------------------
students                 4         4        0
exams                    1         1        0
subjects                 2         2        0
exam_schedule            2         2        0
marks                    6         6        0
--------------------------------------------------------------
TOTAL                             15
```

* **inserted** = new rows written to PostgreSQL.
* **skipped** = the record was already in PostgreSQL (matched by admission
  number / subject code / exam / mark). It is left exactly as it was — this is
  what makes the script safe to run twice.
* Original ids are preserved, so marks still point at the right student and
  exam. If an id was already taken by a different record, the row is inserted
  with a fresh id and its children are re-pointed automatically.
* After copying, the id counters are moved past the highest id, so new
  admissions will not collide with copied ones.

**If you have no SQLite file any more**, skip this step: your PostgreSQL
database is already the only source of truth and the app is ready to use.

**Alternative — run it on Render instead:** web service → **Shell** →
`python migrate_sqlite_to_postgres.py`. You must first upload `exam_manager.db`
into the service directory for that to work; running it locally is simpler.

---

## 7. Verify everything is really in PostgreSQL

Open `/healthz` — the "PostgreSQL tables and row counts" line lists all seven
tables with their row counts:

```
students=214, exams=6, subjects=12, exam_schedule=48, marks=1280,
teachers=5, auth_admins=1
```

MISSING in that list means a table does not exist — open any page once and the
app creates it.

For a deeper check, run these in Render → database → **PSQL** (or any SQL
client):

```sql
-- 1. the five tables exist
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' ORDER BY table_name;

-- 2. row counts
SELECT 'students' AS t, COUNT(*) FROM students
UNION ALL SELECT 'exams', COUNT(*) FROM exams
UNION ALL SELECT 'subjects', COUNT(*) FROM subjects
UNION ALL SELECT 'exam_schedule', COUNT(*) FROM exam_schedule
UNION ALL SELECT 'marks', COUNT(*) FROM marks;

-- 3. every mark points at a real student, exam and subject (all three = 0)
SELECT COUNT(*) FROM marks m LEFT JOIN students s ON s.id = m.student_id WHERE s.id IS NULL;
SELECT COUNT(*) FROM marks m LEFT JOIN exams e    ON e.id = m.exam_id    WHERE e.id IS NULL;
SELECT COUNT(*) FROM marks m LEFT JOIN subjects s ON s.id = m.subject_id WHERE s.id IS NULL;

-- 4. no duplicate admission numbers
SELECT admission_no, COUNT(*) FROM students
GROUP BY admission_no HAVING COUNT(*) > 1;

-- 5. who still needs a password
SELECT COUNT(*) FILTER (WHERE password_hash IS NULL) AS no_password,
       COUNT(*) FILTER (WHERE password_hash IS NOT NULL) AS has_password
FROM students;
```

---

## 8. Testing checklist — admin, teacher, student

Work through these once after deploying. Each line is one screen.

**Admin**

1. Open `/login`, choose **Admin**, sign in with `ADMIN_USERNAME` /
   `ADMIN_PASSWORD`. → Dashboard with your counts.
2. **Students** → your existing students are listed (this is the proof the
   mismatch is gone). Add a student, edit one, search, export CSV.
3. **Exams** → create one. **Subjects** → "Load defaults" works.
   **Exam schedule** → add a paper. **Marks entry** → save marks for a class.
   **Results** → ranks, grades and CSV export.
4. Admin menu → **Student passwords**. The page lists every student with a
   `set` / `not set` tag. Type an admission number (or pick it from the list),
   enter a password of 8+ characters, **Save password** → "Password saved for
   <name> (<admission no>)".
5. Admin menu → **Teacher accounts** → create a teacher login.

**Teacher**

6. Log out, `/login` → **Teacher** → sign in. → Dashboard, and the Students,
   Exams, Marks and Results pages work. The admin menu items are not shown, and
   `/admin/students` answers 403.

**Student**

7. Log out, `/login` → **Student** → admission number (any case, e.g. `adm102`
   works for `ADM102`) + the password the admin set. → **My results** page with
   their own subjects, marks, total, percentage, grade and pass/fail.
8. A student who has no password yet gets: "This account has no password yet.
   Ask the admin to set one." A wrong admission number gets: "No student has
   that admission number…". No more mystery "not found".
9. While logged in as a student, try `/students` → you are sent back to
   **My results**. Student data is not exposed to students.

**Sessions**

10. Reload the page a few times, then restart the service on Render (Manual
    Deploy) and reload again — you should still be logged in. If you are not,
    `SECRET_KEY` is missing (see step 3).

---

## 9. Everyday use after the move

* `exam_manager.db` is no longer read or written. The app will not create it.
  Keep your copy as an archive, or delete it from the repository.
* New students, exams, marks and passwords all go to PostgreSQL immediately —
  the login system sees them at once.
* Deleting a student still deletes their marks; deleting an exam deletes its
  schedule rows and marks (foreign keys with `ON DELETE CASCADE`).
* Nothing about the pages, forms, fields, CSV exports or grading changed.

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `DATABASE_URL is not set` on `/healthz` or the login page | The web service has no database attached | Service → Environment → add `DATABASE_URL` from the database |
| `could not translate host name` / `connection refused` | You used the **External** URL inside Render, or the Internal URL from your laptop | Inside Render use the Internal URL; from your laptop use the External URL |
| `server does not support SSL` | External URL without SSL | Append `?sslmode=require` to the External URL |
| `relation "students" does not exist` | Schema was never created | Open any page, or `/healthz`, once. It is created automatically |
| `duplicate key value violates unique constraint "students_admission_no_key"` | You tried to add an admission number that already exists | That is the intended protection — search the Students page for it |
| `Admission number not found` on the password page | The number does not match any row | The page now lists every student with their exact admission number; copy it from there |
| Login bounces back to the login page | `SECRET_KEY` missing or changed | Set a permanent `SECRET_KEY` in Environment |
| Logged in locally but the cookie is dropped | Secure cookies over http | Run with `SESSION_COOKIE_SECURE=0` locally |
| `gunicorn: command not found` | Wrong start command | Use `gunicorn app:app --bind 0.0.0.0:$PORT` |
| `ModuleNotFoundError: No module named 'db'` | `db.py` was not uploaded | Add `db.py` to the repository root, next to `app.py` |
| A page shows a red error box | Any unexpected error | The box lists the exact error plus an environment check; `/healthz` gives the same as JSON |

---

## 11. How to undo (rollback)

The database is never altered destructively, so a rollback is only about code:

1. Render → your database → **PSQL** → run the contents of
   `exampro_backup_before_migration.sql` (only if you actually need the old
   state back).
2. Render → web service → **Deploys** → open the previous deploy →
   **Redeploy**. That restores the old `app.py` / `auth_system.py`.
3. Put your `exam_manager.db` back next to the app if the old version expects
   it.

---

## 12. What changed in the code (short version)

* **One connection layer** (`db.py`). `app.py` and `auth_system.py` both import
  it, so they read the same `DATABASE_URL`. That is the fix for the mismatch.
* **Schema creation is non-destructive.** `CREATE TABLE IF NOT EXISTS` plus
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for every column the app uses, so
  an existing PostgreSQL table is *extended*, never replaced. A table created by
  hand (even with `id INTEGER PRIMARY KEY`) is adopted: it gets a working id
  sequence and any missing columns.
* **SQLite syntax replaced.** `?` → `%s` placeholders, `IFNULL` → `COALESCE`,
  `LIKE` → `ILIKE` (case-insensitive search), `AUTOINCREMENT` → `BIGSERIAL`,
  `CAST(roll_no AS INTEGER)` → a roll-number sort that cannot fail on
  `"A-4"`-style values, `CURRENT_TIMESTAMP` on real `timestamp` columns.
* **Transactions.** Bulk marks entry for a class now runs in a single
  transaction, so a failure leaves the marks exactly as they were.
* **Dates stay TEXT** in `yyyy-mm-dd` form, exactly as the old database stored
  them — no date conversion, no data rewriting.
* **Login improvements.** Admission numbers are matched ignoring case and
  surrounding spaces; the password page lists your students and their password
  status; students get their own "My results" page and cannot open staff pages.
