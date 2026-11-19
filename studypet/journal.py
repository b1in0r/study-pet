"""User-confirmed daily notes. Recordings are not persisted."""
import uuid
from contextlib import closing
from datetime import date, datetime, timezone

from .storage.database import connect_database


class JournalStore:
    def __init__(self, path):
        self.path = path

    def list(self, limit=50, before_id=None):
        with closing(connect_database(self.path)) as db:
            if before_id:
                cursor = db.execute(
                    'SELECT day,created_at,id FROM journal_entries WHERE id=?', (before_id,),
                ).fetchone()
                if cursor is None:
                    raise ValueError('分页位置已变化，请刷新日记')
                condition, params = 'WHERE (day,created_at,id) < (?,?,?)', (*cursor, limit)
            else:
                condition, params = '', (limit,)
            return [dict(row) for row in db.execute(f'''
                SELECT * FROM journal_entries {condition}
                ORDER BY day DESC,created_at DESC,id DESC LIMIT ?
            ''', params)]

    def save(self, day, body, ident=None):
        try:
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError
        except (TypeError, ValueError) as error:
            raise ValueError('请选择有效日期') from error
        if not isinstance(body, str) or not 0 < len(body.strip()) <= 4000:
            raise ValueError('日记需要 1–4000 字')
        now = datetime.now(timezone.utc).isoformat()
        with closing(connect_database(self.path)) as db, db:
            if ident is None:
                ident = str(uuid.uuid4())
                db.execute('INSERT INTO journal_entries VALUES (?,?,?,?,?)', (ident, day, body.strip(), now, now))
            else:
                result = db.execute('UPDATE journal_entries SET day=?,body=?,updated_at=? WHERE id=?',
                                    (day, body.strip(), now, ident))
                if not result.rowcount:
                    raise ValueError('找不到这篇日记')
        return ident

    def delete(self, ident):
        with closing(connect_database(self.path)) as db, db:
            if not db.execute('DELETE FROM journal_entries WHERE id=?', (ident,)).rowcount:
                raise ValueError('找不到这篇日记')
