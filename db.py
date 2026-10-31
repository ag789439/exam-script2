"""
db.py - the one and only database layer for ExamPro (PostgreSQL).

Both app.py (students, exams, subjects, schedule, marks) and
auth_system.py (logins, passwords) import THIS file, so they are always
talking to the same database: whatever DATABASE_URL points at.

Nothing in here ever drops or recreates a table. Every step is
"CREATE ... IF NOT EXISTS" or "ALTER TABLE ... ADD COLUMN IF NOT EXISTS",
so running it against a database that already holds records is safe.

Environment variable
    DATABASE_URL   postgresql://user:password@host:5432/dbname
                   (Render fills this in automatically when the Postgres
                   service is attached to the web service)
"""

from __future__ import annotations

import os
import threading
from urllib.parse import urlsplit

import psycopg
from psycopg.rows import dict_row

# The five tables of the examination module ...
CORE_TABLES = ("students", "exams", "subjects", "exam_schedule", "marks")
# ... plus the two login tables added by auth_system.py.
AUTH_TABLES = ("teachers", "auth_admins")
ALL_TABLES = CORE_TABLES + AUTH_TABLES


# --------------------------------------------------------------------------
#  connection
# --------------------------------------------------------------------------
def database_url() -> str:
    """DATABASE_URL, normalised for psycopg (postgres:// -> postgresql://)."""
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. ExamPro keeps every record in "
            "PostgreSQL, so this variable must point at your database. "
            "On Render: open the web service > Environment and either attach "
            "the Postgres service or paste its Internal Database URL."
        )
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def connect():
    """A new connection that returns rows as dictionaries."""
    return psycopg.connect(database_url(), row_factory=dict_row,
                           connect_timeout=15)


def connection_info() -> dict:
    """Host / database / user of DATABASE_URL - never the password."""
    parts = urlsplit(database_url())
    return {
        "host": parts.hostname or "(local socket)",
        "port": parts.port or 5432,
        "database": (parts.path or "/").lstrip("/") or "(default)",
        "user": parts.username or "(default)",
    }


