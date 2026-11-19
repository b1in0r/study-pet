"""PC screen bridge. Run: python -m studypet.display --help."""
import argparse
import errno
import json
import os
import sys
import time
from datetime import datetime
from contextlib import contextmanager, nullcontext
from pathlib import Path

from .codex_status import CodexStatus
from .screen_protocol import frame_packet, pack_pixels
from .screen_render import SHANGHAI, calendar_page, codex_page, prepare_font
from .tasks import TaskStore


@contextmanager
def bridge_lock(path):
    """Keep a single sender per output directory, including across launcher runs."""
    with path.open('a+b') as handle:
        try:
            if os.name == 'nt':
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno not in (errno.EACCES, errno.EAGAIN):
                raise
            yield False
        else:
            yield True


def save_screen_status(directory, connected):
    """Expose only confirmed device sync health to the local planner UI."""
    target = directory / 'screen-state.json'
    try:
        previous = json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
        if not isinstance(previous, dict):
            previous = {}
        previous['connected'] = connected
        if connected:
            previous['last_sync_at'] = datetime.now(SHANGHAI).isoformat(timespec='seconds')
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(previous), encoding='utf-8')
        temporary.replace(target)
    except (OSError, ValueError):
        # Health reporting must not interrupt the audio/display bridge.
        pass


def find_port():
    from serial.tools import list_ports
    ports = [port for port in list_ports.comports() if port.vid == 0x303A and port.pid == 0x8001]
    if len(ports) != 1:
        raise RuntimeError('未找到唯一的 StudyPet 屏幕串口，请检查连接或使用 --port COM端口')
    return ports[0].device


def send_pages(port, images):
    import serial
    with serial.Serial(find_port() if port == 'auto' else port, 115200, timeout=0.3, write_timeout=5) as stream:
        stream.reset_input_buffer()
        for index, image in enumerate(images):
            frame = pack_pixels(list(image.getdata()))
            stream.write(frame_packet(index, frame))
            stream.flush()
            deadline = time.monotonic() + 5
            expected = f'OK {index}'
            while time.monotonic() < deadline:
                line = stream.readline().decode('ascii', errors='replace').strip()
                if line == expected:
                    break
                if line.startswith('ERR'):
                    raise RuntimeError('开发板拒绝屏幕数据：' + line)
            else:
                raise TimeoutError('开发板未确认屏幕数据')


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='StudyPet 日历 / 学习计划 / Codex 屏幕桥接')
    parser.add_argument('--db', default='.local/studypet.sqlite3')
    parser.add_argument('--thread-id', default=os.environ.get('CODEX_THREAD_ID'))
    parser.add_argument('--font', default='.local/fonts/NotoSansSC-wght.ttf')
    parser.add_argument('--preview-dir', default='.local/display-preview')
    parser.add_argument('--port', help='auto 或 COM端口；省略时仅生成预览')
    parser.add_argument('--watch', action='store_true', help='持续同步，Ctrl+C 退出')
    parser.add_argument('--interval', type=int, default=30, help='同步间隔，至少 15 秒')
    args = parser.parse_args()
    if args.interval < 15:
        parser.error('--interval 至少为 15 秒')
    output = Path(args.preview_dir)
    output.mkdir(parents=True, exist_ok=True)
    lock = bridge_lock(output.parent / 'screen-bridge.lock') if args.port else nullcontext(True)
    with lock as acquired:
        if not acquired:
            print('屏幕同步已在运行', flush=True)
            return
        if args.port and args.watch:
            (output.parent / 'screen-bridge.pid').write_text(str(os.getpid()), encoding='ascii')
        run(args, output)


def run(args, output):
    face = prepare_font(args.font)
    store = TaskStore(args.db)
    client = None
    snapshot = {}
    try:
        while True:
            now = datetime.now(SHANGHAI)
            try:
                if client is None:
                    client = CodexStatus()
                snapshot = client.snapshot(args.thread_id)
                snapshot['sampled_at'] = now
            except (RuntimeError, TimeoutError, OSError):
                if client:
                    client.close()
                    client = None
                snapshot = dict(snapshot, error=True)
            pages = [calendar_page(now, store.list(), face), codex_page(now, snapshot, face)]
            for name, page in zip(('calendar', 'codex'), pages):
                page.save(output / (name + '.png'))
            if args.port:
                try:
                    send_pages(args.port, pages)
                    save_screen_status(output.parent, True)
                    print(now.strftime('%H:%M:%S'), '已同步日历与 Codex 两页', flush=True)
                except (RuntimeError, TimeoutError, OSError) as error:
                    save_screen_status(output.parent, False)
                    print('屏幕同步暂不可用：', error, flush=True)
                    if not args.watch:
                        raise
            else:
                print('已生成屏幕预览：', output.resolve(), flush=True)
            if not args.watch:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        if client:
            client.close()


if __name__ == '__main__':
    main()
