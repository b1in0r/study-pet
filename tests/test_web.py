import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

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


if __name__ == '__main__':
    unittest.main()
