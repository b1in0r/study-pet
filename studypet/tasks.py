"""Small persistent task store; no model or background scheduler required."""

import json
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .storage.database import connect_database
from .storage.migrate import initialize_database


def aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("时间必须包含时区，例如 2026-11-14T19:00:00+08:00")
    return value.astimezone(timezone.utc)


class TaskStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        initialize_database(self.path)

    def _connect(self):
        return connect_database(self.path)

    @staticmethod
    def event(db, kind, task_id=None, before=None, after=None, source='user', now=None):
        stamp = aware_utc(now or datetime.now(timezone.utc)).isoformat(timespec='microseconds')
        db.execute('''INSERT INTO task_events (task_id, kind, at, before_json, after_json, source)
                      VALUES (?, ?, ?, ?, ?, ?)''',
                   (task_id, kind, stamp, json.dumps(before,ensure_ascii=False) if before is not None else None,
                    json.dumps(after,ensure_ascii=False) if after is not None else None, source))

    def add(self, title: str, due_at: datetime) -> int:
        title = title.strip()
        if not title:
            raise ValueError("任务标题不能为空")
        due = aware_utc(due_at).isoformat(timespec="microseconds")
        with closing(self._connect()) as db, db:
            now = datetime.now(timezone.utc).isoformat(timespec='microseconds')
            cursor = db.execute(
                "INSERT INTO tasks (title, due_at, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (title, due, now, now)
            )
            task_id = cursor.lastrowid
            row = dict(db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone())
            self.event(db, 'created', task_id, after=row)
            return task_id

    def list(self, due_before: datetime | None = None) -> list[dict]:
        query = "SELECT * FROM tasks WHERE deleted_at IS NULL"
        params = ()
        if due_before is not None:
            query += " AND status = 'pending' AND due_at <= ?"
            params = (aware_utc(due_before).isoformat(timespec="microseconds"),)
        query += " ORDER BY due_at, id"
        with closing(self._connect()) as db:
            return [dict(row) for row in db.execute(query, params)]

    def complete(self, task_id: int) -> None:
        self.update(task_id, status="done")

    def update(self, task_id: int, *, title: str | None = None,
               due_at: datetime | None = None, status: str | None = None,
               expected_revision: int | None = None) -> None:
        fields, params = [], []
        if title is not None:
            title = title.strip()
            if not title:
                raise ValueError("任务标题不能为空")
            fields.append("title = ?")
            params.append(title)
        if due_at is not None:
            fields.append("due_at = ?")
            params.append(aware_utc(due_at).isoformat(timespec="microseconds"))
        if status is not None:
            if status not in ("pending", "done"):
                raise ValueError("任务状态必须是 pending 或 done")
            fields.append("status = ?")
            params.append(status)
        if not fields:
            raise ValueError("没有需要更新的内容")
        with closing(self._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM tasks WHERE id = ? AND deleted_at IS NULL', (task_id,)).fetchone()
            if old is None:
                raise ValueError(f"找不到任务 {task_id}")
            if expected_revision is not None and old['revision'] != expected_revision:
                raise ValueError('计划刚刚发生了变化，请刷新后重试')
            if ((title is None or title == old['title']) and
                    (due_at is None or aware_utc(due_at).isoformat(timespec='microseconds') == old['due_at']) and
                    (status is None or status == old['status'])):
                return
            if status is not None and status != old['status']:
                fields.append('completed_at = ?')
                params.append(datetime.now(timezone.utc).isoformat(timespec='microseconds') if status == 'done' else None)
            fields.extend(['updated_at = ?', 'revision = revision + 1'])
            params.append(datetime.now(timezone.utc).isoformat(timespec='microseconds'))
            cursor = db.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ? AND deleted_at IS NULL", (*params, task_id))
            if cursor.rowcount == 0:
                raise ValueError(f"找不到任务 {task_id}")
            new = dict(db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone())
            if new['status'] == 'done' or new['due_at'] != old['due_at']:
                db.execute("UPDATE reminders SET state = 'cancelled' WHERE task_id = ? AND state = 'unread'", (task_id,))
            kind = ('completed' if new['status'] == 'done' and old['status'] != 'done' else
                    'reopened' if new['status'] == 'pending' and old['status'] == 'done' else
                    'rescheduled' if new['due_at'] != old['due_at'] else 'updated')
            self.event(db, kind, task_id, before=dict(old), after=new)

    def delete(self, task_id: int) -> None:
        with closing(self._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM tasks WHERE id = ? AND deleted_at IS NULL', (task_id,)).fetchone()
            if old is None:
                raise ValueError(f"找不到任务 {task_id}")
            cursor = db.execute("UPDATE tasks SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
                                (datetime.now(timezone.utc).isoformat(timespec='microseconds'), task_id))
            if cursor.rowcount == 0:
                raise ValueError(f"找不到任务 {task_id}")
            db.execute("UPDATE reminders SET state = 'cancelled' WHERE task_id = ? AND state = 'unread'", (task_id,))
            self.event(db, 'deleted', task_id, before=dict(old))

    def history(self, limit=100):
        with closing(self._connect()) as db:
            rows = db.execute('SELECT * FROM task_events ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        return [dict(id=row['id'], task_id=row['task_id'], kind=row['kind'], at=row['at'], source=row['source'],
                     before=json.loads(row['before_json']) if row['before_json'] else None,
                     after=json.loads(row['after_json']) if row['after_json'] else None) for row in rows]
