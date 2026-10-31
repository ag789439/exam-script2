#!/usr/bin/env python3
"""
migrate_sqlite_to_postgres.py
=============================
Copy the records from the old SQLite file (exam_manager.db) into the
PostgreSQL database that DATABASE_URL points at.

Safe by design
--------------
* It never drops, truncates or recreates anything.
* Existing PostgreSQL rows are never overwritten: a row that is already
  there (same admission number / subject code / exam / mark) is skipped.
* Original ids are kept, so every foreign key still points at the right
  record. If an id is already taken by a different row, the row is inserted
  with a fresh id and its children are re-pointed automatically.
* One transaction: if anything fails, nothing is written.
* --dry-run does the whole job and then rolls it back, so you can look at
  the report before touching real data.

Usage
-----
    export DATABASE_URL="postgresql://.../exampro"     # Render: External Database URL
    python migrate_sqlite_to_postgres.py --dry-run     # report only
    python migrate_sqlite_to_postgres.py               # do it
    python migrate_sqlite_to_postgres.py --verify      # compare both sides

    # optional: point at a different SQLite file
    python migrate_sqlite_to_postgres.py --sqlite /path/to/exam_manager.db
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime

import psycopg

import db as pgdb

# Parents before children - foreign keys need the parents first.
ORDER = ["students", "exams", "subjects", "exam_schedule", "marks"]

TIMESTAMP_COLUMNS = {("students", "created_at"), ("exams", "created_at"),
                     ("subjects", "created_at"), ("marks", "updated_at")}

TIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y")


# --------------------------------------------------------------------------
#  reading the old file
# --------------------------------------------------------------------------
def open_sqlite(path):
    if not os.path.exists(path):
        sys.exit(f"SQLite file not found: {path}\n"
                 f"Pass the right path with --sqlite /path/to/exam_manager.db")
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def sqlite_tables(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


def sqlite_rows(conn, table):
    cur = conn.execute(f'SELECT * FROM "{table}" ORDER BY id')
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


# --------------------------------------------------------------------------
#  small helpers
# --------------------------------------------------------------------------
def norm(value):
    return ("" if value is None else str(value)).strip()


def parse_timestamp(value):
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def key_students(row):
    return (norm(row.get("admission_no")).lower(),)


def key_exams(row):
    return (norm(row.get("exam_type") or row.get("exam_name")).lower(),
            norm(row.get("academic_year")).lower(),
            norm(row.get("class_name")).lower())


def key_subjects(row):
    return (norm(row.get("subject_code")).upper(),)


def key_exam_schedule(row):
    return (row.get("exam_id"), row.get("subject_id"))


def key_marks(row):
    return (row.get("exam_id"), row.get("student_id"), row.get("subject_id"))


KEY_FUNCS = {
    "students": key_students,
    "exams": key_exams,
    "subjects": key_subjects,
    "exam_schedule": key_exam_schedule,
    "marks": key_marks,
}


def target_columns(conn, table):
    """{column_name: data_type} for a PostgreSQL table."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name, data_type FROM information_schema.columns"
            " WHERE table_schema = current_schema() AND table_name = %s",
            (table,))
        return {r["column_name"]: r["data_type"] for r in cur.fetchall()}


def coerce(table, column, value, data_type):
    """Make a SQLite value acceptable to the PostgreSQL column type."""
    if (table, column) in TIMESTAMP_COLUMNS:
        return parse_timestamp(value)
    if value is None:
        return None
    if data_type in ("text", "character varying", "character"):
        if isinstance(value, bytes):
            return value.decode("utf-8", "replace")
        return value if isinstance(value, str) else str(value)
    if data_type in ("integer", "bigint", "smallint"):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None
    if data_type in ("double precision", "real", "numeric"):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return value


def insert_row(conn, table, row, columns, use_id):
    names = list(columns)
    values = [coerce(table, c, row.get(c), columns[c]) for c in names]
    if use_id:
        names.append("id")
        values.append(int(row["id"]))
    placeholders = ",".join(["%s"] * len(names))
    sql = (f'INSERT INTO "{table}" ({",".join(names)})'
           f' VALUES ({placeholders}) RETURNING id')
    with conn.cursor() as cur:
        cur.execute(sql, values)
        return cur.fetchone()["id"]


