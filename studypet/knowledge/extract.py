"""Bounded local extraction; documents are data, never executable instructions."""
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

MAX_CHARACTERS = 300_000
MAX_PDF_PAGES = 150


class ExtractionError(ValueError):
    pass


def windows_ocr(path, pages=None):
    try:
        from .ocr import recognize
        return recognize(path,pages)
    except Exception as error:
        raise ExtractionError('本地 OCR 未能完成，请手动补充文字') from error


def _text(path):
    data = path.read_bytes()
    for encoding in ('utf-8-sig','utf-16' if data.startswith((b'\xff\xfe',b'\xfe\xff')) else 'gb18030'):
        try:
            text = data.decode(encoding)
            if '\x00' in text:
                raise ExtractionError('文本包含二进制内容，请另存为 UTF-8 文本')
            return [{'text':text,'locator':{'line_start':1,'method':'text'}}], ''
        except UnicodeError:
            continue
    raise ExtractionError('无法解码文本，请另存为 UTF-8')


def _docx(path):
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos)>2000 or sum(info.file_size for info in infos)>80_000_000:
                raise ExtractionError('Word 解压体积过大，请拆分文件')
            info = archive.getinfo('word/document.xml')
            if info.file_size>8_000_000:
                raise ExtractionError('Word 正文过长，请拆分文件')
            raw = archive.read(info)
        if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
            raise ExtractionError('Word XML 格式不受支持')
        root = ET.fromstring(raw)
        ns = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        units = []
        for number, paragraph in enumerate(root.findall('.//w:body//w:p',ns),1):
            text = ''.join(node.text or '' for node in paragraph.findall('.//w:t',ns))
            if text.strip():
                units.append({'text':text,'locator':{'paragraph':number,'method':'docx'}})
        return units,'已提取 Word 正文与表格文字；嵌入图片、页眉和批注未提取'
    except (zipfile.BadZipFile,KeyError,ET.ParseError,RuntimeError) as error:
        raise ExtractionError('Word 文件损坏或格式不受支持，请使用 .docx') from error


def _pdf(path):
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise ExtractionError('未安装 PDF 提取依赖，请安装 requirements-knowledge.txt') from error
    try:
        reader = PdfReader(path)
        if reader.is_encrypted and not reader.decrypt(''):
            raise ExtractionError('PDF 有密码，请先保存无密码副本')
        if len(reader.pages)>MAX_PDF_PAGES:
            raise ExtractionError(f'PDF 超过 {MAX_PDF_PAGES} 页，请拆分')
        units, scanned, count = [], [], 0
        for number,page in enumerate(reader.pages,1):
            stream = page.get_contents()
            if stream is not None and len(stream.get_data())>12_000_000:
                raise ExtractionError('PDF 单页内容过大，请先优化文件')
            text = page.extract_text() or ''
            count += len(text)
            if count>MAX_CHARACTERS:
                raise ExtractionError('提取文字超过 30 万字，请拆分文件')
            if text.strip():
                units.append({'text':text,'locator':{'page':number,'method':'pdf_text'}})
            else:
                scanned.append(number)
        warning = ''
        if scanned:
            try:
                units += windows_ocr(path,scanned[:12])
                warning = '含 OCR 识别文字，请对照原件核对'
                if len(scanned)>12:
                    warning += f'；仅识别前 12 个无文字页，另有 {len(scanned)-12} 页待补充'
            except ExtractionError:
                warning = f'有 {len(scanned)} 页未提取出文字，请手动补充或使用 OCR 后的 PDF'
        units.sort(key=lambda unit:unit['locator'].get('page',0))
        return units,warning
    except ExtractionError:
        raise
    except Exception as error:
        raise ExtractionError('PDF 无法解析，请检查文件后重新导入') from error


def extract_file(path):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in ('.md','.txt'):
        units,message = _text(path)
    elif suffix == '.docx':
        units,message = _docx(path)
    elif suffix == '.pdf':
        units,message = _pdf(path)
    else:
        try:
            from PIL import Image
            with Image.open(path) as picture:
                if picture.format not in ('PNG','JPEG','WEBP','BMP') or picture.width*picture.height>25_000_000:
                    raise ExtractionError('图片格式或尺寸不受支持，请使用 2500 万像素以内的静态图片')
                picture.verify()
        except (ImportError,OSError,ValueError) as error:
            if isinstance(error,ExtractionError):
                raise
            raise ExtractionError('无法读取图片，请检查图片或安装 requirements-knowledge.txt') from error
        try:
            units = windows_ocr(path)
            message = '本地 OCR 识别结果，请对照原图核对；图形含义尚未分析'
        except ExtractionError as error:
            units,message = [],str(error)
    units = [unit for unit in units if unit['text'].strip()]
    if sum(len(unit['text']) for unit in units)>MAX_CHARACTERS:
        raise ExtractionError('提取文字超过 30 万字，请拆分文件')
    return {'units':units,'message':message or ('' if units else '未提取到文字，请手动补充')}
