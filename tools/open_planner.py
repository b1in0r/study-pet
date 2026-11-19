"""Launch both local StudyPet programs and open the planner in the browser."""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = 'http://127.0.0.1:8765'
LOCAL = ROOT / '.local'


def ready():
    try:
        with urllib.request.urlopen(URL + '/api/status', timeout=1) as response:
            status = json.load(response)
        if status.get('service') != 'studypet-planner':
            raise RuntimeError('8765 端口已有其他服务，请先检查端口')
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def start_background(module, log_name, *arguments):
    LOCAL.mkdir(exist_ok=True)
    with (LOCAL / log_name).open('ab') as output:
        return subprocess.Popen(
            [sys.executable, '-u', '-m', module, *arguments],
            cwd=ROOT, stdout=output, stderr=output,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )


def ensure_web():
    if ready():
        return
    process = start_background('studypet.web', 'planner-web.log')
    for _ in range(30):
        time.sleep(0.2)
        if ready():
            if process.poll() is None:
                (LOCAL / 'planner-web.pid').write_text(str(process.pid), encoding='ascii')
            return
        if process.poll() is not None:
            raise RuntimeError('本地服务未启动，请查看 .local/planner-web.log')
    raise RuntimeError('本地服务启动超时')


def start_screen_bridge():
    arguments = ['--port', 'auto', '--watch']
    selection = LOCAL / 'screen-thread-id.txt'
    if selection.is_file():
        thread_id = selection.read_text(encoding='utf-8-sig').strip()
        if thread_id:
            arguments.extend(['--thread-id', thread_id])
    process = start_background('studypet.display', 'screen-bridge.log', *arguments)
    try:
        if process.wait(timeout=1):
            print('屏幕同步启动失败，请查看 .local/screen-bridge.log')
    except subprocess.TimeoutExpired:
        pass


def main():
    ensure_web()
    try:
        start_screen_bridge()
    except (OSError, UnicodeError) as error:
        print('屏幕同步启动失败：', error)
    webbrowser.open(URL)
    print(URL)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(error)
        input('按回车关闭…')
        raise SystemExit(1)