def existing_keys(conn, table):
    """{natural key: id} for the rows already in PostgreSQL."""
    cols = target_columns(conn, table)
    select = [c for c in ("id", "admission_no", "exam_type", "exam_name",
                          "academic_year", "class_name", "subject_code",
                          "exam_id", "subject_id", "student_id") if c in cols]
    with conn.cursor() as cur:
        cur.execute(f'SELECT {",".join(select)} FROM "{table}"')
        rows = cur.fetchall()
    out = {}
    for row in rows:
        out[KEY_FUNCS[table](row)] = row["id"]
    return out


# --------------------------------------------------------------------------
#  the migration itself
# --------------------------------------------------------------------------
def migrate(sqlite_path, dry_run=False):
    lite = open_sqlite(sqlite_path)
    tables = sqlite_tables(lite)

    if dry_run:
        print("DRY RUN - no records will be written; everything is rolled "
              "back.\n(Empty tables are still created if they do not exist "
              "yet - that never touches existing data.)\n")
    # Creates only what is missing: tables, columns, indexes. Nothing dropped.
    pgdb.ensure_schema()
    conn = pgdb.connect()

    report = {}
    id_maps = {t: {} for t in ORDER}
    problems = []

    try:
        for table in ORDER:
            if table not in tables:
                report[table] = (0, 0, 0, "no such table in the SQLite file")
                continue

            source = sqlite_rows(lite, table)
            if not source:
                report[table] = (0, 0, 0, "")
                continue

            columns = target_columns(conn, table)
            if not columns:
                problems.append(f"PostgreSQL table {table} is missing - run "
                                f"the app once, then retry.")
                report[table] = (len(source), 0, len(source), "table missing")
                continue

            already = existing_keys(conn, table)
            inserted = skipped = 0

            for row in source:
                key = KEY_FUNCS[table](row)

                # Children: remap parent ids from SQLite to PostgreSQL.
                if table == "exam_schedule":
                    row = dict(row)
                    row["exam_id"] = id_maps["exams"].get(row.get("exam_id"))
                    row["subject_id"] = id_maps["subjects"].get(row.get("subject_id"))
                    if row["exam_id"] is None or row["subject_id"] is None:
                        skipped += 1
                        continue
                    key = key_exam_schedule(row)
                elif table == "marks":
                    row = dict(row)
                    row["exam_id"] = id_maps["exams"].get(row.get("exam_id"))
                    row["student_id"] = id_maps["students"].get(row.get("student_id"))
                    row["subject_id"] = id_maps["subjects"].get(row.get("subject_id"))
                    if (row["exam_id"] is None or row["student_id"] is None
                            or row["subject_id"] is None):
                        skipped += 1
                        continue
                    key = key_marks(row)

                if key in already:
                    # Already in PostgreSQL: keep it, remember its id.
                    if row.get("id") is not None:
                        id_maps[table][row["id"]] = already[key]
                    skipped += 1
                    continue

                # "id" is added separately when we keep the old id.
                usable = {c: columns[c] for c in columns
                          if c in row and c != "id"}
                try:
                    with conn.transaction():
                        new_id = insert_row(conn, table, row, usable,
                                            use_id=row.get("id") is not None)
                except psycopg.errors.UniqueViolation:
                    # The id is taken by a different row - let PostgreSQL
                    # choose a new one. Children are re-pointed below.
                    try:
                        with conn.transaction():
                            new_id = insert_row(conn, table, row, usable,
                                                use_id=False)
                    except Exception as exc:            # noqa: BLE001
                        problems.append(f"{table} id={row.get('id')}: {exc}")
                        continue
                except Exception as exc:                # noqa: BLE001
                    problems.append(f"{table} id={row.get('id')}: {exc}")
                    continue

                if row.get("id") is not None:
                    id_maps[table][row["id"]] = new_id
                already[key] = new_id
                inserted += 1

            report[table] = (len(source), inserted, skipped, "")

        if dry_run:
            conn.rollback()
        else:
            conn.commit()
            pgdb.reset_sequences(conn)
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
        lite.close()

    print(f"{'table':<15}{'in SQLite':>11}{'inserted':>10}{'skipped':>9}  note")
    print("-" * 62)
    for table in ORDER:
        read, inserted, skipped, note = report.get(table, (0, 0, 0, ""))
        print(f"{table:<15}{read:>11}{inserted:>10}{skipped:>9}  {note}")
    print("-" * 62)
    total_in = sum(r[1] for r in report.values())
    print(f"{'TOTAL':<15}{'':>11}{total_in:>10}")
    if dry_run:
        print("\nNothing was saved (dry run). Run again without --dry-run.")
    else:
        print("\nDone. Id sequences were moved past the highest id, so new "
              "records will not clash with the copied ones.")
    if problems:
        print("\nRows that could not be copied:")
        for p in problems[:40]:
            print("  -", p)
        if len(problems) > 40:
            print(f"  ... and {len(problems) - 40} more")


