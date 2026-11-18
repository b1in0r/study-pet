"""Small persistent task store; no model or background scheduler required."""

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("时间必须包含时区，例如 2026-11-14T19:00:00+08:00")
    return value.astimezone(timezone.utc)


class TaskStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                due_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'done'))
            )""")

    def _connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def add(self, title: str, due_at: datetime) -> int:
        title = title.strip()
        if not title:
            raise ValueError("任务标题不能为空")
        due = aware_utc(due_at).isoformat(timespec="microseconds")
        with closing(self._connect()) as db, db:
            cursor = db.execute(
                "INSERT INTO tasks (title, due_at) VALUES (?, ?)", (title, due)
            )
            return cursor.lastrowid

    def list(self, due_before: datetime | None = None) -> list[dict]:
        query = "SELECT id, title, due_at, status FROM tasks"
        params = ()
        if due_before is not None:
            query += " WHERE status = 'pending' AND due_at <= ?"
            params = (aware_utc(due_before).isoformat(timespec="microseconds"),)
        query += " ORDER BY due_at, id"
        with closing(self._connect()) as db:
            return [dict(row) for row in db.execute(query, params)]

    def complete(self, task_id: int) -> None:
        self.update(task_id, status="done")

    def update(self, task_id: int, *, title: str | None = None,
               due_at: datetime | None = None, status: str | None = None) -> None:
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
            cursor = db.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", (*params, task_id))
            if cursor.rowcount == 0:
                raise ValueError(f"找不到任务 {task_id}")

    def delete(self, task_id: int) -> None:
        with closing(self._connect()) as db, db:
            cursor = db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            if cursor.rowcount == 0:
                raise ValueError(f"找不到任务 {task_id}")
