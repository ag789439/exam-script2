# Exam Manager — web edition (single file, multi-user)

A browser version of the examination module: students, exams, subjects, exam
schedule, marks entry and results. Deployable on Render so it can be opened
from any device with a link.

**Everything is in `app.py`** — the pages, the stylesheet and the icon are
embedded inside the file. There is no `templates/` or `static/` folder to
upload, so an upload cannot break the app.

**Multi-user with private data.** Every person gets their own account. A normal
account sees only the students, exams, subjects, papers, marks and results it
created itself. One admin account sees and edits everything.

## Files

```
app.py               the whole application (routes, database, pages, CSS, icon)
requirements.txt     Flask + gunicorn
Procfile             start command (optional)
render.yaml          Render blueprint (optional)
QUICKSTART_DEPLOY.txt  the short version of this document
```

## Deploy on Render

1. Push `app.py` and `requirements.txt` to a GitHub repository (root level).

2. Render → **New + → Web Service** → select the repository:

   | Field | Value |
   |---|---|
   | Name | `exam-manager` |
   | Region | Singapore |
   | Branch | `main` |
   | Root Directory | *(empty)* |
   | Language | Python 3 |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120` |
   | Instance Type | Free |

3. **Advanced → Add Environment Variable**

   | Key | Value |
   |---|---|
   | `ADMIN_USERNAME` | `admin` (or your own name) |
   | `ADMIN_PASSWORD` | the admin password you want |
   | `SECRET_KEY` | click *Generate* |
   | `SCHOOL_NAME` | e.g. `Jindal Public School` |

   If `ADMIN_PASSWORD` is not set, the app generates one on first boot and
   prints it in the Render logs — look for `first admin account created`.

4. **Create Web Service** → wait for *Live* (2–3 minutes).

5. Open `https://<your-app>.onrender.com/healthz` — every line should be
   `"ok": true`, including `admin account`. Logged out it only answers
   `{"status": "ok"}`; log in first to see the full checklist.

6. Open the root URL, log in as the admin, go to **Users** and create one
   account per teacher.

`render.yaml` is included, so **New + → Blueprint** also works and fills the
build/start commands and variables automatically.

## Accounts, roles and privacy

On the first boot the app creates **one admin account**. Log in as that admin
and open **Users** to create an account for each teacher.

There are **three kinds of account**: admin, teacher and student.

| | student | teacher | admin |
|---|---|---|---|
| own marks and result | **yes — only their own** | — | — |
| records the admin created (school-wide) | no | sees them, cannot change them | full control |
| records the teacher created | no | sees and edits only their own | sees all |
| another teacher's private records | no | **no** — not even by guessing the URL | yes |
| create / disable / delete accounts | no | no | yes |
| marks entry, schedule, results | no | school-wide exams and their own | any exam |

**Student accounts.** When the admin creates a user and sets the role to
`student`, the form asks which student record the account belongs to. That
student then logs in and sees one page — **My result** — with the exams where
marks have been entered, the total, percentage, grade, pass/fail and rank, plus
a subject-wise breakdown. They cannot open any other page, and they cannot see
another student's marks. It does not matter whether the admin or a teacher
entered the marks: the student sees their own result either way.

**How it works.** Every student, exam and subject row carries an `owner_id`:

- `owner_id = NULL` — created by the admin, so it belongs to the **school** and
  every logged-in user can see it (and enter marks for it). Only the admin can
  edit or delete it.
- `owner_id = <user id>` — created by a teacher, so it is **private** to that
  teacher. Nobody else sees it, and only that teacher can edit or delete it.

The tables show an **Owner** column: `School` for shared rows, `You` for your
own, or the username when the admin is looking.

So if the admin sets up the students, the exams and the papers, every teacher
sees that same setup and can fill in the marks — while each teacher's own extra
records stay invisible to the others.

