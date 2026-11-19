"""Read-only Codex app-server client. Does not start turns or expose credentials."""
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path


def find_codex():
    executable = shutil.which('codex')
    if executable or os.name != 'nt':
        return executable
    # The desktop app can put its CLI on PATH only within Codex sessions.
    try:
        package = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
             '(Get-AppxPackage -Name OpenAI.Codex | Sort-Object Version -Descending | '
             'Select-Object -First 1).InstallLocation'],
            capture_output=True, text=True, timeout=6, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        return None
    location = package.stdout.strip()
    if package.returncode == 0 and location:
        candidate = Path(location) / 'app' / 'resources' / 'codex.exe'
        if candidate.is_file():
            return str(candidate)
    return None


class CodexStatus:
    def __init__(self, executable=None, timeout=20):
        executable = executable or find_codex()
        if not executable:
            raise RuntimeError('找不到 Codex CLI，请先安装并登录')
        self.timeout = timeout
        self.sequence = 0
        self.messages = queue.Queue()
        self.process = subprocess.Popen(
            [executable, 'app-server', '--stdio'], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        threading.Thread(target=self._read, daemon=True).start()
        try:
            self.request('initialize', {'clientInfo': {'name': 'studypet_display', 'version': '0.1.0'}})
            self._send({'method': 'initialized'})
        except Exception:
            self.close()
            raise

    def _read(self):
        for line in self.process.stdout:
            try:
                self.messages.put(json.loads(line))
            except ValueError:
                continue
        self.messages.put(None)

    def _send(self, payload):
        self.process.stdin.write(json.dumps(payload) + '\n')
        self.process.stdin.flush()

    def request(self, method, params=None):
        self.sequence += 1
        ident = self.sequence
        payload = {'id': ident, 'method': method}
        if params is not None:
            payload['params'] = params
        self._send(payload)
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Codex 数据读取超时')
            try:
                message = self.messages.get(timeout=remaining)
            except queue.Empty as error:
                raise TimeoutError('Codex 数据读取超时') from error
            if message is None:
                raise RuntimeError('Codex app-server 已退出')
            if message.get('id') != ident:
                continue
            if 'error' in message:
                raise RuntimeError(message['error'].get('message', 'Codex 请求失败'))
            return message.get('result', {})

    def snapshot(self, thread_id=None):
        response = self.request('account/rateLimits/read')
        buckets = response.get('rateLimitsByLimitId') or {}
        result = {'limits': buckets.get('codex') or response.get('rateLimits') or {},
                  'reply': '', 'reply_error': None}
        if not thread_id:
            result['reply_error'] = '未选择 Codex 对话'
            return result
        try:
            cursor = None
            for _ in range(4):
                params = {'threadId': thread_id, 'limit': 100, 'sortDirection': 'desc'}
                if cursor:
                    params['cursor'] = cursor
                page = self.request('thread/items/list', params)
                for record in page.get('data', []):
                    item = record.get('item', record)
                    if (item.get('type') == 'agentMessage'
                            and item.get('phase') in ('final_answer', 'final')
                            and not item.get('questions')):
                        result['reply'] = item.get('text', '')
                        return result
                cursor = page.get('nextCursor')
                if not cursor:
                    break
            result['reply_error'] = '暂无已完成回复'
        except (RuntimeError, TimeoutError) as error:
            result['reply_error'] = '最近回复暂不可用'
        return result

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        for stream in (self.process.stdin, self.process.stdout):
            if stream:
                stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
