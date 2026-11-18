"""Durable personal memory, daily context and deterministic reminder scheduling."""
import json
import threading
from contextlib import closing
from datetime import datetime, timedelta, timezone

from .tasks import TaskStore, aware_utc

SHANGHAI = timezone(timedelta(hours=8), 'Asia/Shanghai')


class AgentStore:
    def __init__(self, tasks):
        self.tasks = tasks

    def settings(self):
        with closing(self.tasks._connect()) as db:
            return {row['key']: json.loads(row['value']) for row in db.execute('SELECT * FROM agent_settings')}

    def update_settings(self, values):
        if not values or any(key not in ('reminders_enabled','desktop_enabled') or type(value) is not bool
                             for key,value in values.items()):
            raise ValueError('提醒设置格式不正确')
        with closing(self.tasks._connect()) as db, db:
            db.executemany('UPDATE agent_settings SET value = ? WHERE key = ?',
                           [(json.dumps(value),key) for key,value in values.items()])
            self.tasks.event(db, 'settings_changed', after=values)

    def memories(self):
        with closing(self.tasks._connect()) as db:
            return [dict(row) for row in db.execute('SELECT * FROM memories ORDER BY id DESC')]

    def add_memory(self, kind, title, content):
        if kind not in ('goal','preference','note','reflection'):
            raise ValueError('请选择有效的记忆类型')
        if not isinstance(title,str) or not 0 < len(title.strip()) <= 120:
            raise ValueError('记忆标题需要 1–120 字')
        if not isinstance(content,str) or not 0 < len(content.strip()) <= 4000:
            raise ValueError('记忆内容需要 1–4000 字')
        with closing(self.tasks._connect()) as db, db:
            cursor = db.execute('INSERT INTO memories (kind,title,content,created_at) VALUES (?,?,?,?)',
                                (kind,title.strip(),content.strip(),datetime.now(timezone.utc).isoformat()))
            # Content stays in the memory table, so deleting a memory removes its body.
            self.tasks.event(db,'memory_added',after={'memory_id':cursor.lastrowid,'kind':kind})
            return cursor.lastrowid

    def delete_memory(self, ident):
        with closing(self.tasks._connect()) as db, db:
            if db.execute('DELETE FROM memories WHERE id = ?', (ident,)).rowcount == 0:
                raise ValueError('找不到这条记忆')
            self.tasks.event(db,'memory_deleted',after={'memory_id':ident})

    def daily_context(self, now=None):
        now = (now or datetime.now(SHANGHAI)).astimezone(SHANGHAI)
        rows = [row for row in self.tasks.list()
                if datetime.fromisoformat(row['due_at']).astimezone(SHANGHAI).date() == now.date()]
        done = sum(row['status'] == 'done' for row in rows)
        pending = [row for row in rows if row['status'] == 'pending']
        upcoming = [row for row in pending if datetime.fromisoformat(row['due_at']) > now]
        next_task = (upcoming or pending or [None])[0]
        summary = f'今天有 {len(rows)} 项计划，已完成 {done} 项。' if rows else '今天还没有计划，先安排一件最重要的事吧。'
        if next_task:
            clock = datetime.fromisoformat(next_task['due_at']).astimezone(SHANGHAI).strftime('%H:%M')
            summary += f'接下来：{clock} {next_task["title"]}。'
        return {'date':now.date().isoformat(),'tasks':rows,'completed':done,'summary':summary,
                'memories':self.memories(),'settings':self.settings()}

    def enqueue_due(self, now):
        now = aware_utc(now)
        start = now.astimezone(SHANGHAI).replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc)
        with closing(self.tasks._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute('''SELECT * FROM tasks WHERE deleted_at IS NULL AND status = 'pending'
                                 AND due_at >= ? AND due_at <= ? ORDER BY due_at,id''',
                              (start.isoformat(timespec='microseconds'),now.isoformat(timespec='microseconds'))).fetchall()
            count = 0
            for row in rows:
                cursor = db.execute('''INSERT OR IGNORE INTO reminders
                    (task_id,due_at,title,created_at) VALUES (?,?,?,?)''',
                    (row['id'],row['due_at'],row['title'],now.isoformat(timespec='microseconds')))
                if cursor.rowcount:
                    count += 1
                    self.tasks.event(db,'reminder_queued',row['id'],after={'title':row['title'],'reminder_id':cursor.lastrowid},
                                     source='agent',now=now)
            return count

    def reminders(self, active_only=True):
        with closing(self.tasks._connect()) as db:
            query = '''SELECT r.*, t.title AS current_title FROM reminders r JOIN tasks t ON t.id = r.task_id'''
            if active_only:
                query += " WHERE r.state = 'unread' AND t.status = 'pending' AND t.deleted_at IS NULL AND t.due_at = r.due_at"
            query += ' ORDER BY r.id DESC LIMIT 30'
            return [dict(row) for row in db.execute(query)]

    def acknowledge(self, ident):
        with closing(self.tasks._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM reminders WHERE id = ?', (ident,)).fetchone()
            if not old:
                raise ValueError('找不到这条提醒')
            if old['state'] != 'unread':
                return
            db.execute("UPDATE reminders SET state = 'acknowledged' WHERE id = ?", (ident,))
            self.tasks.event(db,'reminder_acknowledged',old['task_id'],after={'reminder_id':ident,'title':old['title']})

    def snooze(self, ident, now=None):
        with closing(self.tasks._connect()) as db:
            reminder = db.execute('''SELECT r.*,t.revision AS task_revision FROM reminders r JOIN tasks t ON t.id=r.task_id
                WHERE r.id=? AND r.state='unread' AND t.status='pending' AND t.deleted_at IS NULL AND t.due_at=r.due_at''', (ident,)).fetchone()
        if not reminder:
            raise ValueError('这条提醒已经处理')
        self.tasks.update(reminder['task_id'],due_at=aware_utc(now or datetime.now(timezone.utc))+timedelta(minutes=10),
                          expected_revision=reminder['task_revision'])

    def claim_desktop(self, now):
        now = aware_utc(now)
        start = now.astimezone(SHANGHAI).replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc)
        retry = now - timedelta(seconds=60)
        with closing(self.tasks._connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('''SELECT r.*, t.title AS current_title FROM reminders r JOIN tasks t ON t.id=r.task_id
                WHERE r.state='unread' AND t.status='pending' AND t.deleted_at IS NULL AND t.due_at=r.due_at
                AND r.due_at >= ? AND r.attempts < 3 AND
                (r.desktop_state='pending' OR (r.desktop_state IN ('failed','sending') AND r.last_attempt_at <= ?))
                ORDER BY r.id LIMIT 1''',
                (start.isoformat(timespec='microseconds'),retry.isoformat(timespec='microseconds'))).fetchone()
            if not row:
                return None
            db.execute("UPDATE reminders SET desktop_state='sending', attempts=attempts+1,last_attempt_at=? WHERE id=?",
                       (now.isoformat(timespec='microseconds'),row['id']))
            return dict(row)

    def desktop_result(self, reminder, success, error=None):
        with closing(self.tasks._connect()) as db, db:
            db.execute('UPDATE reminders SET desktop_state=?, desktop_error=? WHERE id=?',
                       ('sent' if success else 'failed',error,reminder['id']))
            self.tasks.event(db,'reminder_sent' if success else 'reminder_failed',reminder['task_id'],
                             after={'reminder_id':reminder['id'],'title':reminder['current_title']},source='agent')


class ReminderEngine:
    def __init__(self, store, notifier):
        self.store, self.notifier = store, notifier
        self.stop_event = threading.Event()
        self.thread = None
        self.last_tick = None
        self.error = None

    def tick(self, now=None):
        now = aware_utc(now or datetime.now(timezone.utc))
        settings = self.store.settings()
        self.last_tick = now.isoformat()
        if not settings['reminders_enabled']:
            return
        self.store.enqueue_due(now)
        if settings['desktop_enabled'] and self.notifier.available:
            for _ in range(5):
                reminder = self.store.claim_desktop(now)
                if not reminder:
                    break
                try:
                    success = self.notifier.send('学习计划到时间了', reminder['current_title'])
                    self.store.desktop_result(reminder,success,None if success else '系统通知未接受')
                except Exception:
                    self.store.desktop_result(reminder,False,'系统通知暂不可用')

    def _run(self):
        while not self.stop_event.is_set():
            try:
                self.tick()
                self.error = None
            except Exception:
                self.error = '提醒检查暂不可用'
            self.stop_event.wait(5)

    def start(self):
        self.thread = threading.Thread(target=self._run,daemon=True,name='StudyPet reminders')
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        self.notifier.close()
