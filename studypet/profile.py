"""User-authored profile entries and references to local supporting documents."""
import uuid
from contextlib import closing
from datetime import datetime, timezone

from .storage.database import connect_database

PROFILE_KINDS = {
    'stage': '当前阶段',
    'experience': '经历',
    'skill': '能力',
    'goal': '目标',
    'constraint': '偏好与约束',
}


class ProfileStore:
    def __init__(self, path):
        self.path = path

    def list(self):
        with closing(connect_database(self.path)) as db:
            return [dict(row) for row in db.execute('''
                SELECT p.*, d.title AS document_title
                FROM profile_entries p
                LEFT JOIN documents d ON d.id = p.document_id AND d.state <> 'deleted'
                ORDER BY p.created_at DESC, p.id
            ''')]

    def save(self, body, ident=None):
        kind, title, details = (body.get(key) for key in ('kind', 'title', 'details'))
        document_id = body.get('document_id')
        if not isinstance(kind, str) or kind not in PROFILE_KINDS:
            raise ValueError('请选择档案类型')
        if not isinstance(title, str) or not 0 < len(title.strip()) <= 120:
            raise ValueError('标题需要 1–120 字')
        if not isinstance(details, str) or not 0 < len(details.strip()) <= 4000:
            raise ValueError('内容需要 1–4000 字')
        if document_id is not None and (not isinstance(document_id, str) or len(document_id) != 36):
            raise ValueError('请选择资料库中的文件')

        now = datetime.now(timezone.utc).isoformat(timespec='microseconds')
        values = (kind, title.strip(), details.strip(), document_id, now)
        with closing(connect_database(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            if document_id is not None:
                document = db.execute(
                    "SELECT id FROM documents WHERE id=? AND state NOT IN ('deleted','importing')",
                    (document_id,),
                ).fetchone()
                if document is None:
                    raise ValueError('关联资料已移除或仍在导入，请刷新后重试')
            if ident is None:
                ident = str(uuid.uuid4())
                db.execute('''
                    INSERT INTO profile_entries(id,kind,title,details,document_id,updated_at,created_at)
                    VALUES(?,?,?,?,?,?,?)
                ''', (ident, *values, now))
            else:
                revision = body.get('revision')
                if type(revision) is not int:
                    raise ValueError('请刷新档案后重试')
                result = db.execute('''
                    UPDATE profile_entries SET kind=?,title=?,details=?,document_id=?,updated_at=?,revision=revision+1
                    WHERE id=? AND revision=?
                ''', (*values, ident, revision))
                if not result.rowcount:
                    raise ValueError('这条档案已修改或移除，请刷新后重试')
        return ident

    def delete(self, ident):
        with closing(connect_database(self.path)) as db, db:
            if not db.execute('DELETE FROM profile_entries WHERE id=?', (ident,)).rowcount:
                raise ValueError('找不到这条档案')
