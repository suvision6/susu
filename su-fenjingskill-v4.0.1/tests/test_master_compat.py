"""Template and preservation tests; not a directing-quality evaluation."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from master_io import Document, FormatError, parse_master, duration, save_exclusive


def fixture(ids=('01','07A'),times=('4.125','暂未确定')):
    text='# 兼容回归\n本轮来源：虚构测试\n本轮范围：局部\n项目条件：短片；中文；16:9；节奏按本场\n\n## 来源依据\n\n```text\n甲：不要。\n```\n\n## 导演设计\n\n保持当前桌侧关系。\n\n## 分镜\n'
    for sid,t in zip(ids,times):
        text+=f'\n### 镜头 {sid}\n场景：S01 桌侧\n预计时长：{t}\n\n#### 原剧本段落\n\n```text\n甲：不要。\n```\n\n#### 运镜＋主画面描述\n\n```text\n【平视，近景，固定镜头】\n甲（画内）：“不要。”  乙尚未接匣。\n```\n\n#### 备注\n\n```text\n```\n'
    return text


class MasterTests(unittest.TestCase):
    def parse(self,text):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'master.md';p.write_bytes(text.encode());before=p.read_bytes();data=parse_master(p,'director')
            self.assertEqual(p.read_bytes(),before);return data
    def test_identity_and_literal(self):
        data=self.parse(fixture());self.assertEqual([s['id'] for s in data['shots']],['01','07A'])
        self.assertIn('”  乙',data['shots'][0]['body']);self.assertEqual(data['shots'][0]['source_text'],'甲：不要。')
    def test_known_unknown(self):
        d=self.parse(fixture());self.assertIsNone(d['statistics']['total_duration_seconds']);self.assertEqual(d['statistics']['known_duration_seconds'],'4.125')
    def test_crlf_and_multiline(self):
        a=self.parse(fixture());b=self.parse(fixture().replace('\n','\r\n'));self.assertEqual(a['shots'],b['shots'])
    def test_long_body_preserved(self):
        value='仍由甲持有。\n'*1000;d=self.parse(fixture().replace('甲（画内）：“不要。”  乙尚未接匣。',value));self.assertEqual(d['shots'][0]['body'].count('仍由甲持有。'),1000)
    def test_finite_positive_durations(self):
        for value in ['0','-2','nan','inf','True']:
            with self.subTest(value=value),self.assertRaises(FormatError):duration(value,'fixture')
    def test_duplicate_id_error(self):
        with self.assertRaises(FormatError):self.parse(fixture(ids=('01','01')))
    def test_fenced_headings_not_structure(self):
        d=Document('# 标题\n## 正文\n```text\n# 不是真标题\n```\n');self.assertEqual(len(d.headings),2)
    def test_save_does_not_replace(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'result.json';save_exclusive(p,b'old');save_exclusive(p,b'old')
            with self.assertRaises(FileExistsError):save_exclusive(p,b'new')
            self.assertEqual(p.read_bytes(),b'old')
    def test_unchanged_parser_blob(self):
        b=(Path(__file__).resolve().parents[1]/'scripts/master_io.py').read_bytes()
        self.assertEqual(hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest(),'88fa186c4f7be012023e5e2b9d135a331dcfe63c')


if __name__=='__main__':unittest.main()
