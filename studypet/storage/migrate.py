"""Transactional, incremental migrations; never run the architecture draft."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .database import connect_database

SCHEMA_VERSION = 3


def _v1(db):
    db.execute("""CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY, title TEXT NOT NULL, due_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'done')))""")
    columns = {row['name'] for row in db.execute('PRAGMA table_info(tasks)')}
    for name, declaration in {'created_at':'TEXT', 'updated_at':'TEXT', 'completed_at':'TEXT',
                              'deleted_at':'TEXT', 'revision':'INTEGER NOT NULL DEFAULT 1'}.items():
        if name not in columns:
            db.execute(f'ALTER TABLE tasks ADD COLUMN {name} {declaration}')
    db.execute('''CREATE TABLE task_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER, kind TEXT NOT NULL,
        at TEXT NOT NULL, before_json TEXT, after_json TEXT, source TEXT NOT NULL)''')
    db.execute('''CREATE TABLE reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER NOT NULL,
        due_at TEXT NOT NULL, title TEXT NOT NULL, created_at TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'unread', desktop_state TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0, last_attempt_at TEXT, desktop_error TEXT,
        UNIQUE(task_id, due_at))''')
    db.execute('''CREATE TABLE memories (id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)''')
    db.execute('CREATE TABLE agent_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    db.executemany('INSERT INTO agent_settings VALUES (?, ?)',
                   [('reminders_enabled','true'), ('desktop_enabled','true')])
    now = datetime.now(timezone.utc).isoformat(timespec='microseconds')
    for row in db.execute('SELECT * FROM tasks').fetchall():
        db.execute('''INSERT INTO task_events(task_id,kind,at,after_json,source)
            VALUES (?,'snapshot_imported',?,?,'migration')''',
            (row['id'],now,json.dumps(dict(row),ensure_ascii=False)))


def _sql(db, filename):
    statement = ''
    for line in (Path(__file__).with_name('migrations') / filename).read_text(encoding='utf-8').splitlines(True):
        statement += line
        if sqlite3.complete_statement(statement):
            db.execute(statement)
            statement = ''
    if statement.strip():
        raise RuntimeError('迁移 SQL 不完整')


def initialize_database(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect_database(path)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError('数据库版本较新，请使用匹配的程序版本')
        if version < 1:
            _v1(db)
        if version < 2:
            _sql(db, '0002_document_library.sql')
        if version < 3:
            _sql(db, '0003_document_category.sql')
        db.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