# --------------------------------------------------------------------------
#  schema - exactly the five tables the app already had, in PostgreSQL form
# --------------------------------------------------------------------------
CREATE_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS students (
        id             BIGSERIAL PRIMARY KEY,
        admission_no   TEXT NOT NULL,
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
        password_hash  TEXT,
        created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT students_admission_no_key UNIQUE (admission_no)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS exams (
        id            BIGSERIAL PRIMARY KEY,
        exam_name     TEXT NOT NULL,
        exam_type     TEXT,
        academic_year TEXT,
        class_name    TEXT,
        start_date    TEXT,
        end_date      TEXT,
        status        TEXT DEFAULT 'Scheduled',
        remarks       TEXT,
        created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS subjects (
        id           BIGSERIAL PRIMARY KEY,
        subject_code TEXT NOT NULL,
        subject_name TEXT NOT NULL,
        class_name   TEXT,
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT subjects_subject_code_key UNIQUE (subject_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS exam_schedule (
        id          BIGSERIAL PRIMARY KEY,
        exam_id     BIGINT NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
        subject_id  BIGINT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
        exam_date   TEXT,
        start_time  TEXT,
        duration    INTEGER,
        room        TEXT,
        invigilator TEXT,
        max_marks   DOUBLE PRECISION DEFAULT 100,
        pass_marks  DOUBLE PRECISION DEFAULT 33,
        CONSTRAINT exam_schedule_exam_id_subject_id_key
            UNIQUE (exam_id, subject_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS marks (
        id             BIGSERIAL PRIMARY KEY,
        exam_id        BIGINT NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
        student_id     BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
        subject_id     BIGINT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
        marks_obtained DOUBLE PRECISION,
        remarks        TEXT,
        status         TEXT DEFAULT 'ENTERED',
        updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT marks_exam_id_student_id_subject_id_key
            UNIQUE (exam_id, student_id, subject_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS teachers (
        id            BIGSERIAL PRIMARY KEY,
        username      TEXT UNIQUE NOT NULL,
        full_name     TEXT NOT NULL,
        password_hash TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_admins (
        id            BIGSERIAL PRIMARY KEY,
        username      TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    )
    """,
]

# Every column the app expects, per table. If an older / hand-made
# PostgreSQL table is missing one of them, it is added (nullable, so
# existing rows are untouched).
COLUMNS = {
    "students": [
        ("admission_no", "TEXT"), ("roll_no", "TEXT"), ("name", "TEXT"),
        ("class_name", "TEXT"), ("section", "TEXT"), ("dob", "TEXT"),
        ("gender", "TEXT"), ("father_name", "TEXT"), ("mother_name", "TEXT"),
        ("phone", "TEXT"), ("email", "TEXT"), ("address", "TEXT"),
        ("admission_date", "TEXT"), ("status", "TEXT DEFAULT 'Active'"),
        ("password_hash", "TEXT"),
        ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ],
    "exams": [
        ("exam_name", "TEXT"), ("exam_type", "TEXT"), ("academic_year", "TEXT"),
        ("class_name", "TEXT"), ("start_date", "TEXT"), ("end_date", "TEXT"),
        ("status", "TEXT DEFAULT 'Scheduled'"), ("remarks", "TEXT"),
        ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ],
    "subjects": [
        ("subject_code", "TEXT"), ("subject_name", "TEXT"), ("class_name", "TEXT"),
        ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ],
    "exam_schedule": [
        ("exam_id", "BIGINT"), ("subject_id", "BIGINT"), ("exam_date", "TEXT"),
        ("start_time", "TEXT"), ("duration", "INTEGER"), ("room", "TEXT"),
        ("invigilator", "TEXT"), ("max_marks", "DOUBLE PRECISION DEFAULT 100"),
        ("pass_marks", "DOUBLE PRECISION DEFAULT 33"),
    ],
    "marks": [
        ("exam_id", "BIGINT"), ("student_id", "BIGINT"), ("subject_id", "BIGINT"),
        ("marks_obtained", "DOUBLE PRECISION"), ("remarks", "TEXT"),
        ("status", "TEXT DEFAULT 'ENTERED'"),
        ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ],
    "teachers": [
        ("username", "TEXT"), ("full_name", "TEXT"), ("password_hash", "TEXT"),
    ],
    "auth_admins": [
        ("username", "TEXT"), ("password_hash", "TEXT"),
    ],
}

# Unique constraints and helpful indexes. The names match what PostgreSQL
# generates for the UNIQUE (...) clauses above, so IF NOT EXISTS finds them.
INDEXES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS students_admission_no_key"
    " ON students (admission_no)",
    "CREATE UNIQUE INDEX IF NOT EXISTS subjects_subject_code_key"
    " ON subjects (subject_code)",
    "CREATE UNIQUE INDEX IF NOT EXISTS exam_schedule_exam_id_subject_id_key"
    " ON exam_schedule (exam_id, subject_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS marks_exam_id_student_id_subject_id_key"
    " ON marks (exam_id, student_id, subject_id)",
    "CREATE INDEX IF NOT EXISTS students_class_name_idx"
    " ON students (class_name)",
    "CREATE INDEX IF NOT EXISTS marks_exam_id_idx ON marks (exam_id)",
    "CREATE INDEX IF NOT EXISTS marks_student_id_idx ON marks (student_id)",
]

TIMESTAMP_COLUMNS = [
    ("students", "created_at"),
    ("exams", "created_at"),
    ("subjects", "created_at"),
    ("marks", "updated_at"),
]

_lock = threading.Lock()
_ready = False


def _try(conn, sql, params=None):
    """Run one statement inside a savepoint; never abort the whole batch."""
    try:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
        return True, None
    except Exception as exc:                      # noqa: BLE001 - report only
        return False, str(exc).strip().splitlines()[0] if str(exc).strip() else repr(exc)


def _column_type(conn, table, column):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT data_type FROM information_schema.columns"
            " WHERE table_schema = current_schema()"
            "   AND table_name = %s AND column_name = %s",
            (table, column))
        row = cur.fetchone()
    return row["data_type"] if row else None


def _ensure_id_sequence(conn, table):
    """Give <table>.id a working default, even on a hand-made table."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_default FROM information_schema.columns"
            " WHERE table_schema = current_schema()"
            "   AND table_name = %s AND column_name = 'id'", (table,))
        row = cur.fetchone()
    if row is None or row["column_default"]:
        return                                    # BIGSERIAL already fine
    seq = f"{table}_id_seq"
    ok, _err = _try(conn, f'CREATE SEQUENCE IF NOT EXISTS "{seq}"')
    if not ok:
        return
    _try(conn, f'ALTER TABLE "{table}" ALTER COLUMN id SET DEFAULT'
               f" nextval('{seq}')")
    # OWNED BY makes pg_get_serial_sequence() find it, which is what
    # reset_sequences() uses to move the counter past the stored ids.
    _try(conn, f'ALTER SEQUENCE "{seq}" OWNED BY "{table}".id')


def reset_sequences(conn=None):
    """Move every id sequence past the highest id already stored.

    Needed after copying old SQLite rows with their original ids, otherwise
    the next INSERT would try to reuse an id and fail with a duplicate key.
    """
    own = conn is None
    conn = conn or connect()
    try:
        with conn.cursor() as cur:
            for table in ALL_TABLES:
                cur.execute("SELECT pg_get_serial_sequence(%s, 'id') AS seq",
                            (table,))
                seq = cur.fetchone()["seq"]
                if not seq:
                    # A table created by hand may have its sequence named
                    # the conventional way but not owned by the column.
                    cur.execute("SELECT to_regclass(%s) AS reg",
                                (f"{table}_id_seq",))
                    seq = cur.fetchone()["reg"]
                if not seq:
                    continue
                cur.execute(
                    "SELECT setval(%s::regclass,"
                    " GREATEST(COALESCE(MAX(id), 1), 1)) FROM " + table,
                    (seq,))
        if own:
            conn.commit()
    finally:
        if own:
            conn.close()


def _apply_schema(conn):
    with conn.cursor() as cur:
        for statement in CREATE_TABLES:
            cur.execute(statement)

    # Add anything an older table is missing (never destructive).
    for table, columns in COLUMNS.items():
        for column, ddl_type in columns:
            _try(conn, f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS'
                       f' "{column}" {ddl_type}')

    # created_at / updated_at may be TEXT in a table somebody created by
    # hand; the app writes real timestamps, so normalise the type.
    for table, column in TIMESTAMP_COLUMNS:
        if _column_type(conn, table, column) in ("text", "character varying"):
            _try(conn,
                 f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE timestamp'
                 f' USING NULLIF(btrim("{column}"::text), \'\')::timestamp')

    for table in ALL_TABLES:
        _ensure_id_sequence(conn, table)

    for statement in INDEXES:
        _try(conn, statement)          # fails harmlessly if duplicates exist

    reset_sequences(conn)


def ensure_schema(force: bool = False) -> None:
    """Create / repair the schema. Runs once per process, then is a no-op."""
    global _ready
    with _lock:
        if _ready and not force:
            return
        with connect() as conn:        # commits on success, closes either way
            _apply_schema(conn)
        _ready = True


def schema_ready() -> bool:
    return _ready


# --------------------------------------------------------------------------
#  read-only helpers (used by /healthz and the migration script)
# --------------------------------------------------------------------------
def table_counts(conn=None) -> dict:
    """{table: row count or None when the table is missing}."""
    own = conn is None
    conn = conn or connect()
    counts = {}
    try:
        for table in ALL_TABLES:
            try:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT COUNT(*) AS c FROM {table}")
                    counts[table] = cur.fetchone()["c"]
            except Exception:                     # noqa: BLE001
                counts[table] = None
                try:
                    conn.rollback()
                except Exception:                 # noqa: BLE001
                    pass
    finally:
        if own:
            conn.close()
    return counts
