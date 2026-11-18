import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from studypet.knowledge.extract import extract_file
from studypet.knowledge.library import LibraryStore
from studypet.storage.database import connect_database
from studypet.storage.migrate import _v1,initialize_database
from studypet.tasks import TaskStore


def docx_bytes():
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w') as archive:
        archive.writestr('word/document.xml','''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>虚构用户学习笔记</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>表格中的技能证据</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>''')
    return output.getvalue()


def pdf_bytes():
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject,DictionaryObject,NameObject
    writer=PdfWriter();page=writer.add_blank_page(width=400,height=300)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),
        NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({
        NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
    stream=DecodedStreamObject();stream.set_data(b'BT /F1 18 Tf 20 200 Td (Fictional learning evidence) Tj ET')
    page[NameObject('/Contents')]=writer._add_object(stream)
    output=io.BytesIO();writer.write(output);return output.getvalue()


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.db=self.root/'test.sqlite3'
        self.library=LibraryStore(self.db,self.root)

    def test_import_persistence_deduplication_and_sources(self):
        content='# 虚构记录\n我正在学习检索增强生成。'.encode()
        result=self.library.import_file('笔记.md',content)
        self.assertFalse(result['duplicate'])
        self.assertEqual(self.library.import_file('同一份.md',content)['id'],result['id'])
        other=LibraryStore(self.db,self.root)
        self.assertEqual(len(other.list()),1)
        self.assertEqual(other.original(result['id'])[0].read_bytes(),content)
        hit=other.search('检索增强')[0]
        self.assertEqual(hit['locator']['line_start'],1)
        self.assertTrue(hit['source_id'])
        self.assertEqual(other.get(result['id'])['state'],'ready')

    def test_correction_invalidates_old_content_and_rejects_stale_edit(self):
        ident=self.library.import_file('笔记.txt','旧关键词'.encode())['id']
        self.library.update(ident,{'text':'新的能力证据','revision':1})
        self.assertEqual(self.library.search('旧关键词'),[])
        self.assertEqual(self.library.search('能力证据')[0]['revision'],2)
        self.assertEqual(self.library.original(ident)[0].read_bytes(),'旧关键词'.encode())
        with self.assertRaises(ValueError):self.library.update(ident,{'text':'过时编辑','revision':1})
        with closing(connect_database(self.db)) as db:
            self.assertEqual([row[0] for row in db.execute('SELECT state FROM sources ORDER BY captured_at')],['excluded','active'])

    def test_pause_preserves_long_text_without_duplicating_overlap(self):
        text='学习证据'*1000
        ident=self.library.import_file('长笔记.md',text.encode())['id']
        self.library.update(ident,{'enabled':False,'revision':1})
        self.assertEqual(self.library.search('学习证据'),[])
        self.assertEqual(self.library.get(ident)['char_count'],len(text))
        self.library.update(ident,{'enabled':True,'revision':2})
        self.assertTrue(self.library.search('学习证据'))
        with closing(connect_database(self.db)) as db:
            units=self.library._units(db,ident,3)
            self.assertEqual(''.join(unit['text'] for unit in units),text)

    def test_delete_removes_original_and_chunks_even_if_original_is_missing(self):
        ident=self.library.import_file('私人.txt',b'FICTIONAL_PRIVATE_TEXT')['id']
        path=self.library.original(ident)[0]
        path.unlink()
        self.library.delete(ident)
        self.assertFalse(path.exists());self.assertEqual(self.library.list(),[])
        self.assertEqual(self.library.search('FICTIONAL'),[])
        with closing(connect_database(self.db)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM document_chunks').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT state FROM sources').fetchone()[0],'deleted')

    def test_failed_extraction_keeps_original_and_allows_manual_transcript(self):
        with patch.object(self.library,'_extract',return_value={'error':'模拟解析失败'}):
            ident=self.library.import_file('损坏.pdf',b'broken pdf')['id']
        self.assertEqual(self.library.get(ident)['state'],'failed')
        self.assertTrue(self.library.original(ident)[0].exists())
        self.library.update(ident,{'text':'人工补充内容','revision':1})
        self.assertEqual(self.library.get(ident)['state'],'ready')
        self.assertEqual(self.library.search('人工补充')[0]['locator']['method'],'user_transcript')

    def test_reject_paths_unsupported_types_and_empty_files(self):
        for name,data in [('../x.md',b'x'),('..\\x.md',b'x'),('x.doc',b'x'),('x.html',b'x'),('x.md',b'')]:
            with self.assertRaises(ValueError):self.library.import_file(name,data)
        self.assertEqual(self.library.list(),[])

    def test_docx_body_and_table_have_paragraph_locations(self):
        path=self.root/'fixture.docx';path.write_bytes(docx_bytes())
        result=extract_file(path)
        self.assertEqual([unit['text'] for unit in result['units']],['虚构用户学习笔记','表格中的技能证据'])
        self.assertEqual(result['units'][1]['locator']['paragraph'],2)

    def test_pdf_text_and_page_provenance(self):
        try:content=pdf_bytes()
        except ImportError:self.skipTest('optional PDF dependency not installed')
        path=self.root/'fixture.pdf';path.write_bytes(content)
        result=extract_file(path)
        self.assertIn('learning evidence',result['units'][0]['text'])
        self.assertEqual(result['units'][0]['locator']['page'],1)

    def test_v1_migration_preserves_tasks_memories_and_rolls_back_on_failure(self):
        path=self.root/'v1.sqlite3'
        with closing(connect_database(path)) as db,db:
            _v1(db);db.execute('PRAGMA user_version=1')
            db.execute("INSERT INTO tasks(id,title,due_at,status) VALUES(9,'虚构旧任务','2026-11-18T12:00:00.000000+00:00','pending')")
            db.execute("INSERT INTO memories(kind,title,content,created_at) VALUES('note','虚构旧笔记','保留内容','2026-11-18')")
        def broken(db,filename):
            db.execute('CREATE TABLE partial_migration(id INTEGER)')
            raise RuntimeError('simulated failure')
        with patch('studypet.storage.migrate._sql',side_effect=broken):
            with self.assertRaises(RuntimeError):initialize_database(path)
        with closing(connect_database(path)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],1)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='partial_migration'").fetchone())
        tasks=TaskStore(path)
        self.assertEqual(tasks.list()[0]['id'],9)
        with closing(connect_database(path)) as db:
            self.assertEqual(db.execute('SELECT content FROM memories').fetchone()[0],'保留内容')
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],3)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])


if __name__=='__main__':unittest.main()
