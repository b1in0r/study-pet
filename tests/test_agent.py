import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime,timedelta
from pathlib import Path

from studypet.agent import AgentStore,ReminderEngine
from studypet.tasks import TaskStore


class FakeNotifier:
    available=True
    def __init__(self, success=True): self.calls=[];self.success=success
    def send(self,title,body): self.calls.append((title,body));return self.success
    def close(self): pass


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'test.sqlite3'
        self.tasks=TaskStore(self.path);self.agent=AgentStore(self.tasks)
        self.now=datetime.fromisoformat('2026-11-18T09:00:00+08:00')
        self.notifier=FakeNotifier();self.engine=ReminderEngine(self.agent,self.notifier)

    def test_reminder_survives_restart_without_repeat(self):
        self.tasks.add('今天',self.now-timedelta(minutes=1))
        self.tasks.add('昨天',self.now-timedelta(days=1))
        done=self.tasks.add('完成了',self.now-timedelta(minutes=2));self.tasks.complete(done)
        self.engine.tick(self.now)
        self.assertEqual(len(self.notifier.calls),1)
        other=ReminderEngine(AgentStore(TaskStore(self.path)),self.notifier)
        other.tick(self.now+timedelta(minutes=3))
        self.assertEqual(len(self.notifier.calls),1)
        self.assertEqual(self.agent.reminders()[0]['desktop_state'],'sent')

    def test_snooze_creates_a_new_scheduled_occurrence(self):
        ident=self.tasks.add('论文',self.now)
        self.engine.tick(self.now)
        reminder=self.agent.reminders()[0]
        self.agent.snooze(reminder['id'],self.now)
        self.assertEqual(self.agent.reminders(),[])
        self.engine.tick(self.now+timedelta(minutes=9))
        self.assertEqual(len(self.notifier.calls),1)
        self.engine.tick(self.now+timedelta(minutes=10))
        self.assertEqual(len(self.notifier.calls),2)
        self.assertEqual(self.tasks.list()[0]['id'],ident)
        self.assertIn('rescheduled',[event['kind'] for event in self.tasks.history()])

    def test_completed_deleted_and_acknowledged_stop_pending_delivery(self):
        first=self.tasks.add('完成',self.now);second=self.tasks.add('移除',self.now);self.tasks.add('确认',self.now)
        self.agent.enqueue_due(self.now)
        self.tasks.complete(first);self.tasks.delete(second)
        reminder=self.agent.reminders()[0]
        self.agent.acknowledge(reminder['id']);self.agent.acknowledge(reminder['id'])
        self.engine.tick(self.now)
        self.assertEqual(self.notifier.calls,[])
        self.assertEqual(len([e for e in self.tasks.history() if e['kind']=='reminder_acknowledged']),1)

    def test_retry_is_bounded_and_delayed(self):
        self.tasks.add('通知失败',self.now)
        notifier=FakeNotifier(False);engine=ReminderEngine(self.agent,notifier)
        for seconds in (0,5,61,65,122,200): engine.tick(self.now+timedelta(seconds=seconds))
        self.assertEqual(len(notifier.calls),3)
        self.assertEqual(self.agent.reminders()[0]['attempts'],3)

    def test_history_preserves_deleted_task_and_ids_are_not_reused(self):
        first=self.tasks.add('记录',self.now)
        self.tasks.update(first,title='修改后的标题');self.tasks.complete(first);self.tasks.delete(first)
        second=self.tasks.add('下一项',self.now)
        self.assertGreater(second,first)
        history=self.tasks.history()
        deletion=next(event for event in history if event['kind']=='deleted')
        self.assertEqual(deletion['before']['title'],'修改后的标题')
        self.assertEqual([row['id'] for row in self.tasks.list()],[second])

    def test_pause_and_explicit_memory_deletion(self):
        self.tasks.add('暂停',self.now)
        self.agent.update_settings({'reminders_enabled':False})
        self.engine.tick(self.now)
        self.assertEqual(self.agent.reminders(),[])
        memory=self.agent.add_memory('goal','论文目标','PRIVATE_MEMORY_BODY')
        self.assertEqual(AgentStore(TaskStore(self.path)).memories()[0]['content'],'PRIVATE_MEMORY_BODY')
        self.agent.delete_memory(memory)
        self.assertEqual(self.agent.memories(),[])
        self.assertNotIn('PRIVATE_MEMORY_BODY',json.dumps(self.tasks.history()))

    def test_optimistic_revision_rejects_stale_reminder_action(self):
        ident=self.tasks.add('原计划',self.now)
        old=self.tasks.list()[0]
        self.tasks.complete(ident)
        with self.assertRaises(ValueError):
            self.tasks.update(ident,due_at=self.now+timedelta(minutes=10),expected_revision=old['revision'])

    def test_repeated_completion_preserves_original_timestamp(self):
        ident=self.tasks.add('只完成一次',self.now)
        self.tasks.complete(ident)
        before=self.tasks.list()[0]
        self.tasks.complete(ident)
        self.assertEqual(self.tasks.list()[0]['completed_at'],before['completed_at'])
        self.assertEqual(len([e for e in self.tasks.history() if e['kind']=='completed']),1)

    def test_legacy_migration_does_not_invent_old_timestamps(self):
        path=Path(self.temp.name)/'legacy.sqlite3'
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('CREATE TABLE tasks (id INTEGER PRIMARY KEY,title TEXT NOT NULL,due_at TEXT NOT NULL,status TEXT NOT NULL)')
            db.execute('INSERT INTO tasks VALUES(1,?,?,?)',('旧计划',self.now.isoformat(),'done'))
        migrated=TaskStore(path)
        self.assertIsNone(migrated.list()[0]['created_at'])
        self.assertIsNone(migrated.list()[0]['completed_at'])
        self.assertEqual(migrated.history()[0]['kind'],'snapshot_imported')
        self.assertEqual(len(TaskStore(path).history()),1)


if __name__=='__main__':unittest.main()
