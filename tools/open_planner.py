"""Open the local planner, starting its server when needed (stdlib only)."""
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


def ready():
    try:
        with urllib.request.urlopen(URL + '/api/status', timeout=1) as response:
            status = json.load(response)
        if status.get('service') != 'studypet-planner':
            raise RuntimeError('8765 端口已有其他服务，请先检查端口')
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def main():
    if not ready():
        local = ROOT / '.local'
        local.mkdir(exist_ok=True)
        with (local / 'planner-web.log').open('ab') as output:
            process = subprocess.Popen([sys.executable, '-u', '-m', 'studypet.web'], cwd=ROOT,
                stdout=output, stderr=output,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        (local / 'planner-web.pid').write_text(str(process.pid), encoding='ascii')
        for _ in range(30):
            time.sleep(0.2)
            if ready():
                break
            if process.poll() is not None:
                raise RuntimeError('本地服务未启动，请查看 .local/planner-web.log')
        else:
            raise RuntimeError('本地服务启动超时')
    webbrowser.open(URL)
    print(URL)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(error)
        input('按回车关闭…')
        raise SystemExit(1)
