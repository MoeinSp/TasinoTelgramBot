"""Helpers for idempotent schema changes on partially-migrated DBs."""
from __future__ import annotations


def column_exists(schema_editor, table: str, column: str) -> bool:
    conn = schema_editor.connection
    with conn.cursor() as cursor:
        if conn.vendor == "postgresql":
            cursor.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = %s AND column_name = %s
                """,
                [table, column],
            )
            return cursor.fetchone() is not None
        cursor.execute(f"PRAGMA table_info({table})")
        return column in {row[1] for row in cursor.fetchall()}


def table_exists(schema_editor, table: str) -> bool:
    conn = schema_editor.connection
    with conn.cursor() as cursor:
        if conn.vendor == "postgresql":
            cursor.execute(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_name = %s
                """,
                [table],
            )
            return cursor.fetchone() is not None
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            [table],
        )
        return cursor.fetchone() is not None


def index_exists(schema_editor, index_name: str) -> bool:
    conn = schema_editor.connection
    with conn.cursor() as cursor:
        if conn.vendor == "postgresql":
            cursor.execute("SELECT 1 FROM pg_class WHERE relname = %s", [index_name])
            return cursor.fetchone() is not None
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
            [index_name],
        )
        return cursor.fetchone() is not None


def constraint_exists(schema_editor, constraint_name: str) -> bool:
    conn = schema_editor.connection
    with conn.cursor() as cursor:
        if conn.vendor == "postgresql":
            cursor.execute(
                "SELECT 1 FROM pg_constraint WHERE conname = %s",
                [constraint_name],
            )
            return cursor.fetchone() is not None
        return False


def add_column_sql(schema_editor, table: str, column: str, sql_type: str) -> None:
    """sql_type example: 'bigint NULL' or 'boolean DEFAULT false NOT NULL'."""
    if column_exists(schema_editor, table, column):
        return
    conn = schema_editor.connection
    with conn.cursor() as cursor:
        cursor.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {sql_type}')


def ensure_index(schema_editor, sql_create: str, index_name: str) -> None:
    if index_exists(schema_editor, index_name):
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(sql_create)


def rename_index_if_needed(schema_editor, old_name: str, new_name: str) -> None:
    if index_exists(schema_editor, new_name):
        return
    if not index_exists(schema_editor, old_name):
        return
    conn = schema_editor.connection
    with conn.cursor() as cursor:
        if conn.vendor == "postgresql":
            cursor.execute(f'ALTER INDEX "{old_name}" RENAME TO "{new_name}"')
