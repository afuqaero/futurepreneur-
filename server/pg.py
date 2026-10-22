"""Small DB-API adapter that lets the SQLite-era code run on Neon Postgres.

The application talks to a tiny subset of sqlite3.Connection: execute,
executemany, executescript, commit/rollback, and named row access. This
adapter translates that surface to psycopg 3, including the few SQLite
dialect differences used by the migrations.
"""

import re

import psycopg
from psycopg.rows import dict_row


class Row(dict):
    """Dict row that also supports integer indexing, like sqlite3.Row."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class EmptyCursor:
    rowcount = 0

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def __iter__(self):
        return iter(())


class PgCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def fetchone(self):
        row = self._cursor.fetchone()
        return Row(row) if row is not None else None

    def fetchall(self):
        return [Row(row) for row in self._cursor.fetchall()]

    def __iter__(self):
        for row in self._cursor:
            yield Row(row)

    def close(self):
        self._cursor.close()


def _translate(sql):
    sql = re.sub(r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b", "SERIAL PRIMARY KEY", sql, flags=re.I)
    sql = re.sub(r"\bREAL\b", "DOUBLE PRECISION", sql, flags=re.I)
    return sql.replace("?", "%s")


def _split_script(sql):
    clean = re.sub(r"--[^\n]*", "", sql)
    for part in clean.split(";"):
        body = part.strip()
        if body:
            yield body


class PgConnection:
    def __init__(self, dsn):
        dsn = (dsn or "").strip().strip('"').strip("'")
        if not dsn:
            raise RuntimeError("DATABASE_URL is not configured")
        self._conn = psycopg.connect(dsn, row_factory=dict_row)

    def execute(self, sql, params=()):
        if re.match(r"^\s*PRAGMA\b", sql, flags=re.I):
            return EmptyCursor()
        cursor = self._conn.cursor()
        cursor.execute(_translate(sql), params)
        return PgCursor(cursor)

    def executemany(self, sql, seq):
        rows = list(seq)
        if not rows:
            return EmptyCursor()
        cursor = self._conn.cursor()
        cursor.executemany(_translate(sql), rows)
        return PgCursor(cursor)

    def executescript(self, sql):
        cursor = self._conn.cursor()
        for statement in _split_script(sql):
            cursor.execute(_translate(statement))
        return PgCursor(cursor)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()
        return False