# --------------------------------------------------------------------------
#  verification
# --------------------------------------------------------------------------
def verify(sqlite_path):
    lite = open_sqlite(sqlite_path)
    tables = sqlite_tables(lite)
    conn = pgdb.connect()
    try:
        print("Row counts: SQLite (old) vs PostgreSQL (live)")
        print("-" * 52)
        print(f"{'table':<15}{'SQLite':>10}{'PostgreSQL':>14}")
        print("-" * 52)
        for table in ORDER:
            old = ("-")
            if table in tables:
                old = lite.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            try:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT COUNT(*) AS c FROM {table}")
                    new = cur.fetchone()["c"]
            except Exception:                          # noqa: BLE001
                conn.rollback()
                new = "MISSING"
            print(f"{table:<15}{old:>10}{new:>14}")

        print("\nIntegrity checks")
        print("-" * 52)
        checks = [
            ("marks with a missing student",
             "SELECT COUNT(*) AS c FROM marks m LEFT JOIN students s"
             " ON s.id = m.student_id WHERE s.id IS NULL"),
            ("marks with a missing exam",
             "SELECT COUNT(*) AS c FROM marks m LEFT JOIN exams e"
             " ON e.id = m.exam_id WHERE e.id IS NULL"),
            ("marks with a missing subject",
             "SELECT COUNT(*) AS c FROM marks m LEFT JOIN subjects s"
             " ON s.id = m.subject_id WHERE s.id IS NULL"),
            ("schedule rows with a missing exam",
             "SELECT COUNT(*) AS c FROM exam_schedule sc LEFT JOIN exams e"
             " ON e.id = sc.exam_id WHERE e.id IS NULL"),
            ("students without an admission number",
             "SELECT COUNT(*) AS c FROM students"
             " WHERE admission_no IS NULL OR btrim(admission_no) = ''"),
            ("students with a password set",
             "SELECT COUNT(*) AS c FROM students"
             " WHERE password_hash IS NOT NULL"),
            ("teacher logins", "SELECT COUNT(*) AS c FROM teachers"),
            ("admin logins", "SELECT COUNT(*) AS c FROM auth_admins"),
        ]
        for label, sql in checks:
            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    value = cur.fetchone()["c"]
                print(f"  {label:<40} {value}")
            except Exception as exc:                   # noqa: BLE001
                conn.rollback()
                print(f"  {label:<40} ERROR: {exc}")

        print("\nFirst students in PostgreSQL")
        print("-" * 52)
        with conn.cursor() as cur:
            cur.execute("SELECT id, admission_no, name, class_name, section,"
                        " (password_hash IS NOT NULL) AS has_password"
                        " FROM students ORDER BY id LIMIT 10")
            for r in cur.fetchall():
                print(f"  {r['id']:>4}  {r['admission_no']:<12}"
                      f"{r['name'][:26]:<28}{r['class_name'] or '':<8}"
                      f"{'password set' if r['has_password'] else 'no password'}")
    finally:
        conn.close()
        lite.close()


def main():
    parser = argparse.ArgumentParser(
        description="Copy old SQLite records into the PostgreSQL database "
                    "used by ExamPro (safe, repeatable, non-destructive).")
    parser.add_argument("--sqlite", default=os.environ.get("DB_PATH")
                        or "exam_manager.db",
                        help="path to the old SQLite file "
                             "(default: ./exam_manager.db)")
    parser.add_argument("--dry-run", action="store_true",
                        help="do everything, then roll it back")
    parser.add_argument("--verify", action="store_true",
                        help="compare both databases and run integrity checks")
    args = parser.parse_args()

    try:
        info = pgdb.connection_info()
    except Exception as exc:                            # noqa: BLE001
        sys.exit(f"DATABASE_URL problem: {exc}")

    print("ExamPro SQLite -> PostgreSQL migration")
    print(f"  source : {os.path.abspath(args.sqlite)}")
    print(f"  target : PostgreSQL {info['host']}:{info['port']}"
          f"/{info['database']} as {info['user']}")
    print("  tip    : back up first - see MIGRATION_GUIDE.md, step 1\n")

    if args.verify:
        verify(args.sqlite)
        return
    migrate(args.sqlite, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
