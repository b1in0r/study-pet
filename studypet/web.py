"""Local planner UI using the same SQLite store as the desktop screen."""
import argparse
import json
import mimetypes
import re
import sys
from contextlib import closing
from datetime import date, datetime, time, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, quote

from .tasks import TaskStore
from .agent import AgentStore, ReminderEngine
from .notifications import DesktopNotifier
from .knowledge.library import LibraryStore, MAX_UPLOAD_BYTES

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


def create_server(port=8765, db='.local/studypet.sqlite3', state_dir='.local', *, enable_agent=False, notifier=None):
    store = TaskStore(db)
    agent = AgentStore(store)
    local = Path(state_dir)
    library = LibraryStore(db,local)
    library.recover_incomplete()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def respond(self, code, data, content_type='application/json; charset=utf-8', headers=None):
            if content_type.startswith('application/json'):
                data = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'same-origin')
            for name,value in (headers or {}).items():
                self.send_header(name,value)
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
            if parsed.path.startswith('/api/library/'):
                try:
                    document_match = re.fullmatch(r'/api/library/documents/([0-9a-f-]{36})(/original|/preview)?',parsed.path)
                    if parsed.path == '/api/library/documents':
                        self.respond(200,{'documents':library.list()})
                    elif parsed.path == '/api/library/search':
                        self.respond(200,{'results':library.search(parse_qs(parsed.query).get('q',[''])[0])})
                    elif document_match and document_match[2]:
                        file,document = library.original(document_match[1])
                        if document_match[2] == '/preview':
                            if not document['mime_type'].startswith('image/'):
                                raise ValueError('这份资料没有图片预览')
                            # Only successfully decoded raster images can be displayed inline.
                            if document['state'] == 'failed':
                                raise ValueError('图片未能读取，请下载原件检查')
                            self.respond(200,file.read_bytes(),document['mime_type'])
                        else:
                            self.respond(200,file.read_bytes(),'application/octet-stream',
                                {'Content-Disposition':"attachment; filename*=UTF-8''"+quote(document['original_name'],safe='')})
                    elif document_match:
                        data=library.get(document_match[1]);data.pop('storage_relpath',None)
                        self.respond(200,data)
                    else:
                        self.respond(404,{'error':'未找到资料'})
                except ValueError as error:
                    self.respond(400,{'error':str(error)})
                return
            if parsed.path == '/api/agent':
                engine = getattr(self.server,'agent_engine',None)
                payload = agent.daily_context()
                payload.update(reminders=agent.reminders(),running=bool(engine and engine.thread and engine.thread.is_alive()),
                               error=engine.error if engine else None,
                               last_checked=engine.last_tick if engine else None,
                               desktop_available=bool(engine and engine.notifier.available),
                               desktop_last_visible_at=getattr(engine.notifier,'last_visible_at',None) if engine else None)
                self.respond(200,payload)
                return
            if parsed.path == '/api/agent/history':
                self.respond(200,{'events':store.history(100)})
                return
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
                      '/library':STATIC/'library.html','/library.js':STATIC/'library.js','/library.css':STATIC/'library.css',
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
                document_match = re.fullmatch(r'/api/library/documents/([0-9a-f-]{36})',path)
                if self.command == 'DELETE':
                    if document_match:
                        library.delete(document_match[1])
                        self.respond(200,{'ok':True})
                        return
                    memory_match = re.fullmatch(r'/api/agent/memories/(\d+)', path)
                    if memory_match:
                        agent.delete_memory(int(memory_match[1]))
                        self.respond(200,{'ok':True})
                        return
                    if not match:
                        self.respond(404, {'error': '未找到计划'})
                        return
                    store.delete(int(match[1]))
                    self.respond(200, {'ok': True})
                    return
                if self.command == 'POST' and path == '/api/library/documents':
                    if self.headers.get('Content-Type','').split(';')[0].strip() != 'application/octet-stream':
                        self.respond(415,{'error':'请选择文件上传'})
                        return
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0 < length <= MAX_UPLOAD_BYTES:
                        self.respond(413,{'error':'请选择 20 MB 以内的非空文件'})
                        return
                    filename=parse_qs(urlsplit(self.path).query).get('filename',[''])[0]
                    data=self.rfile.read(length)
                    if len(data) != length:
                        raise ValueError('上传未完成，请重试')
                    self.respond(201,library.import_file(filename,data))
                    return
                if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                    self.respond(415, {'error': '请使用 JSON 格式'})
                    return
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= (2_000_000 if document_match else 32768):
                    self.respond(413, {'error': '请求内容过大或为空'})
                    return
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('计划格式不正确')
                if self.command == 'PATCH' and document_match:
                    library.update(document_match[1],body)
                    self.respond(200,{'ok':True})
                    return
                reminder_action = re.fullmatch(r'/api/agent/reminders/(\d+)/(ack|snooze)',path)
                if self.command == 'POST' and path == '/api/agent/settings':
                    agent.update_settings(body)
                    self.respond(200,{'ok':True})
                elif self.command == 'POST' and path == '/api/agent/memories':
                    ident = agent.add_memory(body.get('kind'),body.get('title'),body.get('content'))
                    self.respond(201,{'id':ident})
                elif self.command == 'POST' and reminder_action:
                    ident = int(reminder_action[1])
                    agent.acknowledge(ident) if reminder_action[2] == 'ack' else agent.snooze(ident)
                    self.respond(200,{'ok':True})
                elif self.command == 'POST' and path == '/api/agent/test-notification':
                    engine = getattr(self.server,'agent_engine',None)
                    accepted = bool(engine and engine.notifier.send('StudyPet 提醒测试','这是一条测试通知。任务到时间时，我会这样提醒你。'))
                    with closing(store._connect()) as db, db:
                        store.event(db,'notification_test',after={'accepted':accepted})
                    self.respond(200,{'accepted':accepted})
                elif self.command == 'POST' and path == '/api/tasks':
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

    class PlannerServer(ThreadingHTTPServer):
        agent_engine = None
        def server_close(self):
            if self.agent_engine:
                self.agent_engine.close()
                self.agent_engine = None
            super().server_close()

    server = PlannerServer(('127.0.0.1', port), Handler)
    if enable_agent:
        server.agent_engine = ReminderEngine(agent, notifier or DesktopNotifier(f'http://127.0.0.1:{server.server_port}'))
        server.agent_engine.start()
    return server


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='StudyPet 本地计划管理网页')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--db', default='.local/studypet.sqlite3')
    parser.add_argument('--state-dir', default='.local')
    parser.add_argument('--no-agent', action='store_true', help='关闭后台提醒，仅运行计划网页')
    args = parser.parse_args()
    with create_server(args.port, args.db, args.state_dir, enable_agent=not args.no_agent) as server:
        print(f'StudyPet 计划管理：http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
