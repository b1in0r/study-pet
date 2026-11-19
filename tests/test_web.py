import json
import tempfile
import threading
import unittest
from unittest.mock import patch
from contextlib import closing
from datetime import date, timedelta
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import quote

from studypet.tasks import TaskStore
from studypet.local_ai import LocalAIError
from studypet.web import create_server


class PlannerWebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / 'tasks.sqlite3'
        self.server = create_server(0, self.db, self.temp.name)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        request_headers = {'Content-Type': 'application/json'}
        request_headers.update(headers or {})
        connection.request(method, path, json.dumps(body) if body is not None else None, request_headers)
        response = connection.getresponse()
        content = response.read()
        result = json.loads(content) if response.getheader('Content-Type').startswith('application/json') else content
        code = response.status
        connection.close()
        return code, result

    def add(self, title='阅读论文', day='2026-11-18', clock='20:00'):
        code, result = self.request('POST', '/api/tasks', {'title': title, 'date': day, 'time': clock})
        self.assertEqual(code, 201)
        return result['id']

    def test_persists_add_edit_complete_restore_and_delete(self):
        ident = self.add()
        self.assertEqual(TaskStore(self.db).list()[0]['title'], '阅读论文')
        code, _ = self.request('PATCH', f'/api/tasks/{ident}', {'title': '实现屏幕', 'date': '2026-11-19', 'time': '21:30'})
        self.assertEqual(code, 200)
        self.assertEqual(self.request('GET', '/api/tasks?date=2026-11-18')[1]['tasks'], [])
        rows = self.request('GET', '/api/tasks?date=2026-11-19')[1]['tasks']
        self.assertEqual(rows[0]['title'], '实现屏幕')
        for status in ('done', 'pending'):
            self.assertEqual(self.request('PATCH', f'/api/tasks/{ident}', {'status': status})[0], 200)
            self.assertEqual(TaskStore(self.db).list()[0]['status'], status)
        self.assertEqual(self.request('DELETE', f'/api/tasks/{ident}')[0], 200)
        self.assertEqual(TaskStore(self.db).list(), [])

    def test_shanghai_date_boundary_and_calendar_counts(self):
        self.add(day='2026-11-19', clock='00:30')
        self.assertTrue(TaskStore(self.db).list()[0]['due_at'].startswith('2026-11-18T16:30'))
        self.assertEqual(len(self.request('GET', '/api/tasks?date=2026-11-19')[1]['tasks']), 1)
        previous = self.request('GET', '/api/tasks?date=2026-11-18')[1]
        self.assertEqual(previous['tasks'], [])
        self.assertEqual(previous['days']['2026-11-19'], 1)

    def test_invalid_updates_do_not_partially_change_task(self):
        ident = self.add()
        code, _ = self.request('PATCH', f'/api/tasks/{ident}',
                               {'title': '不要保存', 'date': '2026-11-18', 'time': '21:00', 'status': 'invalid'})
        self.assertEqual(code, 400)
        self.assertEqual(TaskStore(self.db).list()[0]['title'], '阅读论文')
        self.assertEqual(self.request('POST', '/api/tasks', {'title': ' ', 'date': '2026-11-18', 'time': '20:00'})[0], 400)
        self.assertEqual(self.request('GET', '/api/tasks?date=not-a-date')[0], 400)

    def test_reject_foreign_origin_and_host_and_serve_ui(self):
        code, _ = self.request('POST', '/api/tasks', {'title': '不应保存', 'date': '2026-11-18', 'time': '20:00'},
                               {'Origin': 'https://example.com'})
        self.assertEqual(code, 403)
        self.assertEqual(TaskStore(self.db).list(), [])
        self.assertEqual(self.request('GET', '/api/tasks', headers={'Host': 'example.com'})[0], 403)
        code, body = self.request('GET', '/')
        self.assertEqual(code, 200)
        self.assertIn(b'id="add-form"', body)

    def test_agent_memory_settings_and_history_api(self):
        content = '学' * 4000
        code, result = self.request('POST','/api/agent/memories',
                                    {'kind':'preference','title':'学习偏好','content':content})
        self.assertEqual(code,201)
        context=self.request('GET','/api/agent')[1]
        self.assertEqual(context['memories'][0]['content'],content)
        self.assertFalse(context['running'])
        self.assertEqual(self.request('POST','/api/agent/settings',{'reminders_enabled':False})[0],200)
        self.assertFalse(self.request('GET','/api/agent')[1]['settings']['reminders_enabled'])
        self.assertEqual(self.request('DELETE',f'/api/agent/memories/{result["id"]}')[0],200)
        self.assertEqual(self.request('GET','/api/agent')[1]['memories'],[])
        history=self.request('GET','/api/agent/history')[1]['events']
        self.assertEqual(history[0]['kind'],'memory_deleted')

    def test_library_binary_upload_search_download_and_delete(self):
        connection=HTTPConnection('127.0.0.1',self.server.server_port,timeout=15)
        raw='虚构知识资料：学习规划'.encode()
        connection.request('POST','/api/library/documents?filename='+quote('笔记.md'),raw,{'Content-Type':'application/octet-stream'})
        response=connection.getresponse();result=json.loads(response.read())
        self.assertEqual(response.status,201);ident=result['id']
        connection.request('GET',f'/api/library/documents/{ident}/original')
        response=connection.getresponse()
        self.assertEqual(response.read(),raw)
        self.assertIn('attachment;',response.getheader('Content-Disposition'))
        connection.close()
        self.assertTrue(self.request('GET','/api/library/search?q='+quote('学习规划'))[1]['results'])
        self.assertEqual(self.request('PATCH',f'/api/library/documents/{ident}',{'enabled':False,'revision':1})[0],200)
        self.assertEqual(self.request('GET','/api/library/search?q='+quote('学习规划'))[1]['results'],[])
        self.assertEqual(self.request('DELETE',f'/api/library/documents/{ident}')[0],200)
        self.assertEqual(self.request('GET','/api/library/documents')[1]['documents'],[])

    def test_library_categories_scope_search_and_keep_document_sources(self):
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        with closing(connection):
            ids = []
            for index, category in enumerate(('undergraduate', 'uncategorized', 'graduate_research')):
                path = f'/api/library/documents?filename=fixture-{index}.md&category={category}'
                connection.request('POST', path, f'共同关键词 {index}'.encode(),
                                   {'Content-Type': 'application/octet-stream'})
                response = connection.getresponse()
                ids.append(json.loads(response.read())['id'])
                self.assertEqual(response.status, 201)

        documents = '/api/library/documents'
        endpoint = '/api/library/document-categories'
        search = '/api/library/search?q=' + quote('共同关键词')
        old = self.request('GET', f'{documents}/{ids[0]}')[1]
        self.assertEqual(old['category'], 'undergraduate')
        self.assertEqual(self.request('GET', f'{documents}/{ids[1]}')[1]['category'], 'uncategorized')
        self.assertEqual(
            self.request('PATCH', endpoint, {'document_ids': ids[:2], 'category': 'campus_recruitment'}),
            (200, {'count': 2}),
        )
        results = self.request('GET', search + '&category=campus_recruitment')[1]['results']
        self.assertEqual({result['document_id'] for result in results}, set(ids[:2]))
        new = self.request('GET', f'{documents}/{ids[0]}')[1]
        self.assertEqual(new['revision'], old['revision'])
        self.assertEqual(new['chunks'], old['chunks'])

        missing = '00000000-0000-0000-0000-000000000000'
        code, _ = self.request('PATCH', endpoint, {'document_ids': [ids[0], missing], 'category': 'work'})
        self.assertEqual(code, 400)
        self.assertEqual(self.request('GET', f'{documents}/{ids[0]}')[1]['category'], 'campus_recruitment')

    def test_profile_edit_and_removed_document_reference(self):
        with closing(HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)) as connection:
            connection.request('POST', '/api/library/documents?filename=evidence.md', b'private fixture',
                               {'Content-Type': 'application/octet-stream'})
            response = connection.getresponse()
            document_id = json.loads(response.read())['id']
            self.assertEqual(response.status, 201)
        body = {'kind': 'skill', 'title': '虚构能力', 'details': '自己确认的证据', 'document_id': document_id}
        code, payload = self.request('POST', '/api/profile', body)
        self.assertEqual(code, 201)
        path = f'/api/profile/{payload["id"]}'
        entry = self.request('GET', '/api/profile')[1]['entries'][0]
        self.assertEqual(entry['document_title'], 'evidence')

        update = dict(body, title='校正后的能力', revision=entry['revision'])
        self.assertEqual(self.request('PATCH', path, update)[0], 200)
        self.assertEqual(self.request('PATCH', path, update)[0], 400)
        self.assertEqual(self.request('DELETE', f'/api/library/documents/{document_id}')[0], 200)
        self.assertEqual(self.request('POST', '/api/profile', body)[0], 400)
        entry = self.request('GET', '/api/profile')[1]['entries'][0]
        self.assertEqual(entry['title'], '校正后的能力')
        self.assertIsNone(entry['document_title'])
        self.assertEqual(self.request('DELETE', path)[0], 200)
        self.assertEqual(self.request('GET', '/api/profile')[1]['entries'], [])

    def test_journal_confirmation_and_assistant_opt_in(self):
        today = self.request('GET', '/api/journal')[1]['today']
        self.assertEqual(self.request('POST', '/api/journal', {'day': '2026-02-30', 'body': '无效'} )[0], 400)
        code, created = self.request('POST', '/api/journal', {'day': today, 'body': '虚构日记，仅供测试'})
        self.assertEqual(code, 201)
        path = f'/api/journal/{created["id"]}'
        self.assertEqual(self.request('PATCH', path, {'day': today, 'body': '已校正的虚构日记'})[0], 200)
        with patch('studypet.codex_text.CodexText.generate') as generate:
            generate.return_value = {'answer': '样例回答', 'source_ids': ['S1', 'S999'], 'task_title': '一分钟复盘'}
            code, data = self.request('POST', '/api/assistant', {'question': '今天进度如何？'})
            self.assertEqual(code, 200)
            self.assertEqual(data['sources'], [])
            self.assertEqual(generate.call_args.args[1]['sources'], [])
            code, data = self.request('POST', '/api/assistant', {'question': '今天进度如何？', 'include_journal': True})
            self.assertEqual(code, 200)
            self.assertEqual([source['id'] for source in data['sources']], ['S1'])
            self.assertEqual(generate.call_args.args[1]['sources'][0]['text'], '已校正的虚构日记')
        self.assertEqual(TaskStore(self.db).list(), [])
        self.assertEqual(self.request('DELETE', path)[0], 200)
        self.assertEqual(self.request('GET', '/api/journal')[1]['entries'], [])

    def test_daily_review_uses_today_records_and_reschedules_only_on_confirmation(self):
        today = date.fromisoformat(self.request('GET', '/api/journal')[1]['today'])
        tomorrow = (today + timedelta(days=1)).isoformat()
        yesterday = (today - timedelta(days=1)).isoformat()
        self.request('POST', '/api/journal', {'day': yesterday, 'body': '昨天的测试日记'})
        self.request('POST', '/api/journal', {'day': today.isoformat(), 'body': '今天整理了实验数据'})
        finished = self.add('今天完成的跨日事项', day=yesterday)
        self.request('PATCH', f'/api/tasks/{finished}', {'status': 'done'})
        pending = self.add('补写论文结果部分', day=today.isoformat())
        original = TaskStore(self.db).list()

        with patch('studypet.codex_text.CodexText.generate', side_effect=LocalAIError('测试无模型')):
            code, review = self.request('POST', '/api/review/today', {})
        self.assertEqual(code, 200)
        self.assertEqual(review['mode'], 'records')
        self.assertEqual(review['model_error'], '测试无模型')
        self.assertEqual(review['journal'], ['今天整理了实验数据'])
        self.assertEqual(review['completed'], ['今天完成的跨日事项'])
        self.assertEqual(review['suggestion']['existing']['id'], pending)
        self.assertTrue(review['question'])
        self.assertEqual(TaskStore(self.db).list(), original)

        with patch('studypet.codex_text.CodexText.generate') as generate:
            generate.return_value = {'progress': '实验数据已经整理。', 'task_title': '补写论文结果部分',
                                     'reason': '今天完成了数据整理。', 'task_ref': f'T{pending}'}
            code, review = self.request('POST', '/api/review/today', {'minutes': 90})
        self.assertEqual(code, 200)
        self.assertEqual(review['mode'], 'model')
        self.assertEqual(generate.call_args.args[1]['明天预计可用分钟'], 90)
        self.assertEqual(review['tomorrow'], tomorrow)
        draft = {'title': review['suggestion']['title'], 'date': tomorrow, 'time': '20:00',
                 'revision': review['suggestion']['existing']['revision']}
        self.assertEqual(self.request('PATCH', f'/api/tasks/{pending}', draft)[0], 200)
        self.assertEqual(self.request('PATCH', f'/api/tasks/{pending}', draft)[0], 400)
        tasks = self.request('GET', f'/api/tasks?date={tomorrow}')[1]['tasks']
        self.assertEqual([task['id'] for task in tasks], [pending])

        with patch('studypet.codex_text.CodexText.generate', return_value={
            'task_title': '今天完成的跨日事项', 'task_ref': f'T{pending}',
            'reason': '重新安排已完成事项', 'question': '今天进展如何？',
        }):
            _, review = self.request('POST', '/api/review/today', {'minutes': 90})
        self.assertEqual(review['suggestion']['title'], '补写论文结果部分')
        self.assertEqual(review['suggestion']['existing']['id'], pending)
        self.assertFalse(review['question'])


if __name__ == '__main__':
    unittest.main()
