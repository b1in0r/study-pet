import json
import tempfile
import threading
import unittest
from contextlib import closing
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import quote

from studypet.tasks import TaskStore
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


if __name__ == '__main__':
    unittest.main()