Two admin rules: an admin cannot disable or delete **their own** account, and an
account that still owns records cannot be deleted (deactivate it instead), so no
data is silently lost. Passwords are stored as salted hashes, never as plain
text.

## Keeping the data (Render's free plan deletes it)

A free Render web service has an **ephemeral disk**: every restart, redeploy or
period of inactivity wipes the SQLite file, so students, marks and accounts
disappear. Two ways out.

### A. A free cloud database (recommended, no card needed)

The app speaks to **Turso**, a hosted SQLite. When `TURSO_URL` is set it uses
that instead of the local file, and nothing else changes.

1. Sign up free at <https://turso.tech> (GitHub login works).
2. **Create Database** — name it `jindal-school`, pick the region closest to you
   (`aws-ap-south-1` for India).
3. Copy the **Database URL** — it looks like
   `libsql://jindal-school-yourname.turso.io`.
4. Click **Create Token** and copy the token.
5. In Render → your service → **Environment**, add:
   - `TURSO_URL` = the `libsql://…` URL
   - `TURSO_TOKEN` = the token
6. **Save** and redeploy. The tables are created automatically on the first boot.

From then on the data lives in Turso, so restarts and redeploys change nothing.

### B. A Render disk (paid instance)

Upgrade the service to **Starter**, then **Disks → Add Disk**, mount path
`/var/data`, and set `DB_PATH=/var/data/exam_manager.db`. Simple, but about
$7/month.

### Checking which database is in use

`/healthz` shows the database path while you are logged in, and the sidebar
footer says `SQLite` or `Cloud (Turso)`.

## Data persistence — read this

Everything is stored in a SQLite file. On Render's **free** plan the filesystem
is temporary, so **the database is wiped whenever the service is redeployed or
restarted** — accounts included.

- fine for a demo — export the CSVs before redeploying;
- add a **Render Disk** mounted at `/var/data` and set
  `DB_PATH=/var/data/exam_manager.db` so data and accounts survive restarts;
- or move to PostgreSQL later (the SQL is plain).

The free instance also sleeps after ~15 minutes without traffic, so the first
visit after a break takes a few seconds.

## Run it locally

```bash
pip install -r requirements.txt
ADMIN_PASSWORD=admin123 python app.py        # http://127.0.0.1:5000
```

## Troubleshooting

Log in, then open `/healthz` on the live site — it lists exactly what is
wrong (logged out it deliberately reveals nothing):

| Check | Meaning if it fails |
|---|---|
| `built-in templates` | should always be *all present* — the pages are inside `app.py` |
| `database writable` | `DB_PATH` points somewhere that does not exist, or the disk is not mounted |
| `admin account` | no active admin exists — nobody can log in; set `ADMIN_PASSWORD` and redeploy |
| `app.py loaded` | shows the path the file was found at |

A 500 page shows the same checklist plus the traceback instead of a blank
“Internal Server Error”. If the service does not start at all (502 / no open
ports), `app.py` is not at the repository root, or the Start Command is wrong.

## Security checklist

- [ ] `ADMIN_PASSWORD` set to something strong
- [ ] `SECRET_KEY` set to a random value
- [ ] One account per teacher — do not share a single login
- [ ] Nobody gets a login they do not need
- [ ] Link shared only with school staff, not posted publicly
- [ ] You know the free plan can reset the database — export CSVs regularly
- [ ] Student data on a hosted server is the school's responsibility under
      India's DPDP Act, 2023; the app stores it on the server you chose and
      sends it nowhere else

## Feature notes

- The exam **type** is the exam's name; the same type cannot be created twice
  for one class and academic year.
- Exams are labelled `Type · Class · Year` everywhere.
- Date of admission is typed by the user — nothing is auto-filled.
- Marks entry saves the whole sheet at once; out-of-range values are ignored.
- Results show total, percentage, CBSE grade (A1…E), failed subjects, pass/fail
  and rank with ties.
- CSV export for the student list and the result sheet (only your own rows,
  unless you are the admin).
