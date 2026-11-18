"""Local originals, versioned extracted chunks and source-filtered search."""
import hashlib
import json
import os
import subprocess
import sys
import threading
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from ..storage.database import connect_database
from ..storage.migrate import initialize_database
from .extract import MAX_CHARACTERS

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
DOCUMENT_CATEGORIES = {
    'uncategorized': '未分类',
    'campus_recruitment': '秋招求职',
    'graduate_research': '研究生科研',
    'undergraduate': '本科经历',
    'work': '工作经历',
}
FORMATS = {'.pdf':'application/pdf', '.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
           '.md':'text/markdown', '.txt':'text/plain', '.png':'image/png', '.jpg':'image/jpeg',
           '.jpeg':'image/jpeg', '.webp':'image/webp', '.bmp':'image/bmp'}


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def chunks_for(units):
    for unit in units:
        text = unit['text']
        for start in range(0,len(text),1100):
            part = text[start:start+1200]
            if not part.strip():
                continue
            locator = {**unit['locator'],'char_start':start,'char_end':start+len(part)}
            if 'line_start' in locator:
                locator['line_start'] += text[:start].count('\n')
            yield part,locator
            if start+1200 >= len(text):
                break


class LibraryStore:
    def __init__(self, db, state_dir):
        self.db = Path(db)
        self.root = Path(state_dir).resolve()
        self.attachments = self.root / 'attachments'
        self.lock = threading.RLock()
        initialize_database(self.db)

    def _connect(self):
        return connect_database(self.db)

    def _path(self, relative):
        target = (self.root / relative).resolve()
        if not target.is_relative_to(self.attachments.resolve()):
            raise ValueError('资料路径无效')
        return target

    def list(self):
        with closing(self._connect()) as db:
            return [dict(row) for row in db.execute('''SELECT id,title,original_name,mime_type,size_bytes,revision,
                enabled,state,message,char_count,created_at,updated_at,category FROM documents WHERE state <> 'deleted'
                ORDER BY created_at DESC,id''')]

    def get(self, ident):
        with closing(self._connect()) as db:
            row = db.execute("SELECT * FROM documents WHERE id=? AND state <> 'deleted'",(ident,)).fetchone()
            if row is None:
                raise ValueError('找不到这份资料')
            result = dict(row)
            result['chunks'] = [dict(chunk,locator=json.loads(chunk['locator_json'])) for chunk in db.execute(
                '''SELECT id,source_id,text_content,locator_json FROM document_chunks
                   WHERE document_id=? AND document_revision=? ORDER BY ordinal''',(ident,row['revision']))]
            return result

    def original(self, ident):
        document = self.get(ident)
        path = self._path(document['storage_relpath'])
        if not path.is_file():
            raise ValueError('原件暂不可读，请检查本地附件目录')
        return path,document

    def _extract(self, path):
        process = subprocess.Popen([sys.executable,'-m','studypet.knowledge.worker',str(path)],
            cwd=Path(__file__).resolve().parents[2],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            output,_ = process.communicate(timeout=90)
        except subprocess.TimeoutExpired:
            if os.name=='nt':
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                process.kill()
            process.communicate()
            return {'error':'提取超时，原件已保存，可以手动补充文字'}
        try:
            if process.returncode:
                return {'error':'提取未完成，原件已保存，可以手动补充文字'}
            return json.loads(output.decode('utf-8'))
        except (UnicodeError,ValueError):
            return {'error':'提取未完成，原件已保存，可以手动补充文字'}

    def import_file(self, filename, data, *, category='uncategorized'):
        if not isinstance(category, str) or category not in DOCUMENT_CATEGORIES:
            raise ValueError('请选择有效的资料分类')
        if not isinstance(filename,str) or not filename.strip() or len(filename)>200 or any(c in filename for c in '/\\\x00\r\n'):
            raise ValueError('文件名无效，请直接选择本地文件')
        suffix = Path(filename).suffix.lower()
        if suffix not in FORMATS:
            raise ValueError('支持 PDF、DOCX、MD、TXT、PNG、JPG、WEBP 和 BMP；旧版 DOC 请另存为 DOCX')
        if not data or len(data)>MAX_UPLOAD_BYTES:
            raise ValueError('请选择 20 MB 以内的非空文件')
        digest = hashlib.sha256(data).hexdigest()
        ident,now = str(uuid.uuid4()),stamp()
        relative = Path('attachments') / ident / '1' / ('original'+suffix)
        path = self._path(relative)
        with self.lock, closing(self._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute("SELECT id FROM documents WHERE content_sha256=? AND state <> 'deleted'",(digest,)).fetchone()
            if old:
                return {'id':old['id'],'duplicate':True}
            path.parent.mkdir(parents=True,exist_ok=True)
            try:
                path.write_bytes(data)
                db.execute('''INSERT INTO documents(id,title,original_name,mime_type,storage_relpath,content_sha256,
                    size_bytes,state,created_at,updated_at,category) VALUES(?,?,?,?,?,?,?,'importing',?,?,?)''',
                    (ident,Path(filename).stem,filename,FORMATS[suffix],relative.as_posix(),digest,len(data),now,now,category))
            except Exception:
                path.unlink(missing_ok=True)
                raise
        result = self._extract(path)
        with self.lock, closing(self._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM documents WHERE id=?',(ident,)).fetchone()
            if row['state'] != 'importing':
                raise ValueError('资料已发生变化，请刷新列表')
            if 'error' in result:
                db.execute("UPDATE documents SET state='failed',message=?,updated_at=? WHERE id=?",(result['error'],stamp(),ident))
            else:
                self._save_chunks(db,dict(row),result['units'],result['message'])
        return {'id':ident,'duplicate':False}

    def _save_chunks(self, db, document, units, message):
        ident,revision = document['id'],document['revision']
        source,now = str(uuid.uuid4()),stamp()
        db.execute('''INSERT INTO sources(id,kind,record_id,source_version,state,captured_at)
            VALUES(?,'document',?,?,?,?)''',(source,ident,str(revision),'active' if document['enabled'] else 'excluded',now))
        for number,(part,locator) in enumerate(chunks_for(units)):
            db.execute('''INSERT INTO document_chunks(id,document_id,document_revision,ordinal,source_id,
                text_content,locator_json,content_sha256) VALUES(?,?,?,?,?,?,?,?)''',
                (str(uuid.uuid4()),ident,revision,number,source,part,json.dumps(locator,ensure_ascii=False),hashlib.sha256(part.encode()).hexdigest()))
        count = sum(len(unit['text']) for unit in units)
        db.execute('UPDATE documents SET state=?,char_count=?,message=?,updated_at=? WHERE id=?',
                   ('ready' if count else 'needs_text',count,message,now,ident))

    def update(self, ident, body):
        if not isinstance(body,dict) or not ({'enabled','text'} & set(body)) or set(body)-{'enabled','text','revision'}:
            raise ValueError('资料更新格式不正确')
        if type(body.get('revision')) is not int:
            raise ValueError('请刷新后重试')
        if 'enabled' in body and type(body['enabled']) is not bool:
            raise ValueError('检索开关格式不正确')
        if 'text' in body and (not isinstance(body['text'],str) or len(body['text'])>MAX_CHARACTERS):
            raise ValueError('文字需要在 30 万字以内')
        with self.lock, closing(self._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute("SELECT * FROM documents WHERE id=? AND state <> 'deleted'",(ident,)).fetchone()
            if not old or old['state']=='importing':
                raise ValueError('资料不存在或仍在提取中，请稍后刷新')
            if old['revision'] != body['revision']:
                raise ValueError('资料刚刚发生变化，请刷新后重试')
            document = dict(old)
            document['revision'] += 1
            document['enabled'] = int(body.get('enabled',bool(old['enabled'])))
            if 'text' in body:
                units = [{'text':body['text'],'locator':{'method':'user_transcript','line_start':1}}] if body['text'].strip() else []
                message = '使用你校正的文字；原件保持不变，引用定位改为文字行号'
            else:
                units = self._units(db,ident,old['revision'])
                message = old['message']
            db.execute("UPDATE sources SET state='excluded' WHERE kind='document' AND record_id=?",(ident,))
            db.execute('DELETE FROM document_chunks WHERE document_id=?',(ident,))
            db.execute('UPDATE documents SET revision=?,enabled=? WHERE id=?',(document['revision'],document['enabled'],ident))
            self._save_chunks(db,document,units,message)

    @staticmethod
    def _units(db, ident, revision):
        # Reconstruct original extraction units without duplicating chunk overlap.
        units = []
        for row in db.execute('SELECT text_content,locator_json FROM document_chunks WHERE document_id=? AND document_revision=? ORDER BY ordinal',(ident,revision)):
            locator = json.loads(row['locator_json'])
            start = locator.pop('char_start',0);locator.pop('char_end',None)
            if start and units:
                units[-1]['text'] += row['text_content'][max(0,len(units[-1]['text'])-start):]
            else:
                units.append({'text':row['text_content'],'locator':locator})
        return units

    def delete(self, ident):
        with self.lock:
            document = self.get(ident)
            path = self._path(document['storage_relpath'])
            with closing(self._connect()) as db, db:
                db.execute("UPDATE documents SET enabled=0,state='failed',message='原件移除未完成，请重试删除',char_count=0,updated_at=? WHERE id=?",(stamp(),ident))
                db.execute("UPDATE sources SET state='deleted' WHERE kind='document' AND record_id=?",(ident,))
                db.execute('DELETE FROM document_chunks WHERE document_id=?',(ident,))
            try:
                path.unlink(missing_ok=True)
            except OSError as error:
                raise ValueError('已停止检索；原件正被占用，请关闭后重试删除') from error
            with closing(self._connect()) as db, db:
                db.execute("UPDATE documents SET state='deleted',title='已移除资料',original_name='',storage_relpath='',message='' WHERE id=?",(ident,))

    def set_category(self, document_ids, category):
        if not isinstance(category, str) or category not in DOCUMENT_CATEGORIES:
            raise ValueError('请选择有效的资料分类')
        if (not isinstance(document_ids, list) or not 1 <= len(document_ids) <= 500
                or any(not isinstance(ident, str) or len(ident) != 36 for ident in document_ids)):
            raise ValueError('请勾选 1 到 500 份资料')
        ids = list(dict.fromkeys(document_ids))
        placeholders = ','.join('?' for _ in ids)
        with self.lock, closing(self._connect()) as db, db:
            result = db.execute(f"""UPDATE documents SET category=?
                WHERE state <> 'deleted' AND id IN ({placeholders})""", (category, *ids))
            if result.rowcount != len(ids):
                raise ValueError('部分资料已移除，请刷新列表后重试')
        return len(ids)

    def search(self, query, *, category=None):
        if not isinstance(query,str) or not 0<len(query.strip())<=100:
            raise ValueError('请输入 1–100 字的关键词')
        query = query.strip()
        if category is not None and (not isinstance(category, str) or category not in DOCUMENT_CATEGORIES):
            raise ValueError('请选择有效的资料分类')
        category_filter = '' if category is None else 'AND d.category=?'
        params = (query, query) if category is None else (query, query, category)
        with closing(self._connect()) as db:
            rows = db.execute(f'''SELECT c.*,d.title,d.original_name,d.category FROM document_chunks c
                JOIN documents d ON d.id=c.document_id AND d.revision=c.document_revision
                JOIN sources s ON s.id=c.source_id
                WHERE d.state='ready' AND d.enabled=1 AND s.state='active' AND s.source_version=CAST(d.revision AS TEXT)
                AND (instr(lower(c.text_content),lower(?))>0 OR instr(lower(d.title),lower(?))>0)
                {category_filter}
                ORDER BY d.updated_at DESC,c.ordinal LIMIT 20''',params).fetchall()
        results = []
        for row in rows:
            text = row['text_content']; offset = max(0,text.lower().find(query.lower())-80)
            results.append({'document_id':row['document_id'],'title':row['title'],'source_id':row['source_id'],
                'revision':row['document_revision'],'locator':json.loads(row['locator_json']),
                'text':text[offset:offset+350],'category':row['category']})
        return results

    def recover_incomplete(self):
        with closing(self._connect()) as db, db:
            db.execute("UPDATE documents SET state='failed',message='上次提取被中断，原件已保留，可以补充文字' WHERE state='importing'")
