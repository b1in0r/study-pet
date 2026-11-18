"""400x300 monochrome desk calendar and Codex pages, rendered on the PC."""
import calendar
import hashlib
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SHANGHAI = timezone(timedelta(hours=8), 'Asia/Shanghai')
FONT_URL = ('https://raw.githubusercontent.com/google/fonts/'
            '7af0d90b4d532ffa4b041937b560c6df4e7b1e95/ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf')
FONT_PATH = Path('.local/fonts/NotoSansSC-wght.ttf')


def prepare_font(path=FONT_PATH):
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.download')
        try:
            with urllib.request.urlopen(FONT_URL, timeout=45) as response:
                data = response.read(20_000_001)
            if len(data) > 20_000_000:
                raise ValueError('字体文件超出预期大小')
            # Pinned Git blob identity prevents silent changes to this font.
            digest = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            if digest != 'fb0637bafbcd804fe32152370a1225990745b4bc':
                raise ValueError('字体校验失败')
            temporary.write_bytes(data)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return str(path.resolve())


@lru_cache(maxsize=20)
def font(path, size, bold=False):
    result = ImageFont.truetype(path, size)
    result.set_variation_by_axes([600 if bold else 400])
    return result


def text(draw, xy, value, size=16, bold=False, fill=0, path=None):
    draw.text(xy, value, font=font(path, size, bold), fill=fill, anchor='lt')


def wrap(value, face, width, max_lines):
    lines, line = [], ''
    for char in value:
        if char == '\n' or (line and face.getlength(line + char) > width):
            lines.append(line)
            line = ''
            if len(lines) == max_lines:
                lines[-1] = lines[-1][:-1] + '…'
                return lines
            if char == '\n':
                continue
        line += char
    if line:
        lines.append(line)
    return lines[:max_lines]


def plain_excerpt(value):
    value = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', value)
    value = re.sub(r'[`*#_]', '', value)
    return re.sub(r'\s+', ' ', value).strip()


def today_tasks(rows, now):
    result = []
    for row in rows:
        due = datetime.fromisoformat(row['due_at']).astimezone(SHANGHAI)
        if due.date() == now.date():
            result.append((due, row))
    return sorted(result, key=lambda item: (item[0], item[1]['id']))


def calendar_page(now, rows, path):
    image = Image.new('L', (400, 300), 255)
    draw = ImageDraw.Draw(image)
    tx = lambda xy, val, size=16, bold=False, fill=0: text(draw, xy, val, size, bold, fill, path)
    tx((16, 15), f'{now.month}月{now.day}日  周{"一二三四五六日"[now.weekday()]}', 25, True)
    tx((317, 22), now.strftime('%H:%M'), 20)
    draw.line((16, 53, 384, 53), fill=0, width=2)
    tx((16, 69), f'{now.year} / {now.month:02}', 18, True)
    for col, day in enumerate('一二三四五六日'):
        tx((20 + col * 22, 101), day, 13)
    for week, days in enumerate(calendar.Calendar().monthdayscalendar(now.year, now.month)):
        for col, day in enumerate(days):
            if not day:
                continue
            x, y = 16 + col * 22, 124 + week * 22
            if day == now.day:
                draw.ellipse((x, y - 2, x + 21, y + 19), fill=0)
            value = str(day)
            offset = (22 - font(path, 14).getlength(value)) / 2
            tx((x + offset, y), value, 14, fill=255 if day == now.day else 0)
    draw.line((183, 69, 183, 250), fill=0)
    items = today_tasks(rows, now)
    tx((201, 69), '今日计划', 20, True)
    if not items:
        tx((201, 119), '今天还没有计划', 17)
        tx((201, 149), '在电脑端添加任务', 15)
    else:
        for index, (due, row) in enumerate(items[:3]):
            y = 108 + index * 47
            draw.rectangle((201, y + 1, 211, y + 11), outline=0)
            if row['status'] == 'done':
                draw.line((203, y + 6, 206, y + 9, 210, y + 2), fill=0, width=2)
            tx((220, y), due.strftime('%H:%M'), 13)
            label = wrap(row['title'], font(path, 16), 177, 1)[0]
            tx((201, y + 19), label, 16)
        done = sum(row['status'] == 'done' for _, row in items)
        tx((201, 252), f'完成 {done}/{len(items)}' + ('  另有任务' if len(items) > 3 else ''), 13)
    draw.line((16, 273, 384, 273), fill=0)
    tx((16, 281), 'KEY 切换 Codex', 12)
    tx((286, 281), '同步 ' + now.strftime('%H:%M'), 12)
    return image.point(lambda value: 255 if value >= 128 else 0, mode='1')


def window_label(minutes):
    if not minutes:
        return '配额窗口'
    if minutes >= 1440 and minutes % 1440 == 0:
        return f'{minutes // 1440}天'
    if minutes % 60 == 0:
        return f'{minutes // 60}小时'
    return f'{minutes}分钟'


def codex_page(now, snapshot, path):
    image = Image.new('L', (400, 300), 255)
    draw = ImageDraw.Draw(image)
    tx = lambda xy, val, size=16, bold=False, fill=0: text(draw, xy, val, size, bold, fill, path)
    tx((16, 15), 'Codex', 27, True)
    tx((225, 24), '用量与最近回复', 17)
    draw.line((16, 53, 384, 53), fill=0, width=2)
    limits = snapshot.get('limits') or {}
    for index, field in enumerate(('primary', 'secondary')):
        y = 66 + index * 43
        window = limits.get(field)
        if not window:
            tx((16, y), '用量暂不可用' if index == 0 else '暂无第二用量窗口', 16)
            continue
        used = max(0, min(100, float(window['usedPercent'])))
        tx((16, y), f'{window_label(window.get("windowDurationMins"))}  已用 {used:g}%', 17, True)
        reset = window.get('resetsAt')
        if reset:
            date = datetime.fromtimestamp(reset, SHANGHAI)
            reset_text = date.strftime('%H:%M') if date.date() == now.date() else date.strftime('%m/%d %H:%M')
            tx((256, y + 3), '重置 ' + reset_text, 12)
        draw.rectangle((16, y + 25, 384, y + 30), outline=0)
        if used:
            draw.rectangle((16, y + 25, 16 + round(368 * used / 100), y + 30), fill=0)
    tx((16, 154), '最近回复摘录', 16, True)
    body = plain_excerpt(snapshot.get('reply', '')) or snapshot.get('reply_error') or '暂无已完成回复'
    for index, line in enumerate(wrap(body, font(path, 16), 368, 4)):
        tx((16, 180 + index * 21), line, 16)
    draw.line((16, 273, 384, 273), fill=0)
    tx((16, 281), 'KEY 返回学习计划', 12)
    stamp = snapshot.get('sampled_at', now)
    label = '更新失败 ' if snapshot.get('error') else '同步 '
    tx((265, 281), label + stamp.strftime('%H:%M'), 12)
    return image.point(lambda value: 255 if value >= 128 else 0, mode='1')


def waiting_page(path):
    image = Image.new('L', (400, 300), 255)
    draw = ImageDraw.Draw(image)
    text(draw, (24, 28), '学习桌历', 32, True, path=path)
    draw.line((24, 88, 376, 88), fill=0, width=2)
    text(draw, (24, 124), '等待电脑同步', 24, path=path)
    text(draw, (24, 172), '请在电脑启动 StudyPet 屏幕程序', 18, path=path)
    text(draw, (24, 249), '扬声器可以独立使用', 16, path=path)
    return image.point(lambda value: 255 if value >= 128 else 0, mode='1')
