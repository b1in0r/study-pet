"""Local planner UI using the same SQLite store as the desktop screen."""
import argparse
import json
import mimetypes
import re
import sys
from datetime import date, datetime, time, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .tasks import TaskStore

SHANGHAI = timezone(timedelta(hours=8), 'Asia/Shanghai')
STATIC = Path(__file__).with_name('web_static')


def parse_day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('请选择有效的日期')
    return date.fromisoformat(value)


def task_fields(body):
    title = body.get('title')
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 120:
        raise ValueError('请填写 1–120 字的计划内容')
    day = parse_day(body.get('date'))
    clock = body.get('time')
    if not isinstance(clock, str) or not re.fullmatch(r'\d{2}:\d{2}', clock):
        raise ValueError('请选择有效的时间')
    due = datetime.combine(day, time.fromisoformat(clock), tzinfo=SHANGHAI)
    return title.strip(), due


def create_server(port=8765, db='.local/studypet.sqlite3', state_dir='.local'):
    store = TaskStore(db)
    local = Path(state_dir)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def respond(self, code, data, content_type='application/json; charset=utf-8'):
            if content_type.startswith('application/json'):
                data = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'same-origin')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def valid_host(self):
            valid = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            return self.headers.get('Host') in valid

        def do_GET(self):
            if not self.valid_host():
                self.respond(403, {'error': '只接受本机访问'})
                return
            parsed = urlsplit(self.path)
            if parsed.path == '/api/tasks':
                try:
                    selected = parse_day(parse_qs(parsed.query).get('date', [datetime.now(SHANGHAI).date().isoformat()])[0])
                    all_rows = store.list()
                    rows, days = [], {}
                    for row in all_rows:
                        local_day = datetime.fromisoformat(row['due_at']).astimezone(SHANGHAI).date()
                        if local_day == selected:
                            rows.append(row)
                        if local_day.year == selected.year and local_day.month == selected.month:
                            key = local_day.isoformat()
                            days[key] = days.get(key, 0) + 1
                    self.respond(200, {'tasks': rows, 'date': selected.isoformat(), 'days': days,
                                      'today': datetime.now(SHANGHAI).date().isoformat()})
                except (ValueError, TypeError):
                    self.respond(400, {'error': '请选择有效的日期'})
                return
            if parsed.path == '/api/status':
                state = {}
                try:
                    state = json.loads((local / 'screen-state.json').read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    pass
                if not isinstance(state, dict):
                    state = {}
                try:
                    recent = (datetime.now(SHANGHAI) - datetime.fromisoformat(state['last_sync_at'])).total_seconds() < 90
                except (KeyError, ValueError, TypeError):
                    recent = False
                self.respond(200, {'service': 'studypet-planner',
                                  'connected': bool(state.get('connected')) and recent,
                                  'last_sync_at': state.get('last_sync_at'),
                                  'today': datetime.now(SHANGHAI).date().isoformat()})
                return
            assets = {'/': STATIC / 'index.html', '/app.css': STATIC / 'app.css', '/app.js': STATIC / 'app.js',
                      '/favicon.svg': STATIC / 'favicon.svg',
                      '/assets/font.ttf': local / 'fonts/NotoSansSC-wght.ttf',
                      '/preview/calendar.png': local / 'display-preview/calendar.png',
                      '/preview/codex.png': local / 'display-preview/codex.png'}
            asset = assets.get(parsed.path)
            if asset is None or not asset.is_file():
                self.respond(404, {'error': '未找到内容'})
                return
            kind = mimetypes.guess_type(asset.name)[0] or 'application/octet-stream'
            if asset.suffix == '.js':
                kind = 'text/javascript'
            if kind.startswith('text/'):
                kind += '; charset=utf-8'
            self.respond(200, asset.read_bytes(), kind)

        def mutate(self):
            if not self.valid_host():
                self.respond(403, {'error': '只接受本机访问'})
                return
            origin = self.headers.get('Origin')
            if origin and origin != f'http://{self.headers.get("Host")}':
                self.respond(403, {'error': '请求来源不匹配'})
                return
            path = urlsplit(self.path).path
            match = re.fullmatch(r'/api/tasks/(\d+)', path)
            try:
                if self.command == 'DELETE':
                    if not match:
                        self.respond(404, {'error': '未找到计划'})
                        return
                    store.delete(int(match[1]))
                    self.respond(200, {'ok': True})
                    return
                if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                    self.respond(415, {'error': '请使用 JSON 格式'})
                    return
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 8192:
                    self.respond(413, {'error': '请求内容过大或为空'})
                    return
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('计划格式不正确')
                if self.command == 'POST' and path == '/api/tasks':
                    title, due = task_fields(body)
                    task_id = store.add(title, due)
                    self.respond(201, {'id': task_id})
                elif self.command == 'PATCH' and match:
                    updates = {}
                    if any(key in body for key in ('title', 'date', 'time')):
                        updates['title'], updates['due_at'] = task_fields(body)
                    if 'status' in body:
                        updates['status'] = body['status']
                    store.update(int(match[1]), **updates)
                    self.respond(200, {'ok': True})
                else:
                    self.respond(404, {'error': '未找到计划'})
            except (ValueError, TypeError, UnicodeError) as error:
                self.respond(400, {'error': str(error) if isinstance(error, ValueError) else '计划格式不正确'})

        do_POST = do_PATCH = do_DELETE = mutate

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='StudyPet 本地计划管理网页')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--db', default='.local/studypet.sqlite3')
    parser.add_argument('--state-dir', default='.local')
    args = parser.parse_args()
    with create_server(args.port, args.db, args.state_dir) as server:
        print(f'StudyPet 计划管理：http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
